"""Unit tests for nfs_provisioner module.

Tests cross-region NFS access, private endpoints, and data replication.
"""

import subprocess
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from azlin.modules.nfs_provisioner import (
    AccessAnalysis,
    AccessStrategy,
    NFSProvisioner,
    NFSProvisionerError,
    PrivateDNSZoneInfo,
    PrivateEndpointInfo,
    ReplicationResult,
    VNetPeeringInfo,
    _validate_resource_id,
    _validate_resource_name,
)


class TestResourceNameValidation:
    """Test resource name validation for security."""

    def test_valid_resource_name(self):
        """Valid resource names should pass."""
        assert _validate_resource_name("my-resource", "test") == "my-resource"
        assert _validate_resource_name("resource_123", "test") == "resource_123"
        assert _validate_resource_name("Resource-ABC", "test") == "Resource-ABC"

    def test_empty_resource_name_raises_error(self):
        """Empty resource name should raise error."""
        with pytest.raises(NFSProvisionerError, match="non-empty string"):
            _validate_resource_name("", "test")

    def test_none_resource_name_raises_error(self):
        """None resource name should raise error."""
        with pytest.raises(NFSProvisionerError, match="non-empty string"):
            _validate_resource_name(None, "test")  # type: ignore

    def test_command_injection_semicolon_raises_error(self):
        """Semicolon should be rejected (command injection)."""
        with pytest.raises(NFSProvisionerError, match="unsafe character"):
            _validate_resource_name("resource;rm -rf", "test")

    def test_command_injection_ampersand_raises_error(self):
        """Ampersand should be rejected (command injection)."""
        with pytest.raises(NFSProvisionerError, match="unsafe character"):
            _validate_resource_name("resource&&whoami", "test")

    def test_command_injection_pipe_raises_error(self):
        """Pipe should be rejected (command injection)."""
        with pytest.raises(NFSProvisionerError, match="unsafe character"):
            _validate_resource_name("resource|cat", "test")

    def test_path_traversal_raises_error(self):
        """Path traversal should be rejected."""
        with pytest.raises(NFSProvisionerError, match="path traversal"):
            _validate_resource_name("../etc/passwd", "test")

    def test_forward_slash_raises_error(self):
        """Forward slash should be rejected."""
        with pytest.raises(NFSProvisionerError, match="path traversal"):
            _validate_resource_name("path/to/resource", "test")


class TestResourceIDValidation:
    """Test Azure resource ID validation."""

    def test_valid_resource_id(self):
        """Valid Azure resource ID should pass."""
        resource_id = "/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/vnet"
        assert _validate_resource_id(resource_id) == resource_id

    def test_empty_resource_id_raises_error(self):
        """Empty resource ID should raise error."""
        with pytest.raises(NFSProvisionerError, match="non-empty string"):
            _validate_resource_id("")

    def test_invalid_format_raises_error(self):
        """Invalid format should raise error."""
        with pytest.raises(NFSProvisionerError, match="Invalid Azure resource ID"):
            _validate_resource_id("not-a-resource-id")

    def test_command_injection_in_resource_id_raises_error(self):
        """Command injection in resource ID should be rejected."""
        with pytest.raises(NFSProvisionerError, match="unsafe character"):
            _validate_resource_id("/subscriptions/sub;whoami/resourceGroups/rg")


class TestAccessStrategy:
    """Test AccessStrategy enumeration."""

    def test_strategy_values(self):
        """Access strategy values should be defined."""
        assert AccessStrategy.DIRECT.value == "direct"
        assert AccessStrategy.PRIVATE_ENDPOINT.value == "private_endpoint"
        assert AccessStrategy.NEW_STORAGE.value == "new_storage"
        assert AccessStrategy.REPLICATE.value == "replicate"


