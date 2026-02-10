"""Tests for azlin restore command - TDD approach.

Testing pyramid:
- 60% Unit tests (fast, heavily mocked)
- 30% Integration tests (multiple components)
- 10% E2E tests (complete workflows)

Security requirements:
- Command injection prevention
- Path traversal prevention
- Input validation (VM names, hostnames, session names)
- Error message sanitization
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

# Import will fail until implementation exists
try:
    from azlin.commands.restore import (
        PlatformDetector,
        RestoreSessionConfig,
        TerminalLauncher,
        TerminalType,
        restore_command,
    )
except ImportError:
    pytest.skip("azlin.commands.restore not implemented yet", allow_module_level=True)


# ============================================================================
# UNIT TESTS (60%)
# ============================================================================


class TestRestoreSessionConfig:
    """Test RestoreSessionConfig dataclass."""

    def test_restore_session_config_creation(self):
        """Test creating a restore session config with required fields."""
        config = RestoreSessionConfig(
            vm_name="test-vm-1",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
        )

        assert config.vm_name == "test-vm-1"
        assert config.hostname == "192.168.1.100"
        assert config.username == "azureuser"
        assert config.ssh_key_path == Path("/home/user/.ssh/id_rsa")
        assert config.tmux_session == "azlin"  # Default value
        assert config.terminal_type == TerminalType.UNKNOWN  # Default value

    def test_restore_session_config_with_custom_session(self):
        """Test creating config with custom tmux session name."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="10.0.0.1",
            username="admin",
            ssh_key_path=Path("/tmp/key"),
            tmux_session="custom-session",
        )

        assert config.tmux_session == "custom-session"

    def test_restore_session_config_with_terminal_type(self):
        """Test creating config with specific terminal type."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="10.0.0.1",
            username="admin",
            ssh_key_path=Path("/tmp/key"),
            terminal_type=TerminalType.MACOS_TERMINAL,
        )

        assert config.terminal_type == TerminalType.MACOS_TERMINAL


class TestPlatformDetectorDetectPlatform:
    """Test platform detection logic."""

    def test_detect_platform_macos(self):
        """Test macOS platform detection."""
        with patch("platform.system", return_value="Darwin"):
            assert PlatformDetector.detect_platform() == "macos"

    def test_detect_platform_windows(self):
        """Test Windows platform detection."""
        with patch("platform.system", return_value="Windows"):
            assert PlatformDetector.detect_platform() == "windows"

    def test_detect_platform_linux_non_wsl(self):
        """Test Linux (non-WSL) platform detection."""
        with patch("platform.system", return_value="Linux"):
            with patch.object(PlatformDetector, "_is_wsl", return_value=False):
                assert PlatformDetector.detect_platform() == "linux"

    def test_detect_platform_wsl(self):
        """Test WSL platform detection."""
        with patch("platform.system", return_value="Linux"):
            with patch.object(PlatformDetector, "_is_wsl", return_value=True):
                assert PlatformDetector.detect_platform() == "wsl"

    def test_detect_platform_unknown(self):
        """Test unknown platform returns 'unknown'."""
        with patch("platform.system", return_value="FreeBSD"):
            assert PlatformDetector.detect_platform() == "unknown"


class TestPlatformDetectorIsWSL:
    """Test WSL detection logic."""

    def test_is_wsl_detects_microsoft_in_proc_version(self):
        """Test WSL detection via /proc/version containing 'microsoft'."""
        mock_data = "Linux version 4.4.0-19041-Microsoft (Microsoft@Microsoft.com)"
        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = mock_data
            assert PlatformDetector._is_wsl() is True

    def test_is_wsl_returns_false_for_regular_linux(self):
        """Test WSL detection returns False for regular Linux."""
        mock_data = "Linux version 5.10.0-8-amd64 (debian-kernel@lists.debian.org)"
        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = mock_data
            assert PlatformDetector._is_wsl() is False

    def test_is_wsl_handles_file_not_found(self):
        """Test WSL detection handles missing /proc/version gracefully."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            assert PlatformDetector._is_wsl() is False

    def test_is_wsl_handles_permission_error(self):
        """Test WSL detection handles permission errors gracefully."""
        with patch("builtins.open", side_effect=PermissionError):
            assert PlatformDetector._is_wsl() is False


