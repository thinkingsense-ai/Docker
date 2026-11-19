#!/bin/bash
# Runs several models one after another ON a benchmark node, in the background, with the judge key read from STDIN (never an argument, never a file).
#   printf '%s' "$ANTHROPIC_API_KEY" | ssh ubuntu@<node> 'bash ~/Docker/demos/benchmark/local-models/queue.sh <shape> <pack> <runs> <model-id> [<model-id> ...]'
# Progress: ~/queue.log on the node; results in ~/bench-out (copy them back with rsync; then `oci_node.py reap --yes` or terminate the node).
# The key is held only in the environment of the background job (the app container gets a dummy: see override-local.yml).
set -u
IFS= read -r K; export ANTHROPIC_API_KEY="$K"; unset K
SHAPE=$1; PACK=$2; RUNS=$3; shift 3
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../../.." && pwd)
export PATH=$HOME/venv/bin:$PATH BENCH_OUT=${BENCH_OUT:-$HOME/bench-out} OMNIGATE_RELEASE_TAG=${OMNIGATE_RELEASE_TAG:-v0.10.21}
mkdir -p "$BENCH_OUT"; cd "$ROOT" || exit 1
( for m in "$@"; do
    echo "=== $m on $SHAPE start $(date -u +%T)"
    "$HERE/run_local.sh" "$m" "$SHAPE" "$PACK" "$RUNS" || echo "=== $m FAILED"
    echo "=== $m end $(date -u +%T)"
  done; echo "=== queue finished $(date -u +%T)" ) > "$HOME/queue.log" 2>&1 < /dev/null &
sleep 1; echo "queued: $* (log ~/queue.log)"
