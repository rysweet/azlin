# Execution Planning Prompt

Create a detailed execution plan for achieving the parsed goals.

## Input
Goal hierarchy: {goals}
Current state: {state}
Previous actions: {history}

## Your Task

Create a step-by-step execution plan that:

1. **Orders operations**: Respect dependencies
2. **Batches parallel work**: What can run concurrently?
3. **Defines success criteria**: How to verify each step?
4. **Plans rollback**: What to do if step fails?

## Output Format

```json
{
  "plan": [
    {
      "step": 1,
      "action": "create_resource_group",
      "goal_id": "goal-001",
      "parallel_group": 1,
      "estimated_duration": "30s",
      "success_criteria": [
        "Resource group exists",
        "az group show returns 200"
      ],
      "rollback": "az group delete --name {name} --yes",
      "iac_fragment": "resource_group.tf"
    },
    {
      "step": 2,
      "action": "create_storage_account",
      "goal_id": "goal-002",
      "parallel_group": 2,
      "estimated_duration": "2m",
      "success_criteria": [
        "Storage account provisioned",
        "Account accessible",
        "Primary key retrievable"
      ],
      "rollback": null,
      "iac_fragment": "storage.tf"
    }
  ],
  "parallel_groups": [
    {
      "group": 1,
      "steps": [1],
      "description": "Foundation resources"
    },
    {
      "group": 2,
      "steps": [2, 3, 4],
      "description": "Data layer - can run in parallel"
    }
  ],
  "estimated_total_duration": "8m",
  "rollback_plan": "Delete resource group (cascades to all resources)"
}
```

## Planning Principles

### Dependency Levels

**Level 0** (Sequential):
- Resource Group
- VNet (if needed)

**Level 1** (Parallel):
- Storage Account
- Cosmos DB
- Key Vault

**Level 2** (Parallel after Level 1):
- App Service
- API Management
- Function App

**Level 3** (Sequential after Level 2):
- Connections
- Configuration
- Managed Identity assignments

### Success Criteria Examples

Resource Group:
- `az group show --name {name}` returns 200
- Location matches requested location

Storage Account:
- `az storage account show --name {name}` returns 200
- Primary key accessible
- Can create test container

App Service:
- `az webapp show --name {name}` returns 200
- Default hostname accessible (returns HTTP 200 or 404, not connection error)
- Managed identity exists (if configured)

Connection:
- Source resource has connection string in environment
- Connection string points to target resource
- Test connection succeeds (optional health check)

### Rollback Strategy

**Per-resource**: Individual delete commands
**Cascade**: Delete resource group deletes everything
**Recommendation**: Use resource group deletion in dev, per-resource in prod

## Adaptation

If step fails:
1. Check if transient (retry after delay)
2. Check if configuration issue (adjust and retry)
3. Try alternative approach (different SKU, region, etc.)
4. If all fail, mark goal as blocked and report to user
