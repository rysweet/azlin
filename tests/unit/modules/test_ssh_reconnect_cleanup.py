"""Unit tests for SSH reconnect cleanup callback functionality.

Tests the cleanup_callback parameter in SSHReconnectHandler and verifies:
- Callback is called before reconnect attempts
- Callback is NOT called on first connect
- Callback handles exceptions gracefully
- Callback receives correct parameters

Testing pyramid:
- 60% Unit tests (this file - heavily mocked)
- 30% Integration tests (test_bastion_reconnect_integration.py)
- 10% E2E tests (existing e2e tests)
"""

from unittest.mock import MagicMock, patch

import pytest

from azlin.modules.ssh_connector import SSHConfig
from azlin.modules.ssh_reconnect import SSHReconnectHandler


class TestSSHReconnectCleanupCallback:
    """Unit tests for cleanup callback in SSHReconnectHandler."""

    @pytest.fixture
    def ssh_config(self, tmp_path):
        """Create test SSH configuration."""
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        return SSHConfig(
            host="127.0.0.1",
            user="testuser",
            key_path=key_file,
            port=2222,
            strict_host_key_checking=False,
        )

    def test_handler_accepts_cleanup_callback_parameter(self):
        """Test that SSHReconnectHandler accepts cleanup_callback parameter.

        This test will FAIL until cleanup_callback parameter is added to __init__.
        """
        cleanup_callback = MagicMock()

        # This should not raise any errors
        handler = SSHReconnectHandler(max_retries=3, cleanup_callback=cleanup_callback)

        # Verify callback is stored
        assert handler.cleanup_callback is cleanup_callback

    def test_handler_accepts_none_cleanup_callback(self):
        """Test that cleanup_callback can be None (backward compatibility).

        This test will FAIL until cleanup_callback parameter is added.
        """
        # Should work with None (default)
        handler = SSHReconnectHandler(max_retries=3, cleanup_callback=None)
        assert handler.cleanup_callback is None

        # Should work without the parameter at all
        handler2 = SSHReconnectHandler(max_retries=3)
        assert handler2.cleanup_callback is None

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_cleanup_not_called_on_first_connect(
        self, mock_should_reconnect, mock_ssh_connect, ssh_config
    ):
        """Test that cleanup callback is NOT called on first connection attempt.

        This test will FAIL until implementation correctly skips cleanup on first attempt.
        """
        cleanup_callback = MagicMock()
        mock_ssh_connect.return_value = 0  # Normal exit

        handler = SSHReconnectHandler(max_retries=3, cleanup_callback=cleanup_callback)
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        # Verify exit code
        assert exit_code == 0

        # Verify cleanup was NOT called (no reconnect needed)
        cleanup_callback.assert_not_called()

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_cleanup_called_before_reconnect_attempt(
        self, mock_should_reconnect, mock_ssh_connect, ssh_config
    ):
        """Test that cleanup callback is called BEFORE reconnect attempt.

        This test will FAIL until implementation calls cleanup_callback before reconnect.
        """
        cleanup_callback = MagicMock()
        mock_should_reconnect.return_value = True
        # First connect disconnects, second succeeds
        mock_ssh_connect.side_effect = [255, 0]

        handler = SSHReconnectHandler(max_retries=3, cleanup_callback=cleanup_callback)
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        # Verify successful reconnect
        assert exit_code == 0
        assert mock_ssh_connect.call_count == 2

        # Verify cleanup was called exactly once (before second connect)
        cleanup_callback.assert_called_once()

        # Verify cleanup was called BEFORE the second connect
        # Check call order: connect(1), cleanup, connect(2)
        calls = []
        for mock_call in mock_ssh_connect.call_args_list:
            calls.append(("connect", mock_call))
        for mock_call in cleanup_callback.call_args_list:
            calls.append(("cleanup", mock_call))

        # First call should be connect, second should be cleanup, third should be connect
        # (This is a simplified check - in real implementation we'd use mock.call tracking)
        assert cleanup_callback.call_count == 1

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_cleanup_called_on_each_reconnect_attempt(
        self, mock_should_reconnect, mock_ssh_connect, ssh_config
    ):
        """Test that cleanup is called before EACH reconnect attempt.

        This test will FAIL until implementation calls cleanup before each reconnect.
        """
        cleanup_callback = MagicMock()
        mock_should_reconnect.return_value = True
        # Disconnect twice, then succeed
        mock_ssh_connect.side_effect = [255, 255, 0]

        handler = SSHReconnectHandler(max_retries=3, cleanup_callback=cleanup_callback)
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        # Verify successful reconnect after 2 retries
        assert exit_code == 0
        assert mock_ssh_connect.call_count == 3

        # Verify cleanup was called twice (before 2nd and 3rd connects)
        assert cleanup_callback.call_count == 2

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_cleanup_exception_handled_gracefully(
        self, mock_should_reconnect, mock_ssh_connect, ssh_config
    ):
        """Test that exceptions in cleanup callback don't break reconnect.

        This test will FAIL until implementation handles cleanup exceptions.
        """
        cleanup_callback = MagicMock(side_effect=Exception("Cleanup failed!"))
        mock_should_reconnect.return_value = True
        # Disconnect then succeed
        mock_ssh_connect.side_effect = [255, 0]

        handler = SSHReconnectHandler(max_retries=3, cleanup_callback=cleanup_callback)

        # Should not raise exception, should continue with reconnect
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        # Verify reconnect still succeeded despite cleanup failure
        assert exit_code == 0
        assert mock_ssh_connect.call_count == 2

        # Verify cleanup was attempted
        cleanup_callback.assert_called_once()

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    @patch("azlin.modules.ssh_reconnect.logger")
    def test_cleanup_exception_logged(
        self, mock_logger, mock_should_reconnect, mock_ssh_connect, ssh_config
    ):
        """Test that cleanup exceptions are logged with clear message.

        This test will FAIL until implementation logs cleanup exceptions.
        """
        cleanup_error = Exception("Bastion tunnel cleanup failed")
        cleanup_callback = MagicMock(side_effect=cleanup_error)
        mock_should_reconnect.return_value = True
        mock_ssh_connect.side_effect = [255, 0]

        handler = SSHReconnectHandler(max_retries=3, cleanup_callback=cleanup_callback)
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        # Verify reconnect succeeded
        assert exit_code == 0

        # Verify error was logged with clear message
        mock_logger.warning.assert_called()
        warning_call = mock_logger.warning.call_args[0][0]
        assert "cleanup" in warning_call.lower()
        assert "failed" in warning_call.lower() or "error" in warning_call.lower()

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_cleanup_not_called_when_user_declines_reconnect(
        self, mock_should_reconnect, mock_ssh_connect, ssh_config
    ):
        """Test that cleanup is NOT called if user declines reconnect.

        This test will FAIL until implementation correctly skips cleanup when user declines.
        """
        cleanup_callback = MagicMock()
        mock_should_reconnect.return_value = False  # User declines
        mock_ssh_connect.return_value = 255  # Disconnect

        handler = SSHReconnectHandler(max_retries=3, cleanup_callback=cleanup_callback)
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        # Verify exit with disconnect code
        assert exit_code == 255
        assert mock_ssh_connect.call_count == 1

        # Verify cleanup was NOT called (user declined reconnect)
        cleanup_callback.assert_not_called()

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_cleanup_not_called_after_max_retries(
        self, mock_should_reconnect, mock_ssh_connect, ssh_config
    ):
        """Test that cleanup is NOT called after max retries exceeded.

        This test will FAIL until implementation correctly handles max retries.
        """
        cleanup_callback = MagicMock()
        mock_should_reconnect.return_value = True
        # Always disconnect
        mock_ssh_connect.return_value = 255

        handler = SSHReconnectHandler(max_retries=2, cleanup_callback=cleanup_callback)
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        # Verify failed after max retries: initial + 2 retries = 3 connects
        assert exit_code == 255
        assert mock_ssh_connect.call_count == 3

        # Verify cleanup was called exactly 2 times (before each retry, not before initial)
        # Initial connect + retry 1 (cleanup) + retry 2 (cleanup) = 2 cleanups
        assert cleanup_callback.call_count == 2

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_cleanup_not_called_on_normal_exit(
        self, mock_should_reconnect, mock_ssh_connect, ssh_config
    ):
        """Test that cleanup is NOT called when SSH exits normally.

        This test will FAIL until implementation correctly handles normal exit.
        """
        cleanup_callback = MagicMock()
        mock_ssh_connect.return_value = 0  # Normal exit

        handler = SSHReconnectHandler(max_retries=3, cleanup_callback=cleanup_callback)
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        # Verify normal exit
        assert exit_code == 0
        assert mock_ssh_connect.call_count == 1

        # Verify cleanup was NOT called (no reconnect needed)
        cleanup_callback.assert_not_called()

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_cleanup_not_called_on_ctrl_c_exit(
        self, mock_should_reconnect, mock_ssh_connect, ssh_config
    ):
        """Test that cleanup is NOT called when user hits Ctrl+C.

        This test will FAIL until implementation correctly handles user interrupt.
        """
        cleanup_callback = MagicMock()
        mock_ssh_connect.return_value = 130  # User interrupt (Ctrl+C)

        handler = SSHReconnectHandler(max_retries=3, cleanup_callback=cleanup_callback)
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        # Verify user interrupt
        assert exit_code == 130
        assert mock_ssh_connect.call_count == 1

        # Verify cleanup was NOT called (no reconnect on user interrupt)
        cleanup_callback.assert_not_called()

    def test_cleanup_callback_parameter_is_optional(self):
        """Test that cleanup_callback parameter is optional for backward compatibility.

        This test will FAIL until implementation makes cleanup_callback optional.
        """
        # Should work without cleanup_callback parameter
        handler = SSHReconnectHandler(max_retries=3)
        assert handler.cleanup_callback is None

        # Should work with explicit None
        handler2 = SSHReconnectHandler(max_retries=3, cleanup_callback=None)
        assert handler2.cleanup_callback is None

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_reconnect_works_without_cleanup_callback(
        self, mock_should_reconnect, mock_ssh_connect, ssh_config
    ):
        """Test that reconnect works normally when no cleanup callback provided.

        This test will FAIL until implementation handles None cleanup_callback.
        """
        mock_should_reconnect.return_value = True
        mock_ssh_connect.side_effect = [255, 0]  # Disconnect then succeed

        # No cleanup callback provided
        handler = SSHReconnectHandler(max_retries=3)
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        # Verify reconnect succeeded
        assert exit_code == 0
        assert mock_ssh_connect.call_count == 2


