// A single-node-pool AKS cluster, sized for a getting-started demo -- same posture as the
// AWS/OCI/GCP stacks (1 node by default, no autoscaling, no multi-nodepool split).
//
// Node architecture MUST match the published omnigate image's: it is arm64-only (no amd64
// manifest), the same as the AWS stack's Graviton (t4g.medium/AL2023_ARM_64_STANDARD) and GCP
// stack's Ampere (t2a-standard-2) pins -- both confirmed live that an amd64 node pool hits
// `ErrImagePull: no match for platform in manifest` on every pull. Azure's arm64 equivalent is
// the Ampere Altra "ps_v5" family (e.g. Standard_D2ps_v5) -- unlike AWS Graviton (broadly
// available in every region) or OCI's Always Free A1 (available in every OCI Always Free
// region), Ampere Altra VM availability on Azure is genuinely narrower and region-dependent as
// of this writing. This is a real, documented limitation of this stack (see README) rather than
// something worked around here -- pick a `location` where `az vm list-skus --size Standard_D2ps
// --location <region> -o table` actually returns results before deploying.
param location string
param nodeSubnetId string
param nodeVmSize string = 'Standard_D2ps_v5'
param nodeCount int = 1
param kubernetesVersion string = ''

resource aks 'Microsoft.ContainerService/managedClusters@2024-05-01' = {
  name: 'omnigate-aks'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    dnsPrefix: 'omnigate-aks'
    kubernetesVersion: empty(kubernetesVersion) ? null : kubernetesVersion
    agentPoolProfiles: [
      {
        name: 'nodepool1'
        count: nodeCount
        vmSize: nodeVmSize
        osType: 'Linux'
        // Confirmed on GCP/AWS's own published-image manifest -- arm64 nodes need arm64-capable
        // OS disk images too, which AKS's Ubuntu-based node image already supports for Ampere SKUs.
        mode: 'System'
        vnetSubnetID: nodeSubnetId
        type: 'VirtualMachineScaleSets'
      }
    ]
    networkProfile: {
      networkPlugin: 'azure'
      // Standard SKU (not "basic") is what gives an L4 TCP-passthrough LoadBalancer for
      // `type: LoadBalancer` Services -- required for the Ask app's SSE streaming responses, same
      // reason the AWS/OCI stacks avoid their clouds' classic/L7 LB defaults (confirmed live on
      // both: an L7 LB buffers SSE and hangs after the first event). AKS's Standard SKU has been
      // the default since Kubernetes 1.19, made explicit here rather than relied on implicitly.
      loadBalancerSku: 'standard'
      // Confirmed live: Azure CNI's default Service CIDR is also 10.0.0.0/16, which fully
      // overlaps network.bicep's VNet (10.0.0.0/16, node subnet 10.0.0.0/20) -- AKS cluster
      // creation failed outright with "ServiceCidrOverlapExistingSubnetsCidr" until these were
      // pinned to a range outside the VNet's address space.
      serviceCidr: '10.1.0.0/16'
      dnsServiceIP: '10.1.0.10'
    }
  }
}

output clusterName string = aks.name
output clusterId string = aks.id
output principalId string = aks.identity.principalId
