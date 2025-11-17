# Strategy Selection Prompt

Given a goal to achieve, select and execute the appropriate strategy.

## Current Goal
Type: {goal_type}
Name: {goal_name}
Dependencies: {dependencies}
Status: {status}

## Available Strategies

1. **Resource Group Strategy**: Create Azure resource group
2. **App Service Strategy**: Deploy App Service (Web App)
3. **Cosmos DB Strategy**: Deploy Cosmos DB account
4. **API Management Strategy**: Deploy API Management gateway
5. **Storage Strategy**: Deploy Storage Account
6. **Key Vault Strategy**: Deploy Key Vault
7. **Connection Strategy**: Connect two resources
8. **VNet Strategy**: Create Virtual Network
9. **Managed Identity Strategy**: Create and assign managed identity

## Your Task

For the current goal:

1. **Select Strategy**: Which strategy should execute?
2. **Gather Parameters**: What parameters does it need?
   - Check previous goal outputs for dependency values
   - Use sensible defaults for missing values
3. **Preflight Check**: Are dependencies ready?
   - All prerequisite resources deployed?
   - Required configuration values available?

## Output Format

```json
{
  "strategy": "app_service",
  "parameters": {
    "name": "app-myservice-prod-eastus",
    "resource_group": "rg-myservice-prod-eastus",
    "location": "eastus",
    "sku": "B1",
    "managed_identity": true
  },
  "preflight": {
    "ready": true,
    "missing_dependencies": [],
    "warnings": ["SKU B1 suitable for dev, consider P1V2 for production"]
  }
}
```

## Strategy Selection Logic

### For Resource Group
Always first step. Needs: name, location.

### For Data Services (Cosmos, Storage)
Deploy early (level 1). No dependencies usually.

### For Key Vault
Deploy at level 1. Will store secrets for other resources.

### For Compute Services (App Service)
Deploy at level 2. May depend on: VNet, managed identity setup.

### For API Management
Deploy at level 2. May front App Service.

### For Connections
Deploy at level 3. Requires both resources to exist.
Use managed identity + Key Vault pattern.

## Error Handling

If dependencies not ready:
```json
{
  "strategy": null,
  "preflight": {
    "ready": false,
    "missing_dependencies": ["azurerm_resource_group.rg-webapp"],
    "action": "wait"
  }
}
```
