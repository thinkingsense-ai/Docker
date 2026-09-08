#!/bin/bash
# Stops and removes all four fixture containers and their data (real containers only -- the seed
# SQL/scripts in this directory are unaffected and can re-create everything with ./seed.sh).
set -euo pipefail
cd "$(dirname "$0")"
docker compose down -v
