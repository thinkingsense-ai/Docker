#!/bin/bash
# Runs the audio demo on this machine: http://localhost:8090  (Ask, if you want it beside it: demos/sounds-pack/docker-compose.sounds.yml, http://localhost:8080)
# First time: python3 -m venv .venv && .venv/bin/pip install -r demos/audio-demo/requirements.txt
#             python3 demos/multimodal-poc/fetch_data.py && python3 demos/multimodal-poc/embed_audio.py        (the audio, about 10 minutes, then its vectors)
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../.." && pwd)
PY=${PYTHON:-$([ -x "$ROOT/.venv/bin/python" ] && echo "$ROOT/.venv/bin/python" || echo python3)}
[ -f "$ROOT/demos/multimodal-poc/out/embeddings.npz" ] || { echo "No audio vectors yet. Run demos/multimodal-poc/fetch_data.py then embed_audio.py first." >&2; exit 1; }
exec "$PY" "$HERE/server.py" "${1:-8090}"
