"""Unit tests for TerminalLauncher restore functionality - TDD approach.

These tests define the contract for terminal launching before implementation.

Security focus:
- SSH command construction
- Input sanitization
- Path validation
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Import will fail until implementation exists
try:
    from azlin.commands.restore import (
        RestoreSessionConfig,
        TerminalLauncher,
        TerminalType,
    )
except ImportError:
    pytest.skip("azlin.commands.restore not implemented yet", allow_module_level=True)


# ============================================================================
# TERMINAL LAUNCHER UNIT TESTS
# ============================================================================


class TestLaunchSession:
    """Test launching individual terminal sessions."""

    def test_launch_session_macos_terminal(self):
        """Test launching macOS Terminal.app session."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            terminal_type=TerminalType.MACOS_TERMINAL,
        )

        with patch("azlin.terminal_launcher.TerminalLauncher.launch") as mock_launch:
            mock_launch.return_value = True
            result = TerminalLauncher.launch_session(config)
            assert result is True
            mock_launch.assert_called_once()

    def test_launch_session_windows_terminal(self):
        """Test launching Windows Terminal session."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            terminal_type=TerminalType.WINDOWS_TERMINAL,
        )

        with patch(
            "azlin.commands.restore.PlatformDetector.get_windows_terminal_path"
        ) as mock_path:
            mock_path.return_value = Path("/mnt/c/wt.exe")
            with patch("subprocess.Popen") as mock_popen:
                mock_popen.return_value = Mock()
                result = TerminalLauncher.launch_session(config)
                assert result is True
                mock_popen.assert_called_once()

    def test_launch_session_gnome_terminal(self):
        """Test launching gnome-terminal session."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            terminal_type=TerminalType.LINUX_GNOME,
        )

        with patch("azlin.terminal_launcher.TerminalLauncher.launch") as mock_launch:
            mock_launch.return_value = True
            result = TerminalLauncher.launch_session(config)
            assert result is True

    def test_launch_session_xterm(self):
        """Test launching xterm session."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            terminal_type=TerminalType.LINUX_XTERM,
        )

        with patch("azlin.terminal_launcher.TerminalLauncher.launch") as mock_launch:
            mock_launch.return_value = True
            result = TerminalLauncher.launch_session(config)
            assert result is True

    def test_launch_session_unsupported_terminal_returns_false(self):
        """Test unsupported terminal type returns False."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            terminal_type=TerminalType.UNKNOWN,
        )

        result = TerminalLauncher.launch_session(config)
        assert result is False

    def test_launch_session_unknown_terminal_prints_error(self):
        """Test error message printed for unknown terminal type."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            terminal_type=TerminalType.UNKNOWN,
        )

        with patch("builtins.print") as mock_print:
            TerminalLauncher.launch_session(config)
            mock_print.assert_called()
            # Should mention unsupported terminal
            call_args = str(mock_print.call_args)
            assert "unsupported" in call_args.lower() or "unknown" in call_args.lower()


# ============================================================================
# LAUNCH ALL SESSIONS TESTS
# ============================================================================


class TestLaunchAllSessions:
    """Test launching multiple sessions."""

    def test_launch_all_sessions_empty_list(self):
        """Test launching with empty session list."""
        sessions = []
        success_count, failed_count = TerminalLauncher.launch_all_sessions(sessions)
        assert success_count == 0
        assert failed_count == 0

    def test_launch_all_sessions_all_succeed(self):
        """Test all sessions launch successfully."""
        sessions = [
            RestoreSessionConfig(
                vm_name=f"vm-{i}",
                hostname=f"192.168.1.{100 + i}",
                username="azureuser",
                ssh_key_path=Path("/home/user/.ssh/id_rsa"),
                terminal_type=TerminalType.MACOS_TERMINAL,
            )
            for i in range(3)
        ]

        with patch.object(TerminalLauncher, "launch_session", return_value=True):
            success_count, failed_count = TerminalLauncher.launch_all_sessions(sessions)
            assert success_count == 3
            assert failed_count == 0

    def test_launch_all_sessions_all_fail(self):
        """Test all sessions fail to launch."""
        sessions = [
            RestoreSessionConfig(
                vm_name=f"vm-{i}",
                hostname=f"192.168.1.{100 + i}",
                username="azureuser",
                ssh_key_path=Path("/home/user/.ssh/id_rsa"),
                terminal_type=TerminalType.MACOS_TERMINAL,
            )
            for i in range(3)
        ]

        with patch.object(TerminalLauncher, "launch_session", return_value=False):
            success_count, failed_count = TerminalLauncher.launch_all_sessions(sessions)
            assert success_count == 0
            assert failed_count == 3

    def test_launch_all_sessions_mixed_results(self):
        """Test mixed success and failure results."""
        sessions = [
            RestoreSessionConfig(
                vm_name=f"vm-{i}",
                hostname=f"192.168.1.{100 + i}",
                username="azureuser",
                ssh_key_path=Path("/home/user/.ssh/id_rsa"),
                terminal_type=TerminalType.MACOS_TERMINAL,
            )
            for i in range(5)
        ]

        # First 3 succeed, last 2 fail
        with patch.object(
            TerminalLauncher, "launch_session", side_effect=[True, True, True, False, False]
        ):
            success_count, failed_count = TerminalLauncher.launch_all_sessions(sessions)
            assert success_count == 3
            assert failed_count == 2

    def test_launch_all_sessions_multi_tab_mode(self):
        """Test multi-tab mode for Windows Terminal."""
        sessions = [
            RestoreSessionConfig(
                vm_name=f"vm-{i}",
                hostname=f"192.168.1.{100 + i}",
                username="azureuser",
                ssh_key_path=Path("/home/user/.ssh/id_rsa"),
                terminal_type=TerminalType.WINDOWS_TERMINAL,
            )
            for i in range(3)
        ]

        with patch.object(
            TerminalLauncher, "_launch_windows_terminal_multi_tab", return_value=(3, 0)
        ) as mock_multi:
            success_count, failed_count = TerminalLauncher.launch_all_sessions(
                sessions, multi_tab=True
            )
            assert success_count == 3
            assert failed_count == 0
            mock_multi.assert_called_once_with(sessions)

    def test_launch_all_sessions_multi_tab_not_windows_terminal(self):
        """Test multi-tab mode ignored for non-Windows Terminal."""
        sessions = [
            RestoreSessionConfig(
                vm_name=f"vm-{i}",
                hostname=f"192.168.1.{100 + i}",
                username="azureuser",
                ssh_key_path=Path("/home/user/.ssh/id_rsa"),
                terminal_type=TerminalType.MACOS_TERMINAL,
            )
            for i in range(3)
        ]

        with patch.object(TerminalLauncher, "launch_session", return_value=True) as mock_launch:
            TerminalLauncher.launch_all_sessions(sessions, multi_tab=True)
            # Should fall back to individual windows
            assert mock_launch.call_count == 3


# ============================================================================
# MACOS TERMINAL LAUNCHER TESTS
# ============================================================================


class TestLaunchMacOSTerminal:
    """Test macOS Terminal.app launching."""

    def test_launch_macos_terminal_creates_terminal_config(self):
        """Test creates TerminalConfig with correct parameters."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            tmux_session="custom-session",
        )

        with patch("azlin.terminal_launcher.TerminalLauncher.launch") as mock_launch:
            mock_launch.return_value = True
            result = TerminalLauncher._launch_macos_terminal(config)
            assert result is True
            mock_launch.assert_called_once()

            # Verify TerminalConfig parameters
            call_args = mock_launch.call_args
            terminal_config = call_args[0][0]
            assert terminal_config.ssh_host == "192.168.1.100"
            assert terminal_config.ssh_user == "azureuser"
            assert terminal_config.tmux_session == "custom-session"
            assert "test-vm" in terminal_config.title

    def test_launch_macos_terminal_uses_fallback_inline_false(self):
        """Test uses fallback_inline=False."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
        )

        with patch("azlin.terminal_launcher.TerminalLauncher.launch") as mock_launch:
            mock_launch.return_value = True
            TerminalLauncher._launch_macos_terminal(config)

            call_kwargs = mock_launch.call_args[1]
            assert call_kwargs.get("fallback_inline") is False

    def test_launch_macos_terminal_handles_failure(self):
        """Test handles terminal launch failure."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
        )

        with patch("azlin.terminal_launcher.TerminalLauncher.launch") as mock_launch:
            mock_launch.return_value = False
            result = TerminalLauncher._launch_macos_terminal(config)
            assert result is False


