"""TMux reconnection tests for terminal launcher.

Tests for Issue #184: TMux Reconnection Fix
Verifies that tmux attempts to attach to existing sessions before creating new ones.

These tests follow TDD principles - they test the EXPECTED behavior:
- TMux should try 'attach-session' FIRST
- Fall back to 'new-session' if attach fails
- Use || operator for fallback logic
- Validation still applies to session names
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from azlin.terminal_launcher import (
    SecurityValidationError,
    TerminalConfig,
    TerminalLauncher,
)


@pytest.fixture
def temp_ssh_key():
    """Create temporary SSH key file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pem") as f:
        f.write("fake ssh key content")
        key_path = Path(f.name)

    yield key_path

    # Cleanup
    key_path.unlink(missing_ok=True)


class TestTmuxReconnection:
    """Test TMux reconnection behavior with attach-session fallback."""

    def test_tmux_command_uses_attach_session_first(self, temp_ssh_key):
        """Test that tmux command attempts attach-session before new-session.

        Expected behavior: When tmux_session is specified, the remote command should:
        1. First try: tmux attach-session -t {session}
        2. Fallback to: tmux new-session -s {session}
        3. Use || operator to chain them

        This test WILL FAIL until the fix is implemented.
        """
        config = TerminalConfig(
            ssh_host="example.com",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
            tmux_session="mysession",
        )

        cmd = TerminalLauncher._build_ssh_command(config)

        # The last argument should be the remote command
        remote_cmd = cmd[-1]

        # Verify it contains both attach-session and new-session
        assert "attach-session" in remote_cmd, (
            "TMux command should include 'attach-session' to reconnect to existing sessions"
        )
        assert "new-session" in remote_cmd, "TMux command should include 'new-session' as fallback"

        # Verify attach comes before new (proper ordering)
        attach_pos = remote_cmd.index("attach-session")
        new_pos = remote_cmd.index("new-session")
        assert attach_pos < new_pos, (
            "attach-session must come BEFORE new-session for reconnection to work"
        )

    def test_tmux_command_uses_or_operator_for_fallback(self, temp_ssh_key):
        """Test that tmux command uses || operator for fallback logic.

        Expected behavior:
        tmux attach-session -t mysession || tmux new-session -s mysession

        The || ensures new-session only runs if attach-session fails.
        This test WILL FAIL until the fix is implemented.
        """
        config = TerminalConfig(
            ssh_host="example.com",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
            tmux_session="mysession",
        )

        cmd = TerminalLauncher._build_ssh_command(config)
        remote_cmd = cmd[-1]

        # Verify || operator is used for fallback
        assert "||" in remote_cmd, (
            "TMux command should use || operator to fallback from attach to new-session"
        )

        # Verify the pattern: attach ... || new ...
        # More flexible check: just verify both commands are present with ||
        assert "attach-session" in remote_cmd
        assert "||" in remote_cmd
        assert "new-session" in remote_cmd

    def test_tmux_attach_uses_correct_flag_and_session_name(self, temp_ssh_key):
        """Test that attach-session uses -t flag with correct session name.

        Expected: tmux attach-session -t {session_name}
        This test WILL FAIL until the fix is implemented.
        """
        session_name = "my-test-session"
        config = TerminalConfig(
            ssh_host="example.com",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
            tmux_session=session_name,
        )

        cmd = TerminalLauncher._build_ssh_command(config)
        remote_cmd = cmd[-1]

        # Verify attach-session uses -t flag (target session)
        assert "attach-session -t" in remote_cmd, (
            "attach-session should use -t flag to specify target session"
        )

        # Verify session name is in the command
        assert session_name in remote_cmd, (
            f"Session name '{session_name}' should appear in tmux command"
        )

    def test_tmux_with_command_still_reconnects(self, temp_ssh_key):
        """Test that tmux reconnection works even when a command is specified.

        Expected behavior:
        tmux attach-session -t mysession || tmux new-session -s mysession {command}

        This test WILL FAIL until the fix is implemented.
        """
        config = TerminalConfig(
            ssh_host="example.com",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
            command="bash",
            tmux_session="mysession",
        )

        cmd = TerminalLauncher._build_ssh_command(config)
        remote_cmd = cmd[-1]

        # Should still use attach || new pattern
        assert "attach-session" in remote_cmd
        assert "||" in remote_cmd
        assert "new-session" in remote_cmd

        # The user command should be included with new-session
        assert "bash" in remote_cmd

    def test_tmux_validation_still_applies(self, temp_ssh_key):
        """Test that session name validation is still enforced.

        Security validation should prevent command injection via session names,
        regardless of the attach/new pattern.

        This test should PASS (validation exists) - it ensures we don't break security.
        """
        malicious_session = "session; rm -rf /"

        with pytest.raises(SecurityValidationError) as exc_info:
            TerminalConfig(
                ssh_host="example.com",
                ssh_user="testuser",
                ssh_key_path=temp_ssh_key,
                tmux_session=malicious_session,
            )

        assert "disallowed characters" in str(exc_info.value).lower()


