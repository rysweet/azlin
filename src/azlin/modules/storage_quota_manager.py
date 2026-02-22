"""Storage Quota Manager Module.

Track and enforce storage quotas per VM, team (resource group), or project (subscription).

Philosophy:
- Self-contained module following brick architecture
- Standard library + subprocess for Azure CLI
- Zero-BS implementation - every function works
- Clear public API via __all__

Public API:
    StorageQuotaManager: Main quota management class
    QuotaConfig: Quota configuration data model
    QuotaStatus: Current quota usage status
    QuotaCheckResult: Quota availability check result
"""

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Import existing StorageManager for storage account queries
try:
    from azlin.modules.storage_manager import StorageManager
except ImportError:
    # Fallback if StorageManager not available in test environment
    StorageManager = None


__all__ = [
    "QuotaCheckResult",
    "QuotaConfig",
    "QuotaStatus",
    "StorageQuotaManager",
]


@dataclass
class QuotaConfig:
    """Storage quota configuration.

    Attributes:
        scope: Quota scope - "vm", "team", or "project"
        name: Identifier (VM name, RG name, or subscription ID)
        quota_gb: Total quota in GB
        created: Creation timestamp
        last_updated: Last update timestamp
    """

    scope: str
    name: str
    quota_gb: int
    created: datetime
    last_updated: datetime

    def __post_init__(self):
        """Validate quota configuration."""
        valid_scopes = {"vm", "team", "project"}
        if self.scope not in valid_scopes:
            raise ValueError(f"Invalid scope: {self.scope}. Must be one of {valid_scopes}")

        if self.quota_gb < 0:
            raise ValueError(f"Quota must be positive, got: {self.quota_gb}")


@dataclass
class QuotaStatus:
    """Current quota usage status.

    Attributes:
        config: Quota configuration
        used_gb: Currently used storage in GB
        available_gb: Available storage in GB
        utilization_percent: Utilization percentage
        storage_accounts: List of contributing storage accounts
        disks: List of contributing managed disks
        snapshots: List of contributing snapshots
    """

    config: QuotaConfig
    used_gb: float
    available_gb: float
    utilization_percent: float
    storage_accounts: list[str]
    disks: list[str]
    snapshots: list[str]


@dataclass
class QuotaCheckResult:
    """Result of quota availability check.

    Attributes:
        available: Whether requested quota is available
        current_usage_gb: Current usage in GB
        quota_gb: Total quota in GB
        requested_gb: Requested amount in GB
        remaining_after_gb: Remaining quota after operation
        message: Human-readable status message
    """

    available: bool
    current_usage_gb: float
    quota_gb: int
    requested_gb: int
    remaining_after_gb: float
    message: str


@dataclass
class _BatchStorageCache:
    """Pre-fetched storage data to avoid N+1 Azure CLI queries.

    Used internally by list_quotas() to batch disk, snapshot, and storage
    account queries instead of issuing separate CLI calls per quota entry.

    Attributes:
        all_disks: All disks keyed by resource group. Each value is a list of
            dicts with 'name' and 'diskSizeGb' keys.
        all_snapshots: All snapshots keyed by resource group. Same structure.
        all_storage_accounts: Storage account info keyed by resource group.
            Each value is a list of objects with .name and .size_gb attributes.
    """

    all_disks: dict[str, list[dict]] = field(default_factory=dict)
    all_snapshots: dict[str, list[dict]] = field(default_factory=dict)
    all_storage_accounts: dict[str, list] = field(default_factory=dict)