class TestPlatformDetectorGetDefaultTerminal:
    """Test default terminal selection."""

    def test_get_default_terminal_macos(self):
        """Test default terminal for macOS is Terminal.app."""
        with patch.object(PlatformDetector, "detect_platform", return_value="macos"):
            assert PlatformDetector.get_default_terminal() == TerminalType.MACOS_TERMINAL

    def test_get_default_terminal_wsl(self):
        """Test default terminal for WSL is Windows Terminal."""
        with patch.object(PlatformDetector, "detect_platform", return_value="wsl"):
            assert PlatformDetector.get_default_terminal() == TerminalType.WINDOWS_TERMINAL

    def test_get_default_terminal_windows(self):
        """Test default terminal for Windows is wt.exe."""
        with patch.object(PlatformDetector, "detect_platform", return_value="windows"):
            assert PlatformDetector.get_default_terminal() == TerminalType.WINDOWS_TERMINAL

    def test_get_default_terminal_linux_gnome(self):
        """Test default terminal for Linux with gnome-terminal available."""
        with patch.object(PlatformDetector, "detect_platform", return_value="linux"):
            with patch.object(
                PlatformDetector, "_has_command", side_effect=lambda cmd: cmd == "gnome-terminal"
            ):
                assert PlatformDetector.get_default_terminal() == TerminalType.LINUX_GNOME

    def test_get_default_terminal_linux_xterm(self):
        """Test fallback to xterm when gnome-terminal not available."""
        with patch.object(PlatformDetector, "detect_platform", return_value="linux"):
            with patch.object(
                PlatformDetector, "_has_command", side_effect=lambda cmd: cmd == "xterm"
            ):
                assert PlatformDetector.get_default_terminal() == TerminalType.LINUX_XTERM

    def test_get_default_terminal_unknown_platform(self):
        """Test unknown platform returns UNKNOWN terminal type."""
        with patch.object(PlatformDetector, "detect_platform", return_value="unknown"):
            assert PlatformDetector.get_default_terminal() == TerminalType.UNKNOWN