# ============================================================================
# WINDOWS TERMINAL LAUNCHER TESTS
# ============================================================================


class TestLaunchWindowsTerminal:
    """Test Windows Terminal launching."""

    def test_launch_windows_terminal_single_window(self):
        """Test launching single Windows Terminal window."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            tmux_session="test-session",
        )

        with patch(
            "azlin.commands.restore.PlatformDetector.get_windows_terminal_path"
        ) as mock_path:
            mock_path.return_value = Path("/mnt/c/wt.exe")
            with patch("subprocess.Popen") as mock_popen:
                mock_popen.return_value = Mock()
                result = TerminalLauncher._launch_windows_terminal(config)
                assert result is True
                mock_popen.assert_called_once()

    def test_launch_windows_terminal_constructs_ssh_command(self):
        """Test SSH command construction for Windows Terminal."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            tmux_session="test-session",
        )

        with patch(
            "azlin.commands.restore.PlatformDetector.get_windows_terminal_path"
        ) as mock_path:
            mock_path.return_value = Path("/mnt/c/wt.exe")
            with patch("subprocess.Popen") as mock_popen:
                mock_popen.return_value = Mock()
                TerminalLauncher._launch_windows_terminal(config)

                call_args = mock_popen.call_args[0][0]
                ssh_cmd_part = " ".join(call_args)

                # Verify SSH command components
                assert "ssh" in ssh_cmd_part
                assert "192.168.1.100" in ssh_cmd_part
                assert "azureuser" in ssh_cmd_part
                assert "/home/user/.ssh/id_rsa" in ssh_cmd_part
                assert "test-session" in ssh_cmd_part

    def test_launch_windows_terminal_not_found(self):
        """Test handles Windows Terminal not found."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
        )

        with patch(
            "azlin.commands.restore.PlatformDetector.get_windows_terminal_path"
        ) as mock_path:
            mock_path.return_value = None
            result = TerminalLauncher._launch_windows_terminal(config)
            assert result is False

    def test_launch_windows_terminal_subprocess_error(self):
        """Test handles subprocess error."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
        )

        with patch(
            "azlin.commands.restore.PlatformDetector.get_windows_terminal_path"
        ) as mock_path:
            mock_path.return_value = Path("/mnt/c/wt.exe")
            with patch("subprocess.Popen", side_effect=Exception("Launch failed")):
                result = TerminalLauncher._launch_windows_terminal(config)
                assert result is False


