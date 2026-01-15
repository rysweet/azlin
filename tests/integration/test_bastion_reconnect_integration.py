"""Integration tests for Bastion tunnel cleanup on SSH reconnect.

Tests the integration between:
- VMConnector passing cleanup callback to SSHReconnectHandler
- BastionManager.close_tunnel() being called on reconnect
- End-to-end cleanup behavior with real Bastion tunnels

Testing pyramid:
- 60% Unit tests (test_ssh_reconnect_cleanup.py)
- 30% Integration tests (this file)
- 10% E2E tests (existing e2e tests)
"""

from unittest.mock import MagicMock, patch

import pytest

from azlin.modules.bastion_manager import BastionManager, BastionTunnel
from azlin.modules.ssh_keys import SSHKeyPair
from azlin.vm_connector import VMConnector
from azlin.vm_manager import VMInfo


class TestBastionReconnectIntegration:
    """Integration tests for Bastion cleanup on reconnect."""

    @pytest.fixture
    def vm_info(self):
        """Create test VM info with private IP (requires Bastion)."""
        return VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip=None,  # Private-only VM
            private_ip="10.0.0.4",
        )

    @pytest.fixture
    def ssh_keys(self, tmp_path):
        """Create test SSH keys."""
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        pub_file = tmp_path / "test_key.pub"
        pub_file.write_text("ssh-ed25519 AAAA...")

        return SSHKeyPair(
            private_path=key_file,
            public_path=pub_file,
            public_key_content="ssh-ed25519 AAAA...",
        )

    @pytest.fixture
    def bastion_tunnel(self):
        """Create test Bastion tunnel."""
        return BastionTunnel(
            local_port=50022,
            bastion_name="test-bastion",
            resource_group="test-rg",
            target_vm_id="/subscriptions/.../test-vm",
            remote_port=22,
            process=MagicMock(),
        )

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    @patch("azlin.vm_connector.BastionManager")
    @patch("azlin.vm_connector.BastionDetector.detect_bastion_for_vm")
    @patch("azlin.vm_connector.VMManager.get_vm")
    @patch("azlin.vm_connector.VMManager.get_vm_resource_id")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    def test_bastion_cleanup_callback_passed_to_reconnect_handler(
        self,
        mock_ensure_keys,
        mock_get_resource_id,
        mock_get_vm,
        mock_detect_bastion,
        mock_bastion_manager_class,
        mock_should_reconnect,
        mock_ssh_connect,
        vm_info,
        ssh_keys,
        bastion_tunnel,
    ):
        """Test that VMConnector passes bastion cleanup callback to reconnect handler.

        This test will FAIL until VMConnector integration is implemented.
        """
        # Setup mocks
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_get_resource_id.return_value = "/subscriptions/.../test-vm"
        mock_detect_bastion.return_value = {
            "name": "test-bastion",
            "resource_group": "test-rg",
            "location": "westus2",
        }

        # Mock BastionManager instance
        mock_bastion_manager = MagicMock(spec=BastionManager)
        mock_bastion_manager.get_available_port.return_value = 50022
        mock_bastion_manager.create_tunnel.return_value = bastion_tunnel
        mock_bastion_manager_class.return_value = mock_bastion_manager

        # Disconnect then succeed
        mock_should_reconnect.return_value = True
        mock_ssh_connect.side_effect = [255, 0]

        # Connect with Bastion
        result = VMConnector.connect(
            vm_identifier="test-vm",
            resource_group="test-rg",
            enable_reconnect=True,
            skip_prompts=True,  # Auto-accept Bastion
        )

        # Verify connection succeeded after reconnect
        assert result is True

        # Verify bastion cleanup was called on reconnect
        # This tests that VMConnector passed close_tunnel as cleanup_callback
        mock_bastion_manager.close_tunnel.assert_called()

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    @patch("azlin.vm_connector.BastionManager")
    @patch("azlin.vm_connector.BastionDetector.detect_bastion_for_vm")
    @patch("azlin.vm_connector.VMManager.get_vm")
    @patch("azlin.vm_connector.VMManager.get_vm_resource_id")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    def test_bastion_tunnel_closed_before_reconnect_attempt(
        self,
        mock_ensure_keys,
        mock_get_resource_id,
        mock_get_vm,
        mock_detect_bastion,
        mock_bastion_manager_class,
        mock_should_reconnect,
        mock_ssh_connect,
        vm_info,
        ssh_keys,
        bastion_tunnel,
    ):
        """Test that Bastion tunnel is closed BEFORE reconnect attempt.

        This test will FAIL until cleanup ordering is correct.
        """
        call_order = []

        def track_close_tunnel(tunnel):
            call_order.append("close_tunnel")

        def track_ssh_connect(*args, **kwargs):
            call_order.append("ssh_connect")
            # First connect disconnects, second succeeds
            if call_order.count("ssh_connect") == 1:
                return 255
            return 0

        # Setup mocks
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_get_resource_id.return_value = "/subscriptions/.../test-vm"
        mock_detect_bastion.return_value = {
            "name": "test-bastion",
            "resource_group": "test-rg",
            "location": "westus2",
        }

        # Mock BastionManager with call tracking
        mock_bastion_manager = MagicMock(spec=BastionManager)
        mock_bastion_manager.get_available_port.return_value = 50022
        mock_bastion_manager.create_tunnel.return_value = bastion_tunnel
        mock_bastion_manager.close_tunnel.side_effect = track_close_tunnel
        mock_bastion_manager_class.return_value = mock_bastion_manager

        mock_should_reconnect.return_value = True
        mock_ssh_connect.side_effect = track_ssh_connect

        # Connect
        result = VMConnector.connect(
            vm_identifier="test-vm",
            resource_group="test-rg",
            enable_reconnect=True,
            skip_prompts=True,
        )

        # Verify success
        assert result is True

        # Verify call order: ssh_connect(1), close_tunnel, ssh_connect(2)
        assert call_order == ["ssh_connect", "close_tunnel", "ssh_connect"]

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    @patch("azlin.vm_connector.BastionManager")
    @patch("azlin.vm_connector.BastionDetector.detect_bastion_for_vm")
    @patch("azlin.vm_connector.VMManager.get_vm")
    @patch("azlin.vm_connector.VMManager.get_vm_resource_id")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    def test_bastion_tunnel_closed_on_each_reconnect(
        self,
        mock_ensure_keys,
        mock_get_resource_id,
        mock_get_vm,
        mock_detect_bastion,
        mock_bastion_manager_class,
        mock_should_reconnect,
        mock_ssh_connect,
        vm_info,
        ssh_keys,
        bastion_tunnel,
    ):
        """Test that Bastion tunnel is closed before EACH reconnect attempt.

        This test will FAIL until multiple cleanup calls work correctly.
        """
        # Setup mocks
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_get_resource_id.return_value = "/subscriptions/.../test-vm"
        mock_detect_bastion.return_value = {
            "name": "test-bastion",
            "resource_group": "test-rg",
            "location": "westus2",
        }

        # Mock BastionManager
        mock_bastion_manager = MagicMock(spec=BastionManager)
        mock_bastion_manager.get_available_port.return_value = 50022
        mock_bastion_manager.create_tunnel.return_value = bastion_tunnel
        mock_bastion_manager_class.return_value = mock_bastion_manager

        # Disconnect twice, then succeed
        mock_should_reconnect.return_value = True
        mock_ssh_connect.side_effect = [255, 255, 0]

        # Connect
        result = VMConnector.connect(
            vm_identifier="test-vm",
            resource_group="test-rg",
            enable_reconnect=True,
            skip_prompts=True,
        )

        # Verify success after 2 reconnects
        assert result is True
        assert mock_ssh_connect.call_count == 3

        # Verify tunnel closed twice (before 2nd and 3rd connects)
        assert mock_bastion_manager.close_tunnel.call_count == 2

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    @patch("azlin.vm_connector.BastionManager")
    @patch("azlin.vm_connector.BastionDetector.detect_bastion_for_vm")
    @patch("azlin.vm_connector.VMManager.get_vm")
    @patch("azlin.vm_connector.VMManager.get_vm_resource_id")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    def test_bastion_tunnel_not_closed_on_first_connect(
        self,
        mock_ensure_keys,
        mock_get_resource_id,
        mock_get_vm,
        mock_detect_bastion,
        mock_bastion_manager_class,
        mock_should_reconnect,
        mock_ssh_connect,
        vm_info,
        ssh_keys,
        bastion_tunnel,
    ):
        """Test that Bastion tunnel is NOT closed on first connection.

        This test will FAIL until first-connect logic is correct.
        """
        # Setup mocks
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_get_resource_id.return_value = "/subscriptions/.../test-vm"
        mock_detect_bastion.return_value = {
            "name": "test-bastion",
            "resource_group": "test-rg",
            "location": "westus2",
        }

        # Mock BastionManager
        mock_bastion_manager = MagicMock(spec=BastionManager)
        mock_bastion_manager.get_available_port.return_value = 50022
        mock_bastion_manager.create_tunnel.return_value = bastion_tunnel
        mock_bastion_manager_class.return_value = mock_bastion_manager

        # Normal exit (no reconnect)
        mock_ssh_connect.return_value = 0

        # Connect
        result = VMConnector.connect(
            vm_identifier="test-vm",
            resource_group="test-rg",
            enable_reconnect=True,
            skip_prompts=True,
        )

        # Verify success
        assert result is True
        assert mock_ssh_connect.call_count == 1

        # Verify tunnel was NOT closed (no reconnect happened)
        mock_bastion_manager.close_tunnel.assert_not_called()

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    @patch("azlin.vm_connector.BastionManager")
    @patch("azlin.vm_connector.BastionDetector.detect_bastion_for_vm")
    @patch("azlin.vm_connector.VMManager.get_vm")
    @patch("azlin.vm_connector.VMManager.get_vm_resource_id")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.modules.ssh_reconnect.logger")
    def test_bastion_cleanup_error_logged_but_reconnect_continues(
        self,
        mock_logger,
        mock_ensure_keys,
        mock_get_resource_id,
        mock_get_vm,
        mock_detect_bastion,
        mock_bastion_manager_class,
        mock_should_reconnect,
        mock_ssh_connect,
        vm_info,
        ssh_keys,
        bastion_tunnel,
    ):
        """Test that Bastion cleanup errors are logged but reconnect continues.

        This test will FAIL until error handling is implemented.
        """
        # Setup mocks
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_get_resource_id.return_value = "/subscriptions/.../test-vm"
        mock_detect_bastion.return_value = {
            "name": "test-bastion",
            "resource_group": "test-rg",
            "location": "westus2",
        }

        # Mock BastionManager with failing cleanup
        mock_bastion_manager = MagicMock(spec=BastionManager)
        mock_bastion_manager.get_available_port.return_value = 50022
        mock_bastion_manager.create_tunnel.return_value = bastion_tunnel
        mock_bastion_manager.close_tunnel.side_effect = Exception("Tunnel cleanup failed")
        mock_bastion_manager_class.return_value = mock_bastion_manager

        # Disconnect then succeed
        mock_should_reconnect.return_value = True
        mock_ssh_connect.side_effect = [255, 0]

        # Connect
        result = VMConnector.connect(
            vm_identifier="test-vm",
            resource_group="test-rg",
            enable_reconnect=True,
            skip_prompts=True,
        )

        # Verify reconnect still succeeded despite cleanup error
        assert result is True
        assert mock_ssh_connect.call_count == 2

        # Verify cleanup was attempted
        mock_bastion_manager.close_tunnel.assert_called_once()

        # Verify error was logged
        mock_logger.warning.assert_called()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "cleanup" in warning_msg.lower()

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    @patch("azlin.vm_connector.BastionManager")
    @patch("azlin.vm_connector.BastionDetector.detect_bastion_for_vm")
    @patch("azlin.vm_connector.VMManager.get_vm")
    @patch("azlin.vm_connector.VMManager.get_vm_resource_id")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    def test_no_bastion_cleanup_when_no_bastion_used(
        self,
        mock_ensure_keys,
        mock_get_resource_id,
        mock_get_vm,
        mock_detect_bastion,
        mock_bastion_manager_class,
        mock_should_reconnect,
        mock_ssh_connect,
        ssh_keys,
    ):
        """Test that no cleanup callback is passed when Bastion is not used.

        This test will FAIL until conditional callback logic is correct.
        """
        # VM with public IP (no Bastion needed)
        vm_info = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",  # Has public IP
            private_ip="10.0.0.4",
        )

        # Setup mocks
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_detect_bastion.return_value = None  # No Bastion detected

        # Disconnect then succeed
        mock_should_reconnect.return_value = True
        mock_ssh_connect.side_effect = [255, 0]

        # Connect without Bastion
        result = VMConnector.connect(
            vm_identifier="test-vm",
            resource_group="test-rg",
            enable_reconnect=True,
        )

        # Verify success
        assert result is True

        # Verify BastionManager was NOT created (no Bastion used)
        mock_bastion_manager_class.assert_not_called()

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_no_cleanup_when_reconnect_disabled(
        self,
        mock_get_vm,
        mock_ensure_keys,
        mock_ssh_connect,
        vm_info,
        ssh_keys,
    ):
        """Test that cleanup callback is not used when reconnect is disabled.

        This test will FAIL until enable_reconnect=False path is correct.
        """
        # Setup mocks
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_ssh_connect.return_value = 0

        # Connect with reconnect disabled
        with patch("azlin.vm_connector.TerminalLauncher.launch") as mock_launch:
            mock_launch.return_value = True

            result = VMConnector.connect(
                vm_identifier="test-vm",
                resource_group="test-rg",
                enable_reconnect=False,  # Reconnect disabled
            )

            # Verify success
            assert result is True

            # Verify TerminalLauncher was used (not SSHReconnectHandler)
            mock_launch.assert_called_once()

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    @patch("azlin.vm_connector.BastionManager")
    @patch("azlin.vm_connector.BastionDetector.detect_bastion_for_vm")
    @patch("azlin.vm_connector.VMManager.get_vm")
    @patch("azlin.vm_connector.VMManager.get_vm_resource_id")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    def test_bastion_tunnel_passed_to_cleanup_callback(
        self,
        mock_ensure_keys,
        mock_get_resource_id,
        mock_get_vm,
        mock_detect_bastion,
        mock_bastion_manager_class,
        mock_should_reconnect,
        mock_ssh_connect,
        vm_info,
        ssh_keys,
        bastion_tunnel,
    ):
        """Test that correct tunnel is passed to cleanup callback.

        This test will FAIL until tunnel reference is correctly passed.
        """
        # Setup mocks
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_get_resource_id.return_value = "/subscriptions/.../test-vm"
        mock_detect_bastion.return_value = {
            "name": "test-bastion",
            "resource_group": "test-rg",
            "location": "westus2",
        }

        # Mock BastionManager
        mock_bastion_manager = MagicMock(spec=BastionManager)
        mock_bastion_manager.get_available_port.return_value = 50022
        mock_bastion_manager.create_tunnel.return_value = bastion_tunnel
        mock_bastion_manager_class.return_value = mock_bastion_manager

        # Disconnect then succeed
        mock_should_reconnect.return_value = True
        mock_ssh_connect.side_effect = [255, 0]

        # Connect
        result = VMConnector.connect(
            vm_identifier="test-vm",
            resource_group="test-rg",
            enable_reconnect=True,
            skip_prompts=True,
        )

        # Verify success
        assert result is True

        # Verify close_tunnel was called with the correct tunnel
        mock_bastion_manager.close_tunnel.assert_called_with(bastion_tunnel)


