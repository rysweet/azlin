# azdoit Enhancement - Test Suite

**Test-Driven Development (TDD) for PR #156 Enhancement**

## Quick Start

### Run All Unit Tests

```bash
cd /path/to/azlin-azdoit
pytest tests/unit/agentic/ -v
```

### Run Specific Module Tests

```bash
# Strategy selector (20 tests)
pytest tests/unit/agentic/test_strategy_selector.py -v

# Cost estimator (30 tests)
pytest tests/unit/agentic/test_cost_estimator.py -v

# State persistence (25 tests)
pytest tests/unit/agentic/test_state_persistence.py -v

# Failure recovery (15 tests)
pytest tests/unit/agentic/test_failure_recovery.py -v

# Terraform generator (12 tests)
pytest tests/unit/agentic/test_terraform_generator.py -v

# MCP client (10 tests)
pytest tests/unit/agentic/test_mcp_client.py -v
```

### Run Integration Tests

```bash
# Requires: az login, terraform installed, MCP Server running
pytest tests/integration/agentic/ -m integration -v
```

### Run E2E Tests

```bash
# WARNING: Costs real money! Only on test Azure subscription
pytest tests/e2e/ -m e2e --run-e2e -v
```

## Test Status

### Unit Tests (112 tests) - 60% of pyramid

| Module | Tests | Status | Priority |
|--------|-------|--------|----------|
| Strategy Selector | 20 | ⏸️ Skipped | HIGH |
| Cost Estimator | 30 | ⏸️ Skipped | HIGH |
| State Persistence | 25 | ⏸️ Skipped | HIGH |
| Failure Recovery | 15 | ⏸️ Skipped | MEDIUM |
| Terraform Generator | 12 | ⏸️ Skipped | MEDIUM |
| MCP Client | 10 | ⏸️ Skipped | MEDIUM |

**Status**: All tests **intentionally skipped** (TDD). Tests define expected behavior before implementation.

## Test-Driven Development Workflow

### 1. Verify Tests Fail (Red)

```bash
# Pick one test to implement
pytest tests/unit/agentic/test_strategy_selector.py::TestStrategySelector::test_selector_initialization -v
```

**Expected**: `FAILED - ImportError: No module named 'azlin.agentic.strategy_selector'`

### 2. Implement Minimum Code (Green)

Create `/Users/ryan/src/azlin-azdoit/src/azlin/agentic/strategy_selector.py`:

```python
class StrategySelector:
    def __init__(self):
        self.strategies = []
```

### 3. Verify Test Passes

```bash
pytest tests/unit/agentic/test_strategy_selector.py::TestStrategySelector::test_selector_initialization -v
```

**Expected**: `PASSED`

### 4. Refactor (Keep Green)

Improve code while keeping tests passing.

## Test Coverage Targets

| Module | Target | Critical Paths |
|--------|--------|----------------|
| Strategy Selector | 85% | Selection logic, fallback |
| Cost Estimator | 80% | Calculations, ±15% accuracy |
| State Manager | 90% | Persistence, recovery |
| Failure Recovery | 75% | Detection, retry |
| Terraform Generator | 70% | HCL generation |
| MCP Client | 75% | Connection, tools |

## Key Test Scenarios

### Strategy Selection
- ✅ Simple VM → Azure CLI
- ✅ AKS cluster → Terraform
- ✅ Query operations → MCP Server
- ✅ Fallback on failure

### Cost Estimation
- ✅ VM cost within ±15%
- ✅ Storage cost accurate
- ✅ AKS breakdown correct
- ✅ Budget alerts trigger

### State Persistence
- ✅ Save to JSON
- ✅ Load by ID
- ✅ Track history
- ✅ Recover after crash

### Failure Recovery
- ✅ Detect QuotaExceeded
- ✅ Research alternatives
- ✅ Retry with backoff (max 5)
- ✅ Escalate to user

## Available Fixtures

