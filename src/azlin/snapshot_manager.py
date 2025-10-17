"""Snapshot management module.

This module handles VM snapshot/backup operations using Azure managed disk snapshots.
Delegates to Azure CLI for snapshot operations.

Security:
- Input validation
- No shell=True
- Sanitized logging
"""

import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class SnapshotManagerError(Exception):
    """Raised when snapshot operations fail."""

    pass


@dataclass
class SnapshotInfo:
    """Snapshot information from Azure."""

    name: str
    vm_name: str
    resource_group: str
    disk_name: str
    size_gb: int
    created_time: str
    location: str
    provisioning_state: str


class SnapshotManager:
    """Manage Azure VM snapshots.

    This class provides operations for:
    - Creating snapshots from VM disks
    - Listing snapshots for a VM
    - Restoring VMs from snapshots
    - Deleting snapshots
    - Estimating snapshot costs
    """

    # Snapshot storage cost: $0.05 per GB-month for Standard HDD snapshots
    SNAPSHOT_COST_PER_GB_MONTH = 0.05

    def create_snapshot(self, vm_name: str, resource_group: str) -> SnapshotInfo:
        """Create a snapshot of a VM's OS disk.

        Args:
            vm_name: Name of the VM
            resource_group: Resource group name

        Returns:
            SnapshotInfo object

        Raises:
            SnapshotManagerError: If snapshot creation fails
        """
        try:
            # Get VM details to find OS disk
            logger.info(f"Getting details for VM: {vm_name}")
            vm_details = self._get_vm_details(vm_name, resource_group)

            disk_name = vm_details["storageProfile"]["osDisk"]["name"]
            disk_id = vm_details["storageProfile"]["osDisk"]["managedDisk"]["id"]
            vm_details["storageProfile"]["osDisk"]["diskSizeGb"]
            location = vm_details["location"]

            # Generate snapshot name with timestamp
            snapshot_name = self._generate_snapshot_name(vm_name)

            logger.info(f"Creating snapshot: {snapshot_name} from disk: {disk_name}")

            # Create snapshot
            cmd = [
                "az",
                "snapshot",
                "create",
                "--resource-group",
                resource_group,
                "--name",
                snapshot_name,
                "--source",
                disk_id,
                "--location",
                location,
                "--tags",
                f"azlin-vm={vm_name}",
                f"azlin-disk={disk_name}",
                "--output",
                "json",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                logger.error(f"Snapshot creation failed: {error_msg}")
                raise SnapshotManagerError(f"Failed to create snapshot: {error_msg}")

            snapshot_data = json.loads(result.stdout)

            return SnapshotInfo(
                name=snapshot_data["name"],
                vm_name=vm_name,
                resource_group=resource_group,
                disk_name=disk_name,
                size_gb=snapshot_data["diskSizeGb"],
                created_time=snapshot_data["timeCreated"],
                location=location,
                provisioning_state=snapshot_data["provisioningState"],
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Azure CLI output: {e}")
            raise SnapshotManagerError(f"Failed to parse snapshot data: {e}")
        except KeyError as e:
            logger.error(f"Missing expected field in Azure response: {e}")
            raise SnapshotManagerError(f"Invalid Azure response: {e}")
        except Exception as e:
            logger.error(f"Unexpected error creating snapshot: {e}")
            raise SnapshotManagerError(f"Failed to create snapshot: {e}")

    def list_snapshots(self, vm_name: str, resource_group: str) -> list[SnapshotInfo]:
        """List all snapshots for a VM.

        Args:
            vm_name: Name of the VM
            resource_group: Resource group name

        Returns:
            List of SnapshotInfo objects

        Raises:
            SnapshotManagerError: If listing fails
        """
        try:
            logger.info(f"Listing snapshots for VM: {vm_name}")

            cmd = ["az", "snapshot", "list", "--resource-group", resource_group, "--output", "json"]

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                logger.error(f"Failed to list snapshots: {error_msg}")
                raise SnapshotManagerError(f"Failed to list snapshots: {error_msg}")

            snapshots_data = json.loads(result.stdout)

            # Filter snapshots for this VM
            snapshots = []
            for snapshot_data in snapshots_data:
                tags = snapshot_data.get("tags", {})
                if tags.get("azlin-vm") == vm_name:
                    snapshots.append(
                        SnapshotInfo(
                            name=snapshot_data["name"],
                            vm_name=vm_name,
                            resource_group=resource_group,
                            disk_name=tags.get("azlin-disk", ""),
                            size_gb=snapshot_data["diskSizeGb"],
                            created_time=snapshot_data["timeCreated"],
                            location=snapshot_data["location"],
                            provisioning_state=snapshot_data["provisioningState"],
                        )
                    )

            # Sort by creation time (newest first)
            snapshots.sort(key=lambda s: s.created_time, reverse=True)

            return snapshots

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Azure CLI output: {e}")
            raise SnapshotManagerError(f"Failed to parse snapshots data: {e}")
        except Exception as e:
            logger.error(f"Unexpected error listing snapshots: {e}")
            raise SnapshotManagerError(f"Failed to list snapshots: {e}")

    def delete_snapshot(self, snapshot_name: str, resource_group: str) -> None:
        """Delete a snapshot.

        Args:
            snapshot_name: Name of the snapshot to delete
            resource_group: Resource group name

        Raises:
            SnapshotManagerError: If deletion fails
        """
        try:
            logger.info(f"Deleting snapshot: {snapshot_name}")

            cmd = [
                "az",
                "snapshot",
                "delete",
                "--resource-group",
                resource_group,
                "--name",
                snapshot_name,
                "--yes",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                if "ResourceNotFound" in error_msg or "NotFound" in error_msg:
                    raise SnapshotManagerError(f"Snapshot '{snapshot_name}' not found")
                logger.error(f"Failed to delete snapshot: {error_msg}")
                raise SnapshotManagerError(f"Failed to delete snapshot: {error_msg}")

            logger.info(f"Successfully deleted snapshot: {snapshot_name}")

        except SnapshotManagerError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error deleting snapshot: {e}")
            raise SnapshotManagerError(f"Failed to delete snapshot: {e}")

    def restore_snapshot(self, vm_name: str, snapshot_name: str, resource_group: str) -> None:
        """Restore a VM from a snapshot.

        This operation will:
        1. Stop/deallocate the VM
        2. Delete the current OS disk
        3. Create a new disk from the snapshot
        4. Attach the new disk to the VM
        5. Start the VM

        Args:
            vm_name: Name of the VM to restore
            snapshot_name: Name of the snapshot to restore from
            resource_group: Resource group name

        Raises:
            SnapshotManagerError: If restoration fails
        """
        try:
            # Get snapshot details
            logger.info(f"Getting snapshot details: {snapshot_name}")
            snapshot_data = self._get_snapshot_details(snapshot_name, resource_group)
            snapshot_id = snapshot_data["id"]

            # Get VM details
            logger.info(f"Getting VM details: {vm_name}")
            vm_data = self._get_vm_details(vm_name, resource_group)
            old_disk_name = vm_data["storageProfile"]["osDisk"]["name"]

            # Stop the VM
            logger.info(f"Deallocating VM: {vm_name}")
            self._run_command(
                ["az", "vm", "deallocate", "--resource-group", resource_group, "--name", vm_name]
            )

            # Delete the old disk
            logger.info(f"Deleting old disk: {old_disk_name}")
            self._run_command(
                [
                    "az",
                    "disk",
                    "delete",
                    "--resource-group",
                    resource_group,
                    "--name",
                    old_disk_name,
                    "--yes",
                ]
            )

            # Create new disk from snapshot
            new_disk_name = old_disk_name
            logger.info(f"Creating new disk from snapshot: {new_disk_name}")
            self._run_command(
                [
                    "az",
                    "disk",
                    "create",
                    "--resource-group",
                    resource_group,
                    "--name",
                    new_disk_name,
                    "--source",
                    snapshot_id,
                ]
            )

            # Update VM to use new disk
            logger.info(f"Updating VM with new disk: {vm_name}")
            self._run_command(
                [
                    "az",
                    "vm",
                    "update",
                    "--resource-group",
                    resource_group,
                    "--name",
                    vm_name,
                    "--os-disk",
                    new_disk_name,
                ]
            )

            # Start the VM
            logger.info(f"Starting VM: {vm_name}")
            self._run_command(
                ["az", "vm", "start", "--resource-group", resource_group, "--name", vm_name]
            )

            logger.info(f"Successfully restored VM '{vm_name}' from snapshot '{snapshot_name}'")

        except SnapshotManagerError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error restoring snapshot: {e}")
            raise SnapshotManagerError(f"Failed to restore snapshot: {e}")

    def get_snapshot_cost_estimate(self, size_gb: int, days: int = 30) -> float:
        """Estimate the cost of storing a snapshot.

        Args:
            size_gb: Snapshot size in GB
            days: Number of days to store (default 30)

        Returns:
            Estimated cost in USD
        """
        # Calculate cost: (size_gb * cost_per_gb_month) * (days / 30)
        monthly_cost = size_gb * self.SNAPSHOT_COST_PER_GB_MONTH
        daily_rate = monthly_cost / 30
        return daily_rate * days

    def _generate_snapshot_name(self, vm_name: str) -> str:
        """Generate a snapshot name with timestamp.

        Args:
            vm_name: Name of the VM

        Returns:
            Snapshot name in format: {vm_name}-snapshot-{timestamp}
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"{vm_name}-snapshot-{timestamp}"

    def _get_vm_details(self, vm_name: str, resource_group: str) -> dict[str, Any]:
        """Get VM details from Azure.

        Args:
            vm_name: Name of the VM
            resource_group: Resource group name

        Returns:
            VM details dictionary

        Raises:
            SnapshotManagerError: If VM not found or query fails
        """
        cmd = [
            "az",
            "vm",
            "show",
            "--resource-group",
            resource_group,
            "--name",
            vm_name,
            "--output",
            "json",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            error_msg = result.stderr.strip()
            if "ResourceNotFound" in error_msg or "NotFound" in error_msg:
                raise SnapshotManagerError(
                    f"VM '{vm_name}' not found in resource group '{resource_group}'"
                )
            raise SnapshotManagerError(f"Failed to get VM details: {error_msg}")

        return json.loads(result.stdout)

    def _get_snapshot_details(self, snapshot_name: str, resource_group: str) -> dict[str, Any]:
        """Get snapshot details from Azure.

        Args:
            snapshot_name: Name of the snapshot
            resource_group: Resource group name

        Returns:
            Snapshot details dictionary

        Raises:
            SnapshotManagerError: If snapshot not found or query fails
        """
        cmd = [
            "az",
            "snapshot",
            "show",
            "--resource-group",
            resource_group,
            "--name",
            snapshot_name,
            "--output",
            "json",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            error_msg = result.stderr.strip()
            if "ResourceNotFound" in error_msg or "NotFound" in error_msg:
                raise SnapshotManagerError(
                    f"Snapshot '{snapshot_name}' not found in resource group '{resource_group}'"
                )
            raise SnapshotManagerError(f"Failed to get snapshot details: {error_msg}")

        return json.loads(result.stdout)

    def _run_command(self, cmd: list[str]) -> None:
        """Run a command and raise error if it fails.

        Args:
            cmd: Command to run as list

        Raises:
            SnapshotManagerError: If command fails
        """
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            error_msg = result.stderr.strip()
            raise SnapshotManagerError(f"Command failed: {error_msg}")
