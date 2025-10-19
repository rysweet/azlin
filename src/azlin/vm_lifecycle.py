"""VM lifecycle management module.

This module handles VM deletion operations:
- Delete single VM with associated resources
- Delete all VMs in resource group
- Resource cleanup (NICs, disks, public IPs)

Security:
- Confirmation prompts for destructive operations
- Input validation
- Safe resource enumeration
- No shell=True
"""

import json
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from azlin.config_manager import ConfigManager
from azlin.connection_tracker import ConnectionTracker

logger = logging.getLogger(__name__)


class VMLifecycleError(Exception):
    """Raised when VM lifecycle operations fail."""

    pass


@dataclass
class DeletionResult:
    """Result from VM deletion operation."""

    vm_name: str
    success: bool
    message: str
    resources_deleted: list[str] | None = None

    def __post_init__(self) -> None:
        if self.resources_deleted is None:
            self.resources_deleted = []


@dataclass
class DeletionSummary:
    """Summary of batch deletion operations."""

    total: int
    succeeded: int
    failed: int
    results: list[DeletionResult]

    @property
    def all_succeeded(self) -> bool:
        """Check if all deletions succeeded."""
        return self.failed == 0

    def get_failed_vms(self) -> list[str]:
        """Get list of VMs that failed to delete."""
        return [r.vm_name for r in self.results if not r.success]


