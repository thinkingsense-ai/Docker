#!/usr/bin/env bash
# The reverse of setup.sh. Tries the real `terraform destroy` first -- needs this exact
# clone/directory's terraform.tfstate, which is why README's "Reconnecting to an existing
# deployment" section matters: re-clicking the Cloud Shell deploy button gets you a fresh clone
# with no state, not your actual deployment. Falls back to deleting the known GCP resources
# directly by name when there's no usable local state to work from -- see README's "Cleanup"
# section for why that gap exists here at all (unlike AWS/OCI, there's no single stack object to
# delete).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "== OmniGate on GKE -- guided teardown =="
echo

# Confirmed live: 7 unattached Persistent Disks (26GB, still billing) were found still sitting in
# the project well after both `terraform destroy` and this script's own manual fallback had
# already run, from every deploy cycle across this stack's testing. Root cause: the Postgres and
# OmniGate data volumes are Kubernetes PersistentVolumeClaims the Helm chart creates *inside* the
# cluster -- Terraform never creates or tracks them (helm_release just installs the chart; it has
# no visibility into what the chart's own templates provision at runtime), so neither
# `terraform destroy` (which only touches Terraform-managed resources) nor deleting the cluster
# directly cleans up the GCE disks backing them. Deleting the cluster out from under live PVCs
# orphans their disks rather than triggering the normal PVC-delete reclaim path.
#
# Fix: after the cluster's gone (either path below), sweep for any disk GKE's CSI driver labeled
# with this cluster's name and delete them directly -- this label survives independently of
# whether the cluster that created it still exists, so it works as a cleanup step regardless of
# which teardown path was taken.
cleanup_orphaned_disks() {
  local project="$1"
  echo
  echo "Checking for orphaned Persistent Disks (Postgres/OmniGate data volumes the Helm chart"
  echo "creates inside the cluster -- Terraform never tracks these, so nothing above this step"
  echo "would have deleted them)..."
  if ! command -v gcloud >/dev/null 2>&1; then
    echo "gcloud not available -- skipping. Check manually:" >&2
    echo "  gcloud compute disks list --project=$project --filter=\"labels.goog-k8s-cluster-name=omnigate-gke\"" >&2
    return 0
  fi
  local disks
  disks="$(gcloud compute disks list --project="$project" \
    --filter="labels.goog-k8s-cluster-name=omnigate-gke" \
    --format="value(name,zone.basename())" 2>/dev/null || true)"
  if [ -z "$disks" ]; then
    echo "None found."
    return 0
  fi
  echo "Found:"
  echo "$disks" | sed 's/^/  - /'
  while IFS="$(printf '\t')" read -r disk_name disk_zone; do
    [ -z "$disk_name" ] && continue
    echo "Deleting disk $disk_name (zone $disk_zone)..."
    gcloud compute disks delete "$disk_name" --zone="$disk_zone" --project="$project" --quiet || true
  done <<< "$disks"
}

# ---- Is there real, usable Terraform state right here? ---------------------------------------
# Checked before anything else: if this clone has no state, the whole terraform-prerequisites
# song and dance below (real terraform, ADC) is pointless -- skip straight to the manual fallback.
have_state=""
if [ -f terraform.tfstate ] && command -v terraform >/dev/null 2>&1 \
   && terraform version 2>&1 | grep -q '^Terraform v'; then
  state_list="$(terraform state list 2>/dev/null || true)"
  [ -n "$state_list" ] && have_state=1
fi