class TestPlatformDetectorHasCommand:
    """Test command availability checking."""

    def test_has_command_returns_true_when_command_exists(self):
        """Test _has_command returns True when command is available."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            assert PlatformDetector._has_command("gnome-terminal") is True
            mock_run.assert_called_once()

    def test_has_command_returns_false_when_command_missing(self):
        """Test _has_command returns False when command not found."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert PlatformDetector._has_command("nonexistent-terminal") is False

    def test_has_command_returns_false_on_timeout(self):
        """Test _has_command returns False on timeout."""
        with patch("subprocess.run", side_effect=TimeoutError):
            assert PlatformDetector._has_command("slow-command") is False

    def test_has_command_returns_false_on_subprocess_error(self):
        """Test _has_command returns False when subprocess fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Subprocess error")
            assert PlatformDetector._has_command("error-command") is False


class TestSecurityInputValidation:
    """Security tests for input validation."""

    def test_vm_name_sanitization_prevents_command_injection(self):
        """Test VM name with shell metacharacters is rejected."""
        # Import SecurityValidationError from restore module
        from azlin.commands.restore import SecurityValidationError

        # VM names should not contain shell metacharacters
        dangerous_vm_names = [
            "vm; rm -rf /",
            "vm && malicious",
            "vm | cat /etc/passwd",
            "vm `whoami`",
            "vm$(whoami)",
        ]

        for vm_name in dangerous_vm_names:
            # Implementation validates and rejects dangerous input
            with pytest.raises(SecurityValidationError):
                config = RestoreSessionConfig(
                    vm_name=vm_name,
                    hostname="10.0.0.1",
                    username="admin",
                    ssh_key_path=Path("/tmp/key"),
                )

    def test_hostname_validation_prevents_command_injection(self):
        """Test hostname with dangerous characters is validated."""
        from azlin.commands.restore import SecurityValidationError

        dangerous_hostnames = [
            "host; rm -rf /",
            "host && malicious",
            "host | whoami",
        ]

        for hostname in dangerous_hostnames:
            # Implementation validates and rejects dangerous input
            with pytest.raises(SecurityValidationError):
                config = RestoreSessionConfig(
                    vm_name="test-vm",
                    hostname=hostname,
                    username="admin",
                    ssh_key_path=Path("/tmp/key"),
                )

    def test_ssh_key_path_prevents_path_traversal(self):
        """Test SSH key path prevents directory traversal attacks."""
        import os

        from azlin.commands.restore import SecurityValidationError

        # Temporarily disable BOTH test mode environment variables
        old_pytest = os.environ.get("PYTEST_CURRENT_TEST")
        old_azlin = os.environ.get("AZLIN_TEST_MODE")

        if old_pytest:
            del os.environ["PYTEST_CURRENT_TEST"]
        if old_azlin:
            del os.environ["AZLIN_TEST_MODE"]

        try:
            dangerous_paths = [
                Path("../../etc/passwd"),
                Path("/etc/shadow"),
                Path("~/../../../root/.ssh/id_rsa"),
            ]

            for path in dangerous_paths:
                # Implementation validates and rejects dangerous paths
                with pytest.raises(SecurityValidationError):
                    config = RestoreSessionConfig(
                        vm_name="test-vm",
                        hostname="10.0.0.1",
                        username="admin",
                        ssh_key_path=path,
                    )
        finally:
            # Restore test mode
            if old_pytest:
                os.environ["PYTEST_CURRENT_TEST"] = old_pytest
            if old_azlin:
                os.environ["AZLIN_TEST_MODE"] = old_azlin

    def test_tmux_session_name_sanitization(self):
        """Test tmux session names are sanitized."""
        from azlin.commands.restore import SecurityValidationError

        dangerous_sessions = [
            "session; malicious",
            "session && rm",
            "session | cat",
        ]

        for session in dangerous_sessions:
            # Implementation validates and rejects dangerous session names
            with pytest.raises(SecurityValidationError):
                config = RestoreSessionConfig(
                    vm_name="test-vm",
                    hostname="10.0.0.1",
                    username="admin",
                    ssh_key_path=Path("/tmp/key"),
                    tmux_session=session,
                )

    def test_error_message_sanitization(self):
        """Test error messages don't leak sensitive information."""
        import os

        from azlin.commands.restore import RestoreSessionConfig, SecurityValidationError

        # Temporarily disable test mode to verify actual validation
        old_pytest = os.environ.get("PYTEST_CURRENT_TEST")
        old_azlin = os.environ.get("AZLIN_TEST_MODE")

        if old_pytest:
            del os.environ["PYTEST_CURRENT_TEST"]
        if old_azlin:
            del os.environ["AZLIN_TEST_MODE"]

        try:
            # Test: Invalid SSH key path shouldn't leak full path
            with pytest.raises(SecurityValidationError) as exc:
                RestoreSessionConfig(
                    vm_name="test-vm",
                    hostname="10.0.0.1",
                    username="testuser",
                    ssh_key_path=Path("/secret/path/to/private/key.pem"),
                    tmux_session="test",
                )

            error_msg = str(exc.value)
            # Error should be helpful but not leak full path details
            assert "ssh key path" in error_msg.lower()
            # Should not expose the full secret path
            assert "/secret/path/to/private" not in error_msg
        finally:
            # Restore test mode
            if old_pytest:
                os.environ["PYTEST_CURRENT_TEST"] = old_pytest
            if old_azlin:
                os.environ["AZLIN_TEST_MODE"] = old_azlin


# ============================================================================
# INTEGRATION TESTS (30%)
# ============================================================================


class TestTerminalLauncherIntegration:
    """Integration tests for TerminalLauncher with mocked subprocess."""

    def test_launch_session_macos_terminal(self, tmp_path):
        """Test launching macOS Terminal.app."""
        # Create a temporary SSH key file for testing
        ssh_key = tmp_path / "id_rsa"
        ssh_key.write_text("fake key")

        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=ssh_key,
            terminal_type=TerminalType.MACOS_TERMINAL,
        )

        with patch.object(TerminalLauncher, "_launch_macos_terminal") as mock_launch:
            mock_launch.return_value = True
            result = TerminalLauncher.launch_session(config)
            assert result is True
            mock_launch.assert_called_once_with(config)

    def test_launch_session_windows_terminal(self):
        """Test launching Windows Terminal."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            terminal_type=TerminalType.WINDOWS_TERMINAL,
        )

        with patch.object(
            PlatformDetector, "get_windows_terminal_path", return_value=Path("/mnt/c/wt.exe")
        ):
            with patch("subprocess.Popen") as mock_popen:
                mock_popen.return_value = Mock()
                result = TerminalLauncher.launch_session(config)
                assert result is True
                mock_popen.assert_called_once()

    def test_launch_session_unsupported_terminal(self):
        """Test launching with unsupported terminal type."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            terminal_type=TerminalType.UNKNOWN,
        )

        result = TerminalLauncher.launch_session(config)
        assert result is False

    def test_launch_all_sessions_individual_windows(self):
        """Test launching multiple sessions in individual windows."""
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

    def test_launch_all_sessions_with_failures(self):
        """Test launching sessions with some failures."""
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

        # Mock first two succeed, third fails
        with patch.object(TerminalLauncher, "launch_session", side_effect=[True, True, False]):
            success_count, failed_count = TerminalLauncher.launch_all_sessions(sessions)
            assert success_count == 2
            assert failed_count == 1

    def test_launch_all_sessions_multi_tab_windows_terminal(self):
        """Test launching Windows Terminal with multi-tab mode."""
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
        ):
            success_count, failed_count = TerminalLauncher.launch_all_sessions(
                sessions, multi_tab=True
            )
            assert success_count == 3
            assert failed_count == 0


