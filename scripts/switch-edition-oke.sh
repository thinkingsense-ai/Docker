#!/bin/bash
# Switch a running OKE stack between the free and commercial OmniGate image without rebuilding it.
# Only the image changes: the cluster, network, databases and OmniGate's saved configuration stay, and the pod
# restarts once on the new image.
#
#   switch-edition-oke.sh --stack-id <stack ocid> --to commercial --pull-user <ns/user> --pull-token <auth token> \
#                         [--image-tag v0.10.4] [--url https://<lb> --admin-token <token>]
#   switch-edition-oke.sh --stack-id <stack ocid> --to free      # back to the public image (e.g. after a lapsed subscription)
#
# The pull user and token are the customer's own OCIR credential for the private commercial repository; they are what
# entitles the stack to the commercial image (revoke them to end access).
# Needs the oci CLI and python3. Note: `oci resource-manager stack update --variables` REPLACES the whole variable map, so this
# reads the current variables, changes four of them, and writes the full set back.
set -euo pipefail
REG=ocir.us-phoenix-1.oci.oraclecloud.com/ax8tpjdxhykk
STACK= TO= USER_= TOKEN= TAG= URL= ATOK=
while [ $# -gt 0 ]; do case $1 in
  --stack-id) STACK=$2; shift 2;; --to) TO=$2; shift 2;; --pull-user) USER_=$2; shift 2;; --pull-token) TOKEN=$2; shift 2;;
  --image-tag) TAG=$2; shift 2;; --url) URL=${2%/}; shift 2;; --admin-token) ATOK=$2; shift 2;;
  *) echo "unknown argument $1" >&2; exit 2;; esac; done
[ -n "$STACK" ] && { [ "$TO" = commercial ] || [ "$TO" = free ]; } || { sed -n 2,12p "$0"; exit 2; }
if [ "$TO" = commercial ] && { [ -z "$USER_" ] || [ -z "$TOKEN" ]; }; then echo "--to commercial needs --pull-user and --pull-token" >&2; exit 2; fi
export OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True SUPPRESS_LABEL_WARNING=True
VARS=$(mktemp); trap 'rm -f "$VARS"' EXIT; chmod 600 "$VARS"
oci resource-manager stack get --stack-id "$STACK" --query 'data.variables' > "$VARS"
python3 - "$VARS" "$TO" "$REG" "$USER_" "$TOKEN" "$TAG" <<'PY'
import json, sys
path, to, reg, user, token, tag = sys.argv[1:7]
v = json.load(open(path))
if to == "commercial":
    v.update(image_repository=f"{reg}/omnigate-commercial", image_pull_username=user, image_pull_auth_token=token)
else:
    for k in ("image_repository", "image_pull_username", "image_pull_auth_token"):
        v.pop(k, None)   # back to the stack's defaults: the public free image, no credentials
if tag:
    v["image_tag"] = tag
json.dump(v, open(path, "w"))
print("image:", v.get("image_repository", "<default: public free image>"), v.get("image_tag", "<default tag>"))
PY
if [ "$TO" = commercial ]; then
  # Check the credential and the tag BEFORE touching the stack: a wrong or revoked token would otherwise roll out a pod that
  # waits forever for an image it cannot pull.
  CHECK_TAG=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('image_tag',''))" "$VARS")
  # No explicit tag in the stack's variables: the stack runs its configured default, so read that from the stack's own Terraform
  # (NOT the newest app release, which may not have a commercial image yet).
  if [ -z "$CHECK_TAG" ]; then
    CFG=$(mktemp -d); oci resource-manager stack get-stack-tf-config --stack-id "$STACK" --file "$CFG/c.zip" >/dev/null 2>&1 && unzip -qo "$CFG/c.zip" -d "$CFG/x" 2>/dev/null
    CHECK_TAG=$(python3 - "$CFG" <<'PY'
import re, glob, sys
fs = glob.glob(sys.argv[1] + "/x/**/variables.tf", recursive=True)
m = re.search(r'variable "image_tag" \{.*?default\s*=\s*"([^"]+)"', open(fs[0]).read(), re.S) if fs else None
print(m.group(1) if m else "")
PY
)
    rm -rf "$CFG"
  fi
  [ -n "$CHECK_TAG" ] || { echo "Could not tell which image tag this stack runs; pass --image-tag." >&2; exit 2; }
  HOST=phx.ocir.io; REPO=${REG#*/}/omnigate-commercial
  WA=$(curl -s -m 15 -D - -o /dev/null "https://$HOST/v2/" | tr -d '\r' | awk -F': ' 'tolower($1)=="www-authenticate"{print $2}')
  REALM=$(echo "$WA" | sed -E 's/.*realm="([^"]*)".*/\1/'); SVC=$(echo "$WA" | sed -E 's/.*service="([^"]*)".*/\1/')
  BT=$(curl -s -m 15 -u "$USER_:$TOKEN" "$REALM?service=$SVC&scope=repository:$REPO:pull" | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))" 2>/dev/null || true)
  [ -n "$BT" ] || { echo "The registry rejected that pull user/token. Nothing was changed." >&2; exit 1; }
  CODE=$(curl -s -m 15 -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $BT" -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.docker.distribution.manifest.list.v2+json' "https://$HOST/v2/$REPO/manifests/${TAG:-$CHECK_TAG}")
  [ "$CODE" = 200 ] || { echo "Commercial image ${TAG:-$CHECK_TAG} not available to this credential (HTTP $CODE). Nothing was changed." >&2; exit 1; }
  echo "credential ok: omnigate-commercial:${TAG:-$CHECK_TAG} is pullable"
fi
oci resource-manager stack update --stack-id "$STACK" --variables "file://$VARS" --force --query 'data."lifecycle-state"' --raw-output >/dev/null
JOB=$(oci resource-manager job create-apply-job --stack-id "$STACK" --execution-plan-strategy AUTO_APPROVED --query 'data.id' --raw-output)
echo "apply job $JOB"
while :; do S=$(oci resource-manager job get --job-id "$JOB" --query 'data."lifecycle-state"' --raw-output); case $S in ACCEPTED|IN_PROGRESS|CANCELING) sleep 15;; *) break;; esac; done
echo "apply: $S"; [ "$S" = SUCCEEDED ] || exit 1
if [ -n "$URL" ] && [ -n "$ATOK" ]; then
  for i in $(seq 1 40); do
    E=$(curl -sk -m 10 -H "Authorization: Bearer $ATOK" "$URL/api/config" | python3 -c "import sys,json;print(json.load(sys.stdin)['edition']['edition'])" 2>/dev/null || true)
    [ -n "$E" ] && { echo "running edition: $E"; exit 0; }; sleep 15
  done
  echo "could not read the running edition from $URL/api/config" >&2; exit 1
fi