if [ -n "$have_state" ]; then
  echo "Found real Terraform state in this directory:"
  echo "$state_list" | sed 's/^/  - /'
  echo
  echo "Using terraform destroy."
  echo

  # Same terraform-isn't-really-installed and ADC gotchas as setup.sh -- see that file's comments
  # for the full "confirmed live" reasoning on both. Duplicated rather than shared: these are two
  # small, standalone scripts, not a package worth factoring a common lib out of.
  if ! terraform version 2>&1 | grep -q '^Terraform v'; then
    if [ "${CLOUD_SHELL:-}" = "true" ]; then
      echo "terraform isn't actually installed yet -- installing it now (Cloud Shell doesn't ship it by default)..."
      wget -q -O - https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
      echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
        | sudo tee /etc/apt/sources.list.d/hashicorp.list >/dev/null
      sudo apt-get update -qq && sudo apt-get install -y terraform -qq
    else
      echo "terraform isn't installed (or isn't real -- check 'terraform version' output above)." >&2
      echo "Install it: https://developer.hashicorp.com/terraform/install" >&2
      exit 1
    fi
  fi

  adc_default_path="$HOME/.config/gcloud/application_default_credentials.json"
  if { [ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] || [ ! -f "$GOOGLE_APPLICATION_CREDENTIALS" ]; } \
     && [ ! -f "$adc_default_path" ]; then
    echo
    echo "Terraform needs its own separate credentials (Application Default Credentials) --"
    echo "Cloud Shell doesn't set these up automatically the way it does for gcloud itself."
    adc_login_log="$(mktemp)"
    gcloud auth application-default login 2>&1 | tee "$adc_login_log"
    adc_path="$(sed -n 's/^Credentials saved to file: \[\(.*\)\]$/\1/p' "$adc_login_log")"
    rm -f "$adc_login_log"
    if [ -n "$adc_path" ] && [ -f "$adc_path" ]; then
      export GOOGLE_APPLICATION_CREDENTIALS="$adc_path"
    fi
  fi

  echo
  terraform destroy

  tf_project_id="$(sed -n 's/^gcp_project_id[[:space:]]*=[[:space:]]*"\(.*\)"$/\1/p' terraform.tfvars 2>/dev/null | head -1)"
  tf_project_id="${tf_project_id:-$(gcloud config get-value project 2>/dev/null || true)}"
  if [ -n "$tf_project_id" ]; then
    cleanup_orphaned_disks "$tf_project_id"
  fi
  exit 0
fi

# ---- No usable state -- manual fallback -------------------------------------------------------
echo "No usable local Terraform state found in this directory."
echo "(You may just be in the wrong ~/cloudshell_open/Docker-N clone -- see README's"
echo " \"Reconnecting to an existing deployment\" section before assuming it's really gone.)"
echo
read -rp "Fall back to deleting the known GCP resources directly by name instead? [y/N] " confirm
case "$confirm" in
  y|Y) ;;
  *) echo "Aborted."; exit 1 ;;
esac

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud is required for the manual fallback and isn't on PATH." >&2
  exit 1
fi

default_project="$(gcloud config get-value project 2>/dev/null || true)"
read -rp "GCP project ID${default_project:+ [$default_project]}: " project_id
project_id="${project_id:-$default_project}"
if [ -z "$project_id" ]; then
  echo "A GCP project ID is required." >&2
  exit 1
fi

default_region="us-central1"
read -rp "GCP region [$default_region]: " region
region="${region:-$default_region}"
zone="${region}-a" # setup.sh never prompts for gcp_zone_suffix, so this matches its default

echo
echo "About to delete, in project '$project_id':"
echo "  - GKE cluster omnigate-gke (zone $zone) and its node pool"
echo "  - Firewall rules omnigate-gke-allow-internal / -health-check / -client-ingress"
echo "  - Subnet omnigate-gke-nodes (region $region)"
echo "  - VPC network omnigate-gke"
echo "This does NOT touch the Artifact Registry image/repo -- see README's Cleanup section to"
echo "remove that separately, if you want it gone too."
echo
read -rp "Type 'destroy' to confirm: " confirm2
if [ "$confirm2" != "destroy" ]; then
  echo "Aborted."
  exit 1
fi
echo

# Deliberately not `set -e` for this block: several of these commonly fail with "not found" on a
# partially-torn-down deployment (a prior attempt already got partway through, or you're re-running
# this after an earlier failure), and that's fine -- keep going through the rest rather than dying
# on the first one. Each command's own failure is still visible; nothing is silenced.
set +e

echo "Deleting GKE cluster (this takes a few minutes)..."
gcloud container clusters delete omnigate-gke --zone "$zone" --project="$project_id" --quiet

echo "Deleting firewall rules..."
gcloud compute firewall-rules delete omnigate-gke-allow-internal omnigate-gke-allow-health-check omnigate-gke-allow-client-ingress --project="$project_id" --quiet

echo "Deleting subnet..."
gcloud compute networks subnets delete omnigate-gke-nodes --region="$region" --project="$project_id" --quiet

echo "Deleting VPC network..."
gcloud compute networks delete omnigate-gke --project="$project_id" --quiet

set -e

cleanup_orphaned_disks "$project_id"

echo
echo "== Done =="
echo "Verify nothing's left with: gcloud container clusters list --project=$project_id"