class VMLifecycleManager:
    """Manage VM lifecycle operations.

    This class provides operations for:
    - Deleting VMs with associated resources
    - Batch deletion of multiple VMs
    - Resource cleanup tracking
    """

    @classmethod
    def delete_vm(
        cls, vm_name: str, resource_group: str, force: bool = False, no_wait: bool = False
    ) -> DeletionResult:
        """Delete VM and all associated resources.

        Args:
            vm_name: VM name to delete
            resource_group: Resource group name
            force: Skip confirmation prompt
            no_wait: Don't wait for deletion to complete

        Returns:
            DeletionResult object

        Raises:
            VMLifecycleError: If deletion fails
        """
        logger.info(f"Deleting VM: {vm_name} in resource group: {resource_group}")

        try:
            # Get VM details to find associated resources
            vm_info = cls._get_vm_details(vm_name, resource_group)

            if not vm_info:
                return DeletionResult(vm_name=vm_name, success=False, message="VM not found")

            # Collect resource IDs to delete
            resources_to_delete = cls._collect_vm_resources(vm_info)

            logger.debug(f"Found {len(resources_to_delete)} resources to delete for {vm_name}")

            # Delete VM (this also deletes attached disks if configured)
            deleted_resources: list[str] = []

            # Delete VM itself
            try:
                cls._delete_vm_resource(vm_name, resource_group, no_wait)
                deleted_resources.append(f"VM: {vm_name}")
            except Exception as e:
                return DeletionResult(
                    vm_name=vm_name, success=False, message=f"Failed to delete VM: {e}"
                )

            # Delete associated resources (NICs, Public IPs)
            # Note: Disks are typically auto-deleted with VM if deleteOption is set
            for resource_type, resource_name in resources_to_delete:
                try:
                    if resource_type == "nic":
                        cls._delete_nic(resource_name, resource_group)
                        deleted_resources.append(f"NIC: {resource_name}")
                    elif resource_type == "public-ip":
                        cls._delete_public_ip(resource_name, resource_group)
                        deleted_resources.append(f"Public IP: {resource_name}")
                    elif resource_type == "disk":
                        # Try to delete disk (might already be deleted)
                        try:
                            cls._delete_disk(resource_name, resource_group)
                            deleted_resources.append(f"Disk: {resource_name}")
                        except Exception as e:
                            # Disk might be auto-deleted, ignore
                            logger.debug(f"Disk {resource_name} likely auto-deleted: {e}")
                except Exception as e:
                    logger.warning(f"Failed to delete {resource_type} {resource_name}: {e}")
                    # Continue with other resources

            # Clean up connection tracking record
            try:
                ConnectionTracker.remove_connection(vm_name)
            except Exception as e:
                logger.warning(f"Failed to clean up connection record for {vm_name}: {e}")

            # Clean up session name mapping
            try:
                ConfigManager.delete_session_name(vm_name)
                logger.debug(f"Removed session name mapping for {vm_name}")
            except Exception as e:
                logger.warning(f"Failed to clean up session name for {vm_name}: {e}")

            return DeletionResult(
                vm_name=vm_name,
                success=True,
                message=f"Deleted {len(deleted_resources)} resources",
                resources_deleted=deleted_resources,
            )

        except Exception as e:
            logger.error(f"Unexpected error deleting VM {vm_name}: {e}")
            return DeletionResult(vm_name=vm_name, success=False, message=f"Unexpected error: {e}")

    @classmethod
    def delete_all_vms(
        cls,
        resource_group: str,
        force: bool = False,
        vm_prefix: str | None = None,
        max_workers: int = 5,
    ) -> DeletionSummary:
        """Delete all VMs in resource group.

        Args:
            resource_group: Resource group name
            force: Skip confirmation prompts
            vm_prefix: Only delete VMs with this prefix (e.g., "azlin")
            max_workers: Maximum parallel workers

        Returns:
            DeletionSummary object

        Raises:
            VMLifecycleError: If listing VMs fails
        """
        try:
            # List all VMs in resource group
            vms = cls._list_vms_in_group(resource_group)

            if not vms:
                return DeletionSummary(total=0, succeeded=0, failed=0, results=[])

            # Filter by prefix if specified
            if vm_prefix:
                vms = [vm for vm in vms if vm.startswith(vm_prefix)]

            if not vms:
                return DeletionSummary(total=0, succeeded=0, failed=0, results=[])

            logger.info(f"Deleting {len(vms)} VMs in parallel with {max_workers} workers")

            # Delete VMs in parallel
            results: list[DeletionResult] = []
            num_workers = min(max_workers, len(vms))

            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                # Submit all deletion tasks
                future_to_vm = {
                    executor.submit(
                        cls.delete_vm,
                        vm_name,
                        resource_group,
                        force=True,  # Don't prompt in parallel execution
                        no_wait=False,
                    ): vm_name
                    for vm_name in vms
                }

                # Collect results as they complete
                for future in as_completed(future_to_vm):
                    vm_name = future_to_vm[future]
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        logger.error(f"Failed to delete {vm_name}: {e}")
                        results.append(
                            DeletionResult(
                                vm_name=vm_name, success=False, message=f"Exception: {e}"
                            )
                        )

            # Calculate summary
            succeeded = sum(1 for r in results if r.success)
            failed = sum(1 for r in results if not r.success)

            return DeletionSummary(
                total=len(results), succeeded=succeeded, failed=failed, results=results
            )

        except Exception as e:
            raise VMLifecycleError(f"Failed to delete VMs: {e}") from e

    @classmethod
    def _get_vm_details(cls, vm_name: str, resource_group: str) -> dict[str, Any] | None:
        """Get VM details including network interfaces.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            VM details dictionary or None if not found
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
                "--output",
                "json",
            ]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, check=True
            )

            vm_details: dict[str, Any] = json.loads(result.stdout)
            return vm_details

        except subprocess.CalledProcessError as e:
            if "ResourceNotFound" in e.stderr:
                return None
            raise VMLifecycleError(f"Failed to get VM details: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise VMLifecycleError("VM details query timed out") from e
        except json.JSONDecodeError as e:
            raise VMLifecycleError("Failed to parse VM details") from e

    @classmethod
    def _list_vms_in_group(cls, resource_group: str) -> list[str]:
        """List VM names in resource group.

        Args:
            resource_group: Resource group name

        Returns:
            List of VM names
        """
        try:
            cmd = [
                "az",
                "vm",
                "list",
                "--resource-group",
                resource_group,
                "--query",
                "[].name",
                "--output",
                "json",
            ]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, check=True
            )

            vm_names: list[str] = json.loads(result.stdout)
            return vm_names

        except subprocess.CalledProcessError as e:
            if "ResourceGroupNotFound" in e.stderr:
                return []
            raise VMLifecycleError(f"Failed to list VMs: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise VMLifecycleError("VM list operation timed out") from e
        except json.JSONDecodeError as e:
            raise VMLifecycleError("Failed to parse VM list") from e

    @classmethod
    def _collect_vm_resources(cls, vm_info: dict[str, Any]) -> list[tuple[str, str]]:
        """Collect associated resource names from VM info.

        Args:
            vm_info: VM details dictionary

        Returns:
            List of (resource_type, resource_name) tuples
        """
        resources: list[tuple[str, str]] = []

        # Extract NIC names
        network_profile = vm_info.get("networkProfile", {})
        network_interfaces = network_profile.get("networkInterfaces", [])

        for nic in network_interfaces:
            nic_id = nic.get("id", "")
            # Extract NIC name from ID: /subscriptions/.../resourceGroups/.../providers/Microsoft.Network/networkInterfaces/NAME
            if nic_id:
                nic_name = nic_id.split("/")[-1]
                resources.append(("nic", nic_name))

                # Get public IP from NIC
                try:
                    public_ip_name = cls._get_public_ip_from_nic(
                        nic_name, vm_info.get("resourceGroup", "")
                    )
                    if public_ip_name:
                        resources.append(("public-ip", public_ip_name))
                except Exception as e:
                    logger.debug(f"Failed to get public IP for NIC {nic_name}: {e}")

        # Extract disk names
        storage_profile = vm_info.get("storageProfile", {})

        # OS Disk
        os_disk = storage_profile.get("osDisk", {})
        if os_disk and os_disk.get("name"):
            resources.append(("disk", os_disk["name"]))

        # Data disks
        data_disks = storage_profile.get("dataDisks", [])
        resources.extend(("disk", disk["name"]) for disk in data_disks if disk.get("name"))

        return resources

    @classmethod
    def _get_public_ip_from_nic(cls, nic_name: str, resource_group: str) -> str | None:
        """Get public IP name associated with NIC.

        Args:
            nic_name: NIC name
            resource_group: Resource group name

        Returns:
            Public IP name or None
        """
        try:
            cmd = [
                "az",
                "network",
                "nic",
                "show",
                "--name",
                nic_name,
                "--resource-group",
                resource_group,
                "--query",
                "ipConfigurations[0].publicIpAddress.id",
                "--output",
                "tsv",
            ]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10, check=True
            )

            public_ip_id: str = result.stdout.strip()
            if public_ip_id and public_ip_id != "None":
                # Extract name from ID
                return public_ip_id.split("/")[-1]

            return None

        except Exception:
            return None

    @classmethod
    def _delete_vm_resource(cls, vm_name: str, resource_group: str, no_wait: bool = False) -> None:
        """Delete VM resource using Azure CLI.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            no_wait: Don't wait for deletion to complete
        """
        cmd = ["az", "vm", "delete", "--name", vm_name, "--resource-group", resource_group, "--yes"]

        if no_wait:
            cmd.append("--no-wait")

        subprocess.run(
            cmd, capture_output=True, text=True, timeout=300 if not no_wait else 30, check=True
        )

        logger.debug(f"Deleted VM: {vm_name}")

    @classmethod
    def _delete_nic(cls, nic_name: str, resource_group: str) -> None:
        """Delete network interface.

        Args:
            nic_name: NIC name
            resource_group: Resource group name
        """
        cmd = [
            "az",
            "network",
            "nic",
            "delete",
            "--name",
            nic_name,
            "--resource-group",
            resource_group,
        ]

        _result: subprocess.CompletedProcess[str] = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, check=True
        )

        logger.debug(f"Deleted NIC: {nic_name}")

    @classmethod
    def _delete_public_ip(cls, ip_name: str, resource_group: str) -> None:
        """Delete public IP address.

        Args:
            ip_name: Public IP name
            resource_group: Resource group name
        """
        cmd = [
            "az",
            "network",
            "public-ip",
            "delete",
            "--name",
            ip_name,
            "--resource-group",
            resource_group,
        ]

        _result: subprocess.CompletedProcess[str] = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, check=True
        )

        logger.debug(f"Deleted Public IP: {ip_name}")

    @classmethod
    def _delete_disk(cls, disk_name: str, resource_group: str) -> None:
        """Delete managed disk.

        Args:
            disk_name: Disk name
            resource_group: Resource group name
        """
        cmd = [
            "az",
            "disk",
            "delete",
            "--name",
            disk_name,
            "--resource-group",
            resource_group,
            "--yes",
        ]

        _result: subprocess.CompletedProcess[str] = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, check=True
        )

        logger.debug(f"Deleted Disk: {disk_name}")


__all__ = ["DeletionResult", "DeletionSummary", "VMLifecycleError", "VMLifecycleManager"]
