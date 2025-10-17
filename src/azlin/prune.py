"""VM pruning module.

This module identifies and prunes inactive VMs based on age and idle time thresholds.
Integrates with connection_tracker to determine VM usage patterns.

Security:
- Confirmation prompts for destructive operations
- Dry-run mode for preview
- Input validation
"""

import logging
from datetime import datetime
from typing import Optional

from azlin.config_manager import ConfigManager
from azlin.connection_tracker import ConnectionTracker
from azlin.vm_lifecycle import VMLifecycleManager
from azlin.vm_manager import VMInfo, VMManager, VMManagerError

logger = logging.getLogger(__name__)


class PruneManager:
    """Manage VM pruning operations."""

    @staticmethod
    def _parse_iso_datetime(timestamp_str: str) -> Optional[datetime]:
        """Parse ISO format timestamp, returning None on error."""
        try:
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def _days_since(timestamp_str: Optional[str]) -> Optional[int]:
        """Calculate days since timestamp, returning None if unparseable."""
        if not timestamp_str:
            return None
        dt = PruneManager._parse_iso_datetime(timestamp_str)
        if not dt:
            return None
        return (datetime.utcnow() - dt.replace(tzinfo=None)).days

    @classmethod
    def filter_by_age(cls, vms: list[VMInfo], age_days: int) -> list[VMInfo]:
        """Filter VMs older than age_days."""
        filtered = []
        for vm in vms:
            age = cls._days_since(vm.created_time)
            if age is not None and age >= age_days:
                filtered.append(vm)
        return filtered

    @classmethod
    def filter_by_idle(
        cls, vms: list[VMInfo], idle_days: int, connection_data: dict[str, dict]
    ) -> list[VMInfo]:
        """Filter VMs idle longer than idle_days, or never connected."""
        filtered = []
        for vm in vms:
            last_connected_str = connection_data.get(vm.name, {}).get("last_connected")
            idle = cls._days_since(last_connected_str)
            # Include if never connected (None) or idle >= threshold
            if idle is None or idle >= idle_days:
                filtered.append(vm)
        return filtered

    @classmethod
    def filter_for_pruning(
        cls,
        vms: list[VMInfo],
        age_days: int,
        idle_days: int,
        connection_data: dict[str, dict],
        include_running: bool = False,
        include_named: bool = False,
    ) -> list[VMInfo]:
        """Filter VMs that meet all pruning criteria.

        Args:
            vms: List of VM info objects
            age_days: Age threshold in days
            idle_days: Idle threshold in days
            connection_data: Connection tracking data
            include_running: Include running VMs (default: False)
            include_named: Include named sessions (default: False)

        Returns:
            VMs that meet all pruning criteria

        Example:
            >>> candidates = PruneManager.filter_for_pruning(
            ...     vms, age_days=30, idle_days=14, connection_data
            ... )
        """
        # Apply age filter
        candidates = cls.filter_by_age(vms, age_days)

        # Apply idle filter
        candidates = cls.filter_by_idle(candidates, idle_days, connection_data)

        # Exclude running VMs unless include_running is True
        if not include_running:
            candidates = [vm for vm in candidates if not vm.is_running()]

        # Exclude named sessions unless include_named is True
        if not include_named:
            candidates = [vm for vm in candidates if not vm.session_name]

        return candidates

    @classmethod
    def format_prune_table(cls, vms: list[VMInfo], connection_data: dict[str, dict]) -> str:
        """Format VM list as a table for display."""
        if not vms:
            return "No VMs to display."

        # Build table
        rows = []
        header = f"{'VM Name':<35} {'Age (days)':<15} {'Idle (days)':<15} {'Status':<15} {'Location':<15} {'Size':<15}"
        separator = "=" * 110

        rows.append(separator)
        rows.append(header)
        rows.append(separator)

        for vm in vms:
            # Calculate age and idle using helper
            age = cls._days_since(vm.created_time)
            age_str = f"{age}d" if age is not None else "Unknown"

            last_connected_str = connection_data.get(vm.name, {}).get("last_connected")
            idle = cls._days_since(last_connected_str)
            idle_str = f"{idle}d" if idle is not None else "Never"

            # Format row
            display_name = vm.get_display_name()
            status = vm.get_status_display()
            location = vm.location or "Unknown"
            size = vm.vm_size or "Unknown"

            row = f"{display_name:<35} {age_str:<15} {idle_str:<15} {status:<15} {location:<15} {size:<15}"
            rows.append(row)

        rows.append(separator)
        return "\n".join(rows)

    @classmethod
    def get_candidates(
        cls,
        resource_group: str,
        age_days: int = 30,
        idle_days: int = 14,
        include_running: bool = False,
        include_named: bool = False,
    ) -> tuple[list[VMInfo], dict[str, dict]]:
        """Get VMs that are candidates for pruning.

        Args:
            resource_group: Resource group name
            age_days: Age threshold in days (default: 30)
            idle_days: Idle threshold in days (default: 14)
            include_running: Include running VMs (default: False)
            include_named: Include named sessions (default: False)

        Returns:
            Tuple of (candidates, connection_data)

        Raises:
            VMManagerError: If VM operations fail

        Example:
            >>> candidates, connection_data = PruneManager.get_candidates(
            ...     resource_group="my-rg",
            ...     age_days=30,
            ...     idle_days=14
            ... )
        """
        # List all VMs in resource group
        vms = VMManager.list_vms(resource_group, include_stopped=True)

        # Load connection data
        connection_data = ConnectionTracker.load_connections()

        # Filter VMs for pruning
        candidates = cls.filter_for_pruning(
            vms,
            age_days=age_days,
            idle_days=idle_days,
            connection_data=connection_data,
            include_running=include_running,
            include_named=include_named,
        )

        return candidates, connection_data

    @classmethod
    def execute_prune(
        cls,
        candidates: list[VMInfo],
        resource_group: str,
    ) -> dict:
        """Execute deletion of candidate VMs.

        Args:
            candidates: List of VMs to delete
            resource_group: Resource group name

        Returns:
            Dictionary with deletion results

        Raises:
            VMManagerError: If VM operations fail

        Example:
            >>> result = PruneManager.execute_prune(
            ...     candidates=candidates,
            ...     resource_group="my-rg"
            ... )
        """
        deleted_count = 0
        failed_count = 0
        errors = []

        for vm in candidates:
            try:
                logger.info(f"Deleting VM: {vm.name}")
                result = VMLifecycleManager.delete_vm(vm.name, resource_group, force=True)

                if result.success:
                    deleted_count += 1
                    # Clean up connection record
                    ConnectionTracker.remove_connection(vm.name)
                    # Clean up session name
                    ConfigManager.delete_session_name(vm.name)
                else:
                    failed_count += 1
                    errors.append(f"{vm.name}: {result.message}")

            except Exception as e:
                logger.error(f"Failed to delete {vm.name}: {e}")
                failed_count += 1
                errors.append(f"{vm.name}: {str(e)}")

        return {
            "deleted": deleted_count,
            "failed": failed_count,
            "errors": errors,
            "message": f"Deleted {deleted_count} VM(s), {failed_count} failed.",
        }

    @classmethod
    def prune(
        cls,
        resource_group: str,
        age_days: int = 30,
        idle_days: int = 14,
        dry_run: bool = False,
        force: bool = False,
        include_running: bool = False,
        include_named: bool = False,
    ) -> dict:
        """Prune inactive VMs based on criteria.

        Args:
            resource_group: Resource group name
            age_days: Age threshold in days (default: 30)
            idle_days: Idle threshold in days (default: 14)
            dry_run: Preview without deleting (default: False)
            force: Skip confirmation prompt (default: False)
            include_running: Include running VMs (default: False)
            include_named: Include named sessions (default: False)

        Returns:
            Dictionary with prune results

        Raises:
            VMManagerError: If VM operations fail

        Example:
            >>> result = PruneManager.prune(
            ...     resource_group="my-rg",
            ...     age_days=30,
            ...     idle_days=14,
            ...     dry_run=True
            ... )
        """
        # Get candidates (single API call)
        candidates, connection_data = cls.get_candidates(
            resource_group=resource_group,
            age_days=age_days,
            idle_days=idle_days,
            include_running=include_running,
            include_named=include_named,
        )

        # If no candidates, return early
        if not candidates:
            return {
                "candidates": [],
                "deleted": 0,
                "failed": 0,
                "errors": [],
                "message": "No VMs eligible for pruning.",
            }

        # In dry-run mode, just show what would be deleted
        if dry_run:
            return {
                "candidates": candidates,
                "deleted": 0,
                "failed": 0,
                "errors": [],
                "message": f"Dry run: {len(candidates)} VM(s) would be deleted.",
            }

        # If not force mode, require confirmation (handled by CLI)
        if not force:
            return {
                "candidates": candidates,
                "deleted": 0,
                "failed": 0,
                "errors": [],
                "message": "Confirmation required.",
            }

        # Execute deletion
        result = cls.execute_prune(candidates, resource_group)
        result["candidates"] = candidates
        return result


__all__ = ["PruneManager"]
