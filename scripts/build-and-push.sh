#!/usr/bin/env bash
# Builds the omnigate image and pushes it to OCIR. Run this once (or whenever the image changes)
# BEFORE running the Resource Manager stack -- ORM's Terraform runner can't build Docker images
# itself, and a real Marketplace listing shouldn't require deployers to build anything either.
#
# Requires: docker, oci CLI configured (`oci setup config`), and an Auth Token (Console ->
# Profile -> Auth Tokens -- separate from the API signing key used for `oci` itself).
#
# Registry hostname: uses the full ocir.<region>.oci.oraclecloud.com form, not the older short
# <region-key>.ocir.io form -- the short form 401'd with "Unauthorized" against a real Identity
# Domains tenancy (confirmed live) even with a valid, freshly-generated Auth Token; the full form
# worked immediately with the same credentials. If you hit the same error, also try prefixing the
# username with the identity domain, e.g. <namespace>/oracleidentitycloudservice/<username>.
#
# Usage (auth token piped via stdin, not left in shell history):
#   OCI_COMPARTMENT_OCID=ocid1.compartment... \
#   ./scripts/build-and-push.sh --region us-phoenix-1 --repo omnigate --username jdoe@example.com <<< "$AUTH_TOKEN"
set -euo pipefail

TAG="latest"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --region) REGION="$2"; shift 2 ;;
    --repo) REPO_NAME="$2"; shift 2 ;;
    --username) OCI_USERNAME="$2"; shift 2 ;;
    --tag) TAG="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

: "${REGION:?--region is required, e.g. us-phoenix-1}"
: "${REPO_NAME:?--repo is required, e.g. omnigate}"
: "${OCI_USERNAME:?--username is required -- your OCI console username/email}"

NAMESPACE=$(oci os ns get --query 'data' --raw-output)
REGISTRY="ocir.${REGION}.oci.oraclecloud.com"
IMAGE="${REGISTRY}/${NAMESPACE}/${REPO_NAME}:${TAG}"

echo "Namespace: ${NAMESPACE}"
echo "Target image: ${IMAGE}"

echo "--- Ensuring OCIR repository exists ---"
oci artifacts container repository create \
  --compartment-id "${OCI_COMPARTMENT_OCID:?set OCI_COMPARTMENT_OCID}" \
  --display-name "${REPO_NAME}" \
  --is-public false \
  --region "${REGION}" \
  2>/dev/null || echo "(repository likely already exists, continuing)"

echo "--- docker login (reading Auth Token from stdin) ---"
docker login "${REGISTRY}" -u "${NAMESPACE}/${OCI_USERNAME}" --password-stdin

echo "--- Building (this compiles llama-server from source, expect several minutes) ---"
cd "$(dirname "$0")/.."
docker build -t "${IMAGE}" .

echo "--- Pushing ---"
docker push "${IMAGE}"

echo ""
echo "Done. Set this as image_repository in terraform/variables.tf's default (or pass -var):"
echo "  ${REGISTRY}/${NAMESPACE}/${REPO_NAME}"
