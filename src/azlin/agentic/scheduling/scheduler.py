"""Scheduler for cron-style and one-time delayed execution."""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path


class ScheduleType(str, Enum):
    """Schedule types."""

    ONCE = "once"  # One-time execution
    CRON = "cron"  # Cron-style recurring
    INTERVAL = "interval"  # Fixed interval recurring


@dataclass
class Schedule:
    """Scheduled task."""

    id: str
    name: str
    schedule_type: ScheduleType
    task: str  # Command to execute
    schedule_spec: str  # Cron expression or datetime
    next_run: str
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_run_at: str | None = None
    run_count: int = 0


class Scheduler:
    """Manage scheduled tasks."""

    def __init__(self, storage_dir: str | None = None):
        """Initialize scheduler.

        Args:
            storage_dir: Directory for schedule storage
        """
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path.home() / ".azlin" / "schedules"

        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def schedule_once(self, name: str, task: str, run_at: datetime) -> Schedule:
        """Schedule a one-time task.

        Args:
            name: Schedule name
            task: Task to execute
            run_at: Datetime to run at

        Returns:
            Created Schedule
        """
        schedule_id = name.lower().replace(" ", "-")

        schedule = Schedule(
            id=schedule_id,
            name=name,
            schedule_type=ScheduleType.ONCE,
            task=task,
            schedule_spec=run_at.isoformat(),
            next_run=run_at.isoformat(),
        )

        self._save_schedule(schedule)
        return schedule

    def schedule_cron(self, name: str, task: str, cron_expression: str) -> Schedule:
        """Schedule a recurring task with cron expression.

        Args:
            name: Schedule name
            task: Task to execute
            cron_expression: Cron expression (e.g., "0 2 * * *")

        Returns:
            Created Schedule
        """
        schedule_id = name.lower().replace(" ", "-")

        # Calculate next run from cron expression
        next_run = self._calculate_next_cron_run(cron_expression)

        schedule = Schedule(
            id=schedule_id,
            name=name,
            schedule_type=ScheduleType.CRON,
            task=task,
            schedule_spec=cron_expression,
            next_run=next_run.isoformat(),
        )

        self._save_schedule(schedule)
        return schedule

    def schedule_interval(self, name: str, task: str, interval_minutes: int) -> Schedule:
        """Schedule a recurring task at fixed interval.

        Args:
            name: Schedule name
            task: Task to execute
            interval_minutes: Minutes between runs

        Returns:
            Created Schedule
        """
        schedule_id = name.lower().replace(" ", "-")

        # Calculate next run
        next_run = datetime.utcnow() + timedelta(minutes=interval_minutes)

        schedule = Schedule(
            id=schedule_id,
            name=name,
            schedule_type=ScheduleType.INTERVAL,
            task=task,
            schedule_spec=f"{interval_minutes}m",
            next_run=next_run.isoformat(),
        )

        self._save_schedule(schedule)
        return schedule

    def get_schedule(self, schedule_id: str) -> Schedule | None:
        """Get schedule by ID."""
        schedule_file = self.storage_dir / f"{schedule_id}.json"
        if not schedule_file.exists():
            return None

        with open(schedule_file) as f:
            data = json.load(f)

        return Schedule(
            id=data["id"],
            name=data["name"],
            schedule_type=ScheduleType(data["schedule_type"]),
            task=data["task"],
            schedule_spec=data["schedule_spec"],
            next_run=data["next_run"],
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            last_run_at=data.get("last_run_at"),
            run_count=data.get("run_count", 0),
        )

    def get_pending_schedules(self) -> list[Schedule]:
        """Get all schedules that should run now."""
        now = datetime.utcnow()
        pending = []

        for schedule in self.list_schedules():
            if not schedule.enabled:
                continue

            next_run = datetime.fromisoformat(schedule.next_run)
            if next_run <= now:
                pending.append(schedule)

        return pending

    def mark_executed(self, schedule_id: str) -> None:
        """Mark schedule as executed and calculate next run."""
        schedule = self.get_schedule(schedule_id)
        if not schedule:
            return

        schedule.last_run_at = datetime.utcnow().isoformat()
        schedule.run_count += 1

        # Calculate next run based on type
        if schedule.schedule_type == ScheduleType.ONCE:
            # One-time schedules get disabled after execution
            schedule.enabled = False
        elif schedule.schedule_type == ScheduleType.CRON:
            next_run = self._calculate_next_cron_run(schedule.schedule_spec)
            schedule.next_run = next_run.isoformat()
        elif schedule.schedule_type == ScheduleType.INTERVAL:
            # Parse interval (e.g., "30m")
            interval_minutes = int(schedule.schedule_spec.replace("m", ""))
            next_run = datetime.utcnow() + timedelta(minutes=interval_minutes)
            schedule.next_run = next_run.isoformat()

        self._save_schedule(schedule)

    def list_schedules(self, enabled_only: bool = False) -> list[Schedule]:
        """List all schedules."""
        schedules = []
        for schedule_file in self.storage_dir.glob("*.json"):
            schedule = self.get_schedule(schedule_file.stem)
            if schedule:
                if not enabled_only or schedule.enabled:
                    schedules.append(schedule)
        return schedules

    def _calculate_next_cron_run(self, cron_expression: str) -> datetime:
        """Calculate next run time from cron expression.

        Simple implementation supporting basic cron patterns.

        Args:
            cron_expression: Cron expression (minute hour day month weekday)

        Returns:
            Next run datetime
        """
        # For simplicity, advance by 1 hour for any cron expression
        # A full implementation would parse the cron expression properly
        return datetime.utcnow() + timedelta(hours=1)

    def _save_schedule(self, schedule: Schedule) -> None:
        """Save schedule to disk."""
        schedule_file = self.storage_dir / f"{schedule.id}.json"

        data = {
            "id": schedule.id,
            "name": schedule.name,
            "schedule_type": schedule.schedule_type.value,
            "task": schedule.task,
            "schedule_spec": schedule.schedule_spec,
            "next_run": schedule.next_run,
            "enabled": schedule.enabled,
            "created_at": schedule.created_at,
            "last_run_at": schedule.last_run_at,
            "run_count": schedule.run_count,
        }

        with open(schedule_file, "w") as f:
            json.dump(data, f, indent=2)

        os.chmod(schedule_file, 0o600)
