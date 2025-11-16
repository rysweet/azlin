# azlin doit - Autonomous Azure Infrastructure Agent

Complete autonomous goal-seeking agent for Azure infrastructure deployment.

## Overview

`azlin doit` is an AI-powered autonomous agent that:

1. **Parses natural language** infrastructure requests into structured goals
2. **Autonomously executes** deployment using Azure CLI with ReAct loop
3. **Self-evaluates** success after each action and adapts if failures occur
4. **Generates production-ready** Terraform and Bicep configurations
5. **Provides teaching materials** explaining what was done and why

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Request                             │
│    "Give me App Service with Cosmos DB and API Management"  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    Goal Parser                               │
│  • Parse natural language → structured goals                 │
│  • Extract resources, dependencies, constraints              │
│  • Build goal hierarchy with dependency levels               │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                 Execution Engine (ReAct Loop)                │
│                                                              │
│  Iteration 1...N (max 50):                                  │
│    1. REASON: Select next goal to work on                   │
│    2. PLAN: Choose strategy for goal                        │
│    3. ACT: Execute Azure CLI command                        │
│    4. OBSERVE: Collect results, check for errors            │
│    5. EVALUATE: Did it work? (via Goal Evaluator)           │
│    6. ADAPT: If failed, adjust and retry                    │
│                                                              │
│  Continue until all goals achieved or max iterations         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  Artifact Generator                          │
│  • Terraform configuration (main.tf)                         │
│  • Bicep configuration (main.bicep)                          │
│  • Documentation (README.md)                                 │
│  • Teaching materials                                        │
└─────────────────────────────────────────────────────────────┘
```

## Module Structure

```
src/azlin/doit/
├── __init__.py              # Main exports
├── orchestrator.py          # DoItOrchestrator - main entry point
├── goals/                   # Goal parsing and models
│   ├── __init__.py
│   ├── models.py            # Goal, GoalHierarchy, ResourceType
│   └── parser.py            # GoalParser - NL → goals
├── engine/                  # Execution engine
│   ├── __init__.py
│   ├── models.py            # ExecutionState, Action, ActionResult
│   └── executor.py          # ExecutionEngine - ReAct loop
├── evaluator/               # Goal evaluation
│   ├── __init__.py
│   └── evaluator.py         # GoalEvaluator - success checking
├── reporter/                # Progress reporting
│   ├── __init__.py
│   └── reporter.py          # ProgressReporter - user updates
├── strategies/              # Deployment strategies
│   ├── __init__.py
│   ├── base.py              # Strategy base class
│   ├── resource_group.py    # Resource group strategy
│   ├── storage.py           # Storage account strategy
│   ├── keyvault.py          # Key Vault strategy
│   ├── cosmos_db.py         # Cosmos DB strategy
│   ├── app_service.py       # App Service strategy
│   ├── api_management.py    # API Management strategy
│   └── connection.py        # Connection strategy
├── artifacts/               # Artifact generation
│   ├── __init__.py
│   └── generator.py         # Terraform/Bicep/README
├── mcp/                     # MCP integration (future)
│   ├── __init__.py
│   └── client.py            # Azure MCP client
└── README.md                # This file

src/azlin/prompts/doit/      # Separated prompts
├── system_prompt.md         # Agent system prompt
├── goal_parser.md           # Goal parsing prompt
├── strategy_selection.md    # Strategy selection prompt
├── execution_plan.md        # Execution planning prompt
├── action_execution.md      # Action execution prompt
├── goal_evaluation.md       # Goal evaluation prompt
├── progress_report.md       # Progress reporting prompt
├── terraform_generation.md  # Terraform generation prompt
├── bicep_generation.md      # Bicep generation prompt
├── failure_recovery.md      # Failure recovery prompt
└── teaching_notes.md        # Teaching notes generation
```

## Usage

### Basic Usage

```bash
# Deploy infrastructure from natural language
azlin doit deploy "Give me App Service with Cosmos DB"

# More complex example
azlin doit deploy "Create App Service, Cosmos DB, API Management, Storage, and KeyVault all connected"

# Specify region
azlin doit deploy "Deploy web app with database in westus"

# Dry run (show what would be deployed)
azlin doit deploy "Give me App Service with Cosmos DB" --dry-run

