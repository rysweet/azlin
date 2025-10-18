"""Unit tests for SSH reconnection functionality."""

from unittest.mock import patch

import pytest

from azlin.modules.ssh_connector import SSHConfig
from azlin.modules.ssh_reconnect import (
    SSHReconnectHandler,
    is_disconnect_exit_code,
    should_attempt_reconnect,
)


class TestDisconnectDetection:
    """Test SSH disconnect detection."""

    def test_is_disconnect_exit_code_for_common_disconnect_codes(self):
        """Test that common disconnect exit codes are detected."""
        # Common SSH disconnect codes
        assert is_disconnect_exit_code(255) is True  # SSH generic error
        assert is_disconnect_exit_code(1) is True  # General errors that might be disconnect

    def test_is_disconnect_exit_code_for_normal_exit(self):
        """Test that normal exit is not treated as disconnect."""
        assert is_disconnect_exit_code(0) is False  # Normal exit

    def test_is_disconnect_exit_code_for_user_interrupt(self):
        """Test that user interrupt is not treated as disconnect."""
        assert is_disconnect_exit_code(130) is False  # Ctrl+C


class TestReconnectPrompt:
    """Test reconnect prompting logic."""

    @patch("click.confirm")
    def test_should_attempt_reconnect_user_accepts(self, mock_confirm):
        """Test reconnect prompt when user accepts."""
        mock_confirm.return_value = True

        result = should_attempt_reconnect("test-vm")

        assert result is True
        mock_confirm.assert_called_once()
        # Check that the prompt mentions the VM name
        call_args = mock_confirm.call_args
        assert "test-vm" in call_args[0][0]

    @patch("click.confirm")
    def test_should_attempt_reconnect_user_declines(self, mock_confirm):
        """Test reconnect prompt when user declines."""
        mock_confirm.return_value = False

        result = should_attempt_reconnect("test-vm")

        assert result is False
        mock_confirm.assert_called_once()


class TestSSHReconnectHandler:
    """Test SSH reconnection handler."""

    @pytest.fixture
    def ssh_config(self, tmp_path):
        """Create test SSH config."""
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        return SSHConfig(host="192.168.1.100", user="testuser", key_path=key_file, port=22)

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_connect_with_reconnect_success_on_first_try(
        self, mock_prompt, mock_connect, ssh_config
    ):
        """Test successful connection on first attempt."""
        mock_connect.return_value = 0

        handler = SSHReconnectHandler(max_retries=3)
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        assert exit_code == 0
        mock_connect.assert_called_once()
        mock_prompt.assert_not_called()

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_connect_with_reconnect_disconnect_then_success(
        self, mock_prompt, mock_connect, ssh_config
    ):
        """Test reconnection after disconnect."""
        # First attempt disconnects, second succeeds
        mock_connect.side_effect = [255, 0]
        mock_prompt.return_value = True

        handler = SSHReconnectHandler(max_retries=3)
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        assert exit_code == 0
        assert mock_connect.call_count == 2
        mock_prompt.assert_called_once_with("test-vm")

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_connect_with_reconnect_user_declines(self, mock_prompt, mock_connect, ssh_config):
        """Test that disconnection without user consent exits."""
        mock_connect.return_value = 255
        mock_prompt.return_value = False

        handler = SSHReconnectHandler(max_retries=3)
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        assert exit_code == 255
        mock_connect.assert_called_once()
        mock_prompt.assert_called_once_with("test-vm")

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_connect_with_reconnect_max_retries_exceeded(
        self, mock_prompt, mock_connect, ssh_config
    ):
        """Test that reconnection stops after max retries."""
        # All attempts fail with disconnect
        mock_connect.return_value = 255
        mock_prompt.return_value = True

        handler = SSHReconnectHandler(max_retries=3)
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        assert exit_code == 255
        # Should try: initial + 3 retries = 4 total attempts
        assert mock_connect.call_count == 4
        # Should prompt 3 times (not after last failure)
        assert mock_prompt.call_count == 3

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_connect_with_reconnect_ignores_normal_exit(
        self, mock_prompt, mock_connect, ssh_config
    ):
        """Test that normal exit (0) doesn't trigger reconnect."""
        mock_connect.return_value = 0

        handler = SSHReconnectHandler(max_retries=3)
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        assert exit_code == 0
        mock_connect.assert_called_once()
        mock_prompt.assert_not_called()

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_connect_with_reconnect_ignores_user_interrupt(
        self, mock_prompt, mock_connect, ssh_config
    ):
        """Test that user interrupt (Ctrl+C) doesn't trigger reconnect."""
        mock_connect.return_value = 130

        handler = SSHReconnectHandler(max_retries=3)
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        assert exit_code == 130
        mock_connect.assert_called_once()
        mock_prompt.assert_not_called()

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_connect_with_reconnect_multiple_disconnects_and_reconnects(
        self, mock_prompt, mock_connect, ssh_config
    ):
        """Test multiple disconnect/reconnect cycles."""
        # Disconnect, reconnect, disconnect again, then succeed
        mock_connect.side_effect = [255, 255, 0]
        mock_prompt.return_value = True

        handler = SSHReconnectHandler(max_retries=3)
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        assert exit_code == 0
        assert mock_connect.call_count == 3
        assert mock_prompt.call_count == 2

    def test_reconnect_handler_default_retry_count(self):
        """Test that default retry count is 3."""
        handler = SSHReconnectHandler()
        assert handler.max_retries == 3

    def test_reconnect_handler_custom_retry_count(self):
        """Test setting custom retry count."""
        handler = SSHReconnectHandler(max_retries=5)
        assert handler.max_retries == 5

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_connect_with_reconnect_other_exit_code(self, mock_prompt, mock_connect, ssh_config):
        """Test that other non-zero exit codes don't trigger reconnect."""
        # Exit code that's not 0, 1, 130, or 255 (e.g., 2)
        mock_connect.return_value = 2

        handler = SSHReconnectHandler(max_retries=3)
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        assert exit_code == 2
        mock_connect.assert_called_once()
        mock_prompt.assert_not_called()

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_connect_with_reconnect_all_params(self, mock_prompt, mock_connect, ssh_config):
        """Test that all parameters are passed correctly to SSHConnector."""
        mock_connect.return_value = 0

        handler = SSHReconnectHandler(max_retries=3)
        exit_code = handler.connect_with_reconnect(
            config=ssh_config, vm_name="test-vm", tmux_session="custom-session", auto_tmux=False
        )

        assert exit_code == 0
        mock_connect.assert_called_once_with(
            config=ssh_config, tmux_session="custom-session", auto_tmux=False
        )
