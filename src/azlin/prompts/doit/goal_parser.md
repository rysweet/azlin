# Goal Parser Prompt

Parse the user's natural language request into a structured goal hierarchy.

## Input
User request: "{user_request}"

## Your Task

Analyze the request and extract:

1. **Primary Resources**: What Azure resources are explicitly mentioned?
   - App Service, Cosmos DB, API Management, Storage Account, Key Vault, etc.

2. **Implicit Requirements**: What's implied but not stated?
   - Resource Group (always needed)
   - Networking (VNet if private connectivity mentioned)
   - Identity (Managed Identity for connections)
   - Monitoring (if production workload)

3. **Relationships**: How do resources connect?
   - "with" = integration/connection needed
   - "behind" = fronted by (e.g., "App Service behind API Management")
   - "using" = dependency (e.g., "App Service using Cosmos DB")

4. **Constraints**: Any specific requirements?
   - Region (default: eastus if not specified)
   - SKU/tier (default: Basic for dev, Standard for prod)
   - Performance requirements
   - Security requirements (private, public)

5. **Goal Hierarchy**: Dependencies between resources
   - Level 0: Resource Group, VNet (if needed)
   - Level 1: Storage, Key Vault, Cosmos DB
   - Level 2: App Service, API Management
   - Level 3: Connections and configurations

## Output Format

Return JSON:
```json
{
  "primary_goal": "Deploy connected Azure services",
  "resources": [
    {
      "type": "azurerm_resource_group",
      "name": "rg-webapp-prod-eastus",
      "level": 0,
      "dependencies": []
    },
    {
      "type": "azurerm_storage_account",
      "name": "stwebappprodeastus",
      "level": 1,
      "dependencies": ["azurerm_resource_group.rg-webapp-prod-eastus"]
    }
  ],
  "connections": [
    {
      "from": "azurerm_app_service",
      "to": "azurerm_cosmosdb_account",
      "type": "connection_string",
      "via": "key_vault_secret"
    }
  ],
  "implicit_requirements": [
    "managed_identity",
    "diagnostic_logs"
  ]
}
```

## Examples

User: "Give me App Service with Cosmos DB"
Parse as:
- Resource Group
- Cosmos DB account
- App Service
- Key Vault (to store Cosmos connection string)
- Managed Identity (for App Service to access Key Vault)
- Connection: App Service -> Key Vault -> Cosmos DB

User: "Create an API behind API Management"
Parse as:
- Resource Group
- API Management
- App Service (to host the API)
- Connection: APIM -> App Service backend