# ============================================================================
# WINDOWS TERMINAL MULTI-TAB TESTS
# ============================================================================


class TestLaunchWindowsTerminalMultiTab:
    """Test Windows Terminal multi-tab launching."""

    def test_launch_windows_terminal_multi_tab_all_succeed(self):
        """Test launching multiple tabs successfully."""
        sessions = [
            RestoreSessionConfig(
                vm_name=f"vm-{i}",
                hostname=f"192.168.1.{100 + i}",
                username="azureuser",
                ssh_key_path=Path("/home/user/.ssh/id_rsa"),
                tmux_session=f"session-{i}",
            )
            for i in range(3)
        ]

        with patch(
            "azlin.commands.restore.PlatformDetector.get_windows_terminal_path"
        ) as mock_path:
            mock_path.return_value = Path("/mnt/c/wt.exe")
            with patch("subprocess.Popen") as mock_popen:
                mock_popen.return_value = Mock()
                success_count, failed_count = TerminalLauncher._launch_windows_terminal_multi_tab(
                    sessions
                )
                assert success_count == 3
                assert failed_count == 0
                mock_popen.assert_called_once()

    def test_launch_windows_terminal_multi_tab_command_structure(self):
        """Test multi-tab command structure."""
        sessions = [
            RestoreSessionConfig(
                vm_name=f"vm-{i}",
                hostname=f"192.168.1.{100 + i}",
                username="azureuser",
                ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            )
            for i in range(3)
        ]

        with patch(
            "azlin.commands.restore.PlatformDetector.get_windows_terminal_path"
        ) as mock_path:
            mock_path.return_value = Path("/mnt/c/wt.exe")
            with patch("subprocess.Popen") as mock_popen:
                mock_popen.return_value = Mock()
                TerminalLauncher._launch_windows_terminal_multi_tab(sessions)

                call_args = mock_popen.call_args[0][0]
                # Verify wt command structure
                assert str(call_args[0]) == "/mnt/c/wt.exe"
                assert "-w" in call_args
                assert "0" in call_args
                assert "new-tab" in call_args

    def test_launch_windows_terminal_multi_tab_not_found(self):
        """Test handles Windows Terminal not found."""
        sessions = [
            RestoreSessionConfig(
                vm_name="vm-1",
                hostname="192.168.1.100",
                username="azureuser",
                ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            )
        ]

        with patch(
            "azlin.commands.restore.PlatformDetector.get_windows_terminal_path"
        ) as mock_path:
            mock_path.return_value = None
            success_count, failed_count = TerminalLauncher._launch_windows_terminal_multi_tab(
                sessions
            )
            assert success_count == 0
            assert failed_count == len(sessions)

    def test_launch_windows_terminal_multi_tab_subprocess_error(self):
        """Test handles subprocess error."""
        sessions = [
            RestoreSessionConfig(
                vm_name="vm-1",
                hostname="192.168.1.100",
                username="azureuser",
                ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            )
        ]

        with patch(
            "azlin.commands.restore.PlatformDetector.get_windows_terminal_path"
        ) as mock_path:
            mock_path.return_value = Path("/mnt/c/wt.exe")
            with patch("subprocess.Popen", side_effect=Exception("Launch failed")):
                success_count, failed_count = TerminalLauncher._launch_windows_terminal_multi_tab(
                    sessions
                )
                assert success_count == 0
                assert failed_count == len(sessions)


