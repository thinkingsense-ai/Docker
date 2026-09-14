data "oci_containerengine_cluster_option" "this" {
  cluster_option_id = "all"
}

resource "oci_containerengine_cluster" "this" {
  compartment_id = var.compartment_ocid
  name           = "omnigate-oke"
  vcn_id         = oci_core_vcn.this.id
  # "BASIC_CLUSTER" is the free-control-plane tier -- the only one within Always Free.
  type = "BASIC_CLUSTER"
  kubernetes_version = data.oci_containerengine_cluster_option.this.kubernetes_versions[
    length(data.oci_containerengine_cluster_option.this.kubernetes_versions) - 1
  ]

  endpoint_config {
    is_public_ip_enabled = true
    subnet_id            = oci_core_subnet.k8s_api.id
  }

  options {
    service_lb_subnet_ids = [oci_core_subnet.lb.id]
    kubernetes_network_config {
      pods_cidr     = "10.244.0.0/16"
      services_cidr = "10.96.0.0/16"
    }
  }
}

resource "oci_containerengine_node_pool" "this" {
  compartment_id     = var.compartment_ocid
  cluster_id         = oci_containerengine_cluster.this.id
  name               = "omnigate-pool"
  node_shape         = "VM.Standard.A1.Flex"
  kubernetes_version = oci_containerengine_cluster.this.kubernetes_version

  node_shape_config {
    ocpus         = var.node_ocpus
    memory_in_gbs = var.node_memory_gb
  }

  node_source_details {
    source_type             = "IMAGE"
    image_id                = data.oci_containerengine_node_pool_option.this.sources[0].image_id
    boot_volume_size_in_gbs = var.node_boot_volume_gb
  }

  node_config_details {
    size = var.node_pool_size
    placement_configs {
      availability_domain = data.oci_identity_availability_domains.this.availability_domains[0].name
      subnet_id           = oci_core_subnet.nodes.id
    }
  }
}

data "oci_containerengine_node_pool_option" "this" {
  # "all" (not a specific cluster id) -- this must resolve on a first-ever plan, before the
  # cluster this stack is about to create exists yet. Scoping it to
  # oci_containerengine_cluster.this.id instead hung for minutes against a real tenancy: the API
  # has nothing to answer with for a cluster ID that doesn't exist until apply.
  node_pool_option_id = "all"
}

data "oci_identity_availability_domains" "this" {
  compartment_id = var.compartment_ocid
}

data "oci_containerengine_cluster_kube_config" "this" {
  cluster_id = oci_containerengine_cluster.this.id
}