class TestWindowsTerminalPathResolution:
    """Test Windows Terminal path resolution in WSL."""

    def test_get_windows_terminal_path_in_wsl(self):
        """Test finding wt.exe in WSL."""
        with patch.object(PlatformDetector, "detect_platform", return_value="wsl"):
            with patch.object(PlatformDetector, "_get_windows_username", return_value="testuser"):
                with patch("pathlib.Path.exists", return_value=True):
                    path = PlatformDetector.get_windows_terminal_path()
                    assert path is not None
                    assert "wt.exe" in str(path)

    def test_get_windows_terminal_path_not_in_wsl(self):
        """Test returns None when not in WSL."""
        with patch.object(PlatformDetector, "detect_platform", return_value="linux"):
            path = PlatformDetector.get_windows_terminal_path()
            assert path is None

    def test_get_windows_terminal_path_with_glob_pattern(self):
        """Test finding wt.exe using glob patterns."""
        with patch.object(PlatformDetector, "detect_platform", return_value="wsl"):
            with patch.object(PlatformDetector, "_get_windows_username", return_value="testuser"):
                with patch("glob.glob", return_value=["/mnt/c/Program Files/WindowsApps/wt.exe"]):
                    path = PlatformDetector.get_windows_terminal_path()
                    assert path is not None
                    assert "wt.exe" in str(path)

    def test_get_windows_username_in_wsl(self):
        """Test extracting Windows username in WSL."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="TestUser\n")
            username = PlatformDetector._get_windows_username()
            assert username == "TestUser"

    def test_get_windows_username_failure(self):
        """Test handling username extraction failure."""
        with patch("subprocess.run", side_effect=Exception("Command failed")):
            username = PlatformDetector._get_windows_username()
            assert username is None


# ============================================================================
# E2E TESTS (10%)
# ============================================================================


def _create_mock_vm(name: str, public_ip: str, resource_group: str = "test-rg") -> Mock:
    """Helper to create properly configured VM mock."""
    mock_vm = Mock()
    mock_vm.name = name
    mock_vm.resource_group = resource_group
    mock_vm.power_state = "VM running"
    mock_vm.public_ip = public_ip
    return mock_vm


class TestRestoreCommandE2E:
    """End-to-end tests for restore command."""

    def test_restore_command_dry_run_no_vms(self):
        """Test restore command in dry-run mode with no VMs."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.list_vms", return_value=[]):
            result = runner.invoke(restore_command, ["--dry-run"])
            assert result.exit_code == 2
            assert "No running VMs found" in result.output

    def test_restore_command_dry_run_with_vms(self):
        """Test restore command in dry-run mode with VMs."""
        runner = CliRunner()

        mock_vms = [
            _create_mock_vm("test-vm-1", "192.168.1.100"),
            _create_mock_vm("test-vm-2", "192.168.1.101"),
        ]

        with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
            with patch("azlin.config_manager.ConfigManager.load_config"):
                with patch(
                    "azlin.config_manager.ConfigManager.get_session_name", return_value=None
                ):
                    result = runner.invoke(restore_command, ["--dry-run"])
                    assert result.exit_code == 0
                    assert "test-vm-1" in result.output
                    assert "test-vm-2" in result.output

    def test_restore_command_executes_successfully(self):
        """Test restore command successfully launches terminals."""
        runner = CliRunner()

        mock_vms = [_create_mock_vm("test-vm-1", "192.168.1.100")]

        with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
            with patch("azlin.config_manager.ConfigManager.load_config"):
                with patch(
                    "azlin.config_manager.ConfigManager.get_session_name", return_value=None
                ):
                    with patch.object(TerminalLauncher, "launch_all_sessions", return_value=(1, 0)):
                        result = runner.invoke(restore_command)
                        assert result.exit_code == 0
                        assert "Successfully restored" in result.output

    def test_restore_command_with_resource_group_filter(self):
        """Test restore command with resource group filter."""
        runner = CliRunner()

        mock_vms = [_create_mock_vm("test-vm-1", "192.168.1.100", "filtered-rg")]

        with patch("azlin.vm_manager.VMManager.list_vms") as mock_list:
            mock_list.return_value = mock_vms
            with patch("azlin.config_manager.ConfigManager.load_config"):
                with patch(
                    "azlin.config_manager.ConfigManager.get_session_name", return_value=None
                ):
                    with patch.object(TerminalLauncher, "launch_all_sessions", return_value=(1, 0)):
                        result = runner.invoke(restore_command, ["--resource-group", "filtered-rg"])
                        assert result.exit_code == 0
                        mock_list.assert_called_once_with("filtered-rg", include_stopped=False)

    def test_restore_command_partial_failure(self):
        """Test restore command with partial failures."""
        runner = CliRunner()

        mock_vms = [_create_mock_vm(f"vm-{i}", f"10.0.0.{i}") for i in range(3)]

        with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
            with patch("azlin.config_manager.ConfigManager.load_config"):
                with patch(
                    "azlin.config_manager.ConfigManager.get_session_name", return_value=None
                ):
                    with patch.object(TerminalLauncher, "launch_all_sessions", return_value=(2, 1)):
                        result = runner.invoke(restore_command)
                        assert result.exit_code == 1  # Partial failure
                        assert "Warning" in result.output
                        assert "failed to launch" in result.output

    def test_restore_command_with_custom_terminal(self):
        """Test restore command with custom terminal override."""
        runner = CliRunner()

        mock_vms = [_create_mock_vm("test-vm", "192.168.1.100")]

        with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
            with patch("azlin.config_manager.ConfigManager.load_config"):
                with patch(
                    "azlin.config_manager.ConfigManager.get_session_name", return_value=None
                ):
                    with patch.object(TerminalLauncher, "launch_all_sessions", return_value=(1, 0)):
                        result = runner.invoke(restore_command, ["--terminal", "windows_terminal"])
                        assert result.exit_code == 0

    def test_restore_command_config_error(self):
        """Test restore command handles config errors."""
        runner = CliRunner()

        with patch(
            "azlin.config_manager.ConfigManager.load_config", side_effect=Exception("Config error")
        ):
            result = runner.invoke(restore_command)
            assert result.exit_code == 2
            assert "error" in result.output.lower()


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


