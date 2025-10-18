"""Unit tests for log_viewer module.

Tests the LogViewer class for retrieving and viewing VM logs.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from azlin.log_viewer import LogResult, LogType, LogViewer, LogViewerError
from azlin.modules.ssh_connector import SSHConfig
from azlin.vm_manager import VMInfo


class TestLogType:
    """Test LogType enum."""

    def test_log_type_values(self):
        """Test that LogType has expected values."""
        assert LogType.SYSTEM.value == "system"
        assert LogType.BOOT.value == "boot"
        assert LogType.APP.value == "app"
        assert LogType.KERNEL.value == "kernel"


class TestLogViewer:
    """Test LogViewer class."""

    @pytest.fixture
    def mock_vm(self):
        """Create a mock VM."""
        vm = Mock(spec=VMInfo)
        vm.name = "test-vm"
        vm.public_ip = "20.1.2.3"
        vm.resource_group = "test-rg"
        vm.is_running.return_value = True
        return vm

    @pytest.fixture
    def ssh_config(self):
        """Create SSH config."""
        return SSHConfig(host="20.1.2.3", user="azureuser", key_path=Path("/home/user/.ssh/id_rsa"))

    def test_get_system_logs_success(self, mock_vm, ssh_config):
        """Test retrieving system logs successfully."""
        with (
            patch("azlin.log_viewer.VMManager") as mock_vm_manager,
            patch("azlin.log_viewer.SSHKeyManager") as mock_ssh_keys,
            patch("azlin.log_viewer.RemoteExecutor") as mock_executor,
        ):
            # Setup mocks
            mock_vm_manager.get_vm.return_value = mock_vm
            mock_ssh_keys.ensure_key_exists.return_value = Mock(
                private_path=Path("/home/user/.ssh/id_rsa")
            )
            mock_executor.execute_command.return_value = Mock(
                success=True,
                stdout="Jan 01 10:00:00 test-vm systemd[1]: Started session.\nJan 01 10:01:00 test-vm kernel: OK",
                stderr="",
                exit_code=0,
            )

            # Execute
            result = LogViewer.get_system_logs(
                vm_name="test-vm", resource_group="test-rg", lines=100
            )

            # Verify
            assert result.success is True
            assert "systemd" in result.logs
            assert result.line_count == 2

            # Verify SSH command
            call_args = mock_executor.execute_command.call_args
            command = call_args[1]["command"]  # kwargs
            assert "journalctl" in command
            assert "--no-pager" in command
            assert "-n 100" in command

    def test_get_boot_logs_success(self, mock_vm):
        """Test retrieving boot logs successfully."""
        with (
            patch("azlin.log_viewer.VMManager") as mock_vm_manager,
            patch("azlin.log_viewer.SSHKeyManager") as mock_ssh_keys,
            patch("azlin.log_viewer.RemoteExecutor") as mock_executor,
        ):
            # Setup mocks
            mock_vm_manager.get_vm.return_value = mock_vm
            mock_ssh_keys.ensure_key_exists.return_value = Mock(
                private_path=Path("/home/user/.ssh/id_rsa")
            )
            mock_executor.execute_command.return_value = Mock(
                success=True, stdout="Boot log line 1\nBoot log line 2", stderr="", exit_code=0
            )

            # Execute
            result = LogViewer.get_boot_logs(vm_name="test-vm", resource_group="test-rg")

            # Verify
            assert result.success is True
            assert "Boot log" in result.logs

            # Verify boot flag
            call_args = mock_executor.execute_command.call_args
            command = call_args[1]["command"]
            assert "-b" in command or "--boot" in command

    def test_get_kernel_logs_success(self, mock_vm):
        """Test retrieving kernel logs successfully."""
        with (
            patch("azlin.log_viewer.VMManager") as mock_vm_manager,
            patch("azlin.log_viewer.SSHKeyManager") as mock_ssh_keys,
            patch("azlin.log_viewer.RemoteExecutor") as mock_executor,
        ):
            # Setup mocks
            mock_vm_manager.get_vm.return_value = mock_vm
            mock_ssh_keys.ensure_key_exists.return_value = Mock(
                private_path=Path("/home/user/.ssh/id_rsa")
            )
            mock_executor.execute_command.return_value = Mock(
                success=True, stdout="kernel: message 1\nkernel: message 2", stderr="", exit_code=0
            )

            # Execute
            result = LogViewer.get_kernel_logs(
                vm_name="test-vm", resource_group="test-rg", lines=50
            )

            # Verify
            assert result.success is True
            assert "kernel" in result.logs

            # Verify kernel flag
            call_args = mock_executor.execute_command.call_args
            command = call_args[1]["command"]
            assert "-k" in command or "--dmesg" in command

    def test_get_logs_with_since_time(self, mock_vm):
        """Test retrieving logs with --since time filter."""
        with (
            patch("azlin.log_viewer.VMManager") as mock_vm_manager,
            patch("azlin.log_viewer.SSHKeyManager") as mock_ssh_keys,
            patch("azlin.log_viewer.RemoteExecutor") as mock_executor,
        ):
            # Setup mocks
            mock_vm_manager.get_vm.return_value = mock_vm
            mock_ssh_keys.ensure_key_exists.return_value = Mock(
                private_path=Path("/home/user/.ssh/id_rsa")
            )
            mock_executor.execute_command.return_value = Mock(
                success=True, stdout="Recent log line", stderr="", exit_code=0
            )

            # Execute
            result = LogViewer.get_system_logs(
                vm_name="test-vm", resource_group="test-rg", since="1 hour ago"
            )

            # Verify
            assert result.success is True

            # Verify --since flag
            call_args = mock_executor.execute_command.call_args
            command = call_args[1]["command"]
            assert "--since" in command
            assert "1 hour ago" in command

    def test_vm_not_found(self):
        """Test error when VM not found."""
        with patch("azlin.log_viewer.VMManager") as mock_vm_manager:
            mock_vm_manager.get_vm.return_value = None

            # Execute and verify exception
            with pytest.raises(LogViewerError) as exc_info:
                LogViewer.get_system_logs(vm_name="nonexistent-vm", resource_group="test-rg")

            assert "not found" in str(exc_info.value).lower()

    def test_vm_not_running(self, mock_vm):
        """Test error when VM is not running."""
        mock_vm.is_running.return_value = False
        mock_vm.power_state = "VM deallocated"

        with patch("azlin.log_viewer.VMManager") as mock_vm_manager:
            mock_vm_manager.get_vm.return_value = mock_vm

            # Execute and verify exception
            with pytest.raises(LogViewerError) as exc_info:
                LogViewer.get_system_logs(vm_name="test-vm", resource_group="test-rg")

            assert "not running" in str(exc_info.value).lower()

    def test_vm_no_public_ip(self, mock_vm):
        """Test error when VM has no public IP."""
        mock_vm.public_ip = None

        with patch("azlin.log_viewer.VMManager") as mock_vm_manager:
            mock_vm_manager.get_vm.return_value = mock_vm

            # Execute and verify exception
            with pytest.raises(LogViewerError) as exc_info:
                LogViewer.get_system_logs(vm_name="test-vm", resource_group="test-rg")

            assert "no public ip" in str(exc_info.value).lower()

    def test_ssh_command_failure(self, mock_vm):
        """Test handling of SSH command failure."""
        with (
            patch("azlin.log_viewer.VMManager") as mock_vm_manager,
            patch("azlin.log_viewer.SSHKeyManager") as mock_ssh_keys,
            patch("azlin.log_viewer.RemoteExecutor") as mock_executor,
        ):
            # Setup mocks
            mock_vm_manager.get_vm.return_value = mock_vm
            mock_ssh_keys.ensure_key_exists.return_value = Mock(
                private_path=Path("/home/user/.ssh/id_rsa")
            )
            mock_executor.execute_command.return_value = Mock(
                success=False, stdout="", stderr="Connection refused", exit_code=255
            )

            # Execute and verify exception
            with pytest.raises(LogViewerError) as exc_info:
                LogViewer.get_system_logs(vm_name="test-vm", resource_group="test-rg")

            assert "failed" in str(exc_info.value).lower()

    def test_follow_logs(self, mock_vm):
        """Test following logs in real-time."""
        with (
            patch("azlin.log_viewer.VMManager") as mock_vm_manager,
            patch("azlin.log_viewer.SSHKeyManager") as mock_ssh_keys,
            patch("azlin.log_viewer.SSHConnector") as mock_connector,
        ):
            # Setup mocks
            mock_vm_manager.get_vm.return_value = mock_vm
            mock_ssh_keys.ensure_key_exists.return_value = Mock(
                private_path=Path("/home/user/.ssh/id_rsa")
            )
            mock_connector.connect.return_value = 0

            # Execute
            exit_code = LogViewer.follow_logs(
                vm_name="test-vm", resource_group="test-rg", log_type=LogType.SYSTEM
            )

            # Verify
            assert exit_code == 0

            # Verify follow command was used
            call_args = mock_connector.connect.call_args
            assert call_args is not None

    def test_parse_time_relative(self):
        """Test parsing relative time strings."""
        # These should be handled by journalctl directly
        times = ["1 hour ago", "30 minutes ago", "2 days ago", "yesterday", "today"]

        for time_str in times:
            # Should not raise exception
            result = LogViewer._validate_time_string(time_str)
            assert result == time_str

    def test_parse_time_absolute(self):
        """Test parsing absolute time strings."""
        times = ["2024-01-01", "2024-01-01 14:30:00"]

        for time_str in times:
            # Should not raise exception
            result = LogViewer._validate_time_string(time_str)
            assert result == time_str

    def test_invalid_time_format(self):
        """Test error on invalid time format."""
        with pytest.raises(LogViewerError) as exc_info:
            LogViewer._validate_time_string("invalid-time-format-xyz")

        assert "invalid time format" in str(exc_info.value).lower()

    def test_line_limiting(self, mock_vm):
        """Test that line limiting is applied correctly."""
        with (
            patch("azlin.log_viewer.VMManager") as mock_vm_manager,
            patch("azlin.log_viewer.SSHKeyManager") as mock_ssh_keys,
            patch("azlin.log_viewer.RemoteExecutor") as mock_executor,
        ):
            # Setup mocks
            mock_vm_manager.get_vm.return_value = mock_vm
            mock_ssh_keys.ensure_key_exists.return_value = Mock(
                private_path=Path("/home/user/.ssh/id_rsa")
            )
            mock_executor.execute_command.return_value = Mock(
                success=True, stdout="log line", stderr="", exit_code=0
            )

            # Execute with custom line limit
            LogViewer.get_system_logs(vm_name="test-vm", resource_group="test-rg", lines=50)

            # Verify -n flag
            call_args = mock_executor.execute_command.call_args
            command = call_args[1]["command"]
            assert "-n 50" in command or "-n50" in command

    def test_get_app_logs_with_service(self, mock_vm):
        """Test retrieving application logs for a specific service."""
        with (
            patch("azlin.log_viewer.VMManager") as mock_vm_manager,
            patch("azlin.log_viewer.SSHKeyManager") as mock_ssh_keys,
            patch("azlin.log_viewer.RemoteExecutor") as mock_executor,
        ):
            # Setup mocks
            mock_vm_manager.get_vm.return_value = mock_vm
            mock_ssh_keys.ensure_key_exists.return_value = Mock(
                private_path=Path("/home/user/.ssh/id_rsa")
            )
            mock_executor.execute_command.return_value = Mock(
                success=True, stdout="app log line", stderr="", exit_code=0
            )

            # Execute
            result = LogViewer.get_app_logs(
                vm_name="test-vm", resource_group="test-rg", service="nginx"
            )

            # Verify
            assert result.success is True

            # Verify -u flag for service
            call_args = mock_executor.execute_command.call_args
            command = call_args[1]["command"]
            assert "-u nginx" in command or "-u=nginx" in command

    def test_build_journalctl_command_system(self):
        """Test building journalctl command for system logs."""
        command = LogViewer._build_journalctl_command(
            log_type=LogType.SYSTEM, lines=100, since=None
        )

        assert "journalctl" in command
        assert "--no-pager" in command
        assert "-n 100" in command

    def test_build_journalctl_command_boot(self):
        """Test building journalctl command for boot logs."""
        command = LogViewer._build_journalctl_command(log_type=LogType.BOOT, lines=100, since=None)

        assert "journalctl" in command
        assert "-b" in command or "--boot" in command

    def test_build_journalctl_command_kernel(self):
        """Test building journalctl command for kernel logs."""
        command = LogViewer._build_journalctl_command(log_type=LogType.KERNEL, lines=50, since=None)

        assert "journalctl" in command
        assert "-k" in command or "--dmesg" in command
        assert "-n 50" in command

    def test_build_journalctl_command_with_since(self):
        """Test building journalctl command with since parameter."""
        command = LogViewer._build_journalctl_command(
            log_type=LogType.SYSTEM, lines=100, since="1 hour ago"
        )

        assert "journalctl" in command
        assert "--since" in command
        assert "1 hour ago" in command

    def test_log_result_properties(self):
        """Test LogResult dataclass properties."""
        result = LogResult(
            success=True,
            logs="test log output",
            vm_name="test-vm",
            log_type=LogType.SYSTEM,
            line_count=5,
        )

        assert result.success is True
        assert result.logs == "test log output"
        assert result.vm_name == "test-vm"
        assert result.log_type == LogType.SYSTEM
        assert result.line_count == 5

    def test_timeout_parameter(self, mock_vm):
        """Test that timeout parameter is passed to SSH executor."""
        with (
            patch("azlin.log_viewer.VMManager") as mock_vm_manager,
            patch("azlin.log_viewer.SSHKeyManager") as mock_ssh_keys,
            patch("azlin.log_viewer.RemoteExecutor") as mock_executor,
        ):
            # Setup mocks
            mock_vm_manager.get_vm.return_value = mock_vm
            mock_ssh_keys.ensure_key_exists.return_value = Mock(
                private_path=Path("/home/user/.ssh/id_rsa")
            )
            mock_executor.execute_command.return_value = Mock(
                success=True, stdout="logs", stderr="", exit_code=0
            )

            # Execute with custom timeout
            LogViewer.get_system_logs(vm_name="test-vm", resource_group="test-rg", timeout=60)

            # Verify timeout was passed
            call_args = mock_executor.execute_command.call_args
            assert call_args[1]["timeout"] == 60
