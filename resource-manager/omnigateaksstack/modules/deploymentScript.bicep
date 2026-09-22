// Azure has no native "run Helm as part of an ARM deployment" resource, the same gap AWS (no
// CloudFormation Helm resource type) and OCI (Terraform *does* have a native helm_release
// provider, so OCI doesn't need this module at all) each hit. AWS's answer is a Lambda-backed
// custom resource requiring its own ECR repo + CodeBuild bootstrap just to get the Lambda's own
// container image built and pushed. Azure's `Microsoft.Resources/deploymentScripts` (kind:
// AzureCLI) is the more direct mirror of that same imperative-script idea, but simpler: it runs
// in a managed container Azure already provides, no image build/push step of our own required.
//
// This resource needs its own identity with permission to fetch AKS credentials -- unlike a
// Lambda execution role (IAM) or ORM's job runner (OCI CLI + tenancy-scoped policy), ARM
// deploymentScripts get no implicit access to sibling resources in the same template.
param location string
param clusterName string
param imageRepository string
param imageTag string
param llmModel string
param exposeWireProtocols bool
param dataVolumeGb int
param postgresStorageGb int
param appUsername string
@secure()
param appPassword string
@secure()
param llmApiKey string
// The Helm chart (helm/omnigate/) ships in this same repo, one directory up from this stack's
// Bicep. It has no independent version -- it travels with the aks-stack-vX.Y.Z release tag, same
// as the OCI stack's chart travels inside its own release zip (see README's "Publishing a
// release"). Default points at this repo's main branch tarball for local/dev testing; a tagged
// release should override this to the matching aks-stack-vX.Y.Z tag's tarball so a deploy from
// an old "Deploy to Azure" button link can't drift from a newer chart on main.
param chartSourceUrl string = 'https://github.com/thinkingsense-ai/Docker/archive/refs/heads/main.tar.gz'

resource deployIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'omnigate-aks-deploy-identity'
  location: location
}

// `scope` on a roleAssignments resource needs an actual resource symbol (or a module/tenant
// scope), not a resourceId() string -- `az bicep build` rejects the string form with BCP036.
// Declaring the cluster as `existing` here (rather than passing its full resource through as a
// module output) is what lets `scope:` bind to it.
resource aksCluster 'Microsoft.ContainerService/managedClusters@2024-05-01' existing = {
  name: clusterName
}

