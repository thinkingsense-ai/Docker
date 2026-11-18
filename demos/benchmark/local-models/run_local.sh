#!/bin/bash
# One model on one shape, end to end: fetch -> serve -> (logging proxy) -> the existing benchmark -> meta file -> stop.
#
#   export ANTHROPIC_API_KEY=sk-ant-...        # for the judge only
#   demos/benchmark/local-models/run_local.sh <model-id> <shape-id> <treasury|bom> <runs> [--vision] [run_variant.sh flags]
#
# Run it ON the node (an OCI instance from oci_node.py, or this laptop with shape local-docker). Results: $BENCH_OUT (default /tmp/bench-out):
# <pack>_base_<model>-<shape>_r<N>.json, j_..._r<N>.json, calls_...jsonl and meta_<model>-<shape>.json (command, hashes, image id).
# Summarise with: python3 report.py summary $BENCH_OUT <pack>_base_<model>-<shape>
set -eu
MID=$1; SID=$2; PACK=$3; RUNS=$4; shift 4
VISION=""; REST=()
for a in "$@"; do [ "$a" = "--vision" ] && VISION="--vision" || REST+=("$a"); done
HERE=$(cd "$(dirname "$0")" && pwd); TOOLS="$HERE/../tools"
export BENCH_OUT=${BENCH_OUT:-/tmp/bench-out}; mkdir -p "$BENCH_OUT"
export BENCH_MODEL="$MID-$SID"                       # becomes the tag in every result file name
export BENCH_OVERRIDE="$HERE/override-local.yml"
PORT=8091
python3 "$HERE/fetch.py" "$MID" ${VISION:+--vision}
python3 "$HERE/serve.py" up "$MID" "$SID" --port $PORT $VISION --meta "$BENCH_OUT/meta_$MID-$SID.json"
trap 'python3 "$HERE/serve.py" down >/dev/null 2>&1 || true' EXIT
export LLM_UPSTREAM="http://127.0.0.1:$PORT"
"$TOOLS/run_variant.sh" "$PACK" base "$RUNS" ${REST[@]+"${REST[@]}"}