class TestAnalyzeNFSAccess:
    """Test NFS access strategy analysis."""

    @patch("azlin.modules.storage_manager.StorageManager.get_storage")
    def test_same_region_recommends_direct(self, mock_get_storage):
        """Same region should recommend direct access."""
        mock_get_storage.return_value = MagicMock(
            name="myaccount",
            size_gb=100,
            tier="Premium",
        )

        analysis = NFSProvisioner.analyze_nfs_access(
            storage_account="myaccount",
            source_region="eastus",
            target_region="eastus",
            resource_group="my-rg",
        )

        assert analysis.same_region is True
        assert analysis.recommended_strategy == AccessStrategy.DIRECT
        assert analysis.estimated_cost_monthly == 0.0

    @patch("azlin.modules.storage_manager.StorageManager.get_storage")
    def test_cross_region_evaluates_strategies(self, mock_get_storage):
        """Cross-region should evaluate multiple strategies."""
        mock_get_storage.return_value = MagicMock(
            name="myaccount",
            size_gb=100,
            tier="Premium",
        )

        analysis = NFSProvisioner.analyze_nfs_access(
            storage_account="myaccount",
            source_region="eastus",
            target_region="westus",
            resource_group="my-rg",
        )

        assert analysis.same_region is False
        # Should have multiple strategies
        assert AccessStrategy.PRIVATE_ENDPOINT in analysis.strategies
        assert AccessStrategy.NEW_STORAGE in analysis.strategies
        assert AccessStrategy.REPLICATE in analysis.strategies

    @patch("azlin.modules.storage_manager.StorageManager.get_storage")
    def test_strategy_includes_costs(self, mock_get_storage):
        """Strategy analysis should include cost estimates."""
        mock_get_storage.return_value = MagicMock(
            name="myaccount",
            size_gb=100,
            tier="Premium",
        )

        analysis = NFSProvisioner.analyze_nfs_access(
            storage_account="myaccount",
            source_region="eastus",
            target_region="westus",
            resource_group="my-rg",
        )

        # Private endpoint strategy should have cost
        pe_strategy = analysis.strategies[AccessStrategy.PRIVATE_ENDPOINT]
        assert "cost_monthly" in pe_strategy
        assert pe_strategy["cost_monthly"] > 0

    @patch("azlin.modules.storage_manager.StorageManager.get_storage")
    def test_invalid_storage_account_raises_error(self, mock_get_storage):
        """Invalid storage account should raise error."""
        mock_get_storage.side_effect = Exception("Not found")

        with pytest.raises(NFSProvisionerError):
            NFSProvisioner.analyze_nfs_access(
                storage_account="missing-account",
                source_region="eastus",
                target_region="westus",
                resource_group="my-rg",
            )