# ============================================================================
# SECURITY TESTS
# ============================================================================


class TestTerminalLauncherSecurity:
    """Security tests for terminal launching."""

    def test_ssh_command_prevents_command_injection_in_hostname(self):
        """Test SSH command construction prevents command injection via hostname."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="host; rm -rf /",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
        )

        with patch(
            "azlin.commands.restore.PlatformDetector.get_windows_terminal_path"
        ) as mock_path:
            mock_path.return_value = Path("/mnt/c/wt.exe")
            with patch("subprocess.Popen") as mock_popen:
                mock_popen.return_value = Mock()
                # Should either reject or safely handle dangerous hostname
                result = TerminalLauncher._launch_windows_terminal(config)
                # Implementation must prevent injection
                if result and mock_popen.called:
                    call_args = mock_popen.call_args[0][0]
                    ssh_cmd = " ".join(call_args)
                    # Verify semicolon is quoted or command rejected
                    assert "rm" not in ssh_cmd or result is False

    def test_ssh_command_prevents_command_injection_in_username(self):
        """Test SSH command construction prevents command injection via username."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="user && malicious",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
        )

        with patch(
            "azlin.commands.restore.PlatformDetector.get_windows_terminal_path"
        ) as mock_path:
            mock_path.return_value = Path("/mnt/c/wt.exe")
            with patch("subprocess.Popen") as mock_popen:
                mock_popen.return_value = Mock()
                result = TerminalLauncher._launch_windows_terminal(config)
                # Implementation must prevent injection
                if result and mock_popen.called:
                    call_args = mock_popen.call_args[0][0]
                    ssh_cmd = " ".join(call_args)
                    assert "malicious" not in ssh_cmd or result is False

    def test_ssh_key_path_prevents_path_traversal(self):
        """Test SSH key path prevents directory traversal."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("../../etc/passwd"),
        )

        with patch(
            "azlin.commands.restore.PlatformDetector.get_windows_terminal_path"
        ) as mock_path:
            mock_path.return_value = Path("/mnt/c/wt.exe")
            with patch("subprocess.Popen") as mock_popen:
                mock_popen.return_value = Mock()
                result = TerminalLauncher._launch_windows_terminal(config)
                # Implementation must validate paths
                if result and mock_popen.called:
                    call_args = mock_popen.call_args[0][0]
                    ssh_cmd = " ".join(call_args)
                    # Should not contain unresolved path traversal
                    assert "/etc/passwd" not in ssh_cmd or result is False

    def test_tmux_session_name_sanitization(self):
        """Test tmux session name is sanitized."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            tmux_session="session; malicious",
        )

        with patch(
            "azlin.commands.restore.PlatformDetector.get_windows_terminal_path"
        ) as mock_path:
            mock_path.return_value = Path("/mnt/c/wt.exe")
            with patch("subprocess.Popen") as mock_popen:
                mock_popen.return_value = Mock()
                result = TerminalLauncher._launch_windows_terminal(config)
                # Implementation must sanitize session names
                if result and mock_popen.called:
                    call_args = mock_popen.call_args[0][0]
                    ssh_cmd = " ".join(call_args)
                    assert "malicious" not in ssh_cmd or result is False

    def test_vm_name_in_title_sanitized(self):
        """Test VM name used in window title is sanitized."""
        config = RestoreSessionConfig(
            vm_name="vm; malicious",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
        )

        with patch(
            "azlin.commands.restore.PlatformDetector.get_windows_terminal_path"
        ) as mock_path:
            mock_path.return_value = Path("/mnt/c/wt.exe")
            with patch("subprocess.Popen") as mock_popen:
                mock_popen.return_value = Mock()
                result = TerminalLauncher._launch_windows_terminal(config)
                # Implementation must sanitize VM names in titles
                if result and mock_popen.called:
                    call_args = mock_popen.call_args[0][0]
                    cmd_str = " ".join(call_args)
                    # Verify semicolon is handled safely
                    assert "malicious" not in cmd_str or result is False
