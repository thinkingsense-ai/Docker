# Keeps an externally-provisioned Autonomous Database's IP access list in step with this stack's
# worker nodes. Opt-in: only active when omnigate_config_db_adb_ocid is set.
#
# Why this exists: every OKE node reaches the ADB from its own public IP (not a shared NAT), and
# those IPs change on every new deploy and every scale-up. Without this, a new pod's first
# connection is refused (ORA-12506) until someone whitelists its node by hand.

locals {
  manage_adb_acl = var.omnigate_config_db_adb_ocid != ""
}

# Runs on every apply, so scale-ups and node replacements are always covered.
# Deliberately has no destroy provisioner: a replacement would otherwise remove the still-valid
# IPs just before re-adding them, opening a window where running pods can't open connections.
resource "null_resource" "adb_acl_add" {
  count      = local.manage_adb_acl ? 1 : 0
  depends_on = [oci_containerengine_node_pool.this]

  # timestamp(), not a node-ID list: the node pool's `nodes` attribute still shows the OLD nodes at
  # plan time and only changes mid-apply on a scale-up, which Terraform rejects as an inconsistent
  # plan (confirmed live). Re-running every apply is cheap -- the script reads the live node IPs
  # and does nothing when the ACL is already right.
  triggers = {
    always = timestamp()
  }

  provisioner "local-exec" {
    command = "bash ${path.module}/scripts/adb-acl.sh add ${var.omnigate_config_db_adb_ocid} ${var.region} ${oci_containerengine_node_pool.this.id}"
  }
}

# Removes this stack's node IPs again at teardown. Triggers are static so it never re-runs on a
# scale change; it reads the node pool's live IPs at destroy time. `|| true`: best-effort, a
# failure here must not block the rest of the destroy.
resource "null_resource" "adb_acl_cleanup" {
  count      = local.manage_adb_acl ? 1 : 0
  depends_on = [oci_containerengine_node_pool.this, null_resource.adb_acl_add]

  triggers = {
    adb       = var.omnigate_config_db_adb_ocid
    region    = var.region
    node_pool = oci_containerengine_node_pool.this.id
    script    = "${path.module}/scripts/adb-acl.sh"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "bash ${self.triggers.script} remove ${self.triggers.adb} ${self.triggers.region} ${self.triggers.node_pool} || true"
  }
}
