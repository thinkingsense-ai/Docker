# Optional source-address allow-list for the public load balancers. A Network Load Balancer passes
# traffic through without the node-level security list ever seeing the client's address (confirmed live:
# restricting the node ports' source range changed nothing), so the restriction has to sit on the load
# balancer itself, as a network security group attached through the Service annotation.
locals {
  client_cidrs = compact(split(",", replace(var.allowed_client_cidrs, " ", "")))
  # Web port plus the opt-in wire-protocol ports.
  nlb_ports = [8080, 1521, 5433, 3306, 7070]
}

resource "oci_core_network_security_group" "nlb_clients" {
  count          = length(local.client_cidrs) > 0 ? 1 : 0
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.this.id
  display_name   = "omnigate-allowed-clients"
}

resource "oci_core_network_security_group_security_rule" "nlb_clients" {
  for_each = length(local.client_cidrs) > 0 ? { for pair in setproduct(local.client_cidrs, local.nlb_ports) : "${pair[0]}-${pair[1]}" => pair } : {}

  network_security_group_id = oci_core_network_security_group.nlb_clients[0].id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = each.value[0]
  source_type               = "CIDR_BLOCK"
  tcp_options {
    destination_port_range {
      min = each.value[1]
      max = each.value[1]
    }
  }
}
