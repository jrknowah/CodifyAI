using '../main.bicep'

// Staging: synthetic data only. Never load real PHI here.
param environmentName = 'staging'
param vnetAddressPrefix = '10.10.0.0/16'

param postgresSkuName = 'Standard_B1ms'
param postgresSkuTier = 'Burstable'
param postgresBackupRetentionDays = 7
param postgresGeoRedundantBackup = false

param minReplicas = 0 // scales to zero when idle; first request is slow
param logRetentionDays = 30
param keyVaultPurgeProtection = false // lets you tear staging down and rebuild

// Set by deploy.sh
param acrName = readEnvironmentVariable('ACR_NAME')
param acrResourceGroup = readEnvironmentVariable('ACR_RG')
param backendImage = readEnvironmentVariable('BACKEND_IMAGE')
param frontendImage = readEnvironmentVariable('FRONTEND_IMAGE')
