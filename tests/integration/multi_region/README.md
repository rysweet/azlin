# Multi-Region Integration Tests

This directory contains integration tests for multi-region orchestration following the 60/30/10 testing pyramid.

## Test Coverage (30% Integration Tests)

These tests focus on:
- Multi-module interactions
- Mocked Azure API
- SSH mocking
- Config persistence workflows
- Complete feature flows

## Test Files

### test_multi_region_deployment_integration.py
Integration tests for multi-region deployment workflows.

**Coverage:**
- ParallelDeployer + ConfigManager + VMProvisioning interaction
- RegionContext + Azure tag integration
- Deployment with config storage
- Partial failure handling
- Concurrency enforcement
- Performance with realistic delays

**Key Tests:**
- `test_deploy_to_multiple_regions_with_config_storage` - Complete deployment with persistence
- `test_deploy_with_region_context_integration` - Deployment with context updates
- `test_deploy_with_partial_failure_continues_others` - Resilient deployment
- `test_sync_from_azure_updates_local_config` - Azure tag sync

### test_failover_integration.py
Integration tests for failover scenarios.

**Coverage:**
- RegionFailover + health checks + Azure API
- Health check flow (Azure VM status + network + SSH)
- Failover execution with config updates
- Auto vs manual decision workflows
- Target health verification
- Data sync during failover

**Key Tests:**
- `test_health_check_all_systems_healthy` - Complete health check flow
- `test_health_check_network_unreachable` - Network failure detection
- `test_execute_failover_with_health_verification` - Complete failover
- `test_hybrid_mode_auto_failover_clear_failure` - Decision logic
- `test_failover_updates_region_context_metadata` - Context integration

### test_cross_region_sync_integration.py
Integration tests for cross-region synchronization.

**Coverage:**
- CrossRegionSync + SSH + Azure Blob integration
- Rsync strategy with SSH
- Azure Blob strategy with staging
- Strategy auto-selection with size estimation
- Multi-path sync
- Progress reporting

**Key Tests:**
- `test_sync_via_rsync_small_files` - Rsync strategy flow
- `test_sync_via_blob_large_files` - Blob strategy flow
- `test_auto_selects_rsync_for_small_files` - Strategy selection
- `test_blob_staging_cleanup` - Cleanup verification
- `test_sync_multiple_paths_partial_failure` - Resilient sync

## Running Integration Tests

```bash
# Run all integration tests
pytest tests/integration/multi_region/ -v

# Run specific module tests
pytest tests/integration/multi_region/test_failover_integration.py -v

# Run with coverage
pytest tests/integration/multi_region/ --cov=azlin.modules --cov-report=html

# Run slower tests
pytest tests/integration/multi_region/ --slow
```

## Test Patterns

### Mocking Azure CLI

```python
with patch('azlin.modules.parallel_deployer.subprocess.run') as mock_run:
    # Mock successful deployment
    mock_run.return_value = Mock(
        returncode=0,
        stdout=json.dumps({"publicIpAddress": "1.2.3.4"})
    )

    result = await deployer.deploy_to_regions(...)
```

### Mocking SSH Operations

```python
mock_ssh = AsyncMock()
mock_ssh.execute_remote_command = AsyncMock(
    return_value="342000000\t/home/azureuser/project"
)

sync = CrossRegionSync(config_manager=mock_config, ssh_connector=mock_ssh)
size = await sync.estimate_transfer_size(...)
```

### Tracking Concurrent Operations

```python
concurrent_count = 0
max_seen = 0
lock = asyncio.Lock()

async def track_concurrency():
    nonlocal concurrent_count, max_seen
    async with lock:
        concurrent_count += 1
        max_seen = max(max_seen, concurrent_count)

    await asyncio.sleep(0.1)  # Simulate work

    async with lock:
        concurrent_count -= 1

assert max_seen <= max_concurrent
```

## Writing New Integration Tests

When adding new integration tests:

1. **Test module interactions**: Focus on how modules work together
2. **Mock external services**: Azure CLI, SSH, network calls
3. **Use realistic data**: Actual region names, VM sizes, IP addresses
4. **Test error propagation**: How errors flow between modules
5. **Verify state changes**: Check config, context, metadata updates

### Good Integration Test Example

```python
@pytest.mark.asyncio
async def test_deploy_with_region_context_integration(self):
    """Test deployment with RegionContext metadata updates."""
    mock_config_manager = Mock()
    region_context = RegionContext(config_manager=mock_config_manager)
    deployer = ParallelDeployer(config_manager=mock_config_manager)

    # Mock VM provisioning
    with patch('azlin.modules.parallel_deployer.subprocess.run') as mock_run:
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps({"publicIpAddress": "1.2.3.4"})
        )

        result = await deployer.deploy_to_regions(
            regions=["eastus"],
            vm_config=Mock()
        )

        # Add to context
        region_context.add_region(
            region="eastus",
            vm_name=result.successful[0].vm_name,
            public_ip=result.successful[0].public_ip,
            is_primary=True
        )

        # Verify integration
        metadata = region_context.get_primary_region()
        assert metadata.region == "eastus"
        assert metadata.public_ip == "1.2.3.4"
```

## Test Status

All tests are currently marked with `pytest.skip("Module not yet implemented")`.

**Next Steps:**
1. Implement modules in `src/azlin/modules/`
2. Remove `pytest.skip()` decorators
3. Fix imports
4. Run tests to verify multi-module interactions

## Performance Targets

Integration tests should be:
- **Moderate speed**: <5 seconds per test
- **Multi-module**: Test 2+ modules together
- **Realistic mocks**: Use realistic Azure/SSH responses
- **State verification**: Verify state changes across modules

Current test count: 30+ integration tests

## Related Documentation

- Unit tests: `tests/unit/multi_region/README.md`
- E2E tests: `tests/e2e/multi_region/README.md`
- Architecture spec: `specs/MULTI_REGION_SPEC.md`
