"""Integration tests for cross-region NFS access with private endpoints.

Tests the complete workflow for accessing NFS storage across regions:
- Cost estimation for cross-region access
- Access strategy analysis
- Private endpoint creation
- VNet peering setup
- Private DNS zone configuration
- Data replication workflows

These tests verify component integration with mocked Azure CLI.
"""

import json
import subprocess
from unittest.mock import Mock, patch

import pytest

from azlin.modules.cost_estimator import CostEstimator
from azlin.modules.interaction_handler import MockInteractionHandler
from azlin.modules.nfs_provisioner import (
    AccessStrategy,
    NetworkConfigurationError,
    NFSProvisioner,
    ValidationError,
)
from azlin.modules.resource_orchestrator import (
    DecisionAction,
    NFSOptions,
    ResourceOrchestrator,
    ResourceType,
)


class TestCrossRegionCostEstimation:
    """Test cost estimation for cross-region NFS access."""

    def test_estimate_private_endpoint_cost_no_transfer(self):
        """Test private endpoint cost with no data transfer."""
        # Act
        cost = CostEstimator.estimate_private_endpoint_cost(0)

        # Assert
        assert cost == 7.30  # Base private endpoint cost
        formatted = CostEstimator.format_cost(cost)
        assert formatted == "$7.30/month"

    def test_estimate_private_endpoint_cost_with_transfer(self):
        """Test private endpoint cost with data transfer."""
        # Act
        cost = CostEstimator.estimate_private_endpoint_cost(100)

        # Assert
        # $7.30 (endpoint) + $1.00 (100 GB * $0.01/GB)
        assert cost == 8.30
        formatted = CostEstimator.format_cost(cost)
        assert formatted == "$8.30/month"

    def test_estimate_private_endpoint_cost_large_transfer(self):
        """Test private endpoint cost with large data transfer."""
        # Act - 1 TB transfer
        cost = CostEstimator.estimate_private_endpoint_cost(1024)

        # Assert
        # $7.30 + $10.24 (1024 GB * $0.01/GB)
        assert cost == 17.54

    def test_estimate_private_endpoint_cost_negative_transfer(self):
        """Test error on negative data transfer."""
        # Act & Assert
        with pytest.raises(ValueError, match="non-negative"):
            CostEstimator.estimate_private_endpoint_cost(-100)

    def test_estimate_nfs_cost_premium(self):
        """Test NFS Premium tier cost estimation."""
        # Act
        cost = CostEstimator.estimate_nfs_cost(100, "Premium")

        # Assert
        assert cost == 20.00  # 100 GB * $0.20/GB

    def test_estimate_nfs_cost_standard(self):
        """Test NFS Standard tier cost estimation."""
        # Act
        cost = CostEstimator.estimate_nfs_cost(500, "Standard")

        # Assert
        assert cost == 30.00  # 500 GB * $0.06/GB

    def test_estimate_nfs_cost_invalid_tier(self):
        """Test error on invalid tier."""
        # Act & Assert
        with pytest.raises(ValueError, match="Invalid tier"):
            CostEstimator.estimate_nfs_cost(100, "InvalidTier")

    def test_estimate_nfs_cost_zero_size(self):
        """Test error on zero size."""
        # Act & Assert
        with pytest.raises(ValueError, match="positive"):
            CostEstimator.estimate_nfs_cost(0, "Premium")


