"""Auto-scaling policy engine for dynamic resource management.

Provides metric-based auto-scaling with:
- CPU, memory, and custom metric triggers
- Scale up/down thresholds
- Min/max instance limits
- Cool-down periods to prevent flapping
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class ScaleMetric(str, Enum):
    """Metrics that can trigger scaling."""

    CPU_PERCENT = "cpu_percent"
    MEMORY_PERCENT = "memory_percent"
    REQUEST_COUNT = "request_count"
    QUEUE_LENGTH = "queue_length"


class ScaleAction(str, Enum):
    """Scaling actions."""

    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    NO_ACTION = "no_action"


@dataclass
class ScalePolicy:
    """Auto-scaling policy definition."""

    policy_id: str
    resource_id: str  # Target resource (VM scale set, etc.)
    metric: ScaleMetric
    scale_up_threshold: float  # Trigger scale up above this
    scale_down_threshold: float  # Trigger scale down below this
    min_instances: int = 1
    max_instances: int = 10
    scale_increment: int = 1  # How many instances to add/remove
    cooldown_seconds: int = 300  # Wait period between scaling actions
    enabled: bool = True
    last_action_time: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ScaleEvent:
    """Record of a scaling event."""

    policy_id: str
    resource_id: str
    action: ScaleAction
    metric_value: float
    previous_instances: int
    new_instances: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
    reason: str = ""


class AutoScaleEngine:
    """Manages auto-scaling policies and executes scaling actions."""

    def __init__(self):
        """Initialize auto-scale engine."""
        self.policies: dict[str, ScalePolicy] = {}
        self.events: list[ScaleEvent] = []

    def create_policy(
        self,
        policy_id: str,
        resource_id: str,
        metric: ScaleMetric,
        scale_up_threshold: float,
        scale_down_threshold: float,
        min_instances: int = 1,
        max_instances: int = 10,
        scale_increment: int = 1,
        cooldown_seconds: int = 300,
    ) -> ScalePolicy:
        """Create auto-scaling policy.

        Args:
            policy_id: Unique policy identifier
            resource_id: Target resource
            metric: Metric to monitor
            scale_up_threshold: Scale up when metric exceeds this
            scale_down_threshold: Scale down when metric below this
            min_instances: Minimum instance count
            max_instances: Maximum instance count
            scale_increment: Instances to add/remove per action
            cooldown_seconds: Wait time between actions

        Returns:
            Created policy

        Raises:
            ValueError: If policy already exists or thresholds invalid
        """
        if policy_id in self.policies:
            raise ValueError(f"Policy {policy_id} already exists")

        if scale_down_threshold >= scale_up_threshold:
            raise ValueError("Scale down threshold must be < scale up threshold")

        if min_instances >= max_instances:
            raise ValueError("Min instances must be < max instances")

        policy = ScalePolicy(
            policy_id=policy_id,
            resource_id=resource_id,
            metric=metric,
            scale_up_threshold=scale_up_threshold,
            scale_down_threshold=scale_down_threshold,
            min_instances=min_instances,
            max_instances=max_instances,
            scale_increment=scale_increment,
            cooldown_seconds=cooldown_seconds,
        )

        self.policies[policy_id] = policy
        return policy

    def evaluate_policy(
        self,
        policy_id: str,
        current_metric_value: float,
        current_instances: int,
    ) -> tuple[ScaleAction, int]:
        """Evaluate policy and determine scaling action.

        Args:
            policy_id: Policy to evaluate
            current_metric_value: Current metric reading
            current_instances: Current instance count

        Returns:
            Tuple of (action, target_instance_count)

        Raises:
            KeyError: If policy doesn't exist
        """
        policy = self.policies[policy_id]

        if not policy.enabled:
            return ScaleAction.NO_ACTION, current_instances

        # Check cooldown period
        if policy.last_action_time:
            elapsed = datetime.utcnow() - policy.last_action_time
            if elapsed < timedelta(seconds=policy.cooldown_seconds):
                return ScaleAction.NO_ACTION, current_instances

        # Determine action
        if current_metric_value >= policy.scale_up_threshold:
            # Scale up if not at max
            if current_instances < policy.max_instances:
                target = min(
                    current_instances + policy.scale_increment,
                    policy.max_instances,
                )
                return ScaleAction.SCALE_UP, target
        elif current_metric_value <= policy.scale_down_threshold:
            # Scale down if not at min
            if current_instances > policy.min_instances:
                target = max(
                    current_instances - policy.scale_increment,
                    policy.min_instances,
                )
                return ScaleAction.SCALE_DOWN, target

        return ScaleAction.NO_ACTION, current_instances

    def record_action(
        self,
        policy_id: str,
        action: ScaleAction,
        metric_value: float,
        previous_instances: int,
        new_instances: int,
        reason: str = "",
    ) -> ScaleEvent:
        """Record scaling action.

        Args:
            policy_id: Policy that triggered action
            action: Action taken
            metric_value: Metric value that triggered action
            previous_instances: Instance count before scaling
            new_instances: Instance count after scaling
            reason: Human-readable reason

        Returns:
            Created event

        Raises:
            KeyError: If policy doesn't exist
        """
        policy = self.policies[policy_id]

        event = ScaleEvent(
            policy_id=policy_id,
            resource_id=policy.resource_id,
            action=action,
            metric_value=metric_value,
            previous_instances=previous_instances,
            new_instances=new_instances,
            reason=reason,
        )

        self.events.append(event)

        # Update policy last action time
        if action != ScaleAction.NO_ACTION:
            policy.last_action_time = datetime.utcnow()

        return event

    def get_policy(self, policy_id: str) -> ScalePolicy:
        """Get policy by ID.

        Args:
            policy_id: Policy identifier

        Returns:
            Policy object

        Raises:
            KeyError: If policy doesn't exist
        """
        if policy_id not in self.policies:
            raise KeyError(f"Policy {policy_id} not found")
        return self.policies[policy_id]

    def disable_policy(self, policy_id: str) -> None:
        """Disable auto-scaling policy.

        Args:
            policy_id: Policy to disable

        Raises:
            KeyError: If policy doesn't exist
        """
        policy = self.get_policy(policy_id)
        policy.enabled = False

    def enable_policy(self, policy_id: str) -> None:
        """Enable auto-scaling policy.

        Args:
            policy_id: Policy to enable

        Raises:
            KeyError: If policy doesn't exist
        """
        policy = self.get_policy(policy_id)
        policy.enabled = True

    def get_events(self, resource_id: str | None = None, limit: int = 100) -> list[ScaleEvent]:
        """Get scaling events.

        Args:
            resource_id: Filter by resource (optional)
            limit: Maximum events to return

        Returns:
            List of events, most recent first
        """
        events = self.events
        if resource_id:
            events = [e for e in events if e.resource_id == resource_id]

        # Sort by timestamp descending
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events[:limit]
