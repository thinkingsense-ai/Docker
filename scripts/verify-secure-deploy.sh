#!/bin/bash
# Checks a fresh free-edition deploy on any of the four clouds: the admin surfaces refuse anonymous callers,
# the admin token works, a wrong token does not, the Ask app is up, and the app's own deployment check reports nothing critical.
#   verify-secure-deploy.sh [--legacy-agent] https://<load-balancer> <admin-api-token>     (or http://<lb>:8080 if HTTPS is off)
# HTTPS deployments use a self-signed certificate unless one was supplied, so the checks do not verify the certificate (curl -k);
# set VERIFY_CA=<ca.pem> to verify it against a CA instead.
# Exits non-zero if any check fails. App v0.10.5+ requires a credential on /mcp/agent (Server#17); on v0.10.4 and
# earlier it answered anonymously, so run with --legacy-agent to report it instead of asserting.
LEGACY=0; [ "$1" = --legacy-agent ] && { LEGACY=1; shift; }
BASE=${1%/}; TOKEN=$2; fail=0
CURL_TLS=(-k); [ -n "${VERIFY_CA:-}" ] && CURL_TLS=(--cacert "$VERIFY_CA")
code() { curl -s "${CURL_TLS[@]}" -o /dev/null -m 15 -w '%{http_code}' "$@"; }
check() { # name expected actual
  if [ "$2" = "$3" ]; then printf 'PASS  %-46s %s\n' "$1" "$3"; else printf 'FAIL  %-46s want %s got %s\n' "$1" "$2" "$3"; fail=1; fi; }
# App 0.10.13 and later answer the deployment check only to a signed-in reader (it now says what is switched on); earlier ones answered anyone.
check "readiness answers the admin token"   200 "$(code -H "Authorization: Bearer $TOKEN" "$BASE/api/deployment-readiness")"
ready=$(curl -s "${CURL_TLS[@]}" -m 30 -H "Authorization: Bearer $TOKEN" "$BASE/api/deployment-readiness")
crit=$(printf '%s' "$ready" | python3 -c 'import json,sys
try: print(",".join(c["id"] for c in json.load(sys.stdin)["checks"] if c.get("severity") == "CRITICAL") or "none")
except Exception: print("unreadable")')
check "deployment check has no critical problem"  none "$crit"
check "Ask app page is up"                  200 "$(code "$BASE/")"
for p in /api/config /metrics /mcp/; do check "anonymous $p refused" 401 "$(code "$BASE$p")"; done
check "anonymous /api/query refused"        401 "$(code -X POST -H 'Content-Type: application/json' -d '{"sql":"select 1"}' "$BASE/api/query")"
check "wrong token refused"                 401 "$(code -X POST -H 'Authorization: Bearer wrong' -H 'Content-Type: application/json' -d '{"sql":"select 1"}' "$BASE/api/query")"
body=$(curl -s "${CURL_TLS[@]}" -m 60 -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"sql":"SELECT COUNT(*) AS n FROM suppliers.suppliers"}' "$BASE/api/query")
if echo "$body" | grep -q '"success" *: *true'; then printf 'PASS  %-46s %s\n' "admin token runs a federated query" "$(echo "$body" | head -c 120)"; else printf 'FAIL  admin token query: %s\n' "$(echo "$body" | head -c 200)"; fail=1; fi
if [ $LEGACY = 1 ]; then printf 'INFO  anonymous /mcp/agent/ (open before v0.10.5)         %s\n' "$(code "$BASE/mcp/agent/")"
else check "anonymous /mcp/agent refused" 401 "$(code -X POST -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' "$BASE/mcp/agent/")"; fi
exit $fail
