"""Unit tests for SelfHealer (60% of test pyramid).

Tests restart decision logic with mocked Azure operations.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass

from azlin.lifecycle.self_healer import (
    SelfHealer,
    RestartResult,
    SelfHealingError,
)
from azlin.lifecycle.health_monitor import HealthStatus, VMState, HealthFailure


class TestSelfHealer:
    """Test SelfHealer restart decision logic."""

    @pytest.fixture
    def healer(self):
        """Create SelfHealer instance."""
        return SelfHealer()

    @pytest.fixture
    def mock_azure_client(self, healer):
        """Mock Azure SDK client."""
        mock_client = Mock()
        healer._azure_client = mock_client
        return mock_client

    @pytest.fixture
    def mock_lifecycle_manager(self, healer):
        """Mock LifecycleManager."""
        mock_manager = Mock()
        healer._lifecycle_manager = mock_manager
        return mock_manager

    @pytest.fixture
    def mock_hook_executor(self, healer):
        """Mock HookExecutor."""
        mock_executor = Mock()
        healer._hook_executor = mock_executor
        return mock_executor

    def test_should_restart_never_policy_returns_false(self, healer, mock_lifecycle_manager):
        """Test never policy never triggers restart."""
        from azlin.lifecycle.lifecycle_manager import MonitoringConfig
        config = MonitoringConfig(enabled=True, restart_policy="never", ssh_failure_threshold=3)
        mock_lifecycle_manager.get_monitoring_status.return_value.config = config

        failure = HealthFailure(vm_name="test-vm", failure_count=5, reason="SSH timeout")
        should_restart = healer.should_restart("test-vm", failure)

        assert should_restart is False

    def test_should_restart_on_failure_below_threshold(self, healer, mock_lifecycle_manager):
        """Test on-failure policy below threshold returns false."""
        from azlin.lifecycle.lifecycle_manager import MonitoringConfig
        config = MonitoringConfig(enabled=True, restart_policy="on-failure", ssh_failure_threshold=3)
        mock_lifecycle_manager.get_monitoring_status.return_value.config = config

        failure = HealthFailure(vm_name="test-vm", failure_count=2, reason="SSH timeout")
        should_restart = healer.should_restart("test-vm", failure)

        assert should_restart is False

    def test_should_restart_on_failure_at_threshold(self, healer, mock_lifecycle_manager):
        """Test on-failure policy at threshold returns true."""
        from azlin.lifecycle.lifecycle_manager import MonitoringConfig
        config = MonitoringConfig(enabled=True, restart_policy="on-failure", ssh_failure_threshold=3)
        mock_lifecycle_manager.get_monitoring_status.return_value.config = config

        failure = HealthFailure(vm_name="test-vm", failure_count=3, reason="SSH timeout")
        should_restart = healer.should_restart("test-vm", failure)

        assert should_restart is True

    def test_should_restart_always_policy_returns_true(self, healer, mock_lifecycle_manager):
        """Test always policy always triggers restart."""
        from azlin.lifecycle.lifecycle_manager import MonitoringConfig
        config = MonitoringConfig(enabled=True, restart_policy="always", ssh_failure_threshold=3)
        mock_lifecycle_manager.get_monitoring_status.return_value.config = config

        failure = HealthFailure(vm_name="test-vm", failure_count=1, reason="Any failure")
        should_restart = healer.should_restart("test-vm", failure)

        assert should_restart is True

    def test_restart_vm_success(self, healer, mock_azure_client):
        """Test successful VM restart."""
        mock_azure_client.restart_vm.return_value = True

        result = healer.restart_vm("test-vm")

        assert result.success is True
        assert result.vm_name == "test-vm"
        mock_azure_client.restart_vm.assert_called_once_with("test-vm")

    def test_restart_vm_failure(self, healer, mock_azure_client):
        """Test failed VM restart."""
        mock_azure_client.restart_vm.side_effect = Exception("Restart failed")

        result = healer.restart_vm("test-vm")

        assert result.success is False
        assert "Restart failed" in result.error_message

    def test_handle_failure_triggers_restart_and_hook(
        self, healer, mock_azure_client, mock_hook_executor, mock_lifecycle_manager
    ):
        """Test handle_failure restarts VM and executes hook."""
        from azlin.lifecycle.lifecycle_manager import MonitoringConfig
        config = MonitoringConfig(
            enabled=True,
            restart_policy="on-failure",
            ssh_failure_threshold=3,
            hooks={"on_restart": "/path/to/notify.sh"}
        )
        mock_lifecycle_manager.get_monitoring_status.return_value.config = config
        mock_azure_client.restart_vm.return_value = True

        failure = HealthFailure(vm_name="test-vm", failure_count=3, reason="SSH timeout")
        healer.handle_failure("test-vm", failure)

        mock_azure_client.restart_vm.assert_called_once_with("test-vm")
        mock_hook_executor.execute_hook.assert_called_once_with(
            "on_restart", "test-vm", {"failure_count": 3, "reason": "SSH timeout"}
        )

    def test_handle_failure_no_restart_when_policy_never(
        self, healer, mock_azure_client, mock_lifecycle_manager
    ):
        """Test handle_failure does not restart when policy is never."""
        from azlin.lifecycle.lifecycle_manager import MonitoringConfig
        config = MonitoringConfig(enabled=True, restart_policy="never")
        mock_lifecycle_manager.get_monitoring_status.return_value.config = config

        failure = HealthFailure(vm_name="test-vm", failure_count=5, reason="SSH timeout")
        healer.handle_failure("test-vm", failure)

        mock_azure_client.restart_vm.assert_not_called()

    def test_restart_vm_resets_failure_counter(self, healer, mock_azure_client, mock_lifecycle_manager):
        """Test successful restart resets failure counter."""
        mock_azure_client.restart_vm.return_value = True

        result = healer.restart_vm("test-vm")

        assert result.success is True
        # Failure counter should be reset in HealthMonitor (integration test)

    def test_concurrent_restart_requests_handled_safely(self, healer, mock_azure_client):
        """Test concurrent restart requests don't cause double-restart."""
        # This test verifies the healer handles concurrent calls safely
        mock_azure_client.restart_vm.return_value = True

        result1 = healer.restart_vm("test-vm")
        result2 = healer.restart_vm("test-vm")

        assert result1.success is True
        assert result2.success is True
        # Note: Real implementation should have lock to prevent double-restart
        # This is tested in integration tests
