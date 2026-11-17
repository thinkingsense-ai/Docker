#!/bin/bash
# Smoke test for the cloud add-on without a cluster: runs the four containers of the add-on pod under the same security settings the chart sets (non-root uid 10001,
# read-only root filesystem, no capabilities, no privilege escalation, writable volumes owned by gid 10001 as fsGroup does), sharing one network like a pod, against a running
# Treasury stack, then starts a workflow, approves it and checks the decision record.
#   NETWORK=treasury-pack_default ASK_URL=http://omnigate:8080 demos/payment-workflow/tests/pod-smoke.sh
# It does NOT test Kubernetes itself (probes, PVC binding, network policy, scheduling): that needs a cluster.
set -u
cd "$(dirname "$0")/../../.." || exit 1
SRC=${CHART_FILES:-$PWD/resource-manager/omnigateaksstack/helm/omnigate/files/payment-workflow}
NETWORK=${NETWORK:-treasury-pack_default}; ASK_URL=${ASK_URL:-http://omnigate:8080}; PORT=${PORT:-8095}
TD=${TEMPORAL_IMAGE:-docker.io/temporalio/temporal@sha256:597a5dbbcc6e7716b326dde4a51622d5ea0879eb0cf06ff8a94381361d0a987d}
PY=${PYTHON_IMAGE:-docker.io/library/python:3.12-slim}; SDK=${SDK_VERSION:-1.30.0}
fail=0; ok() { echo "  PASS  $*"; }; bad() { echo "  FAIL  $*"; fail=1; }
cleanup() { for n in wf-erp wf-inbox wf-worker wf-temporal wfpod; do docker rm -f $n >/dev/null 2>&1; done; docker volume rm -f wfdata wfpylib >/dev/null 2>&1; }
cleanup; docker volume create wfdata >/dev/null; docker volume create wfpylib >/dev/null
docker run --rm -v wfdata:/d -v wfpylib:/p alpine sh -c 'chown 10001:10001 /d /p && chmod 2775 /d /p'
LOCK=(--user 10001:10001 --read-only --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp:rw,uid=10001,gid=10001,mode=1777 -e HOME=/tmp)
echo "init container"; docker run --rm "${LOCK[@]}" -v wfpylib:/pylib $PY pip install --no-cache-dir --disable-pip-version-check --target /pylib temporalio==$SDK >/dev/null 2>&1 && ok "SDK installed as non-root on a read-only root filesystem" || bad "SDK install failed"
docker run -d --name wfpod --network "$NETWORK" -p $PORT:8085 alpine sleep 3600 >/dev/null
docker run -d --name wf-temporal --network container:wfpod "${LOCK[@]}" -e USER=temporal -v wfdata:/data $TD server start-dev --ip 0.0.0.0 --headless --db-filename /data/temporal.db >/dev/null
ENVS=(-e PYTHONPATH=/pylib:/app -e PYTHONDONTWRITEBYTECODE=1 -e TEMPORAL_ADDRESS=localhost:7233 -e ASK_URL=$ASK_URL -e ERP_URL=http://localhost:8086 -e WRITE_BACK=dry-run -e DECISIONS_FILE=/data/decisions.jsonl -e ASK_USER= ${ASK_ADMIN_TOKEN:+-e ASK_ADMIN_TOKEN=$ASK_ADMIN_TOKEN})
docker run -d --name wf-worker --network container:wfpod "${LOCK[@]}" "${ENVS[@]}" -w /app -v "$SRC":/app:ro -v wfpylib:/pylib:ro -v wfdata:/data $PY python /app/worker.py >/dev/null
docker run -d --name wf-inbox --network container:wfpod "${LOCK[@]}" "${ENVS[@]}" -w /app -v "$SRC":/app:ro -v wfpylib:/pylib:ro -v wfdata:/data $PY python /app/inbox.py >/dev/null
docker run -d --name wf-erp --network container:wfpod --user 10001:10001 --read-only --cap-drop ALL --security-opt no-new-privileges -e PYTHONDONTWRITEBYTECODE=1 -w /app -v "$SRC":/app:ro $PY python /app/erp_mock.py 8086 >/dev/null
echo "waiting for the pod"; for i in $(seq 1 60); do curl -sf localhost:$PORT/api/config -o /dev/null && break; sleep 2; done
for c in wf-temporal wf-worker wf-inbox wf-erp; do [ "$(docker inspect -f '{{.State.Running}}' $c)" = true ] && ok "$c is running" || { bad "$c exited: $(docker logs $c 2>&1 | tail -2 | tr '\n' ' ')"; }; done
curl -s localhost:$PORT/api/config | grep -q '"ask": false' && ok "the Ask box and SAP tab are off (no Ask password in the cloud)" || bad "config: $(curl -s localhost:$PORT/api/config)"
N=$(curl -s localhost:$PORT/api/pending | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 'ERR '+str(d)[:100])"); [ "$N" = 7 ] && ok "the inbox reads the 7 pending Treasury payments through the app" || bad "pending: $N"
curl -s -X POST localhost:$PORT/api/start -H 'Content-Type: application/json' -d '{"payment_id":34}' | grep -q true && ok "workflow for payment 34 started" || bad "start failed"
for i in $(seq 1 40); do ST=$(curl -s localhost:$PORT/api/pending | python3 -c "import sys,json; print(([x for x in json.load(sys.stdin) if x['payment_id']=='34'][0]['workflow'] or {}).get('stage'))" 2>/dev/null); [ "$ST" = awaiting_approval ] && break; sleep 3; done
[ "$ST" = awaiting_approval ] && ok "recommendation made, waiting for approval (model: $(curl -s localhost:$PORT/api/pending | python3 -c "import sys,json; print([x for x in json.load(sys.stdin) if x['payment_id']=='34'][0]['workflow']['recommendation']['model'])"))" || bad "stage is $ST"
H=$(curl -s localhost:$PORT/api/pending | python3 -c "import sys,json; print([x for x in json.load(sys.stdin) if x['payment_id']=='34'][0]['workflow']['payload_hash'])" 2>/dev/null)
curl -s -X POST localhost:$PORT/api/decide -H 'Content-Type: application/json' -d "{\"payment_id\":34,\"approver\":\"m.okafor\",\"action\":\"approve\",\"hash\":\"$H\"}" >/dev/null; sleep 5
curl -s localhost:$PORT/api/decisions | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['chain'], len(d['records']))" | grep -q "^ok 1" && ok "decision recorded on the shared volume, hash chain ok" || bad "decisions: $(curl -s localhost:$PORT/api/decisions | head -c 200)"
docker exec wf-erp sh -c 'touch /app/x 2>&1' | grep -qi "read-only" && ok "the root filesystem really is read-only" || bad "root filesystem is writable"
cleanup; echo; [ $fail = 0 ] && echo "ALL PASSED" || echo "FAILURES ABOVE"; exit $fail
