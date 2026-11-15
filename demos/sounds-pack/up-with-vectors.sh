#!/bin/bash
# Starts the sounds pack with the audio embeddings loaded as sounds.recording_embeddings (pgvector), so Ask can answer
# "which recordings sound most like xc1072993?". One command, from anywhere:
#   export OMNIGATE_LLM_API_KEY=sk-ant-...
#   demos/sounds-pack/up-with-vectors.sh [plain|defined] [extra docker compose args, e.g. -d]
#   docker compose --project-directory . -f demos/sounds-pack/docker-compose.sounds.yml down -v     # to stop (from the repository root)
# plain: comments only say what the column is; defined (default): they also say how to use it. The vectors are not committed (they derive from non-commercial
# recordings): the first run makes them with ../multimodal-poc/embed_audio.py, which needs the audio cache (fetch_data.py) and torch + transformers.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../.." && pwd); MODE=${1:-defined}; [ $# -gt 0 ] && shift
NPZ="$ROOT/demos/multimodal-poc/out/embeddings.npz"
if [ ! -f "$NPZ" ]; then
  [ -d "$ROOT/demos/multimodal-poc/cache/audio" ] || { echo "No audio cache. Run: python3 demos/multimodal-poc/fetch_data.py   (about 10 minutes), then this script again." >&2; exit 1; }
  echo "Making the audio embeddings (once)..."; python3 "$ROOT/demos/multimodal-poc/embed_audio.py" >/dev/null || { echo "embed_audio.py failed: needs torch, transformers, soundfile, scipy" >&2; exit 1; }
fi
[ -n "${OMNIGATE_LLM_API_KEY:-}" ] || { echo "Set OMNIGATE_LLM_API_KEY first." >&2; exit 1; }
TMP=$(mktemp -d); python3 "$HERE/experiments/make_vector_sql.py" "$MODE" > "$TMP/vectors.sql"
cat > "$TMP/override.yml" <<YML
services:
  postgres:
    image: pgvector/pgvector:pg16
    volumes:
      - $TMP/vectors.sql:/docker-entrypoint-initdb.d/09-vectors.sql:ro
YML
cd "$ROOT" && exec docker compose --project-directory . -f demos/sounds-pack/docker-compose.sounds.yml -f "$TMP/override.yml" up --build "$@"
