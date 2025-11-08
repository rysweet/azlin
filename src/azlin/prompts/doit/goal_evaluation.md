# Goal Evaluation Prompt

Evaluate whether a goal has been successfully achieved.

## Goal Details
Goal ID: {goal_id}
Type: {goal_type}
Description: {description}
Success criteria: {criteria}

## Action Results
Actions taken: {actions}
Outputs: {outputs}
Errors: {errors}

## Your Task

Determine if this goal is:
1. **ACHIEVED**: Fully completed, all criteria met
2. **PARTIAL**: Some progress, but not complete
3. **FAILED**: Cannot be achieved (tried all alternatives)
4. **BLOCKED**: Waiting on dependencies

## Evaluation Framework

### For Infrastructure Resources

Check:
1. **Existence**: Does resource exist in Azure?
   - Query: `az {resource} show --name {name}`
   - Expected: HTTP 200, JSON with resource details

2. **Status**: Is provisioning complete?
   - Check `provisioningState` field
   - Expected: "Succeeded"

3. **Configuration**: Are properties correct?
   - SKU matches requested
   - Location matches requested
   - Tags applied

4. **Accessibility**: Can resource be reached?
   - Endpoints return valid responses
   - Not blocked by network rules

5. **Integration**: Connected to other resources?
   - Connection strings configured
   - Managed identity assigned
   - Network rules allow traffic

### For Connections

Check:
1. **Source configured**: Source has connection info
2. **Secret stored**: Connection string in Key Vault
3. **Access granted**: Managed identity has permissions
4. **Health check**: Test connection succeeds (optional)

### Confidence Scoring

Assign confidence 0.0 - 1.0:
- **1.0**: All criteria verified programmatically
- **0.8**: Most criteria verified, some assumptions
- **0.6**: Basic existence check, detailed verification pending
- **0.4**: Partial evidence, may need manual verification
- **0.2**: Uncertain, conflicting signals
- **0.0**: Clear failure

## Output Format

```json
{
  "goal_id": "goal-003",
  "status": "ACHIEVED",
  "confidence": 0.95,
  "evaluation": {
    "criteria_met": [
      "Resource exists in Azure",
      "Provisioning state is Succeeded",
      "Primary endpoint accessible",
      "Managed identity configured"
    ],
    "criteria_failed": [],
    "evidence": {
      "existence": {
        "verified": true,
        "method": "az_cli",
        "command": "az webapp show --name app-myservice",
        "result": "Resource found"
      },
      "status": {
        "verified": true,
        "provisioning_state": "Succeeded",
        "runtime_state": "Running"
      },
      "accessibility": {
        "verified": true,
        "endpoint": "https://app-myservice.azurewebsites.net",
        "http_status": 200
      }
    }
  },
  "next_steps": [],
  "teaching_notes": "Successfully deployed App Service with managed identity. The app is running and accessible at its default hostname. Next, we'll configure the connection to Cosmos DB."
}
```

## If Goal Failed

```json
{
  "goal_id": "goal-005",
  "status": "FAILED",
  "confidence": 1.0,
  "evaluation": {
    "criteria_met": [],
    "criteria_failed": [
      "Resource creation failed",
      "Quota limit reached",
      "No alternative approach available"
    ],
    "evidence": {
      "attempts": [
        {
          "approach": "Standard SKU in eastus",
          "result": "QuotaExceeded",
          "error": "Subscription quota exhausted for Standard App Service Plans in eastus"
        },
        {
          "approach": "Standard SKU in westus",
          "result": "QuotaExceeded",
          "error": "Subscription quota exhausted for Standard App Service Plans in westus"
        },
        {
          "approach": "Basic SKU in eastus",
          "result": "QuotaExceeded",
          "error": "All App Service quota exhausted"
        }
      ]
    }
  },
  "next_steps": [
    "Contact Azure support to increase quota",
    "Or use existing App Service Plan"
  ],
  "teaching_notes": "Failed to deploy App Service due to subscription quota limits. This is a common issue in development subscriptions. Solutions: 1) Request quota increase via Azure Portal, 2) Clean up unused resources, 3) Use different subscription."
}
```

## If Blocked

```json
{
  "goal_id": "goal-007",
  "status": "BLOCKED",
  "confidence": 1.0,
  "evaluation": {
    "blocking_goals": ["goal-003", "goal-004"],
    "reason": "Connection requires both App Service and Cosmos DB to be deployed",
    "evidence": {
      "goal-003": "App Service still provisioning",
      "goal-004": "Cosmos DB deployment succeeded"
    }
  },
  "next_steps": ["Wait for goal-003 to complete"],
  "teaching_notes": "This connection goal is waiting for the App Service deployment to finish. This is normal - connections must wait for both endpoints to exist."
}
```

## Teaching Notes

Always include teaching notes that:
- Explain what was checked
- Why certain criteria matter
- What could go wrong
- How to verify manually
- Links to Azure documentation
