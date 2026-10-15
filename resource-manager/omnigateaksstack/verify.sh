#!/usr/bin/env bash
# Guided verification, mirroring the exact commands run by hand during this stack's own
# clean-room validation: fetch cluster credentials, check the pods and the LoadBalancer, then
# actually curl the Ask app to confirm it's serving -- not just "kubectl says Running", which
# doesn't by itself prove the app answered an HTTP request (confirmed live: this distinction
# mattered once, when a deploymentScripts-side bug reported success while the app's own login was
# silently broken -- see README's "Clean-room validated" section).
set -euo pipefail

if [ -z "${1:-}" ]; then
  read -rp "Resource group name: " resource_group
else
  resource_group="$1"
fi
if [ -z "$resource_group" ]; then
  echo "A resource group name is required." >&2
  exit 1
fi

cluster_name="${2:-omnigate-aks}"

if ! command -v az >/dev/null 2>&1; then
  echo "The Azure CLI (az) is required and isn't on PATH: https://learn.microsoft.com/cli/azure/install-azure-cli" >&2
  exit 1
fi
if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl isn't on PATH -- installing via 'az aks install-cli'..."
  az aks install-cli
fi

echo "== Fetching credentials for $cluster_name (resource group $resource_group) =="
az aks get-credentials --resource-group "$resource_group" --name "$cluster_name" --overwrite-existing

echo
echo "== Pods =="
kubectl get pods

echo
echo "== Services =="
kubectl get svc omnigate-omnigate-http omnigate-postgres

echo
echo "== Waiting for the LoadBalancer's public IP (up to 5 minutes) =="
http_ip=""
for _ in $(seq 1 30); do
  http_ip="$(kubectl get svc omnigate-omnigate-http -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
  [ -n "$http_ip" ] && break
  sleep 10
done

if [ -z "$http_ip" ]; then
  echo "No public IP yet -- check 'kubectl get svc omnigate-omnigate-http' again in a minute." >&2
  exit 1
fi

ask_app_url="http://${http_ip}:8080/"
echo
echo "== Checking the Ask app actually responds =="
http_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$ask_app_url" || echo "000")"
if [ "$http_code" = "200" ]; then
  echo "$ask_app_url -> HTTP $http_code (serving)"
else
  echo "$ask_app_url -> HTTP $http_code (not yet serving -- pod may still be starting; check 'kubectl logs deploy/omnigate-omnigate')" >&2
  exit 1
fi

echo
echo "== Done =="
echo "Ask app: $ask_app_url"
echo "Log in with the username/password you set during deploy."
