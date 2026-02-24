"""Unit tests for batch_executor module.

Tests the parallel execution engine for multi-VM operations with mocked
dependencies. Covers TagFilter, BatchResult, BatchSelector, BatchExecutor,
VMMetrics, MetricsCollector, and ConditionalExecutor.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.batch_executor import (
    BatchExecutor,
    BatchExecutorError,
    BatchOperationResult,
    BatchResult,
    BatchSelector,
    MetricsCollector,
    TagFilter,
    VMMetrics,
)
from azlin.modules.ssh_connector import SSHConfig
from azlin.remote_exec import RemoteResult
from azlin.vm_manager import VMInfo

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_vm(
    name: str,
    power_state: str = "VM running",
    public_ip: str | None = "10.0.0.1",
    tags: dict | None = None,
) -> VMInfo:
    """Helper to create VMInfo instances for testing."""
    return VMInfo(
        name=name,
        resource_group="rg-test",
        location="eastus",
        power_state=power_state,
        public_ip=public_ip,
        tags=tags,
    )


@pytest.fixture
def running_vms():
    return [
        _make_vm("vm1", public_ip="10.0.0.1", tags={"env": "dev", "team": "alpha"}),
        _make_vm("vm2", public_ip="10.0.0.2", tags={"env": "prod", "team": "alpha"}),
        _make_vm("vm3", public_ip="10.0.0.3", tags={"env": "dev", "team": "beta"}),
    ]


@pytest.fixture
def ssh_config():
    return SSHConfig(
        host="10.0.0.1", user="azureuser", key_path=Path("/home/azureuser/.ssh/id_rsa")
    )


# ---------------------------------------------------------------------------
# TagFilter
# ---------------------------------------------------------------------------


class TestTagFilter:
    def test_parse_valid(self):
        tag = TagFilter.parse("env=prod")
        assert tag.key == "env"
        assert tag.value == "prod"

    def test_parse_value_with_equals(self):
        """Value can contain '=' characters."""
        tag = TagFilter.parse("config=key=value")
        assert tag.key == "config"
        assert tag.value == "key=value"

    def test_parse_strips_whitespace(self):
        tag = TagFilter.parse("  env  =  dev  ")
        assert tag.key == "env"
        assert tag.value == "dev"

    def test_parse_no_equals_raises(self):
        with pytest.raises(BatchExecutorError, match="Invalid tag format"):
            TagFilter.parse("invalid")

    def test_parse_empty_key_raises(self):
        with pytest.raises(BatchExecutorError, match="Key cannot be empty"):
            TagFilter.parse("=value")

    def test_matches_vm_with_tag(self):
        vm = _make_vm("vm1", tags={"env": "dev"})
        tag = TagFilter(key="env", value="dev")
        assert tag.matches(vm) is True

    def test_no_match_wrong_value(self):
        vm = _make_vm("vm1", tags={"env": "prod"})
        tag = TagFilter(key="env", value="dev")
        assert tag.matches(vm) is False

    def test_no_match_no_tags(self):
        vm = _make_vm("vm1", tags=None)
        tag = TagFilter(key="env", value="dev")
        assert tag.matches(vm) is False


# ---------------------------------------------------------------------------
# BatchResult
# ---------------------------------------------------------------------------


class TestBatchResult:
    def test_properties(self):
        results = [
            BatchOperationResult(vm_name="vm1", success=True, message="ok"),
            BatchOperationResult(vm_name="vm2", success=False, message="fail"),
            BatchOperationResult(vm_name="vm3", success=True, message="ok"),
        ]
        batch = BatchResult(results)

        assert batch.total == 3
        assert batch.succeeded == 2
        assert batch.failed == 1
        assert batch.all_succeeded is False

    def test_all_succeeded_true(self):
        results = [BatchOperationResult(vm_name="vm1", success=True, message="ok")]
        assert BatchResult(results).all_succeeded is True

    def test_all_succeeded_empty(self):
        assert BatchResult([]).all_succeeded is True

    def test_get_failures_and_successes(self):
        results = [
            BatchOperationResult(vm_name="vm1", success=True, message="ok"),
            BatchOperationResult(vm_name="vm2", success=False, message="fail"),
        ]
        batch = BatchResult(results)

        assert len(batch.get_failures()) == 1
        assert batch.get_failures()[0].vm_name == "vm2"
        assert len(batch.get_successes()) == 1

    def test_format_summary(self):
        results = [
            BatchOperationResult(vm_name="vm1", success=True, message="ok"),
            BatchOperationResult(vm_name="vm2", success=False, message="fail"),
        ]
        summary = BatchResult(results).format_summary()
        assert "Total: 2" in summary
        assert "Succeeded: 1" in summary
        assert "Failed: 1" in summary


# ---------------------------------------------------------------------------
# BatchSelector
# ---------------------------------------------------------------------------


class TestBatchSelector:
    def test_select_by_tag(self, running_vms):
        selected = BatchSelector.select_by_tag(running_vms, "env=dev")
        assert len(selected) == 2
        names = {vm.name for vm in selected}
        assert names == {"vm1", "vm3"}

    def test_select_by_pattern(self, running_vms):
        selected = BatchSelector.select_by_pattern(running_vms, "vm[12]")
        assert len(selected) == 2

    def test_select_by_pattern_wildcard(self, running_vms):
        selected = BatchSelector.select_by_pattern(running_vms, "vm*")
        assert len(selected) == 3

    def test_select_all(self, running_vms):
        assert BatchSelector.select_all(running_vms) == running_vms

    def test_select_running_only(self):
        vms = [
            _make_vm("vm1", power_state="VM running"),
            _make_vm("vm2", power_state="VM deallocated"),
            _make_vm("vm3", power_state="VM running"),
        ]
        selected = BatchSelector.select_running_only(vms)
        assert len(selected) == 2


# ---------------------------------------------------------------------------
# BatchExecutor - stop / start / command / sync
# ---------------------------------------------------------------------------


class TestBatchExecutor:
    def test_execute_stop_empty_list(self):
        executor = BatchExecutor(max_workers=2)
        results = executor.execute_stop([], resource_group="rg")
        assert results == []

    @patch("azlin.batch_executor.VMLifecycleController")
    def test_execute_stop_success(self, mock_lifecycle, running_vms):
        mock_lifecycle.stop_vm.return_value = MagicMock(success=True, message="Stopped")

        executor = BatchExecutor(max_workers=2)
        results = executor.execute_stop(running_vms, resource_group="rg")

        assert len(results) == 3
        assert all(r.success for r in results)

    @patch("azlin.batch_executor.VMLifecycleController")
    def test_execute_stop_one_failure(self, mock_lifecycle, running_vms):
        """One VM stop failure should not prevent others from completing."""
        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs.get("vm_name") == "vm2":
                raise Exception("Azure API error")
            return MagicMock(success=True, message="Stopped")

        mock_lifecycle.stop_vm.side_effect = side_effect

        executor = BatchExecutor(max_workers=2)
        results = executor.execute_stop(running_vms, resource_group="rg")

        assert len(results) == 3
        failures = [r for r in results if not r.success]
        assert len(failures) == 1
        assert "Azure API error" in failures[0].message

    @patch("azlin.batch_executor.VMLifecycleController")
    def test_execute_stop_with_progress_callback(self, mock_lifecycle, running_vms):
        mock_lifecycle.stop_vm.return_value = MagicMock(success=True, message="Stopped")

        messages = []
        executor = BatchExecutor(max_workers=1)
        executor.execute_stop(running_vms, resource_group="rg", progress_callback=messages.append)

        # Should have at least one message per VM
        assert len(messages) >= 3

    @patch("azlin.batch_executor.VMLifecycleController")
    def test_execute_start_success(self, mock_lifecycle, running_vms):
        mock_lifecycle.start_vm.return_value = MagicMock(success=True, message="Started")

        executor = BatchExecutor(max_workers=2)
        results = executor.execute_start(running_vms, resource_group="rg")

        assert len(results) == 3
        assert all(r.success for r in results)

    def test_execute_start_empty_list(self):
        executor = BatchExecutor(max_workers=2)
        assert executor.execute_start([], resource_group="rg") == []

    @patch("azlin.batch_executor.SSHKeyManager")
    @patch("azlin.batch_executor.RemoteExecutor")
    def test_execute_command_success(self, mock_remote, mock_keys, running_vms):
        mock_keys.ensure_key_exists.return_value = MagicMock(
            private_path=Path("/home/azureuser/.ssh/id_rsa")
        )
        mock_remote.execute_command.return_value = RemoteResult(
            vm_name="vm", success=True, stdout="hello\n", stderr="", exit_code=0
        )

        executor = BatchExecutor(max_workers=2)
        results = executor.execute_command(running_vms, "echo hello", resource_group="rg")

        assert len(results) == 3
        assert all(r.success for r in results)
        assert all("Exit code: 0" in r.message for r in results)

    @patch("azlin.batch_executor.SSHKeyManager")
    @patch("azlin.batch_executor.RemoteExecutor")
    def test_execute_command_vm_no_ip(self, mock_remote, mock_keys):
        """VM without public IP should fail gracefully."""
        mock_keys.ensure_key_exists.return_value = MagicMock(
            private_path=Path("/home/azureuser/.ssh/id_rsa")
        )
        vms = [_make_vm("vm-no-ip", public_ip=None)]

        executor = BatchExecutor(max_workers=1)
        results = executor.execute_command(vms, "echo hello", resource_group="rg")

        assert len(results) == 1
        assert results[0].success is False
        assert "no public ip" in results[0].message.lower()

    def test_execute_command_empty_list(self):
        executor = BatchExecutor(max_workers=2)
        assert executor.execute_command([], "echo", resource_group="rg") == []

    def test_execute_sync_empty_list(self):
        executor = BatchExecutor(max_workers=2)
        assert executor.execute_sync([], resource_group="rg") == []


# ---------------------------------------------------------------------------
# VMMetrics
# ---------------------------------------------------------------------------


class TestVMMetrics:
    def test_meets_condition_idle(self):
        m = VMMetrics(
            vm_name="vm1",
            load_avg=(0.1, 0.2, 0.3),
            cpu_percent=5.0,
            memory_percent=30.0,
            is_idle=True,
            success=True,
        )
        assert m.meets_condition("idle") is True

    def test_meets_condition_not_idle(self):
        m = VMMetrics(
            vm_name="vm1",
            load_avg=(0.1, 0.2, 0.3),
            cpu_percent=5.0,
            memory_percent=30.0,
            is_idle=False,
            success=True,
        )
        assert m.meets_condition("idle") is False

    def test_meets_condition_cpu_below(self):
        m = VMMetrics(
            vm_name="vm1",
            load_avg=None,
            cpu_percent=40.0,
            memory_percent=None,
            is_idle=False,
            success=True,
        )
        assert m.meets_condition("cpu<50") is True
        assert m.meets_condition("cpu<30") is False

    def test_meets_condition_memory_below(self):
        m = VMMetrics(
            vm_name="vm1",
            load_avg=None,
            cpu_percent=None,
            memory_percent=60.0,
            is_idle=False,
            success=True,
        )
        assert m.meets_condition("mem<80") is True
        assert m.meets_condition("mem<50") is False

    def test_meets_condition_failed_metrics(self):
        m = VMMetrics(
            vm_name="vm1",
            load_avg=None,
            cpu_percent=None,
            memory_percent=None,
            is_idle=False,
            success=False,
        )
        assert m.meets_condition("idle") is False

    def test_meets_condition_unknown_raises(self):
        m = VMMetrics(
            vm_name="vm1",
            load_avg=None,
            cpu_percent=None,
            memory_percent=None,
            is_idle=False,
            success=True,
        )
        with pytest.raises(BatchExecutorError, match="Unknown condition"):
            m.meets_condition("disk<90")

    def test_meets_condition_invalid_cpu_format_raises(self):
        m = VMMetrics(
            vm_name="vm1",
            load_avg=None,
            cpu_percent=50.0,
            memory_percent=None,
            is_idle=False,
            success=True,
        )
        with pytest.raises(BatchExecutorError, match="Invalid CPU condition"):
            m.meets_condition("cpu>50")

    def test_meets_condition_cpu_none(self):
        m = VMMetrics(
            vm_name="vm1",
            load_avg=None,
            cpu_percent=None,
            memory_percent=None,
            is_idle=False,
            success=True,
        )
        assert m.meets_condition("cpu<50") is False


# ---------------------------------------------------------------------------
# MetricsCollector
# ---------------------------------------------------------------------------


class TestMetricsCollector:
    @patch("azlin.batch_executor.RemoteExecutor")
    def test_collect_metrics_success(self, mock_remote, ssh_config):
        mock_remote.execute_command.return_value = RemoteResult(
            vm_name="vm1",
            success=True,
            stdout="0.10 0.20 0.30\n15.5\n42.3\nfalse\n",
            stderr="",
            exit_code=0,
        )

        vm = _make_vm("vm1")
        metrics = MetricsCollector.collect_metrics(vm, ssh_config)

        assert metrics.success is True
        assert metrics.load_avg == (0.10, 0.20, 0.30)
        assert metrics.cpu_percent == 15.5
        assert metrics.memory_percent == 42.3
        assert metrics.is_idle is False

    @patch("azlin.batch_executor.RemoteExecutor")
    def test_collect_metrics_ssh_failure(self, mock_remote, ssh_config):
        mock_remote.execute_command.return_value = RemoteResult(
            vm_name="vm1", success=False, stdout="", stderr="Connection refused", exit_code=255
        )

        vm = _make_vm("vm1")
        metrics = MetricsCollector.collect_metrics(vm, ssh_config)

        assert metrics.success is False
        assert metrics.error is not None

    @patch("azlin.batch_executor.RemoteExecutor")
    def test_collect_metrics_incomplete_output(self, mock_remote, ssh_config):
        mock_remote.execute_command.return_value = RemoteResult(
            vm_name="vm1", success=True, stdout="0.10 0.20\n", stderr="", exit_code=0
        )

        vm = _make_vm("vm1")
        metrics = MetricsCollector.collect_metrics(vm, ssh_config)

        assert metrics.success is False
        assert "Incomplete" in metrics.error

    @patch("azlin.batch_executor.RemoteExecutor")
    def test_collect_metrics_exception(self, mock_remote, ssh_config):
        mock_remote.execute_command.side_effect = Exception("SSH broken")

        vm = _make_vm("vm1")
        metrics = MetricsCollector.collect_metrics(vm, ssh_config)

        assert metrics.success is False
        assert "SSH broken" in metrics.error
