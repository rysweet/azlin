# azlin doit - Quick Start Guide

Get started with autonomous Azure infrastructure deployment in 5 minutes.

## Prerequisites

```bash
# 1. Azure CLI authenticated
az login
az account set --subscription <your-subscription-id>

# 2. azlin installed
pip install -e .

# 3. Verify installation
azlin --version
azlin doit --help
```

## Your First Deployment

### 1. See Examples

```bash
azlin doit examples
```

### 2. Dry Run (Recommended First)

```bash
azlin doit deploy "Give me App Service with Cosmos DB" --dry-run
```

This shows what would be deployed without creating resources.

### 3. Deploy Storage Account (Simple Test)

```bash
azlin doit deploy "Create a storage account"
```

**What happens**:
1. Parses request → Resource Group + Storage Account
2. Deploys Resource Group (30 seconds)
3. Deploys Storage Account (2 minutes)
4. Generates Terraform, Bicep, README
5. Total time: ~3 minutes

**Output**:
```
~/.azlin/doit/output/
├── main.tf            # Terraform
├── variables.tf       # Variables
├── outputs.tf         # Outputs
├── main.bicep         # Bicep
└── README.md          # Complete guide
```

### 4. Deploy Web App + Database

```bash
azlin doit deploy "Give me App Service with Cosmos DB"
```

**What happens**:
1. Parses request → 6 resources with dependencies
2. Deploys in order:
   - Resource Group
   - Key Vault + Cosmos DB (parallel)
   - App Service Plan + App Service
   - Connection (App → KeyVault → Cosmos)
3. Self-evaluates each step
4. Generates production-ready IaC
5. Total time: ~5-7 minutes

**Deployed Resources**:
- ✓ Resource Group
- ✓ Key Vault (with RBAC)
- ✓ Cosmos DB (Session consistency)
- ✓ App Service Plan (B1)
- ✓ App Service (with managed identity)
- ✓ Connection configured via Key Vault

### 5. Deploy Complete Platform

```bash
azlin doit deploy "Create App Service, Cosmos DB, API Management, Storage, and KeyVault all connected"
```

**Time**: ~8-10 minutes (APIM is slow)

## Understanding the Output

### Terminal Output

```
========================================
PROGRESS REPORT - Iteration 5/50
========================================

COMPLETED (3/6):
✓ Resource Group (rg-webapp-dev-eastus)
✓ Storage Account (stwebappdeveastus)
✓ Key Vault (kv-webapp-dev)

IN PROGRESS (1/6):
⟳ Cosmos DB (cosmos-webapp-dev)

PENDING (2/6):
□ App Service
□ API Management

STATUS: On track | 4 minutes elapsed
========================================
```

### Generated Files

#### main.tf (Terraform)
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

resource "azurerm_resource_group" "rg_webapp_dev_eastus" {
  name     = "rg-webapp-dev-eastus"
  location = "eastus"
  ...
}
```

#### main.bicep
```bicep
@description('Azure region for resources')
param location string = resourceGroup().location

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: 'stwebappdeveastus'
  location: location
  ...
}
```

#### README.md
- Architecture diagram
- Resource descriptions
- Cost estimates (~$40/month)
- Deployment instructions
- Security notes
- Troubleshooting guide

## Common Use Cases

### Web Application Stack

```bash
azlin doit deploy "Give me App Service with Cosmos DB"
```

**Use for**: Web apps needing NoSQL database

### API Platform

```bash
azlin doit deploy "Create App Service behind API Management"
```

**Use for**: Managed API gateway with backend services

### Microservices

```bash
azlin doit deploy "Deploy 3 App Services with shared Cosmos DB"
```

**Use for**: Multiple services sharing data layer

### Serverless

```bash
azlin doit deploy "Create Function App with Storage and Key Vault"
```

**Use for**: Event-driven serverless applications

### Regional Deployment

```bash
azlin doit deploy "Deploy web app with database in westus"
```

**Use for**: Specific region requirements

## Options

### Output Directory

```bash
azlin doit deploy "..." --output-dir ./my-infrastructure
```

Default: `~/.azlin/doit/output`

### Max Iterations

```bash
azlin doit deploy "..." --max-iterations 100
```

Default: 50 (safety limit)

### Quiet Mode

```bash
azlin doit deploy "..." --quiet
```

Reduces terminal output verbosity.

## Deploy the Generated Infrastructure

### Option 1: Terraform

```bash
cd ~/.azlin/doit/output

# Initialize
terraform init

# Review plan
terraform plan

# Apply
terraform apply

# Clean up later
terraform destroy
```

### Option 2: Bicep

```bash
cd ~/.azlin/doit/output

# Create resource group
az group create --name <rg-name> --location eastus

# Deploy
az deployment group create \
  --resource-group <rg-name> \
  --template-file main.bicep

