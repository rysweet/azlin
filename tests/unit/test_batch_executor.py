"""Unit tests for batch_executor module.

This module tests batch operations on multiple VMs:
- VM selection by tags, patterns, and all
- Parallel execution
- Result aggregation
- Error handling
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from dataclasses import dataclass

from azlin.batch_executor import (
    BatchSelector,
    BatchExecutor,
    BatchResult,
    BatchOperationResult,
    BatchExecutorError,
    TagFilter,
)
from azlin.vm_manager import VMInfo


@pytest.fixture
def sample_vms():
    """Create sample VMs for testing."""
    return [
        VMInfo(
            name="azlin-dev-01",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.4",
            vm_size="Standard_D2s_v3",
            tags={"env": "dev", "team": "backend"}
        ),
        VMInfo(
            name="azlin-dev-02",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.5",
            vm_size="Standard_D2s_v3",
            tags={"env": "dev", "team": "frontend"}
        ),
        VMInfo(
            name="azlin-prod-01",
            resource_group="test-rg",
            location="westus",
            power_state="VM running",
            public_ip="1.2.3.6",
            vm_size="Standard_D4s_v3",
            tags={"env": "prod", "team": "backend"}
        ),
        VMInfo(
            name="test-vm-01",
            resource_group="test-rg",
            location="eastus",
            power_state="VM stopped",
            public_ip=None,
            vm_size="Standard_B2s",
            tags={"env": "test", "temporary": "true"}
        ),
    ]


class TestTagFilter:
    """Test tag filter parsing and matching."""

    def test_parse_simple_tag(self):
        """Test parsing simple key=value tag."""
        tag_filter = TagFilter.parse("env=dev")
        assert tag_filter.key == "env"
        assert tag_filter.value == "dev"

    def test_parse_tag_with_spaces(self):
        """Test parsing tag with spaces around equals."""
        tag_filter = TagFilter.parse("env = dev")
        assert tag_filter.key == "env"
        assert tag_filter.value == "dev"

    def test_parse_invalid_tag_raises_error(self):
        """Test that invalid tag format raises error."""
        with pytest.raises(BatchExecutorError, match="Invalid tag format"):
            TagFilter.parse("invalid-tag")

    def test_parse_tag_with_multiple_equals(self):
        """Test parsing tag with = in value."""
        tag_filter = TagFilter.parse("config=debug=true")
        assert tag_filter.key == "config"
        assert tag_filter.value == "debug=true"

    def test_matches_vm_with_tag(self, sample_vms):
        """Test matching VM with matching tag."""
        tag_filter = TagFilter.parse("env=dev")
        assert tag_filter.matches(sample_vms[0]) is True

    def test_does_not_match_vm_without_tag(self, sample_vms):
        """Test not matching VM without tag."""
        tag_filter = TagFilter.parse("env=staging")
        assert tag_filter.matches(sample_vms[0]) is False

    def test_does_not_match_vm_with_no_tags(self):
        """Test not matching VM with no tags."""
        vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            tags=None
        )
        tag_filter = TagFilter.parse("env=dev")
        assert tag_filter.matches(vm) is False


class TestBatchSelector:
    """Test VM selection logic."""

    def test_select_by_tag_single_match(self, sample_vms):
        """Test selecting VMs by single tag."""
        selected = BatchSelector.select_by_tag(sample_vms, "env=prod")
        assert len(selected) == 1
        assert selected[0].name == "azlin-prod-01"

    def test_select_by_tag_multiple_matches(self, sample_vms):
        """Test selecting VMs by tag with multiple matches."""
        selected = BatchSelector.select_by_tag(sample_vms, "env=dev")
        assert len(selected) == 2
        assert selected[0].name == "azlin-dev-01"
        assert selected[1].name == "azlin-dev-02"

    def test_select_by_tag_no_matches(self, sample_vms):
        """Test selecting VMs by tag with no matches."""
        selected = BatchSelector.select_by_tag(sample_vms, "env=staging")
        assert len(selected) == 0

    def test_select_by_pattern_exact_match(self, sample_vms):
        """Test selecting VMs by exact name pattern."""
        selected = BatchSelector.select_by_pattern(sample_vms, "azlin-dev-01")
        assert len(selected) == 1
        assert selected[0].name == "azlin-dev-01"

    def test_select_by_pattern_wildcard(self, sample_vms):
        """Test selecting VMs by wildcard pattern."""
        selected = BatchSelector.select_by_pattern(sample_vms, "azlin-dev-*")
        assert len(selected) == 2
        assert all(vm.name.startswith("azlin-dev-") for vm in selected)

    def test_select_by_pattern_prefix(self, sample_vms):
        """Test selecting VMs by prefix pattern."""
        selected = BatchSelector.select_by_pattern(sample_vms, "azlin-*")
        assert len(selected) == 3

    def test_select_by_pattern_no_matches(self, sample_vms):
        """Test selecting VMs by pattern with no matches."""
        selected = BatchSelector.select_by_pattern(sample_vms, "nonexistent-*")
        assert len(selected) == 0

    def test_select_all(self, sample_vms):
        """Test selecting all VMs."""
        selected = BatchSelector.select_all(sample_vms)
        assert len(selected) == 4
        assert selected == sample_vms

    def test_select_running_only(self, sample_vms):
        """Test selecting only running VMs."""
        selected = BatchSelector.select_running_only(sample_vms)
        assert len(selected) == 3
        assert all(vm.is_running() for vm in selected)

    def test_select_by_tag_and_pattern(self, sample_vms):
        """Test combining tag and pattern selection."""
        # First filter by tag
        by_tag = BatchSelector.select_by_tag(sample_vms, "env=dev")
        # Then filter by pattern
        selected = BatchSelector.select_by_pattern(by_tag, "*-01")
        assert len(selected) == 1
        assert selected[0].name == "azlin-dev-01"


class TestBatchExecutor:
    """Test batch operation execution."""

    @patch('azlin.batch_executor.VMLifecycleController')
    def test_execute_stop_single_vm(self, mock_controller, sample_vms):
        """Test executing stop on single VM."""
        # Setup mock
        mock_result = Mock(success=True, message="VM stopped")
        mock_controller.stop_vm.return_value = mock_result

        # Execute
        executor = BatchExecutor(max_workers=1)
        results = executor.execute_stop([sample_vms[0]], "test-rg")

        # Verify
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].vm_name == "azlin-dev-01"
        mock_controller.stop_vm.assert_called_once()

    @patch('azlin.batch_executor.VMLifecycleController')
    def test_execute_stop_multiple_vms(self, mock_controller, sample_vms):
        """Test executing stop on multiple VMs."""
        # Setup mock
        mock_result = Mock(success=True, message="VM stopped")
        mock_controller.stop_vm.return_value = mock_result

        # Execute
        executor = BatchExecutor(max_workers=5)
        results = executor.execute_stop(sample_vms[:3], "test-rg")

        # Verify
        assert len(results) == 3
        assert all(r.success for r in results)
        assert mock_controller.stop_vm.call_count == 3

    @patch('azlin.batch_executor.VMLifecycleController')
    def test_execute_stop_with_failure(self, mock_controller, sample_vms):
        """Test handling VM stop failure."""
        # Setup mock - first succeeds, second fails
        mock_controller.stop_vm.side_effect = [
            Mock(success=True, message="VM stopped"),
            Mock(success=False, message="Stop failed"),
        ]

        # Execute
        executor = BatchExecutor(max_workers=2)
        results = executor.execute_stop(sample_vms[:2], "test-rg")

        # Verify
        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is False

    @patch('azlin.batch_executor.VMLifecycleController')
    def test_execute_start_multiple_vms(self, mock_controller, sample_vms):
        """Test executing start on multiple VMs."""
        # Setup mock
        mock_result = Mock(success=True, message="VM started")
        mock_controller.start_vm.return_value = mock_result

        # Execute
        executor = BatchExecutor(max_workers=5)
        results = executor.execute_start(sample_vms[:2], "test-rg")

        # Verify
        assert len(results) == 2
        assert all(r.success for r in results)

    @patch('azlin.batch_executor.RemoteExecutor')
    @patch('azlin.batch_executor.SSHKeyManager')
    def test_execute_command_multiple_vms(self, mock_ssh_mgr, mock_executor, sample_vms):
        """Test executing command on multiple VMs."""
        # Setup mocks
        mock_ssh_mgr.ensure_key_exists.return_value = Mock(private_path=Path("/fake/key"))
        mock_executor.execute_command.return_value = Mock(
            success=True,
            stdout="output",
            exit_code=0
        )

        # Execute
        executor = BatchExecutor(max_workers=5)
        results = executor.execute_command(sample_vms[:2], "echo test", "test-rg")

        # Verify
        assert len(results) == 2
        assert all(r.success for r in results)

    @patch('azlin.batch_executor.HomeSyncManager')
    @patch('azlin.batch_executor.SSHKeyManager')
    def test_execute_sync_multiple_vms(self, mock_ssh_mgr, mock_sync_mgr, sample_vms):
        """Test executing sync on multiple VMs."""
        # Setup mocks
        mock_ssh_mgr.ensure_key_exists.return_value = Mock(private_path=Path("/fake/key"))
        mock_sync_mgr.sync_to_vm.return_value = Mock(
            success=True,
            files_synced=10,
            bytes_transferred=1024
        )

        # Execute
        executor = BatchExecutor(max_workers=5)
        results = executor.execute_sync(sample_vms[:2], "test-rg")

        # Verify
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_executor_respects_max_workers(self, sample_vms):
        """Test that executor respects max_workers limit."""
        executor = BatchExecutor(max_workers=2)
        assert executor.max_workers == 2

    @patch('azlin.batch_executor.VMLifecycleController')
    def test_execute_with_progress_callback(self, mock_controller, sample_vms):
        """Test progress callback is called during execution."""
        # Setup mock
        mock_controller.stop_vm.return_value = Mock(success=True, message="VM stopped")
        
        # Track progress calls
        progress_calls = []
        
        def progress_callback(msg):
            progress_calls.append(msg)

        # Execute
        executor = BatchExecutor(max_workers=2)
        results = executor.execute_stop(
            sample_vms[:2],
            "test-rg",
            progress_callback=progress_callback
        )

        # Verify progress was reported
        assert len(progress_calls) > 0
        assert any("azlin-dev-01" in call for call in progress_calls)


class TestBatchResult:
    """Test batch result aggregation."""

    def test_batch_result_all_success(self):
        """Test batch result with all successes."""
        results = [
            BatchOperationResult(vm_name="vm1", success=True, message="OK"),
            BatchOperationResult(vm_name="vm2", success=True, message="OK"),
        ]
        batch_result = BatchResult(results)
        
        assert batch_result.total == 2
        assert batch_result.succeeded == 2
        assert batch_result.failed == 0
        assert batch_result.all_succeeded is True

    def test_batch_result_all_failure(self):
        """Test batch result with all failures."""
        results = [
            BatchOperationResult(vm_name="vm1", success=False, message="Error"),
            BatchOperationResult(vm_name="vm2", success=False, message="Error"),
        ]
        batch_result = BatchResult(results)
        
        assert batch_result.total == 2
        assert batch_result.succeeded == 0
        assert batch_result.failed == 2
        assert batch_result.all_succeeded is False

    def test_batch_result_partial_success(self):
        """Test batch result with partial success."""
        results = [
            BatchOperationResult(vm_name="vm1", success=True, message="OK"),
            BatchOperationResult(vm_name="vm2", success=False, message="Error"),
        ]
        batch_result = BatchResult(results)
        
        assert batch_result.total == 2
        assert batch_result.succeeded == 1
        assert batch_result.failed == 1
        assert batch_result.all_succeeded is False

    def test_batch_result_format_summary(self):
        """Test formatting batch result summary."""
        results = [
            BatchOperationResult(vm_name="vm1", success=True, message="OK"),
            BatchOperationResult(vm_name="vm2", success=False, message="Error"),
        ]
        batch_result = BatchResult(results)
        summary = batch_result.format_summary()
        
        assert "Total: 2" in summary
        assert "Succeeded: 1" in summary
        assert "Failed: 1" in summary

    def test_batch_result_get_failures(self):
        """Test getting only failed results."""
        results = [
            BatchOperationResult(vm_name="vm1", success=True, message="OK"),
            BatchOperationResult(vm_name="vm2", success=False, message="Error"),
            BatchOperationResult(vm_name="vm3", success=False, message="Error"),
        ]
        batch_result = BatchResult(results)
        failures = batch_result.get_failures()
        
        assert len(failures) == 2
        assert all(not r.success for r in failures)

    def test_batch_result_get_successes(self):
        """Test getting only successful results."""
        results = [
            BatchOperationResult(vm_name="vm1", success=True, message="OK"),
            BatchOperationResult(vm_name="vm2", success=False, message="Error"),
            BatchOperationResult(vm_name="vm3", success=True, message="OK"),
        ]
        batch_result = BatchResult(results)
        successes = batch_result.get_successes()
        
        assert len(successes) == 2
        assert all(r.success for r in successes)


class TestBatchErrorHandling:
    """Test error handling in batch operations."""

    def test_empty_vm_list(self):
        """Test handling empty VM list."""
        executor = BatchExecutor(max_workers=5)
        results = executor.execute_stop([], "test-rg")
        assert len(results) == 0

    @patch('azlin.batch_executor.VMLifecycleController')
    def test_exception_in_operation(self, mock_controller, sample_vms):
        """Test handling exception during operation."""
        # Setup mock to raise exception
        mock_controller.stop_vm.side_effect = Exception("Network error")

        # Execute
        executor = BatchExecutor(max_workers=1)
        results = executor.execute_stop([sample_vms[0]], "test-rg")

        # Verify error is captured
        assert len(results) == 1
        assert results[0].success is False
        assert "Network error" in results[0].message

    def test_invalid_tag_format(self):
        """Test handling invalid tag format."""
        with pytest.raises(BatchExecutorError, match="Invalid tag format"):
            TagFilter.parse("invalid")

    @patch('azlin.vm_manager.VMManager')
    def test_resource_group_not_found(self, mock_vm_manager):
        """Test handling resource group not found."""
        mock_vm_manager.list_vms.return_value = []

        # This should not raise, just return empty list
        executor = BatchExecutor(max_workers=5)
        results = executor.execute_stop([], "nonexistent-rg")
        assert len(results) == 0


class TestBatchIntegration:
    """Integration tests for batch operations."""

    @patch('azlin.batch_executor.VMLifecycleController')
    def test_end_to_end_stop_by_tag(self, mock_controller, sample_vms):
        """Test end-to-end: select by tag and stop."""
        # Setup mocks
        mock_controller.stop_vm.return_value = Mock(success=True, message="Stopped")

        # Select VMs
        selected = BatchSelector.select_by_tag(sample_vms, "env=dev")

        # Execute stop
        executor = BatchExecutor(max_workers=5)
        results = executor.execute_stop(selected, "test-rg")

        # Verify
        assert len(results) == 2
        assert all(r.success for r in results)

    @patch('azlin.batch_executor.VMLifecycleController')
    def test_end_to_end_start_by_pattern(self, mock_controller, sample_vms):
        """Test end-to-end: select by pattern and start."""
        # Setup mocks
        mock_controller.start_vm.return_value = Mock(success=True, message="Started")

        # Select VMs
        selected = BatchSelector.select_by_pattern(sample_vms, "azlin-*")

        # Execute start
        executor = BatchExecutor(max_workers=5)
        results = executor.execute_start(selected, "test-rg")

        # Verify
        assert len(results) == 3
        assert all(r.success for r in results)
