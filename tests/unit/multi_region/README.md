# Multi-Region Unit Tests

This directory contains unit tests for the multi-region orchestration modules following the 60/30/10 testing pyramid.

## Test Coverage (60% Unit Tests)

These tests focus on:
- Fast execution (<100ms per test)
- Heavily mocked external dependencies (Azure CLI, SSH, subprocess)
- Business logic validation
- Edge cases and boundary conditions
- Input validation

## Test Files

### test_parallel_deployer.py
Unit tests for `parallel_deployer.py` module.

**Coverage:**
- DeploymentResult, DeploymentStatus, MultiRegionResult dataclasses
- ParallelDeployer initialization and validation
- Deployment logic with mocked Azure
- Concurrency limit enforcement
- Error handling and timeout behavior
- Success rate calculations

**Key Tests:**
- `test_deployment_result_creation_success` - Dataclass creation
- `test_deploy_to_regions_empty_list_raises_error` - Input validation
- `test_deploy_multiple_regions_all_success` - Parallel deployment
- `test_deploy_respects_max_concurrent_limit` - Concurrency control
- `test_deploy_timeout_handling` - Timeout behavior

### test_region_failover.py
Unit tests for `region_failover.py` module.

**Coverage:**
- FailoverMode, FailureType enums
- HealthCheckResult, FailoverDecision dataclasses
- Failover decision logic (auto vs manual)
- Confidence calculations
- Health check result creation
- Input validation

**Key Tests:**
- `test_evaluate_failover_network_unreachable_auto` - Auto-failover for clear failures
- `test_evaluate_failover_vm_stopped_manual` - Manual failover for ambiguous cases
- `test_confidence_network_unreachable_high` - High confidence for clear failures
- `test_hybrid_mode_respects_failure_type` - Hybrid mode behavior

### test_cross_region_sync.py
Unit tests for `cross_region_sync.py` module.

**Coverage:**
- SyncStrategy enum
- SyncResult dataclass
- Strategy selection logic (rsync vs Azure Blob)
- Size estimation calculations
- Input validation
- Delete flag behavior

**Key Tests:**
- `test_choose_strategy_small_files_uses_rsync` - Rsync for <100MB
- `test_choose_strategy_large_files_uses_blob` - Blob for >=100MB
- `test_choose_strategy_exactly_100mb_uses_blob` - Boundary condition
- `test_sync_directories_empty_paths_raises_error` - Input validation

### test_region_context.py
Unit tests for `region_context.py` module.

**Coverage:**
- RegionMetadata dataclass
- Region add/get/remove operations
- Primary region management
- List regions with sorting
- Azure tag synchronization
- Input validation

**Key Tests:**
- `test_add_region_minimal_fields` - Add region operation
- `test_set_primary_region_updates_metadata` - Primary region switching
- `test_list_regions_sorted_primary_first` - Region listing with sorting
- `test_sync_from_azure_tags_multiple_vms` - Azure tag integration

## Running Unit Tests

```bash
# Run all unit tests
pytest tests/unit/multi_region/ -v

# Run specific module tests
pytest tests/unit/multi_region/test_parallel_deployer.py -v

# Run with coverage
pytest tests/unit/multi_region/ --cov=azlin.modules --cov-report=html

# Run fast tests only (exclude slow ones)
pytest tests/unit/multi_region/ -m "not slow"
```

## Test Patterns

### Mock Azure CLI Responses

```python
with patch('azlin.modules.parallel_deployer.subprocess.run') as mock_run:
    mock_run.return_value = Mock(
        returncode=0,
        stdout=json.dumps({"publicIpAddress": "1.2.3.4"})
    )
    # Test logic here
```

### Mock Async Methods

```python
with patch.object(deployer, '_deploy_single_region', new_callable=AsyncMock) as mock_deploy:
    mock_deploy.return_value = DeploymentResult(...)
    result = await deployer.deploy_to_regions(...)
```

### Test Async Functions

```python
@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result is not None
```

## Writing New Tests

When adding new unit tests:

1. **Follow naming convention**: `test_<feature>_<scenario>`
2. **Use pytest.skip()**: For not-yet-implemented modules
3. **Mock external dependencies**: Azure CLI, SSH, subprocess
4. **Test edge cases**: Empty inputs, None values, boundary conditions
5. **Assert clearly**: One assertion per concept
6. **Document test purpose**: Clear docstring explaining what's tested

### Good Test Example

```python
def test_deploy_to_regions_empty_list_raises_error(self):
    """Test that empty regions list raises ValueError."""
    mock_config = Mock()
    deployer = ParallelDeployer(config_manager=mock_config)
    mock_vm_config = Mock()

    with pytest.raises(ValueError, match="regions list cannot be empty"):
        asyncio.run(deployer.deploy_to_regions(
            regions=[],
            vm_config=mock_vm_config
        ))
```

## Test Status

All tests in this directory are currently marked with `pytest.skip("Module not yet implemented")` because the modules under test have not been implemented yet.

**Next Steps:**
1. Implement modules in `src/azlin/modules/`
2. Remove `pytest.skip()` decorators
3. Fix imports at top of test files
4. Run tests to verify implementation

## Performance Targets

Unit tests should be:
- **Fast**: <100ms per test
- **Isolated**: No dependencies on other tests
- **Repeatable**: Consistent results every run
- **Self-validating**: Clear pass/fail without manual inspection

Current test count: 100+ unit tests across 4 modules

## Related Documentation

- Integration tests: `tests/integration/multi_region/README.md`
- E2E tests: `tests/e2e/multi_region/README.md`
- Architecture spec: `specs/MULTI_REGION_SPEC.md`
- Testing strategy: See architecture spec section "Testing Strategy"
