// ─── Codelyst — shared resources (deploy once) ────────────────────────────────
// One container registry serves both environments, so the exact image tested
// in staging is the image promoted to prod. Images contain code only, no PHI.

targetScope = 'resourceGroup'

@description('Azure region.')
param location string = resourceGroup().location

@description('Globally unique registry name (alphanumeric, 5-50 chars).')
param acrName string = 'acrcodelyst${take(uniqueString(resourceGroup().id), 8)}'

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: { name: 'Standard' }
  properties: {
    adminUserEnabled: false // pulls use managed identity only
    publicNetworkAccess: 'Enabled'
    policies: {
      retentionPolicy: { status: 'disabled' } // retention needs Premium
    }
  }
  tags: { app: 'codelyst', environment: 'shared' }
}

output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
