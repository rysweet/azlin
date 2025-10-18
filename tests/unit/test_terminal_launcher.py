"""Unit tests for terminal_launcher module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.terminal_launcher import (
    TerminalConfig,
    TerminalLauncher,
    TerminalLauncherError,
)


class TestTerminalConfig:
    """Test TerminalConfig dataclass."""

    def test_terminal_config_creation_minimal(self):
        """Test creating TerminalConfig with minimal required fields."""
        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/azlin_key"),
        )

        assert config.ssh_host == "20.1.2.3"
        assert config.ssh_user == "azureuser"
        assert config.ssh_key_path == Path("/home/user/.ssh/azlin_key")
        assert config.command is None
        assert config.title is None
        assert config.tmux_session is None

    def test_terminal_config_creation_full(self):
        """Test creating TerminalConfig with all fields."""
        config = TerminalConfig(
            ssh_host="my-vm.westus2.cloudapp.azure.com",
            ssh_user="testuser",
            ssh_key_path=Path("/path/to/key"),
            command="ls -la",
            title="My Terminal",
            tmux_session="dev-session",
        )

        assert config.ssh_host == "my-vm.westus2.cloudapp.azure.com"
        assert config.ssh_user == "testuser"
        assert config.ssh_key_path == Path("/path/to/key")
        assert config.command == "ls -la"
        assert config.title == "My Terminal"
        assert config.tmux_session == "dev-session"


class TestBuildSSHCommand:
    """Test SSH command building."""

    def test_build_ssh_command_basic(self):
        """Test building basic SSH command without extras."""
        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/azlin_key"),
        )

        cmd = TerminalLauncher._build_ssh_command(config)

        assert "ssh" in cmd
        assert "-o StrictHostKeyChecking=no" in cmd
        assert "-o UserKnownHostsFile=/dev/null" in cmd
        assert "-i /home/user/.ssh/azlin_key" in cmd
        assert "azureuser@20.1.2.3" in cmd

    def test_build_ssh_command_with_command(self):
        """Test building SSH command with remote command."""
        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
            command="ls -la",
        )

        cmd = TerminalLauncher._build_ssh_command(config)

        assert "ssh" in cmd
        assert "azureuser@20.1.2.3" in cmd
        assert "'ls -la'" in cmd

    def test_build_ssh_command_with_tmux_session(self):
        """Test building SSH command with tmux session."""
        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
            tmux_session="dev-session",
        )

        cmd = TerminalLauncher._build_ssh_command(config)

        assert "ssh" in cmd
        assert "azureuser@20.1.2.3" in cmd
        assert "tmux new-session -A -s" in cmd
        assert "dev-session" in cmd

    def test_build_ssh_command_with_both_command_and_tmux(self):
        """Test building SSH command with both command and tmux."""
        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
            command="bash",
            tmux_session="dev",
        )

        cmd = TerminalLauncher._build_ssh_command(config)

        assert "ssh" in cmd
        assert "azureuser@20.1.2.3" in cmd
        assert "tmux new-session -A -s" in cmd
        assert "dev" in cmd
        assert "bash" in cmd


class TestHasCommand:
    """Test command availability checking."""

    @patch("azlin.terminal_launcher.subprocess.run")
    def test_has_command_exists(self, mock_run):
        """Test detecting existing command."""
        mock_run.return_value = MagicMock(returncode=0)

        result = TerminalLauncher._has_command("gnome-terminal")

        assert result is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["which", "gnome-terminal"]

    @patch("azlin.terminal_launcher.subprocess.run")
    def test_has_command_missing(self, mock_run):
        """Test detecting missing command."""
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, "which")

        result = TerminalLauncher._has_command("nonexistent-terminal")

        assert result is False

    @patch("azlin.terminal_launcher.subprocess.run")
    def test_has_command_timeout(self, mock_run):
        """Test command check timeout handling."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="which", timeout=5)

        result = TerminalLauncher._has_command("slow-command")

        assert result is False


