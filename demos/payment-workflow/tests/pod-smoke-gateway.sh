#!/bin/bash
# Smoke test for the cloud add-on in GATEWAY mode (paymentWorkflow.gateway.enabled) without a cluster: runs the four containers of the pod (Temporal, worker, gateway, ERP mock;
# no inbox) under the security settings the chart sets (non-root uid 10001, read-only root filesystem, no capabilities, no privilege escalation, volumes owned by gid 10001),
# sharing one network like a pod, beside a running Treasury stack whose app points at this pod: OMNIGATE_WORKFLOW_ENGINE=http://wfpod:8094 and the same GATEWAY_TOKEN,
# OMNIGATE_WORKFLOW_MANIFEST=<manifest.gateway.json>, and the commercial edition. Then it drives the app's own workflow API: start, refusals, two approvals, dry run.
#   NETWORK=<stack>_default APP=http://localhost:8080 GATEWAY_TOKEN=<token the app was given> ADMIN_PASSWORD=... demos/payment-workflow/tests/pod-smoke-gateway.sh
# Users alice (starts), bob and carol (approve) must exist with password $USER_PASSWORD (default demo). It does NOT test Kubernetes itself (probes, PVC, network policy, the
# Secret and ConfigMap wiring, scheduling): that needs a cluster. `helm template` covers the rendering.
set -u
cd "$(dirname "$0")/../../.." || exit 1
SRC=${CHART_FILES:-$PWD/resource-manager/omnigateaksstack/helm/omnigate/files/payment-workflow}
NETWORK=${NETWORK:?set NETWORK to the Treasury stack network}; APP=${APP:-http://localhost:8080}; TOKEN=${GATEWAY_TOKEN:?set GATEWAY_TOKEN}; PW=${USER_PASSWORD:-demo}; ADMIN_PW=${ADMIN_PASSWORD:-}
TD=${TEMPORAL_IMAGE:-docker.io/temporalio/temporal@sha256:597a5dbbcc6e7716b326dde4a51622d5ea0879eb0cf06ff8a94381361d0a987d}
PY=${PYTHON_IMAGE:-docker.io/library/python:3.12-slim}; SDK=${SDK_VERSION:-1.30.0}; ASK=${ASK_URL:-http://omnigate:8080}
fail=0; ok() { echo "  PASS  $*"; }; bad() { echo "  FAIL  $*"; fail=1; }
cleanup() { for n in wf-erp wf-gateway wf-worker wf-temporal wfpod; do docker rm -f $n >/dev/null 2>&1; done; docker volume rm -f wfdata wfpylib >/dev/null 2>&1; rm -f /tmp/gws_*; }
cleanup; docker volume create wfdata >/dev/null; docker volume create wfpylib >/dev/null
docker run --rm -v wfdata:/d -v wfpylib:/p alpine sh -c 'chown 10001:10001 /d /p && chmod 2775 /d /p'
LOCK=(--user 10001:10001 --read-only --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp:rw,uid=10001,gid=10001,mode=1777 -e HOME=/tmp)
docker run --rm "${LOCK[@]}" -v wfpylib:/pylib $PY pip install --no-cache-dir --disable-pip-version-check --target /pylib temporalio==$SDK >/dev/null 2>&1 && ok "SDK installed as non-root on a read-only root filesystem" || bad "SDK install failed"
docker run -d --name wfpod --network "$NETWORK" alpine sleep 3600 >/dev/null
docker run -d --name wf-temporal --network container:wfpod "${LOCK[@]}" -e USER=temporal -v wfdata:/data $TD server start-dev --ip 0.0.0.0 --headless --db-filename /data/temporal.db >/dev/null
ENVS=(-e PYTHONPATH=/pylib:/app -e PYTHONDONTWRITEBYTECODE=1 -e TEMPORAL_ADDRESS=localhost:7233)
docker run -d --name wf-worker --network container:wfpod "${LOCK[@]}" "${ENVS[@]}" -e ASK_URL=$ASK -e ERP_URL=http://localhost:8086 -e WRITE_BACK=dry-run -e DECISIONS_FILE=/data/decisions.jsonl ${ASK_ADMIN_TOKEN:+-e ASK_ADMIN_TOKEN=$ASK_ADMIN_TOKEN} -w /app -v "$SRC":/app:ro -v wfpylib:/pylib:ro -v wfdata:/data $PY python /app/worker.py >/dev/null
docker run -d --name wf-gateway --network container:wfpod "${LOCK[@]}" "${ENVS[@]}" -e GATEWAY_PORT=8094 -e GATEWAY_TOKEN="$TOKEN" -w /app -v "$SRC":/app:ro -v wfpylib:/pylib:ro -v wfdata:/data $PY python /app/gateway.py >/dev/null
docker run -d --name wf-erp --network container:wfpod --user 10001:10001 --read-only --cap-drop ALL --security-opt no-new-privileges -e PYTHONDONTWRITEBYTECODE=1 -w /app -v "$SRC":/app:ro $PY python /app/erp_mock.py 8086 >/dev/null
echo "waiting for the pod"; for i in $(seq 1 60); do docker exec wfpod wget -qO- http://127.0.0.1:8094/health 2>/dev/null | grep -q true && break; sleep 2; done
for c in wf-temporal wf-worker wf-gateway wf-erp; do [ "$(docker inspect -f '{{.State.Running}}' $c)" = true ] && ok "$c is running" || bad "$c exited: $(docker logs $c 2>&1 | tail -2 | tr '\n' ' ')"; done
docker exec wfpod wget -qO- http://127.0.0.1:8094/health | grep -q true && ok "gateway /health answers" || bad "gateway /health"
code() { docker exec wfpod wget -S -qO- "$@" 2>&1 | grep -m1 -o "HTTP/[0-9.]* [0-9]*" | awk '{print $2}'; }       # 127.0.0.1, not localhost: the gateway listens on IPv4
[ "$(code http://127.0.0.1:8094/runs/payment-35)" = 401 ] && ok "a call without the token is refused (401)" || bad "unauthenticated call was not refused"
[ "$(code --header="Authorization: Bearer wrong-token-value-0000" http://127.0.0.1:8094/runs/payment-35)" = 401 ] && ok "a wrong token is refused (401)" || bad "wrong token was not refused"
docker run --rm --network container:wfpod "${LOCK[@]}" "${ENVS[@]}" -e GATEWAY_TOKEN=short -w /app -v "$SRC":/app:ro $PY python /app/gateway.py 2>&1 | grep -q "at least 16" && ok "the gateway refuses to start with a short token" || bad "short token accepted"
X='X-Requested-With: smoke'
if [ -n "$ADMIN_PW" ]; then
  curl -s -c /tmp/gws_admin -o /dev/null -d "username=admin&password=$ADMIN_PW" $APP/admin/login
  for u in "alice:true:false" "bob:false:true" "carol:false:true"; do n=${u%%:*}; r=${u#*:}; curl -s -b /tmp/gws_admin -H 'Content-Type: application/json' -H "$X" -d "{\"username\":\"$n\",\"canSeeSql\":false,\"canSeeSources\":false,\"canUploadFiles\":false,\"canStartWorkflows\":${r%%:*},\"canApprove\":${r#*:}}" $APP/api/app-user-access/update >/dev/null; done
fi
for u in alice bob carol; do curl -s -c /tmp/gws_$u -H 'Content-Type: application/json' -H "$X" -d "{\"username\":\"$u\",\"password\":\"$PW\"}" $APP/app/login -o /dev/null; done
J() { python3 -c "import sys,json;d=json.load(sys.stdin);r=d.get('run') or {};print(d.get('code') or r.get('stage'), len(r.get('approvals',[])))"; }
post() { curl -s -b /tmp/gws_$1 -H 'Content-Type: application/json' -H "$X" -d "$3" $APP$2; }
R=$(post alice /app/workflows/start '{"definition":"payment-exception","key":"34"}'); RID=$(echo "$R" | python3 -c "import sys,json;print(json.load(sys.stdin)['run']['id'])" 2>/dev/null)
[ "$RID" = payment-34 ] && ok "the app started a run through the gateway ($RID)" || { bad "start failed: $(echo "$R" | head -c 200)"; }
for i in $(seq 1 40); do S=$(curl -s -b /tmp/gws_alice -H "$X" $APP/app/workflows/runs/$RID); ST=$(echo "$S" | J | cut -d' ' -f1); [ "$ST" = awaiting_approval ] && break; sleep 3; done
[ "$ST" = awaiting_approval ] && ok "the run reached awaiting_approval with real facts and a recommendation" || bad "run stage: $ST"
H=$(echo "$S" | python3 -c "import sys,json;print(json.load(sys.stdin)['run']['payloadHash'])" 2>/dev/null)
[ "$(post alice /app/workflows/runs/$RID/approve "{\"payloadHash\":\"$H\"}" | J | cut -d' ' -f1)" = missing_grant ] && ok "a user without canApprove is refused (missing_grant)" || bad "missing_grant not returned"
[ "$(post bob /app/workflows/runs/$RID/approve '{"payloadHash":"deadbeefdeadbeef"}' | J | cut -d' ' -f1)" = payload_hash_mismatch ] && ok "a stale hash is refused (payload_hash_mismatch)" || bad "stale hash not refused"
post bob /app/workflows/runs/$RID/approve "{\"payloadHash\":\"$H\"}" | J | grep -Eq "^(awaiting_approval|approved|written_back) " && ok "bob approved" || bad "bob's approval failed"
for i in $(seq 1 20); do S=$(curl -s -b /tmp/gws_alice -H "$X" $APP/app/workflows/runs/$RID); ST=$(echo "$S" | J | cut -d' ' -f1); [ "$ST" = written_back ] && break; sleep 2; done
[ "$ST" = written_back ] && ok "one approval completed this single-approval payment: dry run $(echo "$S" | python3 -c "import sys,json;print(json.load(sys.stdin)['run']['writeBack']['call'])")" || bad "run did not finish: $ST"
docker exec wf-worker python -c "import decisions;print(decisions.verify())" 2>/dev/null | grep -q ok && ok "the workflow's own decision record verifies" || bad "decision record check failed"
echo; [ $fail = 0 ] && echo "ALL PASSED" || echo "FAILED"; cleanup; exit $fail
