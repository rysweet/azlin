# azdoit Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User Interface (CLI)                         │
│                     azlin do "create 3 VMs..."                      │
└────────────────────────────────┬────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Intent Parser (Existing)                      │
│  - Natural language → Structured intent                             │
│  - Context-aware parsing                                            │
│  - Confidence scoring                                               │
└────────────────────────────────┬────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Objective State Manager (NEW)                    │
│  - Create objective record                                          │
│  - Persist to JSON                                                  │
│  - Track execution history                                          │
└────────────────────────────────┬────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Strategy Selector (NEW)                         │
│  - Score all strategies                                             │
│  - Apply cost constraints                                           │
│  - Select optimal strategy                                          │
└───┬─────────────┬─────────────┬─────────────┬──────────────────────┘
    │             │             │             │
    ▼             ▼             ▼             ▼
┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐
│ Azure   │  │Terraform│  │   MCP   │  │ Custom  │
│  CLI    │  │Strategy │  │ Server  │  │  Code   │
│Strategy │  │         │  │Strategy │  │Strategy │
└────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘
     │            │            │            │
     └────────────┴────────────┴────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Execution Result Handler                         │
│  - Validate results                                                 │
│  - Update objective state                                           │
│  - Extract resource IDs                                             │
└────────────────────────────────┬────────────────────────────────────┘
                                  │
                          ┌───────┴────────┐
                          │  Success?      │
                          └───────┬────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                   NO                          YES
                    │                           │
                    ▼                           ▼
          ┌──────────────────┐      ┌──────────────────┐
          │ Recovery Agent   │      │ Return Success   │
          │ - Analyze error  │      │ - Show resources │
          │ - Search docs    │      │ - Display cost   │
          │ - Retry/modify   │      └──────────────────┘
          └──────────────────┘
```

## Module Interactions

### 1. Intent Parsing Flow

```
User Request
     │
     ▼
┌──────────────────┐
│ IntentParser     │──→ Claude API
│ - Parse NL       │
│ - Extract params │
└────────┬─────────┘
         │
         ▼
    Intent Dict
  {
    "intent": "provision_vm",
    "parameters": {...},
    "confidence": 0.95,
    "azlin_commands": [...]
  }
```

### 2. Strategy Selection Flow

```
Intent + Context
       │
       ▼
┌──────────────────────┐
│ Strategy Selector    │
│ 1. Score strategies  │◄──┐
│ 2. Check cost limits │   │
│ 3. Apply preferences │   │
└──────────┬───────────┘   │
           │               │
           ▼               │
    All Strategies         │
           │               │
     ┌─────┴─────┐         │
     │           │         │
     ▼           ▼         │
┌─────────┐ ┌─────────┐   │
│can_handle│ │estimate │   │
│  () ?   │ │ _cost() │───┘
└─────────┘ └─────────┘
     │
     ▼
Selected Strategy
```

### 3. Strategy Execution Flow

```
ExecutionContext
       │
       ▼
┌────────────────────┐
│ Strategy.execute() │
│                    │
│ ┌────────────────┐ │
│ │ 1. Prepare     │ │
│ │ 2. Execute     │ │
│ │ 3. Validate    │ │
│ │ 4. Extract     │ │
│ └────────────────┘ │
└──────────┬─────────┘
           │
           ▼
   ExecutionResult
   {
     "success": true,
     "resources_created": [...],
     "cost_estimate": 12.50,
     "outputs": {...}
   }
```

### 4. Recovery Flow

```
Failed Result
      │
      ▼
┌──────────────────────┐
│ RecoveryAgent        │
│ 1. Analyze error     │──→ Claude API
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ MSLearnClient        │
│ 2. Search docs       │──→ MS Learn API
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Generate plan        │──→ Claude API
│ - Retry?             │
│ - Modify params?     │
│ - Change strategy?   │
│ - Escalate?          │
└──────────┬───────────┘
           │
           ▼
    Recovery Plan
           │
      ┌────┴────┐
      │ Retry   │
      └────┬────┘
           │
           ▼
   Execute with
  modified context
```

## Data Flow

### State Persistence

```
┌─────────────────────────────────────────────────────────┐
│            ~/.azlin/azdoit/state/                       │
│                                                         │
│  ┌────────────────────────────────────────────────┐    │
│  │ {uuid}.json                                    │    │
│  │ {                                              │    │
│  │   "objective_id": "...",                       │    │
│  │   "user_request": "create 3 VMs",              │    │
│  │   "intent": {...},                             │    │
│  │   "status": "completed",                       │    │
│  │   "selected_strategy": "terraform",            │    │
│  │   "execution_results": [                       │    │
│  │     {                                          │    │
│  │       "success": true,                         │    │
│  │       "resources_created": [...],              │    │
│  │       "cost_estimate": 36.50                   │    │
│  │     }                                          │    │
│  │   ],                                           │    │
│  │   "total_cost": 36.50,                         │    │
│  │   "created_at": "2025-10-20T...",              │    │
│  │   "updated_at": "2025-10-20T..."               │    │
│  │ }                                              │    │
│  └────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### Configuration

