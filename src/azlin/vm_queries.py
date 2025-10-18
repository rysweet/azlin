"""Centralized Azure VM query operations.

This module provides a single source of truth for all Azure VM queries:
- Listing VMs in resource groups
- Getting VM details and instance views
- Extracting power states
- Batch querying public IPs

Security:
- Input validation
- No shell=True
- Consistent error handling
- Timeout management

Philosophy:
- DRY: Single implementation of common query patterns
- Ruthless Simplicity: Clear, focused API
- Zero-BS: Real implementations, no stubs
"""

import json
import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


class VMQueryError(Exception):
    """Raised when VM query operations fail."""

    pass


class VMQueryService:
    """Centralized service for Azure VM queries.

    This class provides all VM query operations used across the codebase:
    - list_vms(): Get full VM data
    - list_vm_names(): Get just VM names (faster)
    - get_vm_details(): Get VM details without instance view
    - get_vm_instance_view(): Get VM with power state
    - get_power_state(): Extract power state from instance view
    - get_all_public_ips(): Batch query for all public IPs
    """

    @classmethod
    def list_vms(cls, resource_group: str) -> list[dict[str, Any]]:
        """List all VMs in a resource group.

        Args:
            resource_group: Resource group name

        Returns:
            List of VM data dictionaries from Azure CLI

        Raises:
            VMQueryError: If listing fails (except ResourceGroupNotFound)
        """
        try:
            cmd = ["az", "vm", "list", "--resource-group", resource_group, "--output", "json"]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, check=True
            )

            vms_data: list[dict[str, Any]] = json.loads(result.stdout)
            logger.debug(f"Found {len(vms_data)} VMs in resource group: {resource_group}")
            return vms_data

        except subprocess.CalledProcessError as e:
            # Return empty list if resource group doesn't exist
            if "ResourceGroupNotFound" in e.stderr:
                logger.debug(f"Resource group not found: {resource_group}")
                return []
            raise VMQueryError(f"Failed to list VMs: {e.stderr}") from e
        except json.JSONDecodeError as e:
            raise VMQueryError("Failed to parse VM list response") from e
        except subprocess.TimeoutExpired as e:
            raise VMQueryError("VM list operation timed out") from e

    @classmethod
    def list_vm_names(cls, resource_group: str) -> list[str]:
        """List VM names in resource group (faster than full list).

        Args:
            resource_group: Resource group name

        Returns:
            List of VM names

        Raises:
            VMQueryError: If listing fails (except ResourceGroupNotFound)
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
            logger.debug(f"Found {len(vm_names)} VM names in resource group: {resource_group}")
            return vm_names

        except subprocess.CalledProcessError as e:
            # Return empty list if resource group doesn't exist
            if "ResourceGroupNotFound" in e.stderr:
                logger.debug(f"Resource group not found: {resource_group}")
                return []
            raise VMQueryError(f"Failed to list VM names: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise VMQueryError("VM list operation timed out") from e
        except json.JSONDecodeError as e:
            raise VMQueryError("Failed to parse VM list") from e

    @classmethod
    def get_vm_details(cls, vm_name: str, resource_group: str) -> dict[str, Any] | None:
        """Get VM details without instance view.

        Use this when you don't need power state information.
        For power state, use get_vm_instance_view() instead.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            VM details dictionary or None if not found

        Raises:
            VMQueryError: If query fails (except ResourceNotFound)
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
            # Return None if VM doesn't exist
            if "ResourceNotFound" in e.stderr:
                logger.debug(f"VM not found: {vm_name}")
                return None
            raise VMQueryError(f"Failed to get VM details: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise VMQueryError("VM details query timed out") from e
        except json.JSONDecodeError as e:
            raise VMQueryError("Failed to parse VM details") from e

    @classmethod
    def get_vm_instance_view(cls, vm_name: str, resource_group: str) -> dict[str, Any] | None:
        """Get VM instance view with power state information.

        Use this when you need current power state.
        For basic VM details, use get_vm_details() instead (faster).

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            VM instance view dictionary or None if not found

        Raises:
            VMQueryError: If query fails (except ResourceNotFound)
        """
        try:
            cmd = [
                "az",
                "vm",
                "get-instance-view",
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

            instance_view: dict[str, Any] = json.loads(result.stdout)
            return instance_view

        except subprocess.CalledProcessError as e:
            # Return None if VM doesn't exist
            if "ResourceNotFound" in e.stderr:
                logger.debug(f"VM not found: {vm_name}")
                return None
            raise VMQueryError(f"Failed to get VM instance view: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise VMQueryError("VM instance view query timed out") from e
        except json.JSONDecodeError as e:
            raise VMQueryError("Failed to parse VM instance view") from e

    @classmethod
    def get_power_state(cls, vm_info: dict[str, Any]) -> str:
        """Extract power state from VM instance view.

        Args:
            vm_info: VM instance view dictionary (from get_vm_instance_view)

        Returns:
            Power state string (e.g., "VM running", "VM stopped", "VM deallocated")
            Returns "Unknown" if power state cannot be determined
        """
        statuses = vm_info.get("statuses", [])

        for status in statuses:
            code = status.get("code", "")
            if code.startswith("PowerState/"):
                # Convert "PowerState/running" -> "VM running"
                power_state = code.replace("PowerState/", "")
                return f"VM {power_state}"

        return "Unknown"

    @classmethod
    def get_all_public_ips(cls, resource_group: str) -> dict[str, str]:
        """Get all public IPs in resource group in a single batch call.

        This is more efficient than querying public IPs individually.

        Args:
            resource_group: Resource group name

        Returns:
            Dictionary mapping public IP resource name to IP address
            Returns empty dict on failure (graceful degradation)
        """
        try:
            cmd = [
                "az",
                "network",
                "public-ip",
                "list",
                "--resource-group",
                resource_group,
                "--query",
                "[].{name:name, ip:ipAddress}",
                "--output",
                "json",
            ]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10, check=True
            )

            ips_data: list[dict[str, Any]] = json.loads(result.stdout)
            # Only include IPs that have been assigned (ip is not None)
            return {item["name"]: item["ip"] for item in ips_data if item.get("ip")}

        except Exception as e:
            # Graceful degradation - log but don't fail
            logger.debug(f"Failed to fetch public IPs: {e}")
            return {}


__all__ = ["VMQueryError", "VMQueryService"]
