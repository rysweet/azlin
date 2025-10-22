# azdoit Enhancement - API Contracts & Architecture

This directory contains the complete API contracts and architecture documentation for the azdoit enhancement to azlin's PR #156.

## Documents Overview

### 1. [API_CONTRACTS_AZDOIT.md](API_CONTRACTS_AZDOIT.md)
**Complete API specifications for all modules**

Defines the "studs" (interfaces) that modules connect through:
- Strategy system with 4 implementation strategies
- State management with JSON persistence
- Cost estimation with Azure Pricing API
- Recovery agent with MS Learn integration
- Terraform generator and MCP client
- Full type signatures, error hierarchy, and test contracts

**Use this to:** Understand what each module does and how they connect.

### 2. [AZDOIT_ARCHITECTURE.md](AZDOIT_ARCHITECTURE.md)
**Visual architecture and data flow diagrams**

Shows how the system works end-to-end:
- System overview diagrams
- Module interaction flows
- Strategy execution details
- State persistence and configuration
- Error handling and recovery flows

**Use this to:** See the big picture and understand data flow.

### 3. [AZDOIT_IMPLEMENTATION_GUIDE.md](AZDOIT_IMPLEMENTATION_GUIDE.md)
**Step-by-step implementation guidance**

Practical guide for building the system:
- Implementation order (5-week plan)
- Code examples with best practices
- Testing strategies and patterns
- Common pitfalls and solutions
- Security considerations
- Performance tips

**Use this to:** Actually build the modules.

## Quick Start

### For Reviewers

1. **Start with:** [API_CONTRACTS_AZDOIT.md](API_CONTRACTS_AZDOIT.md)
   - Review module interfaces
   - Check error hierarchy
   - Verify JSON schemas

2. **Then read:** [AZDOIT_ARCHITECTURE.md](AZDOIT_ARCHITECTURE.md)
   - Understand system flow
   - Review integration points
   - Check for issues

3. **Provide feedback on:**
   - Interface clarity
   - Missing functionality
   - Better abstractions
   - Simplification opportunities

### For Implementers

1. **Start with:** [AZDOIT_IMPLEMENTATION_GUIDE.md](AZDOIT_IMPLEMENTATION_GUIDE.md)
   - Follow implementation order
   - Use code templates
   - Write tests first

2. **Reference:** [API_CONTRACTS_AZDOIT.md](API_CONTRACTS_AZDOIT.md)
   - Copy interface definitions
   - Implement required methods
   - Follow type signatures

3. **Check:** [AZDOIT_ARCHITECTURE.md](AZDOIT_ARCHITECTURE.md)
   - Verify integration points
   - Ensure data flow is correct
   - Test end-to-end scenarios

## Key Principles

### Bricks & Studs Philosophy

**Bricks (Modules):**
- Self-contained with clear boundaries
- Single responsibility
- No circular dependencies
- Independently testable

**Studs (Interfaces):**
- Stable public APIs
- Full type hints
- Clear contracts
- Observable results

### Design Goals

1. **Minimal** - Every module must justify its existence
2. **Clear** - Obvious what each module does
3. **Testable** - Easy to write unit and integration tests
4. **Regeneratable** - Can rebuild any module from contracts
5. **Observable** - Returns structured results, no hidden state

## Module Summary

### Core Modules (11 new files)

1. **strategy_selector.py** - Choose optimal execution strategy
2. **objective_state.py** - Persist objectives to JSON
3. **cost_estimator.py** - Estimate Azure resource costs
4. **recovery_agent.py** - Research and retry failures
5. **terraform_generator.py** - Generate Terraform HCL
6. **mcp_client.py** - Azure MCP Server client
7. **mslearn_client.py** - MS Learn documentation search
8. **strategies/base.py** - Strategy interface
9. **strategies/azure_cli.py** - Azure CLI strategy
10. **strategies/terraform.py** - Terraform strategy
11. **strategies/mcp_server.py** - MCP Server strategy
12. **strategies/custom_code.py** - Python code gen strategy

