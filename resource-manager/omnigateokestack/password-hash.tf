# Computes OMNIGATE_APP_USERS server-side during apply, so deployers never need local Docker or
# to hand-assemble a "username:saltB64:hashB64::" string themselves -- confirmed live to be the
# single biggest source of confusion in this wizard. Verified the OCI Resource Manager job runner
# has network egress and a JRE already available (no Docker/Podman needed for this specific path),
# so this downloads the exact release jar matching var.image_tag and runs its own PasswordHash
# utility, the same class the app itself uses to verify logins -- guaranteeing the hash format
# always matches whatever's actually deployed, rather than a separately-maintained reimplementation
# of the hashing algorithm risking a subtle mismatch.
resource "null_resource" "app_password_hash" {
  triggers = {
    # Re-run if the password or the deployed image version changes; sha256 of the password avoids
    # putting the plaintext itself in a trigger value (triggers land in state either way, same as
    # the var.omnigate_app_password sensitive variable already does, but no reason to duplicate it).
    password_sha256 = sha256(var.omnigate_app_password)
    image_tag       = var.image_tag
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      curl -fsSL -o /tmp/omnigate-hash-tool.jar \
        "https://github.com/thinkingsense-ai/Docker/releases/download/${var.image_tag}/omnigate.jar"
      java -cp /tmp/omnigate-hash-tool.jar com.omnigate.http.auth.PasswordHash "$OMNIGATE_APP_PASSWORD" \
        > "${path.module}/.app_password_hash"
      rm -f /tmp/omnigate-hash-tool.jar
    EOT
    environment = {
      # Passed via environment, not inlined in the command string, so it never appears in the
      # "Executing: [...]" line Terraform echoes to the job log.
      OMNIGATE_APP_PASSWORD = var.omnigate_app_password
    }
  }
}

data "local_file" "app_password_hash" {
  filename   = "${path.module}/.app_password_hash"
  depends_on = [null_resource.app_password_hash]
}

locals {
  # "username:saltB64:hashB64::" -- the exact OMNIGATE_APP_USERS format the app expects.
  omnigate_app_users_computed = "${var.omnigate_app_username}:${trimspace(data.local_file.app_password_hash.content)}::"
}
