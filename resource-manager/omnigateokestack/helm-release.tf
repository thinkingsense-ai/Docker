# Both providers authenticate against the cluster this same apply just created, using the OCI
# CLI's own token-generating exec plugin (the standard pattern for OKE + Terraform's
# kubernetes/helm providers -- Resource Manager's runner ships the OCI CLI precisely so this
# works without a separately-managed kubeconfig or long-lived cluster credential). Verify this
# resolves cleanly on a real `terraform plan` in Resource Manager (Phase E) -- it's the one piece
# of this stack that depends on tooling inside ORM's execution environment rather than the OCI
# Terraform provider alone.
locals {
  kube_config    = yamldecode(data.oci_containerengine_cluster_kube_config.this.content)
  cluster_server = local.kube_config.clusters[0].cluster.server
  cluster_ca     = local.kube_config.clusters[0].cluster["certificate-authority-data"]
}

provider "kubernetes" {
  host                   = local.cluster_server
  cluster_ca_certificate = base64decode(local.cluster_ca)
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "oci"
    args        = ["ce", "cluster", "generate-token", "--cluster-id", oci_containerengine_cluster.this.id, "--region", var.region]
  }
}

provider "helm" {
  kubernetes {
    host                   = local.cluster_server
    cluster_ca_certificate = base64decode(local.cluster_ca)
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "oci"
      args        = ["ce", "cluster", "generate-token", "--cluster-id", oci_containerengine_cluster.this.id, "--region", var.region]
    }
  }
}

resource "helm_release" "omnigate" {
  name       = "omnigate"
  chart      = "${path.module}/helm/omnigate"
  timeout    = 600
  depends_on = [oci_containerengine_node_pool.this]

  set {
    name  = "image.repository"
    value = var.image_repository
  }
  set {
    name  = "image.tag"
    value = var.image_tag
  }
  set_sensitive {
    name  = "omnigate.llmApiKey"
    value = var.omnigate_llm_api_key
  }
  set {
    name  = "omnigate.llmModel"
    value = var.omnigate_llm_model
  }
  set_sensitive {
    name  = "omnigate.appUsers"
    value = local.omnigate_app_users_computed
  }
  set {
    name  = "omnigate.exposeWireProtocols"
    value = var.expose_wire_protocols
  }
  set {
    name  = "omnigate.dataVolumeSize"
    value = "${var.omnigate_data_storage_gb}Gi"
  }
  set {
    name  = "postgres.storageSize"
    value = "${var.postgres_storage_gb}Gi"
  }
}
