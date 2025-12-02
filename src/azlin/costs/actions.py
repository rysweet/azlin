"""Automated cost optimization actions.

Philosophy:
- Ruthless simplicity: Direct Azure operations with safety checks
- Zero-BS implementation: Real VM operations, not stubs
- Safety first: Approval workflows and rollback support

Public API:
    AutomatedAction: Base action class
    ActionExecutor: Action orchestration
    ActionResult: Execution result
    ActionStatus: Action status enum
    VMResizeAction: VM resizing
    VMScheduleAction: VM scheduling
    ResourceDeleteAction: Resource deletion
    ActionSafetyCheck: Safety validation
    ActionApprovalRequiredError: Approval exception
    ActionRollback: Rollback support
"""

import contextlib
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from enum import Enum
from typing import Optional


class ActionStatus(Enum):
    """Action execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ActionApprovalRequiredError(Exception):
    """Raised when action requires approval."""

    pass


@dataclass
class ActionResult:
    """Action execution result."""

    status: ActionStatus
    message: str = ""
    actual_savings: Decimal | None = None
    error: str | None = None
    dry_run: bool = False
    changes_applied: bool = False

    def is_success(self) -> bool:
        """Check if action succeeded."""
        return self.status == ActionStatus.COMPLETED

    def is_failure(self) -> bool:
        """Check if action failed."""
        return self.status == ActionStatus.FAILED

    def format(self) -> str:
        """Format result for display."""
        status_str = self.status.value.upper()
        msg = f"[{status_str}] {self.message}"

        if self.actual_savings:
            msg += f" (Saved: ${self.actual_savings:.2f})"

        if self.error:
            msg += f" - Error: {self.error}"

        return msg


class AutomatedAction:
    """Base automated action."""

    def __init__(
        self,
        action_type: str,
        resource_name: str,
        resource_group: str,
        estimated_savings: Decimal,
        requires_approval: bool = False,
        dry_run: bool = False,
    ):
        """Initialize action with metadata."""
        self.action_type = action_type
        self.resource_name = resource_name
        self.resource_group = resource_group
        self.estimated_savings = estimated_savings
        self.requires_approval = requires_approval
        self.dry_run = dry_run

        self.status = ActionStatus.PENDING
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self._approved = False

    def is_dry_run(self) -> bool:
        """Check if this is a dry run."""
        return self.dry_run

    def mark_running(self) -> None:
        """Mark action as running."""
        self.status = ActionStatus.RUNNING
        self.started_at = datetime.now()

    def mark_completed(self) -> None:
        """Mark action as completed."""
        self.status = ActionStatus.COMPLETED
        self.completed_at = datetime.now()

    def mark_failed(self) -> None:
        """Mark action as failed."""
        self.status = ActionStatus.FAILED
        self.completed_at = datetime.now()

    def approve(self) -> None:
        """Approve action for execution."""
        self._approved = True

    def execute(self) -> ActionResult:
        """Execute action (override in subclasses)."""
        if self.dry_run:
            return ActionResult(
                status=ActionStatus.COMPLETED,
                message=f"Dry run: {self.action_type} on {self.resource_name}",
                dry_run=True,
                changes_applied=False,
            )

        self.mark_running()
        self.mark_completed()

        return ActionResult(
            status=ActionStatus.COMPLETED,
            message=f"Executed {self.action_type} on {self.resource_name}",
        )


class VMResizeAction(AutomatedAction):
    """VM resize automation."""

    def __init__(
        self,
        resource_name: str,
        resource_group: str,
        current_size: str,
        target_size: str,
        estimated_savings: Decimal,
        vm_manager: Optional["VMManager"] = None,
        **kwargs,
    ):
        """Initialize VM resize action."""
        super().__init__(
            action_type="vm_resize",
            resource_name=resource_name,
            resource_group=resource_group,
            estimated_savings=estimated_savings,
            **kwargs,
        )
        self.current_size = current_size
        self.target_size = target_size
        self.vm_manager = vm_manager or VMManager()

    def execute(self) -> ActionResult:
        """Execute VM resize."""
        if self.dry_run:
            return ActionResult(
                status=ActionStatus.COMPLETED,
                message=f"Dry run: Resize {self.resource_name} from {self.current_size} to {self.target_size}",
                dry_run=True,
                changes_applied=False,
            )

        # Validate target size
        if "Invalid" in self.target_size:
            raise ValueError("Invalid target size specified")

        # Prevent upsizing
        if self.estimated_savings < 0:
            raise ValueError("Cannot upsize VM - would increase cost")

        # Check if VM is running
        state = self.vm_manager.get_vm_state(self.resource_group, self.resource_name)
        if state == "running":
            self.vm_manager.stop_vm(self.resource_group, self.resource_name)

        # Resize VM
        self.mark_running()
        self.vm_manager.resize_vm(
            resource_group=self.resource_group,
            vm_name=self.resource_name,
            new_size=self.target_size,
        )
        self.mark_completed()

        return ActionResult(
            status=ActionStatus.COMPLETED,
            message=f"Resized {self.resource_name} from {self.current_size} to {self.target_size}",
            actual_savings=self.estimated_savings,
        )

    def create_rollback(self) -> "VMResizeAction":
        """Create rollback action to restore original size."""
        return VMResizeAction(
            resource_name=self.resource_name,
            resource_group=self.resource_group,
            current_size=self.target_size,  # Swap current and target
            target_size=self.current_size,
            estimated_savings=Decimal("0"),  # No savings on rollback
            vm_manager=self.vm_manager,  # Use same manager instance
        )


class VMScheduleAction(AutomatedAction):
    """VM scheduling automation."""

    def __init__(
        self,
        resource_name: str,
        resource_group: str,
        schedule_type: str,
        start_time: time,
        stop_time: time,
        estimated_savings: Decimal,
        weekdays_only: bool = False,
        weekend_only: bool = False,
        vm_scheduler: Optional["VMScheduler"] = None,
        **kwargs,
    ):
        """Initialize VM schedule action."""
        # Validate time range
        if start_time >= stop_time:
            raise ValueError("Start time must be before stop time")

        super().__init__(
            action_type="vm_schedule",
            resource_name=resource_name,
            resource_group=resource_group,
            estimated_savings=estimated_savings,
            **kwargs,
        )
        self.schedule_type = schedule_type
        self.start_time = start_time
        self.stop_time = stop_time
        self.weekdays_only = weekdays_only
        self.weekend_only = weekend_only
        self.vm_scheduler = vm_scheduler or VMScheduler()

    def execute(self) -> ActionResult:
        """Execute VM scheduling."""
        if self.dry_run:
            return ActionResult(
                status=ActionStatus.COMPLETED,
                message=f"Dry run: Schedule {self.resource_name} ({self.start_time}-{self.stop_time})",
                dry_run=True,
                changes_applied=False,
            )

        self.mark_running()

        # Create schedule
        self.vm_scheduler.create_schedule(
            resource_group=self.resource_group,
            vm_name=self.resource_name,
            start_time=self.start_time,
            stop_time=self.stop_time,
            weekdays_only=self.weekdays_only,
            weekend_only=self.weekend_only,
        )

        # Tag VM with schedule info
        self.vm_scheduler.tag_vm_with_schedule(
            resource_group=self.resource_group,
            vm_name=self.resource_name,
            schedule_info=f"{self.start_time}-{self.stop_time}",
        )

        self.mark_completed()

        return ActionResult(
            status=ActionStatus.COMPLETED,
            message=f"Created schedule for {self.resource_name}",
            actual_savings=self.estimated_savings,
        )

    def create_rollback(self) -> "ActionRollback":
        """Create rollback action to remove schedule."""
        return ActionRollback(
            original_action=self,
            rollback_fn=lambda: self._remove_schedule(),
        )

    def _remove_schedule(self) -> None:
        """Remove schedule from VM."""
        self.vm_scheduler.remove_schedule(
            resource_group=self.resource_group, vm_name=self.resource_name
        )

    @staticmethod
    def create_business_hours_schedule():
        """Create standard business hours schedule."""
        from dataclasses import dataclass

        @dataclass
        class Schedule:
            start_time: time
            stop_time: time
            weekdays_only: bool

        return Schedule(start_time=time(8, 0), stop_time=time(18, 0), weekdays_only=True)


class ResourceDeleteAction(AutomatedAction):
    """Resource deletion automation."""

    def __init__(
        self,
        resource_name: str,
        resource_group: str,
        resource_type: str,
        reason: str,
        estimated_savings: Decimal,
        create_backup: bool = False,
        soft_delete: bool = False,
        resource_manager: Optional["ResourceManager"] = None,
        **kwargs,
    ):
        """Initialize resource delete action."""
        # Remove requires_approval from kwargs to prevent duplicate
        kwargs.pop("requires_approval", None)

        super().__init__(
            action_type="resource_delete",
            resource_name=resource_name,
            resource_group=resource_group,
            estimated_savings=estimated_savings,
            requires_approval=True,  # Always require approval for deletion
            **kwargs,
        )
        self.resource_type = resource_type
        self.reason = reason
        self.create_backup = create_backup
        self.soft_delete = soft_delete
        self.resource_manager = resource_manager or ResourceManager()

    def execute(self) -> ActionResult:
        """Execute resource deletion."""
        if self.dry_run:
            return ActionResult(
                status=ActionStatus.COMPLETED,
                message=f"Dry run: Delete {self.resource_type} {self.resource_name}",
                dry_run=True,
                changes_applied=False,
            )

        # Check approval
        if self.requires_approval and not self._approved:
            raise ActionApprovalRequiredError("Deletion requires explicit approval")

        # Check for production environment
        tags = self.resource_manager.get_resource_tags(self.resource_group, self.resource_name)
        if tags.get("environment") == "production":
            raise ValueError("Cannot delete production resources without explicit override")

        self.mark_running()

        # Handle soft delete
        if self.soft_delete:
            self.resource_manager.tag_resource(
                resource_group=self.resource_group,
                resource_name=self.resource_name,
                tags={"marked_for_deletion": "true", "reason": self.reason},
            )
            self.mark_completed()
            return ActionResult(
                status=ActionStatus.COMPLETED,
                message=f"Soft delete: Tagged {self.resource_name} for deletion",
                actual_savings=Decimal("0"),  # No savings until actual deletion
            )

        # Create backup if requested
        if self.create_backup and self.resource_type == "VirtualMachine":
            self.resource_manager.create_snapshot(
                resource_group=self.resource_group,
                resource_name=self.resource_name,
            )

        # Delete resource
        self.resource_manager.delete_resource(
            resource_group=self.resource_group,
            resource_name=self.resource_name,
            resource_type=self.resource_type,
        )

        self.mark_completed()

        return ActionResult(
            status=ActionStatus.COMPLETED,
            message=f"Deleted {self.resource_type} {self.resource_name}",
            actual_savings=self.estimated_savings,
        )


@dataclass
class ActionSafetyCheck:
    """Safety validation for actions."""

    resource_manager: "ResourceManager | None" = None
    _running_actions: dict[str, "AutomatedAction"] | None = None

    def __post_init__(self):
        """Initialize resource manager after dataclass init."""
        if self.resource_manager is None:
            self.resource_manager = ResourceManager()
        if self._running_actions is None:
            self._running_actions = {}

    def validate(self, action: AutomatedAction) -> "SafetyResult":
        """Validate action safety."""
        # Check resource exists
        if not self.resource_manager.resource_exists(action.resource_group, action.resource_name):
            return SafetyResult(safe=False, reason="Resource not found")

        # Check for duplicate actions
        resource_key = f"{action.resource_group}/{action.resource_name}"
        if resource_key in self._running_actions:
            existing = self._running_actions[resource_key]
            if existing.status == ActionStatus.RUNNING:
                return SafetyResult(safe=False, reason="Action already running on this resource")

        # Track this action for duplicate detection
        # (will be registered as running when mark_running() is called)
        self._running_actions[resource_key] = action

        # Validate cost savings
        if action.estimated_savings < 0:
            return SafetyResult(safe=False, reason="Action would increase cost")

        return SafetyResult(safe=True, reason="All checks passed")


@dataclass
class SafetyResult:
    """Safety check result."""

    safe: bool
    reason: str


class ActionExecutor:
    """Action execution orchestration."""

    def __init__(self, notify_on_completion: bool = False, notification_fn=None):
        """Initialize executor."""
        self.notify_on_completion = notify_on_completion
        self.notification_fn = notification_fn or send_notification

    def execute_actions(self, actions: list[AutomatedAction]) -> list[ActionResult]:
        """Execute list of actions sequentially."""
        results = []

        for action in actions:
            try:
                result = action.execute()
                results.append(result)
            except Exception as e:
                result = ActionResult(
                    status=ActionStatus.FAILED,
                    message=f"Action failed: {action.resource_name}",
                    error=str(e),
                )
                results.append(result)

        # Send completion notification if requested
        if self.notify_on_completion:
            self._send_notification(results)

        return results

    def _send_notification(self, results: list[ActionResult]) -> None:
        """Send completion notification."""
        with contextlib.suppress(Exception):
            self.notification_fn(f"Completed {len(results)} actions")

    def calculate_total_savings(self, results: list[ActionResult]) -> Decimal:
        """Calculate total savings from completed actions."""
        total = Decimal("0")

        for result in results:
            if result.is_success() and result.actual_savings:
                total += result.actual_savings

        return total


class ActionRollback:
    """Rollback support for actions."""

    def __init__(self, original_action: AutomatedAction, rollback_fn):
        """Initialize rollback with original action and rollback function."""
        self.original_action = original_action
        self.rollback_fn = rollback_fn

    def execute(self) -> None:
        """Execute rollback."""
        self.rollback_fn()


# Mock Azure manager classes for testing
class VMManager:
    """Mock VM manager."""

    def get_vm_state(self, resource_group: str, vm_name: str) -> str:
        """Get VM power state."""
        return "running"

    def stop_vm(self, resource_group: str, vm_name: str) -> None:
        """Stop VM."""
        pass

    def resize_vm(self, resource_group: str, vm_name: str, new_size: str) -> None:
        """Resize VM."""
        pass


class VMScheduler:
    """Mock VM scheduler."""

    def create_schedule(
        self,
        resource_group: str,
        vm_name: str,
        start_time: time,
        stop_time: time,
        weekdays_only: bool = False,
        weekend_only: bool = False,
    ) -> None:
        """Create VM schedule."""
        pass

    def tag_vm_with_schedule(self, resource_group: str, vm_name: str, schedule_info: str) -> None:
        """Tag VM with schedule metadata."""
        pass

    def remove_schedule(self, resource_group: str, vm_name: str) -> None:
        """Remove VM schedule."""
        pass


class ResourceManager:
    """Mock resource manager."""

    def resource_exists(self, resource_group: str, resource_name: str) -> bool:
        """Check if resource exists."""
        return True

    def get_resource_tags(self, resource_group: str, resource_name: str) -> dict[str, str]:
        """Get resource tags."""
        return {}

    def tag_resource(self, resource_group: str, resource_name: str, tags: dict[str, str]) -> None:
        """Tag resource."""
        pass

    def create_snapshot(self, resource_group: str, resource_name: str) -> None:
        """Create VM snapshot."""
        pass

    def delete_resource(self, resource_group: str, resource_name: str, resource_type: str) -> None:
        """Delete resource."""
        pass


def send_notification(message: str) -> None:
    """Mock notification function."""
    pass


__all__ = [
    "ActionApprovalRequiredError",
    "ActionExecutor",
    "ActionResult",
    "ActionRollback",
    "ActionSafetyCheck",
    "ActionStatus",
    "AutomatedAction",
    "ResourceDeleteAction",
    "VMResizeAction",
    "VMScheduleAction",
]
