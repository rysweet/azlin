"""Event-driven workflow triggers for automated azlin execution.

Provides triggers for:
- Git push/pull request events
- Schedule-based execution
- Webhook callbacks
- Manual triggers
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable


class TriggerType(str, Enum):
    """Types of triggers."""

    GIT_PUSH = "git_push"
    PULL_REQUEST = "pull_request"
    WEBHOOK = "webhook"
    MANUAL = "manual"
    SCHEDULE = "schedule"  # Managed by scheduler


class TriggerStatus(str, Enum):
    """Trigger execution status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class TriggerCondition:
    """Conditions that must be met for trigger to fire."""

    branch_pattern: str | None = None  # Git branch pattern (e.g., "main", "feature/*")
    file_patterns: list[str] = field(default_factory=list)  # File globs that must change
    environment: str | None = None  # Target environment


@dataclass
class TriggerAction:
    """Action to execute when trigger fires."""

    action_type: str  # "azlin_doit", "custom_script", etc.
    command: str  # Command/objective to execute
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class Trigger:
    """Event-driven trigger definition."""

    trigger_id: str
    name: str
    trigger_type: TriggerType
    action: TriggerAction
    condition: TriggerCondition | None = None
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_triggered: datetime | None = None


@dataclass
class TriggerExecution:
    """Record of trigger execution."""

    execution_id: str
    trigger_id: str
    status: TriggerStatus
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class TriggerEngine:
    """Manages event-driven triggers."""

    def __init__(self):
        """Initialize trigger engine."""
        self.triggers: dict[str, Trigger] = {}
        self.executions: list[TriggerExecution] = []
        self._handlers: dict[TriggerType, list[Callable]] = {}

    def create_trigger(
        self,
        trigger_id: str,
        name: str,
        trigger_type: TriggerType,
        action: TriggerAction,
        condition: TriggerCondition | None = None,
    ) -> Trigger:
        """Create new trigger.

        Args:
            trigger_id: Unique trigger identifier
            name: Human-readable name
            trigger_type: Type of trigger
            action: Action to execute
            condition: Conditions for firing (optional)

        Returns:
            Created trigger

        Raises:
            ValueError: If trigger already exists
        """
        if trigger_id in self.triggers:
            raise ValueError(f"Trigger {trigger_id} already exists")

        trigger = Trigger(
            trigger_id=trigger_id,
            name=name,
            trigger_type=trigger_type,
            action=action,
            condition=condition,
        )

        self.triggers[trigger_id] = trigger
        return trigger

    def register_handler(
        self,
        trigger_type: TriggerType,
        handler: Callable[[TriggerExecution], None],
    ) -> None:
        """Register handler for trigger type.

        Args:
            trigger_type: Type of trigger
            handler: Async function to execute action
        """
        if trigger_type not in self._handlers:
            self._handlers[trigger_type] = []
        self._handlers[trigger_type].append(handler)

    def fire_trigger(
        self,
        trigger_id: str,
        event_data: dict[str, Any] | None = None,
    ) -> TriggerExecution | None:
        """Fire a trigger if conditions are met.

        Args:
            trigger_id: Trigger to fire
            event_data: Event data for condition evaluation

        Returns:
            Execution if trigger fired, None if conditions not met

        Raises:
            KeyError: If trigger doesn't exist
        """
        trigger = self.triggers[trigger_id]

        if not trigger.enabled:
            return None

        # Check conditions
        if trigger.condition and event_data:
            if not self._evaluate_condition(trigger.condition, event_data):
                return None

        # Create execution
        execution_id = f"{trigger_id}-{datetime.utcnow().timestamp()}"
        execution = TriggerExecution(
            execution_id=execution_id,
            trigger_id=trigger_id,
            status=TriggerStatus.PENDING,
        )

        self.executions.append(execution)
        trigger.last_triggered = datetime.utcnow()

        # Invoke handlers
        handlers = self._handlers.get(trigger.trigger_type, [])
        for handler in handlers:
            try:
                handler(execution)
            except Exception as e:
                execution.status = TriggerStatus.FAILED
                execution.error = str(e)
                execution.completed_at = datetime.utcnow()
                return execution

        return execution

    def _evaluate_condition(
        self,
        condition: TriggerCondition,
        event_data: dict[str, Any],
    ) -> bool:
        """Evaluate if conditions are met.

        Args:
            condition: Trigger conditions
            event_data: Event data

        Returns:
            True if conditions met
        """
        # Check branch pattern
        if condition.branch_pattern:
            branch = event_data.get("branch", "")
            if not self._match_pattern(condition.branch_pattern, branch):
                return False

        # Check file patterns
        if condition.file_patterns:
            changed_files = event_data.get("changed_files", [])
            if not any(
                self._match_pattern(pattern, file)
                for pattern in condition.file_patterns
                for file in changed_files
            ):
                return False

        # Check environment
        if condition.environment:
            if event_data.get("environment") != condition.environment:
                return False

        return True

    def _match_pattern(self, pattern: str, value: str) -> bool:
        """Simple glob-like pattern matching.

        Args:
            pattern: Pattern with * wildcards
            value: Value to match

        Returns:
            True if matches
        """
        if "*" not in pattern:
            return pattern == value

        # Simple wildcard matching
        parts = pattern.split("*")
        if not value.startswith(parts[0]):
            return False
        if not value.endswith(parts[-1]):
            return False

        return True

    def get_trigger(self, trigger_id: str) -> Trigger:
        """Get trigger by ID.

        Args:
            trigger_id: Trigger identifier

        Returns:
            Trigger object

        Raises:
            KeyError: If trigger doesn't exist
        """
        if trigger_id not in self.triggers:
            raise KeyError(f"Trigger {trigger_id} not found")
        return self.triggers[trigger_id]

    def disable_trigger(self, trigger_id: str) -> None:
        """Disable trigger.

        Args:
            trigger_id: Trigger to disable

        Raises:
            KeyError: If trigger doesn't exist
        """
        trigger = self.get_trigger(trigger_id)
        trigger.enabled = False

    def enable_trigger(self, trigger_id: str) -> None:
        """Enable trigger.

        Args:
            trigger_id: Trigger to enable

        Raises:
            KeyError: If trigger doesn't exist
        """
        trigger = self.get_trigger(trigger_id)
        trigger.enabled = True

    def get_executions(
        self,
        trigger_id: str | None = None,
        limit: int = 100,
    ) -> list[TriggerExecution]:
        """Get trigger executions.

        Args:
            trigger_id: Filter by trigger (optional)
            limit: Maximum executions to return

        Returns:
            List of executions, most recent first
        """
        executions = self.executions
        if trigger_id:
            executions = [e for e in executions if e.trigger_id == trigger_id]

        # Sort by started_at descending
        executions.sort(key=lambda e: e.started_at, reverse=True)
        return executions[:limit]
