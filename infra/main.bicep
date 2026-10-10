// ─── Codelyst — one environment (staging or prod) ─────────────────────────────
// Deploy into its own resource group: rg-codelyst-staging / rg-codelyst-prod.
//
//   Internet ──TLS──▶ web (nginx, external ingress)
//                        │ /api  (TLS, inside the VNet)
//                        ▼
//                     api (FastAPI, internal ingress only)
//                        │                 │
//              private endpoint     VNet-injected
//                        ▼                 ▼
//                    Key Vault       PostgreSQL Flexible Server
//
// Nothing that holds data (database, vault, storage) has a public endpoint,
// except the optional SFTP account, which is locked to an IP allowlist.

targetScope = 'resourceGroup'

// ── Parameters ───────────────────────────────────────────────────────────────

@allowed(['staging', 'prod'])
param environmentName string

param location string = resourceGroup().location

@description('Shared registry name and its resource group (from shared.bicep).')
param acrName string
param acrResourceGroup string

@description('Full image references, e.g. acrxyz.azurecr.io/codelyst-api:<git-sha>.')
param backendImage string
param frontendImage string

@description('VNet range. Use a different /16 per environment.')
param vnetAddressPrefix string

param postgresSkuName string = 'Standard_B1ms'
@allowed(['Burstable', 'GeneralPurpose', 'MemoryOptimized'])
param postgresSkuTier string = 'Burstable'
param postgresStorageGb int = 32
@minValue(7)
@maxValue(35)
param postgresBackupRetentionDays int = 7
param postgresGeoRedundantBackup bool = false

@description('0 lets the app scale to zero (cold starts). Use 1+ where people depend on it.')
param minReplicas int = 0
param maxReplicas int = 3

@description('Every user must enroll in TOTP MFA before using the app.')
param requireMfa bool = true

@description('Return CPT codes and descriptors. Leave false until the AMA license is signed.')
param cptLicensed bool = false

param logRetentionDays int = 90

@description('Purge protection cannot be turned off once on. Required for prod.')
param keyVaultPurgeProtection bool = true

@description('SFTP drop for facility exports. Billed hourly while enabled (~$0.30/hr), so leave off until a facility needs it.')
param enableSftpStorage bool = false
@description('Public IPs (CIDR) allowed to reach SFTP, e.g. a facility office.')
param sftpAllowedIps array = []

// Secrets. Pass these on the FIRST deploy. On later deploys leave them empty
// and the values already in Key Vault / on the server are kept.
@secure()
param postgresAdminPassword string = ''
@secure()
param anthropicApiKey string = ''
@secure()
param jwtSecretKey string = ''
@secure()
param jwtRefreshSecretKey string = ''
@secure()
@description('Fernet key that encrypts MFA secrets at rest. Changing it invalidates every MFA enrollment.')
param encryptionKey string = ''

// ── Naming and tags ──────────────────────────────────────────────────────────

var suffix = take(uniqueString(resourceGroup().id), 8)
var isProd = environmentName == 'prod'

var names = {
  logs: 'log-codelyst-${environmentName}'
  identity: 'id-codelyst-${environmentName}'
  vnet: 'vnet-codelyst-${environmentName}'
  keyVault: 'kvclst${environmentName}${suffix}'
  postgres: 'psql-codelyst-${environmentName}-${suffix}'
  caEnv: 'cae-codelyst-${environmentName}'
  api: 'ca-codelyst-api-${environmentName}'
  web: 'ca-codelyst-web-${environmentName}'
  storage: 'stclst${environmentName}${suffix}'
}

var tags = {
  app: 'codelyst'
  environment: environmentName
  dataClassification: isProd ? 'phi' : 'synthetic-only'
  owner: 'DreamLogic Solutions'
}

var postgresAdminLogin = 'codelystadmin'
var databaseName = 'codelyst'

// ── Logging ──────────────────────────────────────────────────────────────────

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: names.logs
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: logRetentionDays
  }
}

// ── Identity ─────────────────────────────────────────────────────────────────

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: names.identity
  location: location
  tags: tags
}