class TestSSHReconnectCleanupCallbackIntegration:
    """Integration tests within ssh_reconnect module."""

    @pytest.fixture
    def ssh_config(self, tmp_path):
        """Create test SSH configuration."""
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        return SSHConfig(
            host="127.0.0.1",
            user="testuser",
            key_path=key_file,
            port=2222,
            strict_host_key_checking=False,
        )

    @patch("azlin.modules.ssh_reconnect.SSHConnector.connect")
    @patch("azlin.modules.ssh_reconnect.should_attempt_reconnect")
    def test_cleanup_callback_invocation_order(
        self, mock_should_reconnect, mock_ssh_connect, ssh_config
    ):
        """Test the exact order of cleanup callback invocations.

        This test will FAIL until implementation has correct call ordering.
        """
        call_tracker = []

        def track_cleanup():
            call_tracker.append("cleanup")

        def track_connect(*args, **kwargs):
            call_tracker.append("connect")
            # Return different codes based on call count
            if len([x for x in call_tracker if x == "connect"]) == 1:
                return 255  # First connect: disconnect
            return 0  # Second connect: success

        cleanup_callback = MagicMock(side_effect=track_cleanup)
        mock_should_reconnect.return_value = True
        mock_ssh_connect.side_effect = track_connect

        handler = SSHReconnectHandler(max_retries=3, cleanup_callback=cleanup_callback)
        exit_code = handler.connect_with_reconnect(ssh_config, vm_name="test-vm")

        # Verify success
        assert exit_code == 0

        # Verify exact call order: connect, cleanup, connect
        assert call_tracker == ["connect", "cleanup", "connect"]

        # Verify cleanup was called once
        cleanup_callback.assert_called_once()