class TestNFSAccessStrategyAnalysis:
    """Test NFS access strategy analysis."""

    @patch("azlin.modules.nfs_provisioner.StorageManager.get_storage")
    def test_analyze_same_region_recommends_direct(self, mock_get_storage):
        """Test same region recommends direct access."""
        # Arrange
        mock_get_storage.return_value = Mock(
            size_gb=100,
            tier="Premium",
        )

        # Act
        analysis = NFSProvisioner.analyze_nfs_access(
            storage_account="mystorageacct",
            source_region="eastus",
            target_region="eastus",
            resource_group="test-rg",
        )

        # Assert
        assert analysis.same_region is True
        assert analysis.recommended_strategy == AccessStrategy.DIRECT
        assert analysis.estimated_latency_ms < 5  # Same region should be very low
        assert analysis.estimated_cost_monthly == 0.0  # No additional cost

        # Verify direct access strategy exists
        direct_strategy = analysis.strategies[AccessStrategy.DIRECT]
        assert direct_strategy["cost_monthly"] == 0.0
        assert "lowest latency" in str(direct_strategy["pros"]).lower()

    @patch("azlin.modules.nfs_provisioner.StorageManager.get_storage")
    def test_analyze_cross_region_includes_all_strategies(self, mock_get_storage):
        """Test cross-region analysis includes all strategies."""
        # Arrange
        mock_get_storage.return_value = Mock(
            size_gb=100,
            tier="Premium",
        )

        # Act
        analysis = NFSProvisioner.analyze_nfs_access(
            storage_account="mystorageacct",
            source_region="eastus",
            target_region="westus",
            resource_group="test-rg",
        )

        # Assert
        assert analysis.same_region is False
        assert len(analysis.strategies) >= 3  # At least 3 strategies

        # Verify all strategies present
        assert AccessStrategy.PRIVATE_ENDPOINT in analysis.strategies
        assert AccessStrategy.NEW_STORAGE in analysis.strategies
        assert AccessStrategy.REPLICATE in analysis.strategies

        # Private endpoint should have cost
        pe_strategy = analysis.strategies[AccessStrategy.PRIVATE_ENDPOINT]
        assert pe_strategy["cost_monthly"] > 0

    @patch("azlin.modules.nfs_provisioner.StorageManager.get_storage")
    def test_analyze_cross_region_recommends_cheaper_option(self, mock_get_storage):
        """Test recommendation based on cost comparison."""
        # Arrange - Small storage makes new storage cheaper
        mock_get_storage.return_value = Mock(
            size_gb=50,  # Small size
            tier="Premium",
        )

        # Act
        analysis = NFSProvisioner.analyze_nfs_access(
            storage_account="mystorageacct",
            source_region="eastus",
            target_region="westus",
            resource_group="test-rg",
            estimated_monthly_transfer_gb=100,
        )

        # Assert
        # With small storage, replication should be recommended
        # (new storage $10/mo vs private endpoint $8.30/mo + transfer)
        assert analysis.recommended_strategy in [
            AccessStrategy.REPLICATE,
            AccessStrategy.PRIVATE_ENDPOINT,
        ]

    def test_analyze_validates_inputs(self):
        """Test input validation for analysis."""
        # Test empty storage account
        with pytest.raises(ValidationError, match="Storage account"):
            NFSProvisioner.analyze_nfs_access(
                storage_account="",
                source_region="eastus",
                target_region="westus",
                resource_group="test-rg",
            )

        # Test invalid characters
        with pytest.raises(ValidationError, match="unsafe character"):
            NFSProvisioner.analyze_nfs_access(
                storage_account="storage;account",
                source_region="eastus",
                target_region="westus",
                resource_group="test-rg",
            )


class TestPrivateEndpointCreation:
    """Test private endpoint creation workflow."""

    @patch("subprocess.run")
    def test_create_private_endpoint_success(self, mock_run):
        """Test successful private endpoint creation."""
        # Arrange
        mock_run.side_effect = [
            # Get storage account resource ID
            Mock(
                returncode=0,
                stdout="/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Storage/storageAccounts/mystorageacct\n",
            ),
            # Get subnet resource ID
            Mock(
                returncode=0,
                stdout="/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Network/virtualNetworks/my-vnet/subnets/my-subnet\n",
            ),
            # Create private endpoint
            Mock(
                returncode=0,
                stdout=json.dumps(
                    {
                        "name": "my-pe",
                        "provisioningState": "Succeeded",
                        "customDnsConfigs": [{"ipAddresses": ["10.0.1.5"]}],
                    }
                ),
            ),
        ]

        # Act
        endpoint = NFSProvisioner.create_private_endpoint(
            name="my-pe",
            resource_group="test-rg",
            region="westus",
            vnet_name="my-vnet",
            subnet_name="my-subnet",
            storage_account="mystorageacct",
            storage_resource_group="storage-rg",
        )

        # Assert
        assert endpoint.name == "my-pe"
        assert endpoint.resource_group == "test-rg"
        assert endpoint.region == "westus"
        assert endpoint.storage_account == "mystorageacct"
        assert endpoint.private_ip == "10.0.1.5"
        assert endpoint.connection_state == "Succeeded"

    @patch("subprocess.run")
    def test_create_private_endpoint_timeout(self, mock_run):
        """Test private endpoint creation timeout handling."""
        # Arrange
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="az", timeout=30)

        # Act & Assert
        with pytest.raises(NetworkConfigurationError, match="private endpoint"):
            NFSProvisioner.create_private_endpoint(
                name="my-pe",
                resource_group="test-rg",
                region="westus",
                vnet_name="my-vnet",
                subnet_name="my-subnet",
                storage_account="mystorageacct",
                storage_resource_group="storage-rg",
            )

    def test_create_private_endpoint_validates_inputs(self):
        """Test input validation for private endpoint creation."""
        # Test empty name
        with pytest.raises(ValidationError, match="Private endpoint"):
            NFSProvisioner.create_private_endpoint(
                name="",
                resource_group="test-rg",
                region="westus",
                vnet_name="my-vnet",
                subnet_name="my-subnet",
                storage_account="mystorageacct",
                storage_resource_group="storage-rg",
            )


