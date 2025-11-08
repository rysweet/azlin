# Failure Recovery Prompt

Handle failures and adapt strategy when things go wrong.

## Failure Context
Action: {action}
Error: {error}
Attempt: {attempt_number}
Previous attempts: {previous_attempts}

## Your Task

Analyze the failure and determine the best recovery strategy.

## Common Azure Failures

### 1. Name Conflicts
**Error**: Resource name already exists
**Examples**:
- Storage account name taken
- App Service name taken
- Key Vault name taken

**Recovery**:
- Try with numeric suffix: `stwebappprod2`
- Try with uniqueString: `stwebappprod${random}`
- Check if existing resource is ours (can reuse?)

### 2. Quota Limits
**Error**: Quota exceeded
**Examples**:
- CPU quota exhausted
- Too many storage accounts
- Region-specific limits

**Recovery**:
- Try different region
- Try lower SKU
- Clean up unused resources
- Report to user (may need quota increase)

### 3. Permission Errors
**Error**: Authorization failed
**Examples**:
- Insufficient role
- Service Principal lacks permission
- Subscription not found

**Recovery**:
- Check authentication: `az account show`
- Verify permissions: `az role assignment list`
- Suggest required roles to user
- Cannot auto-fix (needs admin)

### 4. Transient Failures
**Error**: Service temporarily unavailable
**Examples**:
- Network timeout
- Service throttling
- Provisioning conflict

**Recovery**:
- Retry with exponential backoff
- Wait 30s, 60s, 120s
- Max 3 retries
- If persistent, switch to alternative

### 5. Configuration Errors
**Error**: Invalid parameter
**Examples**:
- Invalid SKU for region
- Incompatible settings
- Missing required field

**Recovery**:
- Try alternative configuration
- Use default values
- Check Azure region capabilities

## Recovery Decision Tree

```
Error Occurred
│
├─ Is it transient? (timeout, throttle)
│  ├─ Yes: Retry with backoff (max 3 times)
│  └─ No: Continue
│
├─ Is it recoverable? (name conflict, config)
│  ├─ Yes: Adjust parameters and retry
│  └─ No: Continue
│
├─ Is there alternative? (different region, SKU)
│  ├─ Yes: Try alternative
│  └─ No: Continue
│
└─ Cannot recover
   ├─ Mark goal as FAILED
   ├─ Report to user
   └─ Continue with other goals
```

## Output Format

```json
{
  "failure_analysis": {
    "type": "NameConflict",
    "severity": "medium",
    "recoverable": true,
    "transient": false,
    "message": "Storage account name 'stwebappprod' already exists"
  },
  "recovery_strategy": {
    "approach": "adjust_and_retry",
    "adjustments": {
      "name": "stwebappprod2"
    },
    "reasoning": "Name collision is common for storage accounts. Trying with numeric suffix.",
    "alternatives": [
      "Use uniqueString()",
      "Check if existing account is ours",
      "Try different naming pattern"
    ],
    "max_retries": 3,
    "current_attempt": 1
  },
  "user_action_required": false,
  "teaching_notes": "Storage account names must be globally unique across all of Azure. Common solution: add random suffix or date string."
}
```

## If Unrecoverable

```json
{
  "failure_analysis": {
    "type": "QuotaExceeded",
    "severity": "high",
    "recoverable": false,
    "transient": false,
    "message": "Subscription quota exhausted for all App Service SKUs in all regions"
  },
  "recovery_strategy": {
    "approach": "report_and_continue",
    "reasoning": "Tried all available regions and SKUs. Quota increase required.",
    "alternatives": [
      "Request quota increase via Azure Portal",
      "Clean up unused App Service Plans",
      "Use existing App Service Plan"
    ]
  },
  "user_action_required": true,
  "user_instructions": [
    "Go to Azure Portal → Subscriptions → Usage + Quotas",
    "Search for 'App Service'",
    "Request quota increase",
    "Or: Delete unused App Service Plans to free quota"
  ],
  "continue_without": true,
  "impact": "Cannot deploy App Service. Other resources will be deployed successfully.",
  "teaching_notes": "Azure subscriptions have resource quotas to prevent runaway costs. Development subscriptions often have lower limits. Production subscriptions can request increases."
}
```

## Retry Logic

### Exponential Backoff
```python
delays = [30, 60, 120]  # seconds
for attempt, delay in enumerate(delays, 1):
    try:
        execute_action()
        break  # Success
    except TransientError:
        if attempt < len(delays):
            wait(delay)
        else:
            raise  # Give up
```

### Parameter Adjustment
```python
# Name conflict
original = "stwebappprod"
attempts = [
    f"{original}2",
    f"{original}3",
    f"{original}{random_suffix()}",
]

# Region fallback
regions = ["eastus", "westus", "westus2", "centralus"]

# SKU downgrade
skus = ["Standard", "Basic", "Free"]
```

## Learning from Failures

Track failures to avoid repeating:
```json
{
  "learned_constraints": {
    "storage_account_names": {
      "taken": ["stwebappprod", "stwebapp"],
      "successful": "stwebappprod3"
    },
    "quota_limits": {
      "app_service_standard_eastus": "exhausted",
      "app_service_basic_eastus": "available"
    },
    "region_capabilities": {
      "eastus": ["available"],
      "westus": ["throttled"]
    }
  }
}
```

## Communication

When failures occur:
1. **Acknowledge**: "Encountered issue: {error}"
2. **Explain**: "This happens because..."
3. **Adapt**: "Trying alternative approach..."
4. **Teach**: "This is a common situation..."
5. **Continue**: "Continuing with deployment..."

Don't panic. Failures are normal and expected.
