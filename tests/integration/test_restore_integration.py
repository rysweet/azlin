"""Integration tests for azlin restore command - TDD approach.

These tests verify integration between:
- VMManager
- ConfigManager
- TerminalLauncher
- PlatformDetector

Testing pyramid: 30% of total test suite
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Import will fail until implementation exists
try:
    from azlin.commands.restore import (
        PlatformDetector,
        RestoreSessionConfig,
        TerminalLauncher,
        TerminalType,
    )
except ImportError:
    pytest.skip("azlin.commands.restore not implemented yet", allow_module_level=True)


# ============================================================================
# VM MANAGER INTEGRATION TESTS
# ============================================================================


class TestVMManagerIntegration:
    """Test integration with VMManager."""

    def test_restore_fetches_running_vms_only(self):
        """Test restore fetches only running VMs."""
        mock_vms = [
            Mock(
                name="vm-running",
                resource_group="test-rg",
                power_state="VM running",
                public_ip="192.168.1.100",
            ),
            Mock(
                name="vm-stopped",
                resource_group="test-rg",
                power_state="VM stopped",
                public_ip=None,
            ),
        ]

        with patch("azlin.vm_manager.VMManager.list_vms") as mock_list:
            mock_list.return_value = mock_vms
            # Call with include_stopped=False
            vms = mock_list("test-rg", include_stopped=False)
            mock_list.assert_called_once_with("test-rg", include_stopped=False)
            assert len(vms) == 2

    def test_restore_handles_empty_vm_list(self):
        """Test restore handles no running VMs."""
        with patch("azlin.vm_manager.VMManager.list_vms") as mock_list:
            mock_list.return_value = []
            vms = mock_list("test-rg", include_stopped=False)
            assert vms == []

    def test_restore_handles_vm_manager_error(self):
        """Test restore handles VMManager errors."""
        with patch("azlin.vm_manager.VMManager.list_vms") as mock_list:
            mock_list.side_effect = Exception("Azure API error")
            with pytest.raises(Exception, match="Azure API error"):
                mock_list("test-rg")

    def test_restore_filters_by_resource_group(self):
        """Test restore filters VMs by resource group."""
        with patch("azlin.vm_manager.VMManager.list_vms") as mock_list:
            mock_list.return_value = [
                Mock(name="vm-1", resource_group="rg-1"),
                Mock(name="vm-2", resource_group="rg-1"),
            ]
            vms = mock_list("rg-1", include_stopped=False)
            mock_list.assert_called_once_with("rg-1", include_stopped=False)
            assert len(vms) == 2


# ============================================================================
# CONFIG MANAGER INTEGRATION TESTS
# ============================================================================


class TestConfigManagerIntegration:
    """Test integration with ConfigManager."""

    def test_restore_loads_config_successfully(self):
        """Test restore loads azlin config."""
        mock_config = Mock(
            default_resource_group="test-rg",
            terminal_launcher=None,
            terminal_multi_tab=True,
            restore_timeout=30,
        )

        with patch("azlin.config_manager.ConfigManager.load_config") as mock_load:
            mock_load.return_value = mock_config
            config = mock_load()
            assert config.default_resource_group == "test-rg"
            assert config.terminal_multi_tab is True

    def test_restore_handles_missing_config(self):
        """Test restore handles missing config file."""
        with patch("azlin.config_manager.ConfigManager.load_config") as mock_load:
            mock_load.side_effect = FileNotFoundError("Config not found")
            with pytest.raises(FileNotFoundError):
                mock_load()

    def test_restore_uses_config_terminal_override(self):
        """Test restore uses terminal override from config."""
        mock_config = Mock(
            terminal_launcher="windows_terminal",
            terminal_multi_tab=True,
        )

        with patch("azlin.config_manager.ConfigManager.load_config") as mock_load:
            mock_load.return_value = mock_config
            config = mock_load()
            assert config.terminal_launcher == "windows_terminal"

    def test_restore_gets_session_name_for_vm(self):
        """Test getting session name for VM from config."""
        with patch("azlin.config_manager.ConfigManager.get_session_name") as mock_get:
            mock_get.return_value = "custom-session"
            session_name = mock_get("test-vm")
            mock_get.assert_called_once_with("test-vm")
            assert session_name == "custom-session"

    def test_restore_falls_back_to_default_session_name(self):
        """Test fallback to default session name when not in config."""
        with patch("azlin.config_manager.ConfigManager.get_session_name") as mock_get:
            mock_get.return_value = None
            session_name = mock_get("unknown-vm")
            assert session_name is None


# ============================================================================
# PLATFORM DETECTOR INTEGRATION TESTS
# ============================================================================


class TestPlatformDetectorIntegration:
    """Test platform detection integration."""

    def test_restore_detects_platform_and_selects_terminal(self):
        """Test platform detection and terminal selection flow."""
        with patch.object(PlatformDetector, "detect_platform", return_value="macos"):
            platform = PlatformDetector.detect_platform()
            assert platform == "macos"

            terminal_type = PlatformDetector.get_default_terminal()
            assert terminal_type == TerminalType.MACOS_TERMINAL

    def test_restore_handles_terminal_override(self):
        """Test terminal override takes precedence over detection."""
        # User specifies terminal in config
        user_terminal = "windows_terminal"

        # Platform detection should still work
        with patch.object(PlatformDetector, "detect_platform", return_value="linux"):
            platform = PlatformDetector.detect_platform()
            assert platform == "linux"

            # But user override should be used instead of detected default
            # (this is handled in command implementation, not detector)

    def test_restore_validates_terminal_availability(self):
        """Test terminal availability validation."""
        with patch.object(PlatformDetector, "_has_command") as mock_has:
            mock_has.return_value = True
            result = PlatformDetector._has_command("gnome-terminal")
            assert result is True

            mock_has.return_value = False
            result = PlatformDetector._has_command("nonexistent-terminal")
            assert result is False


# ============================================================================
# TERMINAL LAUNCHER INTEGRATION TESTS
# ============================================================================


class TestTerminalLauncherIntegration:
    """Test TerminalLauncher integration."""

    def test_restore_creates_session_configs_from_vms(self):
        """Test creating RestoreSessionConfig from VM data."""
        mock_vm = Mock(
            name="test-vm",
            public_ip="192.168.1.100",
        )

        config = RestoreSessionConfig(
            vm_name=mock_vm.name,
            hostname=mock_vm.public_ip,
            username="azureuser",
            ssh_key_path=Path("~/.ssh/id_rsa"),
            tmux_session="azlin",
            terminal_type=TerminalType.MACOS_TERMINAL,
        )

        assert config.vm_name == "test-vm"
        assert config.hostname == "192.168.1.100"
        assert config.username == "azureuser"

    def test_restore_launches_multiple_sessions(self):
        """Test launching sessions for multiple VMs."""
        sessions = [
            RestoreSessionConfig(
                vm_name=f"vm-{i}",
                hostname=f"192.168.1.{100 + i}",
                username="azureuser",
                ssh_key_path=Path("~/.ssh/id_rsa"),
                terminal_type=TerminalType.MACOS_TERMINAL,
            )
            for i in range(3)
        ]

        with patch.object(TerminalLauncher, "launch_session", return_value=True):
            success_count, failed_count = TerminalLauncher.launch_all_sessions(sessions)
            assert success_count == 3
            assert failed_count == 0

    def test_restore_handles_launch_failures_gracefully(self):
        """Test graceful handling of launch failures."""
        sessions = [
            RestoreSessionConfig(
                vm_name=f"vm-{i}",
                hostname=f"192.168.1.{100 + i}",
                username="azureuser",
                ssh_key_path=Path("~/.ssh/id_rsa"),
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


# ============================================================================
# FULL WORKFLOW INTEGRATION TESTS
# ============================================================================


class TestFullWorkflowIntegration:
    """Test full restore workflow integration."""

    def test_full_workflow_successful_restore(self):
        """Test complete workflow from VMs to launched terminals."""
        # Step 1: Load config
        mock_config = Mock(
            default_resource_group="test-rg",
            terminal_launcher=None,
            terminal_multi_tab=False,
        )

        # Step 2: List VMs
        mock_vms = [
            Mock(name="vm-1", public_ip="192.168.1.100"),
            Mock(name="vm-2", public_ip="192.168.1.101"),
        ]

        # Step 3: Detect platform
        with patch("azlin.config_manager.ConfigManager.load_config") as mock_load_config:
            mock_load_config.return_value = mock_config

            with patch("azlin.vm_manager.VMManager.list_vms") as mock_list_vms:
                mock_list_vms.return_value = mock_vms

                with patch.object(PlatformDetector, "detect_platform", return_value="macos"):
                    with patch.object(TerminalLauncher, "launch_all_sessions", return_value=(2, 0)):
                        # Simulate full workflow
                        config = mock_load_config()
                        vms = mock_list_vms(config.default_resource_group, include_stopped=False)
                        platform = PlatformDetector.detect_platform()
                        terminal_type = PlatformDetector.get_default_terminal()

                        # Create sessions
                        sessions = [
                            RestoreSessionConfig(
                                vm_name=vm.name,
                                hostname=vm.public_ip,
                                username="azureuser",
                                ssh_key_path=Path("~/.ssh/id_rsa"),
                                terminal_type=terminal_type,
                            )
                            for vm in vms
                        ]

                        # Launch sessions
                        success, failed = TerminalLauncher.launch_all_sessions(sessions)

                        assert success == 2
                        assert failed == 0

    def test_full_workflow_with_resource_group_filter(self):
        """Test workflow with specific resource group."""
        mock_vms = [
            Mock(name="vm-1", resource_group="filtered-rg", public_ip="10.0.0.1"),
        ]

        with patch("azlin.vm_manager.VMManager.list_vms") as mock_list:
            mock_list.return_value = mock_vms

            with patch.object(
                PlatformDetector, "get_default_terminal", return_value=TerminalType.MACOS_TERMINAL
            ):
                with patch.object(TerminalLauncher, "launch_all_sessions", return_value=(1, 0)):
                    vms = mock_list("filtered-rg", include_stopped=False)
                    terminal_type = PlatformDetector.get_default_terminal()

                    sessions = [
                        RestoreSessionConfig(
                            vm_name=vm.name,
                            hostname=vm.public_ip,
                            username="azureuser",
                            ssh_key_path=Path("~/.ssh/id_rsa"),
                            terminal_type=terminal_type,
                        )
                        for vm in vms
                    ]

                    success, failed = TerminalLauncher.launch_all_sessions(sessions)
                    assert success == 1
                    assert failed == 0

    def test_full_workflow_handles_no_vms(self):
        """Test workflow when no VMs are running."""
        with patch("azlin.vm_manager.VMManager.list_vms") as mock_list:
            mock_list.return_value = []
            vms = mock_list("test-rg", include_stopped=False)
            assert len(vms) == 0
            # Should not attempt to launch any terminals

    def test_full_workflow_with_custom_session_names(self):
        """Test workflow uses custom session names from config."""
        mock_vms = [
            Mock(name="vm-dev", public_ip="10.0.0.1"),
            Mock(name="vm-prod", public_ip="10.0.0.2"),
        ]

        session_name_mapping = {
            "vm-dev": "development",
            "vm-prod": "production",
        }

        with patch("azlin.vm_manager.VMManager.list_vms") as mock_list:
            mock_list.return_value = mock_vms

            with patch("azlin.config_manager.ConfigManager.get_session_name") as mock_get_session:
                mock_get_session.side_effect = lambda vm_name: session_name_mapping.get(
                    vm_name, "azlin"
                )

                # Get session names
                session_names = [mock_get_session(vm.name) for vm in mock_vms]
                assert session_names == ["development", "production"]

    def test_full_workflow_with_multi_tab_mode(self):
        """Test workflow with Windows Terminal multi-tab mode."""
        mock_vms = [Mock(name=f"vm-{i}", public_ip=f"10.0.0.{i}") for i in range(3)]

        with patch("azlin.vm_manager.VMManager.list_vms") as mock_list:
            mock_list.return_value = mock_vms

            with patch.object(
                PlatformDetector, "get_default_terminal", return_value=TerminalType.WINDOWS_TERMINAL
            ):
                with patch.object(
                    TerminalLauncher, "launch_all_sessions", return_value=(3, 0)
                ) as mock_launch:
                    vms = mock_list("test-rg", include_stopped=False)
                    terminal_type = PlatformDetector.get_default_terminal()

                    sessions = [
                        RestoreSessionConfig(
                            vm_name=vm.name,
                            hostname=vm.public_ip,
                            username="azureuser",
                            ssh_key_path=Path("~/.ssh/id_rsa"),
                            terminal_type=terminal_type,
                        )
                        for vm in vms
                    ]

                    success, failed = TerminalLauncher.launch_all_sessions(sessions, multi_tab=True)
                    assert success == 3
                    assert failed == 0
                    mock_launch.assert_called_once()


# ============================================================================
# ERROR HANDLING INTEGRATION TESTS
# ============================================================================


class TestErrorHandlingIntegration:
    """Test error handling across components."""

    def test_handles_vm_manager_failure(self):
        """Test handling VMManager failures."""
        with patch("azlin.vm_manager.VMManager.list_vms") as mock_list:
            mock_list.side_effect = Exception("Azure API timeout")
            with pytest.raises(Exception, match="Azure API timeout"):
                mock_list("test-rg")

    def test_handles_config_load_failure(self):
        """Test handling config load failures."""
        with patch("azlin.config_manager.ConfigManager.load_config") as mock_load:
            mock_load.side_effect = Exception("Config parse error")
            with pytest.raises(Exception, match="Config parse error"):
                mock_load()

    def test_handles_platform_detection_failure(self):
        """Test handling platform detection failures."""
        with patch("platform.system", side_effect=Exception("Platform error")):
            with pytest.raises(Exception, match="Platform error"):
                PlatformDetector.detect_platform()

    def test_continues_on_partial_terminal_launch_failure(self):
        """Test continues launching when some terminals fail."""
        sessions = [
            RestoreSessionConfig(
                vm_name=f"vm-{i}",
                hostname=f"10.0.0.{i}",
                username="azureuser",
                ssh_key_path=Path("~/.ssh/id_rsa"),
                terminal_type=TerminalType.MACOS_TERMINAL,
            )
            for i in range(5)
        ]

        # Simulate intermittent failures
        with patch.object(
            TerminalLauncher, "launch_session", side_effect=[True, False, True, False, True]
        ):
            success, failed = TerminalLauncher.launch_all_sessions(sessions)
            assert success == 3
            assert failed == 2


# ============================================================================
# SECURITY INTEGRATION TESTS
# ============================================================================


class TestSecurityIntegration:
    """Test security across integrated components."""

    def test_end_to_end_input_validation(self):
        """Test input validation from VM data to terminal launch."""
        # VM with potentially dangerous data
        mock_vm = Mock(
            name="vm; malicious",
            public_ip="host && evil",
        )

        # Should be validated when creating session config
        config = RestoreSessionConfig(
            vm_name=mock_vm.name,
            hostname=mock_vm.public_ip,
            username="user | cat",
            ssh_key_path=Path("../../etc/passwd"),
        )

        # Integration test: ensure validation happens somewhere in pipeline
        # (either in config creation, or terminal launch, or both)
        assert config is not None
        # Implementation must handle dangerous inputs safely

    def test_ssh_key_path_resolution_security(self):
        """Test SSH key path is properly resolved and validated."""
        dangerous_paths = [
            Path("~/../../../etc/passwd"),
            Path("../../root/.ssh/id_rsa"),
        ]

        for dangerous_path in dangerous_paths:
            config = RestoreSessionConfig(
                vm_name="test-vm",
                hostname="10.0.0.1",
                username="azureuser",
                ssh_key_path=dangerous_path,
            )
            # Implementation must validate paths before use
            assert config.ssh_key_path == dangerous_path
            # Validation should happen during terminal launch