class TestBastionCleanupEdgeCases:
    """Edge case tests for Bastion cleanup on reconnect."""

    @pytest.fixture
    def vm_info(self):
        """Create test VM info."""
        return VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip=None,
            private_ip="10.0.0.4",
        )

    @pytest.fixture
    def ssh_keys(self, tmp_path):
        """Create test SSH keys."""
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        return SSHKeyPair(
            private_path=key_file,
            public_path=tmp_path / "test_key.pub",
            public_key_content="ssh-ed25519 AAAA...",
        )

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    @patch("azlin.vm_connector.BastionManager")
    @patch("azlin.vm_connector.BastionDetector.detect_bastion_for_vm")
    @patch("azlin.vm_connector.VMManager.get_vm")
    @patch("azlin.vm_connector.VMManager.get_vm_resource_id")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    def test_bastion_cleanup_with_user_declined_reconnect(
        self,
        mock_ensure_keys,
        mock_get_resource_id,
        mock_get_vm,
        mock_detect_bastion,
        mock_bastion_manager_class,
        mock_should_reconnect,
        mock_ssh_connect,
        vm_info,
        ssh_keys,
    ):
        """Test that tunnel is not cleaned when user declines reconnect.

        This test will FAIL until user-decline path is correct.
        """
        # Setup mocks
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_get_resource_id.return_value = "/subscriptions/.../test-vm"
        mock_detect_bastion.return_value = {
            "name": "test-bastion",
            "resource_group": "test-rg",
            "location": "westus2",
        }

        # Mock BastionManager
        mock_bastion_manager = MagicMock(spec=BastionManager)
        mock_bastion_manager.get_available_port.return_value = 50022
        mock_bastion_manager.create_tunnel.return_value = MagicMock()
        mock_bastion_manager_class.return_value = mock_bastion_manager

        # User declines reconnect
        mock_should_reconnect.return_value = False
        mock_ssh_connect.return_value = 255  # Disconnect

        # Connect
        result = VMConnector.connect(
            vm_identifier="test-vm",
            resource_group="test-rg",
            enable_reconnect=True,
            skip_prompts=True,
        )

        # Verify failed (user declined)
        assert result is False

        # Verify tunnel was NOT cleaned (no reconnect attempted)
        mock_bastion_manager.close_tunnel.assert_not_called()
