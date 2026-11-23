#!/bin/bash
# Checks a deployed Agency (the cloud add-on, agency.enabled) from the outside, the way verify-secure-deploy.sh checks the Ask app:
#   verify-agency.sh http://<agency-address>:8097 <business-user> <password>            (HTTP or HTTPS; self-signed HTTPS is accepted, set VERIFY_CA=<ca.pem> to verify)
# It asserts: the layer and its UI answer; the guided demo tour is OFF (it signs in as named demo people and must never run on a real deployment); anonymous callers are refused;
# a wrong password and a cross-site request are refused; the business user signs in; the layer reaches the app; the IT-risk pack answers its approved questions when asked for them
# (VERIFY_ASK=0 skips the question: free edition and a slow model can take a while); and, when the app has the commercial edition, the workflow routes answer.
# Exits non-zero if any check fails. It never prints the password.
BASE=${1%/}; USER_NAME=$2; PASS=$3; fail=0; JAR=$(mktemp); trap 'rm -f "$JAR"' EXIT
[ -n "$BASE" ] && [ -n "$USER_NAME" ] && [ -n "$PASS" ] || { echo "usage: $0 <agency-url> <user> <password>"; exit 2; }
CURL_TLS=(-k); [ -n "${VERIFY_CA:-}" ] && CURL_TLS=(--cacert "$VERIFY_CA")
code() { curl -s "${CURL_TLS[@]}" -o /dev/null -m 20 -w '%{http_code}' "$@"; }
get() { curl -s "${CURL_TLS[@]}" -m 30 "$@"; }
check() { if [ "$2" = "$3" ]; then printf 'PASS  %-52s %s\n' "$1" "$3"; else printf 'FAIL  %-52s want %s got %s\n' "$1" "$2" "$3"; fail=1; fi; }
j() { python3 -c "import json,sys
try:
  d=json.load(sys.stdin)
  for k in sys.argv[1].split('.'): d=d[k] if not isinstance(d,list) else d[int(k)]
  print(d if not isinstance(d,bool) else str(d).lower())
except Exception: print('unreadable')" "$1"; }
check "layer /health answers"                         true "$(get "$BASE/health" | j ok)"
check "the UI page is served"                         200 "$(code "$BASE/")"
S=$(get "$BASE/status")
check "the layer reaches the app"                     true "$(echo "$S" | j server.reachable)"
check "the demo tour is OFF"                          false "$(echo "$S" | j tour.enabled)"
check "the demo tour sign-in route is closed"         404 "$(code -X POST -H 'X-Requested-With: verify' -H 'Content-Type: application/json' -d '{"persona":"curator"}' "$BASE/tour/signin")"
for p in /whoami /conversations /workflows/queue; do check "anonymous $p refused" 401 "$(code "$BASE$p")"; done
check "login without the CSRF header refused"         403 "$(code -b "$JAR" -c "$JAR" -H 'Cookie: x=1' -H 'Content-Type: application/json' -d "{\"username\":\"$USER_NAME\",\"password\":\"x\"}" "$BASE/login")"
check "a wrong password is refused"                   400 "$(code -X POST -H 'X-Requested-With: verify' -H 'Content-Type: application/json' -d "{\"username\":\"$USER_NAME\",\"password\":\"definitely-wrong\"}" "$BASE/login")"
if [ "${BASE#https}" != "$BASE" ]; then
  hdr=$(curl -s "${CURL_TLS[@]}" -D - -o /dev/null -m 20 -X POST -H 'X-Requested-With: verify' -H 'Content-Type: application/json' -d "$(python3 -c 'import json,sys;print(json.dumps({"username":sys.argv[1],"password":sys.argv[2]}))' "$USER_NAME" "$PASS")" "$BASE/login" | tr -d '\r')
  echo "$hdr" | grep -i '^set-cookie:' | grep -qi '; *secure' && printf 'PASS  %-52s %s\n' "the session cookie is marked Secure" "yes" || { printf 'FAIL  %-52s %s\n' "the session cookie is marked Secure" "no"; fail=1; }
else printf 'INFO  %-52s %s\n' "served over HTTPS" "no (plain HTTP: put TLS in front for a real deployment)"; fi
check "the business user signs in"                    200 "$(code -c "$JAR" -X POST -H 'X-Requested-With: verify' -H 'Content-Type: application/json' -d "$(python3 -c 'import json,sys;print(json.dumps({"username":sys.argv[1],"password":sys.argv[2]}))' "$USER_NAME" "$PASS")" "$BASE/login")"
check "the session works (/whoami)"                   "$USER_NAME" "$(get -b "$JAR" "$BASE/whoami" | j userId)"
PK=$(get -b "$JAR" "$BASE/packs"); n=$(echo "$PK" | python3 -c 'import json,sys
try: print(len(json.load(sys.stdin)["packs"]))
except Exception: print(0)')
[ "$n" -ge 1 ] && printf 'PASS  %-52s %s\n' "packs are listed" "$n" || { printf 'FAIL  %-52s %s\n' "packs are listed" "$n"; fail=1; }
ST=$(get -b "$JAR" "$BASE/starters?pack=it-risk"); sn=$(echo "$ST" | python3 -c 'import json,sys
try: d=json.load(sys.stdin); print(len(d.get("questions") or d.get("starters") or []))
except Exception: print(0)')
[ "$sn" -ge 1 ] && printf 'PASS  %-52s %s\n' "IT-risk approved questions are offered" "$sn" || { printf 'FAIL  %-52s %s (the agency-risk pack and its question seeding?)\n' "IT-risk approved questions are offered" "$sn"; fail=1; }
if [ "${VERIFY_ASK:-1}" != 0 ]; then
  Q="Which feeds are we reading, and when did each last answer?"
  out=$(curl -s "${CURL_TLS[@]}" -m "${ASK_TIMEOUT:-180}" -b "$JAR" -X POST -H 'X-Requested-With: verify' -H 'Content-Type: application/json' -d "$(python3 -c 'import json,sys;print(json.dumps({"question":sys.argv[1],"pack":"it-risk"}))' "$Q")" "$BASE/ask")
  if echo "$out" | grep -q '"rows"'; then printf 'PASS  %-52s %s\n' "an approved question is answered with rows" "$(echo "$out" | head -c 80)"; else printf 'FAIL  %-52s %s\n' "an approved question is answered with rows" "$(echo "$out" | head -c 160)"; fail=1; fi
fi
wf=$(code -b "$JAR" "$BASE/workflows/definitions")
case "$wf" in 200) printf 'INFO  %-52s %s\n' "workflows (commercial edition)" "on";; 403) printf 'INFO  %-52s %s\n' "workflows (commercial edition)" "on (403: this login has no workflow grant)";; 404|502|503) printf 'INFO  %-52s %s\n' "workflows (commercial edition)" "off ($wf: expected on the free edition)";; *) check "workflow routes answer sensibly" "200 or 404" "$wf";; esac
[ $fail = 0 ] && echo "ALL PASS" || echo "FAILED"; exit $fail
