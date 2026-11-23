#!/bin/bash
# Smoke test for the Agency workflows pod (agency.workflows.enabled) without a cluster. Builds the workflow image (demos/payment-workflow/Dockerfile, the one the Build Agency image workflow publishes) and uses the
# ensure-register-writer script exactly as the chart renders it:
#  1. a scratch Postgres with the register seed: the init script creates the writer role, which can INSERT but not UPDATE or DELETE;
#  2. the pod's three containers (Temporal, worker, gateway) under the chart's security settings (uid 10001, read-only root filesystem, no capabilities), sharing one network like a pod,
#     beside a running stack (the agency-risk sandbox): the gateway answers /health, refuses a call without its token, and starts an incident-brief run through its contract.
#   NETWORK=<stack>_default ADMIN_TOKEN=<the stack's admin API token> [ASK_URL=http://omnigate:8080] agency/chart/tests/pod-smoke-workflows.sh
# It does NOT test Kubernetes itself (probes, PVC, network policy, Secret and ConfigMap wiring, scheduling): `helm template` covers the rendering.
set -u
cd "$(dirname "$0")/../../.." || exit 1
CHART=${CHART:-resource-manager/omnigateaksstack/helm/omnigate}; IMG=${IMAGE:-agency-workflows-smoke:local}
NETWORK=${NETWORK:?set NETWORK to the stack network}; TOKEN_ADMIN=${ADMIN_TOKEN:?set ADMIN_TOKEN}; ASK=${ASK_URL:-http://omnigate:8080}; GW=smoke-gateway-token-0123456789
PY=${PYTHON_IMAGE:-docker.io/library/python:3.12-slim}; PG=${POSTGRES_IMAGE:-postgres:16-alpine}; SDK=${SDK_VERSION:-1.30.0}
TD=${TEMPORAL_IMAGE:-docker.io/temporalio/temporal@sha256:597a5dbbcc6e7716b326dde4a51622d5ea0879eb0cf06ff8a94381361d0a987d}
fail=0; ok() { echo "  PASS  $*"; }; bad() { echo "  FAIL  $*"; fail=1; }
cleanup() { for n in awf-gateway awf-worker awf-temporal awfpod awf-pg; do docker rm -f $n >/dev/null 2>&1; done; docker volume rm -f awfdata >/dev/null 2>&1; }
trap cleanup EXIT; cleanup
# 1. the init script, as rendered
U=$(python3 -c "import sys;sys.path.insert(0,'scripts');import deploy_options as D;print(D.USERS)")
helm template rel $CHART --set "$U" --set agency.enabled=true --set agency.workflows.enabled=true --set 'demoDatasets={agency-risk}' --set omnigate.license=x --set omnigate.adminApiToken=tok --show-only templates/agency-workflows.yaml > /tmp/awf-render.yaml || { bad "helm template failed"; exit 1; }
python3 - <<'PY'
import re
t = open("/tmp/awf-render.yaml").read(); m = re.search(r"- name: ensure-register-writer.*?command:\n\s+- sh\n\s+- -c\n\s+- \|\n((?:\s{14}.*\n)+?\s{14}SQL\n)", t, re.S)
open("/tmp/awf-init.sh", "w").write("\n".join(l[14:] for l in m.group(1).split("\n")))
PY
docker run -d --name awf-pg -e POSTGRES_PASSWORD=x $PG >/dev/null; sleep 6
docker exec -i awf-pg psql -U postgres -q -v ON_ERROR_STOP=1 < demos/it-risk-register/seed-register-postgres.sql >/dev/null 2>&1 && ok "register seed loaded" || bad "register seed failed"
docker cp /tmp/awf-init.sh awf-pg:/tmp/init.sh
docker exec -e PGUSER=postgres -e PGPASSWORD=x -e PGDATABASE=postgres -e WRITER_PASSWORD=pw-from-secret awf-pg sh /tmp/init.sh >/dev/null 2>&1 && ok "init script ran" || bad "init script failed"
w() { docker exec -e PGPASSWORD=pw-from-secret awf-pg psql -h localhost -U register_writer -d postgres -tA -c "$1" 2>&1; }
w "INSERT INTO register.assessments (item_type, item_ref, node_id, rating, set_by, role, run_id, evidence_digest) SELECT 'system', 'smoke', node_id, 'Low', 'smoke', 'second', 'smoke-1', 'abc' FROM register.taxonomy LIMIT 1" | grep -q "INSERT 0 1" && ok "register_writer can INSERT" || bad "register_writer could not INSERT: $(w "SELECT 1")"
w "UPDATE register.assessments SET rating='High' WHERE run_id='smoke-1'" | grep -qi "permission denied" && ok "register_writer cannot UPDATE" || bad "UPDATE was not refused for lack of permission"
w "DELETE FROM register.assessments WHERE run_id='smoke-1'" | grep -qi "permission denied" && ok "register_writer cannot DELETE" || bad "DELETE was not refused for lack of permission"
# 2. the pod
docker volume create awfdata >/dev/null
docker run --rm -v awfdata:/d alpine sh -c 'chown 10001:10001 /d && chmod 2775 /d'
LOCK=(--user 10001:10001 --read-only --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp:rw,uid=10001,gid=10001,mode=1777 -e HOME=/tmp)
docker build -q -t "$IMG" demos/payment-workflow >/dev/null && ok "workflow image built" || bad "workflow image build failed"
docker run --rm --entrypoint psql "$IMG" --version >/dev/null 2>&1 && ok "the image has the psql client the register write needs" || bad "no psql in the image: the register write would fail after an approval"
docker run -d --name awfpod --network "$NETWORK" alpine sleep 3600 >/dev/null
docker run -d --name awf-temporal --network container:awfpod "${LOCK[@]}" -e USER=temporal -v awfdata:/data $TD server start-dev --ip 0.0.0.0 --headless --db-filename /data/temporal.db >/dev/null
ENVS=(-e PYTHONDONTWRITEBYTECODE=1 -e TEMPORAL_ADDRESS=localhost:7233)
docker run -d --name awf-worker --network container:awfpod "${LOCK[@]}" "${ENVS[@]}" -e ASK_URL=$ASK -e ASK_ADMIN_TOKEN=$TOKEN_ADMIN -e WRITE_BACK=dry-run -e DECISIONS_FILE=/data/decisions.jsonl -e RCA_TABLE_PREFIX=pg. -e RCA_WORKSPACE=it-risk -e QUERY_WORKSPACE=all-data -e SQL_SCHEMA_CONNECTORS="risk=pg,security=mdb" -e REGISTER_WRITE=dry-run -w /app -v awfdata:/data "$IMG" python /app/worker.py >/dev/null
docker run -d --name awf-gateway --network container:awfpod "${LOCK[@]}" "${ENVS[@]}" -e GATEWAY_PORT=8094 -e GATEWAY_TOKEN=$GW -w /app -v awfdata:/data "$IMG" python /app/gateway.py >/dev/null
for i in $(seq 1 40); do docker logs awf-worker 2>&1 | grep -q "worker ready" && break; sleep 2; done
docker logs awf-worker 2>&1 | grep -q "worker ready" && ok "worker ready" || bad "worker did not start: $(docker logs awf-worker 2>&1 | tail -3)"
g() { docker run --rm --network container:awfpod curlimages/curl -s -m 20 -w '\n%{http_code}' "$@"; }
[ "$(g http://localhost:8094/health | tail -1)" = 200 ] && ok "gateway /health" || bad "gateway /health"
[ "$(g http://localhost:8094/runs?stage=awaiting_approval | tail -1)" = 401 ] && ok "gateway refuses a call without its token" || bad "gateway accepted an unauthenticated call"
r=$(g -H "Authorization: Bearer $GW" -H 'Content-Type: application/json' -d '{"definition":"incident-cluster-rca","key":"1","initiator":"smoke","queryId":"q1"}' http://localhost:8094/runs); code=$(echo "$r" | tail -1)
[ "$code" = 201 ] || [ "$code" = 200 ] && ok "gateway started an incident-brief run ($code)" || bad "start answered $code: $(echo "$r" | head -1 | head -c 200)"
sleep 10; r=$(g -H "Authorization: Bearer $GW" http://localhost:8094/runs/rca-1); echo "$r" | head -1 | grep -q '"id": *"rca-1"' && ok "the run can be read back" || bad "run read-back: $(echo "$r" | head -c 200)"
docker logs awf-worker 2>&1 | grep -qi "traceback" && bad "the worker logged a traceback: $(docker logs awf-worker 2>&1 | grep -i -A3 traceback | head -6)" || ok "no traceback in the worker's log"
[ $fail = 0 ] && echo "ALL PASS" || echo "FAILED"; exit $fail
