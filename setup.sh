#!/usr/bin/env bash
# The one setup entry point for this repo -- asks the handful of real questions a new user
# actually needs to answer, then runs the right `docker compose` invocation underneath. You never
# need to know docker-compose.tpch.yml, --profile, or free-edition/ exist to get started; this
# script is the on-ramp, the individual READMEs (addons/tpch-demo/README.md, this repo's own
# README.md) are reference material for anyone who wants to go deeper afterward.
#
# Fully non-interactive mode for scripted installs -- skips every prompt:
#   ./setup.sh --llm-mode local --demo tpch --tpch-mode bundled
#   ./setup.sh --llm-mode cloud --llm-api-key sk-ant-... --demo supply-chain
#   ./setup.sh --llm-mode local --demo none
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

LLM_MODE=""
LLM_API_KEY=""
DEMO=""
TPCH_MODE=""
NON_INTERACTIVE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --llm-mode) LLM_MODE="$2"; NON_INTERACTIVE=true; shift 2 ;;
    --llm-api-key) LLM_API_KEY="$2"; shift 2 ;;
    --demo) DEMO="$2"; NON_INTERACTIVE=true; shift 2 ;;
    --tpch-mode) TPCH_MODE="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--llm-mode local|cloud] [--llm-api-key KEY] [--demo none|supply-chain|tpch] [--tpch-mode bundled|byo]"
      exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

echo "ThinkingSense setup"
echo "───────────────────"

# ---- Hardware note -----------------------------------------------------------------------------
# Real, disclosed limitation: GPU acceleration for the local models (the llama.cpp sidecars and
# the TabPFN predictor) doesn't exist in this repo yet -- both sidecar images are built CPU-only
# today (see sidecars/llama/Dockerfile and sidecars/tabpfn/Dockerfile's own comments). This script
# does not pretend otherwise by offering a GPU option that doesn't work.
echo
echo "Note: local-model acceleration is CPU-only in this release. GPU support is planned but not"
echo "yet available -- proceeding with CPU."

# ---- 1. LLM mode --------------------------------------------------------------------------------
if [[ -z "$LLM_MODE" ]]; then
  echo
  echo "1) How should ThinkingSense answer questions?"
  echo "   [1] Fully local -- no data ever leaves this machine, no API key needed (slower, free)"
  echo "   [2] Cloud-assisted -- escalates to a hosted model (Anthropic) when the local model"
  echo "       isn't confident (faster/more capable, needs an API key)"
  read -rp "   > " choice
  case "$choice" in
    2) LLM_MODE="cloud" ;;
    *) LLM_MODE="local" ;;
  esac
fi

if [[ "$LLM_MODE" == "cloud" && -z "$LLM_API_KEY" && "$NON_INTERACTIVE" == false ]]; then
  read -rp "   Paste your Anthropic API key (or press Enter to add it later): " LLM_API_KEY
fi

# ---- 2. Which demo --------------------------------------------------------------------------------
if [[ -z "$DEMO" ]]; then
  echo
  echo "2) Sample data:"
  echo "   [1] None -- I'll connect my own database(s) (see README.md: \"Add your own database\")"
  echo "   [2] Supply-chain demo -- small, ships with this repo, up in under a minute"
  echo "   [3] TPC-H demo -- a real ~1GB analytical dataset"
  read -rp "   > " choice
  case "$choice" in
    1) DEMO="none" ;;
    3) DEMO="tpch" ;;
    *) DEMO="supply-chain" ;;
  esac
fi

if [[ "$DEMO" == "tpch" && -z "$TPCH_MODE" ]]; then
  echo
  echo "3) Where should the TPC-H data live?"
  echo "   [1] Bundled -- we create a local MinIO + Postgres for you, pre-loaded"
  echo "   [2] Bring your own -- your own AWS/OCI/Azure/GCP bucket and your own Postgres"
  read -rp "   > " choice
  case "$choice" in
    2) TPCH_MODE="byo" ;;
    *) TPCH_MODE="bundled" ;;
  esac
fi

# ---- Run it -------------------------------------------------------------------------------------
echo
case "$DEMO" in
  none)
    echo "No bundled demo selected."
    echo "Next step: edit OMNIGATE_BACKENDS in docker-compose.yml to point at your own database(s)"
    echo "-- see README.md's \"Add your own database\" section -- then run:"
    echo "    docker compose up --build"
    if [[ "$LLM_MODE" == "cloud" ]]; then
      echo "Set OMNIGATE_LLM_API_KEY=${LLM_API_KEY:-<your key>} in a .env file next to docker-compose.yml first."
    fi
    exit 0
    ;;
  supply-chain)
    if [[ "$LLM_MODE" == "cloud" ]]; then
      echo "OMNIGATE_LLM_API_KEY=${LLM_API_KEY}" > "${ROOT_DIR}/.env"
    fi
    echo "Starting the supply-chain demo (this may take a few minutes on first run -- downloading"
    echo "model weights and the Postgres image)..."
    exec docker compose -f "${ROOT_DIR}/docker-compose.yml" up --build
    ;;
  tpch)
    TPCH_ENV="${ROOT_DIR}/addons/tpch-demo/.env"
    if [[ ! -f "$TPCH_ENV" ]]; then
      if [[ "${TPCH_MODE:-bundled}" == "bundled" ]]; then
        cp "${ROOT_DIR}/addons/tpch-demo/.env.example" "$TPCH_ENV"
      else
        echo "No ${TPCH_ENV} found yet. Copy one of .env.aws.example / .env.oci.example /" >&2
        echo ".env.azure.example / .env.gcp.example to ${TPCH_ENV} and fill in your own values," >&2
        echo "then re-run this script." >&2
        exit 1
      fi
    fi
    if [[ "$LLM_MODE" == "cloud" ]]; then
      echo "OMNIGATE_LLM_API_KEY=${LLM_API_KEY}" >> "$TPCH_ENV"
    fi
    exec "${ROOT_DIR}/scripts/enable-tpch-demo.sh" "${TPCH_MODE:-bundled}"
    ;;
  *)
    echo "Unknown --demo value: $DEMO (expected none|supply-chain|tpch)" >&2
    exit 1
    ;;
esac
