# azdoit Enhancement - Test Strategy

**PR #156 Enhancement**
**Test-Driven Development (TDD) Approach**
**Testing Pyramid: 60% Unit / 30% Integration / 10% E2E**

## Overview

This document describes the comprehensive test strategy for the azdoit enhancement, which adds 10 major capabilities to the agentic module:

1. Multi-strategy execution (4 strategies)
2. Azure MCP Server integration (40+ services)
3. Cost estimation and tracking (±15% accuracy target)
4. Intelligent failure recovery (research & retry)
5. State persistence across sessions
6. Auto mode integration
7. Azure-only filtering
8. Prerequisite auto-installation
9. Terraform generation
10. MS Learn integration

## Test Philosophy

### Test-Driven Development (TDD)

All tests are written **BEFORE** implementation:
- Tests define expected behavior
- Implementation makes tests pass
- Refactor while keeping tests green

### Testing Pyramid

```
        /\
       /E2E\      10% - Full user scenarios (real Azure)
      /------\
     /  Intg  \   30% - Component integration (sandbox)
    /----------\
   /    Unit    \ 60% - Core logic (mocked dependencies)
  /--------------\
```

**Rationale:**
- Unit tests: Fast (<100ms), isolated, deterministic
- Integration tests: Medium speed (~5s), real tools, isolated resources
- E2E tests: Slow (5-20min), expensive, real Azure deployments

## Test Coverage Targets

### Unit Tests (60% of pyramid)

**Target: 80% code coverage**

| Module | Test File | Test Count | Priority |
|--------|-----------|------------|----------|
| Strategy Selector | `test_strategy_selector.py` | 20 | HIGH |
| Cost Estimator | `test_cost_estimator.py` | 30 | HIGH |
| State Persistence | `test_state_persistence.py` | 25 | HIGH |
| Failure Recovery | `test_failure_recovery.py` | 15 | MEDIUM |
| Terraform Generator | `test_terraform_generator.py` | 12 | MEDIUM |
| MCP Client | `test_mcp_client.py` | 10 | MEDIUM |

**Total Unit Tests: ~112**

### Integration Tests (30% of pyramid)

**Target: Real tools, isolated resources**

| Test Suite | Test Count | Duration | Prerequisites |
|------------|------------|----------|---------------|
| Azure CLI Execution | 5 | ~30s | `az` CLI, auth |
| Terraform Execution | 5 | ~60s | `terraform` binary |
| MCP Server Connection | 3 | ~10s | MCP Server running |
| Objective Lifecycle | 5 | ~45s | Full system |
| Cost API Integration | 3 | ~15s | Azure APIs |
| Prerequisite Install | 3 | ~20s | System access |

**Total Integration Tests: ~24**

### E2E Tests (10% of pyramid)

**Target: Full user scenarios**

| Scenario | Duration | Cost | Prerequisites |
|----------|----------|------|---------------|
| AKS Deployment | 15-20min | ~$2 | Azure quota |
| Storage Account | 2-5min | ~$0.10 | Azure quota |
| Failure Recovery | 5-10min | $0 (dry-run) | None |
| Cost Tracking (30d) | 30 days | ~$70 | Long-running |

**Total E2E Tests: ~8**

## Test Structure

### Directory Layout

```
tests/
├── conftest.py                      # Shared fixtures
├── unit/
│   └── agentic/
│       ├── test_strategy_selector.py     # 20 tests
│       ├── test_cost_estimator.py        # 30 tests
│       ├── test_state_persistence.py     # 25 tests
│       ├── test_failure_recovery.py      # 15 tests
│       ├── test_terraform_generator.py   # 12 tests
│       └── test_mcp_client.py            # 10 tests
├── integration/
│   └── agentic/
│       └── test_strategy_execution.py    # 24 tests
└── e2e/
    └── test_azdoit_scenarios.py          # 8 tests
```

## Mocking Strategy

### External Dependencies to Mock

1. **Claude API (Anthropic)**
   - Mock: `anthropic.Anthropic` client
   - Return: Structured JSON responses
   - Fixture: `mock_anthropic_client`

2. **Azure CLI**
   - Mock: `subprocess.run` for `az` commands
   - Return: JSON output
   - Fixture: `mock_azure_cli`

