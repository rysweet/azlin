"""Unit tests for VPN and Private Endpoint configuration.

Tests the VPNManager and PrivateEndpointManager classes.
These tests follow TDD RED phase - they will fail until implementation is complete.

Coverage targets:
- VPN gateway creation and configuration
- VPN client config generation
- Private endpoint creation
- Private DNS zone configuration
"""

from unittest.mock import Mock, patch

import pytest

# Mark all tests as TDD RED phase (expected to fail)
pytestmark = [pytest.mark.unit, pytest.mark.tdd_red]


class TestVPNManagerInitialization:
    """Test VPNManager initialization."""

    def test_vpn_manager_creation(self):
        """VPNManager should be initialized with resource group."""
        from azlin.network_security.vpn_manager import VPNManager

        manager = VPNManager(resource_group="test-rg")

        assert manager.resource_group == "test-rg"


class TestVPNManagerPointToSiteVPN:
    """Test Point-to-Site VPN creation."""

    @patch("subprocess.run")
    def test_create_p2s_vpn_creates_gateway_subnet(self, mock_run):
        """create_point_to_site_vpn should create gateway subnet first."""
        from azlin.network_security.vpn_manager import VPNManager

        mock_run.return_value = Mock(returncode=0)

        manager = VPNManager(resource_group="test-rg")

        with patch.object(manager, "_get_gateway_id", return_value="/gateway/id"):
            manager.create_point_to_site_vpn(vnet_name="test-vnet", vpn_gateway_name="test-vpn-gw")

        # Verify gateway subnet creation
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert any("GatewaySubnet" in " ".join(c) for c in calls)

    @patch("subprocess.run")
    def test_create_p2s_vpn_creates_vpn_gateway(self, mock_run):
        """create_point_to_site_vpn should create VPN gateway."""
        from azlin.network_security.vpn_manager import VPNManager

        mock_run.return_value = Mock(returncode=0)

        manager = VPNManager(resource_group="test-rg")

        with patch.object(manager, "_get_gateway_id", return_value="/gateway/id"):
            manager.create_point_to_site_vpn(vnet_name="test-vnet", vpn_gateway_name="test-vpn-gw")

        # Verify VPN gateway creation
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert any("vnet-gateway" in " ".join(c) and "create" in " ".join(c) for c in calls)

    @patch("subprocess.run")
    def test_create_p2s_vpn_uses_no_wait_for_gateway(self, mock_run):
        """VPN gateway creation should use --no-wait (takes 30-45 minutes)."""
        from azlin.network_security.vpn_manager import VPNManager

        mock_run.return_value = Mock(returncode=0)

        manager = VPNManager(resource_group="test-rg")

        with patch.object(manager, "_get_gateway_id", return_value="/gateway/id"):
            manager.create_point_to_site_vpn(vnet_name="test-vnet", vpn_gateway_name="test-vpn-gw")

        # Verify --no-wait flag is used
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert any("--no-wait" in c for c in calls)

    @patch("subprocess.run")
    def test_create_p2s_vpn_configures_openvpn(self, mock_run):
        """Point-to-Site VPN should be configured for OpenVPN."""
        from azlin.network_security.vpn_manager import VPNManager

        mock_run.return_value = Mock(returncode=0)

        manager = VPNManager(resource_group="test-rg")

        with patch.object(manager, "_get_gateway_id", return_value="/gateway/id"):
            manager.create_point_to_site_vpn(vnet_name="test-vnet", vpn_gateway_name="test-vpn-gw")

        # Verify OpenVPN protocol configuration
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert any("OpenVPN" in " ".join(c) for c in calls)

    @patch("subprocess.run")
    def test_create_p2s_vpn_uses_custom_address_pool(self, mock_run):
        """P2S VPN should use custom address pool if provided."""
        from azlin.network_security.vpn_manager import VPNManager

        mock_run.return_value = Mock(returncode=0)

        manager = VPNManager(resource_group="test-rg")

        with patch.object(manager, "_get_gateway_id", return_value="/gateway/id"):
            manager.create_point_to_site_vpn(
                vnet_name="test-vnet",
                vpn_gateway_name="test-vpn-gw",
                address_pool="10.200.0.0/24",
            )

        # Verify custom address pool is used
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert any("10.200.0.0/24" in " ".join(c) for c in calls)

    @patch("subprocess.run")
    def test_create_p2s_vpn_returns_gateway_id(self, mock_run):
        """create_point_to_site_vpn should return gateway resource ID."""
        from azlin.network_security.vpn_manager import VPNManager

        mock_run.return_value = Mock(returncode=0)

        manager = VPNManager(resource_group="test-rg")

        expected_id = "/subscriptions/test/gateways/test-vpn-gw"
        with patch.object(manager, "_get_gateway_id", return_value=expected_id):
            result = manager.create_point_to_site_vpn(
                vnet_name="test-vnet", vpn_gateway_name="test-vpn-gw"
            )

        assert result == expected_id