Plus:
- **errors.py** - Exception hierarchy
- **config.py** - Configuration management

### Integration Points

- **Existing:** IntentParser, CommandExecutor
- **New:** Strategy system, state management, cost estimation, recovery

### JSON Schemas

- **Objective State** - Persistent execution state
- **Configuration** - User preferences and settings

## Implementation Status

- [x] API contracts defined
- [x] Architecture documented
- [x] Implementation guide created
- [ ] Error hierarchy implemented
- [ ] Base strategy interface implemented
- [ ] Objective state manager implemented
- [ ] Azure CLI strategy implemented
- [ ] Strategy selector implemented
- [ ] Terraform strategy implemented
- [ ] Supporting services implemented
- [ ] Advanced strategies implemented
- [ ] CLI integration completed
- [ ] Tests written
- [ ] Documentation updated

## Example Usage

### Basic Flow

```python
from azlin.agentic import handle_do_command

# User runs: azlin do "create 3 VMs called test-{1,2,3}"

result = handle_do_command(
    "create 3 VMs called test-{1,2,3}",
    resource_group="my-rg",
    cost_limit=50.0,
    prefer_terraform=True
)

if result.success:
    print(f"Created {len(result.resources_created)} resources")
    print(f"Total cost: ${result.cost_estimate:.2f}")
else:
    print(f"Failed: {result.error}")
```

### Strategy Selection

```python
from azlin.agentic.strategy_selector import StrategySelector
from azlin.agentic.strategies.base import ExecutionContext

# Create context
context = ExecutionContext(
    intent={"intent": "provision_vm", ...},
    parameters={"vm_name": "test", "count": 3},
    resource_group="my-rg",
    cost_limit=50.0
)

# Select strategy
selector = StrategySelector()
strategy = selector.select(context, preferences={"prefer_terraform": True})

# Execute
result = strategy.execute(context)
```

### State Management

```python
from azlin.agentic.objective_state import ObjectiveStateManager

# Create objective
manager = ObjectiveStateManager()
objective = manager.create_objective(
    user_request="create 3 VMs",
    intent={...},
    parameters={...}
)

# Update with result
manager.update_objective(
    objective.objective_id,
    status="completed",
    result=execution_result
)

# List all objectives
objectives = manager.list_objectives(status="completed")
```

### Recovery Flow

```python
from azlin.agentic.recovery_agent import RecoveryAgent

# Execution failed
if not result.success:
    recovery = RecoveryAgent()

    # Analyze failure and create recovery plan
    plan = recovery.analyze_failure(context, result)

    if plan.strategy == "retry":
        # Attempt recovery
        recovered = recovery.attempt_recovery(context, result, max_attempts=3)

        if recovered and recovered.success:
            print("Recovery succeeded!")
```

## Testing Strategy

### Unit Tests

Each module has comprehensive unit tests:

```bash
pytest tests/unit/test_strategy_selector.py -v
pytest tests/unit/test_objective_state.py -v
pytest tests/unit/strategies/ -v
```

### Integration Tests

End-to-end scenarios:

```bash
pytest tests/integration/test_end_to_end.py -v
pytest tests/integration/test_recovery_flow.py -v
```

### Coverage Goals

- Unit tests: >80% coverage per module
- Integration tests: All critical paths
- Error scenarios: All exception types

## Configuration

### User Configuration File

`~/.azlin/azdoit/config.json`:

```json
{
  "strategy_preferences": {
    "prefer_terraform": false,
    "max_cost": 100.0
  },
  "cost_estimation": {
    "enabled": true,
    "confirmation_threshold": 10.0
  },
  "recovery": {
    "enabled": true,
    "max_attempts": 3
  },
  "mcp_server": {
    "enabled": false,
    "url": "https://azure-mcp.azurewebsites.net"
  }
}
```

