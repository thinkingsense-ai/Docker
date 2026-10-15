data "oci_containerengine_cluster_option" "this" {
  cluster_option_id = "all"
}

locals {
  # Auto-raised, not just documented: confirmed live that leaving node_pool_size at its default
  # while raising omnigate_replica_count schedules fine for the first couple of replicas, then
  # the next pod sits Pending forever ("Insufficient cpu") since there's nowhere left to place it
  # -- a real, reproducible footgun a deployer would only discover after Apply already reports
  # success (helm_release itself times out waiting for a pod that can never schedule). One
  # replica reasonably fits on one node given this stack's default node_ocpus/node_memory_gb
  # sizing, so the minimum sensible node count is exactly the replica count -- never lower it
  # below whatever the deployer explicitly asked for, only raise it when it's short.
  effective_node_pool_size = max(var.node_pool_size, var.omnigate_replica_count)
}

locals {
  # Arm (Ampere A1) node images, not GPU, and the Kubernetes versions that have at least one. Oracle's list of cluster versions is
  # ascending and sometimes runs ahead of its node images, and its list of images is newest-build-first but mixes every Kubernetes
  # version: taking "the last version" with "the first image" made a cluster at one version and a node image at another, which
  # Oracle rejects ("Kubernetes version does not match Kubernetes version of OKE worker node image", seen when v1.37.0 appeared
  # while the first image was for v1.36.4).
  arm_sources = [
    for src in data.oci_containerengine_node_pool_option.this.sources : src
    if length(regexall("aarch64", src.source_name)) > 0 && length(regexall("GPU", src.source_name)) == 0
  ]
  versions_with_arm_image = [
    for v in data.oci_containerengine_cluster_option.this.kubernetes_versions : v
    if length([
      for src in local.arm_sources : src
      if length(regexall("-OKE-${replace(trimprefix(v, "v"), ".", "\\.")}-[0-9]+$", src.source_name)) > 0
    ]) > 0
  ]
  # Pinned by default (reproducible, like image_tag); "" means the newest version that has an arm image.
  kubernetes_version = var.kubernetes_version != "" ? var.kubernetes_version : element(local.versions_with_arm_image, length(local.versions_with_arm_image) - 1)
  # The newest build (Oracle lists newest first) of the image for exactly that version.
  node_images = [
    for src in local.arm_sources : src.image_id
    if length(regexall("-OKE-${replace(trimprefix(local.kubernetes_version, "v"), ".", "\\.")}-[0-9]+$", src.source_name)) > 0
  ]
  node_image_id = local.node_images[0]
}

resource "oci_containerengine_cluster" "this" {
  compartment_id = var.compartment_ocid
  name           = "omnigate-oke"
  vcn_id         = oci_core_vcn.this.id
  # "BASIC_CLUSTER" is the free-control-plane tier -- the only one within Always Free.
  type = "BASIC_CLUSTER"

  lifecycle {
    precondition {
      condition     = length(local.node_images) > 0
      error_message = "Kubernetes ${local.kubernetes_version} has no Arm worker-node image in this region right now. Choose one of: ${join(", ", local.versions_with_arm_image)} (set kubernetes_version, or leave it blank for the newest)."
    }
  }
  kubernetes_version = local.kubernetes_version

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
    image_id                = local.node_image_id
    boot_volume_size_in_gbs = var.node_boot_volume_gb
  }

  node_config_details {
    size = local.effective_node_pool_size
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