class TestVPNManagerClientConfig:
    """Test VPN client configuration generation."""

    @patch("subprocess.run")
    def test_generate_vpn_client_config_calls_az_cli(self, mock_run):
        """generate_vpn_client_config should call Azure CLI."""
        from azlin.network_security.vpn_manager import VPNManager

        mock_run.return_value = Mock(
            returncode=0, stdout='"https://download.example.com/config.zip"\n'
        )

        manager = VPNManager(resource_group="test-rg")
        config_url = manager.generate_vpn_client_config(vpn_gateway_name="test-vpn-gw")

        # Verify az network vnet-gateway vpn-client generate was called
        call_args = mock_run.call_args[0][0]
        assert "az" in call_args
        assert "network" in call_args
        assert "vnet-gateway" in call_args
        assert "vpn-client" in call_args
        assert "generate" in call_args

    @patch("subprocess.run")
    def test_generate_vpn_client_config_returns_download_url(self, mock_run):
        """generate_vpn_client_config should return config download URL."""
        from azlin.network_security.vpn_manager import VPNManager

        expected_url = "https://download.example.com/vpn-config.zip"
        mock_run.return_value = Mock(returncode=0, stdout=f'"{expected_url}"\n')

        manager = VPNManager(resource_group="test-rg")
        config_url = manager.generate_vpn_client_config(vpn_gateway_name="test-vpn-gw")

        assert config_url == expected_url

    @patch("subprocess.run")
    def test_generate_vpn_client_config_uses_amd64(self, mock_run):
        """VPN client config should target AMD64 processor architecture."""
        from azlin.network_security.vpn_manager import VPNManager

        mock_run.return_value = Mock(
            returncode=0, stdout='"https://download.example.com/config.zip"\n'
        )

        manager = VPNManager(resource_group="test-rg")
        manager.generate_vpn_client_config(vpn_gateway_name="test-vpn-gw")

        # Verify Amd64 architecture specified
        call_args = mock_run.call_args[0][0]
        assert "Amd64" in call_args


class TestPrivateEndpointManagerInitialization:
    """Test PrivateEndpointManager initialization."""

    def test_private_endpoint_manager_creation(self):
        """PrivateEndpointManager should be created without parameters."""
        from azlin.network_security.private_endpoint_manager import (
            PrivateEndpointManager,
        )

        manager = PrivateEndpointManager()

        assert manager is not None


class TestPrivateEndpointCreation:
    """Test private endpoint creation."""

    @patch("subprocess.run")
    def test_create_private_endpoint_disables_network_policies(self, mock_run):
        """Private endpoint creation should disable network policies on subnet."""
        from azlin.network_security.private_endpoint_manager import (
            PrivateEndpointManager,
        )

        mock_run.return_value = Mock(returncode=0)

        manager = PrivateEndpointManager()

        with patch.object(manager, "_get_endpoint_id", return_value="/endpoint/id"):
            manager.create_private_endpoint(
                endpoint_name="test-pe",
                resource_group="test-rg",
                vnet_name="test-vnet",
                subnet_name="pe-subnet",
                service_resource_id="/subscriptions/test/keyvault1",
                group_id="vault",
            )

        # Verify subnet update to disable policies
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert any("--disable-private-endpoint-network-policies" in " ".join(c) for c in calls)

    @patch("subprocess.run")
    def test_create_private_endpoint_creates_endpoint(self, mock_run):
        """create_private_endpoint should create the private endpoint."""
        from azlin.network_security.private_endpoint_manager import (
            PrivateEndpointManager,
        )

        mock_run.return_value = Mock(returncode=0)

        manager = PrivateEndpointManager()

        with patch.object(manager, "_get_endpoint_id", return_value="/endpoint/id"):
            manager.create_private_endpoint(
                endpoint_name="test-pe",
                resource_group="test-rg",
                vnet_name="test-vnet",
                subnet_name="pe-subnet",
                service_resource_id="/subscriptions/test/keyvault1",
                group_id="vault",
            )

        # Verify private endpoint creation
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert any("private-endpoint" in " ".join(c) and "create" in " ".join(c) for c in calls)

    @patch("subprocess.run")
    def test_create_private_endpoint_uses_correct_group_id(self, mock_run):
        """Private endpoint should use correct group_id for service type."""
        from azlin.network_security.private_endpoint_manager import (
            PrivateEndpointManager,
        )

        mock_run.return_value = Mock(returncode=0)

        manager = PrivateEndpointManager()

        # Test Key Vault group_id
        with patch.object(manager, "_get_endpoint_id", return_value="/endpoint/id"):
            manager.create_private_endpoint(
                endpoint_name="kv-pe",
                resource_group="test-rg",
                vnet_name="test-vnet",
                subnet_name="pe-subnet",
                service_resource_id="/subscriptions/test/keyvault1",
                group_id="vault",
            )

        # Verify vault group_id is used
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert any("--group-id" in " ".join(c) and "vault" in " ".join(c) for c in calls)

    @patch("subprocess.run")
    def test_create_private_endpoint_returns_endpoint_id(self, mock_run):
        """create_private_endpoint should return endpoint resource ID."""
        from azlin.network_security.private_endpoint_manager import (
            PrivateEndpointManager,
        )

        mock_run.return_value = Mock(returncode=0)

        manager = PrivateEndpointManager()

        expected_id = "/subscriptions/test/endpoints/test-pe"
        with patch.object(manager, "_get_endpoint_id", return_value=expected_id):
            result = manager.create_private_endpoint(
                endpoint_name="test-pe",
                resource_group="test-rg",
                vnet_name="test-vnet",
                subnet_name="pe-subnet",
                service_resource_id="/subscriptions/test/keyvault1",
                group_id="vault",
            )

        assert result == expected_id


