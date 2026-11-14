#!/bin/bash
# Runs one variant of the free-form accuracy benchmark on a local stack, end to end:
#   stack up (question bank OFF, model calls through the logging proxy) -> reference rows -> N runs, each judged -> context report -> stack down
#
#   export ANTHROPIC_API_KEY=sk-ant-...
#   demos/benchmark/tools/run_variant.sh <treasury|bom> <variant-name> <runs> [--comments]
#
# --comments  also writes each table's description into the database (COMMENT ON TABLE ...), which is where the app reads descriptions for its prompts.
# Environment: BENCH_MODEL (default claude-haiku-5-5), OMNIGATE_RELEASE_TAG (default v0.10.17), BENCH_OUT (default /tmp/bench-out), JUDGE_MODEL (default claude-haiku-5-5).
# Results land in $BENCH_OUT as <pack>_<variant>_<model>_r<N>.json (answers), j_..._r<N>.json (judged) and calls_...jsonl (every prompt and reply).
# Needs: docker compose, python3 with the anthropic package, and free ports 8080 and 9099. Takes about 10 minutes per run (BOM 13).
set -u
PACK=$1; VAR=$2; RUNS=$3; COMMENTS=${4:-}
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../../.." && pwd)
export BENCH_MODEL=${BENCH_MODEL:-claude-haiku-5-5}; OUT=${BENCH_OUT:-/tmp/bench-out}; mkdir -p "$OUT"
TAG=${PACK}_${VAR}_${BENCH_MODEL#claude-}; CALLS=$OUT/calls_$TAG.jsonl; rm -f "$CALLS"
BV=TREASURY_BANK_RETRIEVAL; [ "$PACK" = bom ] && BV=BOM_BANK_RETRIEVAL
FILES=(-f "$ROOT/demos/$PACK-pack/docker-compose.$PACK.yml" -f "$HERE/override-proxy.yml")
if [ "$COMMENTS" = "--comments" ]; then
  python3 "$HERE/gen_comments.py" "$PACK" > "$OUT/comments-$PACK-pg.sql"
  { echo "services:"; echo "  postgres:"; echo "    volumes:"; echo "      - $OUT/comments-$PACK-pg.sql:/docker-entrypoint-initdb.d/02-comments.sql:ro"; } > "$OUT/comments-$PACK.yml"
  if [ "$PACK" = treasury ]; then
    python3 "$HERE/gen_comments.py" "$PACK" --mariadb > "$OUT/comments-$PACK-mdb.sql"
    { echo "  mariadb:"; echo "    volumes:"; echo "      - $OUT/comments-$PACK-mdb.sql:/docker-entrypoint-initdb.d/03-comments.sql:ro"; } >> "$OUT/comments-$PACK.yml"
  fi
  FILES+=(-f "$OUT/comments-$PACK.yml")
fi
pkill -f llmproxy.py 2>/dev/null; sleep 1; (nohup python3 "$HERE/llmproxy.py" 9099 "$CALLS" > "$OUT/proxy.log" 2>&1 &); sleep 1
cd "$ROOT" || exit 1
echo "[$TAG] up $(date +%T)"
env OMNIGATE_RELEASE_TAG=${OMNIGATE_RELEASE_TAG:-v0.10.17} $BV=false OMNIGATE_LLM_API_KEY="$ANTHROPIC_API_KEY" docker compose --project-directory . "${FILES[@]}" up --build -d > "$OUT/up-$TAG.log" 2>&1
for i in $(seq 1 80); do n=$(docker ps --format '{{.Names}}' | grep -c "seed-"); [ "$n" = 0 ] && break; sleep 5; done
python3 "$HERE/reference_rows.py" "$ROOT/demos/benchmark/benchmark-$PACK.json" "$OUT/ref_$PACK.json"
for i in $(seq 1 "$RUNS"); do
  python3 "$HERE/bench_run.py" "$ROOT/demos/benchmark/benchmark-$PACK.json" "$OUT/${TAG}_r$i.json" "$CALLS" | tail -1
  JUDGE_MODEL=${JUDGE_MODEL:-claude-haiku-5-5} python3 "$HERE/judge.py" "$OUT/ref_$PACK.json" "$OUT/${TAG}_r$i.json" "$OUT/j_${TAG}_r$i.json"
  echo "[$TAG] run $i done $(date +%T)"
done
KN=$(ls "$ROOT"/demos/$PACK-pack/*-knowledge.json | head -1)
python3 "$HERE/context_report.py" "$ROOT/demos/benchmark/benchmark-$PACK.json" "$KN" "$OUT/${TAG}_r1.json" "$CALLS" | head -3
docker compose --project-directory . "${FILES[@]}" down -v 2>&1 | tail -1; pkill -f llmproxy.py
echo "[$TAG] finished $(date +%T)"
