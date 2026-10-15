#!/usr/bin/env bash
# Guided teardown. Much simpler than the GCP stack's destroy.sh: an ARM deployment -- like a
# CloudFormation stack or an OCI Resource Manager stack -- tracks everything it created as one
# resource group, so there's no local Terraform state to reconnect to and no per-resource manual
# fallback list to keep in sync. Deleting the resource group is the whole story.
set -euo pipefail

if [ -z "${1:-}" ]; then
  read -rp "Resource group name to delete: " resource_group
else
  resource_group="$1"
fi
if [ -z "$resource_group" ]; then
  echo "A resource group name is required." >&2
  exit 1
fi

if ! command -v az >/dev/null 2>&1; then
  echo "The Azure CLI (az) is required and isn't on PATH: https://learn.microsoft.com/cli/azure/install-azure-cli" >&2
  exit 1
fi

if ! az group show --name "$resource_group" >/dev/null 2>&1; then
  echo "Resource group '$resource_group' doesn't exist (or you're not logged into the right subscription -- check 'az account show')." >&2
  exit 1
fi

echo "About to delete resource group '$resource_group' and everything in it:"
az resource list --resource-group "$resource_group" --query "[].{Name:name, Type:type}" -o table
echo

read -rp "Type 'destroy' to confirm: " confirm
if [ "$confirm" != "destroy" ]; then
  echo "Aborted."
  exit 1
fi

echo
az group delete --name "$resource_group" --yes --no-wait
echo "Deletion started (runs in the background). Confirm with: az group exists --name $resource_group"
