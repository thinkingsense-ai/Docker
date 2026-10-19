#!/bin/bash
# Switch a running Azure (AKS) stack between the free and commercial OmniGate image without rebuilding the cluster.
#
#   switch-edition-aks.sh --resource-group omnigate-aks-rg --to commercial --pull-user <ns/user> --pull-token <auth token> \
#                         [--image-tag v0.10.4] [--url https://<lb> --admin-token <token>]
#   switch-edition-aks.sh --resource-group omnigate-aks-rg --to free
#
# Only the image changes: the script fetches cluster credentials and runs `helm upgrade --reuse-values` with the new image, so every
# other setting (logins, API key, sizes) stays and the OmniGate pod restarts. Needs az, helm, kubectl and python3 (Cloud Shell has them).
# Note: re-running the original Azure deployment later resets the image to whatever you pass it, so pass the same image settings again
# (imageRepository, imagePullUsername, imagePullAuthToken) if you do.
set -euo pipefail
. "$(cd "$(dirname "$0")" && pwd)/lib/ocir-check.sh"
RG= TO= USER_= TOKEN= TAG= URL= ATOK= CLUSTER= CHART=https://github.com/thinkingsense-ai/Docker/archive/refs/tags/aks-stack-v1.0.8.tar.gz
while [ $# -gt 0 ]; do case $1 in
  --resource-group) RG=$2; shift 2;; --cluster) CLUSTER=$2; shift 2;; --to) TO=$2; shift 2;; --pull-user) USER_=$2; shift 2;;
  --pull-token) TOKEN=$2; shift 2;; --image-tag) TAG=$2; shift 2;; --url) URL=$2; shift 2;; --admin-token) ATOK=$2; shift 2;;
  --chart-url) CHART=$2; shift 2;;
  *) echo "unknown argument $1" >&2; exit 2;; esac; done
[ -n "$RG" ] && { [ "$TO" = commercial ] || [ "$TO" = free ]; } || { sed -n 2,12p "$0"; exit 2; }
[ -n "$CLUSTER" ] || CLUSTER=$(az aks list -g "$RG" --query '[0].name' -o tsv)
KC=$(mktemp); W=$(mktemp -d); trap 'rm -rf "$KC" "$W"' EXIT; export KUBECONFIG=$KC
az aks get-credentials -g "$RG" -n "$CLUSTER" --file "$KC" --overwrite-existing >/dev/null
CUR_TAG=$(helm get values omnigate -o json | python3 -c "import sys,json;print(json.load(sys.stdin).get('image',{}).get('tag',''))")
if [ "$TO" = commercial ]; then
  { [ -n "$USER_" ] && [ -n "$TOKEN" ]; } || { echo "--to commercial needs --pull-user and --pull-token" >&2; exit 2; }
  check_commercial_pull "$USER_" "$TOKEN" "${TAG:-${CUR_TAG:-$(latest_app_tag)}}"
fi
curl -fsSL "$CHART" | tar -xz -C "$W"
CHART_DIR=$(ls -d "$W"/*/resource-manager/omnigateaksstack/helm/omnigate)
grep -q pullAuthToken "$CHART_DIR/values.yaml" || { echo "that chart predates the commercial-image settings; use --chart-url of aks-stack-v1.0.8 or later" >&2; exit 2; }
ARGS=(--reuse-values)
[ -z "$TAG" ] || ARGS+=(--set-string "image.tag=$TAG")
if [ "$TO" = commercial ]; then
  printf '%s' "$TOKEN" > "$W/token"; chmod 600 "$W/token"
  ARGS+=(--set-string "image.repository=$COMMERCIAL_REPO" --set-string "image.pullUsername=$USER_" --set-file "image.pullAuthToken=$W/token")
else
  ARGS+=(--set-string "image.repository=us-docker.pkg.dev/thinkingsense/omnigate/omnigate" --set-string "image.pullUsername=" --set-string "image.pullAuthToken=")
fi
helm upgrade omnigate "$CHART_DIR" "${ARGS[@]}" --timeout 10m0s --wait
[ -z "$URL" ] || [ -z "$ATOK" ] || wait_for_edition "$URL" "$ATOK"
