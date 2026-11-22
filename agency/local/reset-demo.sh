#!/usr/bin/env bash
# Puts the local sandbox back to a clean demo state, so the guided tour (or the demo storyline) can run again. Every workflow run can only be started once, and each finished run leaves a decision-record entry
# and possibly a register row, so a rehearsal uses them up. This clears: the Temporal and decision-record volumes, and the risk register and major-incident tables (back to their three invented seed rows).
# It keeps: the feed history, the estate and rca data, and the approved questions. Local sandbox only.
#   AGENCY_PROJECT=agency-risk agency/local/reset-demo.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
P=${AGENCY_PROJECT:-agency-local}
# the layer mounts the decision-record volume, so it has to stop too before Docker will delete the volume
docker rm -f "${P}-worker-1" "${P}-gateway-1" "${P}-temporal-1" "${P}-thinking-layer-1" >/dev/null 2>&1 || true
docker volume rm "${P}_temporal-data" "${P}_workflow-data" >/dev/null 2>&1 || true
docker exec -i "${P}-postgres-1" psql -U postgres -d postgres -v ON_ERROR_STOP=1 -q < demos/it-risk-register/seed-register-postgres.sql
docker exec -i "${P}-postgres-1" psql -U postgres -d postgres -q < demos/it-risk-register/grant-register.sql    # must run after every reload, or the Server's read role loses access
AGENCY_PROJECT="$P" agency/local/up.sh
echo "Reset done. Sign in at http://localhost:8097 and press Quickstart tour."
