#!/bin/bash
# Install or renew a commercial licence on a running OmniGate deployment, on any of the four clouds, without redeploying.
#
#   set-licence.sh --token ts1.<payload>.<signature>            # or: --file /path/to/licence
#                  [--kubeconfig F] [--context C] [--namespace default] [--release omnigate]
#                  [--restart] [--url http://<lb>:8080 --admin-token <token>] [--force]
#
# The licence goes into the deployment's licence Secret; the app re-reads it every minute, so a RENEWAL needs no restart.
# The FIRST activation needs the OmniGate pods restarted once (--restart does a rolling restart): the data-source limit and
# clustering are decided when a pod starts.
# The script reads the token before installing it and refuses an expired one. It cannot check the signature (only the app can);
# with --url and --admin-token it waits for the app to report the result, so a wrong or tampered licence shows up here.
set -euo pipefail
TOKEN= FILE= KC= CTX= NS=default REL=omnigate URL= ATOK= RESTART=0 FORCE=0
while [ $# -gt 0 ]; do case $1 in
  --token) TOKEN=$2; shift 2;; --file) FILE=$2; shift 2;; --kubeconfig) KC=$2; shift 2;; --context) CTX=$2; shift 2;;
  --namespace) NS=$2; shift 2;; --release) REL=$2; shift 2;; --url) URL=${2%/}; shift 2;; --admin-token) ATOK=$2; shift 2;;
  --restart) RESTART=1; shift;; --force) FORCE=1; shift;;
  *) echo "unknown argument $1" >&2; exit 2;; esac; done
[ -n "$FILE" ] && TOKEN=$(cat "$FILE")
TOKEN=$(printf '%s' "$TOKEN" | tr -d '[:space:]')
[ -n "$TOKEN" ] || { sed -n 2,13p "$0"; exit 2; }
K=(kubectl); [ -n "$KC" ] && K+=(--kubeconfig "$KC"); [ -n "$CTX" ] && K+=(--context "$CTX"); K+=(-n "$NS")

# Read what the licence says about itself (not verified here).
python3 - "$TOKEN" "$FORCE" <<'PY'
import base64, json, sys, time
token, force = sys.argv[1], sys.argv[2] == "1"
parts = token.split(".")
if len(parts) != 3 or parts[0] != "ts1":
    sys.exit("That is not a ThinkingSense licence (it should look like ts1.<payload>.<signature>).")
try:
    p = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
except Exception:
    sys.exit("The licence could not be read.")
exp = int(p.get("exp", 0)); days = (exp - time.time()) / 86400
print(f"licence for {p.get('customer')}: edition {p.get('edition', 'commercial')}, expires {time.strftime('%Y-%m-%d', time.gmtime(exp))} ({days:.0f} days)")
if p.get("caps"):
    print("limits:", ", ".join(f"{k}={v}" for k, v in p["caps"].items()))
if days <= 0 and not force:
    sys.exit("That licence has already expired. Nothing was changed.")
if 0 < days < 60:
    print(f"note: fewer than 60 days left -- time to renew.")
PY
SECRET="$REL-omnigate-license"
"${K[@]}" get secret "$SECRET" >/dev/null 2>&1 || { echo "Secret $SECRET not found in namespace $NS: this deployment predates the licence support. Update the stack to oke-stack-v1.1.9 or later first." >&2; exit 1; }
P=$(mktemp); trap 'rm -f "$P"' EXIT; chmod 600 "$P"
python3 -c "import json,sys;print(json.dumps({'stringData':{'license':sys.argv[1]}}))" "$TOKEN" > "$P"
"${K[@]}" patch secret "$SECRET" --type merge --patch-file "$P" >/dev/null
echo "licence installed in secret $SECRET"
if [ $RESTART = 1 ]; then
  for w in $("${K[@]}" get deploy,statefulset -l app.kubernetes.io/component=omnigate -o name); do
    "${K[@]}" rollout restart "$w" >/dev/null; "${K[@]}" rollout status "$w" --timeout=600s
  done
fi
if [ -n "$URL" ] && [ -n "$ATOK" ]; then
  echo "waiting for the app to read it (the mounted file refreshes within about two minutes) ..."
  for _ in $(seq 1 24); do
    R=$(curl -s -m 10 -H "Authorization: Bearer $ATOK" "$URL/api/config" | python3 -c "
import sys,json;e=json.load(sys.stdin)['edition'];print(e.get('licenseStatus','?'),e['edition'],e.get('licenseCustomer',''),e.get('licenseExpiresAt',''))" 2>/dev/null || true)
    case $R in VALID*) echo "app reports: $R"; exit 0;; INVALID*|EXPIRED*) echo "app reports: $R -- the licence was not accepted" >&2; exit 1;; esac
    sleep 10
  done
  echo "the app has not reported a valid licence yet (last: ${R:-no answer})" >&2; exit 1
fi
