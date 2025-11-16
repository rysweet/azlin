# Terraform Generation Prompt

Generate production-ready Terraform configuration from executed actions.

## Input
Actions taken: {actions}
Resources created: {resources}
Connections: {connections}
Configuration: {config}

## Your Task

Generate complete Terraform code that:
1. **Recreates all resources**: Exact configuration used
2. **Production-ready**: Security, monitoring, best practices
3. **Modular**: Organized into logical files
4. **Documented**: Comments explaining choices
5. **Parameterized**: Variables for customization

## File Structure

Generate these files:

### main.tf
Main resource definitions

### variables.tf
Input variables with defaults

### outputs.tf
Output values (endpoints, IDs, etc.)

### terraform.tfvars (example)
Example values for variables

### versions.tf
Required providers and versions

### README.md
Usage instructions

## Example: App Service + Cosmos DB

### main.tf
```hcl
terraform {
  required_version = ">= 1.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
}

# Resource Group
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location

  tags = var.tags
}

# Storage Account
resource "azurerm_storage_account" "main" {
  name                     = var.storage_account_name
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  # Security settings
  https_traffic_only_enabled = true
  min_tls_version           = "TLS1_2"
  allow_blob_public_access  = false

  tags = var.tags
}

# Key Vault
resource "azurerm_key_vault" "main" {
  name                       = var.key_vault_name
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  purge_protection_enabled   = false

  # RBAC instead of access policies
  enable_rbac_authorization = true

  tags = var.tags
}

# Cosmos DB
resource "azurerm_cosmosdb_account" "main" {
  name                = var.cosmos_account_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = azurerm_resource_group.main.location
    failover_priority = 0
  }

  tags = var.tags
}

# App Service Plan
resource "azurerm_service_plan" "main" {
  name                = var.app_service_plan_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  os_type             = "Linux"
  sku_name            = var.app_service_sku

  tags = var.tags
}

# App Service
resource "azurerm_linux_web_app" "main" {
  name                = var.app_service_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  service_plan_id     = azurerm_service_plan.main.id

  site_config {
    always_on = var.app_service_sku != "B1" # B1 doesn't support always_on

    application_stack {
      node_version = "18-lts"
    }
  }

  # Managed Identity
  identity {
    type = "SystemAssigned"
  }

  # Application settings
  app_settings = {
    "COSMOS_ENDPOINT" = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.cosmos_endpoint.id})"
    "COSMOS_KEY"      = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.cosmos_key.id})"
  }

  tags = var.tags
}

# Store Cosmos connection info in Key Vault
resource "azurerm_key_vault_secret" "cosmos_endpoint" {
  name         = "cosmos-endpoint"
  value        = azurerm_cosmosdb_account.main.endpoint
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [
    azurerm_role_assignment.app_service_kv_secrets
  ]
}

resource "azurerm_key_vault_secret" "cosmos_key" {
  name         = "cosmos-key"
  value        = azurerm_cosmosdb_account.main.primary_key
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [
    azurerm_role_assignment.app_service_kv_secrets
  ]
}

# Grant App Service access to Key Vault
resource "azurerm_role_assignment" "app_service_kv_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_linux_web_app.main.identity[0].principal_id
}

# Current Azure client config
data "azurerm_client_config" "current" {}
```

### variables.tf
```hcl
variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
  default     = "rg-webapp-prod-eastus"
}

variable "location" {
  description = "Azure region for resources"
  type        = string
  default     = "eastus"
}

variable "storage_account_name" {
  description = "Name of the storage account (must be globally unique)"
  type        = string
  default     = "stwebappprodeastus"
}

variable "key_vault_name" {
  description = "Name of the Key Vault (must be globally unique)"
  type        = string
  default     = "kv-webapp-prod"
}

variable "cosmos_account_name" {
  description = "Name of the Cosmos DB account (must be globally unique)"
  type        = string
  default     = "cosmos-webapp-prod"
}

variable "app_service_plan_name" {
  description = "Name of the App Service Plan"
  type        = string
  default     = "plan-webapp-prod"
}

variable "app_service_name" {
  description = "Name of the App Service (must be globally unique)"
  type        = string
  default     = "app-webapp-prod"
}

variable "app_service_sku" {
  description = "SKU for App Service Plan (B1, B2, B3, S1, S2, S3, P1V2, P2V2, P3V2)"
  type        = string
  default     = "B1"
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    Environment = "Production"
    ManagedBy   = "Terraform"
    Project     = "WebApp"
  }
}
```

### outputs.tf
```hcl
output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.main.name
}

output "app_service_url" {
  description = "URL of the App Service"
  value       = "https://${azurerm_linux_web_app.main.default_hostname}"
}

output "app_service_identity" {
  description = "Managed identity of the App Service"
  value       = azurerm_linux_web_app.main.identity[0].principal_id
}

output "cosmos_endpoint" {
  description = "Cosmos DB endpoint"
  value       = azurerm_cosmosdb_account.main.endpoint
}

output "storage_account_name" {
  description = "Name of the storage account"
  value       = azurerm_storage_account.main.name
}

output "key_vault_name" {
  description = "Name of the Key Vault"
  value       = azurerm_key_vault.main.name
}
```

### versions.tf
```hcl
terraform {
  required_version = ">= 1.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}
```

## Best Practices Applied

1. **Security**:
   - Managed identities instead of connection strings
   - Secrets in Key Vault
   - HTTPS only
   - TLS 1.2 minimum
   - RBAC for Key Vault

2. **Reliability**:
   - Explicit dependencies
   - Proper resource ordering
   - Soft delete for Key Vault

3. **Maintainability**:
   - Variables for customization
   - Descriptive names
   - Comments explaining choices
   - Outputs for integration

4. **Cost Optimization**:
   - Appropriate SKUs for use case
   - LRS replication for non-critical data
   - Session consistency for Cosmos (not Strong)

## Comments to Include

Add comments for:
- Why certain SKUs chosen
- Security configurations
- Integration patterns
- Cost implications
- Alternative options
- Known limitations
