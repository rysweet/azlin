# Action Execution Prompt

Execute a specific action using Azure CLI, REST API, or MCP.

## Current Action
Type: {action_type}
Parameters: {parameters}
Goal: {goal_description}

## Execution Context
Available tools:
- Azure CLI (az): {az_available}
- Azure MCP: {mcp_available}
- Terraform: {terraform_available}
- Bicep: {bicep_available}

## Your Task

Execute the action and collect detailed results.

### 1. Choose Tool

Prefer this order:
1. Azure MCP (if available) - structured responses
2. Azure CLI - reliable, well-documented
3. Azure REST API - for operations not in CLI
4. Terraform/Bicep - for complex deployments

### 2. Execute Command

Build the appropriate command:

**Azure CLI Example**:
```bash
az storage account create \
  --name stwebappprod \
  --resource-group rg-webapp-prod \
  --location eastus \
  --sku Standard_LRS \
  --kind StorageV2 \
  --https-only true \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false
```

**MCP Example**:
```json
{
  "tool": "azure_mcp.create_storage_account",
  "params": {
    "name": "stwebappprod",
    "resource_group": "rg-webapp-prod",
    "location": "eastus",
    "sku": "Standard_LRS"
  }
}
```

### 3. Capture Results

Collect:
- **stdout/stderr**: Full command output
- **exit_code**: Success/failure indicator
- **resource_id**: Azure resource ID if created
- **outputs**: Key values (endpoint URLs, connection strings, etc.)
- **duration**: How long did it take?
- **errors**: Any errors or warnings

### 4. Verify Success

Check against success criteria:
```json
{
  "success": true,
  "criteria_met": [
    "Resource exists",
    "Status is Succeeded",
    "Endpoint accessible"
  ],
  "criteria_failed": [],
  "confidence": 0.95
}
```

## Output Format

```json
{
  "action": "create_storage_account",
  "tool_used": "az_cli",
  "command": "az storage account create ...",
  "execution": {
    "started_at": "2025-01-07T10:30:00Z",
    "completed_at": "2025-01-07T10:32:15Z",
    "duration_seconds": 135,
    "exit_code": 0
  },
  "result": {
    "success": true,
    "resource_id": "/subscriptions/.../resourceGroups/rg-webapp-prod/providers/Microsoft.Storage/storageAccounts/stwebappprod",
    "outputs": {
      "primary_endpoint": "https://stwebappprod.blob.core.windows.net/",
      "primary_key": "***REDACTED***",
      "status": "Succeeded"
    }
  },
  "verification": {
    "criteria_met": ["Resource exists", "Status is Succeeded"],
    "confidence": 1.0
  },
  "iac_fragment": {
    "terraform": "resource \"azurerm_storage_account\" \"main\" { ... }",
    "bicep": "resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = { ... }"
  },
  "logs": "Full command output..."
}
```

## Error Handling

If execution fails:
```json
{
  "action": "create_storage_account",
  "execution": {
    "exit_code": 1,
    "duration_seconds": 5
  },
  "result": {
    "success": false,
    "error": {
      "type": "StorageAccountAlreadyExists",
      "message": "The storage account named stwebappprod already exists under the subscription.",
      "code": "StorageAccountAlreadyExists",
      "recoverable": true,
      "suggested_fix": "Use a different name or use existing account"
    }
  },
  "retry_strategy": {
    "should_retry": true,
    "adjusted_parameters": {
      "name": "stwebappprod2"
    },
    "reason": "Name collision, trying alternative"
  }
}
```

## Security Notes

- Never log secrets in plaintext
- Redact connection strings and keys
- Store secrets in Key Vault immediately
- Use managed identities instead of keys when possible
