# A ZONAL (not regional) cluster is deliberate, not a shortcut: GCP waives the ~$74/mo cluster
# management fee for one zonal (or Autopilot) cluster per billing account, but charges it in full
# for a regional cluster -- the closest GCP gets to OKE's "BASIC_CLUSTER is the free-control-plane
# tier" default. Node compute itself is still real money either way -- see variables.tf's note on
# why this stack doesn't claim an OCI-style "Always Free" posture.

resource "google_container_cluster" "this" {
  project  = var.gcp_project_id
  name     = "omnigate-gke"
  location = "${var.gcp_region}-${var.gcp_zone_suffix}"

  network    = google_compute_network.this.id
  subnetwork = google_compute_subnetwork.nodes.id

  remove_default_node_pool = true
  initial_node_count       = 1

  networking_mode = "VPC_NATIVE"
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  deletion_protection = false

  depends_on = [
    google_compute_firewall.internal,
    google_compute_firewall.health_check,
    google_compute_firewall.client_ingress,
  ]
}

resource "google_container_node_pool" "this" {
  project    = var.gcp_project_id
  name       = "omnigate-pool"
  location   = google_container_cluster.this.location
  cluster    = google_container_cluster.this.name
  node_count = var.node_pool_size

  node_config {
    machine_type = var.node_machine_type
    disk_size_gb = var.node_boot_disk_gb

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]
  }
}

data "google_client_config" "default" {}
