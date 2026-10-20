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

# Deletes the PersistentVolumeClaims (and waits for their disks to go) on `terraform destroy`, while the cluster is still alive.
# The Postgres and OmniGate data volumes are PVCs the chart creates inside the cluster; Terraform does not track them, and
# deleting the cluster with live PVCs orphans their Persistent Disks, which then bill forever (thinkingsense-ai/Docker#83).
# helm_release depends on THIS resource so Helm is fully uninstalled first (deleting a PVC a live pod still uses hangs on
# Kubernetes' pvc-protection finalizer). Mirrors the OCI stack's cleanup_pvcs. Best effort: a missing gcloud/kubectl or an
# already-gone cluster must never block the rest of the destroy.
resource "null_resource" "cleanup_pvcs" {
  depends_on = [google_container_node_pool.this]

  triggers = {
    project  = var.gcp_project_id
    cluster  = google_container_cluster.this.name
    location = google_container_cluster.this.location
  }

  provisioner "local-exec" {
    when = destroy
    environment = {
      KUBECONFIG                 = "/tmp/omnigate-destroy-kubeconfig"
      USE_GKE_GCLOUD_AUTH_PLUGIN = "True"
    }
    command = <<-EOT
      gcloud container clusters get-credentials ${self.triggers.cluster} --location ${self.triggers.location} --project ${self.triggers.project} >/dev/null 2>&1 || { echo "cleanup_pvcs: cluster not reachable, skipping"; exit 0; }
      kubectl delete pvc --all --all-namespaces --wait=true --timeout=180s || true
      # The PVC object disappears first; the disk is deleted by the CSI driver just after. Wait for the volumes themselves.
      kubectl wait --for=delete pv --all --timeout=180s || true
      rm -f /tmp/omnigate-destroy-kubeconfig
    EOT
  }
}

resource "helm_release" "omnigate" {
  name       = "omnigate"
  chart      = "${path.module}/helm/omnigate"
  timeout    = 600
  depends_on = [null_resource.cleanup_pvcs]

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
  set {
    name  = "image.pullUsername"
    value = var.image_pull_username
  }
  set_sensitive {
    name  = "image.pullAuthToken"
    value = var.image_pull_auth_token
  }
  set_sensitive {
    name  = "omnigate.license"
    value = var.omnigate_license
  }
  set_sensitive {
    name  = "omnigate.authUsers"
    value = local.omnigate_auth_users_computed
  }
  set {
    name  = "seedDemoQuestions.enabled"
    value = "true"
  }
  set {
    name  = "seedDemoQuestions.adminUser"
    value = var.omnigate_admin_username
  }
  set_sensitive {
    name = "seedDemoQuestions.adminPassword"
    # The provider parses values like `helm --set`: a comma splits the value and a leading brace starts a list. Escape those
    # (and the backslash itself) so the password goes in byte for byte.
    type  = "string"
    value = replace(replace(replace(replace(var.omnigate_admin_password != "" ? var.omnigate_admin_password : var.omnigate_app_password, "\\", "\\\\"), ",", "\\,"), "{", "\\{"), "}", "\\}")
  }
  set {
    name  = "tls.enabled"
    value = var.enable_https
  }
  set {
    name  = "tls.httpsOnly"
    value = var.tls_https_only
  }
  set_sensitive {
    name  = "tls.keystore"
    value = var.tls_keystore_base64
  }
  set_sensitive {
    name  = "tls.keystorePassword"
    value = var.tls_keystore_password
  }
  set_sensitive {
    name  = "omnigate.adminApiToken"
    value = var.omnigate_admin_api_token
  }
  set {
    name  = "service.loadBalancerSourceRanges"
    value = "{${join(",", compact(split(",", replace(var.allowed_client_cidrs, " ", ""))))}}"
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