class TestVNetPeeringCreation:
    """Test VNet peering creation workflow."""

    @patch("subprocess.run")
    def test_create_vnet_peering_bidirectional(self, mock_run):
        """Test bidirectional VNet peering creation."""
        # Arrange
        mock_run.side_effect = [
            # Get remote VNet resource ID
            Mock(
                returncode=0,
                stdout="/subscriptions/sub/resourceGroups/remote-rg/providers/Microsoft.Network/virtualNetworks/remote-vnet\n",
            ),
            # Create local->remote peering
            Mock(
                returncode=0,
                stdout=json.dumps(
                    {
                        "name": "local-to-remote",
                        "peeringState": "Connected",
                    }
                ),
            ),
            # Get local VNet resource ID
            Mock(
                returncode=0,
                stdout="/subscriptions/sub/resourceGroups/local-rg/providers/Microsoft.Network/virtualNetworks/local-vnet\n",
            ),
            # Create remote->local peering
            Mock(returncode=0, stdout=""),
        ]

        # Act
        peering = NFSProvisioner.create_vnet_peering(
            name="local-to-remote",
            resource_group="local-rg",
            local_vnet="local-vnet",
            remote_vnet="remote-vnet",
            remote_vnet_resource_group="remote-rg",
            allow_forwarded_traffic=True,
        )

        # Assert
        assert peering.name == "local-to-remote"
        assert peering.local_vnet == "local-vnet"
        assert peering.remote_vnet == "remote-vnet"
        assert peering.peering_state == "Connected"
        assert peering.allow_forwarded_traffic is True

        # Verify both peerings were created
        assert mock_run.call_count == 4

    @patch("subprocess.run")
    def test_create_vnet_peering_failure(self, mock_run):
        """Test VNet peering creation failure handling."""
        # Arrange
        mock_run.side_effect = [
            # Get remote VNet resource ID - success
            Mock(returncode=0, stdout="/subscriptions/.../remote-vnet\n"),
            # Create peering - FAILS
            Mock(returncode=1, stderr="PeeringAlreadyExists"),
        ]

        # Act & Assert
        with pytest.raises(NetworkConfigurationError, match="VNet peering"):
            NFSProvisioner.create_vnet_peering(
                name="my-peering",
                resource_group="local-rg",
                local_vnet="local-vnet",
                remote_vnet="remote-vnet",
                remote_vnet_resource_group="remote-rg",
            )


class TestPrivateDNSZoneConfiguration:
    """Test private DNS zone configuration workflow."""

    @patch("subprocess.run")
    def test_configure_private_dns_zone_success(self, mock_run):
        """Test successful private DNS zone configuration."""
        # Arrange
        mock_run.side_effect = [
            # Create DNS zone
            Mock(returncode=0),
            # Get VNet resource ID for link 1
            Mock(returncode=0, stdout="/subscriptions/.../vnet1\n"),
            # Link DNS zone to VNet 1
            Mock(returncode=0),
            # Get VNet resource ID for link 2
            Mock(returncode=0, stdout="/subscriptions/.../vnet2\n"),
            # Link DNS zone to VNet 2
            Mock(returncode=0),
            # Create DNS zone group
            Mock(returncode=0),
        ]

        # Act
        dns_zone = NFSProvisioner.configure_private_dns_zone(
            resource_group="test-rg",
            vnet_names=["vnet1", "vnet2"],
            storage_account="mystorageacct",
            private_endpoint_name="my-pe",
        )

        # Assert
        assert dns_zone.name == "privatelink.file.core.windows.net"
        assert dns_zone.resource_group == "test-rg"
        assert len(dns_zone.linked_vnets) == 2
        assert "vnet1" in dns_zone.linked_vnets
        assert "vnet2" in dns_zone.linked_vnets

    @patch("subprocess.run")
    def test_configure_private_dns_zone_link_failure(self, mock_run):
        """Test DNS zone configuration with link failure."""
        # Arrange
        mock_run.side_effect = [
            # Create DNS zone - success
            Mock(returncode=0),
            # Get VNet resource ID - success
            Mock(returncode=0, stdout="/subscriptions/.../vnet1\n"),
            # Link DNS zone - FAILS
            Mock(returncode=1, stderr="LinkAlreadyExists"),
        ]

        # Act & Assert
        with pytest.raises(NetworkConfigurationError, match="DNS"):
            NFSProvisioner.configure_private_dns_zone(
                resource_group="test-rg",
                vnet_names=["vnet1"],
                storage_account="mystorageacct",
                private_endpoint_name="my-pe",
            )


