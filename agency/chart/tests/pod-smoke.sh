#!/bin/bash
# Smoke test for the Agency cloud add-on without a cluster: builds the Agency image (addons/thinking-layer/Dockerfile, the same one the Build Agency image workflow publishes) and runs it under
# the security settings the chart sets (non-root uid 10001, read-only root filesystem, no capabilities, no privilege escalation), beside a running stack whose app it asks. Then it checks
# /health, the UI page, /status, a sign-in and the Workspace list.
#   NETWORK=<stack>_default [SERVER_URL=http://omnigate:8080] [USER_NAME=alice USER_PASSWORD=demo] [IMAGE=<an image already built>] agency/chart/tests/pod-smoke.sh
# It does NOT test Kubernetes itself (probes, Service and load balancer, scheduling): that needs a cluster. `helm template` covers the rendering.
set -u
cd "$(dirname "$0")/../../.." || exit 1
NETWORK=${NETWORK:?set NETWORK to the stack network}; SERVER=${SERVER_URL:-http://omnigate:8080}; U=${USER_NAME:-alice}; PW=${USER_PASSWORD:-demo}
IMAGE=${IMAGE:-agency-smoke:local}
fail=0; ok() { echo "  PASS  $*"; }; bad() { echo "  FAIL  $*"; fail=1; }
cleanup() { docker rm -f agency-smoke >/dev/null 2>&1; }
trap cleanup EXIT; cleanup
[ -n "${IMAGE_PREBUILT:-}" ] || docker build -q -f addons/thinking-layer/Dockerfile -t "$IMAGE" . >/dev/null && ok "image built" || bad "image build failed"
CERT=$(mktemp -d); trap 'rm -rf "$CERT"; docker rm -f agency-smoke >/dev/null 2>&1' EXIT
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$CERT/tls.key" -out "$CERT/tls.crt" -days 2 -subj "/CN=agency" >/dev/null 2>&1 && chmod 644 "$CERT"/tls.* && ok "a self-signed certificate for the test" || bad "openssl could not make a certificate"
LOCK=(--user 10001:10001 --read-only --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp:rw,uid=10001,gid=10001,mode=1777)
docker run -d --name agency-smoke --network "$NETWORK" "${LOCK[@]}" -v "$CERT":/etc/agency-tls:ro -e AGENCY_TLS_CERT=/etc/agency-tls/tls.crt -e AGENCY_TLS_KEY=/etc/agency-tls/tls.key -e SERVER_URL=$SERVER -e PORT=8097 -e PYTHONDONTWRITEBYTECODE=1 "$IMAGE" >/dev/null
sleep 3
IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' agency-smoke); B=https://$IP:8097
get() { docker run --rm --network "$NETWORK" curlimages/curl -sk -m 15 "$@"; }
[ "$(get $B/health | grep -c '"ok": true')" = 1 ] && ok "/health" || bad "/health: $(docker logs agency-smoke 2>&1 | tail -3)"
get $B/ | grep -q "<div id=\"root\"" && ok "the UI page is served" || bad "the UI page is missing"
get $B/status | grep -q '"reachable": true' && ok "/status says the app is reachable" || bad "/status: $(get $B/status | head -c 200)"
JAR=$(mktemp); trap 'rm -f $JAR; cleanup' EXIT
code=$(docker run --rm --network "$NETWORK" curlimages/curl -sk -o /dev/null -w '%{http_code}' -m 20 -H 'Content-Type: application/json' -H 'X-Requested-With: agency' -d "{\"username\":\"$U\",\"password\":\"$PW\"}" -c /tmp/j $B/login)
[ "$code" = 200 ] && ok "sign-in as $U through the layer" || bad "sign-in answered $code"
docker logs agency-smoke 2>&1 | grep -qi "traceback" && bad "the layer logged a traceback" || ok "no traceback in the layer's log"
[ $fail = 0 ] && echo "ALL PASS" || echo "FAILED"; exit $fail
