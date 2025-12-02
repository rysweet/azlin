"""Unit tests for HealthMonitor (60% of test pyramid).

Tests health checking logic with mocked Azure API and SSH.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from azlin.lifecycle.health_monitor import (
    HealthMonitor,
    HealthStatus,
    VMState,
    VMMetrics,
    HealthCheckError,
)


class TestHealthMonitor:
    """Test HealthMonitor health checking operations."""

    @pytest.fixture
    def monitor(self):
        """Create HealthMonitor instance."""
        return HealthMonitor()

    @pytest.fixture
    def mock_azure_client(self, monitor):
        """Mock Azure SDK client."""
        mock_client = Mock()
        monitor._azure_client = mock_client
        return mock_client

    @pytest.fixture
    def mock_ssh_client(self, monitor):
        """Mock SSH client."""
        mock_client = Mock()
        monitor._ssh_client = mock_client
        return mock_client

    def test_check_vm_health_running_and_reachable(self, monitor, mock_azure_client, mock_ssh_client):
        """Test health check for running VM with SSH connectivity."""
        mock_azure_client.get_vm_state.return_value = "Running"
        mock_ssh_client.check_connectivity.return_value = True
        mock_ssh_client.get_metrics.return_value = VMMetrics(
            cpu_percent=45.2,
            memory_percent=60.5,
            disk_percent=35.0
        )

        health = monitor.check_vm_health("test-vm")

        assert health.vm_name == "test-vm"
        assert health.state == VMState.RUNNING
        assert health.ssh_reachable is True
        assert health.ssh_failures == 0
        assert health.metrics is not None
        assert health.metrics.cpu_percent == 45.2

    def test_check_vm_health_running_ssh_unreachable(self, monitor, mock_azure_client, mock_ssh_client):
        """Test health check for running VM without SSH connectivity."""
        mock_azure_client.get_vm_state.return_value = "Running"
        mock_ssh_client.check_connectivity.return_value = False

        health = monitor.check_vm_health("test-vm")

        assert health.state == VMState.RUNNING
        assert health.ssh_reachable is False
        assert health.ssh_failures == 1  # Incremented
        assert health.metrics is None

    def test_check_vm_health_stopped(self, monitor, mock_azure_client, mock_ssh_client):
        """Test health check for stopped VM."""
        mock_azure_client.get_vm_state.return_value = "Stopped"

        health = monitor.check_vm_health("test-vm")

        assert health.state == VMState.STOPPED
        assert health.ssh_reachable is False
        mock_ssh_client.check_connectivity.assert_not_called()

    def test_check_vm_health_deallocated(self, monitor, mock_azure_client):
        """Test health check for deallocated VM."""
        mock_azure_client.get_vm_state.return_value = "Deallocated"

        health = monitor.check_vm_health("test-vm")

        assert health.state == VMState.DEALLOCATED
        assert health.ssh_reachable is False

    def test_ssh_failure_counter_increments(self, monitor, mock_azure_client, mock_ssh_client):
        """Test SSH failure counter increments on consecutive failures."""
        mock_azure_client.get_vm_state.return_value = "Running"
        mock_ssh_client.check_connectivity.return_value = False

        health1 = monitor.check_vm_health("test-vm")
        health2 = monitor.check_vm_health("test-vm")
        health3 = monitor.check_vm_health("test-vm")

        assert health1.ssh_failures == 1
        assert health2.ssh_failures == 2
        assert health3.ssh_failures == 3

    def test_ssh_failure_counter_resets_on_success(self, monitor, mock_azure_client, mock_ssh_client):
        """Test SSH failure counter resets after successful check."""
        mock_azure_client.get_vm_state.return_value = "Running"

        # Fail twice
        mock_ssh_client.check_connectivity.return_value = False
        monitor.check_vm_health("test-vm")
        monitor.check_vm_health("test-vm")

        # Then succeed
        mock_ssh_client.check_connectivity.return_value = True
        mock_ssh_client.get_metrics.return_value = VMMetrics(50.0, 60.0, 40.0)
        health = monitor.check_vm_health("test-vm")

        assert health.ssh_failures == 0

    def test_get_vm_state_with_invalid_vm(self, monitor, mock_azure_client):
        """Test getting state for non-existent VM raises error."""
        mock_azure_client.get_vm_state.side_effect = Exception("VM not found")

        with pytest.raises(HealthCheckError, match="VM not found"):
            monitor.get_vm_state("nonexistent-vm")

    def test_check_ssh_connectivity_with_timeout(self, monitor, mock_ssh_client):
        """Test SSH connectivity check respects timeout."""
        mock_ssh_client.check_connectivity.side_effect = TimeoutError("Connection timed out")

        result = monitor.check_ssh_connectivity("test-vm", timeout=5)

        assert result is False
        mock_ssh_client.check_connectivity.assert_called_once()

    def test_get_metrics_returns_none_on_ssh_failure(self, monitor, mock_ssh_client):
        """Test metrics collection returns None when SSH fails."""
        mock_ssh_client.get_metrics.side_effect = Exception("SSH connection failed")

        metrics = monitor.get_metrics("test-vm")

        assert metrics is None

    def test_health_check_last_check_timestamp(self, monitor, mock_azure_client, mock_ssh_client):
        """Test health status includes last check timestamp."""
        mock_azure_client.get_vm_state.return_value = "Running"
        mock_ssh_client.check_connectivity.return_value = True
        mock_ssh_client.get_metrics.return_value = VMMetrics(50.0, 60.0, 40.0)

        before = datetime.utcnow()
        health = monitor.check_vm_health("test-vm")
        after = datetime.utcnow()

        assert before <= health.last_check <= after

    def test_multiple_vms_tracked_independently(self, monitor, mock_azure_client, mock_ssh_client):
        """Test multiple VMs tracked with independent failure counters."""
        mock_azure_client.get_vm_state.return_value = "Running"

        # VM1 fails SSH
        mock_ssh_client.check_connectivity.return_value = False
        health1 = monitor.check_vm_health("vm1")

        # VM2 succeeds SSH
        mock_ssh_client.check_connectivity.return_value = True
        mock_ssh_client.get_metrics.return_value = VMMetrics(50.0, 60.0, 40.0)
        health2 = monitor.check_vm_health("vm2")

        assert health1.ssh_failures == 1
        assert health2.ssh_failures == 0