module acrPull 'modules/acr-pull.bicep' = {
  name: 'acr-pull-${environmentName}'
  scope: resourceGroup(acrResourceGroup)
  params: {
    acrName: acrName
    principalId: identity.properties.principalId
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
  scope: resourceGroup(acrResourceGroup)
}

// ── Network ──────────────────────────────────────────────────────────────────
// /16 split: apps /23, postgres /24, private endpoints /24.

var subnetApps = cidrSubnet(vnetAddressPrefix, 23, 0)
var subnetPostgres = cidrSubnet(vnetAddressPrefix, 24, 2)
var subnetEndpoints = cidrSubnet(vnetAddressPrefix, 24, 3)

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: names.vnet
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: [vnetAddressPrefix] }
    subnets: [
      {
        name: 'snet-apps'
        properties: {
          addressPrefix: subnetApps
          delegations: [
            { name: 'aca', properties: { serviceName: 'Microsoft.App/environments' } }
          ]
        }
      }
      {
        name: 'snet-postgres'
        properties: {
          addressPrefix: subnetPostgres
          delegations: [
            { name: 'pg', properties: { serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers' } }
          ]
        }
      }
      {
        name: 'snet-endpoints'
        properties: {
          addressPrefix: subnetEndpoints
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

// ── Key Vault (private) ──────────────────────────────────────────────────────

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: names.keyVault
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: keyVaultPurgeProtection ? true : null
    publicNetworkAccess: 'Disabled'
    networkAcls: { defaultAction: 'Deny', bypass: 'AzureServices' }
  }
}

var kvSecretsUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')

resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, identity.id, kvSecretsUserRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: kvSecretsUserRoleId
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource kvDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.vaultcore.azure.net'
  location: 'global'
  tags: tags
}

resource kvDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: kvDnsZone
  name: '${names.vnet}-link'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnet.id }
    registrationEnabled: false
  }
}

resource kvEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-${names.keyVault}'
  location: location
  tags: tags
  properties: {
    subnet: { id: '${vnet.id}/subnets/snet-endpoints' }
    privateLinkServiceConnections: [
      {
        name: 'kv'
        properties: {
          privateLinkServiceId: keyVault.id
          groupIds: ['vault']
        }
      }
    ]
  }
}

resource kvEndpointDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: kvEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'vault', properties: { privateDnsZoneId: kvDnsZone.id } }
    ]
  }
}

// ── PostgreSQL Flexible Server (VNet-injected, no public access) ─────────────

resource pgDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'codelyst-${environmentName}.private.postgres.database.azure.com'
  location: 'global'
  tags: tags
}

resource pgDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: pgDnsZone
  name: '${names.vnet}-link'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnet.id }
    registrationEnabled: false
  }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: names.postgres
  location: location
  tags: tags
  sku: { name: postgresSkuName, tier: postgresSkuTier }
  properties: {
    version: '16'
    administratorLogin: postgresAdminLogin
    // Omitted on redeploys so the existing password is kept.
    administratorLoginPassword: empty(postgresAdminPassword) ? null : postgresAdminPassword
    authConfig: { passwordAuth: 'Enabled', activeDirectoryAuth: 'Disabled' }
    storage: { storageSizeGB: postgresStorageGb, autoGrow: 'Enabled' }
    backup: {
      backupRetentionDays: postgresBackupRetentionDays
      geoRedundantBackup: postgresGeoRedundantBackup ? 'Enabled' : 'Disabled'
    }
    network: {
      delegatedSubnetResourceId: '${vnet.id}/subnets/snet-postgres'
      privateDnsZoneArmResourceId: pgDnsZone.id
      publicNetworkAccess: 'Disabled'
    }
    highAvailability: { mode: 'Disabled' }
  }
  dependsOn: [pgDnsLink]
}

// Postgres normally logs the full text of any statement that errors. Those
// statements can carry clinical notes, and server logs flow to Log Analytics,
// so keep statement text out of the logs entirely.
resource pgNoStatementLogs 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-12-01-preview' = {
  parent: postgres
  name: 'log_min_error_statement'
  properties: { value: 'PANIC', source: 'user-override' }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01-preview' = {
  parent: postgres
  name: databaseName
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

// ── Secrets (written only when values are passed) ────────────────────────────

var databaseUrl = 'postgresql+asyncpg://${postgresAdminLogin}:${postgresAdminPassword}@${postgres.properties.fullyQualifiedDomainName}:5432/${databaseName}'

resource secretDatabaseUrl 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(postgresAdminPassword)) {
  parent: keyVault
  name: 'database-url'
  properties: { value: databaseUrl, contentType: 'connection-string' }
}

resource secretAnthropic 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(anthropicApiKey)) {
  parent: keyVault
  name: 'anthropic-api-key'
  properties: { value: anthropicApiKey }
}

resource secretJwt 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(jwtSecretKey)) {
  parent: keyVault
  name: 'jwt-secret-key'
  properties: { value: jwtSecretKey }
}

resource secretJwtRefresh 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(jwtRefreshSecretKey)) {
  parent: keyVault
  name: 'jwt-refresh-secret-key'
  properties: { value: jwtRefreshSecretKey }
}

resource secretEncryption 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(encryptionKey)) {
  parent: keyVault
  name: 'encryption-key'
  properties: { value: encryptionKey }
}

// ── Container Apps ───────────────────────────────────────────────────────────

resource caEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: names.caEnv
  location: location
  tags: tags
  properties: {
    vnetConfiguration: {
      infrastructureSubnetId: '${vnet.id}/subnets/snet-apps'
      internal: false
    }
    workloadProfiles: [
      { name: 'Consumption', workloadProfileType: 'Consumption' }
    ]
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    zoneRedundant: false
  }
}

