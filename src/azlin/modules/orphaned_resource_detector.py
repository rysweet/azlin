"""Orphaned Resource Detector Module.

Detect and clean up orphaned managed disks, snapshots, and storage accounts
that are no longer attached to VMs.

Philosophy:
- Self-contained module following brick architecture
- Standard library + subprocess for Azure CLI
- Zero-BS implementation - every function works
- Safety-first approach with multiple checks

Public API:
    OrphanedResourceDetector: Main detection and cleanup class
    OrphanedDisk: Orphaned managed disk data model
    OrphanedSnapshot: Orphaned snapshot data model
    OrphanedStorage: Orphaned storage account data model
    OrphanedResourceReport: Complete scan report
    CleanupResult: Cleanup operation results
"""

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta

# Import existing modules
try:
    from azlin.modules.storage_manager import StorageManager
except ImportError:
    StorageManager = None

try:
    from azlin.config_manager import ConfigManager
except ImportError:
    ConfigManager = None


__all__ = [
    "CleanupResult",
    "OrphanedDisk",
    "OrphanedResourceDetector",
    "OrphanedResourceReport",
    "OrphanedSnapshot",
    "OrphanedStorage",
]


# Cost constants (per GB per month)
PREMIUM_DISK_COST = 0.1536
STANDARD_DISK_COST = 0.04
SNAPSHOT_COST = 0.05
PREMIUM_STORAGE_COST = 0.1536
STANDARD_STORAGE_COST = 0.04


@dataclass
class OrphanedDisk:
    """Orphaned managed disk information.

    Attributes:
        name: Disk name
        resource_group: Resource group containing disk
        size_gb: Disk size in GB
        tier: Disk tier (Premium/Standard)
        created: Creation timestamp
        age_days: Age in days
        last_attached_vm: Last VM it was attached to (if known)
        monthly_cost: Estimated monthly cost
        reason: Why considered orphaned
    """

    name: str
    resource_group: str
    size_gb: int
    tier: str
    created: datetime
    age_days: int
    last_attached_vm: str | None
    monthly_cost: float
    reason: str


@dataclass
class OrphanedSnapshot:
    """Orphaned snapshot information.

    Attributes:
        name: Snapshot name
        resource_group: Resource group containing snapshot
        size_gb: Snapshot size in GB
        created: Creation timestamp
        age_days: Age in days
        source_vm: Source VM name (if known)
        monthly_cost: Estimated monthly cost
        reason: Why considered orphaned
    """

    name: str
    resource_group: str
    size_gb: int
    created: datetime
    age_days: int
    source_vm: str | None
    monthly_cost: float
    reason: str


@dataclass
class OrphanedStorage:
    """Orphaned storage account information.

    Attributes:
        name: Storage account name
        resource_group: Resource group containing storage
        size_gb: Storage size in GB
        tier: Storage tier (Premium/Standard)
        created: Creation timestamp
        age_days: Age in days
        connected_vms: List of connected VMs
        monthly_cost: Estimated monthly cost
        reason: Why considered orphaned
    """

    name: str
    resource_group: str
    size_gb: int
    tier: str
    created: datetime
    age_days: int
    connected_vms: list[str]
    monthly_cost: float
    reason: str


@dataclass
class OrphanedResourceReport:
    """Complete orphaned resources report.

    Attributes:
        disks: List of orphaned disks
        snapshots: List of orphaned snapshots
        storage_accounts: List of orphaned storage accounts
        total_cost_per_month: Total monthly cost of all orphaned resources
        total_size_gb: Total size of all orphaned resources
        scan_date: When scan was performed
    """

    disks: list[OrphanedDisk]
    snapshots: list[OrphanedSnapshot]
    storage_accounts: list[OrphanedStorage]
    total_cost_per_month: float
    total_size_gb: int
    scan_date: datetime


@dataclass
class CleanupResult:
    """Cleanup operation results.

    Attributes:
        deleted_disks: List of deleted disk names
        deleted_snapshots: List of deleted snapshot names
        deleted_storage: List of deleted storage account names
        total_size_freed_gb: Total size freed in GB
        total_cost_saved_per_month: Total monthly cost saved
        errors: List of error messages
        dry_run: Whether this was a dry run
    """

    deleted_disks: list[str]
    deleted_snapshots: list[str]
    deleted_storage: list[str]
    total_size_freed_gb: int
    total_cost_saved_per_month: float
    errors: list[str]
    dry_run: bool