3. **Azure MCP Server**
   - Mock: MCP client connection
   - Return: Tool list and responses
   - Fixture: `mock_mcp_server`

4. **Azure Pricing API**
   - Mock: HTTP requests to pricing API
   - Return: VM/storage pricing data
   - Fixture: `mock_azure_pricing_api`

5. **Terraform Binary**
   - Mock: `subprocess.run` for `terraform` commands
   - Return: Validation/plan results
   - Fixture: `mock_terraform_executor`

6. **MS Learn API**
   - Mock: Documentation search
   - Return: Tutorial links
   - Fixture: `mock_mslearn_client`

### Integration Tests (Real Tools)

Integration tests use **real tools** but **isolated resources**:
- Real `az` CLI (requires `az login`)
- Real `terraform` binary (requires installation)
- Real MCP Server (requires local server)
- Temporary directories for state files
- Dry-run mode to avoid actual deployments

## Test Execution

### Running Tests Locally

```bash
# All tests (fast unit tests only)
pytest tests/unit/ -v

# Specific module
pytest tests/unit/agentic/test_strategy_selector.py -v

# With coverage
pytest tests/unit/ --cov=azlin.agentic --cov-report=html

# Integration tests (requires Azure auth)
pytest tests/integration/ -m integration -v

# E2E tests (requires Azure quota, costs money!)
pytest tests/e2e/ -m e2e -v --run-e2e
```

### Test Markers

```python
@pytest.mark.unit          # Fast, mocked dependencies
@pytest.mark.integration   # Medium, real tools
@pytest.mark.e2e          # Slow, real Azure
@pytest.mark.slow         # Takes >1 minute
@pytest.mark.skip         # Not implemented yet (TDD)
```

## CI/CD Integration

### GitHub Actions Workflow

```yaml
name: azdoit Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -e ".[dev]"
      - run: pytest tests/unit/ --cov --cov-report=xml
      - uses: codecov/codecov-action@v3

  integration-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    steps:
      - uses: actions/checkout@v3
      - uses: azure/login@v1
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      - run: pip install -e ".[dev]"
      - run: |
          curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo apt-key add -
          sudo apt-add-repository "deb [arch=amd64] https://apt.releases.hashicorp.com $(lsb_release -cs) main"
          sudo apt-get update && sudo apt-get install terraform
      - run: pytest tests/integration/ -m integration
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

  e2e-tests:
    runs-on: ubuntu-latest
    needs: [unit-tests, integration-tests]
    # Only run on main branch (expensive!)
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      - uses: azure/login@v1
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      - run: pip install -e ".[dev]"
      - run: pytest tests/e2e/ -m "e2e and not slow"
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

### Required Secrets

- `AZURE_CREDENTIALS`: Azure service principal
- `ANTHROPIC_API_KEY`: Claude API key
- `AZURE_SUBSCRIPTION_ID`: Test subscription
- `AZURE_RESOURCE_GROUP`: Test resource group

## Test Data & Fixtures

### Shared Fixtures (`conftest.py`)

```python
# Temp directories
temp_config_dir          # ~/.azlin mock
temp_objectives_dir      # ~/.azlin/objectives mock

# Mock clients
mock_anthropic_client    # Claude API
mock_azure_cli          # az command
mock_mcp_server         # MCP Server
mock_azure_pricing_api  # Pricing API
mock_terraform_executor # Terraform
mock_mslearn_client     # MS Learn

# Sample data
sample_objective_state     # Full objective JSON
sample_cost_estimate       # Cost breakdown
sample_terraform_config    # HCL config
sample_failure_scenarios   # Error cases
```

### Test Data Files

```
tests/fixtures/
├── terraform/
│   ├── simple_vm.tf
│   ├── aks_cluster.tf
│   └── storage_account.tf
├── objectives/
│   ├── completed_vm.json
│   ├── in_progress_aks.json
│   └── failed_quota.json
└── responses/
    ├── claude_parse_vm.json
    ├── azure_pricing.json
    └── mcp_tools.json
```

## Coverage Requirements

### Minimum Coverage Thresholds

```ini
# pyproject.toml or .coveragerc
[tool.coverage.run]
branch = true
source = ["azlin.agentic"]

