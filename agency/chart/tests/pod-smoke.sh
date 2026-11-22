#!/bin/bash
# Smoke test for the Agency cloud add-on without a cluster: runs the pod's two steps under the security settings the chart sets (non-root uid 10001, read-only root filesystem, no
# capabilities, no privilege escalation), from the SAME files the chart puts in its ConfigMaps (files/agency/*.py, contract.json, catalogue.json, web.tgz): first the init step that
# unpacks the UI, then the layer, beside a running stack whose app it asks. Then it checks /health, the UI page, /status, a sign-in and the Workspace list.
#   NETWORK=<stack>_default [SERVER_URL=http://omnigate:8080] [USER_NAME=alice USER_PASSWORD=demo] agency/chart/tests/pod-smoke.sh
# It does NOT test Kubernetes itself (probes, Service and load balancer, ConfigMap size limits, scheduling): that needs a cluster. `helm template` covers the rendering.
set -u
cd "$(dirname "$0")/../../.." || exit 1
SRC=${CHART_FILES:-$PWD/resource-manager/omnigateaksstack/helm/omnigate/files/agency}
NETWORK=${NETWORK:?set NETWORK to the stack network}; SERVER=${SERVER_URL:-http://omnigate:8080}; U=${USER_NAME:-alice}; PW=${USER_PASSWORD:-demo}
PY=${PYTHON_IMAGE:-docker.io/library/python:3.12-slim}
fail=0; ok() { echo "  PASS  $*"; }; bad() { echo "  FAIL  $*"; fail=1; }
cleanup() { docker rm -f agency-smoke >/dev/null 2>&1; docker volume rm -f agency-smoke-web >/dev/null 2>&1; }
trap cleanup EXIT; cleanup
docker volume create agency-smoke-web >/dev/null
docker run --rm alpine true >/dev/null 2>&1; docker run --rm -v agency-smoke-web:/w alpine chown 10001:10001 /w
LOCK=(--user 10001:10001 --read-only --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp:rw,uid=10001,gid=10001,mode=1777)
# the init step, word for word as in the chart (the web.tgz is mounted read-only at /in)
docker run --rm "${LOCK[@]}" -v "$SRC":/in:ro -v agency-smoke-web:/web $PY python -c "import tarfile; tarfile.open('/in/web.tgz').extractall('/web', filter='data')" && ok "UI unpacked by the init step" || bad "init step failed"
docker run -d --name agency-smoke --network "$NETWORK" "${LOCK[@]}" -w /app -v "$SRC":/app:ro -v agency-smoke-web:/web:ro \
  -e SERVER_URL=$SERVER -e AGENCY_WEB_DIST=/web -e PACKS_CATALOGUE=/app/catalogue.json -e PORT=8097 -e PYTHONDONTWRITEBYTECODE=1 $PY python app.py >/dev/null
sleep 3
IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' agency-smoke); B=http://$IP:8097
get() { docker run --rm --network "$NETWORK" curlimages/curl -s -m 15 "$@"; }
[ "$(get $B/health | grep -c '"ok": true')" = 1 ] && ok "/health" || bad "/health: $(docker logs agency-smoke 2>&1 | tail -3)"
get $B/ | grep -q "<div id=\"root\"" && ok "the UI page is served" || bad "the UI page is missing"
get $B/status | grep -q '"reachable": true' && ok "/status says the app is reachable" || bad "/status: $(get $B/status | head -c 200)"
JAR=$(mktemp); trap 'rm -f $JAR; cleanup' EXIT
code=$(docker run --rm --network "$NETWORK" curlimages/curl -s -o /dev/null -w '%{http_code}' -m 20 -H 'Content-Type: application/json' -H 'X-Requested-With: agency' -d "{\"username\":\"$U\",\"password\":\"$PW\"}" -c /tmp/j $B/login)
[ "$code" = 200 ] && ok "sign-in as $U through the layer" || bad "sign-in answered $code"
docker logs agency-smoke 2>&1 | grep -qi "traceback" && bad "the layer logged a traceback" || ok "no traceback in the layer's log"
[ $fail = 0 ] && echo "ALL PASS" || echo "FAILED"; exit $fail