class TestCreatePrivateEndpoint:
    """Test private endpoint creation."""

    @patch("azlin.modules.nfs_provisioner.subprocess.run")
    def test_create_private_endpoint_success(self, mock_run):
        """Private endpoint creation should succeed."""
        # Mock storage account ID query
        storage_id = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/myaccount"
        subnet_id = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/vnet/subnets/subnet"

        # Mock subprocess calls
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=storage_id),  # storage ID query
            MagicMock(returncode=0, stdout=subnet_id),  # subnet ID query
            MagicMock(  # private endpoint create
                returncode=0,
                stdout='{"name": "my-pe", "provisioningState": "Succeeded", "customDnsConfigs": [{"ipAddresses": ["10.0.0.4"]}]}',
            ),
        ]

        endpoint = NFSProvisioner.create_private_endpoint(
            name="my-pe",
            resource_group="my-rg",
            region="eastus",
            vnet_name="my-vnet",
            subnet_name="my-subnet",
            storage_account="myaccount",
            storage_resource_group="storage-rg",
        )

        assert endpoint.name == "my-pe"
        assert endpoint.private_ip == "10.0.0.4"
        assert endpoint.connection_state == "Succeeded"
        assert mock_run.call_count == 3

    @patch("azlin.modules.nfs_provisioner.subprocess.run")
    def test_create_private_endpoint_validation_error(self, mock_run):
        """Invalid inputs should raise validation error."""
        with pytest.raises(NFSProvisionerError):
            NFSProvisioner.create_private_endpoint(
                name="pe;whoami",  # Invalid character
                resource_group="my-rg",
                region="eastus",
                vnet_name="vnet",
                subnet_name="subnet",
                storage_account="storage",
                storage_resource_group="rg",
            )

    @patch("azlin.modules.nfs_provisioner.subprocess.run")
    def test_create_private_endpoint_command_failure(self, mock_run):
        """Command failure should raise NFSProvisionerError."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="Error")

        with pytest.raises(NFSProvisionerError):
            NFSProvisioner.create_private_endpoint(
                name="my-pe",
                resource_group="my-rg",
                region="eastus",
                vnet_name="vnet",
                subnet_name="subnet",
                storage_account="storage",
                storage_resource_group="rg",
            )


class TestCreateVNetPeering:
    """Test VNet peering creation."""

    @patch("azlin.modules.nfs_provisioner.subprocess.run")
    def test_create_vnet_peering_success(self, mock_run):
        """VNet peering should create bidirectional connection."""
        remote_vnet_id = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/remote-vnet"
        local_vnet_id = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/local-vnet"

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=remote_vnet_id),  # remote vnet ID
            MagicMock(  # local peering create
                returncode=0,
                stdout='{"name": "peer1", "peeringState": "Connected"}',
            ),
            MagicMock(returncode=0, stdout=local_vnet_id),  # local vnet ID
            MagicMock(returncode=0),  # remote peering create
        ]

        peering = NFSProvisioner.create_vnet_peering(
            name="my-peering",
            resource_group="local-rg",
            local_vnet="local-vnet",
            remote_vnet="remote-vnet",
            remote_vnet_resource_group="remote-rg",
        )

        assert peering.name == "my-peering"
        assert peering.peering_state == "Connected"
        assert peering.local_vnet == "local-vnet"
        assert peering.remote_vnet == "remote-vnet"
        # Should create both directions
        assert mock_run.call_count == 4

    @patch("azlin.modules.nfs_provisioner.subprocess.run")
    def test_create_vnet_peering_with_forwarded_traffic(self, mock_run):
        """Peering with forwarded traffic should set flag."""
        remote_vnet_id = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/remote-vnet"
        local_vnet_id = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/local-vnet"

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=remote_vnet_id),
            MagicMock(returncode=0, stdout='{"name": "peer", "peeringState": "Connected"}'),
            MagicMock(returncode=0, stdout=local_vnet_id),
            MagicMock(returncode=0),
        ]

        peering = NFSProvisioner.create_vnet_peering(
            name="my-peering",
            resource_group="local-rg",
            local_vnet="local-vnet",
            remote_vnet="remote-vnet",
            remote_vnet_resource_group="remote-rg",
            allow_forwarded_traffic=True,
        )

        assert peering.allow_forwarded_traffic is True


class TestConfigurePrivateDNSZone:
    """Test private DNS zone configuration."""

    @patch("azlin.modules.nfs_provisioner.subprocess.run")
    def test_configure_dns_zone_success(self, mock_run):
        """DNS zone configuration should succeed."""
        vnet_id = (
            "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/vnet"
        )

        mock_run.side_effect = [
            MagicMock(returncode=0),  # create zone
            MagicMock(returncode=0, stdout=vnet_id),  # get vnet ID
            MagicMock(returncode=0),  # link vnet
            MagicMock(returncode=0),  # create zone group
        ]

        dns_zone = NFSProvisioner.configure_private_dns_zone(
            resource_group="my-rg",
            vnet_names=["my-vnet"],
            storage_account="myaccount",
            private_endpoint_name="my-pe",
        )

        assert dns_zone.name == "privatelink.file.core.windows.net"
        assert "my-vnet" in dns_zone.linked_vnets
        assert dns_zone.record_count == 1

    @patch("azlin.modules.nfs_provisioner.subprocess.run")
    def test_configure_dns_zone_multiple_vnets(self, mock_run):
        """DNS zone should link multiple VNets."""
        vnet1_id = (
            "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/vnet1"
        )
        vnet2_id = (
            "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/vnet2"
        )

        mock_run.side_effect = [
            MagicMock(returncode=0),  # create zone
            MagicMock(returncode=0, stdout=vnet1_id),  # vnet1 ID
            MagicMock(returncode=0),  # link vnet1
            MagicMock(returncode=0, stdout=vnet2_id),  # vnet2 ID
            MagicMock(returncode=0),  # link vnet2
            MagicMock(returncode=0),  # create zone group
        ]

        dns_zone = NFSProvisioner.configure_private_dns_zone(
            resource_group="my-rg",
            vnet_names=["vnet1", "vnet2"],
            storage_account="myaccount",
            private_endpoint_name="my-pe",
        )

        assert len(dns_zone.linked_vnets) == 2
        assert "vnet1" in dns_zone.linked_vnets
        assert "vnet2" in dns_zone.linked_vnets


class TestSetupPrivateEndpointAccess:
    """Test complete private endpoint access setup."""

    @patch("azlin.modules.nfs_provisioner.NFSProvisioner.create_private_endpoint")
    @patch("azlin.modules.nfs_provisioner.NFSProvisioner.create_vnet_peering")
    @patch("azlin.modules.nfs_provisioner.NFSProvisioner.configure_private_dns_zone")
    def test_setup_without_peering(self, mock_dns, mock_peering, mock_endpoint):
        """Setup without source VNet should skip peering."""
        mock_endpoint.return_value = PrivateEndpointInfo(
            name="my-pe",
            resource_group="my-rg",
            region="eastus",
            storage_account="storage",
            vnet_name="target-vnet",
            subnet_name="subnet",
            private_ip="10.0.0.4",
            connection_state="Succeeded",
            dns_configured=False,
            created=datetime.now(),
        )

        mock_dns.return_value = PrivateDNSZoneInfo(
            name="privatelink.file.core.windows.net",
            resource_group="my-rg",
            linked_vnets=["target-vnet"],
            record_count=1,
        )

        endpoint, peering, dns = NFSProvisioner.setup_private_endpoint_access(
            storage_account="myaccount",
            storage_resource_group="storage-rg",
            target_region="eastus",
            target_resource_group="my-rg",
            target_vnet="target-vnet",
            target_subnet="subnet",
        )

        assert endpoint.name == "my-pe"
        assert peering is None  # No peering created
        assert dns.name == "privatelink.file.core.windows.net"

    @patch("azlin.modules.nfs_provisioner.NFSProvisioner.create_private_endpoint")
    @patch("azlin.modules.nfs_provisioner.NFSProvisioner.create_vnet_peering")
    @patch("azlin.modules.nfs_provisioner.NFSProvisioner.configure_private_dns_zone")
    def test_setup_with_peering(self, mock_dns, mock_peering, mock_endpoint):
        """Setup with source VNet should create peering."""
        mock_endpoint.return_value = PrivateEndpointInfo(
            name="my-pe",
            resource_group="my-rg",
            region="eastus",
            storage_account="storage",
            vnet_name="target-vnet",
            subnet_name="subnet",
            private_ip="10.0.0.4",
            connection_state="Succeeded",
            dns_configured=False,
            created=datetime.now(),
        )

        mock_peering.return_value = VNetPeeringInfo(
            name="peering",
            resource_group="my-rg",
            local_vnet="target-vnet",
            remote_vnet="source-vnet",
            peering_state="Connected",
            allow_forwarded_traffic=True,
            allow_gateway_transit=False,
            use_remote_gateways=False,
            created=datetime.now(),
        )

        mock_dns.return_value = PrivateDNSZoneInfo(
            name="privatelink.file.core.windows.net",
            resource_group="my-rg",
            linked_vnets=["target-vnet", "source-vnet"],
            record_count=1,
        )

        endpoint, peering, dns = NFSProvisioner.setup_private_endpoint_access(
            storage_account="myaccount",
            storage_resource_group="storage-rg",
            target_region="eastus",
            target_resource_group="my-rg",
            target_vnet="target-vnet",
            target_subnet="subnet",
            source_vnet="source-vnet",
            source_resource_group="source-rg",
        )

        assert endpoint.name == "my-pe"
        assert peering is not None
        assert peering.local_vnet == "target-vnet"
        assert peering.remote_vnet == "source-vnet"
        assert len(dns.linked_vnets) == 2


class TestReplicateNFSData:
    """Test NFS data replication."""

    @patch("azlin.modules.nfs_provisioner.subprocess.run")
    def test_replicate_data_success(self, mock_run):
        """Data replication should succeed."""
        # Mock storage key queries and azcopy
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="source-key"),  # source key
            MagicMock(returncode=0, stdout="target-key"),  # target key
            MagicMock(returncode=0, stdout="sas-token"),  # SAS token
            MagicMock(returncode=0, stdout="{}"),  # azcopy
        ]

        result = NFSProvisioner.replicate_nfs_data(
            source_storage="source-account",
            source_resource_group="source-rg",
            target_storage="target-account",
            target_resource_group="target-rg",
            share_name="home",
        )

        assert result.success is True
        assert "source-account" in result.source_endpoint
        assert "target-account" in result.target_endpoint

    @patch("azlin.modules.nfs_provisioner.subprocess.run")
    def test_replicate_data_azcopy_failure(self, mock_run):
        """Azcopy failure should be reported."""
        # Mock successful key queries but failed azcopy
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="source-key"),
            MagicMock(returncode=0, stdout="target-key"),
            MagicMock(returncode=0, stdout="sas-token"),
            MagicMock(returncode=1, stderr="Azcopy failed"),  # azcopy failure
        ]

        result = NFSProvisioner.replicate_nfs_data(
            source_storage="source",
            source_resource_group="rg",
            target_storage="target",
            target_resource_group="rg",
        )

        assert result.success is False
        assert len(result.errors) > 0

    def test_replicate_data_validation_error(self):
        """Invalid storage names should raise error."""
        with pytest.raises(NFSProvisionerError):
            NFSProvisioner.replicate_nfs_data(
                source_storage="source;rm -rf",  # Invalid
                source_resource_group="rg",
                target_storage="target",
                target_resource_group="rg",
            )


class TestDataModels:
    """Test data model classes."""

    def test_access_analysis_get_strategy_details(self):
        """AccessAnalysis should return strategy details."""
        analysis = AccessAnalysis(
            source_storage="storage",
            source_region="eastus",
            target_region="westus",
            recommended_strategy=AccessStrategy.DIRECT,
            strategies={
                AccessStrategy.DIRECT: {"cost": 0},
                AccessStrategy.PRIVATE_ENDPOINT: {"cost": 10},
            },
            same_region=True,
            estimated_latency_ms=1.0,
            estimated_cost_monthly=0.0,
        )

        direct_details = analysis.get_strategy_details(AccessStrategy.DIRECT)
        assert direct_details == {"cost": 0}

    def test_replication_result_with_errors(self):
        """ReplicationResult should track errors."""
        result = ReplicationResult(
            success=False,
            source_endpoint="source/share",
            target_endpoint="target/share",
            files_copied=0,
            bytes_copied=0,
            duration_seconds=10.0,
            errors=["Error 1", "Error 2"],
        )

        assert result.success is False
        assert len(result.errors) == 2


class TestConstants:
    """Test module constants."""

    def test_private_endpoint_constants(self):
        """Private endpoint constants should be defined."""
        assert NFSProvisioner.PRIVATE_ENDPOINT_GROUP_ID == "file"
        assert NFSProvisioner.PRIVATE_DNS_ZONE_NAME == "privatelink.file.core.windows.net"

    def test_cost_constants(self):
        """Cost constants should be defined."""
        assert NFSProvisioner.PRIVATE_ENDPOINT_COST == 7.30
        assert NFSProvisioner.VNET_PEERING_COST_PER_GB == 0.01

    def test_latency_constants(self):
        """Latency constants should be defined."""
        assert NFSProvisioner.SAME_REGION_LATENCY == 1.0
        assert NFSProvisioner.CROSS_REGION_LATENCY == 50.0
        assert NFSProvisioner.PRIVATE_ENDPOINT_OVERHEAD == 2.0
