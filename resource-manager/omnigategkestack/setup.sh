#!/usr/bin/env bash
# Collapses the "gcloud config set project -> enable APIs -> hand-edit terraform.tfvars ->
# terraform init -> terraform apply" walkthrough into one script, so GCP's deploy path is closer
# in step-count to AWS's "Launch Stack, fill 2 fields" / OCI's "Launch Stack, fill a form" --
# still a terminal, not a native GCP form (see README's "Why no schema.yaml" section for why that
# gap exists at all), but down to "run this script" instead of five separate manual steps.
#
# Safe to re-run: re-prompts for anything not already set in terraform.tfvars, and `terraform
# apply` on an existing deployment is just a normal (idempotent) update, same as running it by
# hand a second time would be.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "== OmniGate on GKE -- guided setup =="
echo

# ---- 1. Tools --------------------------------------------------------------------------------
missing=()
for tool in gcloud terraform curl python3; do
  command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "Missing required tool(s): ${missing[*]}" >&2
  echo "Cloud Shell has all of these preinstalled -- if you're running this locally instead, install them first." >&2
  exit 1
fi

# Same keg-only-Homebrew-JDK gotcha as password-hash.tf -- checked here too so it's caught before
# terraform apply gets 10+ minutes into cluster creation, not after.
if ! java -version >/dev/null 2>&1; then
  found=""
  for candidate in /opt/homebrew/opt/openjdk/bin /usr/local/opt/openjdk/bin; do
    if [ -x "$candidate/java" ]; then
      export PATH="$candidate:$PATH"
      found=1
      break
    fi
  done
  if [ -z "$found" ]; then
    echo "No working java found (needed for password-hash.tf)." >&2
    echo "Cloud Shell has this preinstalled. Locally on macOS: brew install openjdk." >&2
    exit 1
  fi
fi

# ---- 2. Project -------------------------------------------------------------------------------
default_project="$(gcloud config get-value project 2>/dev/null || true)"
read -rp "GCP project ID${default_project:+ [$default_project]}: " project_id
project_id="${project_id:-$default_project}"
if [ -z "$project_id" ]; then
  echo "A GCP project ID is required." >&2
  exit 1
fi
gcloud config set project "$project_id" >/dev/null

echo "Checking billing is linked to $project_id..."
# Confirmed live: swallowing stderr here (an earlier version used 2>/dev/null) hides the real
# cause of any gcloud failure -- a permissions hiccup, an API not enabled yet, a transient auth
# issue -- and reports the generic "billing is not linked" message even when billing genuinely
# IS linked. Capture stderr and only hard-fail on a confirmed "False", not on a command error;
# terraform apply will fail with a clear, real error if billing truly isn't linked.
billing_output="$(gcloud billing projects describe "$project_id" --format="value(billingEnabled)" 2>&1)"
billing_rc=$?
if [ $billing_rc -ne 0 ]; then
  echo "Warning: couldn't verify billing status -- 'gcloud billing projects describe' failed:" >&2
  echo "  $billing_output" >&2
  echo "Continuing anyway; terraform apply will fail clearly if billing genuinely isn't linked." >&2
elif [ "$billing_output" != "True" ]; then
  echo "Billing is not linked to $project_id -- link a billing account before continuing (Console: Billing > Link a billing account)." >&2
  exit 1
fi

echo "Enabling required APIs (container, compute, artifactregistry)..."
gcloud services enable container.googleapis.com compute.googleapis.com artifactregistry.googleapis.com \
  --project "$project_id" >/dev/null

default_region="us-central1"
read -rp "GCP region [$default_region]: " region
region="${region:-$default_region}"

# ---- 3. Application config ----------------------------------------------------------------
default_username="demo"
read -rp "Ask-app login username [$default_username]: " app_username
app_username="${app_username:-$default_username}"

while true; do
  read -rsp "Ask-app login password: " app_password
  echo
  if [ -n "$app_password" ]; then
    break
  fi
  echo "Password can't be empty -- refusing to deploy the well-known demo/demo login on a public LoadBalancer." >&2
done

while true; do
  read -rsp "Anthropic API key (from console.anthropic.com): " llm_api_key
  echo
  if [ -n "$llm_api_key" ]; then
    break
  fi
  echo "Required -- the gateway deploys fine without one but can't answer any question." >&2
done

# ---- 4. Write terraform.tfvars -------------------------------------------------------------
cat > terraform.tfvars <<EOF
gcp_project_id = "$project_id"
gcp_region     = "$region"

omnigate_app_username = "$app_username"
omnigate_app_password = "$app_password"
omnigate_llm_api_key  = "$llm_api_key"
EOF
echo
echo "Wrote terraform.tfvars (gitignored, never sent anywhere else)."

# ---- 5. Deploy -----------------------------------------------------------------------------
echo
echo "Running terraform init && terraform apply..."
terraform init
terraform apply

echo
echo "== Done =="
echo "Run this to get kubectl access:"
terraform output -raw kubeconfig_command
echo
echo

# Confirmed live: on a local (non-Cloud-Shell) macOS Homebrew gcloud install, kubectl fails here
# with "executable gke-gcloud-auth-plugin not found" even after `gcloud components install
# gke-gcloud-auth-plugin` -- the binary lands in a directory Homebrew's cask doesn't add to PATH.
# Cloud Shell already has this plugin on PATH, so this only bites the local-CLI path.
if ! command -v gke-gcloud-auth-plugin >/dev/null 2>&1; then
  for candidate in /opt/homebrew/share/google-cloud-sdk/bin /usr/local/share/google-cloud-sdk/bin; do
    if [ -x "$candidate/gke-gcloud-auth-plugin" ]; then
      echo "Note: kubectl needs gke-gcloud-auth-plugin, which isn't on PATH yet. Add it with:"
      echo "  echo 'export PATH=\"$candidate:\$PATH\"' >> ~/.zshrc && source ~/.zshrc"
      echo
      break
    fi
  done
fi

echo "Then, once the LoadBalancer has a public IP:"
echo "  kubectl get svc omnigate-omnigate-http"
echo "Open http://<that-ip>:8080/ and log in with the username/password you just set."