class TestPrivateDNSZoneConfiguration:
    """Test Private DNS zone configuration."""

    @patch("subprocess.run")
    def test_create_private_dns_zone_creates_zone(self, mock_run):
        """create_private_dns_zone should create DNS zone."""
        from azlin.network_security.private_endpoint_manager import (
            PrivateEndpointManager,
        )

        mock_run.return_value = Mock(returncode=0)

        manager = PrivateEndpointManager()

        manager.create_private_dns_zone(
            zone_name="privatelink.vaultcore.azure.net",
            resource_group="test-rg",
            vnet_name="test-vnet",
        )

        # Verify private DNS zone creation
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert any(
            "private-dns" in " ".join(c) and "zone" in " ".join(c) and "create" in " ".join(c)
            for c in calls
        )

    @patch("subprocess.run")
    def test_create_private_dns_zone_links_to_vnet(self, mock_run):
        """Private DNS zone should be linked to VNet."""
        from azlin.network_security.private_endpoint_manager import (
            PrivateEndpointManager,
        )

        mock_run.return_value = Mock(returncode=0)

        manager = PrivateEndpointManager()

        manager.create_private_dns_zone(
            zone_name="privatelink.vaultcore.azure.net",
            resource_group="test-rg",
            vnet_name="test-vnet",
        )

        # Verify VNet link creation
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert any(
            "link" in " ".join(c) and "vnet" in " ".join(c) and "create" in " ".join(c)
            for c in calls
        )

    @patch("subprocess.run")
    def test_create_private_dns_zone_disables_auto_registration(self, mock_run):
        """VNet link should have auto-registration disabled."""
        from azlin.network_security.private_endpoint_manager import (
            PrivateEndpointManager,
        )

        mock_run.return_value = Mock(returncode=0)

        manager = PrivateEndpointManager()

        manager.create_private_dns_zone(
            zone_name="privatelink.vaultcore.azure.net",
            resource_group="test-rg",
            vnet_name="test-vnet",
        )

        # Verify registration-enabled is false
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert any(
            "--registration-enabled" in " ".join(c) and "false" in " ".join(c) for c in calls
        )

    @patch("subprocess.run")
    def test_create_private_dns_zone_uses_correct_zone_names(self, mock_run):
        """DNS zone names should match Azure service privatelink conventions."""
        from azlin.network_security.private_endpoint_manager import (
            PrivateEndpointManager,
        )

        mock_run.return_value = Mock(returncode=0)

        manager = PrivateEndpointManager()

        # Test Key Vault DNS zone
        manager.create_private_dns_zone(
            zone_name="privatelink.vaultcore.azure.net",
            resource_group="test-rg",
            vnet_name="test-vnet",
        )

        calls = [c[0][0] for c in mock_run.call_args_list]
        assert any("privatelink.vaultcore.azure.net" in " ".join(c) for c in calls)


class TestVPNPrivateEndpointIntegration:
    """Test integration patterns between VPN and private endpoints."""

    @patch("subprocess.run")
    def test_secure_infrastructure_setup_workflow(self, mock_run):
        """Complete secure infrastructure should include VPN + private endpoints."""
        from azlin.network_security.private_endpoint_manager import (
            PrivateEndpointManager,
        )
        from azlin.network_security.vpn_manager import VPNManager

        mock_run.return_value = Mock(returncode=0)

        vpn_manager = VPNManager(resource_group="test-rg")
        pe_manager = PrivateEndpointManager()

        # Setup VPN
        with patch.object(vpn_manager, "_get_gateway_id", return_value="/gateway/id"):
            vpn_id = vpn_manager.create_point_to_site_vpn(
                vnet_name="test-vnet", vpn_gateway_name="test-vpn-gw"
            )

        # Setup Private Endpoint
        with patch.object(pe_manager, "_get_endpoint_id", return_value="/endpoint/id"):
            pe_id = pe_manager.create_private_endpoint(
                endpoint_name="kv-pe",
                resource_group="test-rg",
                vnet_name="test-vnet",
                subnet_name="pe-subnet",
                service_resource_id="/subscriptions/test/keyvault1",
                group_id="vault",
            )

        # Setup Private DNS
        pe_manager.create_private_dns_zone(
            zone_name="privatelink.vaultcore.azure.net",
            resource_group="test-rg",
            vnet_name="test-vnet",
        )

        # Verify all components created
        assert vpn_id is not None
        assert pe_id is not None
        # Verify multiple Azure CLI calls were made
        assert mock_run.call_count >= 5
