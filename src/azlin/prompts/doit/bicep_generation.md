# Bicep Generation Prompt

Generate production-ready Bicep configuration from executed actions.

## Input
Actions taken: {actions}
Resources created: {resources}
Connections: {connections}

## Your Task

Generate complete Bicep code with:
1. **Main template**: All resources
2. **Parameters file**: Configurable values
3. **Modules**: Reusable components (optional)
4. **README**: Deployment instructions

## File Structure

### main.bicep
Main template with all resources

### main.parameters.json
Parameter values

### modules/ (optional)
Reusable Bicep modules

### README.md
Deployment guide

## Example: App Service + Cosmos DB

### main.bicep
```bicep
@description('Name of the resource group')
param location string = resourceGroup().location

@description('Environment name (dev, staging, prod)')
@allowed([
  'dev'
  'staging'
  'prod'
])
param environment string = 'prod'

@description('Base name for resources')
param baseName string = 'webapp'

@description('App Service SKU')
@allowed([
  'B1'
  'B2'
  'B3'
  'S1'
  'S2'
  'S3'
  'P1V2'
  'P2V2'
  'P3V2'
])
param appServiceSku string = 'B1'

@description('Tags to apply to all resources')
param tags object = {
  Environment: environment
  ManagedBy: 'Bicep'
  Project: baseName
}

// Storage Account
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: 'st${baseName}${environment}${uniqueString(resourceGroup().id)}'
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
  tags: tags
}

// Key Vault
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${baseName}-${environment}-${uniqueString(resourceGroup().id)}'
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: false
  }
  tags: tags
}

// Cosmos DB Account
resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: 'cosmos-${baseName}-${environment}-${uniqueString(resourceGroup().id)}'
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
  }
  tags: tags
}

// App Service Plan
resource appServicePlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: 'plan-${baseName}-${environment}'
  location: location
  sku: {
    name: appServiceSku
  }
  kind: 'linux'
  properties: {
    reserved: true // Required for Linux
  }
  tags: tags
}

// App Service
resource appService 'Microsoft.Web/sites@2023-01-01' = {
  name: 'app-${baseName}-${environment}-${uniqueString(resourceGroup().id)}'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'NODE|18-lts'
      alwaysOn: appServiceSku != 'B1' // B1 doesn't support always on
      appSettings: [
        {
          name: 'COSMOS_ENDPOINT'
          value: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/cosmos-endpoint/)'
        }
        {
          name: 'COSMOS_KEY'
          value: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/cosmos-key/)'
        }
      ]
    }
    httpsOnly: true
  }
  tags: tags
}

// Grant App Service access to Key Vault
resource keyVaultRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, appService.id, 'Key Vault Secrets User')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6') // Key Vault Secrets User
    principalId: appService.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Store Cosmos connection info in Key Vault
resource cosmosEndpointSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'cosmos-endpoint'
  properties: {
    value: cosmosAccount.properties.documentEndpoint
  }
  dependsOn: [
    keyVaultRoleAssignment
  ]
}

resource cosmosKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'cosmos-key'
  properties: {
    value: cosmosAccount.listKeys().primaryMasterKey
  }
  dependsOn: [
    keyVaultRoleAssignment
  ]
}

// Outputs
output appServiceUrl string = 'https://${appService.properties.defaultHostName}'
output appServiceIdentity string = appService.identity.principalId
output cosmosEndpoint string = cosmosAccount.properties.documentEndpoint
output storageAccountName string = storageAccount.name
output keyVaultName string = keyVault.name
```

### main.parameters.json
```json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "environment": {
      "value": "prod"
    },
    "baseName": {
      "value": "webapp"
    },
    "appServiceSku": {
      "value": "B1"
    },
    "tags": {
      "value": {
        "Environment": "Production",
        "ManagedBy": "Bicep",
        "Project": "WebApp"
      }
    }
  }
}
```

### README.md
```markdown
# Azure Infrastructure - Bicep Deployment

This Bicep template deploys:
- App Service (Linux, Node.js 18 LTS)
- Cosmos DB (SQL API)
- Storage Account
- Key Vault
- Managed Identity integration

## Prerequisites

- Azure CLI installed
- Azure subscription
- Appropriate permissions

## Deployment

### Deploy to existing resource group:
```bash
az group create --name rg-webapp-prod --location eastus

az deployment group create \
  --resource-group rg-webapp-prod \
  --template-file main.bicep \
  --parameters main.parameters.json
```

### Deploy with inline parameters:
```bash
az deployment group create \
  --resource-group rg-webapp-prod \
  --template-file main.bicep \
  --parameters environment=prod baseName=myapp appServiceSku=B1
```

## Post-Deployment

1. Deploy application code:
```bash
az webapp deployment source config-zip \
  --resource-group rg-webapp-prod \
  --name <app-service-name> \
  --src app.zip
```

2. Verify Cosmos connection:
```bash
az webapp config appsettings list \
  --resource-group rg-webapp-prod \
  --name <app-service-name>
```

## Architecture

```
┌─────────────┐
│ App Service │
└──────┬──────┘
       │ Managed Identity
       ▼
┌─────────────┐      ┌───────────┐
│  Key Vault  │─────▶│ Cosmos DB │
└─────────────┘      └───────────┘
       │
       ▼
   Secrets
```

## Security Features

- Managed Identity (no credentials in code)
- Key Vault for secrets
- HTTPS only
- TLS 1.2 minimum
- RBAC for Key Vault access
- No public blob access

## Cost Estimation

Monthly cost (approximate):
- App Service B1: $13
- Cosmos DB (400 RU/s): $24
- Storage Account: $1-5
- Key Vault: $0 (basic operations)
**Total: ~$40/month**

Costs vary by region and usage.
```

## Bicep Best Practices

1. **Use parameters**: Make templates reusable
2. **Use uniqueString()**: For globally unique names
3. **Use parent/child syntax**: For nested resources
4. **Use symbolic names**: Not resource IDs
5. **Add descriptions**: Document all parameters
6. **Use allowed values**: Constrain inputs
7. **Group related resources**: Use modules for complex templates
8. **Add outputs**: Return useful values
