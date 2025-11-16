"""Tests for ConditionalExecutor and VMMetrics.

Following TDD pyramid pattern:
- Unit tests for condition parsing and evaluation
- Integration tests for metrics collection
- E2E tests for filtering workflow
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from azlin.batch_executor import (
    BatchExecutorError,
    ConditionalExecutor,
    MetricsCollector,
    VMMetrics,
)
from azlin.modules.ssh_connector import SSHConfig
from azlin.vm_manager import VMInfo


class TestVMMetrics:
    """Unit tests for VMMetrics condition evaluation."""

    def test_idle_condition_met(self):
        """Test idle condition when VM is idle."""
        metrics = VMMetrics(
            vm_name="test-vm",
            load_avg=(0.5, 0.6, 0.7),
            cpu_percent=10.0,
            memory_percent=50.0,
            is_idle=True,
            success=True,
        )

        assert metrics.meets_condition("idle") is True

    def test_idle_condition_not_met(self):
        """Test idle condition when VM is not idle."""
        metrics = VMMetrics(
            vm_name="test-vm",
            load_avg=(2.0, 2.1, 2.2),
            cpu_percent=80.0,
            memory_percent=70.0,
            is_idle=False,
            success=True,
        )

        assert metrics.meets_condition("idle") is False

    def test_cpu_condition_met_less_than(self):
        """Test CPU condition with < operator."""
        metrics = VMMetrics(
            vm_name="test-vm",
            load_avg=(0.5, 0.6, 0.7),
            cpu_percent=30.0,
            memory_percent=50.0,
            is_idle=False,
            success=True,
        )

        assert metrics.meets_condition("cpu<50") is True

    def test_cpu_condition_not_met(self):
        """Test CPU condition when threshold exceeded."""
        metrics = VMMetrics(
            vm_name="test-vm",
            load_avg=(0.5, 0.6, 0.7),
            cpu_percent=60.0,
            memory_percent=50.0,
            is_idle=False,
            success=True,
        )

        assert metrics.meets_condition("cpu<50") is False

    def test_cpu_condition_below_format(self):
        """Test CPU condition with 'below' format."""
        metrics = VMMetrics(
            vm_name="test-vm",
            load_avg=(0.5, 0.6, 0.7),
            cpu_percent=40.0,
            memory_percent=50.0,
            is_idle=False,
            success=True,
        )

        assert metrics.meets_condition("cpu-below-50") is True

    def test_memory_condition_met(self):
        """Test memory condition when below threshold."""
        metrics = VMMetrics(
            vm_name="test-vm",
            load_avg=(0.5, 0.6, 0.7),
            cpu_percent=30.0,
            memory_percent=60.0,
            is_idle=False,
            success=True,
        )

        assert metrics.meets_condition("mem<80") is True
        assert metrics.meets_condition("memory-below-80") is True

    def test_condition_with_no_metrics(self):
        """Test condition evaluation when metrics collection failed."""
        metrics = VMMetrics(
            vm_name="test-vm",
            load_avg=None,
            cpu_percent=None,
            memory_percent=None,
            is_idle=False,
            success=False,
            error="Connection failed",
        )

        assert metrics.meets_condition("idle") is False
        assert metrics.meets_condition("cpu<50") is False

    def test_invalid_condition_format(self):
        """Test that invalid condition raises error."""
        metrics = VMMetrics(
            vm_name="test-vm",
            load_avg=(0.5, 0.6, 0.7),
            cpu_percent=30.0,
            memory_percent=50.0,
            is_idle=False,
            success=True,
        )

        with pytest.raises(BatchExecutorError, match="Invalid CPU condition"):
            metrics.meets_condition("cpuinvalid")

    def test_unknown_condition(self):
        """Test that unknown condition raises error."""
        metrics = VMMetrics(
            vm_name="test-vm",
            load_avg=(0.5, 0.6, 0.7),
            cpu_percent=30.0,
            memory_percent=50.0,
            is_idle=False,
            success=True,
        )

        with pytest.raises(BatchExecutorError, match="Unknown condition"):
            metrics.meets_condition("unknown")


class TestMetricsCollector:
    """Integration tests for metrics collection."""

    @patch("azlin.batch_executor.RemoteExecutor.execute_command")
    def test_collect_metrics_success(self, mock_execute):
        """Test successful metrics collection."""
        # Mock successful command execution
        mock_result = Mock()
        mock_result.success = True
        mock_result.stdout = "0.5 0.6 0.7\n25.0\n60.0\nfalse"
        mock_result.stderr = ""
        mock_execute.return_value = mock_result

        vm = Mock(spec=VMInfo)
        vm.name = "test-vm"

        ssh_config = SSHConfig(host="10.0.0.1", user="azureuser", key_path="/tmp/key")

        metrics = MetricsCollector.collect_metrics(vm, ssh_config)

        assert metrics.success is True
        assert metrics.vm_name == "test-vm"
        assert metrics.load_avg == (0.5, 0.6, 0.7)
        assert metrics.cpu_percent == 25.0
        assert metrics.memory_percent == 60.0
        assert metrics.is_idle is False

    @patch("azlin.batch_executor.RemoteExecutor.execute_command")
    def test_collect_metrics_idle_vm(self, mock_execute):
        """Test metrics collection for idle VM."""
        mock_result = Mock()
        mock_result.success = True
        mock_result.stdout = "0.1 0.2 0.3\n5.0\n30.0\ntrue"
        mock_result.stderr = ""
        mock_execute.return_value = mock_result

        vm = Mock(spec=VMInfo)
        vm.name = "idle-vm"

        ssh_config = SSHConfig(host="10.0.0.2", user="azureuser", key_path="/tmp/key")

        metrics = MetricsCollector.collect_metrics(vm, ssh_config)

        assert metrics.success is True
        assert metrics.is_idle is True
        assert metrics.cpu_percent == 5.0

    @patch("azlin.batch_executor.RemoteExecutor.execute_command")
    def test_collect_metrics_failure(self, mock_execute):
        """Test metrics collection failure."""
        mock_result = Mock()
        mock_result.success = False
        mock_result.stderr = "SSH connection failed"
        mock_execute.return_value = mock_result

        vm = Mock(spec=VMInfo)
        vm.name = "failed-vm"

        ssh_config = SSHConfig(host="10.0.0.3", user="azureuser", key_path="/tmp/key")

        metrics = MetricsCollector.collect_metrics(vm, ssh_config)

        assert metrics.success is False
        assert metrics.vm_name == "failed-vm"
        assert metrics.error is not None
        assert "failed" in metrics.error.lower()

    @patch("azlin.batch_executor.RemoteExecutor.execute_command")
    def test_collect_metrics_incomplete_output(self, mock_execute):
        """Test handling of incomplete metrics output."""
        mock_result = Mock()
        mock_result.success = True
        mock_result.stdout = "0.5 0.6\n"  # Incomplete output
        mock_result.stderr = ""
        mock_execute.return_value = mock_result

        vm = Mock(spec=VMInfo)
        vm.name = "incomplete-vm"

        ssh_config = SSHConfig(host="10.0.0.4", user="azureuser", key_path="/tmp/key")

        metrics = MetricsCollector.collect_metrics(vm, ssh_config)

        assert metrics.success is False
        assert "Incomplete" in metrics.error


class TestConditionalExecutor:
    """Integration tests for conditional VM filtering."""

    @patch("azlin.batch_executor.SSHKeyManager.ensure_key_exists")
    @patch("azlin.batch_executor.MetricsCollector.collect_metrics")
    def test_filter_by_idle_condition(self, mock_collect, mock_keys):
        """Test filtering VMs by idle condition."""
        # Setup mocks
        mock_keys.return_value = Mock(private_path="/tmp/key")

        # Create test VMs
        vm1 = Mock(spec=VMInfo)
        vm1.name = "idle-vm"
        vm1.public_ip = "10.0.0.1"

        vm2 = Mock(spec=VMInfo)
        vm2.name = "busy-vm"
        vm2.public_ip = "10.0.0.2"

        vms = [vm1, vm2]

        # Mock metrics - vm1 is idle, vm2 is busy
        def mock_collect_side_effect(vm, ssh_config):
            if vm.name == "idle-vm":
                return VMMetrics(
                    vm_name="idle-vm",
                    load_avg=(0.1, 0.2, 0.3),
                    cpu_percent=5.0,
                    memory_percent=30.0,
                    is_idle=True,
                    success=True,
                )
            else:
                return VMMetrics(
                    vm_name="busy-vm",
                    load_avg=(2.0, 2.1, 2.2),
                    cpu_percent=80.0,
                    memory_percent=70.0,
                    is_idle=False,
                    success=True,
                )

        mock_collect.side_effect = mock_collect_side_effect

        # Execute filtering
        executor = ConditionalExecutor(max_workers=2)
        filtered_vms, metrics = executor.filter_by_condition(vms, "idle", "test-rg")

        # Verify results
        assert len(filtered_vms) == 1
        assert filtered_vms[0].name == "idle-vm"
        assert "idle-vm" in metrics
        assert "busy-vm" in metrics

    @patch("azlin.batch_executor.SSHKeyManager.ensure_key_exists")
    @patch("azlin.batch_executor.MetricsCollector.collect_metrics")
    def test_filter_by_cpu_condition(self, mock_collect, mock_keys):
        """Test filtering VMs by CPU condition."""
        mock_keys.return_value = Mock(private_path="/tmp/key")

        vm1 = Mock(spec=VMInfo)
        vm1.name = "low-cpu"
        vm1.public_ip = "10.0.0.1"

        vm2 = Mock(spec=VMInfo)
        vm2.name = "high-cpu"
        vm2.public_ip = "10.0.0.2"

        vms = [vm1, vm2]

        def mock_collect_side_effect(vm, ssh_config):
            if vm.name == "low-cpu":
                return VMMetrics(
                    vm_name="low-cpu",
                    load_avg=(0.5, 0.6, 0.7),
                    cpu_percent=30.0,
                    memory_percent=50.0,
                    is_idle=False,
                    success=True,
                )
            else:
                return VMMetrics(
                    vm_name="high-cpu",
                    load_avg=(3.0, 3.1, 3.2),
                    cpu_percent=90.0,
                    memory_percent=80.0,
                    is_idle=False,
                    success=True,
                )

        mock_collect.side_effect = mock_collect_side_effect

        executor = ConditionalExecutor(max_workers=2)
        filtered_vms, metrics = executor.filter_by_condition(vms, "cpu<50", "test-rg")

        assert len(filtered_vms) == 1
        assert filtered_vms[0].name == "low-cpu"

    @patch("azlin.batch_executor.SSHKeyManager.ensure_key_exists")
    def test_filter_no_matching_vms(self, mock_keys):
        """Test filtering when no VMs match condition."""
        mock_keys.return_value = Mock(private_path="/tmp/key")

        executor = ConditionalExecutor(max_workers=2)
        filtered_vms, metrics = executor.filter_by_condition([], "idle", "test-rg")

        assert len(filtered_vms) == 0
        assert len(metrics) == 0
