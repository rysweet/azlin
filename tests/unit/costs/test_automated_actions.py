"""Unit tests for automated optimization actions.

Test Structure: 60% Unit tests (TDD Red Phase)
Feature: Automated cost optimization actions (VM resizing, scheduling, cleanup)

These tests follow TDD approach - ALL tests should FAIL initially until
the automated actions implementation is complete.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import Mock, MagicMock, patch, call

import pytest

from azlin.costs.actions import (
    AutomatedAction,
    ActionExecutor,
    ActionResult,
    ActionStatus,
    VMResizeAction,
    VMScheduleAction,
    ResourceDeleteAction,
    ActionSafetyCheck,
    ActionApprovalRequiredError,
    ActionRollback,
)


class TestAutomatedAction:
    """Tests for base automated action."""

    def test_action_initialization(self):
        """Test action initializes with correct data."""
        action = AutomatedAction(
            action_type="vm_resize",
            resource_name="azlin-vm-dev-01",
            resource_group="test-rg",
            estimated_savings=Decimal("180.00"),
            requires_approval=False,
        )

        assert action.action_type == "vm_resize"
        assert action.resource_name == "azlin-vm-dev-01"
        assert action.estimated_savings == Decimal("180.00")

    def test_action_tracks_execution_status(self):
        """Test action tracks execution status (pending/running/completed/failed)."""
        action = AutomatedAction(
            action_type="vm_delete",
            resource_name="test-vm",
            resource_group="test-rg",
            estimated_savings=Decimal("100.00"),
        )

        assert action.status == ActionStatus.PENDING

        action.mark_running()
        assert action.status == ActionStatus.RUNNING

        action.mark_completed()
        assert action.status == ActionStatus.COMPLETED

    def test_action_records_execution_time(self):
        """Test action records when it was executed."""
        action = AutomatedAction(
            action_type="vm_schedule",
            resource_name="test-vm",
            resource_group="test-rg",
            estimated_savings=Decimal("50.00"),
        )

        action.mark_running()
        start_time = action.started_at

        action.mark_completed()
        end_time = action.completed_at

        assert start_time is not None
        assert end_time is not None
        assert end_time > start_time

    def test_action_supports_dry_run_mode(self):
        """Test action can run in dry-run mode (preview only)."""
        action = AutomatedAction(
            action_type="vm_resize",
            resource_name="test-vm",
            resource_group="test-rg",
            estimated_savings=Decimal("100.00"),
            dry_run=True,
        )

        assert action.is_dry_run()
        result = action.execute()

        # Dry run shouldn't make actual changes
        assert result.dry_run is True
        assert not result.changes_applied


class TestVMResizeAction:
    """Tests for VM resize automation."""

    @patch("azlin.costs.actions.VMManager")
    def test_resize_action_changes_vm_size(self, mock_vm_manager_class):
        """Test resize action changes VM to smaller size."""
        mock_vm_manager = mock_vm_manager_class.return_value

        action = VMResizeAction(
            resource_name="azlin-vm-oversized",
            resource_group="test-rg",
            current_size="Standard_E16as_v5",
            target_size="Standard_E8as_v5",
            estimated_savings=Decimal("180.00"),
        )

        result = action.execute()

        mock_vm_manager.resize_vm.assert_called_once_with(
            resource_group="test-rg",
            vm_name="azlin-vm-oversized",
            new_size="Standard_E8as_v5",
        )

        assert result.status == ActionStatus.COMPLETED

    @patch("azlin.costs.actions.VMManager")
    def test_resize_action_validates_target_size(self, mock_vm_manager):
        """Test resize action validates target VM size exists."""
        action = VMResizeAction(
            resource_name="test-vm",
            resource_group="test-rg",
            current_size="Standard_D4s_v5",
            target_size="Invalid_Size",
            estimated_savings=Decimal("100.00"),
        )

        with pytest.raises(ValueError, match="(?i)invalid"):
            action.execute()

    @patch("azlin.costs.actions.VMManager")
    def test_resize_action_handles_running_vms(self, mock_vm_manager_class):
        """Test resize action stops VM before resize."""
        mock_vm_manager = mock_vm_manager_class.return_value
        mock_vm_manager.get_vm_state.return_value = "running"

        action = VMResizeAction(
            resource_name="test-vm",
            resource_group="test-rg",
            current_size="Standard_D4s_v5",
            target_size="Standard_D2s_v5",
            estimated_savings=Decimal("75.00"),
        )

        result = action.execute()

        # Should stop VM before resizing
        assert mock_vm_manager.stop_vm.called
        assert mock_vm_manager.resize_vm.called

    @patch("azlin.costs.actions.VMManager")
    def test_resize_action_prevents_upsize(self, mock_vm_manager):
        """Test resize action prevents upsizing (cost increase)."""
        action = VMResizeAction(
            resource_name="test-vm",
            resource_group="test-rg",
            current_size="Standard_D2s_v5",
            target_size="Standard_D8s_v5",  # Larger size!
            estimated_savings=Decimal("-200.00"),  # Negative savings
        )

        with pytest.raises(ValueError, match="(?i)increase cost"):
            action.execute()

    @patch("azlin.costs.actions.VMManager")
    def test_resize_action_supports_rollback(self, mock_vm_manager_class):
        """Test resize action can be rolled back to original size."""
        mock_vm_manager = mock_vm_manager_class.return_value

        action = VMResizeAction(
            resource_name="test-vm",
            resource_group="test-rg",
            current_size="Standard_E8as_v5",
            target_size="Standard_E4as_v5",
            estimated_savings=Decimal("120.00"),
        )

        action.execute()

        # Rollback to original size
        rollback = action.create_rollback()
        rollback.execute()

        calls = mock_vm_manager.resize_vm.call_args_list
        assert calls[0][1]["new_size"] == "Standard_E4as_v5"  # Forward
        assert calls[1][1]["new_size"] == "Standard_E8as_v5"  # Rollback


class TestVMScheduleAction:
    """Tests for VM scheduling automation."""

    @patch("azlin.costs.actions.VMScheduler")
    def test_schedule_action_creates_startup_shutdown_schedule(self, mock_scheduler_class):
        """Test schedule action creates business hours schedule."""
        mock_scheduler = mock_scheduler_class.return_value

        action = VMScheduleAction(
            resource_name="azlin-vm-dev-01",
            resource_group="test-rg",
            schedule_type="business_hours",
            start_time=time(8, 0),
            stop_time=time(18, 0),
            weekdays_only=True,
            estimated_savings=Decimal("200.00"),
        )

        result = action.execute()

        mock_scheduler.create_schedule.assert_called_once()
        call_kwargs = mock_scheduler.create_schedule.call_args[1]

        assert call_kwargs["start_time"] == time(8, 0)
        assert call_kwargs["stop_time"] == time(18, 0)
        assert call_kwargs["weekdays_only"] is True

    @patch("azlin.costs.actions.VMScheduler")
    def test_schedule_action_validates_time_range(self, mock_scheduler):
        """Test schedule action validates start time before stop time."""
        with pytest.raises(ValueError, match="(?i)start"):
            VMScheduleAction(
                resource_name="test-vm",
                resource_group="test-rg",
                schedule_type="custom",
                start_time=time(18, 0),
                stop_time=time(8, 0),  # Before start time!
                estimated_savings=Decimal("100.00"),
            )

    @patch("azlin.costs.actions.VMScheduler")
    def test_schedule_action_supports_weekend_only(self, mock_scheduler_class):
        """Test schedule action supports weekend-only schedules."""
        mock_scheduler = mock_scheduler_class.return_value

        action = VMScheduleAction(
            resource_name="azlin-vm-training",
            resource_group="test-rg",
            schedule_type="weekend_only",
            start_time=time(0, 0),
            stop_time=time(23, 59),
            weekdays_only=False,
            weekend_only=True,
            estimated_savings=Decimal("350.00"),
        )

        result = action.execute()

        call_kwargs = mock_scheduler.create_schedule.call_args[1]
        assert call_kwargs["weekend_only"] is True

    @patch("azlin.costs.actions.VMScheduler")
    def test_schedule_action_tags_vm_with_schedule(self, mock_scheduler_class):
        """Test schedule action tags VM with schedule metadata."""
        mock_scheduler = mock_scheduler_class.return_value

        action = VMScheduleAction(
            resource_name="test-vm",
            resource_group="test-rg",
            schedule_type="business_hours",
            start_time=time(8, 0),
            stop_time=time(18, 0),
            estimated_savings=Decimal("150.00"),
        )

        action.execute()

        # Should tag VM with schedule info
        mock_scheduler.tag_vm_with_schedule.assert_called_once()

    @patch("azlin.costs.actions.VMScheduler")
    def test_schedule_action_can_be_disabled(self, mock_scheduler_class):
        """Test schedule action can be disabled to restore 24/7 operation."""
        mock_scheduler = mock_scheduler_class.return_value

        action = VMScheduleAction(
            resource_name="test-vm",
            resource_group="test-rg",
            schedule_type="business_hours",
            start_time=time(8, 0),
            stop_time=time(18, 0),
            estimated_savings=Decimal("150.00"),
        )

        action.execute()

        # Disable schedule
        rollback = action.create_rollback()
        rollback.execute()

        mock_scheduler.remove_schedule.assert_called_once_with(
            resource_group="test-rg", vm_name="test-vm"
        )


class TestResourceDeleteAction:
    """Tests for resource deletion automation."""

    @patch("azlin.costs.actions.ResourceManager")
    def test_delete_action_removes_resource(self, mock_resource_manager_class):
        """Test delete action removes unused resource."""
        mock_resource_manager = mock_resource_manager_class.return_value

        action = ResourceDeleteAction(
            resource_name="disk-orphaned-01",
            resource_group="test-rg",
            resource_type="Disk",
            reason="Unattached for 30+ days",
            estimated_savings=Decimal("40.96"),
        )

        # Approve deletion
        action.approve()
        result = action.execute()

        mock_resource_manager.delete_resource.assert_called_once_with(
            resource_group="test-rg",
            resource_name="disk-orphaned-01",
            resource_type="Disk",
        )

    @patch("azlin.costs.actions.ResourceManager")
    def test_delete_action_requires_approval(self, mock_resource_manager):
        """Test delete action requires explicit approval."""
        action = ResourceDeleteAction(
            resource_name="vm-old",
            resource_group="test-rg",
            resource_type="VirtualMachine",
            reason="Stopped for 60+ days",
            estimated_savings=Decimal("250.00"),
            requires_approval=True,
        )

        # Execute without approval - should fail
        with pytest.raises(ActionApprovalRequiredError) as exc_info:
            action.execute()

        assert "approval" in str(exc_info.value).lower()

    @patch("azlin.costs.actions.ResourceManager")
    def test_delete_action_creates_snapshot_before_deletion(self, mock_resource_manager_class):
        """Test delete action creates backup snapshot for VMs."""
        mock_resource_manager = mock_resource_manager_class.return_value

        action = ResourceDeleteAction(
            resource_name="vm-to-delete",
            resource_group="test-rg",
            resource_type="VirtualMachine",
            reason="Unused",
            estimated_savings=Decimal("200.00"),
            create_backup=True,
        )

        action.approve()
        action.execute()

        # Should create snapshot before deletion
        mock_resource_manager.create_snapshot.assert_called_once()
        mock_resource_manager.delete_resource.assert_called_once()

    @patch("azlin.costs.actions.ResourceManager")
    def test_delete_action_prevents_production_deletion(self, mock_resource_manager_class):
        """Test delete action prevents accidental production resource deletion."""
        mock_resource_manager = mock_resource_manager_class.return_value

        # Should detect production tag and block
        mock_resource_manager.get_resource_tags.return_value = {"environment": "production"}

        action = ResourceDeleteAction(
            resource_name="vm-prod-critical",
            resource_group="production-rg",
            resource_type="VirtualMachine",
            reason="Low utilization",
            estimated_savings=Decimal("500.00"),
        )

        action.approve()

        with pytest.raises(ValueError, match="(?i)production"):
            action.execute()

    @patch("azlin.costs.actions.ResourceManager")
    def test_delete_action_supports_soft_delete(self, mock_resource_manager_class):
        """Test delete action supports soft delete (tagging instead of deleting)."""
        mock_resource_manager = mock_resource_manager_class.return_value

        action = ResourceDeleteAction(
            resource_name="disk-maybe-unused",
            resource_group="test-rg",
            resource_type="Disk",
            reason="Unattached",
            estimated_savings=Decimal("20.00"),
            soft_delete=True,
        )

        action.approve()
        action.execute()

        # Should tag instead of delete
        mock_resource_manager.tag_resource.assert_called_once()
        mock_resource_manager.delete_resource.assert_not_called()


class TestActionSafetyCheck:
    """Tests for action safety checks."""

    def test_safety_check_validates_resource_exists(self):
        """Test safety check verifies resource exists before action."""
        with patch("azlin.costs.actions.ResourceManager") as mock_rm_class:
            mock_rm = mock_rm_class.return_value
            mock_rm.resource_exists.return_value = False

            safety = ActionSafetyCheck()

            action = AutomatedAction(
                action_type="vm_resize",
                resource_name="nonexistent-vm",
                resource_group="test-rg",
                estimated_savings=Decimal("100.00"),
            )

            result = safety.validate(action)

            assert result.safe is False
            assert "not found" in result.reason.lower()

    def test_safety_check_prevents_duplicate_actions(self):
        """Test safety check prevents running duplicate actions."""
        safety = ActionSafetyCheck()

        action1 = VMResizeAction(
            resource_name="test-vm",
            resource_group="test-rg",
            current_size="Standard_D4s_v5",
            target_size="Standard_D2s_v5",
            estimated_savings=Decimal("75.00"),
        )

        action2 = VMResizeAction(
            resource_name="test-vm",
            resource_group="test-rg",
            current_size="Standard_D4s_v5",
            target_size="Standard_D2s_v5",
            estimated_savings=Decimal("75.00"),
        )

        # First action passes
        result1 = safety.validate(action1)
        assert result1.safe is True

        action1.mark_running()

        # Second action on same resource fails
        result2 = safety.validate(action2)
        assert result2.safe is False
        assert "already running" in result2.reason.lower()

    def test_safety_check_validates_cost_savings(self):
        """Test safety check validates action actually saves money."""
        safety = ActionSafetyCheck()

        action = VMResizeAction(
            resource_name="test-vm",
            resource_group="test-rg",
            current_size="Standard_D2s_v5",
            target_size="Standard_D4s_v5",  # Larger!
            estimated_savings=Decimal("-100.00"),  # Negative!
        )

        result = safety.validate(action)

        assert result.safe is False
        assert "increase cost" in result.reason.lower()


class TestActionExecutor:
    """Tests for action execution orchestration."""

    def test_executor_runs_single_action(self):
        """Test executor runs a single action."""
        action = Mock(spec=AutomatedAction)
        action.execute.return_value = ActionResult(status=ActionStatus.COMPLETED)

        executor = ActionExecutor()
        results = executor.execute_actions([action])

        assert len(results) == 1
        assert results[0].status == ActionStatus.COMPLETED
        action.execute.assert_called_once()

    def test_executor_runs_multiple_actions_sequentially(self):
        """Test executor runs actions one at a time."""
        actions = [
            Mock(spec=AutomatedAction, resource_name=f"vm-{i}") for i in range(3)
        ]

        for action in actions:
            action.execute.return_value = ActionResult(status=ActionStatus.COMPLETED)

        executor = ActionExecutor()
        results = executor.execute_actions(actions)

        assert len(results) == 3
        for action in actions:
            action.execute.assert_called_once()

    def test_executor_handles_action_failures(self):
        """Test executor continues after action failure."""
        action1 = Mock(spec=AutomatedAction)
        action1.resource_name = "vm-1"
        action1.execute.return_value = ActionResult(status=ActionStatus.COMPLETED)

        action2 = Mock(spec=AutomatedAction)
        action2.resource_name = "vm-2"
        action2.execute.side_effect = Exception("Action failed")

        action3 = Mock(spec=AutomatedAction)
        action3.resource_name = "vm-3"
        action3.execute.return_value = ActionResult(status=ActionStatus.COMPLETED)

        executor = ActionExecutor()
        results = executor.execute_actions([action1, action2, action3])

        # Should execute all actions despite failure
        assert len(results) == 3
        assert results[0].status == ActionStatus.COMPLETED
        assert results[1].status == ActionStatus.FAILED
        assert results[2].status == ActionStatus.COMPLETED

    def test_executor_respects_dry_run_mode(self):
        """Test executor respects dry-run flag."""
        action = Mock(spec=AutomatedAction)
        action.is_dry_run.return_value = True
        action.execute.return_value = ActionResult(status=ActionStatus.COMPLETED, dry_run=True)

        executor = ActionExecutor()
        results = executor.execute_actions([action])

        assert results[0].dry_run is True

    def test_executor_tracks_total_savings(self):
        """Test executor calculates total savings from all actions."""
        actions = [
            Mock(spec=AutomatedAction, estimated_savings=Decimal("100.00")),
            Mock(spec=AutomatedAction, estimated_savings=Decimal("50.00")),
            Mock(spec=AutomatedAction, estimated_savings=Decimal("75.00")),
        ]

        for i, action in enumerate(actions):
            action.execute.return_value = ActionResult(
                status=ActionStatus.COMPLETED,
                actual_savings=Decimal(["100.00", "50.00", "75.00"][i])
            )

        executor = ActionExecutor()
        results = executor.execute_actions(actions)

        total_savings = executor.calculate_total_savings(results)
        assert total_savings == Decimal("225.00")

    def test_executor_sends_completion_notification(self):
        """Test executor sends notification after batch completion."""
        mock_notify = Mock()
        action = Mock(spec=AutomatedAction)
        action.execute.return_value = ActionResult(status=ActionStatus.COMPLETED)

        executor = ActionExecutor(notify_on_completion=True, notification_fn=mock_notify)
        executor.execute_actions([action])

        mock_notify.assert_called_once()


class TestActionResult:
    """Tests for action execution results."""

    def test_result_captures_success(self):
        """Test result captures successful execution."""
        result = ActionResult(
            status=ActionStatus.COMPLETED,
            message="VM resized successfully",
            actual_savings=Decimal("180.00"),
        )

        assert result.is_success()
        assert result.actual_savings == Decimal("180.00")

    def test_result_captures_failure(self):
        """Test result captures failed execution."""
        result = ActionResult(
            status=ActionStatus.FAILED,
            message="Failed to resize VM",
            error="VM is locked",
        )

        assert result.is_failure()
        assert result.error == "VM is locked"

    def test_result_formats_for_display(self):
        """Test result formats nicely for display."""
        result = ActionResult(
            status=ActionStatus.COMPLETED,
            message="Schedule created for azlin-vm-dev-01",
            actual_savings=Decimal("200.00"),
        )

        formatted = result.format()

        assert "COMPLETED" in formatted.upper()
        assert "$200.00" in formatted
        assert "azlin-vm-dev-01" in formatted
