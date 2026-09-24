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

# Deletes stray PVCs before the cluster is torn down, so their backing block volumes actually
# get reclaimed instead of orphaned. `helm uninstall` deletes the StatefulSet but deliberately
# leaves its volumeClaimTemplates-created PVCs behind (standard Kubernetes data-safety behavior)
# -- left alone that's permanent, since once `terraform destroy` reaches the cluster/node pool
# next, the CSI driver is gone too and nothing ever processes the PVC's deletion. Confirmed live:
# seven abandoned 50GB block volumes (350GB) from past test destroys, silently exceeding the
# tenancy's 200GB Always Free block-storage cap and blocking every later deploy's own volume
# provisioning until manually cleaned up.
#
# `depends_on` here is load-bearing for ordering, not just "needs the node pool to exist":
# destroy-time provisioners run right before their own resource is torn down, and Terraform
# destroys dependents before what they depend on. So this resource must be created (and thus
# destroyed) strictly *between* helm_release and the node pool -- depends_on the node pool (so
# it's destroyed before the node pool, while the cluster/CSI driver are still alive) while
# helm_release depends on THIS resource instead of the node pool directly (so helm is fully
# uninstalled -- and its Pods released their PVCs -- before this runs; deleting a PVC still in
# use by a live Pod hangs on Kubernetes' own pvc-protection finalizer).
resource "null_resource" "cleanup_pvcs" {
  depends_on = [oci_containerengine_node_pool.this]

  triggers = {
    cluster_id = oci_containerengine_cluster.this.id
    region     = var.region
  }

  provisioner "local-exec" {
    when    = destroy
    # `|| true` throughout: this is best-effort cleanup, not a required step -- a missing
    # kubectl binary or an already-gone cluster must never block the rest of the destroy.
    command = <<-EOT
      oci ce cluster create-kubeconfig --cluster-id ${self.triggers.cluster_id} --region ${self.triggers.region} --file /tmp/omnigate-destroy-kubeconfig --token-version 2.0.0 || true
      KUBECONFIG=/tmp/omnigate-destroy-kubeconfig kubectl delete pvc --all --all-namespaces --wait=true --timeout=120s || true
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
  set_sensitive {
    name  = "omnigate.appUsers"
    value = local.omnigate_app_users_computed
  }
  set {
    name  = "omnigate.exposeWireProtocols"
    value = var.expose_wire_protocols
  }
  set {
    name  = "omnigate.replicaCount"
    value = var.omnigate_replica_count
  }
  # configDb.external is derived, not a separate variable: true the moment a real config-DB URL
  # is supplied, so a deployer setting omnigate_replica_count > 1 without also filling in the
  # config-DB variables gets the chart's own real `required` validation error (see
  # helm/omnigate/templates/secrets.yaml) instead of a silently-ignored setting.
  set {
    name  = "omnigate.configDb.external"
    value = var.omnigate_config_db_url != ""
  }
  set {
    name  = "omnigate.configDb.configDbUrl"
    value = var.omnigate_config_db_url
  }
  set {
    name  = "omnigate.configDb.configDbUser"
    value = var.omnigate_config_db_user
  }
  set_sensitive {
    name  = "omnigate.configDb.configDbPassword"
    value = var.omnigate_config_db_password
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