class TestCompletePrivateEndpointSetup:
    """Test complete private endpoint access setup."""

    @patch("subprocess.run")
    def test_setup_private_endpoint_access_with_peering(self, mock_run):
        """Test complete setup with VNet peering."""
        # Arrange
        mock_run.side_effect = [
            # Create private endpoint - storage resource ID
            Mock(returncode=0, stdout="/subscriptions/.../storageAccounts/storage\n"),
            # Create private endpoint - subnet resource ID
            Mock(returncode=0, stdout="/subscriptions/.../subnets/subnet\n"),
            # Create private endpoint
            Mock(
                returncode=0,
                stdout=json.dumps(
                    {
                        "name": "storage-pe-westus",
                        "provisioningState": "Succeeded",
                        "customDnsConfigs": [{"ipAddresses": ["10.0.1.5"]}],
                    }
                ),
            ),
            # VNet peering - remote VNet ID
            Mock(returncode=0, stdout="/subscriptions/.../source-vnet\n"),
            # VNet peering - create local->remote
            Mock(
                returncode=0,
                stdout=json.dumps(
                    {
                        "name": "target-vnet-to-source-vnet",
                        "peeringState": "Connected",
                    }
                ),
            ),
            # VNet peering - local VNet ID
            Mock(returncode=0, stdout="/subscriptions/.../target-vnet\n"),
            # VNet peering - create remote->local
            Mock(returncode=0),
            # DNS configuration - create zone
            Mock(returncode=0),
            # DNS configuration - get target VNet ID
            Mock(returncode=0, stdout="/subscriptions/.../target-vnet\n"),
            # DNS configuration - link target VNet
            Mock(returncode=0),
            # DNS configuration - get source VNet ID
            Mock(returncode=0, stdout="/subscriptions/.../source-vnet\n"),
            # DNS configuration - link source VNet
            Mock(returncode=0),
            # DNS configuration - create zone group
            Mock(returncode=0),
        ]

        # Act
        endpoint, peering, dns_zone = NFSProvisioner.setup_private_endpoint_access(
            storage_account="mystorageacct",
            storage_resource_group="storage-rg",
            target_region="westus",
            target_resource_group="target-rg",
            target_vnet="target-vnet",
            target_subnet="target-subnet",
            source_vnet="source-vnet",
            source_resource_group="source-rg",
        )

        # Assert
        assert endpoint.name == "mystorageacct-pe-westus"
        assert endpoint.storage_account == "mystorageacct"

        assert peering is not None
        assert peering.local_vnet == "target-vnet"
        assert peering.remote_vnet == "source-vnet"

        assert dns_zone.name == "privatelink.file.core.windows.net"
        assert len(dns_zone.linked_vnets) == 2

    @patch("subprocess.run")
    def test_setup_private_endpoint_access_without_peering(self, mock_run):
        """Test setup without VNet peering (same VNet scenario)."""
        # Arrange
        mock_run.side_effect = [
            # Create private endpoint - storage resource ID
            Mock(returncode=0, stdout="/subscriptions/.../storageAccounts/storage\n"),
            # Create private endpoint - subnet resource ID
            Mock(returncode=0, stdout="/subscriptions/.../subnets/subnet\n"),
            # Create private endpoint
            Mock(
                returncode=0,
                stdout=json.dumps(
                    {
                        "name": "storage-pe-westus",
                        "provisioningState": "Succeeded",
                        "customDnsConfigs": [{"ipAddresses": ["10.0.1.5"]}],
                    }
                ),
            ),
            # DNS configuration steps (no peering)
            Mock(returncode=0),  # Create zone
            Mock(returncode=0, stdout="/subscriptions/.../target-vnet\n"),  # Get VNet ID
            Mock(returncode=0),  # Link VNet
            Mock(returncode=0),  # Create zone group
        ]

        # Act
        endpoint, peering, dns_zone = NFSProvisioner.setup_private_endpoint_access(
            storage_account="mystorageacct",
            storage_resource_group="storage-rg",
            target_region="westus",
            target_resource_group="target-rg",
            target_vnet="target-vnet",
            target_subnet="target-subnet",
            # No source VNet - no peering
        )

        # Assert
        assert endpoint.name == "mystorageacct-pe-westus"
        assert peering is None  # No peering created
        assert dns_zone is not None
        assert len(dns_zone.linked_vnets) == 1


