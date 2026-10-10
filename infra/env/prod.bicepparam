using '../main.bicep'

// Prod: real PHI. Pilot facilities run here.
param environmentName = 'prod'
param vnetAddressPrefix = '10.20.0.0/16'

param postgresSkuName = 'Standard_B2s'
param postgresSkuTier = 'Burstable' // move to GeneralPurpose (e.g. Standard_D2ds_v5) as load grows
param postgresBackupRetentionDays = 35
param postgresGeoRedundantBackup = true // must be set at creation; cannot be added later

param minReplicas = 1 // always warm for coders
param logRetentionDays = 365
param keyVaultPurgeProtection = true

// Turn on when the first facility starts sending file exports.
param enableSftpStorage = false
param sftpAllowedIps = []

// Set by deploy.sh
param acrName = readEnvironmentVariable('ACR_NAME')
param acrResourceGroup = readEnvironmentVariable('ACR_RG')
param backendImage = readEnvironmentVariable('BACKEND_IMAGE')
param frontendImage = readEnvironmentVariable('FRONTEND_IMAGE')
