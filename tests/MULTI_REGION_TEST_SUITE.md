# Multi-Region Test Suite - Comprehensive Overview

This document provides a complete overview of the multi-region test suite following TDD principles and the 60/30/10 testing pyramid.

## Test Suite Summary

| Test Type | Count | Percentage | Execution Time | Status |
|-----------|-------|------------|----------------|--------|
| **Unit Tests** | ~100 | 60% | <10 seconds | ✅ Complete (skipped - modules not implemented) |
| **Integration Tests** | ~30 | 30% | ~2 minutes | ✅ Complete (skipped - modules not implemented) |
| **E2E Tests** | ~15 | 10% | ~30 minutes | ✅ Complete (skipped - modules not implemented) |
| **Total** | ~145 | 100% | ~35 minutes | **All failing tests ready for TDD** |

## Test Directory Structure

```
tests/
├── unit/
│   └── multi_region/
│       ├── __init__.py
│       ├── README.md
│       ├── test_parallel_deployer.py (30 tests)
│       ├── test_region_failover.py (35 tests)
│       ├── test_cross_region_sync.py (25 tests)
│       └── test_region_context.py (25 tests)
├── integration/
│   └── multi_region/
│       ├── __init__.py
│       ├── README.md
│       ├── test_multi_region_deployment_integration.py (12 tests)
│       ├── test_failover_integration.py (10 tests)
│       └── test_cross_region_sync_integration.py (15 tests)
└── e2e/
    └── multi_region/
        ├── __init__.py
        ├── README.md
        └── test_multi_region_e2e.py (8 tests)
```

## Test Coverage by Module

### Brick 11: ParallelDeployer

**Unit Tests (60%):**
- Dataclass behavior (DeploymentResult, MultiRegionResult)
- Initialization and configuration
- Input validation (empty lists, None values, invalid regions)
- Parallel deployment logic
- Concurrency limit enforcement
- Timeout handling
- Error handling (partial failures, all failures)
- Success rate calculations

**Integration Tests (30%):**
- Multi-module interaction (ParallelDeployer + ConfigManager + VMProvisioning)
- Config storage after each deployment
- Region context updates
- Azure CLI mocking with realistic responses
- Partial failure resilience
- Performance with realistic delays

**E2E Tests (10%):**
- Real Azure deployment to 3 regions
- Performance benchmark (<10 minutes target)
- Real resource creation and cleanup

**Total: 42 tests for ParallelDeployer**

### Brick 12: RegionFailover

**Unit Tests (60%):**
- Enum behavior (FailoverMode, FailureType)
- Dataclass behavior (HealthCheckResult, FailoverDecision)
- Failover decision logic (auto vs manual)
- Confidence calculations (0.0-1.0)
- Health check result creation
- Mode behavior (AUTO, MANUAL, HYBRID)
- Input validation

**Integration Tests (30%):**
- Health check flow (Azure VM status + network + SSH)
- Complete failover execution
- Target health verification
- Config updates during failover
- Auto vs manual workflows
- Data sync integration

**E2E Tests (10%):**
- Real failover between regions
- Performance benchmark (<60 seconds target)
- VM stop simulation
- Data integrity verification

**Total: 45 tests for RegionFailover**

### Brick 13: CrossRegionSync

**Unit Tests (60%):**
- Enum behavior (SyncStrategy)
- Dataclass behavior (SyncResult)
- Strategy selection logic (rsync vs Azure Blob)
- Size estimation calculations
- Boundary conditions (100MB threshold)
- Input validation
- Delete flag behavior

**Integration Tests (30%):**
- Rsync strategy with SSH
- Azure Blob strategy with staging
- Strategy auto-selection
- Multi-path sync
- Progress reporting
- Error handling (upload failures, SSH failures)
- Staging cleanup verification

**E2E Tests (10%):**
- Real data transfer (100MB dataset)
- Performance benchmark (<3 minutes for 100MB)
- Data integrity verification (MD5 checksums)
- Reliability benchmark (99.9% target)

**Total: 40 tests for CrossRegionSync**

### Brick 14: RegionContext

**Unit Tests (60%):**
- Dataclass behavior (RegionMetadata)
- Add/get/remove region operations
- Primary region management
- List regions with sorting
- Azure tag integration
- Input validation

**Integration Tests (30%):**
- Azure tag creation during add_region
- Sync from Azure updates local config
- Tag cleanup during remove_region
- Multi-region context management

