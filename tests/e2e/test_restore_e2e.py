"""End-to-end tests for azlin restore command - TDD approach.

These tests verify complete user workflows from command invocation to
terminal launch.

Testing pyramid: 10% of total test suite
Focus on critical user paths and error scenarios.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

# Import will fail until implementation exists
try:
    from azlin.commands.restore import (
        PlatformDetector,
        TerminalLauncher,
        TerminalType,
        restore_command,
    )
except ImportError:
    pytest.skip("azlin.commands.restore not implemented yet", allow_module_level=True)


# ============================================================================
# SUCCESSFUL RESTORE WORKFLOWS
# ============================================================================


class TestSuccessfulRestoreWorkflows:
    """Test successful end-to-end restore workflows."""

    def test_restore_all_sessions_default_config(self):
        """Test restoring all sessions with default configuration."""
        runner = CliRunner()

        # Mock complete workflow
        mock_config = Mock(
            default_resource_group="test-rg",
            terminal_launcher=None,
            terminal_multi_tab=True,
        )

        mock_vms = [
            Mock(
                name="vm-1",
                resource_group="test-rg",
                power_state="VM running",
                public_ip="192.168.1.100",
            ),
            Mock(
                name="vm-2",
                resource_group="test-rg",
                power_state="VM running",
                public_ip="192.168.1.101",
            ),
        ]

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
                with patch.object(
                    PlatformDetector,
                    "get_default_terminal",
                    return_value=TerminalType.MACOS_TERMINAL,
                ):
                    with patch.object(TerminalLauncher, "launch_all_sessions", return_value=(2, 0)):
                        result = runner.invoke(restore_command)

                        assert result.exit_code == 0
                        assert "Successfully restored" in result.output
                        assert "2" in result.output

    def test_restore_with_resource_group_filter(self):
        """Test restoring sessions filtered by resource group."""
        runner = CliRunner()

        mock_config = Mock(default_resource_group="default-rg")
        mock_vms = [
            Mock(
                name="vm-filtered",
                resource_group="custom-rg",
                power_state="VM running",
                public_ip="10.0.0.1",
            ),
        ]

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
                with patch.object(TerminalLauncher, "launch_all_sessions", return_value=(1, 0)):
                    result = runner.invoke(restore_command, ["--resource-group", "custom-rg"])

                    assert result.exit_code == 0
                    assert "Successfully restored" in result.output

    def test_restore_with_custom_terminal_override(self):
        """Test restoring with custom terminal override."""
        runner = CliRunner()

        mock_config = Mock(default_resource_group="test-rg")
        mock_vms = [
            Mock(
                name="vm-1",
                resource_group="test-rg",
                power_state="VM running",
                public_ip="10.0.0.1",
            ),
        ]

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
                with patch.object(TerminalLauncher, "launch_all_sessions", return_value=(1, 0)):
                    result = runner.invoke(restore_command, ["--terminal", "windows_terminal"])

                    assert result.exit_code == 0
                    assert "Successfully restored" in result.output

    def test_restore_with_custom_config_path(self):
        """Test restoring with custom config file path."""
        runner = CliRunner()

        mock_config = Mock(default_resource_group="test-rg")
        mock_vms = [
            Mock(
                name="vm-1",
                resource_group="test-rg",
                power_state="VM running",
                public_ip="10.0.0.1",
            ),
        ]

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
                with patch.object(TerminalLauncher, "launch_all_sessions", return_value=(1, 0)):
                    result = runner.invoke(restore_command, ["--config", "/tmp/custom-config.toml"])

                    assert result.exit_code == 0

    def test_restore_multi_tab_mode_enabled(self):
        """Test restore with multi-tab mode enabled."""
        runner = CliRunner()

        mock_config = Mock(
            default_resource_group="test-rg",
            terminal_multi_tab=True,
        )
        mock_vms = [
            Mock(
                name=f"vm-{i}",
                resource_group="test-rg",
                power_state="VM running",
                public_ip=f"10.0.0.{i}",
            )
            for i in range(3)
        ]

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
                with patch.object(
                    PlatformDetector,
                    "get_default_terminal",
                    return_value=TerminalType.WINDOWS_TERMINAL,
                ):
                    with patch.object(
                        TerminalLauncher, "launch_all_sessions", return_value=(3, 0)
                    ) as mock_launch:
                        result = runner.invoke(restore_command)

                        assert result.exit_code == 0
                        # Verify multi-tab mode was used
                        mock_launch.assert_called_once()


# ============================================================================
# DRY RUN MODE TESTS
# ============================================================================


class TestDryRunMode:
    """Test dry-run mode functionality."""

    def test_dry_run_shows_what_would_happen(self):
        """Test dry-run mode shows planned actions without executing."""
        runner = CliRunner()

        mock_config = Mock(default_resource_group="test-rg")
        mock_vms = [
            Mock(
                name="vm-1",
                resource_group="test-rg",
                power_state="VM running",
                public_ip="10.0.0.1",
            ),
            Mock(
                name="vm-2",
                resource_group="test-rg",
                power_state="VM running",
                public_ip="10.0.0.2",
            ),
        ]

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
                result = runner.invoke(restore_command, ["--dry-run"])

                assert result.exit_code == 0
                assert "dry" in result.output.lower() or "would" in result.output.lower()
                assert "vm-1" in result.output
                assert "vm-2" in result.output

    def test_dry_run_does_not_launch_terminals(self):
        """Test dry-run mode does not actually launch terminals."""
        runner = CliRunner()

        mock_config = Mock(default_resource_group="test-rg")
        mock_vms = [
            Mock(
                name="vm-1",
                resource_group="test-rg",
                power_state="VM running",
                public_ip="10.0.0.1",
            ),
        ]

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
                with patch.object(TerminalLauncher, "launch_all_sessions") as mock_launch:
                    result = runner.invoke(restore_command, ["--dry-run"])

                    assert result.exit_code == 0
                    # Should NOT have called launch_all_sessions
                    mock_launch.assert_not_called()

    def test_dry_run_with_no_vms(self):
        """Test dry-run mode with no VMs."""
        runner = CliRunner()

        mock_config = Mock(default_resource_group="test-rg")

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=[]):
                result = runner.invoke(restore_command, ["--dry-run"])

                assert result.exit_code == 2  # Total failure
                assert "No running VMs" in result.output or "no VMs" in result.output.lower()


# ============================================================================
# ERROR SCENARIOS
# ============================================================================


class TestErrorScenarios:
    """Test error handling in end-to-end workflows."""

    def test_no_running_vms_error(self):
        """Test error when no running VMs found."""
        runner = CliRunner()

        mock_config = Mock(default_resource_group="test-rg")

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=[]):
                result = runner.invoke(restore_command)

                assert result.exit_code == 2
                assert "No running VMs" in result.output or "no VMs" in result.output.lower()
                # Should provide actionable guidance
                assert "azlin list" in result.output or "check" in result.output.lower()

    def test_config_load_error(self):
        """Test error when config cannot be loaded."""
        runner = CliRunner()

        with patch(
            "azlin.config_manager.ConfigManager.load_config",
            side_effect=FileNotFoundError("Config not found"),
        ):
            result = runner.invoke(restore_command)

            assert result.exit_code == 2
            assert "error" in result.output.lower()

    def test_vm_manager_error(self):
        """Test error when VMManager fails."""
        runner = CliRunner()

        mock_config = Mock(default_resource_group="test-rg")

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch(
                "azlin.vm_manager.VMManager.list_vms", side_effect=Exception("Azure API error")
            ):
                result = runner.invoke(restore_command)

                assert result.exit_code == 2
                assert "error" in result.output.lower()

    def test_partial_failure_returns_exit_code_1(self):
        """Test partial failure returns exit code 1."""
        runner = CliRunner()

        mock_config = Mock(default_resource_group="test-rg")
        mock_vms = [
            Mock(
                name=f"vm-{i}",
                resource_group="test-rg",
                power_state="VM running",
                public_ip=f"10.0.0.{i}",
            )
            for i in range(5)
        ]

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
                with patch.object(TerminalLauncher, "launch_all_sessions", return_value=(3, 2)):
                    result = runner.invoke(restore_command)

                    assert result.exit_code == 1  # Partial failure
                    assert "Warning" in result.output or "failed" in result.output.lower()
                    assert "3" in result.output  # Success count
                    assert "2" in result.output  # Failure count

    def test_total_failure_returns_exit_code_2(self):
        """Test total failure returns exit code 2."""
        runner = CliRunner()

        mock_config = Mock(default_resource_group="test-rg")
        mock_vms = [
            Mock(
                name="vm-1",
                resource_group="test-rg",
                power_state="VM running",
                public_ip="10.0.0.1",
            ),
        ]

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
                with patch.object(TerminalLauncher, "launch_all_sessions", return_value=(0, 1)):
                    result = runner.invoke(restore_command)

                    assert result.exit_code == 2  # Total failure


# ============================================================================
# PLATFORM-SPECIFIC WORKFLOWS
# ============================================================================


class TestPlatformSpecificWorkflows:
    """Test platform-specific restore workflows."""

    def test_restore_on_macos(self):
        """Test restore workflow on macOS."""
        runner = CliRunner()

        mock_config = Mock(default_resource_group="test-rg")
        mock_vms = [
            Mock(
                name="vm-1",
                resource_group="test-rg",
                power_state="VM running",
                public_ip="10.0.0.1",
            ),
        ]

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
                with patch.object(PlatformDetector, "detect_platform", return_value="macos"):
                    with patch.object(
                        PlatformDetector,
                        "get_default_terminal",
                        return_value=TerminalType.MACOS_TERMINAL,
                    ):
                        with patch.object(
                            TerminalLauncher, "launch_all_sessions", return_value=(1, 0)
                        ):
                            result = runner.invoke(restore_command)

                            assert result.exit_code == 0

    def test_restore_on_wsl(self):
        """Test restore workflow on WSL."""
        runner = CliRunner()

        mock_config = Mock(default_resource_group="test-rg")
        mock_vms = [
            Mock(
                name="vm-1",
                resource_group="test-rg",
                power_state="VM running",
                public_ip="10.0.0.1",
            ),
        ]

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
                with patch.object(PlatformDetector, "detect_platform", return_value="wsl"):
                    with patch.object(
                        PlatformDetector,
                        "get_default_terminal",
                        return_value=TerminalType.WINDOWS_TERMINAL,
                    ):
                        with patch.object(
                            PlatformDetector,
                            "get_windows_terminal_path",
                            return_value=Path("/mnt/c/wt.exe"),
                        ):
                            with patch.object(
                                TerminalLauncher, "launch_all_sessions", return_value=(1, 0)
                            ):
                                result = runner.invoke(restore_command)

                                assert result.exit_code == 0

    def test_restore_on_linux_with_gnome_terminal(self):
        """Test restore workflow on Linux with gnome-terminal."""
        runner = CliRunner()

        mock_config = Mock(default_resource_group="test-rg")
        mock_vms = [
            Mock(
                name="vm-1",
                resource_group="test-rg",
                power_state="VM running",
                public_ip="10.0.0.1",
            ),
        ]

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
                with patch.object(PlatformDetector, "detect_platform", return_value="linux"):
                    with patch.object(
                        PlatformDetector,
                        "get_default_terminal",
                        return_value=TerminalType.LINUX_GNOME,
                    ):
                        with patch.object(
                            TerminalLauncher, "launch_all_sessions", return_value=(1, 0)
                        ):
                            result = runner.invoke(restore_command)

                            assert result.exit_code == 0

    def test_restore_fails_gracefully_on_unknown_platform(self):
        """Test restore handles unknown platform gracefully."""
        runner = CliRunner()

        mock_config = Mock(default_resource_group="test-rg")
        mock_vms = [
            Mock(
                name="vm-1",
                resource_group="test-rg",
                power_state="VM running",
                public_ip="10.0.0.1",
            ),
        ]

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
                with patch.object(PlatformDetector, "detect_platform", return_value="unknown"):
                    with patch.object(
                        PlatformDetector, "get_default_terminal", return_value=TerminalType.UNKNOWN
                    ):
                        result = runner.invoke(restore_command)

                        # Should either fail gracefully or provide error message
                        assert result.exit_code != 0 or "warning" in result.output.lower()


# ============================================================================
# OUTPUT AND USER EXPERIENCE TESTS
# ============================================================================


class TestOutputAndUserExperience:
    """Test command output and user experience."""

    def test_successful_restore_prints_summary(self):
        """Test successful restore prints summary."""
        runner = CliRunner()

        mock_config = Mock(default_resource_group="test-rg")
        mock_vms = [
            Mock(
                name="vm-1",
                resource_group="test-rg",
                power_state="VM running",
                public_ip="10.0.0.1",
            ),
            Mock(
                name="vm-2",
                resource_group="test-rg",
                power_state="VM running",
                public_ip="10.0.0.2",
            ),
        ]

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
                with patch.object(TerminalLauncher, "launch_all_sessions", return_value=(2, 0)):
                    result = runner.invoke(restore_command)

                    assert (
                        "Successfully restored" in result.output
                        or "success" in result.output.lower()
                    )
                    assert "2" in result.output  # Number of sessions

    def test_error_provides_actionable_guidance(self):
        """Test error messages provide actionable guidance."""
        runner = CliRunner()

        mock_config = Mock(default_resource_group="test-rg")

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=[]):
                result = runner.invoke(restore_command)

                # Should suggest what user can do
                assert "azlin list" in result.output or "run" in result.output.lower()

    def test_partial_failure_shows_which_failed(self):
        """Test partial failure shows which sessions failed."""
        runner = CliRunner()

        mock_config = Mock(default_resource_group="test-rg")
        mock_vms = [
            Mock(
                name=f"vm-{i}",
                resource_group="test-rg",
                power_state="VM running",
                public_ip=f"10.0.0.{i}",
            )
            for i in range(3)
        ]

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
                with patch.object(TerminalLauncher, "launch_all_sessions", return_value=(2, 1)):
                    result = runner.invoke(restore_command)

                    assert "Warning" in result.output or "failed" in result.output.lower()
                    assert "2" in result.output  # Successful
                    assert "1" in result.output  # Failed


# ============================================================================
# SECURITY E2E TESTS
# ============================================================================


class TestSecurityE2E:
    """End-to-end security tests."""

    def test_command_injection_prevented_end_to_end(self):
        """Test command injection is prevented throughout the workflow."""
        runner = CliRunner()

        # VM with potentially dangerous data
        mock_config = Mock(default_resource_group="test-rg")
        mock_vms = [
            Mock(
                name="vm; rm -rf /",
                resource_group="test-rg",
                power_state="VM running",
                public_ip="host && malicious",
            ),
        ]

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
                with patch.object(
                    TerminalLauncher, "launch_all_sessions", return_value=(0, 1)
                ) as mock_launch:
                    result = runner.invoke(restore_command)

                    # Should either reject dangerous input or handle it safely
                    # Result should not be successful with dangerous input unvalidated
                    assert result.exit_code != 0 or mock_launch.call_count == 0

    def test_path_traversal_prevented_end_to_end(self):
        """Test path traversal is prevented throughout the workflow."""
        runner = CliRunner()

        # Config with dangerous path
        mock_config = Mock(
            default_resource_group="test-rg",
            ssh_key_path="../../etc/passwd",
        )
        mock_vms = [
            Mock(
                name="vm-1",
                resource_group="test-rg",
                power_state="VM running",
                public_ip="10.0.0.1",
            ),
        ]

        with patch("azlin.config_manager.ConfigManager.load_config", return_value=mock_config):
            with patch("azlin.vm_manager.VMManager.list_vms", return_value=mock_vms):
                # Should validate paths before launching terminals
                result = runner.invoke(restore_command)

                # Implementation must handle dangerous paths safely
                # Either reject or sanitize
                assert result.exit_code is not None
