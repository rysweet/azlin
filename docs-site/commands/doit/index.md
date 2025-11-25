# Doit Commands

Autonomous Azure infrastructure deployment using natural language.

## Overview

azlin doit is an AI-powered infrastructure deployment system that understands natural language requests and autonomously deploys Azure resources using Azure CLI.

## Key Features

- **Natural Language**: Describe what you need in plain English
- **Autonomous Deployment**: AI agent plans and executes deployment
- **Dependency Resolution**: Automatically determines correct resource order
- **Infrastructure as Code**: Generates Terraform and Bicep templates
- **Production Ready**: Creates secure, well-architected infrastructure
- **Educational**: Explains what it's doing and why

## Commands

- [deploy](deploy.md) - Deploy infrastructure from natural language
- [list](list.md) - List all doit-created resources
- [show](show.md) - Show detailed resource information
- [status](status.md) - Check deployment session status
- [cleanup](cleanup.md) - Delete all doit-created resources
- [examples](examples.md) - View example requests

## Quick Start

### 1. Simple web app

```bash
azlin doit deploy "Create a web app with database"
```

### 2. Preview before deploying

```bash
azlin doit deploy "Create App Service with Cosmos DB" --dry-run
```

### 3. Complex infrastructure

```bash
azlin doit deploy "Deploy microservices with API Management, KeyVault, Storage, and Cosmos DB in eastus"
```

### 4. List created resources

```bash
azlin doit list
```

### 5. Clean up

```bash
azlin doit cleanup --dry-run
azlin doit cleanup
```

## How It Works

1. **Parse Request**: AI parses your natural language into concrete goals
2. **Plan Deployment**: Determines dependencies and order
3. **Execute**: Deploys using Azure CLI with error handling
4. **Verify**: Validates each resource was created successfully
5. **Generate IaC**: Creates Terraform and Bicep templates
6. **Explain**: Provides documentation and learning materials

## Example Requests

### Web Applications

```bash
# Simple web app
azlin doit deploy "web app"

# Web app with database
azlin doit deploy "web app with SQL database"

# Full stack
azlin doit deploy "web app, database, storage, and CDN"
```

### Data Services

```bash
# NoSQL database
azlin doit deploy "Cosmos DB with MongoDB API"

# Data warehouse
azlin doit deploy "SQL database with data factory"

# Cache
azlin doit deploy "Redis cache for session storage"
```

### Microservices

```bash
# API backend
azlin doit deploy "API Management with backend services"

# Event-driven
azlin doit deploy "Service Bus, Functions, and Event Grid"

# Container platform
azlin doit deploy "AKS cluster with ACR and monitoring"
```

### Security & Secrets

```bash
# Secrets management
azlin doit deploy "KeyVault with managed identity"

# Secure networking
azlin doit deploy "VNet with private endpoints and NSG"
```

## Output Artifacts

After deployment, doit generates:

### 1. Terraform Template

```hcl
# main.tf
terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

resource "azurerm_app_service" "main" {
  # Generated configuration
}
```

### 2. Bicep Template

```bicep
resource webApp 'Microsoft.Web/sites@2022-03-01' = {
  name: 'myapp'
  location: resourceGroup().location
  // Generated configuration
}
```

### 3. Documentation

```markdown
# Deployment Guide

## Resources Created
- App Service: myapp-web
- SQL Database: myapp-db
- Storage Account: myappstorage

## Architecture
[Diagram and explanation]

## Next Steps
[Post-deployment tasks]
```

## Resource Tagging

All doit-created resources are tagged with:

```yaml
azlin-doit-owner: user@example.com
azlin-doit-session: abc123
azlin-doit-timestamp: 2025-11-24T10:30:00Z
azlin-doit-request: "web app with database"
```

This enables:
- Easy identification
- Bulk cleanup
- Cost tracking
- Audit trail

## Best Practices

### 1. Start with dry-run

```bash
azlin doit deploy "complex infrastructure" --dry-run
```

### 2. Be specific about regions

```bash
azlin doit deploy "web app in eastus"
```

### 3. Review generated IaC

```bash
azlin doit deploy "app service" -o ./infrastructure
cd infrastructure
cat terraform/main.tf
```

### 4. Clean up test deployments

```bash
azlin doit cleanup
```

## Related Commands

- [azlin do](../ai/do.md) - Natural language VM management
- [azlin autopilot](../autopilot/index.md) - Cost optimization
