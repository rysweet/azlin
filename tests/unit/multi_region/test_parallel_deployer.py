"""Unit tests for parallel_deployer.py module.

Testing pyramid: 60% unit tests
- Fast execution (<100ms per test)
- Heavily mocked external dependencies
- Focus on business logic and edge cases

Test coverage:
- DeploymentResult and MultiRegionResult dataclass behavior
- ParallelDeployer initialization
- Validation of input parameters
- Error handling for edge cases
- Success rate calculations
- Concurrency limits
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch
import pytest

# Module under test
from azlin.modules.parallel_deployer import (
    ParallelDeployer,
    DeploymentResult,
    DeploymentStatus,
    MultiRegionResult,
)


# ============================================================================
# UNIT TESTS - Dataclass Behavior (60%)
# ============================================================================


class TestDeploymentStatus:
    """Test DeploymentStatus enum."""

    def test_deployment_status_values(self):
        """Test that DeploymentStatus has expected values."""
        assert DeploymentStatus.PENDING.value == "pending"
        assert DeploymentStatus.IN_PROGRESS.value == "in_progress"
        assert DeploymentStatus.SUCCESS.value == "success"
        assert DeploymentStatus.FAILED.value == "failed"


class TestDeploymentResult:
    """Test DeploymentResult dataclass."""

    def test_deployment_result_creation_success(self):
        """Test creating a successful deployment result."""
result = DeploymentResult(
    region="eastus",
    status=DeploymentStatus.SUCCESS,
    vm_name="vm-eastus-123",
    public_ip="1.2.3.4",
    duration_seconds=180.5
)
assert result.region == "eastus"
assert result.status == DeploymentStatus.SUCCESS
assert result.vm_name == "vm-eastus-123"
assert result.public_ip == "1.2.3.4"
assert result.error is None
assert result.duration_seconds == 180.5

    def test_deployment_result_creation_failure(self):
        """Test creating a failed deployment result."""
result = DeploymentResult(
    region="westeurope",
    status=DeploymentStatus.FAILED,
    vm_name="vm-westeu-123",
    error="SkuNotAvailable: Standard_B2s not available in westeurope",
    duration_seconds=45.2
)
assert result.region == "westeurope"
assert result.status == DeploymentStatus.FAILED
assert result.public_ip is None
assert "SkuNotAvailable" in result.error

    def test_deployment_result_defaults(self):
        """Test DeploymentResult with default values."""
result = DeploymentResult(
    region="eastus",
    status=DeploymentStatus.PENDING,
    vm_name="vm-eastus-123"
)
assert result.public_ip is None
assert result.error is None
assert result.duration_seconds == 0.0


class TestMultiRegionResult:
    """Test MultiRegionResult dataclass."""

    def test_multi_region_result_all_success(self):
        """Test MultiRegionResult with all deployments successful."""
successful = [
    DeploymentResult("eastus", DeploymentStatus.SUCCESS, "vm-eastus", "1.2.3.4", None, 180.0),
    DeploymentResult("westus2", DeploymentStatus.SUCCESS, "vm-westus2", "5.6.7.8", None, 190.0),
    DeploymentResult("westeurope", DeploymentStatus.SUCCESS, "vm-westeu", "9.10.11.12", None, 210.0)
]
result = MultiRegionResult(
    total_regions=3,
    successful=successful,
    failed=[],
    total_duration_seconds=210.0
)
assert result.total_regions == 3
assert len(result.successful) == 3
assert len(result.failed) == 0
assert result.success_rate == 1.0

    def test_multi_region_result_partial_failure(self):
        """Test MultiRegionResult with partial failures."""
successful = [
    DeploymentResult("eastus", DeploymentStatus.SUCCESS, "vm-eastus", "1.2.3.4", None, 180.0),
    DeploymentResult("westus2", DeploymentStatus.SUCCESS, "vm-westus2", "5.6.7.8", None, 190.0)
]
failed = [
    DeploymentResult("westeurope", DeploymentStatus.FAILED, "vm-westeu", None, "SkuNotAvailable", 45.0)
]
result = MultiRegionResult(
    total_regions=3,
    successful=successful,
    failed=failed,
    total_duration_seconds=190.0
)
assert result.total_regions == 3
assert len(result.successful) == 2
assert len(result.failed) == 1
assert result.success_rate == pytest.approx(0.667, rel=0.01)

    def test_multi_region_result_all_failed(self):
        """Test MultiRegionResult with all deployments failed."""
failed = [
    DeploymentResult("eastus", DeploymentStatus.FAILED, "vm-eastus", None, "NetworkError", 30.0),
    DeploymentResult("westus2", DeploymentStatus.FAILED, "vm-westus2", None, "QuotaExceeded", 25.0)
]
result = MultiRegionResult(
    total_regions=2,
    successful=[],
    failed=failed,
    total_duration_seconds=30.0
)
assert result.total_regions == 2
assert len(result.successful) == 0
assert len(result.failed) == 2
assert result.success_rate == 0.0

    def test_multi_region_result_success_rate_edge_case_zero_regions(self):
        """Test success_rate calculation with zero total regions."""
result = MultiRegionResult(
    total_regions=0,
    successful=[],
    failed=[],
    total_duration_seconds=0.0
)
assert result.success_rate == 0.0


# ============================================================================
# UNIT TESTS - ParallelDeployer Class (60%)
# ============================================================================


class TestParallelDeployerInit:
    """Test ParallelDeployer initialization."""

    def test_parallel_deployer_init_defaults(self):
        """Test ParallelDeployer initialization with defaults."""
mock_config = Mock()
deployer = ParallelDeployer(config_manager=mock_config)
assert deployer.config_manager == mock_config
assert deployer.max_concurrent == 10

    def test_parallel_deployer_init_custom_concurrent(self):
        """Test ParallelDeployer initialization with custom max_concurrent."""
mock_config = Mock()
deployer = ParallelDeployer(config_manager=mock_config, max_concurrent=5)
assert deployer.max_concurrent == 5

    def test_parallel_deployer_init_invalid_max_concurrent_negative(self):
        """Test ParallelDeployer rejects negative max_concurrent."""
mock_config = Mock()
with pytest.raises(ValueError, match="max_concurrent must be positive"):
    ParallelDeployer(config_manager=mock_config, max_concurrent=-1)

    def test_parallel_deployer_init_invalid_max_concurrent_zero(self):
        """Test ParallelDeployer rejects zero max_concurrent."""
mock_config = Mock()
with pytest.raises(ValueError, match="max_concurrent must be positive"):
    ParallelDeployer(config_manager=mock_config, max_concurrent=0)


class TestParallelDeployerValidation:
    """Test input validation for ParallelDeployer methods."""

    def test_deploy_to_regions_empty_list_raises_error(self):
        """Test that empty regions list raises ValueError."""
mock_config = Mock()
deployer = ParallelDeployer(config_manager=mock_config)
mock_vm_config = Mock()
with pytest.raises(ValueError, match="regions list cannot be empty"):
    asyncio.run(deployer.deploy_to_regions(regions=[], vm_config=mock_vm_config))

    def test_deploy_to_regions_none_regions_raises_error(self):
        """Test that None regions raises TypeError."""
mock_config = Mock()
deployer = ParallelDeployer(config_manager=mock_config)
mock_vm_config = Mock()
with pytest.raises(TypeError, match="regions cannot be None"):
    asyncio.run(deployer.deploy_to_regions(regions=None, vm_config=mock_vm_config))

    def test_deploy_to_regions_none_vm_config_raises_error(self):
        """Test that None vm_config raises TypeError."""
mock_config = Mock()
deployer = ParallelDeployer(config_manager=mock_config)
with pytest.raises(TypeError, match="vm_config cannot be None"):
    asyncio.run(deployer.deploy_to_regions(regions=["eastus"], vm_config=None))

    def test_deploy_to_regions_invalid_region_names(self):
        """Test that invalid region names raise ValueError."""
mock_config = Mock()
deployer = ParallelDeployer(config_manager=mock_config)
mock_vm_config = Mock()
with pytest.raises(ValueError, match="Invalid region"):
    asyncio.run(deployer.deploy_to_regions(
        regions=["eastus", "invalid-region-name", "westus2"],
        vm_config=mock_vm_config
    ))


class TestParallelDeployerDeployment:
    """Test deployment logic of ParallelDeployer."""

    @pytest.mark.asyncio
    async def test_deploy_single_region_success(self):
        """Test successful deployment to a single region."""
mock_config = Mock()
deployer = ParallelDeployer(config_manager=mock_config)
mock_vm_config = Mock()
        #
# Mock the _deploy_single_region method
with patch.object(deployer, '_deploy_single_region', new_callable=AsyncMock) as mock_deploy:
    mock_deploy.return_value = DeploymentResult(
        region="eastus",
        status=DeploymentStatus.SUCCESS,
        vm_name="vm-eastus-123",
        public_ip="1.2.3.4",
        duration_seconds=180.0
    )
        #
    result = await deployer.deploy_to_regions(
        regions=["eastus"],
        vm_config=mock_vm_config
    )
        #
    assert result.total_regions == 1
    assert len(result.successful) == 1
    assert len(result.failed) == 0
    assert result.success_rate == 1.0

    @pytest.mark.asyncio
    async def test_deploy_multiple_regions_all_success(self):
        """Test successful deployment to multiple regions."""
mock_config = Mock()
deployer = ParallelDeployer(config_manager=mock_config, max_concurrent=3)
mock_vm_config = Mock()
        #
# Mock successful deployments for all regions
async def mock_deploy(region, vm_config):
    await asyncio.sleep(0.01)  # Simulate deployment time
    return DeploymentResult(
        region=region,
        status=DeploymentStatus.SUCCESS,
        vm_name=f"vm-{region}-123",
        public_ip=f"1.2.3.{hash(region) % 255}",
        duration_seconds=180.0
    )
        #
with patch.object(deployer, '_deploy_single_region', side_effect=mock_deploy):
    result = await deployer.deploy_to_regions(
        regions=["eastus", "westus2", "westeurope"],
        vm_config=mock_vm_config
    )
        #
    assert result.total_regions == 3
    assert len(result.successful) == 3
    assert len(result.failed) == 0
    assert result.success_rate == 1.0

    @pytest.mark.asyncio
    async def test_deploy_multiple_regions_partial_failure(self):
        """Test deployment with partial failures."""
mock_config = Mock()
deployer = ParallelDeployer(config_manager=mock_config)
mock_vm_config = Mock()
        #
async def mock_deploy(region, vm_config):
    await asyncio.sleep(0.01)
    if region == "westeurope":
        return DeploymentResult(
            region=region,
            status=DeploymentStatus.FAILED,
            vm_name=f"vm-{region}-123",
            error="SkuNotAvailable: Standard_B2s not available",
            duration_seconds=45.0
        )
    return DeploymentResult(
        region=region,
        status=DeploymentStatus.SUCCESS,
        vm_name=f"vm-{region}-123",
        public_ip=f"1.2.3.{hash(region) % 255}",
        duration_seconds=180.0
    )
        #
with patch.object(deployer, '_deploy_single_region', side_effect=mock_deploy):
    result = await deployer.deploy_to_regions(
        regions=["eastus", "westus2", "westeurope"],
        vm_config=mock_vm_config
    )
        #
    assert result.total_regions == 3
    assert len(result.successful) == 2
    assert len(result.failed) == 1
    assert result.success_rate == pytest.approx(0.667, rel=0.01)

    @pytest.mark.asyncio
    async def test_deploy_respects_max_concurrent_limit(self):
        """Test that max_concurrent limit is respected during deployment."""
mock_config = Mock()
max_concurrent = 2
deployer = ParallelDeployer(config_manager=mock_config, max_concurrent=max_concurrent)
mock_vm_config = Mock()
        #
# Track concurrent executions
concurrent_count = 0
max_seen = 0
lock = asyncio.Lock()
        #
async def mock_deploy(region, vm_config):
    nonlocal concurrent_count, max_seen
    async with lock:
        concurrent_count += 1
        max_seen = max(max_seen, concurrent_count)
        #
    await asyncio.sleep(0.05)  # Simulate deployment time
        #
    async with lock:
        concurrent_count -= 1
        #
    return DeploymentResult(
        region=region,
        status=DeploymentStatus.SUCCESS,
        vm_name=f"vm-{region}-123",
        public_ip="1.2.3.4",
        duration_seconds=50.0
    )
        #
with patch.object(deployer, '_deploy_single_region', side_effect=mock_deploy):
    result = await deployer.deploy_to_regions(
        regions=["eastus", "westus2", "westeurope", "northeurope"],
        vm_config=mock_vm_config
    )
        #
    assert max_seen <= max_concurrent, f"Exceeded max_concurrent: {max_seen} > {max_concurrent}"
    assert result.total_regions == 4
    assert len(result.successful) == 4

    @pytest.mark.asyncio
    async def test_deploy_timeout_handling(self):
        """Test that deployment timeout is handled properly."""
mock_config = Mock()
deployer = ParallelDeployer(config_manager=mock_config)
mock_vm_config = Mock()
        #
async def mock_deploy_timeout(region, vm_config):
    if region == "eastus":
        await asyncio.sleep(0.1)  # Simulate timeout
        raise asyncio.TimeoutError("Deployment timed out")
    return DeploymentResult(
        region=region,
        status=DeploymentStatus.SUCCESS,
        vm_name=f"vm-{region}-123",
        public_ip="1.2.3.4",
        duration_seconds=180.0
    )
        #
with patch.object(deployer, '_deploy_single_region', side_effect=mock_deploy_timeout):
    result = await deployer.deploy_to_regions(
        regions=["eastus", "westus2"],
        vm_config=mock_vm_config
    )
        #
    assert result.total_regions == 2
    assert len(result.successful) == 1
    assert len(result.failed) == 1
    assert "timeout" in result.failed[0].error.lower()


class TestParallelDeployerErrorHandling:
    """Test error handling in ParallelDeployer."""

    @pytest.mark.asyncio
    async def test_deploy_all_regions_fail_raises_deployment_error(self):
        """Test that all regions failing raises DeploymentError."""
mock_config = Mock()
deployer = ParallelDeployer(config_manager=mock_config)
mock_vm_config = Mock()
        #
async def mock_deploy_fail(region, vm_config):
    return DeploymentResult(
        region=region,
        status=DeploymentStatus.FAILED,
        vm_name=f"vm-{region}-123",
        error="NetworkError: Failed to connect",
        duration_seconds=30.0
    )
        #
with patch.object(deployer, '_deploy_single_region', side_effect=mock_deploy_fail):
    with pytest.raises(Exception, match="All regions failed"):
        await deployer.deploy_to_regions(
            regions=["eastus", "westus2"],
            vm_config=mock_vm_config
        )

    @pytest.mark.asyncio
    async def test_deploy_handles_unexpected_exceptions(self):
        """Test that unexpected exceptions are handled gracefully."""
mock_config = Mock()
deployer = ParallelDeployer(config_manager=mock_config)
mock_vm_config = Mock()
        #
async def mock_deploy_exception(region, vm_config):
    if region == "eastus":
        raise RuntimeError("Unexpected error")
    return DeploymentResult(
        region=region,
        status=DeploymentStatus.SUCCESS,
        vm_name=f"vm-{region}-123",
        public_ip="1.2.3.4",
        duration_seconds=180.0
    )
        #
with patch.object(deployer, '_deploy_single_region', side_effect=mock_deploy_exception):
    result = await deployer.deploy_to_regions(
        regions=["eastus", "westus2"],
        vm_config=mock_vm_config
    )
        #
    assert result.total_regions == 2
    assert len(result.successful) == 1
    assert len(result.failed) == 1
    assert "Unexpected error" in result.failed[0].error


# ============================================================================
# UNIT TESTS - Success Rate Calculations (60%)
# ============================================================================


class TestSuccessRateCalculations:
    """Test success rate calculation edge cases."""

    def test_success_rate_100_percent(self):
        """Test success rate with 100% success."""
result = MultiRegionResult(
    total_regions=5,
    successful=[Mock()] * 5,
    failed=[],
    total_duration_seconds=300.0
)
assert result.success_rate == 1.0

    def test_success_rate_0_percent(self):
        """Test success rate with 0% success."""
result = MultiRegionResult(
    total_regions=5,
    successful=[],
    failed=[Mock()] * 5,
    total_duration_seconds=150.0
)
assert result.success_rate == 0.0

    def test_success_rate_50_percent(self):
        """Test success rate with 50% success."""
result = MultiRegionResult(
    total_regions=4,
    successful=[Mock()] * 2,
    failed=[Mock()] * 2,
    total_duration_seconds=200.0
)
assert result.success_rate == 0.5

    def test_success_rate_single_region_success(self):
        """Test success rate with single successful region."""
result = MultiRegionResult(
    total_regions=1,
    successful=[Mock()],
    failed=[],
    total_duration_seconds=180.0
)
assert result.success_rate == 1.0

    def test_success_rate_single_region_failure(self):
        """Test success rate with single failed region."""
result = MultiRegionResult(
    total_regions=1,
    successful=[],
    failed=[Mock()],
    total_duration_seconds=30.0
)
assert result.success_rate == 0.0
