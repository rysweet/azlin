# azdoit API Contracts - Executive Summary

## Overview

This document provides a high-level summary of the API contracts designed for the azdoit enhancement to azlin PR #156.

**Total Documentation:** 7,761 lines across 7 documents
**Core Contract:** 2,594 lines of detailed API specifications
**Architecture:** 634 lines of visual diagrams and data flows
**Implementation:** 1,060 lines of practical guidance

## What We Designed

### 11 New Modules Following Bricks & Studs Philosophy

```
Strategy System (5 modules)
├── strategy_selector.py      - Choose optimal execution strategy
└── strategies/
    ├── base.py               - Strategy interface (THE STUD)
    ├── azure_cli.py          - Execute via Azure CLI
    ├── terraform.py          - Execute via Terraform
    ├── mcp_server.py         - Execute via MCP Server
    └── custom_code.py        - Generate and execute Python

State & Supporting Services (6 modules)
├── objective_state.py        - Persist objectives to JSON
├── cost_estimator.py         - Estimate Azure costs
├── recovery_agent.py         - Research and retry failures
├── terraform_generator.py    - Generate Terraform HCL
├── mcp_client.py            - Azure MCP Server client
└── mslearn_client.py        - MS Learn documentation search
```

## Key Design Decisions

### 1. Strategy Pattern for Execution

**Problem:** Multiple ways to execute Azure operations (CLI, Terraform, MCP, custom code)

**Solution:** Strategy pattern with unified interface

```python
class ExecutionStrategy(ABC):
    def can_handle(context) -> bool        # Can this strategy execute the intent?
    def estimate_cost(context) -> float    # What will it cost?
    def execute(context) -> ExecutionResult  # Do it
    def validate(result) -> bool           # Did it work?
    def rollback(result) -> bool           # Clean up if failed
```

**Benefits:**
- Add new strategies without changing existing code
- Test strategies independently
- Select optimal strategy automatically
- Consistent error handling

### 2. JSON-Based State Persistence

**Problem:** Need to track objectives, execution history, costs

**Solution:** One JSON file per objective in `~/.azlin/azdoit/state/`

```json
{
  "objective_id": "uuid",
  "user_request": "create 3 VMs",
  "status": "completed",
  "selected_strategy": "terraform",
  "resources_created": [...],
  "total_cost": 36.50
}
```

**Benefits:**
- Human-readable for debugging
- No database dependency
- Easy to backup/restore
- Simple cleanup of old objectives

### 3. Cost Estimation Before Execution

**Problem:** Users need to know cost before creating resources

**Solution:** CostEstimator with Azure Pricing API integration

```python
estimator = AzureCostEstimator()
cost = estimator.estimate_intent(intent, parameters)

if cost > user_limit:
    confirm = ask_user(f"This will cost ${cost:.2f}. Continue?")
```

**Benefits:**
- Prevent budget overruns
- User control over spending
- Per-strategy cost estimates
- Cost breakdown by resource

### 4. Intelligent Recovery Agent

**Problem:** Failures should be researched and retried intelligently

**Solution:** Recovery agent that analyzes errors, searches docs, generates recovery plans

```python
recovery = RecoveryAgent()
plan = recovery.analyze_failure(context, failed_result)

if plan.strategy == "retry":
    recovered = recovery.attempt_recovery(context, result)
```

**Benefits:**
- Automatic error research
- MS Learn documentation integration
- Intelligent retry strategies
- Reduced manual intervention

## Interface Contracts

### Core Data Structures

**ExecutionContext** (Input to all strategies):
```python
@dataclass
class ExecutionContext:
    intent: Dict[str, Any]          # Parsed intent from IntentParser
    parameters: Dict[str, Any]       # Extracted parameters
    resource_group: Optional[str]    # Target resource group
    dry_run: bool = False           # Preview mode
    verbose: bool = False           # Detailed output
    cost_limit: Optional[float] = None  # Max cost in USD
```

**ExecutionResult** (Output from all strategies):
```python
@dataclass
class ExecutionResult:
    success: bool                    # Did it work?
    strategy: StrategyType          # Which strategy was used
    outputs: Dict[str, Any]         # Strategy-specific outputs
    resources_created: List[str]    # Azure resource IDs
    cost_estimate: Optional[float]  # Estimated cost
    execution_time: float           # Seconds
    error: Optional[str] = None     # Error message if failed
```

### Strategy Interface (The Main Stud)

```python
class ExecutionStrategy(ABC):
    @abstractmethod
    def can_handle(self, context: ExecutionContext) -> bool:
        """Can this strategy execute the intent?"""

    @abstractmethod
    def estimate_cost(self, context: ExecutionContext) -> float:
        """What will it cost?"""

    @abstractmethod
    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute the intent."""

    @abstractmethod
    def validate(self, result: ExecutionResult) -> bool:
        """Did execution succeed?"""

    @abstractmethod
    def rollback(self, result: ExecutionResult) -> bool:
        """Clean up on failure."""
```

## Data Flow

### End-to-End Execution