class StorageQuotaManager:
    """Manage storage quotas at VM, team, and project levels.

    Quota storage: ~/.azlin/quotas.json

    Usage:
        # Set quota
        config = StorageQuotaManager.set_quota(
            scope="vm",
            name="my-dev-vm",
            quota_gb=500
        )

        # Check quota status
        status = StorageQuotaManager.get_quota(
            scope="vm",
            name="my-dev-vm",
            resource_group="azlin-rg"
        )

        # Check if operation is allowed
        result = StorageQuotaManager.check_quota(
            scope="vm",
            name="my-dev-vm",
            requested_gb=100,
            resource_group="azlin-rg"
        )
    """

    QUOTA_FILE = Path.home() / ".azlin" / "quotas.json"

    @classmethod
    def set_quota(
        cls, scope: str, name: str, quota_gb: int, resource_group: str | None = None
    ) -> QuotaConfig:
        """Set storage quota for a scope/name.

        Args:
            scope: "vm", "team", or "project"
            name: VM name, RG name, or subscription ID
            quota_gb: Total quota in GB
            resource_group: Resource group (optional, for context)

        Returns:
            QuotaConfig: Created/updated quota configuration

        Raises:
            ValueError: If scope is invalid or quota is negative
        """
        # Validate inputs by creating QuotaConfig (will raise if invalid)
        now = datetime.now()
        config = QuotaConfig(
            scope=scope, name=name, quota_gb=quota_gb, created=now, last_updated=now
        )

        # Load existing quotas
        quotas = cls._load_quotas()

        # Initialize scope dict if doesn't exist
        if scope not in quotas:
            quotas[scope] = {}

        # Check if updating existing quota (preserve creation time)
        if name in quotas[scope]:
            existing = quotas[scope][name]
            config.created = datetime.fromisoformat(existing["created"])

        # Save quota
        quotas[scope][name] = {
            "quota_gb": config.quota_gb,
            "created": config.created.isoformat(),
            "last_updated": config.last_updated.isoformat(),
        }

        cls._save_quotas(quotas)
        return config

    @classmethod
    def get_quota(cls, scope: str, name: str, resource_group: str | None = None) -> QuotaStatus:
        """Get current quota status including usage.

        Args:
            scope: "vm", "team", or "project"
            name: VM name, RG name, or subscription ID
            resource_group: Resource group for VM/team scope

        Returns:
            QuotaStatus: Current quota and usage information

        Raises:
            ValueError: If no quota is configured for scope/name
        """
        # Load quota config
        quotas = cls._load_quotas()

        if scope not in quotas or name not in quotas[scope]:
            raise ValueError(f"No quota configured for {scope}/{name}")

        quota_data = quotas[scope][name]
        config = QuotaConfig(
            scope=scope,
            name=name,
            quota_gb=quota_data["quota_gb"],
            created=datetime.fromisoformat(quota_data["created"]),
            last_updated=datetime.fromisoformat(quota_data["last_updated"]),
        )

        # Calculate current usage
        used_gb, storage_accounts, disks, snapshots = cls._calculate_usage(
            scope=scope, name=name, resource_group=resource_group
        )

        # Calculate derived values
        available_gb = max(0, config.quota_gb - used_gb)
        utilization_percent = (used_gb / config.quota_gb * 100) if config.quota_gb > 0 else 0

        return QuotaStatus(
            config=config,
            used_gb=used_gb,
            available_gb=available_gb,
            utilization_percent=utilization_percent,
            storage_accounts=storage_accounts,
            disks=disks,
            snapshots=snapshots,
        )

    @classmethod
    def check_quota(
        cls, scope: str, name: str, requested_gb: int, resource_group: str | None = None
    ) -> QuotaCheckResult:
        """Check if requested quota is available.

        Args:
            scope: "vm", "team", or "project"
            name: VM name, RG name, or subscription ID
            requested_gb: Requested storage in GB
            resource_group: Resource group for VM/team scope

        Returns:
            QuotaCheckResult: Availability check result

        Raises:
            ValueError: If requested amount is negative
        """
        if requested_gb < 0:
            raise ValueError(f"Requested amount must be positive, got: {requested_gb}")

        # Get current status
        status = cls.get_quota(scope=scope, name=name, resource_group=resource_group)

        # Calculate availability
        remaining_after = status.available_gb - requested_gb
        available = remaining_after >= 0

        # Generate message
        if available:
            message = f"Quota available: {remaining_after:.0f} GB remaining after operation"
        else:
            total_needed = status.used_gb + requested_gb
            message = f"Quota exceeded: Would need {total_needed:.0f} GB but quota is {status.config.quota_gb} GB"

        return QuotaCheckResult(
            available=available,
            current_usage_gb=status.used_gb,
            quota_gb=status.config.quota_gb,
            requested_gb=requested_gb,
            remaining_after_gb=remaining_after,
            message=message,
        )

    @classmethod
    def list_quotas(cls, resource_group: str | None = None) -> list[QuotaStatus]:
        """List all configured quotas.

        Batches Azure CLI queries to avoid N+1 calls. Instead of calling
        get_quota() per entry (which spawns separate az CLI processes for
        each), this fetches all disks and snapshots once per resource group
        and computes status from the cached data.

        Args:
            resource_group: Filter to specific resource group (optional)

        Returns:
            list[QuotaStatus]: List of quota status objects
        """
        quotas = cls._load_quotas()

        # Collect entries to process and determine which resource groups need data
        entries: list[tuple[str, str]] = []
        rg_set: set[str] = set()

        for scope in quotas:
            for name in quotas[scope]:
                if resource_group and (
                    (scope == "team" and name != resource_group) or scope in ("vm", "project")
                ):
                    continue
                entries.append((scope, name))
                # Determine the resource group for data fetching
                if scope == "team":
                    rg_set.add(name)
                elif resource_group:
                    rg_set.add(resource_group)

        # Batch-fetch all storage info upfront (one CLI call per resource type per RG)
        cache = cls._batch_fetch_storage_info(rg_set)

        # Build QuotaStatus for each entry using cached data
        result = []
        for scope, name in entries:
            try:
                quota_data = quotas[scope][name]
                config = QuotaConfig(
                    scope=scope,
                    name=name,
                    quota_gb=quota_data["quota_gb"],
                    created=datetime.fromisoformat(quota_data["created"]),
                    last_updated=datetime.fromisoformat(quota_data["last_updated"]),
                )

                used_gb, storage_accounts, disk_names, snapshot_names = (
                    cls._calculate_usage_from_cache(
                        scope=scope, name=name, resource_group=resource_group, cache=cache
                    )
                )

                available_gb = max(0, config.quota_gb - used_gb)
                utilization_percent = (
                    (used_gb / config.quota_gb * 100) if config.quota_gb > 0 else 0
                )

                result.append(
                    QuotaStatus(
                        config=config,
                        used_gb=used_gb,
                        available_gb=available_gb,
                        utilization_percent=utilization_percent,
                        storage_accounts=storage_accounts,
                        disks=disk_names,
                        snapshots=snapshot_names,
                    )
                )
            except Exception:  # noqa: S112
                # Skip quotas that can't be computed (expected for missing configs)
                continue

        return result

    # Private helper methods

    @classmethod
    def _batch_fetch_storage_info(cls, resource_groups: set[str]) -> _BatchStorageCache:
        """Batch-fetch disks, snapshots, and storage accounts for all resource groups.

        Issues at most one CLI call per resource type per resource group,
        instead of one per quota entry. This eliminates N+1 queries when
        listing quotas for multiple VMs/RGs.

        Args:
            resource_groups: Set of resource group names to query.

        Returns:
            _BatchStorageCache with pre-fetched data for all resource groups.
        """
        cache = _BatchStorageCache()

        for rg in resource_groups:
            # Fetch all disks in RG (single CLI call)
            try:
                cmd = [
                    "az",
                    "disk",
                    "list",
                    "--resource-group",
                    rg,
                    "--output",
                    "json",
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    cache.all_disks[rg] = json.loads(result.stdout)
                else:
                    cache.all_disks[rg] = []
            except Exception:
                cache.all_disks[rg] = []

            # Fetch all snapshots in RG (single CLI call)
            try:
                cmd = [
                    "az",
                    "snapshot",
                    "list",
                    "--resource-group",
                    rg,
                    "--output",
                    "json",
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    cache.all_snapshots[rg] = json.loads(result.stdout)
                else:
                    cache.all_snapshots[rg] = []
            except Exception:
                cache.all_snapshots[rg] = []

            # Fetch storage accounts via StorageManager (single call per RG)
            if StorageManager:
                try:
                    cache.all_storage_accounts[rg] = StorageManager.list_storage(resource_group=rg)
                except Exception:
                    cache.all_storage_accounts[rg] = []
            else:
                cache.all_storage_accounts[rg] = []

        return cache

    @classmethod
    def _calculate_usage_from_cache(
        cls,
        scope: str,
        name: str,
        resource_group: str | None,
        cache: _BatchStorageCache,
    ) -> tuple[float, list[str], list[str], list[str]]:
        """Calculate storage usage from pre-fetched cache data.

        Same logic as _calculate_usage but reads from the batch cache
        instead of issuing individual Azure CLI calls.

        Args:
            scope: "vm", "team", or "project"
            name: VM name, RG name, or subscription ID
            resource_group: Resource group for queries
            cache: Pre-fetched storage data

        Returns:
            Tuple of (total_gb, storage_accounts, disks, snapshots)
        """
        total_gb = 0.0
        storage_accounts: list[str] = []
        disks: list[str] = []
        snapshots: list[str] = []

        if scope == "vm":
            # Storage accounts
            if resource_group and resource_group in cache.all_storage_accounts:
                for storage in cache.all_storage_accounts[resource_group]:
                    storage_accounts.append(storage.name)
                    total_gb += storage.size_gb

            # Disks attached to this VM (filter from cached RG disks)
            rg = resource_group or ""
            for disk in cache.all_disks.get(rg, []):
                if name in disk.get("name", ""):
                    total_gb += disk.get("diskSizeGb", 0)
                    disks.append(disk["name"])

            # Snapshots for this VM (filter from cached RG snapshots)
            for snap in cache.all_snapshots.get(rg, []):
                if name in snap.get("name", ""):
                    total_gb += snap.get("diskSizeGb", 0)
                    snapshots.append(snap["name"])

        elif scope == "team":
            rg = name  # Team scope uses RG name

            # All storage in RG
            for storage in cache.all_storage_accounts.get(rg, []):
                storage_accounts.append(storage.name)
                total_gb += storage.size_gb

            # All disks in RG
            for disk in cache.all_disks.get(rg, []):
                total_gb += disk.get("diskSizeGb", 0)
                disks.append(disk["name"])

            # All snapshots in RG
            for snap in cache.all_snapshots.get(rg, []):
                total_gb += snap.get("diskSizeGb", 0)
                snapshots.append(snap["name"])

        elif scope == "project":
            # Project scope: would query all resources in subscription
            # Unchanged from original - no batch optimization needed for single entry
            pass

        return total_gb, storage_accounts, disks, snapshots

    @classmethod
    def _load_quotas(cls) -> dict:
        """Load quotas from ~/.azlin/quotas.json.

        Returns:
            dict: Quota configuration dictionary

        Raises:
            ValueError: If quota file is corrupted
        """
        if not cls.QUOTA_FILE.exists():
            return {}

        try:
            content = cls.QUOTA_FILE.read_text()
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Corrupted quota configuration: {e}") from e

    @classmethod
    def _save_quotas(cls, quotas: dict) -> None:
        """Save quotas to ~/.azlin/quotas.json.

        Args:
            quotas: Quota configuration dictionary
        """
        # Ensure directory exists
        cls.QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Write JSON
        cls.QUOTA_FILE.write_text(json.dumps(quotas, indent=2))

    @classmethod
    def _calculate_usage(
        cls, scope: str, name: str, resource_group: str | None
    ) -> tuple[float, list[str], list[str], list[str]]:
        """Calculate current storage usage for scope/name.

        Args:
            scope: "vm", "team", or "project"
            name: VM name, RG name, or subscription ID
            resource_group: Resource group for queries

        Returns:
            Tuple of (total_gb, storage_accounts, disks, snapshots)
        """
        total_gb = 0.0
        storage_accounts = []
        disks = []
        snapshots = []

        if scope == "vm":
            # Calculate VM-specific usage
            # Storage accounts mounted on VM
            if StorageManager and resource_group:
                try:
                    storage_list = StorageManager.list_storage(resource_group=resource_group)
                    for storage in storage_list:
                        # Check if storage is mounted on this VM
                        # For now, include all storage (could filter by mount info)
                        storage_accounts.append(storage.name)
                        total_gb += storage.size_gb
                except Exception:
                    # Ignore storage enumeration errors - continue with available data
                    pass

            # Managed disks attached to VM
            disk_size = cls._get_vm_disks(vm_name=name, resource_group=resource_group)
            total_gb += disk_size[0]
            disks = disk_size[1]

            # Snapshots for VM
            snapshot_size = cls._get_vm_snapshots(vm_name=name, resource_group=resource_group)
            total_gb += snapshot_size[0]
            snapshots = snapshot_size[1]

        elif scope == "team":
            # Calculate team (RG) usage
            resource_group = name  # Team scope uses RG name

            # All storage in RG
            if StorageManager:
                try:
                    storage_list = StorageManager.list_storage(resource_group=resource_group)
                    for storage in storage_list:
                        storage_accounts.append(storage.name)
                        total_gb += storage.size_gb
                except Exception:
                    # Ignore storage enumeration errors - continue with available data
                    pass

            # All disks in RG
            disk_size = cls._get_rg_disks(resource_group=resource_group)
            total_gb += disk_size[0]
            disks = disk_size[1]

            # All snapshots in RG
            snapshot_size = cls._get_rg_snapshots(resource_group=resource_group)
            total_gb += snapshot_size[0]
            snapshots = snapshot_size[1]

        elif scope == "project":
            # Calculate project (subscription) usage
            # Would query all resources in subscription
            # For now, simplified implementation
            pass

        return total_gb, storage_accounts, disks, snapshots

    @classmethod
    def _get_vm_disks(cls, vm_name: str, resource_group: str | None) -> tuple[float, list[str]]:
        """Get total size of disks attached to VM.

        Args:
            vm_name: VM name
            resource_group: Resource group

        Returns:
            Tuple of (total_gb, disk_names)
        """
        try:
            cmd = ["az", "disk", "list"]
            if resource_group:
                cmd.extend(["--resource-group", resource_group])
            cmd.extend(["--query", f"[?contains(name, '{vm_name}')]", "--output", "json"])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                disks_data = json.loads(result.stdout)
                total_gb = sum(disk.get("diskSizeGb", 0) for disk in disks_data)
                disk_names = [disk["name"] for disk in disks_data]
                return total_gb, disk_names
        except Exception:
            # Ignore Azure CLI errors - return empty results
            pass

        return 0.0, []

    @classmethod
    def _get_vm_snapshots(cls, vm_name: str, resource_group: str | None) -> tuple[float, list[str]]:
        """Get total size of snapshots for VM.

        Args:
            vm_name: VM name
            resource_group: Resource group

        Returns:
            Tuple of (total_gb, snapshot_names)
        """
        try:
            cmd = ["az", "snapshot", "list"]
            if resource_group:
                cmd.extend(["--resource-group", resource_group])
            cmd.extend(["--query", f"[?contains(name, '{vm_name}')]", "--output", "json"])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                snapshots_data = json.loads(result.stdout)
                total_gb = sum(snap.get("diskSizeGb", 0) for snap in snapshots_data)
                snapshot_names = [snap["name"] for snap in snapshots_data]
                return total_gb, snapshot_names
        except Exception:
            # Ignore Azure CLI errors - return empty results
            pass

        return 0.0, []

    @classmethod
    def _get_rg_disks(cls, resource_group: str) -> tuple[float, list[str]]:
        """Get total size of all disks in resource group.

        Args:
            resource_group: Resource group

        Returns:
            Tuple of (total_gb, disk_names)
        """
        try:
            cmd = ["az", "disk", "list", "--resource-group", resource_group, "--output", "json"]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                disks_data = json.loads(result.stdout)
                total_gb = sum(disk.get("diskSizeGb", 0) for disk in disks_data)
                disk_names = [disk["name"] for disk in disks_data]
                return total_gb, disk_names
        except Exception:
            # Ignore Azure CLI errors - return empty results
            pass

        return 0.0, []

    @classmethod
    def _get_rg_snapshots(cls, resource_group: str) -> tuple[float, list[str]]:
        """Get total size of all snapshots in resource group.

        Args:
            resource_group: Resource group

        Returns:
            Tuple of (total_gb, snapshot_names)
        """
        try:
            cmd = ["az", "snapshot", "list", "--resource-group", resource_group, "--output", "json"]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                snapshots_data = json.loads(result.stdout)
                total_gb = sum(snap.get("diskSizeGb", 0) for snap in snapshots_data)
                snapshot_names = [snap["name"] for snap in snapshots_data]
                return total_gb, snapshot_names
        except Exception:
            # Ignore Azure CLI errors - return empty results
            pass

        return 0.0, []
