// omnigateaksstack -- Azure Bicep/ARM stack for OmniGate (NL2SQL gateway) + a seeded Postgres
// demo backend on a new AKS cluster. Resource-group scoped, deployed via the Portal's "Deploy to
// Azure" button (driven by createUiDefinition.json, this template's analog of the OCI stack's
// schema.yaml) or the `az deployment group create` CLI, same two paths as the AWS/OCI stacks.
//
// See README.md for the full deploy story and this stack's node-architecture limitation (Ampere
// Altra arm64 VM availability is narrower on Azure than AWS Graviton or OCI's Always Free A1).

@description('Azure region to deploy into. Must have Ampere Altra (Dps/Eps v5-family) VM availability -- see README.')
param location string = resourceGroup().location

@description('Ask-app login username (not an Azure/AAD account).')
param appUsername string = 'demo'

@description('Ask-app login password, plain text -- hashed automatically during deployment using the deployed image\'s own PasswordHash utility. Required so this deployment does not ship the repo\'s well-known demo/demo login on a public LoadBalancer.')
@secure()
param appPassword string

@description('Login name for the admin console. The admin console, admin API and /mcp endpoint require this login, so they are not open to the internet.')
param adminUsername string = 'admin'

@description('Admin console password, plain text. Leave blank to use the Ask-app password for the admin login as well; set a different one if you will share the Ask-app login with other people.')
@secure()
param adminPassword string = ''

@description('Optional. Comma-separated CIDR ranges (e.g. 203.0.113.7/32) allowed to reach OmniGate. Blank = open to the internet, fine for a first try-out; set it once real data is connected, because the agent endpoint (/mcp/agent) answers questions without a login using your Anthropic key.')
param allowedClientCidrs string = ''

@description('Anthropic API key from console.anthropic.com. Required -- the Ask app cannot answer any question without it.')
@secure()
param llmApiKey string

@description('Anthropic model used for NL2SQL.')
@allowed([
  'claude-sonnet-5'
  'claude-opus-5'
  'claude-haiku-4-5-20251001'
])
param llmModel string = 'claude-sonnet-5'

@description('Also expose the Oracle/Postgres/MySQL/gRPC wire-protocol ports via a second public LoadBalancer. Off by default.')
param exposeWireProtocols bool = false

@description('AKS node count.')
@minValue(1)
@maxValue(4)
param nodeCount int = 1

@description('AKS node VM size. Must be an arm64 (Ampere Altra) SKU to match the arm64-only omnigate image -- see README\'s node-architecture note.')
param nodeVmSize string = 'Standard_D2ps_v5'

@description('Postgres PVC size (GB).')
@minValue(1)
@maxValue(100)
param postgresStorageGb int = 5

@description('OmniGate ConfigStore PVC size (GB) -- holds admin-set config (e.g. an API key entered live in the UI) so it survives pod restarts.')
@minValue(1)
@maxValue(20)
param omnigateDataStorageGb int = 2

@description('Container image repository (advanced). Defaults to the publisher\'s GCP Artifact Registry mirror -- confirmed live that OCI\'s own OCIR registry rejects external pulls from a Free Tier tenancy (403 "Free tier account is not supported"), so pulling the AWS stack\'s documented OCIR path directly does not actually work cross-cloud; the GCP mirror does. Deployers should not need to build or push anything themselves.')
param imageRepository string = 'us-docker.pkg.dev/thinkingsense/omnigate/omnigate'

@description('Image tag (advanced). Pinned to a specific free-edition release rather than "latest" -- confirmed live that "latest" had silently stopped tracking new app releases (frozen at v0.6.0\'s content for two releases, since v0.7.0/v0.8.0 were only ever published to a different registry this stack never pulled from), so a moving-target default was not actually keeping deployers current, just non-reproducible. The AWS/OCI/GCP stacks made the identical fix the same way -- bump this deliberately when a newer free-edition image is built and pushed, do not go back to "latest".')
param imageTag string = 'v0.10.4'

@description('Tarball URL containing this stack\'s Helm chart (advanced). Pinned to this release\'s own tag so a deploy from this exact "Deploy to Azure" button/azuredeploy.json can never drift from a newer chart on main -- bump this alongside the version tag on every release, see README\'s "Publishing a release".')
param chartSourceUrl string = 'https://github.com/thinkingsense-ai/Docker/archive/refs/tags/aks-stack-v1.0.5.tar.gz'

module network 'modules/network.bicep' = {
  name: 'omnigate-network'
  params: {
    location: location
  }
}

module aks 'modules/aks.bicep' = {
  name: 'omnigate-aks-cluster'
  params: {
    location: location
    nodeSubnetId: network.outputs.nodeSubnetId
    nodeVmSize: nodeVmSize
    nodeCount: nodeCount
  }
}

module helmInstall 'modules/deploymentScript.bicep' = {
  name: 'omnigate-helm-install'
  params: {
    location: location
    clusterName: aks.outputs.clusterName
    imageRepository: imageRepository
    imageTag: imageTag
    llmModel: llmModel
    exposeWireProtocols: exposeWireProtocols
    dataVolumeGb: omnigateDataStorageGb
    postgresStorageGb: postgresStorageGb
    appUsername: appUsername
    appPassword: appPassword
    adminUsername: adminUsername
    adminPassword: empty(adminPassword) ? appPassword : adminPassword
    allowedClientCidrs: allowedClientCidrs
    llmApiKey: llmApiKey
    chartSourceUrl: chartSourceUrl
  }
}

output clusterName string = aks.outputs.clusterName
output kubeconfigCommand string = 'az aks get-credentials --resource-group ${resourceGroup().name} --name ${aks.outputs.clusterName}'
output askAppUrl string = helmInstall.outputs.askAppUrl
