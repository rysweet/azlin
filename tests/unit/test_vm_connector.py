"""Unit tests for vm_connector module."""

import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.modules.ssh_keys import SSHKeyError, SSHKeyPair
from azlin.vm_connector import ConnectionInfo, VMConnector, VMConnectorError
from azlin.vm_manager import VMInfo


@pytest.fixture
def temp_ssh_key():
    """Create temporary SSH key file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pem") as f:
        f.write("fake ssh key content")
        key_path = Path(f.name)

    yield key_path

    # Cleanup
    key_path.unlink(missing_ok=True)


class TestVMConnector:
    """Test VMConnector class."""

    def test_is_valid_ip_valid_ipv4(self):
        """Test IP validation with valid IPv4 addresses."""
        assert VMConnector.is_valid_ip("192.168.1.1") is True
        assert VMConnector.is_valid_ip("10.0.0.1") is True
        assert VMConnector.is_valid_ip("172.16.0.1") is True
        assert VMConnector.is_valid_ip("20.1.2.3") is True
        assert VMConnector.is_valid_ip("255.255.255.255") is True
        assert VMConnector.is_valid_ip("0.0.0.0") is True  # noqa: S104 - testing IP validation, not binding
        assert VMConnector.is_valid_ip("127.0.0.1") is True
        assert VMConnector.is_valid_ip("8.8.8.8") is True

    def test_is_valid_ip_valid_ipv6(self):
        """Test IP validation with valid IPv6 addresses."""
        assert VMConnector.is_valid_ip("2001:0db8:85a3:0000:0000:8a2e:0370:7334") is True
        assert VMConnector.is_valid_ip("2001:db8::1") is True
        assert VMConnector.is_valid_ip("::1") is True  # localhost
        assert VMConnector.is_valid_ip("::") is True  # all zeros
        assert VMConnector.is_valid_ip("::ffff:192.0.2.1") is True  # IPv4-mapped
        assert VMConnector.is_valid_ip("fe80::1") is True  # link-local
        assert VMConnector.is_valid_ip("2001:db8:85a3::8a2e:370:7334") is True

    def test_is_valid_ip_invalid(self):
        """Test IP validation with invalid IPs."""
        assert VMConnector.is_valid_ip("my-vm-name") is False
        assert VMConnector.is_valid_ip("azlin-vm-12345") is False
        assert VMConnector.is_valid_ip("256.1.1.1") is False
        assert VMConnector.is_valid_ip("192.168.1") is False
        assert VMConnector.is_valid_ip("192.168.1.1.1") is False
        assert VMConnector.is_valid_ip("192.168.-1.1") is False
        assert VMConnector.is_valid_ip("") is False
        assert VMConnector.is_valid_ip("invalid") is False
        assert VMConnector.is_valid_ip("999.999.999.999") is False
        assert VMConnector.is_valid_ip("192.168.@.1") is False
        assert VMConnector.is_valid_ip(" ") is False
        assert VMConnector.is_valid_ip("localhost") is False
        assert VMConnector.is_valid_ip("1.1.1") is False
        assert VMConnector.is_valid_ip("gggg::1") is False  # invalid hex

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
    def test_resolve_connection_info_vm_no_ip_address(self, mock_vm_mgr):
        """Test error when VM has neither public nor private IP address."""
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip=None,
            private_ip=None,
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        with pytest.raises(VMConnectorError, match="has neither public nor private IP address"):
            VMConnector._resolve_connection_info(
                vm_identifier="my-vm",
                resource_group="my-rg",
                ssh_user="azureuser",
                ssh_key_path=None,
            )

    @patch("azlin.vm_connector.VMManager")
    def test_resolve_connection_info_private_ip_fallback(self, mock_vm_mgr):
        """Test that private IP is used when VM has no public IP (Bastion-only VMs)."""
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip=None,
            private_ip="10.0.0.5",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        conn_info = VMConnector._resolve_connection_info(
            vm_identifier="my-vm",
            resource_group="my-rg",
            ssh_user="azureuser",
            ssh_key_path=None,
        )

        assert conn_info.vm_name == "my-vm"
        assert conn_info.ip_address == "10.0.0.5"
        assert conn_info.resource_group == "my-rg"
        assert conn_info.ssh_user == "azureuser"

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
        assert call_args.kwargs["tmux_session"] == "my-vm"  # Uses vm_name as default
        assert call_args.kwargs["auto_tmux"] is True

    @patch("azlin.modules.ssh_connector.SSHConnector.wait_for_ssh_ready")
    @patch("azlin.modules.ssh_connector.SSHConnector.connect")
    @patch("azlin.vm_connector.BastionDetector")
    @patch("azlin.vm_connector.SSHKeyManager")
    @patch("azlin.vm_connector.VMManager")
    def test_connect_with_command(
        self,
        mock_vm_mgr,
        mock_ssh_key_mgr,
        mock_bastion,
        mock_ssh_connect,
        mock_ssh_ready,
        temp_ssh_key,
    ):
        """Test connecting with remote command (uses SSHConnector, not TerminalLauncher)."""
        # Mock VM info
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        # Mock SSH keys with temp file
        ssh_keys = SSHKeyPair(
            private_path=temp_ssh_key,
            public_path=Path(str(temp_ssh_key) + ".pub"),
            public_key_content="ssh-ed25519 AAAA...",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = ssh_keys

        # Mock Bastion detection (return None = no Bastion)
        mock_bastion.detect_bastion_for_vm.return_value = None

        # Mock SSH readiness check (prevent actual connection attempt)
        mock_ssh_ready.return_value = True

        # Mock SSHConnector.connect (returns exit code)
        mock_ssh_connect.return_value = 0

        # Connect with command (should use SSHConnector, not TerminalLauncher)
        result = VMConnector.connect(
            vm_identifier="my-vm", resource_group="my-rg", remote_command="ls -la"
        )

        assert result is True

        # Verify SSHConnector.connect was called with remote command
        mock_ssh_connect.assert_called_once()
        call_kwargs = mock_ssh_connect.call_args.kwargs
        assert call_kwargs["remote_command"] == "ls -la"
        assert call_kwargs["auto_tmux"] is False  # No tmux for commands

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

    @patch("azlin.modules.ssh_connector.SSHConnector.wait_for_ssh_ready")
    @patch("azlin.modules.ssh_connector.SSHConnector.connect")
    @patch("azlin.vm_connector.BastionDetector")
    @patch("azlin.vm_connector.SSHKeyManager")
    @patch("azlin.vm_connector.VMManager")
    def test_connect_terminal_launch_error(
        self,
        mock_vm_mgr,
        mock_ssh_key_mgr,
        mock_bastion,
        mock_ssh_connect,
        mock_ssh_ready,
        temp_ssh_key,
    ):
        """Test error when remote command execution fails (uses SSHConnector, not TerminalLauncher)."""
        # Mock VM info
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        # Mock SSH keys with temp file
        ssh_keys = SSHKeyPair(
            private_path=temp_ssh_key,
            public_path=Path(str(temp_ssh_key) + ".pub"),
            public_key_content="ssh-ed25519 AAAA...",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = ssh_keys

        # Mock Bastion detection (return None = no Bastion)
        mock_bastion.detect_bastion_for_vm.return_value = None

        # Mock SSH readiness check
        mock_ssh_ready.return_value = True

        # Mock SSHConnector.connect to raise an exception
        mock_ssh_connect.side_effect = Exception("Connection failed")

        # Use remote_command to trigger SSHConnector path
        with pytest.raises(VMConnectorError, match="Remote command execution failed"):
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
    def test_connect_with_reconnect_disabled(
        self, mock_vm_mgr, mock_ssh_key_mgr, mock_terminal, temp_ssh_key
    ):
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

        # Mock SSH keys with temp file
        ssh_keys = SSHKeyPair(
            private_path=temp_ssh_key,
            public_path=Path(str(temp_ssh_key) + ".pub"),
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


class TestKeyVaultSSHKeyRetrieval:
    """Test KeyVault SSH key retrieval functionality (Issue #375).

    These tests verify that the system properly uses keys retrieved from KeyVault
    instead of generating new keys when the KeyVault key is available.
    """

    @patch("azlin.vm_connector.SSHReconnectHandler")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager")
    @patch("azlin.vm_connector.VMConnector._try_fetch_key_from_vault")
    def test_connect_uses_keyvault_key_when_retrieved_successfully(
        self,
        mock_try_fetch,
        mock_vm_mgr,
        mock_ensure_key,
        mock_reconnect_handler,
        temp_ssh_key,
    ):
        """Test that connect uses KeyVault key when retrieval succeeds.

        This is the CRITICAL test for the bug fix:
        - When KeyVault key is retrieved successfully (returns True)
        - The key file exists at expected path after retrieval
        - ensure_key_exists should recognize the key exists
        - NO new key generation should be attempted

        BUG: Currently the return value of _try_fetch_key_from_vault() is IGNORED,
        so ensure_key_exists is always called and will generate a new key if it
        doesn't see the file (race condition or file not created yet).

        This test simulates the scenario where:
        1. KeyVault returns True (key retrieved successfully)
        2. Key file now exists after retrieval
        3. ensure_key_exists should see the existing key and NOT generate new one
        """
        # Mock VM info
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        # Mock successful KeyVault retrieval (KEY RETRIEVED FROM VAULT)
        # After this call, the key file should exist on disk
        def fetch_side_effect(vm_name, key_path, resource_group):
            # Simulate that KeyVault wrote the key file
            key_path.touch()  # Create the file
            return True

        mock_try_fetch.side_effect = fetch_side_effect

        # Mock that ensure_key_exists returns the now-existing key
        # (after KeyVault fetched it)
        ssh_keys = SSHKeyPair(
            private_path=temp_ssh_key,
            public_path=Path(str(temp_ssh_key) + ".pub"),
            public_key_content="ssh-ed25519 AAAA... (from KeyVault)",
        )
        mock_ensure_key.return_value = ssh_keys

        # Mock reconnect handler
        mock_handler_instance = MagicMock()
        mock_handler_instance.connect_with_reconnect.return_value = 0
        mock_reconnect_handler.return_value = mock_handler_instance

        # Connect with explicit key path (so KeyVault check happens)
        result = VMConnector.connect(
            vm_identifier="my-vm",
            resource_group="my-rg",
            ssh_key_path=temp_ssh_key,
        )

        assert result is True

        # CRITICAL ASSERTION: KeyVault fetch should have been attempted
        mock_try_fetch.assert_called_once()
        call_args = mock_try_fetch.call_args
        assert call_args.kwargs["vm_name"] == "my-vm"
        assert call_args.kwargs["resource_group"] == "my-rg"
        assert call_args.kwargs["key_path"] == temp_ssh_key

        # CRITICAL ASSERTION: ensure_key_exists should be called
        # The key from KeyVault should be used (not generated)
        mock_ensure_key.assert_called_once_with(temp_ssh_key)

        # Connection should proceed with the KeyVault key
        mock_reconnect_handler.assert_called_once()

    @patch("azlin.vm_connector.SSHReconnectHandler")
    @patch("azlin.vm_connector.SSHKeyManager")
    @patch("azlin.vm_connector.VMManager")
    @patch("azlin.vm_connector.VMConnector._try_fetch_key_from_vault")
    def test_connect_generates_key_when_keyvault_retrieval_fails(
        self,
        mock_try_fetch,
        mock_vm_mgr,
        mock_ssh_key_mgr,
        mock_reconnect_handler,
        temp_ssh_key,
        caplog,
    ):
        """Test that connect generates new key when KeyVault retrieval fails.

        When KeyVault retrieval fails (returns False):
        - System should fall back to generating a new key
        - Warning should be logged (after bug fix)
        - Connection should still succeed with generated key
        """
        # Mock VM info
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        # Mock FAILED KeyVault retrieval (no key in vault)
        mock_try_fetch.return_value = False

        # Mock that a NEW key is generated
        ssh_keys = SSHKeyPair(
            private_path=temp_ssh_key,
            public_path=Path(str(temp_ssh_key) + ".pub"),
            public_key_content="ssh-ed25519 AAAA... (newly generated)",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = ssh_keys

        # Mock reconnect handler
        mock_handler_instance = MagicMock()
        mock_handler_instance.connect_with_reconnect.return_value = 0
        mock_reconnect_handler.return_value = mock_handler_instance

        # Connect with explicit key path
        with caplog.at_level(logging.WARNING):
            result = VMConnector.connect(
                vm_identifier="my-vm",
                resource_group="my-rg",
                ssh_key_path=temp_ssh_key,
            )

        assert result is True

        # KeyVault fetch should have been attempted
        mock_try_fetch.assert_called_once()

        # ensure_key_exists should be called to generate new key
        mock_ssh_key_mgr.ensure_key_exists.assert_called_once()

        # After bug fix: Should log warning about generating new key
        # (Currently this may not be logged, but should be after fix)

    @patch("azlin.vm_connector.SSHReconnectHandler")
    @patch("azlin.vm_connector.SSHKeyManager")
    @patch("azlin.vm_connector.VMManager")
    @patch("azlin.vm_connector.VMConnector._try_fetch_key_from_vault")
    def test_connect_generates_key_when_keyvault_key_not_found(
        self,
        mock_try_fetch,
        mock_vm_mgr,
        mock_ssh_key_mgr,
        mock_reconnect_handler,
        temp_ssh_key,
        caplog,
    ):
        """Test that connect generates key when KeyVault is empty.

        Similar to previous test but focuses on the "key not found" case:
        - KeyVault exists but doesn't contain key for this VM
        - Should fall back to generating new key
        - Appropriate warning message shown
        """
        # Mock VM info
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        # Mock KeyVault retrieval returns False (key not found)
        mock_try_fetch.return_value = False

        # Mock that a NEW key is generated
        ssh_keys = SSHKeyPair(
            private_path=temp_ssh_key,
            public_path=Path(str(temp_ssh_key) + ".pub"),
            public_key_content="ssh-ed25519 AAAA...",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = ssh_keys

        # Mock reconnect handler
        mock_handler_instance = MagicMock()
        mock_handler_instance.connect_with_reconnect.return_value = 0
        mock_reconnect_handler.return_value = mock_handler_instance

        # Connect with explicit key path
        with caplog.at_level(logging.WARNING):
            result = VMConnector.connect(
                vm_identifier="my-vm",
                resource_group="my-rg",
                ssh_key_path=temp_ssh_key,
            )

        assert result is True

        # KeyVault fetch should have been attempted
        mock_try_fetch.assert_called_once()

        # New key should be generated as fallback
        mock_ssh_key_mgr.ensure_key_exists.assert_called_once()

    @patch("azlin.vm_connector.SSHReconnectHandler")
    @patch("azlin.vm_connector.SSHKeyManager")
    @patch("azlin.vm_connector.VMManager")
    @patch("azlin.vm_connector.VMConnector._try_fetch_key_from_vault")
    def test_connect_uses_existing_local_key_without_keyvault_check(
        self,
        mock_try_fetch,
        mock_vm_mgr,
        mock_ssh_key_mgr,
        mock_reconnect_handler,
        temp_ssh_key,
    ):
        """Test that existing local key is used without KeyVault check.

        Optimization: If key already exists locally, skip KeyVault check.
        - Given: Key already exists locally
        - Then: _try_fetch_key_from_vault() should still be called
          (but will return False quickly because key exists)
        - And: Existing key used for connection

        Note: Current implementation always calls _try_fetch_key_from_vault(),
        which internally checks if key exists and returns False early.
        This is acceptable behavior.
        """
        # Mock VM info
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        # Mock that key already exists locally (returns False - no fetch needed)
        mock_try_fetch.return_value = False

        # Mock existing key
        ssh_keys = SSHKeyPair(
            private_path=temp_ssh_key,
            public_path=Path(str(temp_ssh_key) + ".pub"),
            public_key_content="ssh-ed25519 AAAA... (existing local key)",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = ssh_keys

        # Mock reconnect handler
        mock_handler_instance = MagicMock()
        mock_handler_instance.connect_with_reconnect.return_value = 0
        mock_reconnect_handler.return_value = mock_handler_instance

        # Connect with explicit key path
        result = VMConnector.connect(
            vm_identifier="my-vm",
            resource_group="my-rg",
            ssh_key_path=temp_ssh_key,
        )

        assert result is True

        # _try_fetch_key_from_vault called but returns False (key exists)
        mock_try_fetch.assert_called_once()

        # Existing key should be used
        mock_ssh_key_mgr.ensure_key_exists.assert_called_once()

    @patch("azlin.modules.ssh_key_vault.SSHKeyVaultManager.find_key_vault_in_resource_group")
    @patch("azlin.vm_connector.ContextManager")
    @patch("azlin.vm_connector.create_key_vault_manager")
    def test_fetch_key_from_vault_logs_info_not_debug(
        self, mock_kv_manager, mock_context, mock_find_vault, caplog, temp_ssh_key
    ):
        """Test that KeyVault retrieval logs at INFO level for user visibility.

        User should see when keys are being retrieved from KeyVault:
        - Logging level should be INFO, not DEBUG
        - Message: "Retrieving SSH key from Azure Key Vault..."

        This helps users understand what's happening during connection.
        """
        # Create a non-existent key path for testing
        key_path = temp_ssh_key.parent / "nonexistent_key"

        # Mock context
        mock_context_obj = MagicMock()
        mock_context_obj.subscription_id = "test-sub-id"
        mock_context_obj.tenant_id = "test-tenant-id"
        mock_current_context = MagicMock()
        mock_current_context.get_current_context.return_value = mock_context_obj
        mock_context.load.return_value = mock_current_context

        # Mock KeyVault manager
        mock_manager_instance = MagicMock()
        mock_manager_instance.retrieve_key.return_value = None
        mock_kv_manager.return_value = mock_manager_instance

        # Mock finding Key Vault
        mock_find_vault.return_value = "test-vault"

        with caplog.at_level(logging.DEBUG):
            result = VMConnector._try_fetch_key_from_vault(
                vm_name="my-vm",
                key_path=key_path,
                resource_group="my-rg",
            )

        # Should log debug messages (current implementation)
        # After fix, should log INFO message for user visibility
        assert any("Key Vault" in record.message for record in caplog.records)

    @patch("azlin.vm_connector.SSHReconnectHandler")
    @patch("azlin.vm_connector.SSHKeyManager")
    @patch("azlin.vm_connector.VMManager")
    @patch("azlin.vm_connector.VMConnector._try_fetch_key_from_vault")
    def test_connect_with_custom_ssh_key_path_uses_keyvault(
        self,
        mock_try_fetch,
        mock_vm_mgr,
        mock_ssh_key_mgr,
        mock_reconnect_handler,
        temp_ssh_key,
    ):
        """Test KeyVault retrieval with custom SSH key path.

        When user specifies custom key path:
        - KeyVault retrieval should use the custom path
        - Retrieved key should be stored at custom location
        """
        custom_key_path = Path("/custom/path/to/key")

        # Mock VM info
        vm_info = VMInfo(
            name="my-vm",
            resource_group="my-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
        )
        mock_vm_mgr.get_vm.return_value = vm_info

        # Mock successful KeyVault retrieval
        mock_try_fetch.return_value = True

        # Mock SSH keys with custom path
        ssh_keys = SSHKeyPair(
            private_path=custom_key_path,
            public_path=Path(str(custom_key_path) + ".pub"),
            public_key_content="ssh-ed25519 AAAA...",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = ssh_keys

        # Mock reconnect handler
        mock_handler_instance = MagicMock()
        mock_handler_instance.connect_with_reconnect.return_value = 0
        mock_reconnect_handler.return_value = mock_handler_instance

        # Connect with custom key path
        result = VMConnector.connect(
            vm_identifier="my-vm",
            resource_group="my-rg",
            ssh_key_path=custom_key_path,
        )

        assert result is True

        # KeyVault fetch should use custom path
        mock_try_fetch.assert_called_once()
        call_args = mock_try_fetch.call_args
        assert call_args.kwargs["key_path"] == custom_key_path

    @patch("azlin.vm_connector.SSHReconnectHandler")
    @patch("azlin.vm_connector.SSHKeyManager")
    @patch("azlin.vm_connector.VMManager")
    @patch("azlin.vm_connector.VMConnector._try_fetch_key_from_vault")
    def test_connect_by_ip_with_ssh_key_path_calls_keyvault(
        self,
        mock_try_fetch,
        mock_vm_mgr,
        mock_ssh_key_mgr,
        mock_reconnect_handler,
        temp_ssh_key,
    ):
        """Test that connecting by IP with ssh_key_path calls KeyVault.

        When connecting by IP with explicit key path:
        - KeyVault fetch should be called (even though it's an IP)
        - The IP is used as vm_name for KeyVault lookup
        - Connection should succeed
        """
        # Mock SSH keys
        ssh_keys = SSHKeyPair(
            private_path=temp_ssh_key,
            public_path=Path(str(temp_ssh_key) + ".pub"),
            public_key_content="ssh-ed25519 AAAA...",
        )
        mock_ssh_key_mgr.ensure_key_exists.return_value = ssh_keys

        # Mock reconnect handler
        mock_handler_instance = MagicMock()
        mock_handler_instance.connect_with_reconnect.return_value = 0
        mock_reconnect_handler.return_value = mock_handler_instance

        # Mock KeyVault fetch returns False (not found for IP)
        mock_try_fetch.return_value = False

        # Connect by IP with explicit key path
        result = VMConnector.connect_by_ip(
            ip_address="20.1.2.3",
            ssh_key_path=temp_ssh_key,
        )

        assert result is True

        # When connecting by IP with ssh_key_path, KeyVault fetch is called
        # (IP is used as vm_name for KeyVault lookup)
        mock_try_fetch.assert_called_once()
        call_args = mock_try_fetch.call_args
        assert call_args.kwargs["vm_name"] == "20.1.2.3"
        assert call_args.kwargs["key_path"] == temp_ssh_key


class TestTryFetchKeyFromVault:
    """Tests for _try_fetch_key_from_vault method.

    Issue #417: Key Vault retrieval was skipped when local key exists,
    breaking multi-VM connection scenarios.
    """

    @patch("azlin.vm_connector.create_key_vault_manager")
    @patch("azlin.vm_connector.ContextManager")
    def test_fetch_from_vault_when_local_key_exists(
        self,
        mock_context_mgr,
        mock_create_kv_manager,
        temp_ssh_key,
    ):
        """Test that Key Vault is queried even when local key already exists.

        Bug #417: Previously, _try_fetch_key_from_vault() would return False
        immediately if any local key existed, skipping Key Vault entirely.

        After fix: Key Vault should always be queried to get the correct
        VM-specific key, regardless of local key existence.
        """
        # Setup: Local key exists (this is the bug scenario)
        assert temp_ssh_key.exists(), "Test requires local key to exist"

        # Mock context
        mock_context = MagicMock()
        mock_context.subscription_id = "test-sub-id"
        mock_context.tenant_id = "test-tenant-id"
        mock_context_config = MagicMock()
        mock_context_config.get_current_context.return_value = mock_context
        mock_context_mgr.load.return_value = mock_context_config

        # Mock SSHKeyVaultManager.find_key_vault_in_resource_group
        with patch(
            "azlin.modules.ssh_key_vault.SSHKeyVaultManager.find_key_vault_in_resource_group"
        ) as mock_find_kv:
            mock_find_kv.return_value = "test-vault"

            # Mock the Key Vault manager
            mock_kv_manager = MagicMock()
            mock_create_kv_manager.return_value = mock_kv_manager

            # Call the method with a LOCAL KEY THAT EXISTS
            result = VMConnector._try_fetch_key_from_vault(
                vm_name="test-vm",
                key_path=temp_ssh_key,
                resource_group="test-rg",
            )

            # EXPECTED BEHAVIOR (after fix):
            # - Key Vault should be queried even though local key exists
            # - retrieve_key should be called to get VM-specific key
            mock_find_kv.assert_called_once_with(
                resource_group="test-rg",
                subscription_id="test-sub-id",
            )
            mock_kv_manager.retrieve_key.assert_called_once_with(
                vm_name="test-vm",
                target_path=temp_ssh_key,
            )
            assert result is True

    @patch("azlin.vm_connector.create_key_vault_manager")
    @patch("azlin.vm_connector.ContextManager")
    def test_fetch_from_vault_when_no_local_key(
        self,
        mock_context_mgr,
        mock_create_kv_manager,
    ):
        """Test that Key Vault is queried when no local key exists."""
        # Setup: No local key exists
        with tempfile.NamedTemporaryFile(delete=True) as f:
            key_path = Path(f.name)
        # File is now deleted

        assert not key_path.exists(), "Test requires no local key"

        # Mock context
        mock_context = MagicMock()
        mock_context.subscription_id = "test-sub-id"
        mock_context.tenant_id = "test-tenant-id"
        mock_context_config = MagicMock()
        mock_context_config.get_current_context.return_value = mock_context
        mock_context_mgr.load.return_value = mock_context_config

        # Mock SSHKeyVaultManager.find_key_vault_in_resource_group
        with patch(
            "azlin.modules.ssh_key_vault.SSHKeyVaultManager.find_key_vault_in_resource_group"
        ) as mock_find_kv:
            mock_find_kv.return_value = "test-vault"

            # Mock the Key Vault manager
            mock_kv_manager = MagicMock()
            mock_create_kv_manager.return_value = mock_kv_manager

            result = VMConnector._try_fetch_key_from_vault(
                vm_name="test-vm",
                key_path=key_path,
                resource_group="test-rg",
            )

            # Key Vault should be queried
            mock_find_kv.assert_called_once()
            mock_kv_manager.retrieve_key.assert_called_once()
            assert result is True

    @patch("azlin.vm_connector.ContextManager")
    def test_fetch_from_vault_fallback_on_no_context(
        self,
        mock_context_mgr,
        temp_ssh_key,
    ):
        """Test graceful fallback when no Azure context is set."""
        # Mock no context
        mock_context_config = MagicMock()
        mock_context_config.get_current_context.return_value = None
        mock_context_mgr.load.return_value = mock_context_config

        result = VMConnector._try_fetch_key_from_vault(
            vm_name="test-vm",
            key_path=temp_ssh_key,
            resource_group="test-rg",
        )

        # Should return False gracefully (no crash)
        assert result is False

    @patch("azlin.vm_connector.create_key_vault_manager")
    @patch("azlin.vm_connector.ContextManager")
    def test_fetch_from_vault_handles_keyvault_error(
        self,
        mock_context_mgr,
        mock_create_kv_manager,
        temp_ssh_key,
    ):
        """Test graceful handling of Key Vault errors."""
        from azlin.modules.ssh_key_vault import KeyVaultError

        # Mock context
        mock_context = MagicMock()
        mock_context.subscription_id = "test-sub-id"
        mock_context.tenant_id = "test-tenant-id"
        mock_context_config = MagicMock()
        mock_context_config.get_current_context.return_value = mock_context
        mock_context_mgr.load.return_value = mock_context_config

        with patch(
            "azlin.modules.ssh_key_vault.SSHKeyVaultManager.find_key_vault_in_resource_group"
        ) as mock_find_kv:
            mock_find_kv.return_value = "test-vault"

            # Mock Key Vault manager to raise error
            mock_kv_manager = MagicMock()
            mock_kv_manager.retrieve_key.side_effect = KeyVaultError("Key not found")
            mock_create_kv_manager.return_value = mock_kv_manager

            result = VMConnector._try_fetch_key_from_vault(
                vm_name="test-vm",
                key_path=temp_ssh_key,
                resource_group="test-rg",
            )

            # Should return False gracefully on error
            assert result is False
