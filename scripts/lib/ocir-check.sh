# Shared by the switch-edition-*.sh scripts: confirm a registry credential and image tag are good BEFORE changing a deployment,
# so a wrong or revoked token cannot roll out a pod that waits forever for an image it cannot pull.
OCIR_HOST=${OCIR_HOST:-phx.ocir.io}
OCIR_NAMESPACE=${OCIR_NAMESPACE:-ax8tpjdxhykk}
COMMERCIAL_REPO_PATH=$OCIR_NAMESPACE/omnigate-commercial
FREE_REPO=ocir.us-phoenix-1.oci.oraclecloud.com/$OCIR_NAMESPACE/omnigate
COMMERCIAL_REPO=ocir.us-phoenix-1.oci.oraclecloud.com/$COMMERCIAL_REPO_PATH

# check_commercial_pull <user> <token> <tag>   -> exits the script with a message when refused
check_commercial_pull() {
  local user=$1 token=$2 tag=$3 wa realm svc bt code
  wa=$(curl -s -m 15 -D - -o /dev/null "https://$OCIR_HOST/v2/" | tr -d '\r' | awk -F': ' 'tolower($1)=="www-authenticate"{print $2}')
  realm=$(echo "$wa" | sed -E 's/.*realm="([^"]*)".*/\1/'); svc=$(echo "$wa" | sed -E 's/.*service="([^"]*)".*/\1/')
  bt=$(curl -s -m 15 -u "$user:$token" "$realm?service=$svc&scope=repository:$COMMERCIAL_REPO_PATH:pull" | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))" 2>/dev/null || true)
  [ -n "$bt" ] || { echo "The registry rejected that pull user/token. Nothing was changed." >&2; exit 1; }
  code=$(curl -s -m 15 -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $bt" \
    -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.docker.distribution.manifest.list.v2+json' \
    "https://$OCIR_HOST/v2/$COMMERCIAL_REPO_PATH/manifests/$tag")
  [ "$code" = 200 ] || { echo "Commercial image $tag is not available to this credential (HTTP $code). Nothing was changed." >&2; exit 1; }
  echo "credential ok: omnigate-commercial:$tag is pullable"
}

# latest_app_tag -> the newest published OmniGate app release (used when no tag is given)
latest_app_tag() { curl -s -m 15 https://api.github.com/repos/thinkingsense-ai/Docker/releases/latest | python3 -c "import sys,json;print(json.load(sys.stdin)['tag_name'])"; }

# wait_for_edition <url> <admin token>  -> prints the running edition once the app answers
wait_for_edition() {
  local e
  for _ in $(seq 1 60); do
    e=$(curl -s -m 10 -H "Authorization: Bearer $2" "${1%/}/api/config" | python3 -c "import sys,json;print(json.load(sys.stdin)['edition']['edition'])" 2>/dev/null || true)
    [ -n "$e" ] && { echo "running edition: $e"; return 0; }; sleep 15
  done
  echo "could not read the running edition from ${1%/}/api/config" >&2; return 1
}