class TestRestoreCommandErrorHandling:
    """Test error handling for restore command."""

    def test_handles_no_vms_gracefully(self):
        """Test graceful handling when no VMs are running."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.list_vms", return_value=[]):
            result = runner.invoke(restore_command)
            assert result.exit_code == 2
            assert "No running VMs found" in result.output

    def test_handles_vm_manager_error(self):
        """Test handling of VM manager errors."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.list_vms", side_effect=Exception("Azure error")):
            result = runner.invoke(restore_command)
            assert result.exit_code == 2
            assert "error" in result.output.lower()

    def test_handles_terminal_launch_error(self):
        """Test handling of terminal launch errors."""
        runner = CliRunner()

        mock_vms = [_create_mock_vm("test-vm", "10.0.0.1")]

        with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
            with patch("azlin.config_manager.ConfigManager.load_config"):
                with patch(
                    "azlin.config_manager.ConfigManager.get_session_name", return_value=None
                ):
                    with patch.object(
                        TerminalLauncher,
                        "launch_all_sessions",
                        side_effect=Exception("Terminal error"),
                    ):
                        result = runner.invoke(restore_command)
                        assert result.exit_code == 2

    def test_provides_actionable_error_messages(self):
        """Test error messages provide actionable guidance."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.list_vms", return_value=[]):
            result = runner.invoke(restore_command)
            # Error message should suggest what to do next
            assert "azlin list" in result.output or "no VMs" in result.output.lower()


class TestSessionCrossingPrevention:
    """Tests for issue #593: Prevent session crossing due to env var not propagating.

    The bug: When running `azlin restore`, the AZLIN_DISABLE_BASTION_POOL env var
    doesn't propagate through `bash -l` to uvx subprocesses, causing the bastion
    pool to be enabled when it should be disabled, leading to tunnel reuse that
    can connect to the wrong VM.

    The fix: Pass `--disable-bastion-pool` flag via CLI instead of env var.
    """

    def test_multi_tab_command_includes_disable_bastion_pool_flag(self):
        """Test that multi-tab launch includes --disable-bastion-pool in connect command."""
        sessions = [
            RestoreSessionConfig(
                vm_name=f"vm-{i}",
                hostname=f"192.168.1.{100 + i}",
                username="azureuser",
                ssh_key_path=Path("/home/user/.ssh/id_rsa"),
                terminal_type=TerminalType.WINDOWS_TERMINAL,
                tmux_session=f"session-{i}",
            )
            for i in range(2)
        ]

        with patch.object(
            PlatformDetector, "get_windows_terminal_path", return_value=Path("/mnt/c/wt.exe")
        ):
            with patch("subprocess.Popen") as mock_popen:
                with patch("time.sleep"):  # Skip delays
                    mock_popen.return_value = Mock()
                    TerminalLauncher._launch_windows_terminal_multi_tab(sessions)

                    # Verify Popen was called with --disable-bastion-pool in the command
                    assert mock_popen.call_count >= 1
                    for call in mock_popen.call_args_list:
                        args = call[0][0]  # First positional arg is the command list
                        # Find the bash -c command argument
                        for arg in args:
                            if isinstance(arg, str) and "azlin connect" in arg:
                                assert "--disable-bastion-pool" in arg, (
                                    f"Command missing --disable-bastion-pool: {arg}"
                                )

    def test_single_window_command_includes_disable_bastion_pool_flag(self):
        """Test that single window launch includes --disable-bastion-pool in connect command."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            terminal_type=TerminalType.WINDOWS_TERMINAL,
            tmux_session="my-session",
        )

        with patch.object(
            PlatformDetector, "get_windows_terminal_path", return_value=Path("/mnt/c/wt.exe")
        ):
            with patch("subprocess.Popen") as mock_popen:
                mock_popen.return_value = Mock()
                TerminalLauncher._launch_windows_terminal(config)

                # Verify Popen was called
                assert mock_popen.call_count == 1
                args = mock_popen.call_args[0][0]

                # Find the bash -c command argument
                for arg in args:
                    if isinstance(arg, str) and "azlin connect" in arg:
                        assert "--disable-bastion-pool" in arg, (
                            f"Command missing --disable-bastion-pool: {arg}"
                        )
                        break
                else:
                    pytest.fail("No azlin connect command found in Popen args")

    def test_macos_terminal_command_includes_disable_bastion_pool_flag(self):
        """Test that macOS terminal launch includes --disable-bastion-pool in connect command."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            terminal_type=TerminalType.MACOS_TERMINAL,
            tmux_session="my-session",
        )

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = Mock()
            TerminalLauncher._launch_macos_terminal(config)

            # Verify Popen was called
            assert mock_popen.call_count == 1
            args = mock_popen.call_args[0][0]

            # For osascript, the command is embedded in the script
            script_content = args[2]  # osascript -e "script"
            assert "--disable-bastion-pool" in script_content, (
                f"Command missing --disable-bastion-pool: {script_content}"
            )

    def test_gnome_terminal_command_includes_disable_bastion_pool_flag(self):
        """Test that GNOME terminal launch includes --disable-bastion-pool in connect command."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            terminal_type=TerminalType.LINUX_GNOME,
            tmux_session="my-session",
        )

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = Mock()
            TerminalLauncher._launch_gnome_terminal(config)

            # Verify Popen was called
            assert mock_popen.call_count == 1
            args = mock_popen.call_args[0][0]

            # Find the bash -c command argument
            for arg in args:
                if isinstance(arg, str) and "azlin connect" in arg:
                    assert "--disable-bastion-pool" in arg, (
                        f"Command missing --disable-bastion-pool: {arg}"
                    )
                    break
            else:
                pytest.fail("No azlin connect command found in Popen args")

    def test_xterm_command_includes_disable_bastion_pool_flag(self):
        """Test that xterm launch includes --disable-bastion-pool in connect command."""
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.100",
            username="azureuser",
            ssh_key_path=Path("/home/user/.ssh/id_rsa"),
            terminal_type=TerminalType.LINUX_XTERM,
            tmux_session="my-session",
        )

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = Mock()
            TerminalLauncher._launch_xterm(config)

            # Verify Popen was called
            assert mock_popen.call_count == 1
            args = mock_popen.call_args[0][0]

            # Find the bash -c command argument
            for arg in args:
                if isinstance(arg, str) and "azlin connect" in arg:
                    assert "--disable-bastion-pool" in arg, (
                        f"Command missing --disable-bastion-pool: {arg}"
                    )
                    break
            else:
                pytest.fail("No azlin connect command found in Popen args")