resource aksClusterAdminRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, clusterName, deployIdentity.id, 'aks-cluster-admin')
  scope: aksCluster
  properties: {
    // "Azure Kubernetes Service Cluster Admin Role" -- lets this identity pull an admin
    // kubeconfig via `az aks get-credentials`, the direct analog of the OCI CLI's
    // `oci ce cluster generate-token` exec plugin the OKE stack's helm/kubernetes providers use.
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '0ab0b1a8-8aac-4efd-b8c2-3ee1fb270be8')
    principalId: deployIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource helmInstall 'Microsoft.Resources/deploymentScripts@2023-08-01' = {
  name: 'omnigate-helm-install'
  location: location
  kind: 'AzureCLI'
  dependsOn: [
    aksClusterAdminRole
  ]
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${deployIdentity.id}': {}
    }
  }
  properties: {
    azCliVersion: '2.63.0'
    retentionInterval: 'P1D'
    timeout: 'PT20M'
    cleanupPreference: 'OnSuccess'
    environmentVariables: [
      { name: 'RESOURCE_GROUP', value: resourceGroup().name }
      { name: 'CLUSTER_NAME', value: clusterName }
      { name: 'IMAGE_REPOSITORY', value: imageRepository }
      { name: 'IMAGE_TAG', value: imageTag }
      { name: 'LLM_MODEL', value: llmModel }
      { name: 'EXPOSE_WIRE_PROTOCOLS', value: string(exposeWireProtocols) }
      { name: 'DATA_VOLUME_GB', value: string(dataVolumeGb) }
      { name: 'POSTGRES_STORAGE_GB', value: string(postgresStorageGb) }
      { name: 'APP_USERNAME', value: appUsername }
      { name: 'CHART_SOURCE_URL', value: chartSourceUrl }
      { name: 'APP_PASSWORD', secureValue: appPassword }
      { name: 'LLM_API_KEY', secureValue: llmApiKey }
    ]
    scriptContent: '''
      set -euo pipefail

      # Confirmed live: the AzureCLI deploymentScripts container is Alpine-based (apk), not the
      # Azure Linux (tdnf) image assumed here originally -- ships with neither curl nor a JRE nor
      # openssl by default. The very first `curl` call in an earlier version of this script failed
      # outright with "curl: command not found"; after adding curl+JRE, Helm's own install script
      # then failed with "In order to verify checksum, openssl must first be installed." Install
      # all three together, before anything else needs them. Falling back through tdnf/apt
      # defensively in case this base image ever changes, same spirit as the GCP stack's
      # Homebrew-keg-only fallback in password-hash.tf's build.
      echo "== Installing curl, openssl, and a JRE =="
      if command -v apk >/dev/null 2>&1; then
        apk add --no-cache curl openssl ca-certificates openjdk17-jre-headless
      elif command -v tdnf >/dev/null 2>&1; then
        tdnf install -y curl openssl ca-certificates || true
        tdnf install -y msopenjdk-17 || tdnf install -y java-17-openjdk-headless
      elif command -v apt-get >/dev/null 2>&1; then
        apt-get update -qq
        apt-get install -y -qq curl openssl ca-certificates
        apt-get install -y -qq default-jre-headless
      else
        echo "No supported package manager found for installing curl/openssl/a JRE" >&2
        exit 1
      fi
      command -v curl >/dev/null 2>&1 || { echo "curl still not available after install attempt" >&2; exit 1; }
      command -v openssl >/dev/null 2>&1 || { echo "openssl still not available after install attempt" >&2; exit 1; }
      command -v java >/dev/null 2>&1 || { echo "java still not available after install attempt" >&2; exit 1; }

      echo "== Installing Helm =="
      curl -fsSL -o /tmp/get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3
      chmod +x /tmp/get_helm.sh
      /tmp/get_helm.sh

      echo "== Fetching AKS credentials =="
      az aks get-credentials --resource-group "$RESOURCE_GROUP" --name "$CLUSTER_NAME" --overwrite-existing --admin

      echo "== Fetching the Helm chart =="
      curl -fsSL -o /tmp/chart.tar.gz "$CHART_SOURCE_URL"
      mkdir -p /tmp/chart
      tar -xzf /tmp/chart.tar.gz -C /tmp/chart --strip-components=1
      CHART_DIR=$(find /tmp/chart -type d -path '*omnigateaksstack/helm/omnigate' | head -1)
      if [ -z "$CHART_DIR" ]; then
        echo "Could not locate helm/omnigate inside $CHART_SOURCE_URL" >&2
        exit 1
      fi

      # Computes OMNIGATE_APP_USERS server-side, the same algorithm as the AWS Lambda's
      # resolve_jar_url()/compute_password_hash() and OCI's password-hash.tf `data "external"`:
      # resolve the exact release jar matching $IMAGE_TAG (a literal version tag, or GitHub
      # /releases/latest if the tag is the literal string "latest" -- the default OCI/ACR-style
      # docker tag, not itself a GitHub release name), download it, and run its own bundled
      # PasswordHash utility so the hash format always matches whatever image is actually
      # deployed, rather than a separately-maintained reimplementation of the hash algorithm.
      echo "== Computing app login hash =="
      if [ "$IMAGE_TAG" = "latest" ]; then
        JAR_URL=$(python3 -c "
import json, urllib.request
with urllib.request.urlopen('https://api.github.com/repos/thinkingsense-ai/Docker/releases/latest', timeout=15) as r:
    release = json.load(r)
for asset in release.get('assets', []):
    if asset['name'] == 'omnigate.jar':
        print(asset['browser_download_url'])
        break
else:
    raise SystemExit('omnigate.jar asset not found on latest GitHub release')
")
      else
        JAR_URL="https://github.com/thinkingsense-ai/Docker/releases/download/${IMAGE_TAG}/omnigate.jar"
      fi
      curl -fsSL -o /tmp/omnigate-hash-tool.jar "$JAR_URL"
      APP_HASH=$(java -cp /tmp/omnigate-hash-tool.jar com.omnigate.http.auth.PasswordHash "$APP_PASSWORD")
      rm -f /tmp/omnigate-hash-tool.jar
      # Confirmed live: AppAuthConfig.parse (com.omnigate.http.ask.auth.AppAuthConfig) requires
      # exactly 5 colon-separated fields (username:salt:hash:roles:attrs) and silently SKIPS any
      # entry that doesn't split into 5 -- omitting the trailing "::" for the empty roles/
      # attributes fields left the user list empty and login silently disabled ("web UI
      # business-user login disabled -- set OMNIGATE_APP_USERS"), no error, no crash, just an
      # unusable login. The trailing "::" is not optional cosmetic formatting.
      APP_USERS="${APP_USERNAME}:${APP_HASH}::"

      echo "== Installing the omnigate Helm release =="
      helm upgrade --install omnigate "$CHART_DIR" \
        --set image.repository="$IMAGE_REPOSITORY" \
        --set image.tag="$IMAGE_TAG" \
        --set omnigate.llmModel="$LLM_MODEL" \
        --set omnigate.exposeWireProtocols="$EXPOSE_WIRE_PROTOCOLS" \
        --set omnigate.dataVolumeSize="${DATA_VOLUME_GB}Gi" \
        --set postgres.storageSize="${POSTGRES_STORAGE_GB}Gi" \
        --set-string omnigate.appUsers="$APP_USERS" \
        --set-string omnigate.llmApiKey="$LLM_API_KEY" \
        --timeout 10m0s \
        --wait

      # Redact secrets from this script's own process environment before it exits -- deploymentScripts
      # persists stdout/stderr into the resource's execution logs, so anything echoed (deliberately
      # or by a stray `set -x`) would otherwise leak. Mirrors the redaction discipline AWS's
      # handler.py added after a real bug there leaked the *previous* password on every Update
      # event (it originally redacted only the current ResourceProperties, not the old ones).
      unset APP_PASSWORD LLM_API_KEY APP_USERS APP_HASH

      echo "== Waiting for the LoadBalancer IP =="
      HTTP_IP=""
      for i in $(seq 1 30); do
        HTTP_IP=$(kubectl get svc omnigate-omnigate-http -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)
        [ -n "$HTTP_IP" ] && break
        sleep 10
      done

      if [ -n "$HTTP_IP" ]; then
        ASK_APP_URL="http://${HTTP_IP}:8080/"
      else
        ASK_APP_URL="pending -- run: kubectl get svc omnigate-omnigate-http"
      fi
      # Confirmed live: hand-escaped quotes inside a Bicep triple-quoted string
      # (`\\"..\\"`) do not round-trip the way a plain bash script would expect -- the resulting
      # scriptoutputs.json was malformed and ARM rejected the whole deployment with
      # "DeploymentScriptInvalidOutputs", even though the Helm install itself had already
      # succeeded. Building the JSON with python3's json.dumps (already a dependency via the
      # jar-resolution step above) sidesteps shell/Bicep escaping entirely.
      ASK_APP_URL="$ASK_APP_URL" python3 -c "
import json, os
json.dump({'askAppUrl': os.environ['ASK_APP_URL']}, open(os.environ['AZ_SCRIPTS_OUTPUT_PATH'], 'w'))
"
    '''
  }
}

output askAppUrl string = helmInstall.properties.outputs.askAppUrl