class TestResourceOrchestratorNFSDecisions:
    """Test ResourceOrchestrator NFS decision workflows."""

    def test_ensure_nfs_access_same_region(self):
        """Test NFS access decision for same region (direct access)."""
        # Arrange
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(interaction_handler=handler)

        options = NFSOptions(
            region="eastus",
            resource_group="test-rg",
            storage_account_name="mystorageacct",
            storage_account_region="eastus",
            share_name="home",
        )

        # Act
        decision = orchestrator.ensure_nfs_access(options)

        # Assert
        assert decision.action == DecisionAction.USE_EXISTING
        assert decision.resource_type == ResourceType.NFS
        assert decision.metadata["cross_region"] is False
        assert decision.cost_estimate is None  # No additional cost

        # Verify info message shown
        infos = handler.get_interactions_by_type("info")
        assert len(infos) == 1
        assert "local region" in infos[0]["message"].lower()

    def test_ensure_nfs_access_cross_region_user_approves(self):
        """Test cross-region NFS access when user approves setup."""
        # Arrange
        # User chooses option 0 (setup cross-region)
        handler = MockInteractionHandler(choice_responses=[0])
        orchestrator = ResourceOrchestrator(interaction_handler=handler)

        options = NFSOptions(
            region="westus",
            resource_group="test-rg",
            storage_account_name="mystorageacct",
            storage_account_region="eastus",  # Different region
            share_name="home",
        )

        # Act
        decision = orchestrator.ensure_nfs_access(options)

        # Assert
        assert decision.action == DecisionAction.CREATE
        assert decision.resource_type == ResourceType.NFS
        assert decision.metadata["cross_region"] is True
        assert decision.cost_estimate is not None
        assert decision.cost_estimate > 0

        # Verify warning and info shown
        warnings = handler.get_interactions_by_type("warning")
        _infos = handler.get_interactions_by_type("info")
        assert len(warnings) >= 1
        assert any("cross-region" in w["message"].lower() for w in warnings)

    def test_ensure_nfs_access_cross_region_user_uses_local_storage(self):
        """Test cross-region NFS when user chooses local storage fallback."""
        # Arrange
        # User chooses option 1 (use local storage)
        handler = MockInteractionHandler(choice_responses=[1])
        orchestrator = ResourceOrchestrator(interaction_handler=handler)

        options = NFSOptions(
            region="westus",
            resource_group="test-rg",
            storage_account_name="mystorageacct",
            storage_account_region="eastus",
            share_name="home",
        )

        # Act
        decision = orchestrator.ensure_nfs_access(options)

        # Assert
        assert decision.action == DecisionAction.SKIP
        assert decision.resource_type == ResourceType.NFS
        assert decision.metadata["fallback"] == "local-storage"

    def test_ensure_nfs_access_cross_region_user_cancels(self):
        """Test cross-region NFS when user cancels."""
        # Arrange
        # User chooses option 2 (cancel)
        handler = MockInteractionHandler(choice_responses=[2])
        orchestrator = ResourceOrchestrator(interaction_handler=handler)

        options = NFSOptions(
            region="westus",
            resource_group="test-rg",
            storage_account_name="mystorageacct",
            storage_account_region="eastus",
            share_name="home",
        )

        # Act
        decision = orchestrator.ensure_nfs_access(options)

        # Assert
        assert decision.action == DecisionAction.CANCEL
        assert decision.resource_type == ResourceType.NFS


