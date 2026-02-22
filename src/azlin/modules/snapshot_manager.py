"""VM Snapshot Management Module.

This module provides scheduled snapshot functionality for Azure VMs.
Implements event-driven snapshot management with VM tags for metadata storage.

Design Philosophy:
- Manual trigger via CLI (no background daemon)
- VM tags for schedule metadata (no external database)
- FIFO retention with configurable snapshot count
- Simple, zero-BS implementation
"""

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from azlin.azure_cli_executor import run_az_command

logger = logging.getLogger(__name__)


class SnapshotError(Exception):
    """Raised when snapshot operations fail."""

    pass


@dataclass
class SnapshotSchedule:
    """Snapshot schedule configuration stored in VM tags."""

    enabled: bool
    interval_hours: int
    keep_count: int
    last_snapshot_time: datetime | None = None

    def to_tag_value(self) -> str:
        """Serialize to tag value (JSON string)."""
        data = {
            "enabled": self.enabled,
            "interval_hours": self.interval_hours,
            "keep_count": self.keep_count,
            "last_snapshot_time": (
                self.last_snapshot_time.isoformat() if self.last_snapshot_time else None
            ),
        }
        return json.dumps(data)

    @classmethod
    def from_tag_value(cls, tag_value: str) -> "SnapshotSchedule":
        """Deserialize from tag value (JSON string)."""
        try:
            data = json.loads(tag_value)
            last_snapshot = None
            if data.get("last_snapshot_time"):
                last_snapshot = datetime.fromisoformat(data["last_snapshot_time"])

            return cls(
                enabled=data.get("enabled", True),
                interval_hours=data.get("interval_hours", 24),
                keep_count=data.get("keep_count", 2),
                last_snapshot_time=last_snapshot,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise SnapshotError(f"Failed to parse snapshot schedule from tag: {e}") from e


@dataclass
class SnapshotInfo:
    """Information about a VM snapshot."""

    name: str
    resource_group: str
    source_vm: str
    creation_time: datetime
    size_gb: int | None = None


class SnapshotManager:
    """Manages VM snapshot operations and scheduling."""

    SCHEDULE_TAG_KEY = "azlin:snapshot-schedule"

    # Azure naming validation patterns
    VM_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
    RG_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.\(\)]{1,90}$")

    @classmethod
    def _validate_vm_name(cls, vm_name: str) -> None:
        """Validate VM name against Azure naming rules.

        Args:
            vm_name: VM name to validate

        Raises:
            SnapshotError: If VM name is invalid
        """
        if not vm_name or not cls.VM_NAME_PATTERN.match(vm_name):
            raise SnapshotError(
                f"Invalid VM name: {vm_name}. Must be 1-64 alphanumeric/hyphen/underscore characters"
            )

    @classmethod
    def _validate_resource_group(cls, rg_name: str) -> None:
        """Validate resource group name against Azure naming rules.

        Args:
            rg_name: Resource group name to validate

        Raises:
            SnapshotError: If resource group name is invalid
        """
        if not rg_name or not cls.RG_NAME_PATTERN.match(rg_name):
            raise SnapshotError(f"Invalid resource group name: {rg_name}")

    @classmethod
    def enable_snapshots(
        cls,
        vm_name: str,
        resource_group: str,
        interval_hours: int,
        keep_count: int = 2,
    ) -> None:
        """Enable scheduled snapshots for a VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            interval_hours: Hours between snapshots
            keep_count: Number of snapshots to keep (default 2)

        Raises:
            SnapshotError: If enable operation fails
        """
        cls._validate_vm_name(vm_name)
        cls._validate_resource_group(resource_group)

        if interval_hours < 1:
            raise SnapshotError("Interval must be at least 1 hour")
        if keep_count < 1:
            raise SnapshotError("Keep count must be at least 1")

        schedule = SnapshotSchedule(
            enabled=True,
            interval_hours=interval_hours,
            keep_count=keep_count,
            last_snapshot_time=None,
        )

        cls._set_vm_tag(vm_name, resource_group, cls.SCHEDULE_TAG_KEY, schedule.to_tag_value())
        logger.info(
            f"Enabled snapshots for {vm_name}: every {interval_hours}h, keeping {keep_count}"
        )

    @classmethod
    def disable_snapshots(cls, vm_name: str, resource_group: str) -> None:
        """Disable scheduled snapshots for a VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Raises:
            SnapshotError: If disable operation fails
        """
        cls._validate_vm_name(vm_name)
        cls._validate_resource_group(resource_group)

        cls._remove_vm_tag(vm_name, resource_group, cls.SCHEDULE_TAG_KEY)
        logger.info(f"Disabled snapshots for {vm_name}")

    @classmethod
    def get_snapshot_schedule(cls, vm_name: str, resource_group: str) -> SnapshotSchedule | None:
        """Get snapshot schedule for a VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            SnapshotSchedule if configured, None otherwise

        Raises:
            SnapshotError: If retrieval fails
        """
        tag_value = cls._get_vm_tag(vm_name, resource_group, cls.SCHEDULE_TAG_KEY)
        if not tag_value:
            return None

        return SnapshotSchedule.from_tag_value(tag_value)

    @classmethod
    def sync_snapshots(cls, resource_group: str, vm_name: str | None = None) -> dict[str, Any]:
        """Sync snapshots for VMs based on their schedules.

        This is the main entry point called by CLI.
        Checks all VMs (or specific VM) and creates snapshots if needed.

        Args:
            resource_group: Resource group name
            vm_name: Optional specific VM name

        Returns:
            Dictionary with sync results

        Raises:
            SnapshotError: If sync operation fails
        """
        results = {"checked": 0, "created": 0, "cleaned": 0, "skipped": 0}

        # Get VMs to check
        vms = [vm_name] if vm_name else cls._list_vms_with_snapshots(resource_group)

        for vm in vms:
            results["checked"] += 1

            try:
                schedule = cls.get_snapshot_schedule(vm, resource_group)
                if not schedule or not schedule.enabled:
                    results["skipped"] += 1
                    continue

                # Check if snapshot is needed
                if cls._needs_snapshot(schedule):
                    snapshot_name = cls._create_snapshot(vm, resource_group)
                    results["created"] += 1
                    logger.info(f"Created snapshot {snapshot_name} for {vm}")

                    # Update last snapshot time (timezone-aware)
                    schedule.last_snapshot_time = datetime.now(UTC)
                    cls._set_vm_tag(
                        vm, resource_group, cls.SCHEDULE_TAG_KEY, schedule.to_tag_value()
                    )

                    # Clean up old snapshots
                    deleted = cls._cleanup_old_snapshots(vm, resource_group, schedule.keep_count)
                    results["cleaned"] += deleted

            except Exception as e:
                logger.error(f"Failed to sync snapshots for {vm}: {e}")
                # Continue with other VMs

        return results

    @classmethod
    def create_snapshot(cls, vm_name: str, resource_group: str) -> SnapshotInfo:
        """Create a snapshot manually (public API for CLI).

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            SnapshotInfo object

        Raises:
            SnapshotError: If snapshot creation fails
        """
        cls._validate_vm_name(vm_name)
        cls._validate_resource_group(resource_group)

        snapshot_name = cls._create_snapshot(vm_name, resource_group)

        # Get snapshot info to return
        snapshots = cls._list_vm_snapshots(vm_name, resource_group)
        for snapshot in snapshots:
            if snapshot.name == snapshot_name:
                return snapshot

        raise SnapshotError(f"Created snapshot {snapshot_name} but failed to retrieve info")

    @classmethod
    def list_snapshots(cls, vm_name: str, resource_group: str) -> list[SnapshotInfo]:
        """List snapshots for a VM (public API for CLI).

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            List of SnapshotInfo objects

        Raises:
            SnapshotError: If listing fails
        """
        cls._validate_vm_name(vm_name)
        cls._validate_resource_group(resource_group)
        return cls._list_vm_snapshots(vm_name, resource_group)

    @classmethod
    def delete_snapshot(cls, snapshot_name: str, resource_group: str) -> None:
        """Delete a snapshot (public API for CLI).

        Args:
            snapshot_name: Snapshot name
            resource_group: Resource group name

        Raises:
            SnapshotError: If deletion fails
        """
        cls._validate_resource_group(resource_group)
        cls._delete_snapshot(snapshot_name, resource_group)

    @classmethod
    def get_snapshot_cost_estimate(cls, size_gb: int, days: int = 30) -> float:
        """Estimate monthly snapshot storage cost (public API for CLI).

        Args:
            size_gb: Snapshot size in GB
            days: Number of days to estimate (default: 30)

        Returns:
            Estimated cost in USD
        """
        # Azure snapshot storage pricing: ~$0.05 per GB-month for standard storage
        # This is an approximation - actual costs vary by region and storage type
        cost_per_gb_month = 0.05
        return size_gb * cost_per_gb_month * (days / 30.0)

    @classmethod
    def restore_snapshot(cls, vm_name: str, snapshot_name: str, resource_group: str) -> None:
        """Restore a VM from a snapshot (public API for CLI).

        This operation:
        1. Stops the VM
        2. Creates a new disk from the snapshot
        3. Swaps the VM's OS disk with the new disk
        4. Starts the VM

        Args:
            vm_name: VM name
            snapshot_name: Snapshot name to restore from
            resource_group: Resource group name

        Raises:
            SnapshotError: If restore fails
        """
        cls._validate_vm_name(vm_name)
        cls._validate_resource_group(resource_group)

        try:
            # Stop VM
            stop_cmd = [
                "az",
                "vm",
                "stop",
                "--name",
                vm_name,
                "--resource-group",
                resource_group,
            ]
            subprocess.run(stop_cmd, capture_output=True, text=True, timeout=300, check=True)

            # Create disk from snapshot
            disk_name = f"{vm_name}-restored-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            create_disk_cmd = [
                "az",
                "disk",
                "create",
                "--name",
                disk_name,
                "--resource-group",
                resource_group,
                "--source",
                snapshot_name,
                "--output",
                "json",
            ]
            result = subprocess.run(
                create_disk_cmd, capture_output=True, text=True, timeout=300, check=True
            )
            disk_data = json.loads(result.stdout)
            disk_id = disk_data["id"]

            # Attach new disk as OS disk
            attach_cmd = [
                "az",
                "vm",
                "update",
                "--name",
                vm_name,
                "--resource-group",
                resource_group,
                "--os-disk",
                disk_id,
            ]
            subprocess.run(attach_cmd, capture_output=True, text=True, timeout=300, check=True)

            # Start VM
            start_cmd = [
                "az",
                "vm",
                "start",
                "--name",
                vm_name,
                "--resource-group",
                resource_group,
            ]
            subprocess.run(start_cmd, capture_output=True, text=True, timeout=300, check=True)

        except subprocess.CalledProcessError as e:
            raise SnapshotError(f"Failed to restore snapshot: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise SnapshotError("Snapshot restore timed out") from e
        except json.JSONDecodeError as e:
            raise SnapshotError(f"Failed to parse restore response: {e}") from e

    @classmethod
    def _needs_snapshot(cls, schedule: SnapshotSchedule) -> bool:
        """Check if a new snapshot is needed based on schedule.

        Args:
            schedule: Snapshot schedule configuration

        Returns:
            True if snapshot is needed
        """
        if not schedule.last_snapshot_time:
            return True  # Never taken snapshot

        # Use timezone-aware datetime for comparison
        now = datetime.now(UTC)

        # Ensure last_snapshot_time is timezone-aware
        last_time = schedule.last_snapshot_time
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=UTC)

        elapsed = now - last_time
        threshold = timedelta(hours=schedule.interval_hours)

        return elapsed >= threshold

    @classmethod
    def _create_snapshot(cls, vm_name: str, resource_group: str) -> str:
        """Create a snapshot of VM's OS disk.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            Snapshot name

        Raises:
            SnapshotError: If snapshot creation fails
        """
        # Generate snapshot name with timestamp
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        snapshot_name = f"{vm_name}-snapshot-{timestamp}"

        # Get VM's OS disk ID
        disk_id = cls._get_vm_os_disk_id(vm_name, resource_group)

        # Create snapshot using Azure CLI
        try:
            cmd = [
                "az",
                "snapshot",
                "create",
                "--name",
                snapshot_name,
                "--resource-group",
                resource_group,
                "--source",
                disk_id,
                "--output",
                "json",
            ]

            result = run_az_command(cmd, timeout=300)

            snapshot_data = json.loads(result.stdout)
            logger.debug(f"Created snapshot: {snapshot_data['id']}")

            return snapshot_name

        except subprocess.CalledProcessError as e:
            raise SnapshotError(f"Failed to create snapshot: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise SnapshotError("Snapshot creation timed out") from e
        except json.JSONDecodeError as e:
            raise SnapshotError(f"Failed to parse snapshot creation response: {e}") from e

    @classmethod
    def _get_vm_os_disk_id(cls, vm_name: str, resource_group: str) -> str:
        """Get VM's OS disk ID.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            OS disk resource ID

        Raises:
            SnapshotError: If retrieval fails
        """
        try:
            cmd = [
                "az",
                "vm",
                "show",
                "--name",
                vm_name,
                "--resource-group",
                resource_group,
                "--query",
                "storageProfile.osDisk.managedDisk.id",
                "--output",
                "tsv",
            ]

            result = run_az_command(cmd, timeout=30)

            disk_id = result.stdout.strip()
            if not disk_id:
                raise SnapshotError(f"VM {vm_name} has no OS disk")

            return disk_id

        except subprocess.CalledProcessError as e:
            raise SnapshotError(f"Failed to get VM OS disk: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise SnapshotError("Get VM OS disk timed out") from e

    @classmethod
    def _cleanup_old_snapshots(cls, vm_name: str, resource_group: str, keep_count: int) -> int:
        """Delete old snapshots beyond keep_count (FIFO).

        Args:
            vm_name: VM name
            resource_group: Resource group name
            keep_count: Number of snapshots to keep

        Returns:
            Number of snapshots deleted

        Raises:
            SnapshotError: If cleanup fails
        """
        # List all snapshots for this VM
        snapshots = cls._list_vm_snapshots(vm_name, resource_group)

        # Sort by creation time (oldest first)
        snapshots.sort(key=lambda s: s.creation_time)

        # Delete oldest beyond keep_count
        to_delete = snapshots[:-keep_count] if len(snapshots) > keep_count else []

        deleted_count = 0
        for snapshot in to_delete:
            try:
                cls._delete_snapshot(snapshot.name, resource_group)
                deleted_count += 1
                logger.debug(f"Deleted old snapshot: {snapshot.name}")
            except Exception as e:
                logger.warning(f"Failed to delete snapshot {snapshot.name}: {e}")
                # Continue with other snapshots

        return deleted_count

    @classmethod
    def _list_vm_snapshots(cls, vm_name: str, resource_group: str) -> list[SnapshotInfo]:
        """List all snapshots for a VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            List of SnapshotInfo objects

        Raises:
            SnapshotError: If listing fails
        """
        try:
            # List ALL snapshots, then filter in Python (prevents JMESPath injection)
            cmd = [
                "az",
                "snapshot",
                "list",
                "--resource-group",
                resource_group,
                "--output",
                "json",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

            all_snapshots = json.loads(result.stdout)

            # Filter snapshots in Python (safe from injection)
            expected_prefix = f"{vm_name}-snapshot-"
            snapshots_data = [
                snap for snap in all_snapshots if snap.get("name", "").startswith(expected_prefix)
            ]

            snapshots = []
            for snap in snapshots_data:
                creation_time = datetime.fromisoformat(snap["timeCreated"].replace("Z", "+00:00"))
                snapshots.append(
                    SnapshotInfo(
                        name=snap["name"],
                        resource_group=resource_group,
                        source_vm=vm_name,
                        creation_time=creation_time,
                        size_gb=snap.get("diskSizeGb"),
                    )
                )

            return snapshots

        except subprocess.CalledProcessError as e:
            raise SnapshotError(f"Failed to list snapshots: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise SnapshotError("List snapshots timed out") from e
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise SnapshotError(f"Failed to parse snapshot list: {e}") from e

    @classmethod
    def _delete_snapshot(cls, snapshot_name: str, resource_group: str) -> None:
        """Delete a snapshot.

        Args:
            snapshot_name: Snapshot name
            resource_group: Resource group name

        Raises:
            SnapshotError: If deletion fails
        """
        try:
            cmd = [
                "az",
                "snapshot",
                "delete",
                "--name",
                snapshot_name,
                "--resource-group",
                resource_group,
                "--yes",
            ]

            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            )

            logger.debug(f"Deleted snapshot: {snapshot_name}")

        except subprocess.CalledProcessError as e:
            raise SnapshotError(f"Failed to delete snapshot: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise SnapshotError("Snapshot deletion timed out") from e

    @classmethod
    def _list_vms_with_snapshots(cls, resource_group: str) -> list[str]:
        """List all VMs that have snapshot schedules configured.

        Args:
            resource_group: Resource group name

        Returns:
            List of VM names

        Raises:
            SnapshotError: If listing fails
        """
        try:
            cmd = [
                "az",
                "vm",
                "list",
                "--resource-group",
                resource_group,
                "--query",
                f'[?tags."{cls.SCHEDULE_TAG_KEY}" != null].name',
                "--output",
                "json",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

            return json.loads(result.stdout)

        except subprocess.CalledProcessError as e:
            raise SnapshotError(f"Failed to list VMs: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise SnapshotError("List VMs timed out") from e
        except json.JSONDecodeError as e:
            raise SnapshotError(f"Failed to parse VM list: {e}") from e

    @classmethod
    def _get_vm_tag(cls, vm_name: str, resource_group: str, tag_key: str) -> str | None:
        """Get a specific tag value from a VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            tag_key: Tag key to retrieve

        Returns:
            Tag value or None if not found

        Raises:
            SnapshotError: If retrieval fails
        """
        try:
            cmd = [
                "az",
                "vm",
                "show",
                "--name",
                vm_name,
                "--resource-group",
                resource_group,
                "--query",
                f'tags."{tag_key}"',
                "--output",
                "tsv",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

            tag_value = result.stdout.strip()
            return tag_value if tag_value else None

        except subprocess.CalledProcessError as e:
            raise SnapshotError(f"Failed to get VM tag: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise SnapshotError("Get VM tag timed out") from e

    @classmethod
    def _set_vm_tag(cls, vm_name: str, resource_group: str, tag_key: str, tag_value: str) -> None:
        """Set a tag on a VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            tag_key: Tag key
            tag_value: Tag value

        Raises:
            SnapshotError: If setting fails
        """
        try:
            cmd = [
                "az",
                "vm",
                "update",
                "--name",
                vm_name,
                "--resource-group",
                resource_group,
                "--set",
                f"tags.{tag_key}={tag_value}",
            ]

            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )

            logger.debug(f"Set tag {tag_key} on VM {vm_name}")

        except subprocess.CalledProcessError as e:
            raise SnapshotError(f"Failed to set VM tag: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise SnapshotError("Set VM tag timed out") from e

    @classmethod
    def _remove_vm_tag(cls, vm_name: str, resource_group: str, tag_key: str) -> None:
        """Remove a tag from a VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            tag_key: Tag key to remove

        Raises:
            SnapshotError: If removal fails
        """
        try:
            cmd = [
                "az",
                "vm",
                "update",
                "--name",
                vm_name,
                "--resource-group",
                resource_group,
                "--remove",
                f"tags.{tag_key}",
            ]

            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )

            logger.debug(f"Removed tag {tag_key} from VM {vm_name}")

        except subprocess.CalledProcessError as e:
            raise SnapshotError(f"Failed to remove VM tag: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise SnapshotError("Remove VM tag timed out") from e


__all__ = ["SnapshotError", "SnapshotInfo", "SnapshotManager", "SnapshotSchedule"]