### State Directory

`~/.azlin/azdoit/state/`:
- Contains JSON files for each objective
- One file per objective: `{uuid}.json`
- Automatic cleanup of old objectives

## CLI Commands

### Enhanced `azlin do` Command

```bash
# Basic usage
azlin do "create a VM called test"

# With strategy preference
azlin do "create 3 VMs" --prefer-terraform

# With cost limit
azlin do "provision fleet" --cost-limit 50

# Dry run
azlin do "delete all VMs" --dry-run

# Disable recovery
azlin do "create VM" --no-recovery

# View objectives
azlin do list
azlin do show --objective-id {uuid}
```

## Dependencies

### New Dependencies

- `anthropic>=0.40.0` - Already in PR #156
- No additional dependencies needed for core functionality

### Optional Dependencies

- `hcl2` - For Terraform HCL parsing (if needed)
- `requests` - For MCP Server client (standard library alternative: `urllib`)

## Performance

### Expected Performance

- Intent parsing: <2 seconds
- Strategy selection: <100ms
- Azure CLI execution: 30-300 seconds (depends on operation)
- Terraform execution: 60-600 seconds (depends on complexity)
- State persistence: <10ms

### Optimization Opportunities

- Cache pricing data (reduce API calls)
- Parallel strategy scoring (if multiple strategies viable)
- Lazy load strategies (only load when needed)
- Background state cleanup (don't block user)

## Security

### Considerations

1. **Command Injection** - Use list args, not shell=True
2. **API Key Exposure** - Never log full keys
3. **Path Traversal** - Validate file paths
4. **Cost Limits** - Respect user-defined limits
5. **Resource Cleanup** - Always rollback on failure

### Best Practices

- Validate all user inputs
- Use subprocess safely
- Sanitize file paths
- Respect cost constraints
- Clean up temporary files

## Troubleshooting

### Common Issues

**Strategy not selected:**
- Check `can_handle()` implementation
- Verify intent type matches
- Check cost limits

**State file corrupted:**
- Delete file from `~/.azlin/azdoit/state/`
- Run cleanup: `azlin do cleanup`

**Cost estimation fails:**
- Check network connectivity
- Verify Azure Pricing API access
- Use fallback estimates

**Recovery fails:**
- Check error message
- Verify MS Learn API access
- Try manual recovery

## Contributing

When adding new features:

1. **Design API contract first** - Update contracts document
2. **Update architecture** - Add to architecture diagram
3. **Write tests** - Before implementation
4. **Implement module** - Follow implementation guide
5. **Update documentation** - Keep docs in sync

## Philosophy Alignment

This design follows azlin's core philosophy:

- **Ruthless Simplicity** - Every module justified
- **Bricks & Studs** - Clear interfaces, isolated modules
- **Zero-BS** - No stubs, no TODOs, real implementations
- **Quality over Speed** - Well-tested, robust code
- **Regeneratable** - Can rebuild from contracts

## Next Steps

1. **Review contracts** - Provide feedback on APIs
2. **Approve architecture** - Verify design is sound
3. **Begin implementation** - Follow 5-week plan
4. **Iterate** - Improve based on real usage
5. **Document learnings** - Update guides with insights

## Questions?

For questions about:

- **Contracts** - See [API_CONTRACTS_AZDOIT.md](API_CONTRACTS_AZDOIT.md)
- **Architecture** - See [AZDOIT_ARCHITECTURE.md](AZDOIT_ARCHITECTURE.md)
- **Implementation** - See [AZDOIT_IMPLEMENTATION_GUIDE.md](AZDOIT_IMPLEMENTATION_GUIDE.md)

Or open an issue for clarification.

---

**Design Status:** ✅ Complete and ready for review

**Implementation Status:** 🚧 Pending approval

**Integration Status:** ⏳ Awaiting implementation