# Clean up later
az group delete --name <rg-name> --yes
```

## Troubleshooting

### "Command not found: azlin doit"

```bash
# Reinstall azlin
pip uninstall azlin
pip install -e .

# Or add to PATH
export PATH="$PATH:$HOME/.local/bin"
```

### "Azure CLI not authenticated"

```bash
az login
az account show  # Verify
```

### "Resource name already exists"

The agent will automatically try alternative names (e.g., `storage2`, `storage3`).

If it keeps failing, check:
```bash
az storage account check-name --name <name>
```

### "Deployment failed"

Check the generated README:
```bash
cat ~/.azlin/doit/output/README.md
```

Look in the "Troubleshooting" section.

### "Quota exceeded"

The agent will try:
1. Different region
2. Lower SKU
3. Report to you if all options exhausted

Request quota increase:
```bash
# Azure Portal → Subscriptions → Usage + Quotas
```

## What Gets Deployed

### Security Features (Always Applied)

- ✅ Managed identities (no credentials in code)
- ✅ Secrets in Key Vault
- ✅ HTTPS enforced
- ✅ TLS 1.2 minimum
- ✅ RBAC for Key Vault access
- ✅ Public blob access disabled

### Default SKUs (Cost-Optimized)

- App Service: B1 ($13/month)
- Cosmos DB: 400 RU/s ($24/month)
- Storage: Standard_LRS ($1-5/month)
- Key Vault: Standard ($0 for basic ops)

### Resource Naming Convention

Format: `<type>-<name>-<env>-<region>`

Examples:
- `rg-webapp-dev-eastus`
- `app-webapp-dev-eastus`
- `cosmos-webapp-dev-eastus`
- `kv-webapp-dev` (global)
- `stwebappdeveastus` (no hyphens)

## Cost Management

### Before Deployment

Use `--dry-run` to see what will be deployed:
```bash
azlin doit deploy "..." --dry-run
```

Check README after deployment for cost estimates.

### After Deployment

Monitor costs:
```bash
az consumption usage list --output table
```

Set budget alerts in Azure Portal.

### Clean Up

Delete resource group (deletes everything):
```bash
az group delete --name rg-webapp-dev-eastus --yes
```

Or use Terraform:
```bash
terraform destroy
```

## Advanced Usage

### Custom Output Directory

```bash
azlin doit deploy "..." --output-dir ~/projects/my-infra
```

### Multiple Deployments

Each deployment creates a timestamp-based output:
```bash
azlin doit deploy "..." --output-dir ~/infra/deploy-$(date +%Y%m%d-%H%M%S)
```

### Production Deployment

Specify "production" in request for higher SKUs:
```bash
azlin doit deploy "Create production App Service with Cosmos DB"
```

This uses:
- App Service: S1 ($70/month) instead of B1
- Cosmos DB: Same
- Other resources: Appropriate production settings

## Getting Help

### Show Examples

```bash
azlin doit examples
```

### View Status

```bash
azlin doit status  # (Future feature)
```

### List Recent Deployments

```bash
azlin doit list  # (Future feature)
```

### Main Help

```bash
azlin doit --help
azlin doit deploy --help
```

## Next Steps

1. ✅ Start with dry run
2. ✅ Deploy simple storage account
3. ✅ Deploy web app + database
4. ✅ Review generated Terraform/Bicep
5. ✅ Deploy generated infrastructure
6. ✅ Explore more complex scenarios

## Real-World Example

Let's build a complete web application infrastructure:

```bash
# Step 1: Deploy infrastructure
azlin doit deploy "Give me App Service with Cosmos DB, Storage, and KeyVault all connected"

# Step 2: Review generated artifacts
cd ~/.azlin/doit/output
cat README.md

# Step 3: Deploy with Terraform
terraform init
terraform plan
terraform apply

# Step 4: Deploy your application
APP_NAME=$(terraform output -raw app_service_name)
az webapp deployment source config-zip \
  --name $APP_NAME \
  --resource-group rg-webapp-dev-eastus \
  --src myapp.zip

# Step 5: Test
APP_URL=$(terraform output -raw app_service_url)
curl $APP_URL
```

Done! You now have a production-ready web application infrastructure deployed and documented.

## Learn More

- [Full Documentation](src/azlin/doit/README.md)
- [Implementation Details](IMPLEMENTATION_SUMMARY.md)
- [Prompt Files](src/azlin/prompts/doit/)
- [Azure CLI Docs](https://learn.microsoft.com/cli/azure/)
- [Terraform Azure Provider](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs)

## Support

For issues or questions:
- Check generated README.md troubleshooting section
- Review Azure Portal for resource status
- Check Azure CLI logs: `az account list`
- Open GitHub issue: [azlin issues](https://github.com/ruvnet/azlin/issues)

---

**Ready to deploy? Start here:**

```bash
azlin doit deploy "Give me App Service with Cosmos DB" --dry-run
```
