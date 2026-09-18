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
for tool in gcloud curl python3; do
  command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "Missing required tool(s): ${missing[*]}" >&2
  echo "Cloud Shell has all of these preinstalled -- if you're running this locally instead, install them first." >&2
  exit 1
fi

# terraform gets its own check, not the command -v loop above: confirmed live, Cloud Shell can
# have a `terraform` on PATH that isn't actually installed -- running it just prints Debian's
# "here's how to apt install this" advisory and (confirmed live) exits 0, so `command -v` finds
# it, `set -e` never trips, and every terraform command downstream silently no-ops while this
# script sails on to a misleading "== Done ==". Check the real output of `terraform version`
# instead of just PATH presence, and if it's the advisory stub, install it ourselves in Cloud
# Shell using the exact commands Cloud Shell's own advisory prints -- CLOUD_SHELL=true is how
# Cloud Shell identifies itself in its own environment.
if ! terraform version 2>&1 | grep -q '^Terraform v'; then
  if [ "${CLOUD_SHELL:-}" = "true" ]; then
    echo "terraform isn't actually installed yet -- installing it now (Cloud Shell doesn't ship it by default)..."
    wget -q -O - https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
      | sudo tee /etc/apt/sources.list.d/hashicorp.list >/dev/null
    sudo apt-get update -qq && sudo apt-get install -y terraform -qq
    if ! terraform version 2>&1 | grep -q '^Terraform v'; then
      echo "terraform install didn't take -- install it manually (see https://developer.hashicorp.com/terraform/install) and re-run this script." >&2
      exit 1
    fi
  else
    echo "terraform isn't installed (or isn't real -- check 'terraform version' output above)." >&2
    echo "Install it: https://developer.hashicorp.com/terraform/install" >&2
    exit 1
  fi
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

# Confirmed live: even inside Cloud Shell, which auto-authenticates the signed-in Google user,
# gcloud can end up with no active account selected (seen after cloning into a second/third
# Docker-N workspace in the same session) -- every gcloud call below then fails with "You do not
# currently have an active account selected", which is a confusing place to first discover that.
# Catch it here with a direct fix instead.
if [ -z "$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null)" ]; then
  echo "No active gcloud account. Run 'gcloud auth login', then re-run this script." >&2
  exit 1
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
# Confirmed live, twice: an earlier version swallowed stderr (2>/dev/null), hiding the real cause
# of any gcloud failure and reporting the generic "billing is not linked" even when billing
# genuinely was linked. The fix-after-that still silently killed the whole script on that same
# failure -- `set -e` (top of this file) triggers on a failing command substitution assignment
# (billing_output="$(cmd)") the instant it fails, before the next line ever runs, so the
# error-surfacing code below never got a chance to execute. `set +e`/`set -e` around just this
# one command is what actually lets us capture the failure and report it instead of dying silently.
set +e
billing_output="$(gcloud billing projects describe "$project_id" --format="value(billingEnabled)" 2>&1)"
billing_rc=$?
set -e
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

# Confirmed live: Terraform's google provider needs Application Default Credentials (ADC) --
# a separate credential store from the regular `gcloud auth login` session that gcloud itself
# uses (and which every gcloud call above this point already relied on successfully). Unlike a
# real Compute Engine VM, Cloud Shell does NOT provision ADC automatically via its metadata
# server -- without this, the very first resource terraform tries to create fails with
# "oauth2/google: invalid token JSON from metadata: EOF". Doesn't affect gcloud at all, only
# Terraform (and anything else using ADC directly), which is why every gcloud step above this
# point can succeed while this one still needs its own separate login.
if ! gcloud auth application-default print-access-token >/dev/null 2>&1; then
  echo
  echo "Terraform needs its own separate credentials (Application Default Credentials) --"
  echo "Cloud Shell doesn't set these up automatically the way it does for gcloud itself."
  gcloud auth application-default login
fi

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
