"""Integration tests for VM lifecycle system (30% of test pyramid).

Tests full workflows with multiple components interacting.
"""

from unittest.mock import Mock, patch

import pytest

from azlin.lifecycle.health_monitor import HealthMonitor, VMState
from azlin.lifecycle.hook_executor import HookExecutor, HookType
from azlin.lifecycle.lifecycle_manager import LifecycleManager, MonitoringConfig
from azlin.lifecycle.self_healer import SelfHealer


class TestHealthWorkflow:
    """Test complete health check → failure → restart workflow."""

    @pytest.fixture
    def components(self, tmp_path):
        """Create integrated component stack."""
        config_path = tmp_path / "lifecycle-config.toml"
        with patch("azlin.lifecycle.lifecycle_manager.LIFECYCLE_CONFIG_PATH", config_path):
            manager = LifecycleManager()
            monitor = HealthMonitor()
            healer = SelfHealer()
            executor = HookExecutor()
            yield {
                "manager": manager,
                "monitor": monitor,
                "healer": healer,
                "executor": executor,
                "config_path": config_path,
            }

    @pytest.fixture
    def mock_azure(self, components):
        """Mock Azure client for integration tests."""
        mock_client = Mock()
        mock_client.get_vm_state.return_value = "Running"
        mock_client.restart_vm.return_value = True
        components["monitor"]._azure_client = mock_client
        components["healer"]._azure_client = mock_client
        return mock_client

    @pytest.fixture
    def mock_ssh(self, components):
        """Mock SSH client for integration tests."""
        mock_client = Mock()
        mock_client.check_connectivity.return_value = True
        components["monitor"]._ssh_client = mock_client
        return mock_client

    def test_enable_monitoring_and_check_health(self, components, mock_azure, mock_ssh):
        """Test enabling monitoring and performing health check."""
        manager = components["manager"]
        monitor = components["monitor"]

        # Enable monitoring
        config = MonitoringConfig(enabled=True, check_interval_seconds=60)
        manager.enable_monitoring("test-vm", config)

        # Perform health check
        health = monitor.check_vm_health("test-vm")

        assert health.vm_name == "test-vm"
        assert health.state == VMState.RUNNING
        assert health.ssh_reachable is True

    def test_ssh_failure_triggers_restart(self, components, mock_azure, mock_ssh):
        """Test SSH failures trigger automatic restart."""
        manager = components["manager"]
        monitor = components["monitor"]
        healer = components["healer"]

        # Enable monitoring with on-failure restart policy
        config = MonitoringConfig(
            enabled=True, restart_policy="on-failure", ssh_failure_threshold=3
        )
        manager.enable_monitoring("test-vm", config)

        # Simulate SSH failures
        mock_ssh.check_connectivity.return_value = False

        # First two failures don't trigger restart
        monitor.check_vm_health("test-vm")
        monitor.check_vm_health("test-vm")
        health = monitor.check_vm_health("test-vm")

        assert health.ssh_failures == 3

        # Healer should decide to restart
        from azlin.lifecycle.health_monitor import HealthFailure

        failure = HealthFailure(vm_name="test-vm", failure_count=3, reason="SSH connectivity lost")
        should_restart = healer.should_restart("test-vm", failure)
        assert should_restart is True

        # Execute restart
        result = healer.restart_vm("test-vm")
        assert result.success is True
        mock_azure.restart_vm.assert_called_once_with("test-vm")

    def test_hook_execution_on_failure(self, components, mock_azure, mock_ssh, tmp_path):
        """Test hook executes when failure occurs."""
        manager = components["manager"]
        executor = components["executor"]

        # Create hook script
        hook_script = tmp_path / "alert.sh"
        hook_script.write_text("#!/bin/bash\\necho 'Alert triggered'")
        hook_script.chmod(0o755)

        # Enable monitoring with hook
        config = MonitoringConfig(enabled=True, hooks={"on_failure": str(hook_script)})
        manager.enable_monitoring("test-vm", config)

        # Execute hook
        with patch("azlin.lifecycle.hook_executor.subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = Mock(
                returncode=0, stdout="Alert triggered", stderr=""
            )

            result = executor.execute_hook(HookType.ON_FAILURE, "test-vm", {"failure_count": 1})

            assert result.success is True
            assert "Alert triggered" in result.stdout

    def test_config_persistence_across_components(self, components):
        """Test configuration persists and is readable by all components."""
        manager1 = components["manager"]
        config_path = components["config_path"]

        # Enable monitoring with first manager
        config = MonitoringConfig(
            enabled=True, check_interval_seconds=90, restart_policy="on-failure"
        )
        manager1.enable_monitoring("test-vm", config)

        # Create new manager instance (simulates daemon reload)
        with patch("azlin.lifecycle.lifecycle_manager.LIFECYCLE_CONFIG_PATH", config_path):
            manager2 = LifecycleManager()
            status = manager2.get_monitoring_status("test-vm")

        assert status.enabled is True
        assert status.config.check_interval_seconds == 90
        assert status.config.restart_policy == "on-failure"

    def test_multiple_vms_monitored_independently(self, components, mock_azure, mock_ssh):
        """Test multiple VMs monitored with independent state."""
        manager = components["manager"]
        monitor = components["monitor"]

        # Enable monitoring for two VMs
        config1 = MonitoringConfig(enabled=True, restart_policy="never")
        config2 = MonitoringConfig(enabled=True, restart_policy="on-failure")
        manager.enable_monitoring("vm1", config1)
        manager.enable_monitoring("vm2", config2)

        # VM1 SSH fails
        mock_ssh.check_connectivity.return_value = False
        health1 = monitor.check_vm_health("vm1")

        # VM2 SSH succeeds
        mock_ssh.check_connectivity.return_value = True
        from azlin.lifecycle.health_monitor import VMMetrics

        mock_ssh.get_metrics.return_value = VMMetrics(50.0, 60.0, 40.0)
        health2 = monitor.check_vm_health("vm2")

        assert health1.ssh_failures == 1
        assert health2.ssh_failures == 0

        vms = manager.list_monitored_vms()
        assert len(vms) == 2


# Note: Daemon integration tests have been moved to test_daemon_integration.py
# which provides comprehensive unit, integration, and near-E2E testing for
# LifecycleDaemon and DaemonController with 79% coverage.
