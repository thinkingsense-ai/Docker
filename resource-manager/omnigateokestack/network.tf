# Minimal single-VCN network: public subnets for both the OKE API endpoint and worker nodes.
# Simplest thing that works for a getting-started / Marketplace demo stack -- a production
# hardening pass would split this into a private worker subnet behind a NAT gateway. Security
# lists below are intentionally permissive (0.0.0.0/0) for the same reason; the app itself
# requires a login for the Ask app and the wire ports are opt-in via var.expose_wire_protocols.

resource "oci_core_vcn" "this" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.0.0.0/16"]
  display_name   = "omnigate-vcn"
  dns_label      = "omnigatevcn"
}

resource "oci_core_internet_gateway" "this" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.this.id
  display_name   = "omnigate-igw"
}

# A Service Gateway (for reaching Oracle Services Network without a public IP) is only needed
# for private worker subnets -- these subnets already have full internet access via the Internet
# Gateway below, which already reaches Oracle Services' public endpoints. OCI's route table
# validation also rejects an IGW route and a Service-Gateway "All Services" route coexisting in
# the same table (confirmed live: "Internet Gateway target cannot be used together with Service
# Gateway target for All Services"), so adding one here would be both unnecessary and broken.

resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.this.id
  display_name   = "omnigate-public-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_internet_gateway.this.id
  }
}

resource "oci_core_security_list" "k8s_api" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.this.id
  display_name   = "omnigate-k8s-api-seclist"

  ingress_security_rules {
    protocol = "6" # TCP
    source   = "0.0.0.0/0"
    tcp_options {
      min = 6443
      max = 6443
    }
  }
  # Also required (not just 6443) for worker-to-API-endpoint registration -- OKE's own
  # documented requirement; missing this caused a real node registration timeout.
  ingress_security_rules {
    protocol = "6" # TCP
    source   = "10.0.0.0/16"
    tcp_options {
      min = 12250
      max = 12250
    }
  }
  # Path MTU discovery -- OKE explicitly documents this as required for node registration.
  ingress_security_rules {
    protocol = "1" # ICMP
    source   = "0.0.0.0/0"
    icmp_options {
      type = 3
      code = 4
    }
  }
  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
}

resource "oci_core_security_list" "nodes" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.this.id
  display_name   = "omnigate-nodes-seclist"

  # Intra-VCN: node-to-node (pod networking, kube-proxy, etc.) and control-plane-to-node.
  ingress_security_rules {
    protocol = "all"
    source   = "10.0.0.0/16"
  }
  # NodePort range -- the LB talks to node ports over the VCN once traffic reaches a node.
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options {
      min = 30000
      max = 32767
    }
  }
  # Path MTU discovery -- OKE explicitly documents this as required for node registration.
  ingress_security_rules {
    protocol = "1" # ICMP
    source   = "0.0.0.0/0"
    icmp_options {
      type = 3
      code = 4
    }
  }
  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }

  # OKE's own LoadBalancer controller (cloud-controller-manager) mutates this exact security
  # list directly, adding/removing a narrow per-NodePort rule as Services of type LoadBalancer
  # come and go -- confirmed live (a rule for the LB's actual NodePort 30767 appeared here on its
  # own). Our own 30000-32767 ingress rule above already covers the full NodePort range, so that
  # CCM-managed rule is redundant for connectivity, but without this Terraform fights the
  # controller every apply trying to prune it back to exactly what's declared here.
  lifecycle {
    ignore_changes = [ingress_security_rules]
  }
}

resource "oci_core_security_list" "lb" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.this.id
  display_name   = "omnigate-lb-seclist"

  # Intra-VCN: LB-to-node NodePort traffic and control-plane reachability.
  ingress_security_rules {
    protocol = "all"
    source   = "10.0.0.0/16"
  }
  # OmniGate's HTTP port (Ask app + admin console) -- the NLB's own public listener sits in this
  # subnet, and OCI Network Load Balancers enforce their own subnet's security lists on the
  # frontend listener, not just on the node-facing hop. Deliberately a SEPARATE security list
  # from oci_core_security_list.nodes (not shared, as an earlier version of this file did):
  # that list has `lifecycle { ignore_changes = [ingress_security_rules] }` to avoid fighting
  # OKE's cloud-controller-manager, which also means Terraform silently never applies rule
  # changes to it on subsequent applies -- confirmed live, this rule was added to that list's
  # .tf source and a real `terraform apply` reported success while adding nothing. This
  # dedicated list has no such lifecycle block, so it's actually managed.
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options {
      min = 8080
      max = 8080
    }
  }
  # Wire-protocol ports (Oracle/Postgres/MySQL/gRPC) -- only opened when the second NLB is
  # actually created (var.expose_wire_protocols), same reasoning as the HTTP rule above.
  dynamic "ingress_security_rules" {
    for_each = var.expose_wire_protocols ? [1521, 5433, 3306, 7070] : []
    content {
      protocol = "6"
      source   = "0.0.0.0/0"
      tcp_options {
        min = ingress_security_rules.value
        max = ingress_security_rules.value
      }
    }
  }
  # Path MTU discovery -- OKE explicitly documents this as required for node registration.
  ingress_security_rules {
    protocol = "1" # ICMP
    source   = "0.0.0.0/0"
    icmp_options {
      type = 3
      code = 4
    }
  }
  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
}

resource "oci_core_subnet" "k8s_api" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.this.id
  cidr_block                 = "10.0.0.0/28"
  display_name               = "omnigate-k8s-api-subnet"
  dns_label                  = "k8sapi"
  route_table_id             = oci_core_route_table.public.id
  security_list_ids          = [oci_core_security_list.k8s_api.id]
  prohibit_public_ip_on_vnic = false
}

resource "oci_core_subnet" "nodes" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.this.id
  cidr_block                 = "10.0.16.0/20"
  display_name               = "omnigate-nodes-subnet"
  dns_label                  = "nodes"
  route_table_id             = oci_core_route_table.public.id
  security_list_ids          = [oci_core_security_list.nodes.id]
  prohibit_public_ip_on_vnic = false
}

resource "oci_core_subnet" "lb" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.this.id
  cidr_block                 = "10.0.1.0/24"
  display_name               = "omnigate-lb-subnet"
  dns_label                  = "lb"
  route_table_id             = oci_core_route_table.public.id
  security_list_ids          = [oci_core_security_list.lb.id]
  prohibit_public_ip_on_vnic = false
}
