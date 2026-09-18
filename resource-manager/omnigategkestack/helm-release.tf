# Both providers authenticate against the cluster this same apply just created, using a
# short-lived access token from data.google_client_config (gke.tf) -- the standard pattern for
# GKE + Terraform's kubernetes/helm providers, the direct analog of the OCI stack's `oci ce
# cluster generate-token` exec-plugin approach. Cloud Shell (this stack's documented deploy path)
# already has an active gcloud auth session, so this works without a separately-managed kubeconfig
# or long-lived cluster credential.

provider "kubernetes" {
  host                   = "https://${google_container_cluster.this.endpoint}"
  cluster_ca_certificate = base64decode(google_container_cluster.this.master_auth[0].cluster_ca_certificate)
  token                  = data.google_client_config.default.access_token
}

provider "helm" {
  kubernetes {
    host                   = "https://${google_container_cluster.this.endpoint}"
    cluster_ca_certificate = base64decode(google_container_cluster.this.master_auth[0].cluster_ca_certificate)
    token                  = data.google_client_config.default.access_token
  }
}

resource "helm_release" "omnigate" {
  name       = "omnigate"
  chart      = "${path.module}/helm/omnigate"
  timeout    = 600
  depends_on = [google_container_node_pool.this]

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
