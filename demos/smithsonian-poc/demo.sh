#!/bin/bash
# One-stop helper for the Smithsonian POC demo. See SETUP.md.
#   ./demo.sh check    verify the prerequisites
#   ./demo.sh models   start the three local model servers (if not already running)
#   ./demo.sh up       load data, start the demo, build the vocabulary, approve the demo questions
#   ./demo.sh status   what is running
#   ./demo.sh stop     stop the demo (and the model servers this script started)
#   ./demo.sh reset    stop, then delete the demo's saved settings so the next "up" starts clean
set -uo pipefail
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"
MODELS="${OMNIGATE_MODELS_DIR:-$HOME/.cache/omnigate-models}"
AGENTIC_MODEL="$MODELS/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
FAST_MODEL="$MODELS/qwen2.5-0.5b-instruct-q4_k_m.gguf"
EMBED_MODEL="$MODELS/nomic-embed-text-v1.5.Q4_K_M.gguf"
PORT=8110
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Admin-SI-1}"
COOKIE=/tmp/si-demo-admin.txt

say() { printf '%s\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1 && say "  ok   $1" || { say "  MISSING $1 -- $2"; MISSING=1; }; }
up_port() { curl -s -m 3 -o /dev/null "http://127.0.0.1:$1$2"; }

check() {
  MISSING=0
  say "Prerequisites:"
  need java "install a Java 21 JDK"
  need mvn "install Maven (only needed to build the jar)"
  need psql "install PostgreSQL client tools"
  need llama-server "brew install llama.cpp"
  need curl "install curl"
  need python3 "install Python 3"
  for f in "$AGENTIC_MODEL" "$FAST_MODEL" "$EMBED_MODEL"; do
    [ -f "$f" ] && say "  ok   $(basename "$f")" || { say "  MISSING model $f (see SETUP.md, 'Download the models')"; MISSING=1; }
  done
  [ -f "$ROOT/target/omnigate.jar" ] && say "  ok   target/omnigate.jar" || { say "  MISSING target/omnigate.jar -- run: (cd web && npm ci && npm run build) && mvn -DskipTests package"; MISSING=1; }
  psql -h 127.0.0.1 -d postgres -Atc "select 1" >/dev/null 2>&1 && say "  ok   Postgres reachable on 127.0.0.1:5432" || { say "  MISSING a Postgres on 127.0.0.1:5432 you can log into without a password"; MISSING=1; }
  [ "$MISSING" = 0 ] && say "All set." || { say "Fix the items above, then run ./demo.sh check again."; return 1; }
}

start_model() { # name port model extra...
  local name=$1 port=$2 model=$3; shift 3
  if curl -s -m 2 "http://127.0.0.1:$port/health" >/dev/null 2>&1; then say "  $name already running on :$port"; return; fi
  nohup llama-server -m "$model" --port "$port" --host 127.0.0.1 -ngl 0 "$@" > "/tmp/si-demo-$name.log" 2>&1 &
  echo $! >> /tmp/si-demo-models.pids
  say "  started $name on :$port"
}

models() {
  say "Local model servers:"
  start_model agentic 18090 "$AGENTIC_MODEL" -c 8192
  start_model fast 8092 "$FAST_MODEL" -c 4096
  start_model embeddings 8120 "$EMBED_MODEL" --embeddings -c 2048
  for p in 18090 8092 8120; do
    for i in $(seq 1 30); do curl -s -m 2 "http://127.0.0.1:$p/health" >/dev/null 2>&1 && break; sleep 2; done
    curl -s -m 2 "http://127.0.0.1:$p/health" >/dev/null 2>&1 && say "  ready :$p" || say "  NOT READY :$p (see /tmp/si-demo-*.log)"
  done
}

wait_ready() {
  for i in $(seq 1 40); do
    [ "$(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/admin/login)" = 200 ] && return 0; sleep 3
  done; return 1
}

up() {
  check || return 1
  models
  say "Loading the data into Postgres (database si_poc)..."; ./load-data.sh || return 1
  say "Starting the demo on :$PORT..."; [ -f server.pid ] && kill "$(cat server.pid)" 2>/dev/null; sleep 2
  ./launch.sh >/dev/null; wait_ready || { say "The demo did not start; see server.log"; return 1; }
  rm -f "$COOKIE"; curl -s -c "$COOKIE" -o /dev/null -d "username=admin&password=$ADMIN_PASSWORD" "http://127.0.0.1:$PORT/admin/login"
  say "Building the subject vocabulary (about a minute)..."
  curl -s -b "$COOKIE" -H 'Content-Type: application/json' \
    -d '{"backend":"si","table":"si_topics","labelColumn":"topic","unitColumn":"unit_code","mergeThreshold":0.90,"reviewThreshold":0.80}' \
    "http://127.0.0.1:$PORT/api/ontology/vocabulary/build"; echo
  curl -s -b "$COOKIE" "http://127.0.0.1:$PORT/api/ontology/vocabulary/concepts.csv" > vocabulary-concepts.csv
  ./load-vocabulary.sh || return 1
  ./approve-demo-questions.sh || return 1
  say ""; say "Ready. Admin  http://127.0.0.1:$PORT/admin   (admin / $ADMIN_PASSWORD)"
  say "       Ask    http://localhost:$PORT         (curator / Curator-SI-1, public / Public-SI-1)"
  say "Tip: use 127.0.0.1 for the admin and localhost for Ask so the two sign-ins do not replace each other."
}

status() {
  for pair in "agentic model:18090:/health" "fast model:8092:/health" "embedding model:8120:/health" "demo app:$PORT:/admin/login"; do
    IFS=: read -r label port path <<<"$pair"
    up_port "$port" "$path" && say "  up    $label (:$port)" || say "  down  $label (:$port)"
  done
}

stop() {
  [ -f server.pid ] && kill "$(cat server.pid)" 2>/dev/null && say "  stopped the demo"; rm -f server.pid
  pkill -f "demo-smithsonian-poc/run.jar" 2>/dev/null
  [ -f /tmp/si-demo-models.pids ] && xargs kill < /tmp/si-demo-models.pids 2>/dev/null && say "  stopped the model servers this script started"; rm -f /tmp/si-demo-models.pids
}

case "${1:-}" in
  check) check ;;
  models) models ;;
  up) up ;;
  status) status ;;
  stop) stop ;;
  reset) stop; rm -rf data audit.log server.log; say "  cleared the demo's saved settings" ;;
  *) sed -n 2,9p "$0" ;;
esac
