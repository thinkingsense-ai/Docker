# Minimal single-VPC network: one public subnet for both the GKE nodes and control-plane traffic.
# Simplest thing that works for a getting-started demo stack -- same posture as the OCI stack's
# network.tf (its comment applies here verbatim: "a production hardening pass would split this
# into a private worker subnet behind a NAT gateway"). Firewall rules below are intentionally
# permissive (0.0.0.0/0 on the NodePort range) for the same reason; the app itself requires a
# login for the Ask app and the wire ports are opt-in via var.expose_wire_protocols.

locals {
  name = "omnigate-gke"
}

resource "google_compute_network" "this" {
  project                 = var.gcp_project_id
  name                    = local.name
  auto_create_subnetworks = false
}

# VPC-native (alias IP) GKE requires the subnet to carry secondary ranges for pod and Service IPs
# up front -- unlike AWS's VPC CNI, which hands out pod IPs from the same subnet as the node.
resource "google_compute_subnetwork" "nodes" {
  project       = var.gcp_project_id
  name          = "${local.name}-nodes"
  region        = var.gcp_region
  network       = google_compute_network.this.id
  ip_cidr_range = "10.0.0.0/20"

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.4.0.0/14"
  }
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.0.16.0/20"
  }
}

# Node-to-node and pod-to-pod traffic across the whole VPC-native address space -- the direct
# analog of the OCI stack's `oci_core_security_list.nodes` "protocol = all, source = 10.0.0.0/16"
# rule. A custom (non-default) VPC has no implied "allow internal" rule the way the GCP default
# network does, so this has to be created explicitly.
resource "google_compute_firewall" "internal" {
  project = var.gcp_project_id
  name    = "${local.name}-allow-internal"
  network = google_compute_network.this.id

  source_ranges = [
    google_compute_subnetwork.nodes.ip_cidr_range,
    google_compute_subnetwork.nodes.secondary_ip_range[0].ip_cidr_range,
    google_compute_subnetwork.nodes.secondary_ip_range[1].ip_cidr_range,
  ]

  allow {
    protocol = "all"
  }
}

# Google's documented health-check source ranges for the external passthrough Network Load
# Balancer -- see https://cloud.google.com/load-balancing/docs/health-checks#fw-rule. Targets the
# whole dynamically-allocated NodePort range (30000-32767) rather than a specific port, same
# reasoning as the OCI stack's NodePort-range rule: a Kubernetes Service of type=LoadBalancer
# allocates NodePorts dynamically unless pinned.
resource "google_compute_firewall" "health_check" {
  project       = var.gcp_project_id
  name          = "${local.name}-allow-health-check"
  network       = google_compute_network.this.id
  source_ranges = ["130.211.0.0/22", "35.191.0.0/16"]

  allow {
    protocol = "tcp"
    ports    = ["30000-32767"]
  }
}

# Public client traffic to the LoadBalancer -- GCP's external passthrough LB preserves the
# client's real source IP and forwards straight to the node's NodePort, so (unlike an AWS NLB,
# which is its own hop with its own security group) this node-level firewall rule is the only
# place that traffic is actually filtered.
resource "google_compute_firewall" "client_ingress" {
  project       = var.gcp_project_id
  name          = "${local.name}-allow-client-ingress"
  network       = google_compute_network.this.id
  source_ranges = ["0.0.0.0/0"]

  allow {
    protocol = "tcp"
    ports    = ["30000-32767"]
  }
}