```python
# Directories
temp_config_dir          # Mock ~/.azlin
temp_objectives_dir      # Mock ~/.azlin/objectives

# Mock Clients
mock_anthropic_client    # Claude API
mock_azure_cli          # az commands
mock_mcp_server         # MCP Server
mock_azure_pricing_api  # Pricing API
mock_terraform_executor # Terraform
mock_mslearn_client     # MS Learn

# Sample Data
sample_objective_state
sample_cost_estimate
sample_terraform_config
sample_objectives_for_strategy
sample_failure_scenarios
```

## Running Tests

### By Type

```bash
pytest -m unit           # Unit tests only
pytest -m integration    # Integration tests
pytest -m e2e           # E2E tests (costs money!)
pytest -m "not slow"    # Skip slow tests
```

### With Coverage

```bash
pytest tests/unit/agentic/ --cov=azlin.agentic --cov-report=html
open htmlcov/index.html
```

### Verbose Output

```bash
pytest -vv              # Very verbose
pytest -s               # Show print statements
pytest -x               # Stop on first failure
```

## Prerequisites

### Unit Tests
- Python 3.11+
- pytest 7.4+
- No external dependencies (all mocked)

### Integration Tests
- Azure CLI (`az login`)
- Terraform binary
- MCP Server (optional)
- ANTHROPIC_API_KEY environment variable

### E2E Tests
- Azure subscription with quota
- ANTHROPIC_API_KEY
- Budget for test resources (~$5-10)

## File Structure

```
tests/
├── conftest.py                           # Shared fixtures
├── unit/agentic/                         # 60% - Fast, mocked
│   ├── test_strategy_selector.py         #   20 tests
│   ├── test_cost_estimator.py            #   30 tests
│   ├── test_state_persistence.py         #   25 tests
│   ├── test_failure_recovery.py          #   15 tests
│   ├── test_terraform_generator.py       #   12 tests
│   └── test_mcp_client.py                #   10 tests
├── integration/agentic/                  # 30% - Real tools
│   └── test_strategy_execution.py        #   24 tests
└── e2e/                                  # 10% - Real Azure
    └── test_azdoit_scenarios.py          #    8 tests
```

## Common Patterns

### Test with Mock

```python
def test_example(mock_anthropic_client):
    parser = IntentParser()
    parser.client = mock_anthropic_client
    result = parser.parse("Create VM")
    assert result["intent"] == "provision_vm"
```

### Test State Persistence

```python
def test_state(temp_objectives_dir):
    manager = StateManager(objectives_dir=temp_objectives_dir)
    obj = manager.create_objective("Test", {"intent": "test"})
    loaded = manager.load_objective(obj["id"])
    assert loaded["id"] == obj["id"]
```

### Test Cost Accuracy

```python
def test_cost(mock_azure_pricing_api):
    estimator = CostEstimator(pricing_api=mock_azure_pricing_api)
    cost = estimator.estimate_vm_cost("Standard_D2s_v3")
    assert cost == pytest.approx(70.08, rel=0.15)  # ±15%
```

## Troubleshooting

```bash
# Tests not found?
pytest --collect-only

# Import errors?
pip install -e .

# Azure auth?
az login && az account show

# MCP Server?
npx @microsoft/azure-mcp-server
```

## Next Steps

1. **Implement Strategy Selector** (highest priority)
   - Unskip tests one by one
   - Make each test pass
   - Refactor

2. **Continue with Other Modules**
   - Cost Estimator
   - State Persistence
   - Failure Recovery
   - Terraform Generator
   - MCP Client

3. **Integration Tests**
   - After unit tests pass
   - Unskip integration tests

4. **E2E Validation**
   - Manual testing
   - Real Azure deployment
   - Cost tracking validation

## Documentation

- **Full Strategy**: `docs/AZDOIT_TEST_STRATEGY.md`
- **PR #156**: Original agentic module
- **pytest**: https://docs.pytest.org/

---

**Version**: 1.0.0
**Updated**: 2025-10-20
**Status**: TDD - Tests define expected behavior, awaiting implementation