```
┌─────────────────────────────────────────────────────────┐
│            ~/.azlin/azdoit/config.json                  │
│                                                         │
│  {                                                      │
│    "strategy_preferences": {                           │
│      "prefer_terraform": false,                        │
│      "max_cost": 100.0                                 │
│    },                                                  │
│    "cost_estimation": {                                │
│      "enabled": true,                                  │
│      "confirmation_threshold": 10.0                    │
│    },                                                  │
│    "recovery": {                                       │
│      "enabled": true,                                  │
│      "max_attempts": 3                                 │
│    },                                                  │
│    "mcp_server": {                                     │
│      "enabled": false,                                 │
│      "url": "https://..."                              │
│    }                                                   │
│  }                                                     │
└─────────────────────────────────────────────────────────┘
```

## Strategy Details

### Azure CLI Strategy

```
Intent → Generate CLI Commands → Execute → Parse Output

Example:
  provision_vm
       │
       ▼
  [
    "az group create --name rg-vm1 --location eastus",
    "az vm create --name vm1 --resource-group rg-vm1 ..."
  ]
       │
       ▼
  subprocess.run(...)
       │
       ▼
  Parse JSON output
       │
       ▼
  Extract resource IDs
```

### Terraform Strategy

```
Intent → Generate HCL → Init → Plan → Apply → Extract State

Example:
  provision_vm
       │
       ▼
  main.tf
  ┌────────────────────────┐
  │ resource "azurerm_vm" {│
  │   name = "vm1"         │
  │   ...                  │
  │ }                      │
  └────────────────────────┘
       │
       ▼
  terraform init
       │
       ▼
  terraform plan
       │
       ▼
  terraform apply -auto-approve
       │
       ▼
  terraform show -json
       │
       ▼
  Extract resource IDs from state
```

### MCP Server Strategy

```
Intent → MCP API Call → Await Response → Extract Resources

Example:
  provision_vm
       │
       ▼
  POST /execute
  {
    "operation": "provision_vm",
    "parameters": {...}
  }
       │
       ▼
  MCP Server handles:
  - Resource creation
  - Validation
  - Best practices
       │
       ▼
  Response:
  {
    "success": true,
    "resources": [...],
    "cost": 12.50
  }
```

### Custom Code Strategy

```
Intent → Generate Python → Execute → Capture Output

Example:
  complex_operation
       │
       ▼
  Claude generates:
  ┌────────────────────────┐
  │ from azure.identity... │
  │                        │
  │ def provision_vms():   │
  │   client = ...         │
  │   for i in range(3):   │
  │     client.create(...) │
  └────────────────────────┘
       │
       ▼
  exec() in isolated env
       │
       ▼
  Capture stdout/resources
```

## Cost Estimation Integration

```
Before Execution:

User Request
     │
     ▼
Parse Intent
     │
     ▼
┌─────────────────────┐
│ CostEstimator       │
│ - Query pricing API │
│ - Calculate total   │
└──────────┬──────────┘
           │
           ▼
    Estimated Cost
           │
    ┌──────┴───────┐
    │ > threshold? │
    └──────┬───────┘
           │
      ┌────┴────┐
      NO       YES
      │         │
      │         ▼
      │    ┌────────────────┐
      │    │ Ask user:      │
      │    │ "Cost: $25.50" │
      │    │ "Continue?"    │
      │    └────────────────┘
      │
      ▼
  Proceed with execution
```

## Module Dependencies

```
┌─────────────────────────────────────────────────────────┐
│                     External APIs                       │
│  - Anthropic Claude API                                 │
│  - Azure Pricing API                                    │
│  - MS Learn API                                         │
│  - Azure MCP Server                                     │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    Core Services                        │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐        │
│  │   Intent   │  │  Strategy  │  │   State    │        │
│  │   Parser   │  │  Selector  │  │  Manager   │        │
│  └────────────┘  └────────────┘  └────────────┘        │
│                                                         │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐        │
│  │    Cost    │  │  Recovery  │  │  MS Learn  │        │
│  │ Estimator  │  │   Agent    │  │   Client   │        │
│  └────────────┘  └────────────┘  └────────────┘        │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   Strategy Layer                        │
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐        │
│  │ Azure  │  │Terraform│  │  MCP   │  │Custom  │        │
│  │  CLI   │  │        │  │ Server │  │  Code  │        │
│  └────────┘  └────────┘  └────────┘  └────────┘        │
│                                                         │
│  ┌────────────┐  ┌────────────┐                        │
│  │ Terraform  │  │    MCP     │                        │
│  │ Generator  │  │   Client   │                        │
│  └────────────┘  └────────────┘                        │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   Azure Resources                       │
│  - Virtual Machines                                     │
│  - Storage Accounts                                     │
│  - Networking                                           │
│  - ...                                                  │
└─────────────────────────────────────────────────────────┘
```