**E2E Tests (10%):**
- (Covered by complete workflow tests)

**Total: 35 tests for RegionContext**

## Running the Test Suite

### Quick Start

```bash
# Run all multi-region tests (unit + integration, skipping E2E)
pytest tests/unit/multi_region/ tests/integration/multi_region/ -v

# Run with coverage report
pytest tests/unit/multi_region/ tests/integration/multi_region/ --cov=azlin.modules --cov-report=html

# View coverage report
open htmlcov/index.html
```

### By Test Type

```bash
# Unit tests only (fast, <10 seconds)
pytest tests/unit/multi_region/ -v

# Integration tests only (moderate, ~2 minutes)
pytest tests/integration/multi_region/ -v

# E2E tests only (slow, expensive - requires Azure)
export AZLIN_RUN_E2E_TESTS=true
pytest tests/e2e/multi_region/ -v -m e2e
```

### By Module

```bash
# ParallelDeployer tests
pytest tests/unit/multi_region/test_parallel_deployer.py tests/integration/multi_region/test_multi_region_deployment_integration.py -v

# RegionFailover tests
pytest tests/unit/multi_region/test_region_failover.py tests/integration/multi_region/test_failover_integration.py -v

# CrossRegionSync tests
pytest tests/unit/multi_region/test_cross_region_sync.py tests/integration/multi_region/test_cross_region_sync_integration.py -v

# RegionContext tests
pytest tests/unit/multi_region/test_region_context.py -v
```

## Test Development Workflow (TDD)

### Red-Green-Refactor Cycle

1. **RED**: Write failing test first
   - All tests currently in "RED" state (pytest.skip)
   - Remove pytest.skip() one test at a time

2. **GREEN**: Implement minimal code to pass
   - Write just enough code to make the test pass
   - Don't worry about optimization yet

3. **REFACTOR**: Improve code without breaking tests
   - Clean up implementation
   - All tests still pass

### Example TDD Workflow

```bash
# Step 1: Pick a test to implement (start with simplest)
# Edit: tests/unit/multi_region/test_parallel_deployer.py
# Remove pytest.skip() from: test_deployment_status_values

# Step 2: Run the test (should fail - RED)
pytest tests/unit/multi_region/test_parallel_deployer.py::TestDeploymentStatus::test_deployment_status_values -v

# Step 3: Implement the code (GREEN)
# Create: src/azlin/modules/parallel_deployer.py
# Add: DeploymentStatus enum

# Step 4: Run test again (should pass - GREEN)
pytest tests/unit/multi_region/test_parallel_deployer.py::TestDeploymentStatus::test_deployment_status_values -v

# Step 5: Refactor if needed
# Clean up code, run test again to ensure still passing

# Step 6: Repeat for next test
```

### Recommended Test Order

**Phase 1: Dataclasses (Easiest)**
1. `test_deployment_status_values` - Enum
2. `test_deployment_result_creation_success` - Dataclass
3. `test_multi_region_result_all_success` - Dataclass
4. `test_failover_mode_values` - Enum
5. `test_sync_strategy_values` - Enum

**Phase 2: Initialization (Easy)**
1. `test_parallel_deployer_init_defaults` - Constructor
2. `test_region_failover_init_defaults` - Constructor
3. `test_cross_region_sync_init` - Constructor
4. `test_region_context_init` - Constructor

**Phase 3: Business Logic (Medium)**
1. `test_choose_strategy_small_files_uses_rsync` - Strategy selection
2. `test_evaluate_failover_network_unreachable_auto` - Decision logic
3. `test_add_region_minimal_fields` - CRUD operations

**Phase 4: Complex Logic (Hard)**
1. `test_deploy_multiple_regions_all_success` - Async parallel
2. `test_deploy_respects_max_concurrent_limit` - Concurrency
3. `test_health_check_all_systems_healthy` - Multi-system integration

**Phase 5: Integration (Hardest)**
1. Integration tests (after unit tests pass)
2. E2E tests (after integration tests pass)

## Test Metrics and Goals

### Coverage Goals

| Module | Unit Coverage | Integration Coverage | E2E Coverage | Total Coverage |
|--------|---------------|---------------------|--------------|----------------|
| parallel_deployer.py | 90%+ | 80%+ | 50%+ | **85%+** |
| region_failover.py | 90%+ | 80%+ | 50%+ | **85%+** |
| cross_region_sync.py | 90%+ | 80%+ | 50%+ | **85%+** |
| region_context.py | 90%+ | 80%+ | 40%+ | **80%+** |
| **Overall** | **90%+** | **80%+** | **45%+** | **83%+** |

