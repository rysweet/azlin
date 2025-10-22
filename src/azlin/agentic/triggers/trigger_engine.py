"""Event-driven trigger engine for automated azlin operations."""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class TriggerType(str, Enum):
    """Trigger event types."""

    WEBHOOK = "webhook"
    GIT_PUSH = "git_push"
    SCHEDULE = "schedule"
    METRIC_THRESHOLD = "metric_threshold"
    MANUAL = "manual"


@dataclass
class Trigger:
    """Trigger definition for automated execution."""

    id: str
    name: str
    trigger_type: TriggerType
    action: str  # Command to execute
    conditions: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_triggered_at: str | None = None
    trigger_count: int = 0


class TriggerEngine:
    """Manage and execute triggers."""

    def __init__(self, storage_dir: str | None = None):
        """Initialize trigger engine.

        Args:
            storage_dir: Directory for trigger storage
        """
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path.home() / ".azlin" / "triggers"

        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def create_trigger(
        self,
        name: str,
        trigger_type: TriggerType,
        action: str,
        conditions: dict[str, Any] | None = None,
    ) -> Trigger:
        """Create a new trigger.

        Args:
            name: Trigger name
            trigger_type: Type of trigger
            action: Action to execute (azlin command)
            conditions: Trigger conditions

        Returns:
            Created Trigger
        """
        trigger_id = name.lower().replace(" ", "-")

        trigger = Trigger(
            id=trigger_id,
            name=name,
            trigger_type=trigger_type,
            action=action,
            conditions=conditions or {},
        )

        self._save_trigger(trigger)
        return trigger

    def get_trigger(self, trigger_id: str) -> Trigger | None:
        """Get trigger by ID."""
        trigger_file = self.storage_dir / f"{trigger_id}.json"
        if not trigger_file.exists():
            return None

        with open(trigger_file) as f:
            data = json.load(f)

        return Trigger(
            id=data["id"],
            name=data["name"],
            trigger_type=TriggerType(data["trigger_type"]),
            action=data["action"],
            conditions=data.get("conditions", {}),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            last_triggered_at=data.get("last_triggered_at"),
            trigger_count=data.get("trigger_count", 0),
        )

    def evaluate_trigger(self, trigger_id: str, event_data: dict[str, Any]) -> bool:
        """Evaluate if trigger conditions are met.

        Args:
            trigger_id: Trigger ID
            event_data: Event data to evaluate

        Returns:
            True if trigger should fire
        """
        trigger = self.get_trigger(trigger_id)
        if not trigger or not trigger.enabled:
            return False

        # Simple condition matching
        conditions = trigger.conditions

        # Check all conditions
        for key, expected_value in conditions.items():
            if key not in event_data:
                return False
            if event_data[key] != expected_value:
                return False

        return True

    def fire_trigger(self, trigger_id: str) -> bool:
        """Record trigger firing.

        Args:
            trigger_id: Trigger ID

        Returns:
            True if successful
        """
        trigger = self.get_trigger(trigger_id)
        if not trigger:
            return False

        trigger.last_triggered_at = datetime.utcnow().isoformat()
        trigger.trigger_count += 1

        self._save_trigger(trigger)
        return True

    def list_triggers(self, trigger_type: TriggerType | None = None) -> list[Trigger]:
        """List all triggers, optionally filtered by type."""
        triggers = []
        for trigger_file in self.storage_dir.glob("*.json"):
            trigger = self.get_trigger(trigger_file.stem)
            if trigger and (trigger_type is None or trigger.trigger_type == trigger_type):
                triggers.append(trigger)
        return triggers

    def _save_trigger(self, trigger: Trigger) -> None:
        """Save trigger to disk."""
        trigger_file = self.storage_dir / f"{trigger.id}.json"

        data = {
            "id": trigger.id,
            "name": trigger.name,
            "trigger_type": trigger.trigger_type.value,
            "action": trigger.action,
            "conditions": trigger.conditions,
            "enabled": trigger.enabled,
            "created_at": trigger.created_at,
            "last_triggered_at": trigger.last_triggered_at,
            "trigger_count": trigger.trigger_count,
        }

        with open(trigger_file, "w") as f:
            json.dump(data, f, indent=2)

        os.chmod(trigger_file, 0o600)