```
1. User Input
   "create 3 VMs called test-{1,2,3}"

2. Intent Parser (existing)
   → Intent: "provision_vm"
   → Parameters: {"vm_name": "test-*", "count": 3}
   → Confidence: 0.95

3. Objective State Manager (new)
   → Create objective record
   → Persist to ~/.azlin/azdoit/state/{uuid}.json

4. Cost Estimator (new)
   → Estimate: $36.50 for 3 VMs
   → Check against user limit
   → Confirm with user if needed

5. Strategy Selector (new)
   → Score all strategies:
     - Azure CLI: 0.7 (simple, fast)
     - Terraform: 0.9 (best for multi-resource)
     - MCP: 0.6 (not needed)
     - Custom: 0.5 (fallback)
   → Select: Terraform (highest score)

6. Strategy Execution (new)
   → Generate Terraform HCL
   → terraform init, plan, apply
   → Extract resource IDs from state
   → Return ExecutionResult

7. State Update (new)
   → Update objective with result
   → Track resources created
   → Record actual cost

8. Success/Failure Handling
   → If success: Show resources and cost
   → If failure: Attempt recovery

9. Recovery (if needed)
   → Analyze error message
   → Search MS Learn docs
   → Generate recovery plan
   → Retry with modifications
```

## Strategy Selection Logic

### Scoring Algorithm

Each strategy is scored 0.0 to 1.0 based on:

1. **Can Handle** - Does strategy support this operation?
2. **Cost Efficiency** - Lower cost = higher score
3. **User Preferences** - Boost score if user prefers this strategy
4. **Intent Complexity** - Match strategy to complexity
   - Simple operations → Azure CLI
   - Multi-resource → Terraform
   - Managed services → MCP
   - Complex logic → Custom code

### Example Scoring

```
Intent: "provision 5 VMs with shared storage"

Azure CLI:
  - Can handle: Yes (but sequential)
  - Cost: $50 (standard)
  - Preference: None
  - Complexity: Medium (multiple commands)
  → Score: 0.65

Terraform:
  - Can handle: Yes (parallel, idempotent)
  - Cost: $50 (same resources)
  - Preference: None
  - Complexity: High (perfect fit)
  → Score: 0.90 ✓ SELECTED

MCP Server:
  - Can handle: Yes
  - Cost: $50
  - Preference: None
  - Complexity: Abstracted
  → Score: 0.70

Custom Code:
  - Can handle: Yes (fallback)
  - Cost: $50 + API calls
  - Preference: None
  - Complexity: High (overkill)
  → Score: 0.50
```

## Integration with Existing Code

### Minimal Changes to PR #156

The existing `IntentParser` and `CommandExecutor` remain **unchanged**. We add:

```python
# In cli.py or new orchestrator.py

def handle_do_command(user_request: str, **options):
    # 1. Parse intent (existing IntentParser)
    parser = IntentParser()
    intent = parser.parse(user_request)

    # 2. Create objective (new ObjectiveStateManager)
    state_manager = ObjectiveStateManager()
    objective = state_manager.create_objective(user_request, intent, intent["parameters"])

    # 3. Estimate cost (new CostEstimator)
    estimator = AzureCostEstimator()
    cost = estimator.estimate_intent(intent, intent["parameters"])

    # 4. Confirm if needed
    if cost > options.get("cost_limit", float("inf")):
        if not confirm_with_user(f"Cost: ${cost:.2f}. Continue?"):
            return

    # 5. Select strategy (new StrategySelector)
    context = ExecutionContext(
        intent=intent,
        parameters=intent["parameters"],
        **options
    )
    selector = StrategySelector()
    strategy = selector.select(context)

    # 6. Execute (new Strategy)
    result = strategy.execute(context)

    # 7. Update state (new ObjectiveStateManager)
    state_manager.update_objective(objective.objective_id, result=result)

    # 8. Handle failure (new RecoveryAgent)
    if not result.success:
        recovery = RecoveryAgent()
        recovered = recovery.attempt_recovery(context, result)
        if recovered:
            result = recovered

    return result
```

## Configuration

### User Config File

`~/.azlin/azdoit/config.json`:

```json
{
  "strategy_preferences": {
    "prefer_terraform": false,
    "prefer_mcp": false,
    "max_cost": 100.0
  },
  "cost_estimation": {
    "enabled": true,
    "confirmation_threshold": 10.0
  },
  "recovery": {
    "enabled": true,
    "max_attempts": 3,
    "use_mslearn": true
  }
}
```

## Error Handling

### Complete Exception Hierarchy

```python
AzDoItError (base)
├── IntentParseError
├── StrategyError
│   ├── NoStrategyFoundError
│   ├── StrategyExecutionError
│   ├── AzureCLIError
│   ├── TerraformError
│   ├── MCPError
│   └── CodeGenerationError
├── StateError
│   └── ObjectiveNotFoundError
├── CostEstimationError
├── RecoveryError
└── ValidationError
```

All exceptions are **observable** with structured error data.

## Testing Strategy

### Unit Tests (>80% coverage per module)

```python
# Example: test_strategy_selector.py
def test_select_azure_cli_for_simple_vm():
def test_select_terraform_for_fleet():
def test_no_strategy_found_raises_error():
def test_cost_limit_filters_expensive_strategies():
```