class OrphanedResourceDetector:
    """Detect and clean up orphaned Azure resources.

    Safety mechanisms:
    - Minimum age requirements prevent accidental deletion
    - Respect azlin:keep tags for protected resources
    - Default dry_run=True for safety
    - Check attachment status before deletion

    Usage:
        # Scan for orphaned resources
        report = OrphanedResourceDetector.scan_all(resource_group="test-rg")

        # Clean up (dry run by default)
        result = OrphanedResourceDetector.cleanup_orphaned(
            resource_group="test-rg",
            resource_type="all",
            min_age_days=7
        )

        # Actually delete (requires dry_run=False)
        result = OrphanedResourceDetector.cleanup_orphaned(
            resource_group="test-rg",
            resource_type="disk",
            min_age_days=7,
            dry_run=False
        )
    """

    @classmethod
    def scan_orphaned_disks(cls, resource_group: str, min_age_days: int = 7) -> list[OrphanedDisk]:
        """Scan for orphaned managed disks.

        Disks are considered orphaned if:
        - Not attached to any VM (managedBy is None)
        - Age > min_age_days
        - Does not have azlin:keep tag

        Args:
            resource_group: Resource group to scan
            min_age_days: Minimum age in days (default: 7)

        Returns:
            List of orphaned disks
        """
        try:
            cmd = ["az", "disk", "list", "--resource-group", resource_group, "--output", "json"]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode != 0:
                return []

            disks_data = json.loads(result.stdout)
            orphaned = []

            for disk in disks_data:
                # Check if attached
                if disk.get("managedBy") is not None:
                    continue

                # Check azlin:keep tag
                tags = disk.get("tags", {})
                if tags.get("azlin:keep"):
                    continue

                # Calculate age
                created_str = disk.get("timeCreated", "")
                if created_str:
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    age_days = (datetime.now(created.tzinfo) - created).days
                else:
                    # If no creation time, assume old enough
                    age_days = min_age_days + 1
                    created = datetime.now() - timedelta(days=age_days)

                # Check age
                if age_days < min_age_days:
                    continue

                # Calculate cost
                size_gb = disk.get("diskSizeGb", 0)
                tier = disk.get("sku", {}).get("tier", "Standard")
                if tier == "Premium":
                    monthly_cost = size_gb * PREMIUM_DISK_COST
                else:
                    monthly_cost = size_gb * STANDARD_DISK_COST

                # Determine last attached VM (if available)
                last_vm = (
                    disk.get("managedBy", "").split("/")[-1] if disk.get("managedBy") else None
                )

                orphaned.append(
                    OrphanedDisk(
                        name=disk["name"],
                        resource_group=resource_group,
                        size_gb=size_gb,
                        tier=tier,
                        created=created.replace(tzinfo=None),
                        age_days=age_days,
                        last_attached_vm=last_vm,
                        monthly_cost=monthly_cost,
                        reason=f"Disk unattached for {age_days} days",
                    )
                )

            return orphaned

        except Exception:
            return []

    @classmethod
    def scan_orphaned_snapshots(
        cls, resource_group: str, min_age_days: int = 30
    ) -> list[OrphanedSnapshot]:
        """Scan for orphaned snapshots.

        Snapshots are considered orphaned if:
        - Source VM no longer exists
        - Age > min_age_days
        - Does not have azlin:keep tag

        Args:
            resource_group: Resource group to scan
            min_age_days: Minimum age in days (default: 30)

        Returns:
            List of orphaned snapshots
        """
        try:
            # Get all snapshots
            cmd_snapshots = [
                "az",
                "snapshot",
                "list",
                "--resource-group",
                resource_group,
                "--output",
                "json",
            ]

            result_snapshots = subprocess.run(
                cmd_snapshots, capture_output=True, text=True, timeout=60
            )

            if result_snapshots.returncode != 0:
                return []

            snapshots_data = json.loads(result_snapshots.stdout)

            # Get all VMs to check if source exists
            cmd_vms = ["az", "vm", "list", "--resource-group", resource_group, "--output", "json"]

            result_vms = subprocess.run(cmd_vms, capture_output=True, text=True, timeout=60)

            vm_names = set()
            if result_vms.returncode == 0:
                vms_data = json.loads(result_vms.stdout)
                vm_names = {vm["name"] for vm in vms_data}

            orphaned = []

            for snapshot in snapshots_data:
                # Check azlin:keep tag
                tags = snapshot.get("tags", {})
                if tags.get("azlin:keep"):
                    continue

                # Calculate age
                created_str = snapshot.get("timeCreated", "")
                if created_str:
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    age_days = (datetime.now(created.tzinfo) - created).days
                else:
                    age_days = min_age_days + 1
                    created = datetime.now() - timedelta(days=age_days)

                # Check age
                if age_days < min_age_days:
                    continue

                # Check if source VM exists
                source_vm = tags.get("source-vm")
                if source_vm and source_vm in vm_names:
                    # Source VM still exists, not orphaned
                    continue

                # Calculate cost
                size_gb = snapshot.get("diskSizeGb", 0)
                monthly_cost = size_gb * SNAPSHOT_COST

                orphaned.append(
                    OrphanedSnapshot(
                        name=snapshot["name"],
                        resource_group=resource_group,
                        size_gb=size_gb,
                        created=created.replace(tzinfo=None),
                        age_days=age_days,
                        source_vm=source_vm,
                        monthly_cost=monthly_cost,
                        reason="Source VM no longer exists" if source_vm else "Old snapshot",
                    )
                )

            return orphaned

        except Exception:
            return []

    @classmethod
    def scan_orphaned_storage(
        cls, resource_group: str, min_age_days: int = 30
    ) -> list[OrphanedStorage]:
        """Scan for orphaned storage accounts.

        Storage accounts are considered orphaned if:
        - No connected VMs
        - Age > min_age_days
        - Does not have azlin:keep tag
        - Not marked as shared in config

        Args:
            resource_group: Resource group to scan
            min_age_days: Minimum age in days (default: 30)

        Returns:
            List of orphaned storage accounts
        """
        if not StorageManager:
            return []

        try:
            storage_list = StorageManager.list_storage(resource_group=resource_group)
            orphaned = []

            for storage in storage_list:
                # Check if has connected VMs
                connected_vms = getattr(storage, "connected_vms", [])
                if connected_vms:
                    continue

                # Check azlin:keep tag
                tags = getattr(storage, "tags", {})
                if tags.get("azlin:keep"):
                    continue

                # Check if marked as shared
                if ConfigManager:
                    try:
                        if ConfigManager.is_shared_storage(storage.name):
                            continue
                    except Exception:
                        pass

                # Calculate age
                created = getattr(
                    storage, "created", datetime.now() - timedelta(days=min_age_days + 1)
                )
                age_days = (datetime.now() - created).days

                # Check age
                if age_days < min_age_days:
                    continue

                # Calculate cost
                size_gb = storage.size_gb
                tier = getattr(storage, "tier", "Standard")
                if tier == "Premium":
                    monthly_cost = size_gb * PREMIUM_STORAGE_COST
                else:
                    monthly_cost = size_gb * STANDARD_STORAGE_COST

                orphaned.append(
                    OrphanedStorage(
                        name=storage.name,
                        resource_group=resource_group,
                        size_gb=size_gb,
                        tier=tier,
                        created=created,
                        age_days=age_days,
                        connected_vms=connected_vms,
                        monthly_cost=monthly_cost,
                        reason=f"No VMs connected for {age_days} days",
                    )
                )

            return orphaned

        except Exception:
            return []

    @classmethod
    def scan_all(cls, resource_group: str) -> OrphanedResourceReport:
        """Scan for all orphaned resources.

        Args:
            resource_group: Resource group to scan

        Returns:
            OrphanedResourceReport: Complete scan report
        """
        # Scan all resource types
        disks = cls.scan_orphaned_disks(resource_group=resource_group, min_age_days=7)
        snapshots = cls.scan_orphaned_snapshots(resource_group=resource_group, min_age_days=30)
        storage = cls.scan_orphaned_storage(resource_group=resource_group, min_age_days=30)

        # Calculate totals
        total_cost = (
            sum(d.monthly_cost for d in disks)
            + sum(s.monthly_cost for s in snapshots)
            + sum(st.monthly_cost for st in storage)
        )

        total_size = (
            sum(d.size_gb for d in disks)
            + sum(s.size_gb for s in snapshots)
            + sum(st.size_gb for st in storage)
        )

        return OrphanedResourceReport(
            disks=disks,
            snapshots=snapshots,
            storage_accounts=storage,
            total_cost_per_month=total_cost,
            total_size_gb=total_size,
            scan_date=datetime.now(),
        )

    @classmethod
    def cleanup_orphaned(
        cls,
        resource_group: str,
        resource_type: str,  # "disk", "snapshot", "storage", "all"
        min_age_days: int,
        dry_run: bool = True,
    ) -> CleanupResult:
        """Clean up orphaned resources.

        Safety: dry_run=True by default. Set to False to actually delete.

        Args:
            resource_group: Resource group to clean up
            resource_type: Type of resources to clean ("disk", "snapshot", "storage", "all")
            min_age_days: Minimum age in days
            dry_run: If True, only simulate deletion (default: True)

        Returns:
            CleanupResult: Cleanup operation results
        """
        deleted_disks = []
        deleted_snapshots = []
        deleted_storage = []
        errors = []
        total_size = 0
        total_cost = 0.0

        # Scan for orphaned resources
        if resource_type in ["disk", "all"]:
            disks = cls.scan_orphaned_disks(
                resource_group=resource_group, min_age_days=min_age_days
            )

            for disk in disks:
                if not dry_run:
                    try:
                        cmd = [
                            "az",
                            "disk",
                            "delete",
                            "--name",
                            disk.name,
                            "--resource-group",
                            resource_group,
                            "--yes",
                        ]
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

                        if result.returncode == 0:
                            deleted_disks.append(disk.name)
                            total_size += disk.size_gb
                            total_cost += disk.monthly_cost
                        else:
                            errors.append(f"Failed to delete disk {disk.name}: {result.stderr}")
                    except Exception as e:
                        errors.append(f"Error deleting disk {disk.name}: {e}")

        if resource_type in ["snapshot", "all"]:
            snapshots = cls.scan_orphaned_snapshots(
                resource_group=resource_group, min_age_days=min_age_days
            )

            for snapshot in snapshots:
                if not dry_run:
                    try:
                        cmd = [
                            "az",
                            "snapshot",
                            "delete",
                            "--name",
                            snapshot.name,
                            "--resource-group",
                            resource_group,
                            "--yes",
                        ]
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

                        if result.returncode == 0:
                            deleted_snapshots.append(snapshot.name)
                            total_size += snapshot.size_gb
                            total_cost += snapshot.monthly_cost
                        else:
                            errors.append(
                                f"Failed to delete snapshot {snapshot.name}: {result.stderr}"
                            )
                    except Exception as e:
                        errors.append(f"Error deleting snapshot {snapshot.name}: {e}")

        if resource_type in ["storage", "all"]:
            storage_accounts = cls.scan_orphaned_storage(
                resource_group=resource_group, min_age_days=min_age_days
            )

            for storage in storage_accounts:
                if not dry_run:
                    try:
                        if StorageManager:
                            # Use StorageManager to delete storage account
                            StorageManager.delete_storage(
                                name=storage.name, resource_group=resource_group, force=True
                            )
                            deleted_storage.append(storage.name)
                            total_size += storage.size_gb
                            total_cost += storage.monthly_cost
                    except Exception as e:
                        errors.append(f"Error deleting storage {storage.name}: {e}")

        return CleanupResult(
            deleted_disks=deleted_disks,
            deleted_snapshots=deleted_snapshots,
            deleted_storage=deleted_storage,
            total_size_freed_gb=total_size,
            total_cost_saved_per_month=total_cost,
            errors=errors,
            dry_run=dry_run,
        )
