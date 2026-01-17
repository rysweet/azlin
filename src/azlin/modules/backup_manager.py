"""Automated backup management with retention policies.

Philosophy:
- Single responsibility: backup automation and retention
- Extends SnapshotManager for core snapshot operations
- Self-contained and regeneratable
- Security-first: input validation, no credentials in code

Public API (the "studs"):
    BackupManager: Main backup orchestration class
    BackupSchedule: Schedule configuration dataclass
    BackupInfo: Backup metadata dataclass
    configure_backup(): Configure backup schedule for VM
    trigger_backup(): Execute scheduled backup operation
    list_backups(): List all backups with retention info
    cleanup_expired_backups(): Remove backups beyond retention policies
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from azlin.modules.snapshot_manager import SnapshotManager

logger = logging.getLogger(__name__)


class BackupError(Exception):
    """Raised when backup operations fail."""

    pass


@dataclass
class BackupSchedule:
    """Backup schedule configuration stored in VM tags."""

    enabled: bool
    daily_retention: int  # Days to keep daily backups
    weekly_retention: int  # Weeks to keep weekly backups
    monthly_retention: int  # Months to keep monthly backups
    last_daily: datetime | None = None
    last_weekly: datetime | None = None
    last_monthly: datetime | None = None
    cross_region_enabled: bool = False
    target_region: str | None = None

    def to_tag_value(self) -> str:
        """Serialize to tag value (JSON string)."""
        data = {
            "enabled": self.enabled,
            "daily_retention": self.daily_retention,
            "weekly_retention": self.weekly_retention,
            "monthly_retention": self.monthly_retention,
            "last_daily": self.last_daily.isoformat() if self.last_daily else None,
            "last_weekly": self.last_weekly.isoformat() if self.last_weekly else None,
            "last_monthly": self.last_monthly.isoformat() if self.last_monthly else None,
            "cross_region_enabled": self.cross_region_enabled,
            "target_region": self.target_region,
        }
        return json.dumps(data)

    @classmethod
    def from_tag_value(cls, tag_value: str) -> "BackupSchedule":
        """Deserialize from tag value (JSON string)."""
        try:
            data = json.loads(tag_value)

            # Parse datetime fields
            last_daily = None
            if data.get("last_daily"):
                last_daily = datetime.fromisoformat(data["last_daily"])

            last_weekly = None
            if data.get("last_weekly"):
                last_weekly = datetime.fromisoformat(data["last_weekly"])

            last_monthly = None
            if data.get("last_monthly"):
                last_monthly = datetime.fromisoformat(data["last_monthly"])

            return cls(
                enabled=data.get("enabled", True),
                daily_retention=data.get("daily_retention", 7),
                weekly_retention=data.get("weekly_retention", 4),
                monthly_retention=data.get("monthly_retention", 12),
                last_daily=last_daily,
                last_weekly=last_weekly,
                last_monthly=last_monthly,
                cross_region_enabled=data.get("cross_region_enabled", False),
                target_region=data.get("target_region"),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise BackupError(f"Failed to parse backup schedule from tag: {e}") from e


@dataclass
class BackupInfo:
    """Backup metadata with retention tier."""

    snapshot_name: str
    vm_name: str
    resource_group: str
    creation_time: datetime
    retention_tier: str  # daily, weekly, monthly
    replicated: bool = False
    verified: bool = False
    size_gb: int | None = None


class BackupManager:
    """Automated backup management with tiered retention."""

    BACKUP_SCHEDULE_TAG = "azlin:backup-schedule"
    BACKUP_TIER_TAG = "azlin:backup-tier"

    @classmethod
    def configure_backup(
        cls,
        vm_name: str,
        resource_group: str,
        daily_retention: int = 7,
        weekly_retention: int = 4,
        monthly_retention: int = 12,
        cross_region: bool = False,
        target_region: str | None = None,
    ) -> None:
        """Configure backup schedule with retention policies.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            daily_retention: Days to keep daily backups (default: 7)
            weekly_retention: Weeks to keep weekly backups (default: 4)
            monthly_retention: Months to keep monthly backups (default: 12)
            cross_region: Enable cross-region replication (default: False)
            target_region: Target region for cross-region replication

        Raises:
            BackupError: If configuration fails
        """
        # Input validation
        if not vm_name or len(vm_name) > 64:
            raise BackupError("Invalid VM name: must be 1-64 characters")
        if not resource_group:
            raise BackupError("Invalid resource group: cannot be empty")
        if daily_retention <= 0:
            raise BackupError("daily_retention must be positive")
        if weekly_retention <= 0:
            raise BackupError("weekly_retention must be positive")
        if monthly_retention <= 0:
            raise BackupError("monthly_retention must be positive")
        if cross_region and not target_region:
            raise BackupError("target_region required when cross_region is enabled")

        schedule = BackupSchedule(
            enabled=True,
            daily_retention=daily_retention,
            weekly_retention=weekly_retention,
            monthly_retention=monthly_retention,
            cross_region_enabled=cross_region,
            target_region=target_region,
        )

        cls._set_vm_tag(vm_name, resource_group, cls.BACKUP_SCHEDULE_TAG, schedule.to_tag_value())
        logger.info(f"Configured backup schedule for {vm_name}")

    @classmethod
    def trigger_backup(
        cls,
        vm_name: str,
        resource_group: str,
        force_tier: str | None = None,
    ) -> BackupInfo:
        """Execute scheduled backup with appropriate retention tier.

        Determines tier based on schedule:
        - Daily: Every day
        - Weekly: First backup of each week (Sunday)
        - Monthly: First backup of each month (1st day)

        Args:
            vm_name: VM name
            resource_group: Resource group name
            force_tier: Force specific retention tier (daily, weekly, monthly)

        Returns:
            BackupInfo object

        Raises:
            BackupError: If backup fails
        """
        # Get backup schedule
        tag_value = cls._get_vm_tag(vm_name, resource_group, cls.BACKUP_SCHEDULE_TAG)
        if not tag_value:
            raise BackupError("No backup schedule configured for this VM")

        schedule = BackupSchedule.from_tag_value(tag_value)
        if not schedule.enabled:
            raise BackupError("Backup schedule is disabled for this VM")

        # Determine retention tier
        if force_tier:
            if force_tier not in ("daily", "weekly", "monthly"):
                raise BackupError(f"Invalid retention tier: {force_tier}")
            tier = force_tier
        else:
            tier = cls._determine_tier(schedule)

        # Create backup snapshot
        snapshot_name = cls._create_backup_snapshot(vm_name, resource_group, tier)

        # Update schedule with new last backup time
        now = datetime.now(UTC)
        if tier == "daily":
            schedule.last_daily = now
        elif tier == "weekly":
            schedule.last_weekly = now
        elif tier == "monthly":
            schedule.last_monthly = now

        # Update VM tag with new schedule (best effort)
        try:
            cls._set_vm_tag(
                vm_name, resource_group, cls.BACKUP_SCHEDULE_TAG, schedule.to_tag_value()
            )
        except Exception as e:
            logger.warning(f"Failed to update backup schedule tag (non-fatal): {e}")

        # Cleanup expired backups (best effort - don't fail backup on cleanup errors)
        try:
            cls.cleanup_expired_backups(vm_name, resource_group)
        except Exception as e:
            logger.warning(f"Backup cleanup failed (non-fatal): {e}")

        # Return backup info
        return BackupInfo(
            snapshot_name=snapshot_name,
            vm_name=vm_name,
            resource_group=resource_group,
            creation_time=now,
            retention_tier=tier,
        )

    @classmethod
    def list_backups(
        cls,
        vm_name: str,
        resource_group: str,
        tier: str | None = None,
    ) -> list[BackupInfo]:
        """List all backups with retention tier information.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            tier: Optional filter by retention tier (daily, weekly, monthly)

        Returns:
            List of BackupInfo objects

        Raises:
            BackupError: If listing fails
        """
        # List all snapshots for this VM
        snapshots = SnapshotManager.list_snapshots(vm_name, resource_group)

        backups = []
        for snapshot in snapshots:
            # Check if this snapshot is a backup (has backup tier tag)
            tags = getattr(snapshot, "tags", {})
            if not tags or cls.BACKUP_TIER_TAG not in tags:
                continue

            backup_tier = tags[cls.BACKUP_TIER_TAG]

            # Filter by tier if specified
            if tier and backup_tier != tier:
                continue

            backups.append(
                BackupInfo(
                    snapshot_name=snapshot.name,
                    vm_name=vm_name,
                    resource_group=resource_group,
                    creation_time=snapshot.creation_time,
                    retention_tier=backup_tier,
                    size_gb=snapshot.size_gb,
                )
            )

        return backups

    @classmethod
    def cleanup_expired_backups(
        cls,
        vm_name: str,
        resource_group: str,
    ) -> dict[str, int]:
        """Remove backups beyond retention policies.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            Dictionary with counts: {"daily": N, "weekly": M, "monthly": K}

        Raises:
            BackupError: If cleanup fails
        """
        # Get backup schedule
        tag_value = cls._get_vm_tag(vm_name, resource_group, cls.BACKUP_SCHEDULE_TAG)
        if not tag_value:
            return {"daily": 0, "weekly": 0, "monthly": 0}

        schedule = BackupSchedule.from_tag_value(tag_value)

        # List all backups
        backups = cls.list_backups(vm_name, resource_group)

        # Group by tier
        daily_backups = [b for b in backups if b.retention_tier == "daily"]
        weekly_backups = [b for b in backups if b.retention_tier == "weekly"]
        monthly_backups = [b for b in backups if b.retention_tier == "monthly"]

        # Sort by creation time (newest first)
        daily_backups.sort(key=lambda b: b.creation_time, reverse=True)
        weekly_backups.sort(key=lambda b: b.creation_time, reverse=True)
        monthly_backups.sort(key=lambda b: b.creation_time, reverse=True)

        # Calculate retention cutoffs
        now = datetime.now(UTC)
        daily_cutoff = now - timedelta(days=schedule.daily_retention)
        weekly_cutoff = now - timedelta(weeks=schedule.weekly_retention)
        monthly_cutoff = now - timedelta(days=schedule.monthly_retention * 30)

        deleted_count = {"daily": 0, "weekly": 0, "monthly": 0}

        # Delete expired daily backups
        for backup in daily_backups:
            if backup.creation_time < daily_cutoff:
                try:
                    SnapshotManager.delete_snapshot(backup.snapshot_name, resource_group)
                    deleted_count["daily"] += 1
                    logger.debug(f"Deleted expired daily backup: {backup.snapshot_name}")
                except Exception as e:
                    logger.warning(f"Failed to delete backup {backup.snapshot_name}: {e}")
                    # Continue with other backups

        # Delete expired weekly backups
        for backup in weekly_backups:
            if backup.creation_time < weekly_cutoff:
                try:
                    SnapshotManager.delete_snapshot(backup.snapshot_name, resource_group)
                    deleted_count["weekly"] += 1
                    logger.debug(f"Deleted expired weekly backup: {backup.snapshot_name}")
                except Exception as e:
                    logger.warning(f"Failed to delete backup {backup.snapshot_name}: {e}")

        # Delete expired monthly backups
        for backup in monthly_backups:
            if backup.creation_time < monthly_cutoff:
                try:
                    SnapshotManager.delete_snapshot(backup.snapshot_name, resource_group)
                    deleted_count["monthly"] += 1
                    logger.debug(f"Deleted expired monthly backup: {backup.snapshot_name}")
                except Exception as e:
                    logger.warning(f"Failed to delete backup {backup.snapshot_name}: {e}")

        return deleted_count

    @classmethod
    def _determine_tier(cls, schedule: BackupSchedule) -> str:
        """Determine retention tier for this backup.

        Logic:
        - First backup ever: Always daily
        - Monthly: First backup of each month (day == 1 and last_monthly not set for this month)
        - Weekly: First backup of each week (Sunday, weekday == 6 and last_weekly not set for this week)
        - Daily: All other backups

        Args:
            schedule: Backup schedule configuration

        Returns:
            Retention tier (daily, weekly, monthly)
        """
        now = datetime.now(UTC)

        # First backup ever? Always daily
        if not schedule.last_daily and not schedule.last_weekly and not schedule.last_monthly:
            return "daily"

        # First backup of month? (day == 1 AND haven't done monthly this month)
        if now.day == 1 and (not schedule.last_monthly or schedule.last_monthly.month != now.month):
            return "monthly"

        # First backup of week? (Sunday = 6 in Python weekday() AND haven't done weekly this week)
        if now.weekday() == 6 and (
            not schedule.last_weekly or (now - schedule.last_weekly).days >= 7
        ):
            return "weekly"

        # Default to daily
        return "daily"

    @classmethod
    def _create_backup_snapshot(cls, vm_name: str, resource_group: str, tier: str) -> str:
        """Create backup snapshot using SnapshotManager and tag with tier.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            tier: Retention tier (daily, weekly, monthly)

        Returns:
            Snapshot name

        Raises:
            BackupError: If snapshot creation fails
        """
        try:
            # Use SnapshotManager to create snapshot
            snapshot_info = SnapshotManager.create_snapshot(vm_name, resource_group)

            # Tag snapshot with backup tier
            cls._tag_snapshot_as_backup(snapshot_info.name, resource_group, tier)

            return snapshot_info.name

        except Exception as e:
            raise BackupError(f"Failed to create backup snapshot: {e}") from e

    @classmethod
    def _tag_snapshot_as_backup(cls, snapshot_name: str, resource_group: str, tier: str) -> None:
        """Tag snapshot with backup tier.

        Args:
            snapshot_name: Snapshot name
            resource_group: Resource group name
            tier: Retention tier (daily, weekly, monthly)

        Raises:
            BackupError: If tagging fails
        """
        import subprocess

        try:
            cmd = [
                "az",
                "snapshot",
                "update",
                "--name",
                snapshot_name,
                "--resource-group",
                resource_group,
                "--set",
                f"tags.{cls.BACKUP_TIER_TAG}={tier}",
            ]

            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )

            logger.debug(f"Tagged snapshot {snapshot_name} as {tier} backup")

        except subprocess.CalledProcessError as e:
            raise BackupError(f"Failed to tag snapshot: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise BackupError("Snapshot tagging timed out") from e

    @classmethod
    def _get_vm_tag(cls, vm_name: str, resource_group: str, tag_key: str) -> str | None:
        """Get a specific tag value from a VM (delegates to SnapshotManager)."""
        return SnapshotManager._get_vm_tag(vm_name, resource_group, tag_key)

    @classmethod
    def _set_vm_tag(cls, vm_name: str, resource_group: str, tag_key: str, tag_value: str) -> None:
        """Set a tag on a VM (delegates to SnapshotManager)."""
        SnapshotManager._set_vm_tag(vm_name, resource_group, tag_key, tag_value)


__all__ = ["BackupError", "BackupInfo", "BackupManager", "BackupSchedule"]
