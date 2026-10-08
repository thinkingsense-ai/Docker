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
    INPUT=$(cat)
    PASSWORD=$(printf '%s' "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin)['password'], end='')")
    ADMIN_PASSWORD=$(printf '%s' "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin)['admin_password'], end='')")
    fetch_latest_release_jar_url() {
      python3 -c "
import json, urllib.request
with urllib.request.urlopen('https://api.github.com/repos/thinkingsense-ai/Docker/releases/latest', timeout=15) as r:
    release = json.load(r)
for asset in release.get('assets', []):
    if asset['name'] == 'omnigate.jar':
        print(asset['browser_download_url'])
        break
else:
    raise SystemExit('omnigate.jar asset not found on latest GitHub release')
"
    }
    # var.image_tag is the OCIR *docker* tag, which isn't necessarily a real thinkingsense-ai/
    # Docker GitHub release tag -- true for the literal "latest" (no release is ever named that),
    # and confirmed live also true for any custom/private image tag (e.g. an internal commercial
    # test build pushed straight to OCIR under its own tag, never published as a GitHub release at
    # all -- "External Program Execution Failed" from a 404, breaking the whole apply before any
    # real infrastructure is touched). Try the direct release-tag download first (the fast path
    # for a real versioned release); silently fall back to whatever GitHub currently calls
    # "latest" if that fails for any reason, rather than hard-failing -- PasswordHash's algorithm
    # is stable across editions/builds, so any reasonably current jar produces the same hash
    # format the app expects.
    # Base version first: strip any build suffix so a custom image tag like v0.10.3-hotfix still
    # hashes with the matching release jar (v0.10.3) instead of whatever "latest" happens to be.
    BASE_TAG=$(printf '%s' "${var.image_tag}" | sed -E 's/^(v[0-9]+\.[0-9]+\.[0-9]+).*/\1/')
    if [ "${var.image_tag}" != "latest" ] && curl -fsSL -o /tmp/omnigate-hash-tool.jar "https://github.com/thinkingsense-ai/Docker/releases/download/$BASE_TAG/omnigate.jar" 2>/dev/null; then
      : # release-tag download succeeded
    else
      JAR_URL=$(fetch_latest_release_jar_url)
      curl -fsSL -o /tmp/omnigate-hash-tool.jar "$JAR_URL" 1>&2
    fi
    HASH=$(java -cp /tmp/omnigate-hash-tool.jar com.omnigate.http.auth.PasswordHash "$PASSWORD")
    ADMIN_HASH=$(java -cp /tmp/omnigate-hash-tool.jar com.omnigate.http.auth.PasswordHash "$ADMIN_PASSWORD")
    rm -f /tmp/omnigate-hash-tool.jar
    python3 -c "import json,sys; print(json.dumps({'hash': sys.argv[1], 'admin_hash': sys.argv[2]}))" "$HASH" "$ADMIN_HASH"
  EOT
  ]

  query = {
    password = var.omnigate_app_password
    # Blank means "use the Ask-app password for the admin login too" (see omnigate_admin_password).
    admin_password = var.omnigate_admin_password != "" ? var.omnigate_admin_password : var.omnigate_app_password
  }
}

locals {
  # "username:saltB64:hashB64::" -- the exact OMNIGATE_APP_USERS format the app expects.
  omnigate_app_users_computed = "${var.omnigate_app_username}:${data.external.app_password_hash.result.hash}::"

  # "username:saltB64:hashB64:admin" -- OMNIGATE_AUTH_USERS. Setting it turns admin authentication ON, which is
  # the point: without it the admin console, /api/query and /mcp are open to anyone who can reach the load balancer.
  omnigate_auth_users_computed = "${var.omnigate_admin_username}:${data.external.app_password_hash.result.admin_hash}:admin"
}
