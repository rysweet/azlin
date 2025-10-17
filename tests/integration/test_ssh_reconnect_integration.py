"""Integration tests for SSH reconnection functionality.

These tests verify the integration between vm_connector and ssh_reconnect modules.
"""

from unittest.mock import patch

import pytest
from azlin.modules.ssh_keys import SSHKeyPair
from azlin.vm_connector import VMConnector
from azlin.vm_manager import VMInfo


class TestSSHReconnectIntegration:
    """Integration tests for SSH reconnect feature."""

    @pytest.fixture
    def vm_info(self):
        """Create test VM info."""
        return VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            power_state="VM running",
            public_ip="20.1.2.3",
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
    @patch("azlin.modules.ssh_reconnect.click.confirm")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_reconnect_on_disconnect(
        self, mock_get_vm, mock_ensure_keys, mock_confirm, mock_ssh_connect, vm_info, ssh_keys
    ):
        """Test auto-reconnect when SSH disconnects."""
        # Setup mocks
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_confirm.return_value = True

        # First connect disconnects (255), second succeeds (0)
        mock_ssh_connect.side_effect = [255, 0]

        # Connect
        result = VMConnector.connect(
            vm_identifier="test-vm", resource_group="test-rg", enable_reconnect=True
        )

        # Should succeed after reconnect
        assert result is True

        # Should have connected twice
        assert mock_ssh_connect.call_count == 2

        # User should have been prompted once
        mock_confirm.assert_called_once()
        call_args = mock_confirm.call_args[0][0]
        assert "test-vm" in call_args
        assert "disconnected" in call_args

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.click.confirm")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_no_reconnect_on_user_decline(
        self, mock_get_vm, mock_ensure_keys, mock_confirm, mock_ssh_connect, vm_info, ssh_keys
    ):
        """Test that connection ends when user declines reconnect."""
        # Setup mocks
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_confirm.return_value = False  # User declines
        mock_ssh_connect.return_value = 255  # Disconnect

        # Connect
        result = VMConnector.connect(
            vm_identifier="test-vm", resource_group="test-rg", enable_reconnect=True
        )

        # Should fail (user declined)
        assert result is False

        # Should have only tried once
        assert mock_ssh_connect.call_count == 1

        # User should have been prompted
        mock_confirm.assert_called_once()

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.click.confirm")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_multiple_reconnect_attempts(
        self, mock_get_vm, mock_ensure_keys, mock_confirm, mock_ssh_connect, vm_info, ssh_keys
    ):
        """Test multiple reconnect attempts before success."""
        # Setup mocks
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_confirm.return_value = True

        # Disconnect twice, then succeed
        mock_ssh_connect.side_effect = [255, 255, 0]

        # Connect
        result = VMConnector.connect(
            vm_identifier="test-vm", resource_group="test-rg", enable_reconnect=True
        )

        # Should succeed after 2 reconnects
        assert result is True
        assert mock_ssh_connect.call_count == 3
        assert mock_confirm.call_count == 2

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.click.confirm")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_max_retries_exceeded(
        self, mock_get_vm, mock_ensure_keys, mock_confirm, mock_ssh_connect, vm_info, ssh_keys
    ):
        """Test that reconnection stops after max retries."""
        # Setup mocks
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_confirm.return_value = True
        mock_ssh_connect.return_value = 255  # Always disconnect

        # Connect with max_retries=2
        result = VMConnector.connect(
            vm_identifier="test-vm",
            resource_group="test-rg",
            enable_reconnect=True,
            max_reconnect_retries=2,
        )

        # Should fail after max retries
        assert result is False

        # Should try: initial + 2 retries = 3 times
        assert mock_ssh_connect.call_count == 3

        # Should prompt 2 times (not after last failure)
        assert mock_confirm.call_count == 2

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_normal_exit_no_reconnect_prompt(
        self, mock_get_vm, mock_ensure_keys, mock_ssh_connect, vm_info, ssh_keys
    ):
        """Test that normal exit (0) doesn't prompt for reconnect."""
        # Setup mocks
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_ssh_connect.return_value = 0  # Normal exit

        # Connect
        with patch("azlin.modules.ssh_reconnect.click.confirm") as mock_confirm:
            result = VMConnector.connect(
                vm_identifier="test-vm", resource_group="test-rg", enable_reconnect=True
            )

            # Should succeed
            assert result is True

            # Should not prompt for reconnect
            mock_confirm.assert_not_called()

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_ctrl_c_no_reconnect_prompt(
        self, mock_get_vm, mock_ensure_keys, mock_ssh_connect, vm_info, ssh_keys
    ):
        """Test that Ctrl+C (130) doesn't prompt for reconnect."""
        # Setup mocks
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_ssh_connect.return_value = 130  # User interrupt

        # Connect
        with patch("azlin.modules.ssh_reconnect.click.confirm") as mock_confirm:
            result = VMConnector.connect(
                vm_identifier="test-vm", resource_group="test-rg", enable_reconnect=True
            )

            # Should return False (interrupted)
            assert result is False

            # Should not prompt for reconnect
            mock_confirm.assert_not_called()

    @patch("azlin.vm_connector.TerminalLauncher.launch")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_reconnect_disabled_uses_terminal_launcher(
        self, mock_get_vm, mock_ensure_keys, mock_terminal_launch, vm_info, ssh_keys
    ):
        """Test that disabling reconnect uses terminal launcher."""
        # Setup mocks
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_terminal_launch.return_value = True

        # Connect with reconnect disabled
        result = VMConnector.connect(
            vm_identifier="test-vm", resource_group="test-rg", enable_reconnect=False
        )

        # Should succeed
        assert result is True

        # Should use terminal launcher, not SSH connector
        mock_terminal_launch.assert_called_once()

    @patch("azlin.vm_connector.TerminalLauncher.launch")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_remote_command_bypasses_reconnect(
        self, mock_get_vm, mock_ensure_keys, mock_terminal_launch, vm_info, ssh_keys
    ):
        """Test that remote commands bypass reconnect feature."""
        # Setup mocks
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_terminal_launch.return_value = True

        # Connect with remote command
        result = VMConnector.connect(
            vm_identifier="test-vm",
            resource_group="test-rg",
            remote_command="ls -la",
            enable_reconnect=True,  # Even with this enabled
        )

        # Should succeed
        assert result is True

        # Should use terminal launcher for remote command
        mock_terminal_launch.assert_called_once()

        # Verify command was passed
        call_args = mock_terminal_launch.call_args[0][0]
        assert call_args.command == "ls -la"

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.click.confirm")
    @patch("azlin.vm_connector.SSHKeyManager.ensure_key_exists")
    @patch("azlin.vm_connector.VMManager.get_vm")
    def test_reconnect_with_tmux_session(
        self, mock_get_vm, mock_ensure_keys, mock_confirm, mock_ssh_connect, vm_info, ssh_keys
    ):
        """Test reconnect maintains tmux session name."""
        # Setup mocks
        mock_get_vm.return_value = vm_info
        mock_ensure_keys.return_value = ssh_keys
        mock_confirm.return_value = True
        mock_ssh_connect.side_effect = [255, 0]  # Disconnect then succeed

        # Connect with custom tmux session
        result = VMConnector.connect(
            vm_identifier="test-vm",
            resource_group="test-rg",
            use_tmux=True,
            tmux_session="custom-session",
        )

        # Should succeed
        assert result is True

        # Verify tmux session was passed on both attempts
        for call_args in mock_ssh_connect.call_args_list:
            assert call_args.kwargs["tmux_session"] == "custom-session"
            assert call_args.kwargs["auto_tmux"] is True