[tool.coverage.report]
fail_under = 80
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
]

[tool.coverage.html]
directory = "htmlcov"
```

### Coverage by Module

| Module | Target | Critical Paths |
|--------|--------|----------------|
| Strategy Selector | 85% | Selection logic, fallback |
| Cost Estimator | 80% | Calculations, ±15% accuracy |
| State Manager | 90% | Persistence, recovery |
| Failure Recovery | 75% | Detection, retry logic |
| Terraform Generator | 70% | HCL generation |
| MCP Client | 75% | Connection, tool calls |

## Critical Test Scenarios

### High Priority (Must Pass)

1. **Strategy Selection**
   - Simple VM → Azure CLI
   - AKS cluster → Terraform
   - Query operations → MCP Server
   - Fallback on failure

2. **Cost Estimation**
   - VM cost within ±15%
   - Storage cost accurate
   - AKS cluster cost breakdown
   - Budget alerts

3. **State Persistence**
   - Save objective to JSON
   - Load objective by ID
   - Track execution history
   - Recover after crash

4. **Failure Recovery**
   - Detect QuotaExceeded
   - Research alternatives
   - Retry with backoff
   - Max 5 attempts

### Medium Priority

5. **Terraform Generation**
   - Valid HCL syntax
   - Resource dependencies
   - Terraform validate passes

6. **MCP Integration**
   - Connect to server
   - List available tools
   - Execute tool calls

### Low Priority

7. **Auto Mode Integration**
8. **Prerequisite Installation**
9. **MS Learn Integration**

## Performance Requirements

| Test Type | Target | Actual | Notes |
|-----------|--------|--------|-------|
| Unit test | <100ms | TBD | Per test |
| Integration test | <5s | TBD | Per test |
| E2E (simple) | <5min | TBD | VM provision |
| E2E (complex) | <20min | TBD | AKS cluster |

## Security Testing

### Security Scenarios

1. **Code Generation Safety**
   - Reject dangerous code (`os.system`, `eval`)
   - Sandbox execution
   - Path validation

2. **Credential Handling**
   - No API keys in logs
   - No credentials in state files
   - Secure Azure auth

3. **Resource Limits**
   - Max 100 VMs per objective
   - Cost limit enforcement
   - Quota checks

## Known Limitations

1. **Azure Pricing API**
   - Pricing changes daily
   - Not all regions covered
   - Free tier not always accurate

2. **MCP Server**
   - Requires local server running
   - Tool availability varies
   - Connection timeout handling

3. **Terraform State**
   - Remote state not mocked
   - Plan output parsing fragile
   - Provider version pinning

## Test Maintenance

### Updating Tests

When adding new features:
1. Write failing tests first (TDD)
2. Update fixtures in `conftest.py`
3. Add integration test scenarios
4. Document in this file

### Flaky Tests

If tests are flaky:
1. Add retry logic for network calls
2. Increase timeouts for slow operations
3. Use `pytest-rerunfailures`: `@pytest.mark.flaky(reruns=3)`

### Mocking Updates

When Azure APIs change:
1. Update fixtures with new response format
2. Version-pin test dependencies
3. Document breaking changes

## Success Criteria

### Definition of Done

- ✅ All unit tests passing (80%+ coverage)
- ✅ Integration tests passing (Azure CLI, Terraform)
- ✅ E2E scenarios documented and validated
- ✅ CI/CD pipeline configured
- ✅ No security vulnerabilities in tests
- ✅ Performance requirements met

### Quality Gates

1. **PR Merge**: All unit tests + integration tests passing
2. **Main Merge**: E2E smoke tests passing
3. **Release**: Full E2E suite passing + manual validation

## References

- [PR #156 - Agentic Do Mode](https://github.com/rysweet/azlin/pull/156)
- [pytest Documentation](https://docs.pytest.org/)
- [Azure CLI Reference](https://learn.microsoft.com/cli/azure/)
- [Terraform Azure Provider](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs)
- [Azure MCP Server](https://github.com/rysweet/MicrosoftHackathon2025-AgenticCoding)

---

**Last Updated**: 2025-10-20
**Test Framework**: pytest 7.4+
**Python Version**: 3.11+
**Azure CLI Version**: 2.50+
**Terraform Version**: 1.5+
