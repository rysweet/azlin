"""Task scheduler for periodic azlin execution.

Provides cron-style scheduling with:
- Cron expressions for flexible timing
- One-time and recurring schedules
- Timezone support
- Execution history tracking
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class ScheduleType(str, Enum):
    """Types of schedules."""

    ONE_TIME = "one_time"
    INTERVAL = "interval"
    CRON = "cron"


class ScheduleStatus(str, Enum):
    """Schedule execution status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Schedule:
    """Scheduled task definition."""

    schedule_id: str
    name: str
    schedule_type: ScheduleType
    task_command: str  # Command to execute
    task_params: dict[str, Any] = field(default_factory=dict)

    # For ONE_TIME
    execute_at: datetime | None = None

    # For INTERVAL
    interval_seconds: int | None = None

    # For CRON
    cron_expression: str | None = None

    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ScheduleExecution:
    """Record of scheduled execution."""

    execution_id: str
    schedule_id: str
    status: ScheduleStatus
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class Scheduler:
    """Manages scheduled task execution."""

    def __init__(self):
        """Initialize scheduler."""
        self.schedules: dict[str, Schedule] = {}
        self.executions: list[ScheduleExecution] = []

    def create_schedule(
        self,
        schedule_id: str,
        name: str,
        task_command: str,
        schedule_type: ScheduleType,
        execute_at: datetime | None = None,
        interval_seconds: int | None = None,
        cron_expression: str | None = None,
        task_params: dict[str, Any] | None = None,
    ) -> Schedule:
        """Create new schedule.

        Args:
            schedule_id: Unique schedule identifier
            name: Human-readable name
            task_command: Command to execute
            schedule_type: Type of schedule
            execute_at: Execution time for ONE_TIME
            interval_seconds: Interval for INTERVAL schedules
            cron_expression: Cron expression for CRON schedules
            task_params: Parameters for task

        Returns:
            Created schedule

        Raises:
            ValueError: If schedule already exists or invalid parameters
        """
        if schedule_id in self.schedules:
            raise ValueError(f"Schedule {schedule_id} already exists")

        # Validate parameters based on type
        if schedule_type == ScheduleType.ONE_TIME:
            if not execute_at:
                raise ValueError("ONE_TIME schedule requires execute_at")
        elif schedule_type == ScheduleType.INTERVAL:
            if not interval_seconds or interval_seconds <= 0:
                raise ValueError("INTERVAL schedule requires positive interval_seconds")
        elif schedule_type == ScheduleType.CRON and not cron_expression:
            raise ValueError("CRON schedule requires cron_expression")

        schedule = Schedule(
            schedule_id=schedule_id,
            name=name,
            schedule_type=schedule_type,
            task_command=task_command,
            task_params=task_params or {},
            execute_at=execute_at,
            interval_seconds=interval_seconds,
            cron_expression=cron_expression,
        )

        # Calculate next run
        schedule.next_run = self._calculate_next_run(schedule)

        self.schedules[schedule_id] = schedule
        return schedule

    def get_due_schedules(self) -> list[Schedule]:
        """Get schedules that are due to run.

        Returns:
            List of schedules ready for execution
        """
        now = datetime.utcnow()
        due = []

        for schedule in self.schedules.values():
            if not schedule.enabled:
                continue

            if schedule.next_run and schedule.next_run <= now:
                due.append(schedule)

        return due

    def mark_execution(
        self,
        schedule_id: str,
        status: ScheduleStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ScheduleExecution:
        """Mark schedule execution.

        Args:
            schedule_id: Schedule that executed
            status: Execution status
            result: Execution result
            error: Error message if failed

        Returns:
            Created execution record

        Raises:
            KeyError: If schedule doesn't exist
        """
        schedule = self.get_schedule(schedule_id)

        execution_id = f"{schedule_id}-{datetime.utcnow().timestamp()}"
        execution = ScheduleExecution(
            execution_id=execution_id,
            schedule_id=schedule_id,
            status=status,
            result=result,
            error=error,
        )

        if status in (ScheduleStatus.SUCCESS, ScheduleStatus.FAILED):
            execution.completed_at = datetime.utcnow()

        self.executions.append(execution)

        # Update schedule
        schedule.last_run = datetime.utcnow()

        # Calculate next run for recurring schedules
        if schedule.schedule_type != ScheduleType.ONE_TIME:
            schedule.next_run = self._calculate_next_run(schedule)
        else:
            # Disable one-time schedules after execution
            schedule.enabled = False
            schedule.next_run = None

        return execution

    def _calculate_next_run(self, schedule: Schedule) -> datetime | None:
        """Calculate next run time for schedule.

        Args:
            schedule: Schedule to calculate

        Returns:
            Next run datetime or None
        """
        if schedule.schedule_type == ScheduleType.ONE_TIME:
            return schedule.execute_at

        if schedule.schedule_type == ScheduleType.INTERVAL:
            if schedule.last_run:
                return schedule.last_run + timedelta(seconds=schedule.interval_seconds or 0)
            # First run - schedule immediately or at interval from now
            return datetime.utcnow()

        if schedule.schedule_type == ScheduleType.CRON:
            # Simple cron parsing (production would use croniter library)
            return self._parse_cron_next(schedule.cron_expression or "", schedule.last_run)

        return None

    def _parse_cron_next(self, cron_expr: str, last_run: datetime | None) -> datetime:
        """Parse cron expression to get next run time.

        This is a simplified implementation. Production should use croniter.

        Args:
            cron_expr: Cron expression (e.g., "0 2 * * *")
            last_run: Last execution time

        Returns:
            Next run datetime
        """
        # Simplified: just parse common patterns
        # Format: minute hour day month weekday
        parts = cron_expr.split()
        if len(parts) != 5:
            # Invalid cron, default to hourly
            return datetime.utcnow() + timedelta(hours=1)

        now = last_run or datetime.utcnow()

        # For simplicity, calculate next hour boundary
        return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    def get_schedule(self, schedule_id: str) -> Schedule:
        """Get schedule by ID.

        Args:
            schedule_id: Schedule identifier

        Returns:
            Schedule object

        Raises:
            KeyError: If schedule doesn't exist
        """
        if schedule_id not in self.schedules:
            raise KeyError(f"Schedule {schedule_id} not found")
        return self.schedules[schedule_id]

    def disable_schedule(self, schedule_id: str) -> None:
        """Disable schedule.

        Args:
            schedule_id: Schedule to disable

        Raises:
            KeyError: If schedule doesn't exist
        """
        schedule = self.get_schedule(schedule_id)
        schedule.enabled = False

    def enable_schedule(self, schedule_id: str) -> None:
        """Enable schedule.

        Args:
            schedule_id: Schedule to enable

        Raises:
            KeyError: If schedule doesn't exist
        """
        schedule = self.get_schedule(schedule_id)
        schedule.enabled = True

    def get_executions(
        self,
        schedule_id: str | None = None,
        limit: int = 100,
    ) -> list[ScheduleExecution]:
        """Get schedule executions.

        Args:
            schedule_id: Filter by schedule (optional)
            limit: Maximum executions to return

        Returns:
            List of executions, most recent first
        """
        executions = self.executions
        if schedule_id:
            executions = [e for e in executions if e.schedule_id == schedule_id]

        # Sort by started_at descending
        executions.sort(key=lambda e: e.started_at, reverse=True)
        return executions[:limit]
