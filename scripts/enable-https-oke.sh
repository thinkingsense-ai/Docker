#!/bin/bash
# Replace the automatic self-signed certificate of a running OKE stack with one from a LOCAL TEST CA, for INTERNAL TESTING (see
# lib/local-ca.sh). HTTPS itself is on by default; this only swaps the certificate so browsers that trust the local CA show a clean padlock.
# The certificate has to name the load balancer's address, which only exists after the first deploy, so this runs after it:
# it reads the address, issues a certificate, writes it into the stack's variables and applies. The app restarts once.
#
#   enable-https-oke.sh --stack-id <stack ocid> [--address <ip or dns name>] [--also <more names> ...]
#
# Needs the oci CLI, openssl and python3. Note `oci resource-manager stack update --variables` REPLACES the whole variable map, so
# this reads the current variables, changes two of them, and writes the full set back.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); . "$HERE/lib/local-ca.sh"
STACK= ADDR= ALSO=()
while [ $# -gt 0 ]; do case $1 in
  --stack-id) STACK=$2; shift 2;; --address) ADDR=$2; shift 2;; --also) ALSO+=("$2"); shift 2;;
  *) echo "unknown argument $1" >&2; exit 2;; esac; done
[ -n "$STACK" ] || { sed -n 2,9p "$0"; exit 2; }
export OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True SUPPRESS_LABEL_WARNING=True
if [ -z "$ADDR" ]; then
  JOB=$(oci resource-manager job list --stack-id "$STACK" --query 'data[?operation==`APPLY` && "lifecycle-state"==`SUCCEEDED`]|[0].id' --raw-output)
  [ -n "$JOB" ] && [ "$JOB" != null ] || { echo "No successful apply found for this stack; deploy it first or pass --address." >&2; exit 1; }
  T=$(mktemp); oci resource-manager job get-job-tf-state --job-id "$JOB" --file "$T" >/dev/null
  ADDR=$(python3 -c "import json,re,sys;u=json.load(open(sys.argv[1]))['outputs']['ask_app_url']['value'];print(re.sub(r'^https?://|[:/].*$','',u) if '<' not in u else '')" "$T"); rm -f "$T"
  [ -n "$ADDR" ] || { echo "The load balancer address is not known yet; pass --address <ip>." >&2; exit 1; }
fi
echo "address: $ADDR"
local_ca_init
P12=$(mktemp); PASS=$(openssl rand -hex 16); trap 'rm -f "$P12" "$VARS"' EXIT
local_ca_issue_p12 "$P12" "$PASS" "$ADDR" "${ALSO[@]+"${ALSO[@]}"}"
VARS=$(mktemp); chmod 600 "$VARS"
oci resource-manager stack get --stack-id "$STACK" --query 'data.variables' > "$VARS"
python3 - "$VARS" "$P12" "$PASS" <<'PY'
import base64, json, sys
path, p12, pw = sys.argv[1:4]
v = json.load(open(path))
v["tls_keystore_base64"] = base64.b64encode(open(p12, "rb").read()).decode()
v["tls_keystore_password"] = pw
json.dump(v, open(path, "w"))
PY
oci resource-manager stack update --stack-id "$STACK" --variables "file://$VARS" --force --query 'data."lifecycle-state"' --raw-output >/dev/null
JOB=$(oci resource-manager job create-apply-job --stack-id "$STACK" --execution-plan-strategy AUTO_APPROVED --query 'data.id' --raw-output)
echo "apply job $JOB"
while :; do S=$(oci resource-manager job get --job-id "$JOB" --query 'data."lifecycle-state"' --raw-output); case $S in ACCEPTED|IN_PROGRESS|CANCELING) sleep 15;; *) break;; esac; done
echo "apply: $S"; [ "$S" = SUCCEEDED ] || exit 1
for i in $(seq 1 40); do
  C=$(curl -s -m 10 --cacert "$LOCAL_CA_DIR/ca.pem" -o /dev/null -w '%{http_code}' "https://$ADDR/" || true)
  [ "$C" = 200 ] || [ "$C" = 302 ] || [ "$C" = 401 ] && { echo "HTTPS ok: https://$ADDR/ (HTTP $C, certificate verified against the local CA)"; local_ca_trust_hint; exit 0; }
  sleep 15
done
echo "HTTPS did not answer on https://$ADDR/ (last HTTP code ${C:-none})" >&2; exit 1
