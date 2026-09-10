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
  # NodePort range -- the NLB's *internal* hop to the node (its own backend-to-node traffic, not
  # what an external client connects to). Confirmed live this is NOT sufficient by itself: the NLB
  # additionally needs its own listener port and health-check port open below, or the backend
  # never gets marked healthy / the listener drops all inbound traffic with a silent timeout.
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options {
      min = 30000
      max = 32767
    }
  }
  # OCI's NLB health-checks each backend via this exact port/path (kube-proxy's health endpoint)
  # regardless of the Service's externalTrafficPolicy. Missing this, the backend is marked
  # unhealthy and the NLB drops all traffic -- confirmed live, and easy to miss because the error
  # is a silent connection timeout at the LB, not an explicit error anywhere.
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options {
      min = 10256
      max = 10256
    }
  }
  # The actual public listener ports on the LB subnet (Ask app, and the wire-protocol NLB's
  # ports when exposeWireProtocols=true) -- distinct from the NodePort range above. Confirmed
  # live that opening only the NodePort range is NOT enough: clients connect to the LB on these
  # ports directly, and without an explicit rule here that inbound connection is silently dropped
  # (a bare connection timeout, not a clear error) even though the NodePort hop itself works fine.
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options {
      min = 8081
      max = 8081
    }
  }
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options {
      min = 1521
      max = 1521
    }
  }
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options {
      min = 5433
      max = 5433
    }
  }
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options {
      min = 3306
      max = 3306
    }
  }
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options {
      min = 7070
      max = 7070
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

  # NOTE: OKE's own LoadBalancer controller (cloud-controller-manager) also mutates this exact
  # security list, adding/removing a narrow per-NodePort rule as Services of type LoadBalancer
  # come and go. Our own 30000-32767 ingress rule above already covers the full NodePort range,
  # so that CCM-managed rule is redundant for connectivity -- a plain `terraform plan` may show a
  # 1-rule diff wanting to prune it, which is harmless to apply. Deliberately NOT using
  # `lifecycle { ignore_changes = [ingress_security_rules] }` here even though it would silence
  # that diff: confirmed live that doing so also silently blocks any *legitimate* future edit to
  # this rule list from ever being applied through Terraform again.
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
  security_list_ids          = [oci_core_security_list.nodes.id]
  prohibit_public_ip_on_vnic = false
}
