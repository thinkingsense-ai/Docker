#!/bin/bash
# Agency on this machine: the all-packs stack (six packs, 76 approved questions), the thinking layer with the new UI, the table/document/image adapters, upload sharing on,
# pack Workspaces loaded, and demo logins with different grants. From anywhere:
#   agency/local/up.sh            start (first run builds images and downloads the embedding model and the museum sample: several minutes)
#   agency/local/up.sh down       stop and wipe the data
#   agency/local/up.sh layer      rebuild and restart only the thinking layer (and its UI) after you change addons/thinking-layer or agency/web
# Set OMNIGATE_LLM_API_KEY to your Anthropic key for free-form questions; without it the approved questions still work. LOCAL ONLY.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../.." && pwd); cd "$ROOT"
F=(-f docker-compose.yml -f demos/all-packs/docker-compose.packs.yml -f addons/thinking-layer/docker-compose.layer.yml -f addons/table-adapter/docker-compose.table.yml
   -f addons/document-adapter/docker-compose.document.yml -f addons/image-adapter/docker-compose.image.yml -f agency/local/docker-compose.agency-local.yml
   -f demos/it-risk-rca/docker-compose.rca.yml)
# The IT-risk root-cause case (demos/it-risk-rca): its questions join the all-packs ones in one file for the question seeder.
mkdir -p agency/local/.runtime
python3 - <<'PY'
import json
a = json.load(open("demos/all-packs/demo-questions-all-packs.json")); b = json.load(open("demos/it-risk-rca/demo-questions-rca.json"))
json.dump(a + b, open("agency/local/.runtime/demo-questions.json", "w"), indent=1)
PY
[ -f agency/local/commercial.override.yml ] && F+=(-f agency/local/commercial.override.yml)
dc() { docker compose --project-directory . -p "${AGENCY_PROJECT:-agency-local}" "${F[@]}" "$@"; }
case "${1:-up}" in
  down) dc down -v; exit 0;;
  layer) export OMNIGATE_LLM_API_KEY=${OMNIGATE_LLM_API_KEY:-dummy}; dc up --build -d thinking-layer; exit 0;;
esac
export OMNIGATE_LLM_API_KEY=${OMNIGATE_LLM_API_KEY:-dummy}
dc up --build -d
python3 "$HERE/bootstrap.py"
echo
echo "Agency  http://localhost:8097   sign in as curator / Curator-SI-1 (everything), alice / demo (starts workflows), bob and carol / demo (approve), public / Public-SI-1 (restricted)"
echo "Ask     http://localhost:8080   Admin  http://localhost:8080/admin  admin / Admin-SI-1"
[ -z "${OMNIGATE_LLM_API_KEY##dummy}" ] && echo "No model key set: approved questions work, free-form ones will not (export OMNIGATE_LLM_API_KEY=sk-ant-... and run this again)."
