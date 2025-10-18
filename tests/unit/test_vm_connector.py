"""Unit tests for vm_connector module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.modules.ssh_keys import SSHKeyError, SSHKeyPair
from azlin.terminal_launcher import TerminalLauncherError
from azlin.vm_connector import ConnectionInfo, VMConnector, VMConnectorError
from azlin.vm_manager import VMInfo


class TestVMConnector:
    """Test VMConnector class."""

    def test_is_valid_ip_valid(self):
        """Test IP validation with valid IPs."""
        assert VMConnector._is_valid_ip("192.168.1.1") is True
        assert VMConnector._is_valid_ip("10.0.0.1") is True
        assert VMConnector._is_valid_ip("172.16.0.1") is True
        assert VMConnector._is_valid_ip("20.1.2.3") is True
        assert VMConnector._is_valid_ip("255.255.255.255") is True

    def test_is_valid_ip_invalid(self):
        """Test IP validation with invalid IPs."""
        assert VMConnector._is_valid_ip("my-vm-name") is False
        assert VMConnector._is_valid_ip("azlin-vm-12345") is False
        assert VMConnector._is_valid_ip("256.1.1.1") is False
        assert VMConnector._is_valid_ip("192.168.1") is False
        assert VMConnector._is_valid_ip("192.168.1.1.1") is False
        assert VMConnector._is_valid_ip("192.168.-1.1") is False
        assert VMConnector._is_valid_ip("") is False
        assert VMConnector._is_valid_ip("invalid") is False

    @patch("azlin.vm_connector.VMManager")
    @patch("azlin.vm_connector.ConfigManager")
    def test_resolve_connection_info_by_ip(self, mock_config_mgr, mock_vm_mgr):
        """Test resolving connection info by IP address."""
        conn_info = VMConnector._resolve_connection_info(
            vm_identifier="20.1.2.3", resource_group=None, ssh_user="testuser", ssh_key_path=None
        )

        assert conn_info.vm_name == "20.1.2.3"
        assert conn_info.ip_address == "20.1.2.3"
        assert conn_info.resource_group == "unknown"
        assert conn_info.ssh_user == "testuser"

        # Should not call VMManager for IP
        mock_vm_mgr.get_vm.assert_not_called()

    @patch("azlin.vm_connector.VMManager")
    @patch("azlin.vm_connector.ConfigManager")
    def test_resolve_connection_info_by_name_with_rg(self, mock_config_mgr, mock_vm_mgr):
        """Test resolving connection info by VM name with explicit resource group."""
        # Mock VM info
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        conn_info = VMConnector._resolve_connection_info(
            vm_identifier="my-vm", resource_group="my-rg", ssh_user="azureuser", ssh_key_path=None
        )

        assert conn_info.vm_name == "my-vm"
        assert conn_info.ip_address == "20.1.2.3"
        assert conn_info.resource_group == "my-rg"
        assert conn_info.ssh_user == "azureuser"

        mock_vm_mgr.get_vm.assert_called_once_with("my-vm", "my-rg")

    @patch("azlin.vm_connector.VMManager")
    @patch("azlin.vm_connector.ConfigManager")
    def test_resolve_connection_info_by_name_from_config(self, mock_config_mgr, mock_vm_mgr):
        """Test resolving connection info using resource group from config."""
        # Mock config
        mock_config = MagicMock()
        mock_config.default_resource_group = "config-rg"
        mock_config_mgr.load_config.return_value = mock_config

        # Mock VM info
        vm_info = VMInfo(
            name="my-vm",
            resource_group="config-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        conn_info = VMConnector._resolve_connection_info(
            vm_identifier="my-vm", resource_group=None, ssh_user="azureuser", ssh_key_path=None
        )

        assert conn_info.vm_name == "my-vm"
        assert conn_info.ip_address == "20.1.2.3"
        assert conn_info.resource_group == "config-rg"

        mock_config_mgr.load_config.assert_called_once()
        mock_vm_mgr.get_vm.assert_called_once_with("my-vm", "config-rg")

    @patch("azlin.vm_connector.VMManager")
    @patch("azlin.vm_connector.ConfigManager")
    def test_resolve_connection_info_no_resource_group(self, mock_config_mgr, mock_vm_mgr):
        """Test error when no resource group available for VM name."""
        # Mock config with no default resource group
        mock_config = MagicMock()
        mock_config.default_resource_group = None
        mock_config_mgr.load_config.return_value = mock_config

        with pytest.raises(VMConnectorError, match="Resource group required"):
            VMConnector._resolve_connection_info(
                vm_identifier="my-vm", resource_group=None, ssh_user="azureuser", ssh_key_path=None
            )

    @patch("azlin.vm_connector.VMManager")
    def test_resolve_connection_info_vm_not_found(self, mock_vm_mgr):
        """Test error when VM not found."""
        mock_vm_mgr.get_vm.return_value = None

        with pytest.raises(VMConnectorError, match="VM not found"):
            VMConnector._resolve_connection_info(
                vm_identifier="nonexistent-vm",
                resource_group="my-rg",
                ssh_user="azureuser",
                ssh_key_path=None,
            )

    @patch("azlin.vm_connector.VMManager")
    def test_resolve_connection_info_vm_no_public_ip(self, mock_vm_mgr):
        """Test error when VM has no public IP."""
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip=None,
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        with pytest.raises(VMConnectorError, match="has no public IP"):
            VMConnector._resolve_connection_info(
                vm_identifier="my-vm",
                resource_group="my-rg",
                ssh_user="azureuser",
                ssh_key_path=None,
            )

    @patch("azlin.vm_connector.SSHReconnectHandler")
    @patch("azlin.vm_connector.SSHKeyManager")
    @patch("azlin.vm_connector.VMManager")
    def test_connect_by_ip(self, mock_vm_mgr, mock_ssh_key_mgr, mock_reconnect_handler):
        """Test connecting by IP address with reconnect."""
        # Mock SSH keys
        ssh_keys = SSHKeyPair(
            private_path=Path("/home/user/.ssh/azlin_key"),
            public_path=Path("/home/user/.ssh/azlin_key.pub"),
            public_key_content="ssh-ed25519 AAAA...",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = ssh_keys

        # Mock reconnect handler
        mock_handler_instance = MagicMock()
        mock_handler_instance.connect_with_reconnect.return_value = 0
        mock_reconnect_handler.return_value = mock_handler_instance

        # Connect by IP
        result = VMConnector.connect_by_ip(
            ip_address="20.1.2.3", use_tmux=True, ssh_user="azureuser"
        )

        assert result is True
        mock_ssh_key_mgr.ensure_key_exists.assert_called_once()
        mock_reconnect_handler.assert_called_once_with(max_retries=3)
        mock_handler_instance.connect_with_reconnect.assert_called_once()

    @patch("azlin.vm_connector.SSHReconnectHandler")
    @patch("azlin.vm_connector.SSHKeyManager")
    @patch("azlin.vm_connector.VMManager")
    def test_connect_by_name(self, mock_vm_mgr, mock_ssh_key_mgr, mock_reconnect_handler):
        """Test connecting by VM name with reconnect."""
        # Mock VM info
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        # Mock SSH keys
        ssh_keys = SSHKeyPair(
            private_path=Path("/home/user/.ssh/azlin_key"),
            public_path=Path("/home/user/.ssh/azlin_key.pub"),
            public_key_content="ssh-ed25519 AAAA...",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = ssh_keys

        # Mock reconnect handler
        mock_handler_instance = MagicMock()
        mock_handler_instance.connect_with_reconnect.return_value = 0
        mock_reconnect_handler.return_value = mock_handler_instance

        # Connect by name
        result = VMConnector.connect_by_name(vm_name="my-vm", resource_group="my-rg", use_tmux=True)

        assert result is True
        mock_vm_mgr.get_vm.assert_called_once_with("my-vm", "my-rg")
        mock_reconnect_handler.assert_called_once_with(max_retries=3)

        # Verify reconnect was called with correct params
        call_args = mock_handler_instance.connect_with_reconnect.call_args
        assert call_args.kwargs["vm_name"] == "my-vm"
        assert call_args.kwargs["tmux_session"] == "my-vm"
        assert call_args.kwargs["auto_tmux"] is True

    @patch("azlin.vm_connector.TerminalLauncher")
    @patch("azlin.vm_connector.SSHKeyManager")
    @patch("azlin.vm_connector.VMManager")
    def test_connect_with_command(self, mock_vm_mgr, mock_ssh_key_mgr, mock_terminal):
        """Test connecting with remote command."""
        # Mock VM info
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        # Mock SSH keys
        ssh_keys = SSHKeyPair(
            private_path=Path("/home/user/.ssh/azlin_key"),
            public_path=Path("/home/user/.ssh/azlin_key.pub"),
            public_key_content="ssh-ed25519 AAAA...",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = ssh_keys

        # Mock terminal launch
        mock_terminal.launch.return_value = True

        # Connect with command
        result = VMConnector.connect(
            vm_identifier="my-vm", resource_group="my-rg", remote_command="ls -la"
        )

        assert result is True

        # Verify terminal config includes command
        call_args = mock_terminal.launch.call_args
        config = call_args[0][0]
        assert config.command == "ls -la"

    @patch("azlin.vm_connector.SSHReconnectHandler")
    @patch("azlin.vm_connector.SSHKeyManager")
    @patch("azlin.vm_connector.VMManager")
    def test_connect_no_tmux(self, mock_vm_mgr, mock_ssh_key_mgr, mock_reconnect_handler):
        """Test connecting without tmux."""
        # Mock VM info
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        # Mock SSH keys
        ssh_keys = SSHKeyPair(
            private_path=Path("/home/user/.ssh/azlin_key"),
            public_path=Path("/home/user/.ssh/azlin_key.pub"),
            public_key_content="ssh-ed25519 AAAA...",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = ssh_keys

        # Mock reconnect handler
        mock_handler_instance = MagicMock()
        mock_handler_instance.connect_with_reconnect.return_value = 0
        mock_reconnect_handler.return_value = mock_handler_instance

        # Connect without tmux
        result = VMConnector.connect(vm_identifier="my-vm", resource_group="my-rg", use_tmux=False)

        assert result is True

        # Verify reconnect was called without tmux
        call_args = mock_handler_instance.connect_with_reconnect.call_args
        assert call_args.kwargs["auto_tmux"] is False

    def test_connect_by_ip_invalid_ip(self):
        """Test error with invalid IP address."""
        with pytest.raises(VMConnectorError, match="Invalid IP address"):
            VMConnector.connect_by_ip("not-an-ip")

    @patch("azlin.vm_connector.SSHKeyManager")
    @patch("azlin.vm_connector.VMManager")
    def test_connect_ssh_key_error(self, mock_vm_mgr, mock_ssh_key_mgr):
        """Test error when SSH key operations fail."""
        # Mock VM info
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        # Mock SSH key error
        mock_ssh_key_mgr.ensure_key_exists.side_effect = SSHKeyError("Key generation failed")

        with pytest.raises(VMConnectorError, match="SSH key error"):
            VMConnector.connect("my-vm", resource_group="my-rg")

    @patch("azlin.vm_connector.TerminalLauncher")
    @patch("azlin.vm_connector.SSHKeyManager")
    @patch("azlin.vm_connector.VMManager")
    def test_connect_terminal_launch_error(self, mock_vm_mgr, mock_ssh_key_mgr, mock_terminal):
        """Test error when terminal launch fails (with remote command, bypasses reconnect)."""
        # Mock VM info
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        # Mock SSH keys
        ssh_keys = SSHKeyPair(
            private_path=Path("/home/user/.ssh/azlin_key"),
            public_path=Path("/home/user/.ssh/azlin_key.pub"),
            public_key_content="ssh-ed25519 AAAA...",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = ssh_keys

        # Mock terminal launch error
        mock_terminal.launch.side_effect = TerminalLauncherError("Launch failed")

        # Use remote_command to force terminal launcher path
        with pytest.raises(VMConnectorError, match="Failed to launch terminal"):
            VMConnector.connect("my-vm", resource_group="my-rg", remote_command="ls -la")


class TestConnectionInfo:
    """Test ConnectionInfo dataclass."""

    def test_connection_info_creation(self):
        """Test creating ConnectionInfo object."""
        conn_info = ConnectionInfo(
            vm_name="my-vm",
            ip_address="20.1.2.3",
            resource_group="my-rg",
            ssh_user="testuser",
            ssh_key_path=Path("/path/to/key"),
        )

        assert conn_info.vm_name == "my-vm"
        assert conn_info.ip_address == "20.1.2.3"
        assert conn_info.resource_group == "my-rg"
        assert conn_info.ssh_user == "testuser"
        assert conn_info.ssh_key_path == Path("/path/to/key")

    def test_connection_info_defaults(self):
        """Test ConnectionInfo default values."""
        conn_info = ConnectionInfo(vm_name="my-vm", ip_address="20.1.2.3", resource_group="my-rg")

        assert conn_info.ssh_user == "azureuser"
        assert conn_info.ssh_key_path is None

    @patch("azlin.vm_connector.SSHReconnectHandler")
    @patch("azlin.vm_connector.SSHKeyManager")
    @patch("azlin.vm_connector.VMManager")
    def test_connect_with_reconnect_enabled(
        self, mock_vm_mgr, mock_ssh_key_mgr, mock_reconnect_handler
    ):
        """Test connecting with auto-reconnect enabled (default)."""
        # Mock VM info
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        # Mock SSH keys
        ssh_keys = SSHKeyPair(
            private_path=Path("/home/user/.ssh/azlin_key"),
            public_path=Path("/home/user/.ssh/azlin_key.pub"),
            public_key_content="ssh-ed25519 AAAA...",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = ssh_keys

        # Mock reconnect handler
        mock_handler_instance = MagicMock()
        mock_handler_instance.connect_with_reconnect.return_value = 0
        mock_reconnect_handler.return_value = mock_handler_instance

        # Connect with default (reconnect enabled)
        result = VMConnector.connect(
            vm_identifier="my-vm", resource_group="my-rg", enable_reconnect=True
        )

        assert result is True
        mock_reconnect_handler.assert_called_once_with(max_retries=3)
        mock_handler_instance.connect_with_reconnect.assert_called_once()

    @patch("azlin.vm_connector.TerminalLauncher")
    @patch("azlin.vm_connector.SSHKeyManager")
    @patch("azlin.vm_connector.VMManager")
    def test_connect_with_reconnect_disabled(self, mock_vm_mgr, mock_ssh_key_mgr, mock_terminal):
        """Test connecting with auto-reconnect disabled."""
        # Mock VM info
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        # Mock SSH keys
        ssh_keys = SSHKeyPair(
            private_path=Path("/home/user/.ssh/azlin_key"),
            public_path=Path("/home/user/.ssh/azlin_key.pub"),
            public_key_content="ssh-ed25519 AAAA...",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = ssh_keys

        # Mock terminal launch
        mock_terminal.launch.return_value = True

        # Connect with reconnect disabled
        result = VMConnector.connect(
            vm_identifier="my-vm", resource_group="my-rg", enable_reconnect=False
        )

        assert result is True
        # Should use terminal launcher, not reconnect handler
        mock_terminal.launch.assert_called_once()

    @patch("azlin.vm_connector.SSHReconnectHandler")
    @patch("azlin.vm_connector.SSHKeyManager")
    @patch("azlin.vm_connector.VMManager")
    def test_connect_with_custom_retry_count(
        self, mock_vm_mgr, mock_ssh_key_mgr, mock_reconnect_handler
    ):
        """Test connecting with custom reconnect retry count."""
        # Mock VM info
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        # Mock SSH keys
        ssh_keys = SSHKeyPair(
            private_path=Path("/home/user/.ssh/azlin_key"),
            public_path=Path("/home/user/.ssh/azlin_key.pub"),
            public_key_content="ssh-ed25519 AAAA...",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = ssh_keys

        # Mock reconnect handler
        mock_handler_instance = MagicMock()
        mock_handler_instance.connect_with_reconnect.return_value = 0
        mock_reconnect_handler.return_value = mock_handler_instance

        # Connect with custom retry count
        result = VMConnector.connect(
            vm_identifier="my-vm", resource_group="my-rg", max_reconnect_retries=5
        )

        assert result is True
        mock_reconnect_handler.assert_called_once_with(max_retries=5)

    @patch("azlin.vm_connector.SSHReconnectHandler")
    @patch("azlin.vm_connector.SSHKeyManager")
    @patch("azlin.vm_connector.VMManager")
    def test_connect_with_reconnect_failure(
        self, mock_vm_mgr, mock_ssh_key_mgr, mock_reconnect_handler
    ):
        """Test connecting when reconnect fails."""
        # Mock VM info
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        # Mock SSH keys
        ssh_keys = SSHKeyPair(
            private_path=Path("/home/user/.ssh/azlin_key"),
            public_path=Path("/home/user/.ssh/azlin_key.pub"),
            public_key_content="ssh-ed25519 AAAA...",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = ssh_keys

        # Mock reconnect handler with non-zero exit
        mock_handler_instance = MagicMock()
        mock_handler_instance.connect_with_reconnect.return_value = 255
        mock_reconnect_handler.return_value = mock_handler_instance

        # Connect should return False on non-zero exit
        result = VMConnector.connect(vm_identifier="my-vm", resource_group="my-rg")

        assert result is False
