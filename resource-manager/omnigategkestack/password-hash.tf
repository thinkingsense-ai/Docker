# Computes OMNIGATE_APP_USERS server-side during apply, identical in spirit and almost identical
# in implementation to the OCI stack's password-hash.tf -- see that file for the full reasoning on
# why this is a `data "external"` source (not a null_resource + local_file, which breaks on
# `destroy`: each Cloud Shell/CI run gets a fresh checkout, so a file a local-exec provisioner
# wrote during an earlier `apply` doesn't exist when a later `destroy` tries to read it).
#
# Requires curl, java (a JRE), and python3 on whatever machine runs `terraform apply` -- Cloud
# Shell (this stack's documented deploy path, see tutorial.md) has all three preinstalled, same as
# the OCI Resource Manager job runner did for the OCI stack.
data "external" "app_password_hash" {
  program = ["bash", "-c", <<-EOT
    set -e
    # Homebrew's openjdk formula is keg-only (deliberately not symlinked onto PATH, to avoid
    # clashing with macOS's own /usr/bin/java stub) -- confirmed live on a real deploy attempt.
    # `command -v java` is NOT a safe existence check here: the macOS stub is still found by it,
    # then fails only when actually invoked (it just pops an "install Java" prompt and exits
    # nonzero). So prefer a real Homebrew JDK on PATH unconditionally whenever one is present,
    # rather than only falling back to it when nothing resolves at all.
    for candidate in /opt/homebrew/opt/openjdk/bin /usr/local/opt/openjdk/bin; do
      if [ -x "$candidate/java" ]; then
        export PATH="$candidate:$PATH"
        break
      fi
    done
    PASSWORD=$(python3 -c "import json,sys; print(json.load(sys.stdin)['password'], end='')")
    # var.image_tag is the Artifact Registry *docker* tag (default "latest"), which is not itself
    # a GitHub release tag -- there is no release literally named "latest". When it's an actual
    # version (e.g. "v0.6.0") matching a real release, use it directly; otherwise resolve the
    # GitHub API's own "latest release" so the jar always matches whatever :latest currently
    # points at -- same fix as the OCI stack's identical comment/bug (a plain
    # releases/download/latest/omnigate.jar URL 404s).
    if [ "${var.image_tag}" = "latest" ]; then
      JAR_URL=$(python3 -c "
import json, urllib.request
with urllib.request.urlopen('https://api.github.com/repos/thinkingsense-ai/Docker/releases/latest', timeout=15) as r:
    release = json.load(r)
for asset in release.get('assets', []):
    if asset['name'] == 'omnigate.jar':
        print(asset['browser_download_url'])
        break
else:
    raise SystemExit('omnigate.jar asset not found on latest GitHub release')
")
    else
      JAR_URL="https://github.com/thinkingsense-ai/Docker/releases/download/${var.image_tag}/omnigate.jar"
    fi
    curl -fsSL -o /tmp/omnigate-hash-tool.jar "$JAR_URL" 1>&2
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