### Performance Goals

| Test Type | Target | Current |
|-----------|--------|---------|
| Unit test execution | <100ms per test | Not measured yet |
| Integration test execution | <5s per test | Not measured yet |
| E2E test execution | Varies (see targets below) | Not measured yet |
| Total unit suite | <10 seconds | Not measured yet |
| Total integration suite | <2 minutes | Not measured yet |

### E2E Performance Targets

| Feature | Target | Test |
|---------|--------|------|
| 3-region deployment | <10 minutes | `test_deploy_to_3_real_azure_regions` |
| Failover completion | <60 seconds | `test_auto_failover_completes_under_60_seconds` |
| 100MB sync (rsync) | <3 minutes | `test_sync_100mb_dataset_between_real_regions` |
| 500MB sync (blob) | <8 minutes | Not implemented yet |
| Sync reliability | 99.9% | `test_sync_reliability_99_9_percent` |

## Key Testing Patterns

### Pattern 1: Mock Azure CLI Responses

```python
with patch('azlin.modules.parallel_deployer.subprocess.run') as mock_run:
    mock_run.return_value = Mock(
        returncode=0,
        stdout=json.dumps({"publicIpAddress": "1.2.3.4"})
    )
    result = await deployer.deploy_to_regions(...)
```

### Pattern 2: Test Async Functions

```python
@pytest.mark.asyncio
async def test_async_deployment():
    result = await deployer.deploy_to_regions(...)
    assert result.success_rate == 1.0
```

### Pattern 3: Test Concurrency Limits

```python
concurrent_count = 0
max_seen = 0
lock = asyncio.Lock()

async def track_concurrency():
    nonlocal concurrent_count, max_seen
    async with lock:
        concurrent_count += 1
        max_seen = max(max_seen, concurrent_count)
    # ... do work ...
    async with lock:
        concurrent_count -= 1

assert max_seen <= max_concurrent
```

### Pattern 4: Test Input Validation

```python
with pytest.raises(ValueError, match="regions list cannot be empty"):
    await deployer.deploy_to_regions(regions=[], vm_config=mock_config)
```

## Test Fixtures

Common fixtures are defined in `tests/conftest.py`:

- `temp_ssh_dir` - Temporary SSH directory
- `temp_config_dir` - Temporary config directory
- `protect_production_config` - Production config protection (CRITICAL)
- `set_test_mode_env` - Sets AZLIN_TEST_MODE environment variable

## CI/CD Integration

### GitHub Actions Workflow

```yaml
name: Multi-Region Tests

on:
  pull_request:
    paths:
      - 'src/azlin/modules/**'
      - 'tests/unit/multi_region/**'
      - 'tests/integration/multi_region/**'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -e .[dev]
      - name: Run unit tests
        run: pytest tests/unit/multi_region/ -v --cov=azlin.modules --cov-report=xml
      - name: Run integration tests
        run: pytest tests/integration/multi_region/ -v
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

### Nightly E2E Tests

```yaml
name: E2E Tests

on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM daily

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - name: Azure Login
        uses: azure/login@v1
      - name: Run E2E Tests
        env:
          AZLIN_RUN_E2E_TESTS: true
        run: pytest tests/e2e/multi_region/ -v -m e2e
```

## Current Status

**Test Suite Status**: ✅ Complete, all tests written and ready for TDD

**Implementation Status**: ❌ Modules not yet implemented

**Next Steps**:
1. Begin TDD workflow (RED phase complete)
2. Implement modules one test at a time (GREEN phase)
3. Refactor as needed (REFACTOR phase)
4. Track coverage and performance metrics
5. Run E2E tests for final validation

## Related Documentation

- Architecture Specification: `specs/MULTI_REGION_SPEC.md`
- Unit Tests README: `tests/unit/multi_region/README.md`
- Integration Tests README: `tests/integration/multi_region/README.md`
- E2E Tests README: `tests/e2e/multi_region/README.md`
- Testing Strategy: See architecture spec section 9

---

**Test Suite Version**: 1.0
**Last Updated**: 2025-12-01
**Status**: Ready for TDD implementation