### Integration Tests (All critical paths)

```python
# Example: test_end_to_end.py
def test_provision_vm_end_to_end():
def test_recovery_from_quota_error():
def test_cost_estimation_prevents_overrun():
```

## Philosophy Alignment

### Bricks & Studs

✅ **Self-contained modules** - Each can be tested independently
✅ **Stable interfaces** - ExecutionStrategy is the main stud
✅ **Clear boundaries** - No circular dependencies
✅ **Regeneratable** - Can rebuild any module from contracts

### Ruthless Simplicity

✅ **Every module justified** - Each solves a specific problem
✅ **Minimal abstractions** - Only strategy pattern, no over-engineering
✅ **No premature optimization** - Start simple, optimize later
✅ **Observable** - All operations return structured results

### Quality Over Speed

✅ **Full type hints** - Every public method typed
✅ **Comprehensive tests** - Unit and integration coverage
✅ **Real implementations** - No stubs, no TODOs
✅ **Error handling** - Every failure mode considered

## Implementation Timeline

### 5-Week Plan

**Week 1: Foundation**
- Error hierarchy
- Base strategy interface
- Objective state manager

**Week 2: Core Strategies**
- Azure CLI strategy
- Strategy selector
- Terraform strategy

**Week 3: Supporting Services**
- Terraform generator
- Cost estimator
- MCP client
- MS Learn client

**Week 4: Advanced Features**
- MCP Server strategy
- Custom code strategy
- Recovery agent

**Week 5: Integration**
- CLI integration
- Configuration management
- End-to-end testing

## Deliverables

### Documentation (7 files, 7,761 lines)

1. **API_CONTRACTS_AZDOIT.md** (2,594 lines)
   - Complete API specifications
   - Type signatures for all modules
   - JSON schemas for data structures
   - Error hierarchy
   - Test contracts

2. **AZDOIT_ARCHITECTURE.md** (634 lines)
   - System overview diagrams
   - Module interaction flows
   - Data flow diagrams
   - Strategy execution details

3. **AZDOIT_IMPLEMENTATION_GUIDE.md** (1,060 lines)
   - Implementation order
   - Code templates
   - Best practices
   - Common pitfalls
   - Security considerations

4. **AZDOIT_README.md** (443 lines)
   - Quick start guide
   - Module summary
   - Example usage
   - Configuration

Plus existing security documentation:
5. AZDOIT_SECURITY_DESIGN.md (1,200 lines)
6. AZDOIT_SECURITY_IMPLEMENTATION.md (1,465 lines)
7. AZDOIT_SECURITY_SUMMARY.md (365 lines)

### Code Artifacts

- 11 Python modules (estimated 2,500-3,000 LOC)
- 30+ unit test files (estimated 2,000 LOC)
- 10+ integration test files (estimated 1,000 LOC)
- Configuration schemas
- CLI integration

## Success Metrics

### Functionality

- [ ] All 4 strategies implemented and working
- [ ] Strategy selection accurate >90% of time
- [ ] State persistence reliable
- [ ] Cost estimation within 10% of actual
- [ ] Recovery succeeds >50% of retryable failures

### Quality

- [ ] >80% unit test coverage
- [ ] All critical paths integration tested
- [ ] Type checking passes (mypy)
- [ ] Linting passes (ruff)
- [ ] Zero security vulnerabilities

### User Experience

- [ ] Natural language commands work intuitively
- [ ] Cost confirmations prevent overruns
- [ ] Error messages are actionable
- [ ] Recovery is transparent
- [ ] Dry-run mode is accurate

## Next Steps

1. **Review API Contracts**
   - Check interfaces are clear
   - Verify nothing is missing
   - Suggest improvements

2. **Approve Architecture**
   - Confirm design is sound
   - Verify integration points
   - Sign off on approach

3. **Begin Implementation**
   - Start with Week 1 modules
   - Test as you go
   - Iterate based on learnings

4. **Continuous Review**
   - Weekly progress reviews
   - Adjust plan as needed
   - Update documentation

## Questions & Feedback

### For Reviewers

- Are the interfaces clear and complete?
- Is anything over-engineered?
- Are there simpler approaches?
- What's missing?

### For Implementers

- Is the implementation guide sufficient?
- Are the code templates helpful?
- What additional guidance is needed?
- Where are the ambiguities?

## Conclusion

This design provides:

✅ **Complete API contracts** for all 11 new modules
✅ **Clear architecture** with visual diagrams
✅ **Practical implementation guide** with examples
✅ **Comprehensive documentation** for all scenarios
✅ **Philosophy alignment** with azlin's principles

**Total effort:** ~2,500-3,000 LOC + 2,000 test LOC = **4,500-5,000 LOC**

**Timeline:** 5 weeks for complete implementation

**Risk:** Low - All modules are independently testable

**Impact:** High - Enables natural language Azure operations with multiple execution strategies, cost awareness, and automatic recovery

---

**Status:** ✅ Design complete and ready for review

**Reviewers:** Please provide feedback on the API contracts and architecture

**Implementers:** Wait for approval, then begin with Week 1 modules
