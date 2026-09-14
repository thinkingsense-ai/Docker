# Computes OMNIGATE_APP_USERS server-side during apply, so deployers never need local Docker or
# to hand-assemble a "username:saltB64:hashB64::" string themselves -- confirmed live to be the
# single biggest source of confusion in this wizard. Verified the OCI Resource Manager job runner
# has network egress, a JRE, and python3 already available (no Docker/Podman needed), so this
# downloads the exact release jar matching var.image_tag and runs its own PasswordHash utility,
# the same class the app itself uses to verify logins -- guaranteeing the hash format always
# matches whatever's actually deployed, rather than a separately-maintained reimplementation of
# the hashing algorithm risking a subtle mismatch.
#
# A "data" source, not a null_resource + local_file: that combination was the first version of
# this file, and it broke on `destroy` -- confirmed live. Each Resource Manager job (plan, apply,
# destroy) gets a fresh extraction of the config, so a file a local-exec provisioner wrote during
# an earlier `apply` job simply doesn't exist when a later `destroy` job's `data.local_file` tries
# to read it, and unlike a resource's provisioners, a data source is always read regardless of
# operation. `data "external"` has no such gap: its program re-runs fresh on every plan/apply/
# destroy and returns its result directly, with nothing written to disk to go stale. Password
# is passed via `query` (JSON on stdin) and parsed with python3, not hand-rolled shell/sed
# string extraction, so quotes/backslashes/unicode in a real password can't break the parse.
data "external" "app_password_hash" {
  program = ["bash", "-c", <<-EOT
    set -e
    PASSWORD=$(python3 -c "import json,sys; print(json.load(sys.stdin)['password'], end='')")
    curl -fsSL -o /tmp/omnigate-hash-tool.jar \
      "https://github.com/thinkingsense-ai/Docker/releases/download/${var.image_tag}/omnigate.jar" 1>&2
    HASH=$(java -cp /tmp/omnigate-hash-tool.jar com.omnigate.http.auth.PasswordHash "$PASSWORD")
    rm -f /tmp/omnigate-hash-tool.jar
    python3 -c "import json,sys; print(json.dumps({'hash': sys.argv[1]}))" "$HASH"
  EOT
  ]

  query = {
    password = var.omnigate_app_password
  }
}

locals {
  # "username:saltB64:hashB64::" -- the exact OMNIGATE_APP_USERS format the app expects.
  omnigate_app_users_computed = "${var.omnigate_app_username}:${data.external.app_password_hash.result.hash}::"
}