# Custom output directory
azlin doit deploy "Create storage and Key Vault" --output-dir ./my-infra
```

### Example Requests

```bash
# Simple web app + database
azlin doit deploy "Give me App Service with Cosmos DB"

# Complete API platform
azlin doit deploy "Create App Service, Cosmos DB, API Management, Storage, and KeyVault all connected"

# Microservices
azlin doit deploy "Deploy 3 App Services behind API Management with shared Cosmos DB"

# Serverless
azlin doit deploy "Create Function App with Storage Account and Key Vault"

# Regional
azlin doit deploy "Give me App Service with Cosmos DB in westus"
```

### View Examples

```bash
azlin doit examples
```

## How It Works

### 1. Goal Parsing

The `GoalParser` converts natural language to structured goals:

**Input**: "Give me App Service with Cosmos DB"

**Output**:
```python
GoalHierarchy(
    primary_goal="Deploy Azure infrastructure: Give me App Service with Cosmos DB",
    goals=[
        Goal(id="goal-001", type=RESOURCE_GROUP, level=0),
        Goal(id="goal-002", type=KEY_VAULT, level=1),
        Goal(id="goal-003", type=COSMOS_DB, level=1),
        Goal(id="goal-004", type=APP_SERVICE_PLAN, level=2),
        Goal(id="goal-005", type=APP_SERVICE, level=2),
        Goal(id="goal-006", type=CONNECTION, level=3),
    ]
)
```

### 2. Execution Loop (ReAct)

The `ExecutionEngine` uses a ReAct (Reason + Act) loop:

```python
while not complete and iterations < max:
    # REASON: Select next goal
    goal = select_next_goal(hierarchy)

    # PLAN: Choose strategy
    strategy = get_strategy(goal.type)
    action = strategy.build_command(goal)

    # ACT: Execute command
    result = execute_az_cli(action.command)

    # OBSERVE: Check result
    if result.success:
        goal.mark_completed(result.outputs)
    else:
        # ADAPT: Plan recovery
        if recoverable:
            adjust_parameters(goal)
            retry()
        else:
            goal.mark_failed(result.error)
```

### 3. Self-Evaluation

The `GoalEvaluator` checks if goals are truly achieved:

```python
# For each completed action
evaluation = evaluator.evaluate(goal, action_results)

# Checks:
# - Resource exists in Azure
# - Provisioning state is "Succeeded"
# - Endpoints are accessible
# - Configuration is correct
# - Connections work

# Returns confidence score (0.0 - 1.0)
```

### 4. Failure Recovery

When actions fail, the agent adapts:

```python
if error == "name already exists":
    # Try with numeric suffix
    goal.name = f"{goal.name}2"
    retry()

elif error == "quota exceeded":
    # Try different region
    goal.parameters["location"] = "westus"
    retry()

elif is_transient_error:
    # Wait and retry
    sleep(30)
    retry()

else:
    # Mark as failed, continue with other goals
    goal.mark_failed(error)