class TestTmuxCommandStructure:
    """Test the structure and format of tmux commands."""

    def test_no_tmux_when_session_not_specified(self, temp_ssh_key):
        """Test that no tmux command is added when tmux_session is None.

        This test should PASS - it verifies current behavior is preserved.
        """
        config = TerminalConfig(
            ssh_host="example.com",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
            command="ls -la",
        )

        cmd = TerminalLauncher._build_ssh_command(config)

        # Should not contain tmux
        assert not any("tmux" in arg for arg in cmd)

    def test_tmux_command_is_single_string_argument(self, temp_ssh_key):
        """Test that the tmux command is passed as a single string to SSH.

        SSH expects the remote command as a single argument, not split up.
        This test should PASS - verifies the command structure.
        """
        config = TerminalConfig(
            ssh_host="example.com",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
            tmux_session="mysession",
        )

        cmd = TerminalLauncher._build_ssh_command(config)

        # Should be a list
        assert isinstance(cmd, list)

        # SSH base command, then remote command as last element
        assert cmd[0] == "ssh"

        # The tmux command should be in the last element as a single string
        remote_cmd = cmd[-1]
        assert isinstance(remote_cmd, str)
        assert "tmux" in remote_cmd


class TestTmuxMacOSIntegration:
    """Test tmux reconnection through macOS terminal launcher."""

    @patch("subprocess.run")
    def test_macos_launch_includes_tmux_reconnection(self, mock_run, temp_ssh_key):
        """Test that macOS terminal launch includes the tmux reconnection pattern.

        This verifies the fix works through the full macOS launch path.
        This test WILL FAIL until the fix is implemented.
        """
        from unittest.mock import MagicMock

        mock_run.return_value = MagicMock(returncode=0, stderr="")

        config = TerminalConfig(
            ssh_host="example.com",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
            tmux_session="mysession",
        )

        TerminalLauncher._launch_macos(config)

        # Verify subprocess.run was called
        assert mock_run.called

        # Get the AppleScript that was executed
        call_args = mock_run.call_args[0][0]
        applescript = call_args[2]  # Third argument is the script

        # Verify the AppleScript contains the tmux reconnection pattern
        assert "attach-session" in applescript
        assert "||" in applescript
        assert "new-session" in applescript


class TestTmuxLinuxIntegration:
    """Test tmux reconnection through Linux terminal launcher."""

    @patch("subprocess.Popen")
    def test_linux_launch_includes_tmux_reconnection(self, mock_popen, temp_ssh_key):
        """Test that Linux terminal launch includes the tmux reconnection pattern.

        This verifies the fix works through the full Linux launch path.
        This test WILL FAIL until the fix is implemented.
        """
        with patch.object(TerminalLauncher, "_has_command", return_value=True):
            config = TerminalConfig(
                ssh_host="example.com",
                ssh_user="testuser",
                ssh_key_path=temp_ssh_key,
                tmux_session="mysession",
            )

            TerminalLauncher._launch_linux(config)

            # Verify Popen was called
            assert mock_popen.called

            # Get the command that was passed
            call_args = mock_popen.call_args[0][0]

            # The SSH command should be in the args after '--'
            # Find the tmux command in the arguments
            cmd_str = " ".join(call_args)

            assert "attach-session" in cmd_str
            assert "||" in cmd_str
            assert "new-session" in cmd_str
