// Minimal single-VNet network: one subnet for the AKS node pool. Simplest thing that works for a
// getting-started / one-click demo stack -- same "simplest thing that works" posture as the
// AWS/OCI/GCP stacks (no NAT gateway, no private cluster, no network hardening pass). The Ask
// app itself requires a login and the wire ports are opt-in via exposeWireProtocols, same as the
// other three stacks.

param location string
param vnetAddressPrefix string = '10.0.0.0/16'
param nodeSubnetPrefix string = '10.0.0.0/20'

resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: 'omnigate-aks-vnet'
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [vnetAddressPrefix]
    }
    subnets: [
      {
        name: 'omnigate-aks-nodes'
        properties: {
          addressPrefix: nodeSubnetPrefix
        }
      }
    ]
  }
}

output vnetId string = vnet.id
output nodeSubnetId string = vnet.properties.subnets[0].id