class TestNFSDataReplication:
    """Test NFS data replication workflow."""

    @patch("subprocess.run")
    def test_replicate_nfs_data_success(self, mock_run):
        """Test successful data replication."""
        # Arrange
        mock_run.side_effect = [
            # Get source storage key
            Mock(returncode=0, stdout="source-key-value\n"),
            # Get target storage key
            Mock(returncode=0, stdout="target-key-value\n"),
            # Run azcopy
            Mock(returncode=0, stdout=json.dumps({})),
        ]

        # Act
        result = NFSProvisioner.replicate_nfs_data(
            source_storage="source-storage",
            source_resource_group="source-rg",
            target_storage="target-storage",
            target_resource_group="target-rg",
            share_name="home",
        )

        # Assert
        assert result.success is True
        assert result.source_endpoint == "source-storage/home"
        assert result.target_endpoint == "target-storage/home"
        assert result.duration_seconds > 0
        assert len(result.errors) == 0

    @patch("subprocess.run")
    def test_replicate_nfs_data_azcopy_failure(self, mock_run):
        """Test azcopy failure during replication."""
        # Arrange
        mock_run.side_effect = [
            # Get source storage key
            Mock(returncode=0, stdout="source-key-value\n"),
            # Get target storage key
            Mock(returncode=0, stdout="target-key-value\n"),
            # Run azcopy - FAILS
            Mock(returncode=1, stderr="Transfer failed"),
        ]

        # Act
        result = NFSProvisioner.replicate_nfs_data(
            source_storage="source-storage",
            source_resource_group="source-rg",
            target_storage="target-storage",
            target_resource_group="target-rg",
            share_name="home",
        )

        # Assert
        assert result.success is False
        assert len(result.errors) > 0
        assert "azcopy failed" in result.errors[0]

    def test_replicate_nfs_data_validates_inputs(self):
        """Test input validation for replication."""
        # Test invalid storage name
        with pytest.raises(ValidationError, match="Source storage"):
            NFSProvisioner.replicate_nfs_data(
                source_storage="",
                source_resource_group="source-rg",
                target_storage="target-storage",
                target_resource_group="target-rg",
            )


class TestEndToEndCrossRegionNFS:
    """Integration test for complete cross-region NFS workflow."""

    @patch("subprocess.run")
    @patch("azlin.modules.nfs_provisioner.StorageManager.get_storage")
    def test_complete_workflow_private_endpoint_setup(self, mock_get_storage, mock_run):
        """Test complete workflow: analyze -> prompt -> setup private endpoint."""
        # Arrange
        mock_get_storage.return_value = Mock(size_gb=100, tier="Premium")

        # User chooses to setup cross-region access (option 0)
        handler = MockInteractionHandler(choice_responses=[0])
        orchestrator = ResourceOrchestrator(interaction_handler=handler)

        options = NFSOptions(
            region="westus",
            resource_group="test-rg",
            storage_account_name="mystorageacct",
            storage_account_region="eastus",
            share_name="home",
        )

        # Mock all Azure CLI calls for private endpoint setup
        mock_run.side_effect = [
            # Private endpoint creation
            Mock(returncode=0, stdout="/subscriptions/.../storage\n"),
            Mock(returncode=0, stdout="/subscriptions/.../subnet\n"),
            Mock(
                returncode=0,
                stdout=json.dumps(
                    {
                        "name": "mystorageacct-pe-westus",
                        "provisioningState": "Succeeded",
                        "customDnsConfigs": [{"ipAddresses": ["10.0.1.5"]}],
                    }
                ),
            ),
            # DNS configuration
            Mock(returncode=0),  # Create zone
            Mock(returncode=0, stdout="/subscriptions/.../vnet\n"),  # Get VNet
            Mock(returncode=0),  # Link VNet
            Mock(returncode=0),  # Create zone group
        ]

        # Act - Step 1: Get user decision
        decision = orchestrator.ensure_nfs_access(options)

        # Assert decision
        assert decision.action == DecisionAction.CREATE
        assert decision.metadata["cross_region"] is True

        # Act - Step 2: Analyze access strategy
        analysis = NFSProvisioner.analyze_nfs_access(
            storage_account=options.storage_account_name,
            source_region=options.storage_account_region,
            target_region=options.region,
            resource_group=options.resource_group,
        )

        # Assert analysis
        assert analysis.same_region is False
        assert AccessStrategy.PRIVATE_ENDPOINT in analysis.strategies

        # Act - Step 3: Setup private endpoint (simplified)
        endpoint, peering, dns_zone = NFSProvisioner.setup_private_endpoint_access(
            storage_account=options.storage_account_name,
            storage_resource_group=options.resource_group,
            target_region=options.region,
            target_resource_group=options.resource_group,
            target_vnet="target-vnet",
            target_subnet="target-subnet",
        )

        # Assert setup
        assert endpoint.storage_account == options.storage_account_name
        assert dns_zone.name == "privatelink.file.core.windows.net"

        # Verify user interactions
        choice_interactions = handler.get_interactions_by_type("choice")
        assert len(choice_interactions) == 1
        assert "cross-region" in choice_interactions[0]["message"].lower()