## Error Handling Flow

```
┌─────────────────┐
│ Execute Strategy│
└────────┬────────┘
         │
    ┌────┴────┐
    │ Success?│
    └────┬────┘
         │
    ┌────┴────┐
    NO       YES
    │         │
    │         ▼
    │    ┌────────────┐
    │    │ Validate   │
    │    └──────┬─────┘
    │           │
    │      ┌────┴────┐
    │      │ Valid?  │
    │      └────┬────┘
    │           │
    │      ┌────┴────┐
    │      NO       YES
    │      │         │
    ▼      ▼         ▼
┌──────────────┐  ┌──────────────┐
│ Rollback     │  │ Return       │
│ - Delete res │  │ Success      │
└──────┬───────┘  └──────────────┘
       │
       ▼
┌──────────────┐
│ Recovery?    │
│ enabled      │
└──────┬───────┘
       │
  ┌────┴────┐
  NO       YES
  │         │
  │         ▼
  │    ┌──────────────┐
  │    │ Recovery     │
  │    │ Agent        │
  │    │ - Analyze    │
  │    │ - Research   │
  │    │ - Retry      │
  │    └──────┬───────┘
  │           │
  │      ┌────┴────┐
  │      │Success? │
  │      └────┬────┘
  │           │
  │      ┌────┴────┐
  │      NO       YES
  │      │         │
  ▼      ▼         ▼
┌──────────────┐  ┌──────────────┐
│ Return       │  │ Return       │
│ Failure      │  │ Success      │
└──────────────┘  └──────────────┘
```

## CLI Integration

```
┌─────────────────────────────────────────────────────────┐
│ azlin do "create 3 VMs called test-{1,2,3}"            │
│          --dry-run                                      │
│          --cost-limit 50                                │
│          --prefer-terraform                             │
│          --resource-group my-rg                         │
│          --verbose                                      │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│ CLI Handler (cli.py)                                   │
│ - Parse arguments                                       │
│ - Load config                                           │
│ - Setup logging                                         │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│ Orchestrator (new in cli.py or separate module)       │
│ 1. Parse intent                                         │
│ 2. Create objective                                     │
│ 3. Estimate cost                                        │
│ 4. Confirm with user (if needed)                        │
│ 5. Select strategy                                      │
│ 6. Execute                                              │
│ 7. Handle errors/recovery                               │
│ 8. Update state                                         │
│ 9. Display results                                      │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│ Output                                                  │
│                                                         │
│ ✓ Intent: provision_vm (confidence: 0.95)              │
│ ✓ Strategy: terraform                                  │
│ ✓ Estimated cost: $36.50                               │
│ ✓ Created 3 VMs:                                       │
│   - test-1 (Standard_D2s_v3)                           │
│   - test-2 (Standard_D2s_v3)                           │
│   - test-3 (Standard_D2s_v3)                           │
│                                                         │
│ Objective ID: 7f3d8a1b-4e2c-...                        │
│ View state: azlin do list --objective-id <id>          │
└─────────────────────────────────────────────────────────┘
```

## Extensibility

### Adding a New Strategy

```python
# 1. Create strategy implementation
from .base import ExecutionStrategy, StrategyType, ExecutionContext, ExecutionResult

class MyNewStrategy(ExecutionStrategy):
    def can_handle(self, context: ExecutionContext) -> bool:
        # Define when to use this strategy
        return context.intent.get("intent") == "my_operation"

    def estimate_cost(self, context: ExecutionContext) -> float:
        # Cost estimation logic
        return 0.0

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        # Execution logic
        pass

    def validate(self, result: ExecutionResult) -> bool:
        # Validation logic
        pass

    def rollback(self, result: ExecutionResult) -> bool:
        # Rollback logic
        pass

# 2. Register in strategy selector
# In strategy_selector.py _load_strategies():
return {
    StrategyType.AZURE_CLI: AzureCLIStrategy(),
    StrategyType.TERRAFORM: TerraformStrategy(),
    StrategyType.MCP_SERVER: MCPServerStrategy(),
    StrategyType.CUSTOM_CODE: CustomCodeStrategy(),
    StrategyType.MY_NEW: MyNewStrategy(),  # Add here
}
```

That's it! The strategy selector will automatically consider your new strategy.

## Philosophy Alignment

This architecture follows azlin's **bricks & studs** philosophy:

### Bricks (Self-contained modules)
- Each strategy is independent
- State manager is isolated
- Recovery agent is standalone
- Cost estimator is separate

### Studs (Stable interfaces)
- `ExecutionStrategy` interface
- `ExecutionResult` dataclass
- `ObjectiveState` schema
- Public APIs with type hints

### Regeneratable
- Any module can be rebuilt from contracts
- Interfaces remain stable
- Implementation details can change

### Observable
- All operations return structured results
- State is persisted
- Execution history is tracked
- No hidden side effects

### Ruthless Simplicity
- Each module has ONE purpose
- Minimal dependencies between modules
- No premature abstractions
- Clear data flow
