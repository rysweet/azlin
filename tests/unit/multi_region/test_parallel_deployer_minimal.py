"""Minimal unit tests for parallel_deployer.py module."""

from unittest.mock import Mock

import pytest

from azlin.modules.parallel_deployer import (
    DeploymentResult,
    DeploymentStatus,
    MultiRegionResult,
    ParallelDeployer,
)


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
            duration_seconds=180.5,
        )
        assert result.region == "eastus"
        assert result.status == DeploymentStatus.SUCCESS
        assert result.vm_name == "vm-eastus-123"
        assert result.public_ip == "1.2.3.4"
        assert result.error is None
        assert result.duration_seconds == 180.5


class TestMultiRegionResult:
    """Test MultiRegionResult dataclass."""

    def test_multi_region_result_all_success(self):
        """Test MultiRegionResult with all deployments successful."""
        successful = [
            DeploymentResult(
                "eastus", DeploymentStatus.SUCCESS, "vm-eastus", "1.2.3.4", None, 180.0
            ),
            DeploymentResult(
                "westus2", DeploymentStatus.SUCCESS, "vm-westus2", "5.6.7.8", None, 190.0
            ),
        ]
        result = MultiRegionResult(
            total_regions=2, successful=successful, failed=[], total_duration_seconds=190.0
        )
        assert result.total_regions == 2
        assert len(result.successful) == 2
        assert len(result.failed) == 0
        assert result.success_rate == 1.0


class TestParallelDeployerInit:
    """Test ParallelDeployer initialization."""

    def test_parallel_deployer_init_defaults(self):
        """Test ParallelDeployer initialization with defaults."""
        mock_config = Mock()
        deployer = ParallelDeployer(config_manager=mock_config)
        assert deployer.config_manager == mock_config
        assert deployer.max_concurrent == 10

    def test_parallel_deployer_init_invalid_max_concurrent_negative(self):
        """Test ParallelDeployer rejects negative max_concurrent."""
        mock_config = Mock()
        with pytest.raises(ValueError, match="max_concurrent must be positive"):
            ParallelDeployer(config_manager=mock_config, max_concurrent=-1)


class TestParallelDeployerValidation:
    """Test input validation for ParallelDeployer methods."""

    @pytest.mark.asyncio
    async def test_deploy_to_regions_empty_list_raises_error(self):
        """Test that empty regions list raises ValueError."""
        mock_config = Mock()
        deployer = ParallelDeployer(config_manager=mock_config)
        mock_vm_config = Mock()
        with pytest.raises(ValueError, match="regions list cannot be empty"):
            await deployer.deploy_to_regions(regions=[], vm_config=mock_vm_config)

    @pytest.mark.asyncio
    async def test_deploy_to_regions_none_regions_raises_error(self):
        """Test that None regions raises TypeError."""
        mock_config = Mock()
        deployer = ParallelDeployer(config_manager=mock_config)
        mock_vm_config = Mock()
        with pytest.raises(TypeError, match="regions cannot be None"):
            await deployer.deploy_to_regions(regions=None, vm_config=mock_vm_config)


class TestParallelDeployerDeployment:
    """Test deployment logic of ParallelDeployer."""

    @pytest.mark.skip(reason="Requires proper VM config mocking - fix in follow-up PR")
    @pytest.mark.asyncio
    async def test_deploy_multiple_regions_all_success(self):
        """Test successful deployment to multiple regions."""
        mock_config = Mock()
        deployer = ParallelDeployer(config_manager=mock_config, max_concurrent=3)
        mock_vm_config = Mock()

        result = await deployer.deploy_to_regions(
            regions=["eastus", "westus2", "westeurope"], vm_config=mock_vm_config
        )

        assert result.total_regions == 3
        assert len(result.successful) == 3
        assert len(result.failed) == 0
        assert result.success_rate == 1.0
