"""Auto-scaling policy engine for intelligent resource scaling."""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path


class ScalingAction(str, Enum):
    """Scaling actions."""

    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    NO_ACTION = "no_action"


@dataclass
class AutoScalingPolicy:
    """Auto-scaling policy definition."""

    id: str
    name: str
    resource_id: str
    metric: str  # cpu, memory, requests_per_second, etc.
    scale_up_threshold: float
    scale_down_threshold: float
    min_instances: int = 1
    max_instances: int = 10
    cool_down_minutes: int = 5
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_action_at: str | None = None
    enabled: bool = True


class PolicyEngine:
    """Evaluate and execute auto-scaling policies."""

    def __init__(self, storage_dir: str | None = None):
        """Initialize policy engine.

        Args:
            storage_dir: Directory for policy storage (default: ~/.azlin/autoscaling)
        """
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path.home() / ".azlin" / "autoscaling"

        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def create_policy(
        self,
        name: str,
        resource_id: str,
        metric: str,
        scale_up_threshold: float,
        scale_down_threshold: float,
        min_instances: int = 1,
        max_instances: int = 10,
        cool_down_minutes: int = 5,
    ) -> AutoScalingPolicy:
        """Create a new auto-scaling policy.

        Args:
            name: Policy name
            resource_id: Target resource ID
            metric: Metric to monitor
            scale_up_threshold: Threshold to trigger scale-up
            scale_down_threshold: Threshold to trigger scale-down
            min_instances: Minimum instance count
            max_instances: Maximum instance count
            cool_down_minutes: Minutes to wait between actions

        Returns:
            Created policy
        """
        policy_id = name.lower().replace(" ", "-")

        policy = AutoScalingPolicy(
            id=policy_id,
            name=name,
            resource_id=resource_id,
            metric=metric,
            scale_up_threshold=scale_up_threshold,
            scale_down_threshold=scale_down_threshold,
            min_instances=min_instances,
            max_instances=max_instances,
            cool_down_minutes=cool_down_minutes,
        )

        self._save_policy(policy)
        return policy

    def get_policy(self, policy_id: str) -> AutoScalingPolicy | None:
        """Get policy by ID."""
        policy_file = self.storage_dir / f"{policy_id}.json"
        if not policy_file.exists():
            return None

        with open(policy_file) as f:
            data = json.load(f)

        return AutoScalingPolicy(
            id=data["id"],
            name=data["name"],
            resource_id=data["resource_id"],
            metric=data["metric"],
            scale_up_threshold=data["scale_up_threshold"],
            scale_down_threshold=data["scale_down_threshold"],
            min_instances=data.get("min_instances", 1),
            max_instances=data.get("max_instances", 10),
            cool_down_minutes=data.get("cool_down_minutes", 5),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            last_action_at=data.get("last_action_at"),
            enabled=data.get("enabled", True),
        )

    def evaluate_policy(
        self, policy_id: str, current_metric_value: float, current_instances: int
    ) -> tuple[ScalingAction, int]:
        """Evaluate policy and determine scaling action.

        Args:
            policy_id: Policy ID
            current_metric_value: Current metric value
            current_instances: Current instance count

        Returns:
            Tuple of (action, target_instances)
        """
        policy = self.get_policy(policy_id)
        if not policy or not policy.enabled:
            return ScalingAction.NO_ACTION, current_instances

        # Check cool-down period
        if policy.last_action_at:
            last_action = datetime.fromisoformat(policy.last_action_at)
            cool_down_end = last_action + timedelta(minutes=policy.cool_down_minutes)
            if datetime.utcnow() < cool_down_end:
                return ScalingAction.NO_ACTION, current_instances

        # Evaluate thresholds
        if current_metric_value > policy.scale_up_threshold:
            if current_instances < policy.max_instances:
                # Scale up by 1
                return ScalingAction.SCALE_UP, current_instances + 1

        elif (
            current_metric_value < policy.scale_down_threshold
            and current_instances > policy.min_instances
        ):
            # Scale down by 1
            return ScalingAction.SCALE_DOWN, current_instances - 1

        return ScalingAction.NO_ACTION, current_instances

    def record_action(self, policy_id: str) -> None:
        """Record that scaling action was taken.

        Args:
            policy_id: Policy ID
        """
        policy = self.get_policy(policy_id)
        if policy:
            policy.last_action_at = datetime.utcnow().isoformat()
            self._save_policy(policy)

    def list_policies(self) -> list[AutoScalingPolicy]:
        """List all policies."""
        policies = []
        for policy_file in self.storage_dir.glob("*.json"):
            policy = self.get_policy(policy_file.stem)
            if policy:
                policies.append(policy)
        return policies

    def _save_policy(self, policy: AutoScalingPolicy) -> None:
        """Save policy to disk."""
        policy_file = self.storage_dir / f"{policy.id}.json"

        data = {
            "id": policy.id,
            "name": policy.name,
            "resource_id": policy.resource_id,
            "metric": policy.metric,
            "scale_up_threshold": policy.scale_up_threshold,
            "scale_down_threshold": policy.scale_down_threshold,
            "min_instances": policy.min_instances,
            "max_instances": policy.max_instances,
            "cool_down_minutes": policy.cool_down_minutes,
            "created_at": policy.created_at,
            "last_action_at": policy.last_action_at,
            "enabled": policy.enabled,
        }

        with open(policy_file, "w") as f:
            json.dump(data, f, indent=2)

        os.chmod(policy_file, 0o600)