var webFqdn = '${names.web}.${caEnv.properties.defaultDomain}'
var kvUri = keyVault.properties.vaultUri

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: names.api
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    environmentId: caEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false // reachable only from inside the environment
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        { server: acr.properties.loginServer, identity: identity.id }
      ]
      secrets: [
        { name: 'database-url', keyVaultUrl: '${kvUri}secrets/database-url', identity: identity.id }
        { name: 'anthropic-api-key', keyVaultUrl: '${kvUri}secrets/anthropic-api-key', identity: identity.id }
        { name: 'jwt-secret-key', keyVaultUrl: '${kvUri}secrets/jwt-secret-key', identity: identity.id }
        { name: 'jwt-refresh-secret-key', keyVaultUrl: '${kvUri}secrets/jwt-refresh-secret-key', identity: identity.id }
        { name: 'encryption-key', keyVaultUrl: '${kvUri}secrets/encryption-key', identity: identity.id }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: backendImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'APP_ENV', value: isProd ? 'production' : 'staging' }
            // TLS terminates at the Container Apps ingress, which sets
            // X-Forwarded-Proto. The app trusts that header only from inside
            // this VNet (TRUSTED_PROXIES) and redirects anything that was plain HTTP.
            { name: 'ENFORCE_HTTPS', value: 'true' }
            { name: 'TRUSTED_PROXIES', value: vnetAddressPrefix }
            { name: 'DATABASE_SSL', value: 'true' }
            { name: 'ALLOWED_ORIGINS', value: 'https://${webFqdn}' }
            { name: 'REQUIRE_MFA', value: string(requireMfa) }
            { name: 'CPT_LICENSED', value: string(cptLicensed) }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'ANTHROPIC_API_KEY', secretRef: 'anthropic-api-key' }
            { name: 'SECRET_KEY', secretRef: 'jwt-secret-key' }
            { name: 'REFRESH_SECRET_KEY', secretRef: 'jwt-refresh-secret-key' }
            { name: 'ENCRYPTION_KEY', secretRef: 'encryption-key' }
          ]
          probes: [
            { type: 'Liveness', httpGet: { path: '/health', port: 8000 }, periodSeconds: 30 }
            { type: 'Readiness', httpGet: { path: '/health', port: 8000 }, periodSeconds: 10 }
          ]
        }
      ]
      scale: { minReplicas: minReplicas, maxReplicas: maxReplicas }
    }
  }
  dependsOn: [
    acrPull
    kvSecretsUser
    kvEndpointDns
    kvDnsLink
    database
    pgNoStatementLogs
    secretDatabaseUrl
    secretAnthropic
    secretJwt
    secretJwtRefresh
    secretEncryption
  ]
}

resource web 'Microsoft.App/containerApps@2024-03-01' = {
  name: names.web
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    environmentId: caEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 80
        transport: 'auto'
        allowInsecure: false // HTTP requests are redirected to HTTPS
      }
      registries: [
        { server: acr.properties.loginServer, identity: identity.id }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: frontendImage
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            { name: 'BACKEND_FQDN', value: api.properties.configuration.ingress.fqdn }
          ]
          probes: [
            { type: 'Liveness', httpGet: { path: '/', port: 80 }, periodSeconds: 30 }
          ]
        }
      ]
      scale: { minReplicas: minReplicas, maxReplicas: maxReplicas }
    }
  }
  dependsOn: [acrPull]
}

// ── Diagnostic logs → Log Analytics ──────────────────────────────────────────

resource kvDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-log-analytics'
  scope: keyVault
  properties: {
    workspaceId: logs.id
    logs: [{ categoryGroup: 'audit', enabled: true }]
  }
}

resource pgDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-log-analytics'
  scope: postgres
  properties: {
    workspaceId: logs.id
    logs: [{ categoryGroup: 'allLogs', enabled: true }]
    metrics: [{ category: 'AllMetrics', enabled: true }]
  }
}

// ── Optional: SFTP drop for facility exports ─────────────────────────────────

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = if (enableSftpStorage) {
  name: names.storage
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: isProd ? 'Standard_ZRS' : 'Standard_LRS' }
  properties: {
    isHnsEnabled: true // required for SFTP
    isSftpEnabled: true
    isLocalUserEnabled: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Enabled' // facilities connect from the internet...
    networkAcls: {
      defaultAction: 'Deny' // ...but only from allowlisted IPs
      bypass: 'AzureServices'
      ipRules: [for ip in sftpAllowedIps: { value: ip, action: 'Allow' }]
    }
    encryption: {
      services: {
        blob: { enabled: true, keyType: 'Account' }
      }
      keySource: 'Microsoft.Storage'
      requireInfrastructureEncryption: true
    }
  }
}

// ── Outputs ──────────────────────────────────────────────────────────────────

output webUrl string = 'https://${webFqdn}'
output apiInternalFqdn string = api.properties.configuration.ingress.fqdn
output keyVaultName string = keyVault.name
output postgresServerName string = postgres.name
output logAnalyticsWorkspace string = logs.name