class TestLaunchMacOS:
    """Test macOS terminal launching."""

    @patch("azlin.terminal_launcher.subprocess.run")
    def test_launch_macos_success(self, mock_run):
        """Test successful macOS terminal launch."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
        )

        result = TerminalLauncher._launch_macos(config)

        assert result is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "osascript"
        assert args[1] == "-e"
        assert "Terminal" in args[2]
        assert "do script" in args[2]

    @patch("azlin.terminal_launcher.subprocess.run")
    def test_launch_macos_applescript_failure(self, mock_run):
        """Test macOS terminal launch AppleScript failure."""
        mock_run.return_value = MagicMock(
            returncode=1, stderr="execution error: Terminal got an error"
        )

        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
        )

        result = TerminalLauncher._launch_macos(config)

        assert result is False

    @patch("azlin.terminal_launcher.subprocess.run")
    def test_launch_macos_with_custom_title(self, mock_run):
        """Test macOS launch with custom title."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
            title="My Custom Terminal",
        )

        result = TerminalLauncher._launch_macos(config)

        assert result is True
        args = mock_run.call_args[0][0]
        assert "My Custom Terminal" in args[2]

    @patch("azlin.terminal_launcher.subprocess.run")
    def test_launch_macos_command_escaping(self, mock_run):
        """Test macOS launch properly escapes special characters."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
            command='echo "test"',
        )

        result = TerminalLauncher._launch_macos(config)

        assert result is True
        # Verify escaping happened
        applescript = mock_run.call_args[0][0][2]
        assert '\\"' in applescript  # Quotes should be escaped


class TestLaunchLinux:
    """Test Linux terminal launching."""

    @patch("azlin.terminal_launcher.subprocess.Popen")
    @patch("azlin.terminal_launcher.TerminalLauncher._has_command")
    def test_launch_linux_gnome_terminal(self, mock_has_cmd, mock_popen):
        """Test launching with gnome-terminal."""
        mock_has_cmd.side_effect = lambda cmd: cmd == "gnome-terminal"
        mock_popen.return_value = MagicMock()

        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
        )

        result = TerminalLauncher._launch_linux(config)

        assert result is True
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args[0] == "gnome-terminal"
        assert "--title" in args
        assert "bash" in args
        assert "-c" in args

    @patch("azlin.terminal_launcher.subprocess.Popen")
    @patch("azlin.terminal_launcher.TerminalLauncher._has_command")
    def test_launch_linux_xterm_fallback(self, mock_has_cmd, mock_popen):
        """Test falling back to xterm when gnome-terminal unavailable."""
        mock_has_cmd.side_effect = lambda cmd: cmd == "xterm"
        mock_popen.return_value = MagicMock()

        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
        )

        result = TerminalLauncher._launch_linux(config)

        assert result is True
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args[0] == "xterm"
        assert "-title" in args
        assert "-e" in args

    @patch("azlin.terminal_launcher.TerminalLauncher._has_command")
    def test_launch_linux_no_terminal_found(self, mock_has_cmd):
        """Test error when no terminal emulator available."""
        mock_has_cmd.return_value = False

        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
        )

        result = TerminalLauncher._launch_linux(config)

        assert result is False

    @patch("azlin.terminal_launcher.subprocess.Popen")
    @patch("azlin.terminal_launcher.TerminalLauncher._has_command")
    def test_launch_linux_gnome_terminal_fails(self, mock_has_cmd, mock_popen):
        """Test fallback when gnome-terminal launch fails."""
        mock_has_cmd.side_effect = lambda cmd: cmd in ["gnome-terminal", "xterm"]
        # First call (gnome-terminal) fails, second call (xterm) succeeds
        mock_popen.side_effect = [Exception("Launch failed"), MagicMock()]

        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
        )

        result = TerminalLauncher._launch_linux(config)

        assert result is True
        # Should have tried both terminals
        assert mock_popen.call_count == 2

    @patch("azlin.terminal_launcher.subprocess.Popen")
    @patch("azlin.terminal_launcher.TerminalLauncher._has_command")
    def test_launch_linux_both_terminals_fail(self, mock_has_cmd, mock_popen):
        """Test when both gnome-terminal and xterm fail."""
        mock_has_cmd.side_effect = lambda cmd: cmd in ["gnome-terminal", "xterm"]
        # Both terminals fail to launch
        mock_popen.side_effect = [
            Exception("gnome-terminal failed"),
            Exception("xterm failed"),
        ]

        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
        )

        result = TerminalLauncher._launch_linux(config)

        assert result is False
        # Should have tried both terminals
        assert mock_popen.call_count == 2


class TestFallbackInlineSSH:
    """Test fallback inline SSH connection."""

    @patch("azlin.terminal_launcher.subprocess.run")
    def test_fallback_inline_ssh_success(self, mock_run):
        """Test successful inline SSH connection."""
        mock_run.return_value = MagicMock(returncode=0)

        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
        )

        result = TerminalLauncher._fallback_inline_ssh(config)

        assert result is True
        mock_run.assert_called_once()
        # Verify subprocess.run was called with list (not shell=True)
        args = mock_run.call_args[0][0]
        assert isinstance(args, list)
        assert args[0] == "ssh"

    @patch("azlin.terminal_launcher.subprocess.run")
    def test_fallback_inline_ssh_failure(self, mock_run):
        """Test failed inline SSH connection."""
        mock_run.return_value = MagicMock(returncode=255)

        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
        )

        result = TerminalLauncher._fallback_inline_ssh(config)

        assert result is False

    @patch("azlin.terminal_launcher.subprocess.run")
    def test_fallback_inline_ssh_exception(self, mock_run):
        """Test exception during inline SSH connection."""
        mock_run.side_effect = Exception("Connection failed")

        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
        )

        result = TerminalLauncher._fallback_inline_ssh(config)

        assert result is False


class TestLaunch:
    """Test main launch method."""

    @patch("azlin.terminal_launcher.sys.platform", "darwin")
    @patch("azlin.terminal_launcher.TerminalLauncher._launch_macos")
    def test_launch_macos_success(self, mock_launch_macos):
        """Test launch on macOS platform."""
        mock_launch_macos.return_value = True

        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
        )

        result = TerminalLauncher.launch(config)

        assert result is True
        mock_launch_macos.assert_called_once_with(config)

    @patch("azlin.terminal_launcher.sys.platform", "linux")
    @patch("azlin.terminal_launcher.TerminalLauncher._launch_linux")
    def test_launch_linux_success(self, mock_launch_linux):
        """Test launch on Linux platform."""
        mock_launch_linux.return_value = True

        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
        )

        result = TerminalLauncher.launch(config)

        assert result is True
        mock_launch_linux.assert_called_once_with(config)

    @patch("azlin.terminal_launcher.sys.platform", "win32")
    @patch("azlin.terminal_launcher.TerminalLauncher._fallback_inline_ssh")
    def test_launch_unsupported_platform(self, mock_fallback):
        """Test launch on unsupported platform falls back to inline."""
        mock_fallback.return_value = True

        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
        )

        result = TerminalLauncher.launch(config)

        assert result is True
        mock_fallback.assert_called_once_with(config)

    @patch("azlin.terminal_launcher.sys.platform", "darwin")
    @patch("azlin.terminal_launcher.TerminalLauncher._fallback_inline_ssh")
    @patch("azlin.terminal_launcher.TerminalLauncher._launch_macos")
    def test_launch_fallback_on_failure(self, mock_launch_macos, mock_fallback):
        """Test fallback to inline SSH when platform launch fails."""
        mock_launch_macos.side_effect = Exception("Launch failed")
        mock_fallback.return_value = True

        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
        )

        result = TerminalLauncher.launch(config, fallback_inline=True)

        assert result is True
        mock_fallback.assert_called_once_with(config)

    @patch("azlin.terminal_launcher.sys.platform", "darwin")
    @patch("azlin.terminal_launcher.TerminalLauncher._launch_macos")
    def test_launch_no_fallback_raises_error(self, mock_launch_macos):
        """Test launch raises error when fallback disabled."""
        mock_launch_macos.side_effect = Exception("Launch failed")

        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
        )

        with pytest.raises(TerminalLauncherError, match="Terminal launch failed"):
            TerminalLauncher.launch(config, fallback_inline=False)

    @patch("azlin.terminal_launcher.sys.platform", "win32")
    @patch("azlin.terminal_launcher.TerminalLauncher._fallback_inline_ssh")
    def test_launch_unsupported_platform_no_fallback(self, mock_fallback):
        """Test unsupported platform returns False when fallback disabled."""
        config = TerminalConfig(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
        )

        result = TerminalLauncher.launch(config, fallback_inline=False)

        assert result is False
        mock_fallback.assert_not_called()


class TestLaunchCommandInTerminal:
    """Test convenience method for launching terminal with command."""

    @patch("azlin.terminal_launcher.TerminalLauncher.launch")
    def test_launch_command_in_terminal(self, mock_launch):
        """Test launching terminal with command."""
        mock_launch.return_value = True

        result = TerminalLauncher.launch_command_in_terminal(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
            command="ls -la",
            title="Test Terminal",
        )

        assert result is True
        mock_launch.assert_called_once()

        # Verify config was created correctly
        config = mock_launch.call_args[0][0]
        assert config.ssh_host == "20.1.2.3"
        assert config.ssh_user == "azureuser"
        assert config.ssh_key_path == Path("/home/user/.ssh/key")
        assert config.command == "ls -la"
        assert config.title == "Test Terminal"

    @patch("azlin.terminal_launcher.TerminalLauncher.launch")
    def test_launch_command_in_terminal_default_title(self, mock_launch):
        """Test launching terminal with default title."""
        mock_launch.return_value = True

        result = TerminalLauncher.launch_command_in_terminal(
            ssh_host="20.1.2.3",
            ssh_user="azureuser",
            ssh_key_path=Path("/home/user/.ssh/key"),
            command="htop",
        )

        assert result is True
        config = mock_launch.call_args[0][0]
        assert config.title == "azlin - htop"
