"""Unit tests for SSH bastion routing functionality.

Tests the SSH configuration builder that determines whether to use
direct SSH or bastion tunneling based on VM network configuration.

Following TDD approach - these tests should FAIL initially and PASS
after implementing bastion routing support for multi-VM commands.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from azlin.modules.ssh_connector import SSHConfig
from azlin.vm_manager import VMInfo


class SSHConfigBuilder:
    """Builder for SSH configurations with bastion awareness.

    This class should be implemented to support the fix for issue-281.
    Determines whether to use direct SSH or bastion tunnel based on VM connectivity.
    """

    pass


class TestSSHConfigBuilder:
    """Test SSH config builder with bastion awareness."""

    def test_build_config_for_vm_with_public_ip(self):
        """Test SSH config for VM with public IP uses direct connection."""
        vm = VMInfo(
            name="public-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
            private_ip="10.0.0.1",
        )
        ssh_key = Path("/home/user/.ssh/azlin_key")

        # Should create direct SSH config
        config = SSHConfigBuilder.build_for_vm(vm, ssh_key, bastion_manager=None)

        assert config.host == "20.1.2.3"
        assert config.port == 22
        assert config.user == "azureuser"
        assert config.key_path == ssh_key

    def test_build_config_for_vm_without_public_ip_requires_bastion(self):
        """Test SSH config for private-only VM requires bastion manager."""
        vm = VMInfo(
            name="private-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip=None,
            private_ip="10.0.0.2",
        )
        ssh_key = Path("/home/user/.ssh/azlin_key")

        # Should raise error when no bastion manager provided
        with pytest.raises(ValueError, match="Bastion manager required"):
            SSHConfigBuilder.build_for_vm(vm, ssh_key, bastion_manager=None)

    @patch("azlin.modules.bastion_manager.BastionManager")
    def test_build_config_for_vm_without_public_ip_uses_bastion(self, mock_bastion_mgr):
        """Test SSH config for private-only VM creates bastion tunnel."""
        vm = VMInfo(
            name="private-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip=None,
            private_ip="10.0.0.2",
        )
        ssh_key = Path("/home/user/.ssh/azlin_key")

        # Mock bastion manager
        mock_bastion = MagicMock()
        mock_tunnel = Mock()
        mock_tunnel.local_port = 50022
        mock_bastion.create_tunnel.return_value = mock_tunnel

        # Should create bastion tunnel config
        config = SSHConfigBuilder.build_for_vm(vm, ssh_key, bastion_manager=mock_bastion)

        assert config.host == "127.0.0.1"
        assert config.port == 50022
        assert config.user == "azureuser"
        assert config.key_path == ssh_key

        # Verify tunnel was created
        mock_bastion.create_tunnel.assert_called_once()

    def test_build_config_for_vm_with_no_ip_fails(self):
        """Test error when VM has neither public nor private IP."""
        vm = VMInfo(
            name="no-ip-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip=None,
            private_ip=None,
        )
        ssh_key = Path("/home/user/.ssh/azlin_key")

        with pytest.raises(ValueError, match="no IP address"):
            SSHConfigBuilder.build_for_vm(vm, ssh_key, bastion_manager=None)

    def test_build_config_for_stopped_vm_fails(self):
        """Test error when VM is not running."""
        vm = VMInfo(
            name="stopped-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM stopped",
            public_ip="20.1.2.3",
        )
        ssh_key = Path("/home/user/.ssh/azlin_key")

        with pytest.raises(ValueError, match="not running"):
            SSHConfigBuilder.build_for_vm(vm, ssh_key, bastion_manager=None)

    @patch("azlin.modules.bastion_manager.BastionManager")
    def test_build_configs_for_mixed_vms(self, mock_bastion_mgr):
        """Test building configs for mix of public and private VMs."""
        vms = [
            VMInfo(
                name="public-vm-1",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip="20.1.2.3",
                private_ip="10.0.0.1",
            ),
            VMInfo(
                name="private-vm-1",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip=None,
                private_ip="10.0.0.2",
            ),
            VMInfo(
                name="public-vm-2",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip="20.1.2.4",
                private_ip="10.0.0.3",
            ),
        ]
        ssh_key = Path("/home/user/.ssh/azlin_key")

        # Mock bastion manager
        mock_bastion = MagicMock()
        mock_tunnel = Mock()
        mock_tunnel.local_port = 50022
        mock_bastion.create_tunnel.return_value = mock_tunnel

        # Should build configs for all VMs
        configs = SSHConfigBuilder.build_for_vms(vms, ssh_key, bastion_manager=mock_bastion)

        assert len(configs) == 3

        # First VM should use direct connection
        assert configs[0].host == "20.1.2.3"
        assert configs[0].port == 22

        # Second VM should use bastion
        assert configs[1].host == "127.0.0.1"
        assert configs[1].port == 50022

        # Third VM should use direct connection
        assert configs[2].host == "20.1.2.4"
        assert configs[2].port == 22

        # Bastion tunnel should be created once for private VM
        assert mock_bastion.create_tunnel.call_count == 1


class TestBastionTunnelLifecycle:
    """Test bastion tunnel creation and cleanup lifecycle."""

    @patch("azlin.modules.bastion_manager.BastionManager")
    def test_tunnel_created_on_demand(self, mock_bastion_mgr):
        """Test tunnel is created when needed for private VM."""
        mock_bastion = MagicMock()
        mock_tunnel = Mock()
        mock_tunnel.local_port = 50022
        mock_bastion.create_tunnel.return_value = mock_tunnel

        vm = VMInfo(
            name="private-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip=None,
            private_ip="10.0.0.2",
        )

        # Tunnel should be created
        config = SSHConfigBuilder.build_for_vm(
            vm, Path("/tmp/key"), bastion_manager=mock_bastion
        )

        assert config.port == 50022
        mock_bastion.create_tunnel.assert_called_once()

    @patch("azlin.modules.bastion_manager.BastionManager")
    def test_tunnel_reused_for_multiple_connections(self, mock_bastion_mgr):
        """Test same tunnel can be reused for multiple SSH connections."""
        mock_bastion = MagicMock()
        mock_tunnel = Mock()
        mock_tunnel.local_port = 50022
        mock_bastion.create_tunnel.return_value = mock_tunnel

        vm = VMInfo(
            name="private-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip=None,
            private_ip="10.0.0.2",
        )

        # Create config twice
        config1 = SSHConfigBuilder.build_for_vm(
            vm, Path("/tmp/key"), bastion_manager=mock_bastion
        )
        config2 = SSHConfigBuilder.build_for_vm(
            vm, Path("/tmp/key"), bastion_manager=mock_bastion
        )

        # Should use same port
        assert config1.port == config2.port
        assert config1.port == 50022

    @patch("azlin.modules.bastion_manager.BastionManager")
    def test_tunnel_cleanup_on_error(self, mock_bastion_mgr):
        """Test tunnel is cleaned up if SSH connection fails."""
        mock_bastion = MagicMock()
        mock_tunnel = Mock()
        mock_tunnel.local_port = 50022
        mock_bastion.create_tunnel.side_effect = Exception("Tunnel creation failed")

        vm = VMInfo(
            name="private-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip=None,
            private_ip="10.0.0.2",
        )

        # Should propagate error
        with pytest.raises(Exception, match="Tunnel creation failed"):
            SSHConfigBuilder.build_for_vm(
                vm, Path("/tmp/key"), bastion_manager=mock_bastion
            )


class TestVMConnectivityDetection:
    """Test VM connectivity detection logic."""

    def test_vm_has_direct_connectivity_with_public_ip(self):
        """Test VM with public IP has direct connectivity."""
        vm = VMInfo(
            name="public-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )

        assert SSHConfigBuilder.has_direct_connectivity(vm) is True

    def test_vm_needs_bastion_without_public_ip(self):
        """Test VM without public IP needs bastion."""
        vm = VMInfo(
            name="private-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip=None,
            private_ip="10.0.0.2",
        )

        assert SSHConfigBuilder.has_direct_connectivity(vm) is False

    def test_vm_needs_bastion_with_empty_public_ip(self):
        """Test VM with empty string public IP needs bastion."""
        vm = VMInfo(
            name="private-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip="",
            private_ip="10.0.0.2",
        )

        assert SSHConfigBuilder.has_direct_connectivity(vm) is False

    def test_unreachable_vm_without_any_ip(self):
        """Test VM without any IP is unreachable."""
        vm = VMInfo(
            name="no-ip-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip=None,
            private_ip=None,
        )

        assert SSHConfigBuilder.is_reachable(vm) is False

    def test_stopped_vm_is_unreachable(self):
        """Test stopped VM is unreachable."""
        vm = VMInfo(
            name="stopped-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM stopped",
            public_ip="20.1.2.3",
        )

        assert SSHConfigBuilder.is_reachable(vm) is False

    def test_filter_reachable_vms(self):
        """Test filtering only reachable VMs."""
        vms = [
            VMInfo(
                name="public-vm",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip="20.1.2.3",
            ),
            VMInfo(
                name="private-vm",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip=None,
                private_ip="10.0.0.2",
            ),
            VMInfo(
                name="stopped-vm",
                resource_group="test-rg",
                location="westus2",
                power_state="VM stopped",
                public_ip="20.1.2.4",
            ),
            VMInfo(
                name="no-ip-vm",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip=None,
                private_ip=None,
            ),
        ]

        reachable = SSHConfigBuilder.filter_reachable_vms(vms)

        # Should include only running VMs with at least one IP
        assert len(reachable) == 2
        assert reachable[0].name == "public-vm"
        assert reachable[1].name == "private-vm"
