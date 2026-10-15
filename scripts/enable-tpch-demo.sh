#!/usr/bin/env bash
# One documented entry point for the TPC-H demo add-on, so nobody has to remember Compose profile
# syntax -- see addons/tpch-demo/README.md for what this actually does and why it's a fully
# separate, standalone stack rather than something layered onto the main docker-compose.yml.
#
# Usage:
#   ./scripts/enable-tpch-demo.sh bundled   # ships its own MinIO + Postgres, pre-loaded
#   ./scripts/enable-tpch-demo.sh byo       # bring your own S3-compatible bucket + Postgres
set -euo pipefail

MODE="${1:-}"
ADDON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../addons/tpch-demo" && pwd)"

if [[ "$MODE" != "bundled" && "$MODE" != "byo" ]]; then
  echo "Usage: $0 bundled|byo" >&2
  echo "  bundled - run with the add-on's own MinIO + Postgres, pre-loaded with ~1GB of TPC-H data" >&2
  echo "  byo     - point LINEITEM and the dimension tables at your own object storage + database" >&2
  echo "            (edit ${ADDON_DIR}/.env first -- see .env.aws.example / .env.oci.example /" >&2
  echo "            .env.azure.example / .env.gcp.example for the values each provider needs)" >&2
  exit 1
fi

if [[ ! -f "${ADDON_DIR}/.env" ]]; then
  echo "No ${ADDON_DIR}/.env found yet." >&2
  if [[ "$MODE" == "bundled" ]]; then
    echo "Copying .env.example -> .env with its working defaults." >&2
    cp "${ADDON_DIR}/.env.example" "${ADDON_DIR}/.env"
  else
    echo "Copy one of .env.aws.example / .env.oci.example / .env.azure.example / .env.gcp.example" >&2
    echo "to ${ADDON_DIR}/.env and fill in your own values first, then re-run this script." >&2
    exit 1
  fi
fi

exec docker compose -f "${ADDON_DIR}/docker-compose.tpch.yml" --profile "tpch-${MODE}" up --build
