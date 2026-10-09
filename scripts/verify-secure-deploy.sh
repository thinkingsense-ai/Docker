#!/bin/bash
# Checks a fresh free-edition deploy on any of the four clouds: the admin surfaces refuse anonymous callers,
# the admin token works, a wrong token does not, and the Ask app is up.
#   verify-secure-deploy.sh http://<load-balancer>:8080 <admin-api-token>
# Exits non-zero if any check fails. /mcp/agent is reported, not asserted: it is open by design until
# thinkingsense-ai/Server#17 is fixed (use the allowed-client-CIDRs setting to limit it).
BASE=${1%/}; TOKEN=$2; fail=0
code() { curl -s -o /dev/null -m 15 -w '%{http_code}' "$@"; }
check() { # name expected actual
  if [ "$2" = "$3" ]; then printf 'PASS  %-46s %s\n' "$1" "$3"; else printf 'FAIL  %-46s want %s got %s\n' "$1" "$2" "$3"; fail=1; fi; }
check "readiness is public"                 200 "$(code "$BASE/api/deployment-readiness")"
check "Ask app page is up"                  200 "$(code "$BASE/app/")"
for p in /api/config /metrics /mcp/; do check "anonymous $p refused" 401 "$(code "$BASE$p")"; done
check "anonymous /api/query refused"        401 "$(code -X POST -H 'Content-Type: application/json' -d '{"sql":"select 1"}' "$BASE/api/query")"
check "wrong token refused"                 401 "$(code -X POST -H 'Authorization: Bearer wrong' -H 'Content-Type: application/json' -d '{"sql":"select 1"}' "$BASE/api/query")"
body=$(curl -s -m 60 -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"sql":"SELECT COUNT(*) AS n FROM suppliers.suppliers"}' "$BASE/api/query")
if echo "$body" | grep -q '"success" *: *true'; then printf 'PASS  %-46s %s\n' "admin token runs a federated query" "$(echo "$body" | head -c 120)"; else printf 'FAIL  admin token query: %s\n' "$(echo "$body" | head -c 200)"; fail=1; fi
printf 'INFO  anonymous /mcp/agent/ (open by design for now)      %s\n' "$(code "$BASE/mcp/agent/")"
exit $fail