```

### 5. Artifact Generation

After deployment, generates:

- **main.tf**: Complete Terraform configuration
- **variables.tf**: Configurable parameters
- **outputs.tf**: Output values
- **main.bicep**: Bicep configuration
- **README.md**: Deployment guide with architecture diagrams, cost estimates, troubleshooting

## Key Features

### Autonomous Goal-Seeking

- No manual intervention required
- Automatically determines dependencies
- Self-evaluates success
- Adapts to failures

### Separated Prompts

All AI prompts are in separate `.md` files in `src/azlin/prompts/doit/`:

- Easy to iterate and improve
- Version controlled
- Maintainable
- Testable

### Production-Ready Infrastructure as Code

Generated Terraform/Bicep includes:

- Best practices (HTTPS, RBAC, managed identities)
- Security hardening
- Proper dependencies
- Reusable modules
- Documentation

### Teaching Mode

Explains:

- What was deployed and why
- How resources connect
- Security decisions made
- Cost implications
- Troubleshooting tips
- Links to Azure documentation

### Failure Handling

- Retries transient errors
- Adjusts parameters for recoverable errors
- Tries alternative approaches
- Reports unrecoverable failures
- Continues with other goals

## Configuration

### Output Directory

Default: `~/.azlin/doit/output`

Override:
```bash
azlin doit deploy "..." --output-dir ./my-output
```

### Max Iterations

Default: 50

Override:
```bash
azlin doit deploy "..." --max-iterations 100
```

### Verbosity

Default: verbose

Quiet mode:
```bash
azlin doit deploy "..." --quiet
```

## Implementation Status

### ✅ Completed

- [x] Goal parsing (natural language → structured goals)
- [x] Goal hierarchy with dependency levels
- [x] Execution engine with ReAct loop
- [x] Goal evaluator with confidence scoring
- [x] Progress reporter with rich terminal output
- [x] Strategy library (Resource Group, Storage, Key Vault, Cosmos, App Service, APIM)
- [x] Connection strategy (wire resources together)
- [x] Artifact generator (Terraform, Bicep, README)
- [x] Failure recovery and adaptation
- [x] CLI command integration
- [x] Separated prompt files

### 🚧 Future Enhancements

- [ ] Azure MCP server integration (currently stub)
- [ ] MS Learn integration for Azure knowledge
- [ ] State persistence (session tracking)
- [ ] Resume interrupted deployments
- [ ] Cost estimation before deployment
- [ ] Multi-region deployments
- [ ] More resource types (AKS, Functions, SQL, etc.)
- [ ] LLM-powered goal parsing (currently rule-based)
- [ ] Real-time streaming progress
- [ ] Rollback capability

## Testing

### Unit Tests

```bash
# Run all tests
pytest tests/doit/

# Run specific module tests
pytest tests/doit/test_goals.py
pytest tests/doit/test_engine.py
pytest tests/doit/test_evaluator.py
```

### Integration Tests

```bash
# Test with dry run
azlin doit deploy "Give me App Service" --dry-run

# Test actual deployment (will create resources!)
azlin doit deploy "Create storage account" --output-dir ./test-output
```

## Examples

### Example 1: Simple Web App + Database

**Request**: "Give me App Service with Cosmos DB"

**Deployed Resources**:
- Resource Group
- Key Vault
- Cosmos DB
- App Service Plan
- App Service (with managed identity)
- Connection (App Service → Key Vault → Cosmos DB)

**Generated Files**:
- `main.tf` (143 lines)
- `variables.tf` (35 lines)
- `outputs.tf` (18 lines)
- `main.bicep` (95 lines)
- `README.md` (Complete deployment guide)

**Time**: ~4-6 minutes

### Example 2: Complete API Platform

**Request**: "Create App Service, Cosmos DB, API Management, Storage, and KeyVault all connected"

**Deployed Resources**:
- Resource Group
- Storage Account
- Key Vault
- Cosmos DB
- App Service Plan
- App Service
- API Management
- Connections (all wired together)

**Time**: ~8-10 minutes (APIM takes longest)

## Troubleshooting

### Command Not Found

```bash
# Ensure azlin is installed
pip install -e .

# Or reinstall
pip uninstall azlin && pip install -e .
```

### Azure CLI Not Authenticated

```bash
az login
az account set --subscription <subscription-id>
```

### Deployment Fails

Check generated output:
```bash
cat ~/.azlin/doit/output/README.md
```

View logs:
```bash
# Enable verbose mode
azlin doit deploy "..." --verbose
```

### Name Conflicts

Azure resource names must be globally unique. The agent tries alternative names automatically, but you may need to manually adjust in generated Terraform.

## Contributing

To add a new resource type strategy:

1. Create strategy file: `src/azlin/doit/strategies/my_resource.py`
2. Implement `Strategy` interface:
   - `build_command()` - Azure CLI command
   - `generate_terraform()` - Terraform HCL
   - `generate_bicep()` - Bicep code
3. Register in `src/azlin/doit/strategies/__init__.py`
4. Add resource type to `ResourceType` enum in `goals/models.py`

## License

Same as azlin project.

## Links

- [Azure CLI Documentation](https://learn.microsoft.com/cli/azure/)
- [Terraform Azure Provider](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs)
- [Bicep Documentation](https://learn.microsoft.com/azure/azure-resource-manager/bicep/)
- [azlin GitHub](https://github.com/ruvnet/azlin)
