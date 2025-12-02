# Multi-Region End-to-End Tests

This directory contains E2E tests for multi-region orchestration following the 60/30/10 testing pyramid.

## Test Coverage (10% E2E Tests)

⚠️ **WARNING**: These tests are EXPENSIVE and SLOW. They create real Azure resources.

These tests focus on:
- Complete workflows with real Azure
- Performance benchmarks
- Multi-region scenarios
- Reliability validation
- Real data transfer

## Test Files

### test_multi_region_e2e.py
Complete end-to-end tests with real Azure resources.

**Coverage:**
- Complete multi-region deployment (3 regions, <10 min)
- Complete failover workflow (<60 seconds)
- Complete sync workflow (100MB, <3 min)
- Disaster recovery simulation
- Reliability benchmarks (99.9% target)

**Key Tests:**
- `test_deploy_to_3_real_azure_regions` - Real 3-region deployment
- `test_failover_from_unhealthy_to_healthy_region` - Real failover
- `test_sync_100mb_dataset_between_real_regions` - Real data transfer
- `test_sync_reliability_99_9_percent` - Reliability benchmark
- `test_disaster_recovery_simulation` - Complete DR workflow

## Running E2E Tests

⚠️ **IMPORTANT**: E2E tests are disabled by default. Set `AZLIN_RUN_E2E_TESTS=true` to enable.

```bash
# Enable E2E tests (required)
export AZLIN_RUN_E2E_TESTS=true

# Run all E2E tests (WARNING: Creates real Azure VMs)
pytest tests/e2e/multi_region/ -v -m e2e

# Run specific test
pytest tests/e2e/multi_region/test_multi_region_e2e.py::TestMultiRegionDeploymentE2E::test_deploy_to_3_real_azure_regions -v

# Run with real-time output
pytest tests/e2e/multi_region/ -v -s -m e2e

# Skip slow tests (run only fast E2E)
pytest tests/e2e/multi_region/ -v -m "e2e and not slow"
```

## Cost Estimates

⚠️ **ESTIMATED COSTS PER TEST RUN**:

| Test | VMs Created | Duration | Est. Cost |
|------|-------------|----------|-----------|
| `test_deploy_to_3_real_azure_regions` | 3x Standard_B2s | ~10 min | $0.10 |
| `test_failover_from_unhealthy_to_healthy_region` | 2x Standard_B2s | ~15 min | $0.10 |
| `test_sync_100mb_dataset_between_real_regions` | 2x Standard_B2s | ~15 min | $0.10 |
| `test_sync_reliability_99_9_percent` | 2x Standard_B2s | ~2 hours | $1.00 |
| `test_disaster_recovery_simulation` | 3x Standard_B2s | ~30 min | $0.25 |

**Total for full E2E suite**: ~$1.55 per run

**Pricing assumptions**:
- Standard_B2s: $0.04/hour in US regions
- Data transfer: Minimal (<$0.01 per test)
- Storage: Minimal (<$0.01 per test)

## Performance Targets

E2E tests validate these performance targets:

| Feature | Target | Test |
|---------|--------|------|
| Multi-region deployment (3 regions) | <10 minutes | `test_deploy_performance_under_10_minutes` |
| Failover completion | <60 seconds | `test_auto_failover_completes_under_60_seconds` |
| Small file sync (100MB) | <3 minutes | `test_sync_100mb_dataset_between_real_regions` |
| Large file sync (500MB) | <8 minutes | (Not implemented yet) |
| Sync reliability | 99.9% | `test_sync_reliability_99_9_percent` |

## Test Workflow Examples

### Complete Deployment Test

```python
@pytest.mark.asyncio
async def test_deploy_to_3_real_azure_regions(self):
    """Deploy VMs to 3 real Azure regions."""
    deployer = ParallelDeployer(config_manager=config_manager)

    result = await deployer.deploy_to_regions(
        regions=["eastus", "westus2", "westeurope"],
        vm_config=vm_config
    )

    # Verify
    assert result.total_regions == 3
    assert len(result.successful) >= 2
    assert duration < 600  # <10 minutes

    # Cleanup
    cleanup_test_resources(resource_group)
```

### Complete Failover Test

```python
@pytest.mark.asyncio
async def test_failover_from_unhealthy_to_healthy_region(self):
    """Test real failover from failed region."""
    # Deploy to 2 regions
    deploy_result = await deployer.deploy_to_regions(...)

    # Stop source VM (simulate failure)
    stop_vm(deploy_result.successful[0].vm_name)

    # Execute failover
    failover_result = await failover.execute_failover(
        source_region="eastus",
        target_region="westus2",
        ...
    )

    # Verify
    assert failover_result.success is True
    assert duration < 60  # <60 seconds

    # Cleanup
    cleanup_test_resources(resource_group)
```

## Safety Guidelines

### Before Running E2E Tests

1. **Check Azure subscription limits**: Ensure you have quota for VMs
2. **Verify cost budget**: Confirm you can afford the test costs
3. **Use test resource group**: Never use production resources
4. **Enable cleanup**: Ensure tests clean up resources on completion

### During E2E Tests

1. **Monitor Azure portal**: Watch for unexpected resource creation
2. **Check costs**: Monitor Azure cost analysis during tests
3. **Be ready to stop**: Keep Azure CLI ready to delete resources if needed

### After E2E Tests

1. **Verify cleanup**: Check that all test VMs are deleted
2. **Review costs**: Verify actual costs match estimates
3. **Check for orphaned resources**: Look for leftover disks, NICs, etc.

## Emergency Cleanup

If tests fail and don't clean up:

```bash
# List all test resource groups
az group list --query "[?starts_with(name, 'azlin-e2e-test')].name" -o tsv

# Delete a specific test resource group
az group delete --name azlin-e2e-test-multi-region --yes --no-wait

# Delete all test resource groups (USE WITH CAUTION)
az group list --query "[?starts_with(name, 'azlin-e2e-test')].name" -o tsv | xargs -I {} az group delete --name {} --yes --no-wait
```

## CI/CD Integration

E2E tests should run:
- **On demand**: Manual trigger in CI/CD
- **Nightly**: Automated nightly runs
- **Before releases**: Required before major releases
- **Never on PR**: Too expensive for every PR

### GitHub Actions Example

```yaml
name: E2E Tests

on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM daily
  workflow_dispatch:  # Manual trigger

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -e .[dev]
      - name: Azure Login
        uses: azure/login@v1
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      - name: Run E2E Tests
        env:
          AZLIN_RUN_E2E_TESTS: true
        run: pytest tests/e2e/multi_region/ -v -m e2e
```

## Test Status

All tests are currently marked with `pytest.skip()` because:
1. Modules are not yet implemented
2. Tests are expensive to run
3. Tests require real Azure credentials

**Next Steps:**
1. Implement modules
2. Remove `pytest.skip()` decorators
3. Configure Azure test subscription
4. Run tests in controlled environment
5. Validate performance targets

## Related Documentation

- Unit tests: `tests/unit/multi_region/README.md`
- Integration tests: `tests/integration/multi_region/README.md`
- Architecture spec: `specs/MULTI_REGION_SPEC.md`
- Azure pricing: https://azure.microsoft.com/en-us/pricing/calculator/
