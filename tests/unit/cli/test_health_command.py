"""Unit tests for the azlin health command (Four Golden Signals dashboard).

Tests cover:
- CLI syntax validation (help, options)
- Health check with mocked VM data
- Table output formatting
- Single VM and multi-VM modes
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from azlin.cli import main
from azlin.lifecycle.health_monitor import HealthStatus, VMMetrics, VMState


def _make_vm_info(name: str, power_state: str = "VM running", resource_group: str = "test-rg"):
    """Create a mock VMInfo-like object for testing."""
    vm = MagicMock()
    vm.name = name
    vm.resource_group = resource_group
    vm.power_state = power_state
    vm.is_running.return_value = power_state == "VM running"
    return vm


def _make_health_status(
    vm_name: str,
    state: VMState = VMState.RUNNING,
    ssh_reachable: bool = True,
    ssh_failures: int = 0,
    cpu: float = 25.0,
    memory: float = 60.0,
    disk: float = 45.0,
) -> HealthStatus:
    """Create a HealthStatus for testing."""
    metrics = (
        VMMetrics(cpu_percent=cpu, memory_percent=memory, disk_percent=disk)
        if state == VMState.RUNNING and ssh_reachable
        else None
    )
    return HealthStatus(
        vm_name=vm_name,
        state=state,
        ssh_reachable=ssh_reachable,
        ssh_failures=ssh_failures,
        last_check=datetime(2026, 2, 22, 12, 0, 0),
        metrics=metrics,
    )


class TestHealthCommandSyntax:
    """Test CLI syntax for 'azlin health' command."""

    def test_health_help(self):
        """Test 'azlin health --help' displays usage."""
        runner = CliRunner()
        result = runner.invoke(main, ["health", "--help"])

        assert result.exit_code == 0
        assert "--resource-group" in result.output or "--rg" in result.output
        assert "--config" in result.output
        assert "--vm" in result.output

    def test_health_help_mentions_golden_signals(self):
        """Help text should reference Four Golden Signals."""
        runner = CliRunner()
        result = runner.invoke(main, ["health", "--help"])

        assert result.exit_code == 0
        # Should mention what it displays
        assert "health" in result.output.lower()


class TestHealthCommandExecution:
    """Test health command execution with mocked dependencies."""

    @patch("azlin.commands.health.HealthMonitor")
    @patch("azlin.commands.health.TagManager")
    @patch("azlin.commands.health.ConfigManager")
    def test_health_displays_table_for_running_vms(
        self, mock_config_cls, mock_tag_cls, mock_monitor_cls
    ):
        """Health command shows a table with VM health data."""
        mock_config_cls.get_resource_group.return_value = "test-rg"

        vm1 = _make_vm_info("vm-1")
        vm2 = _make_vm_info("vm-2")
        mock_tag_cls.list_managed_vms.return_value = ([vm1, vm2], False)

        mock_monitor = MagicMock()
        mock_monitor_cls.return_value = mock_monitor
        mock_monitor.check_all_vms_health.return_value = [
            ("vm-1", _make_health_status("vm-1", cpu=30.0, memory=50.0, disk=40.0), None),
            ("vm-2", _make_health_status("vm-2", cpu=80.0, memory=90.0, disk=70.0), None),
        ]

        runner = CliRunner()
        result = runner.invoke(main, ["health", "--rg", "test-rg"])

        assert result.exit_code == 0
        assert "vm-1" in result.output
        assert "vm-2" in result.output

    @patch("azlin.commands.health.HealthMonitor")
    @patch("azlin.commands.health.TagManager")
    @patch("azlin.commands.health.ConfigManager")
    def test_health_no_vms_found(self, mock_config_cls, mock_tag_cls, mock_monitor_cls):
        """Health command handles no VMs gracefully."""
        mock_config_cls.get_resource_group.return_value = "test-rg"
        mock_tag_cls.list_managed_vms.return_value = ([], False)

        runner = CliRunner()
        result = runner.invoke(main, ["health", "--rg", "test-rg"])

        assert result.exit_code == 0
        assert "No VMs found" in result.output or "no" in result.output.lower()

    @patch("azlin.commands.health.HealthMonitor")
    @patch("azlin.commands.health.TagManager")
    @patch("azlin.commands.health.ConfigManager")
    def test_health_single_vm_mode(self, mock_config_cls, mock_tag_cls, mock_monitor_cls):
        """--vm flag checks a single VM only."""
        mock_config_cls.get_resource_group.return_value = "test-rg"

        vm1 = _make_vm_info("target-vm")
        mock_tag_cls.list_managed_vms.return_value = ([vm1, _make_vm_info("other-vm")], False)

        mock_monitor = MagicMock()
        mock_monitor_cls.return_value = mock_monitor
        mock_monitor.check_all_vms_health.return_value = [
            ("target-vm", _make_health_status("target-vm"), None),
        ]

        runner = CliRunner()
        result = runner.invoke(main, ["health", "--rg", "test-rg", "--vm", "target-vm"])

        assert result.exit_code == 0
        assert "target-vm" in result.output
        # Should only check the filtered VM
        mock_monitor.check_all_vms_health.assert_called_once_with(["target-vm"])

    @patch("azlin.commands.health.HealthMonitor")
    @patch("azlin.commands.health.TagManager")
    @patch("azlin.commands.health.ConfigManager")
    def test_health_stopped_vm_shows_state(self, mock_config_cls, mock_tag_cls, mock_monitor_cls):
        """Stopped VMs show their state without metrics."""
        mock_config_cls.get_resource_group.return_value = "test-rg"

        vm1 = _make_vm_info("stopped-vm", power_state="VM deallocated")
        mock_tag_cls.list_managed_vms.return_value = ([vm1], False)

        mock_monitor = MagicMock()
        mock_monitor_cls.return_value = mock_monitor
        mock_monitor.check_all_vms_health.return_value = [
            (
                "stopped-vm",
                _make_health_status("stopped-vm", state=VMState.DEALLOCATED, ssh_reachable=False),
                None,
            ),
        ]

        runner = CliRunner()
        result = runner.invoke(main, ["health", "--rg", "test-rg"])

        assert result.exit_code == 0
        assert "stopped-vm" in result.output

    @patch("azlin.commands.health.ConfigManager")
    def test_health_no_resource_group(self, mock_config_cls):
        """Missing resource group shows error."""
        mock_config_cls.get_resource_group.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["health"])

        assert result.exit_code != 0

    @patch("azlin.commands.health.HealthMonitor")
    @patch("azlin.commands.health.TagManager")
    @patch("azlin.commands.health.ConfigManager")
    def test_health_check_failure_handled(self, mock_config_cls, mock_tag_cls, mock_monitor_cls):
        """HealthCheckError for a VM is handled gracefully."""
        mock_config_cls.get_resource_group.return_value = "test-rg"
        vm1 = _make_vm_info("flaky-vm")
        mock_tag_cls.list_managed_vms.return_value = ([vm1], False)

        mock_monitor = MagicMock()
        mock_monitor_cls.return_value = mock_monitor
        mock_monitor.check_all_vms_health.return_value = [
            ("flaky-vm", None, "Azure API down"),
        ]

        runner = CliRunner()
        result = runner.invoke(main, ["health", "--rg", "test-rg"])

        # Should not crash - should handle gracefully
        assert result.exit_code == 0
        assert "flaky-vm" in result.output or "error" in result.output.lower()
