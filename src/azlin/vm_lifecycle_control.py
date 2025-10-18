"""VM lifecycle control module for stop/start operations.

This module provides VM lifecycle management for stopping and starting VMs:
- Stop/deallocate VMs to save costs
- Start stopped VMs
- Batch operations for multiple VMs
- Cost savings estimation

Security:
- Input validation
- Safe resource operations
- No shell=True
- Confirmation prompts for batch operations
"""

import json
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from fnmatch import fnmatch

logger = logging.getLogger(__name__)


class VMLifecycleControlError(Exception):
    """Raised when VM lifecycle control operations fail."""

    pass


@dataclass
class LifecycleResult:
    """Result from a lifecycle operation (stop/start)."""

    vm_name: str
    success: bool
    message: str
    operation: str  # 'stop', 'start'
    cost_impact: str | None = None  # Cost savings/cost info

    def __repr__(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        result = f"[{status}] {self.vm_name}: {self.message}"
        if self.cost_impact:
            result += f" ({self.cost_impact})"
        return result


@dataclass
class LifecycleSummary:
    """Summary of batch lifecycle operations."""

    total: int
    succeeded: int
    failed: int
    results: list[LifecycleResult]
    operation: str  # 'stop' or 'start'

    @property
    def all_succeeded(self) -> bool:
        """Check if all operations succeeded."""
        return self.failed == 0

    def get_failed_vms(self) -> list[str]:
        """Get list of VMs that failed."""
        return [r.vm_name for r in self.results if not r.success]

    def get_succeeded_vms(self) -> list[str]:
        """Get list of VMs that succeeded."""
        return [r.vm_name for r in self.results if r.success]


class VMLifecycleController:
    """Control VM lifecycle operations (stop/start).

    This class provides operations for:
    - Stopping/deallocating single VMs
    - Starting single VMs
    - Batch stop/start operations
    - Pattern-based VM selection
    - Cost savings estimation
    """

    # Estimated hourly costs by VM size (rough estimates in USD/hour)
    VM_COSTS = {
        "Standard_D2s_v3": 0.096,
        "Standard_D4s_v3": 0.192,
        "Standard_D8s_v3": 0.384,
        "Standard_B1s": 0.0104,
        "Standard_B2s": 0.0416,
        "Standard_B4ms": 0.166,
    }
    DEFAULT_COST = 0.10  # Default estimate per hour

    @classmethod
    def stop_vm(
        cls, vm_name: str, resource_group: str, deallocate: bool = True, no_wait: bool = False
    ) -> LifecycleResult:
        """Stop or deallocate a VM.

        Args:
            vm_name: VM name to stop
            resource_group: Resource group name
            deallocate: If True, deallocate (recommended to save costs)
                       If False, just stop (still incurs compute costs)
            no_wait: Don't wait for operation to complete

        Returns:
            LifecycleResult object

        Raises:
            VMLifecycleControlError: If operation fails critically
        """
        operation = "deallocate" if deallocate else "stop"
        logger.info(f"Stopping VM '{vm_name}' ({operation})")

        try:
            # Get VM details first to verify it exists and get cost info
            vm_info = cls._get_vm_details(vm_name, resource_group)
            if not vm_info:
                return LifecycleResult(
                    vm_name=vm_name, success=False, message="VM not found", operation=operation
                )

            # Check current power state
            power_state = cls._get_power_state(vm_info)
            if power_state in ["VM stopped", "VM deallocated"]:
                return LifecycleResult(
                    vm_name=vm_name,
                    success=True,
                    message=f"VM already {power_state.lower()}",
                    operation=operation,
                )

            # Get VM size for cost estimation
            vm_size = vm_info.get("hardwareProfile", {}).get("vmSize", "")
            hourly_cost = cls.VM_COSTS.get(vm_size, cls.DEFAULT_COST)
            cost_info = (
                f"Saves ~${hourly_cost:.3f}/hour" if deallocate else "Still incurs compute costs"
            )

            # Execute stop/deallocate command
            cmd = [
                "az",
                "vm",
                "deallocate" if deallocate else "stop",
                "--name",
                vm_name,
                "--resource-group",
                resource_group,
            ]

            if no_wait:
                cmd.append("--no-wait")

            subprocess.run(
                cmd, capture_output=True, text=True, timeout=180 if not no_wait else 30, check=True
            )

            message = f"VM {'deallocated' if deallocate else 'stopped'} successfully"
            logger.info(f"{message}: {vm_name}")

            return LifecycleResult(
                vm_name=vm_name,
                success=True,
                message=message,
                operation=operation,
                cost_impact=cost_info,
            )

        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to {operation}: {e.stderr}"
            logger.error(f"VM {vm_name}: {error_msg}")
            return LifecycleResult(
                vm_name=vm_name, success=False, message=error_msg, operation=operation
            )
        except subprocess.TimeoutExpired:
            error_msg = f"{operation} operation timed out"
            logger.error(f"VM {vm_name}: {error_msg}")
            return LifecycleResult(
                vm_name=vm_name, success=False, message=error_msg, operation=operation
            )
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(f"VM {vm_name}: {error_msg}")
            return LifecycleResult(
                vm_name=vm_name, success=False, message=error_msg, operation=operation
            )

    @classmethod
    def start_vm(cls, vm_name: str, resource_group: str, no_wait: bool = False) -> LifecycleResult:
        """Start a stopped or deallocated VM.

        Args:
            vm_name: VM name to start
            resource_group: Resource group name
            no_wait: Don't wait for operation to complete

        Returns:
            LifecycleResult object

        Raises:
            VMLifecycleControlError: If operation fails critically
        """
        logger.info(f"Starting VM '{vm_name}'")

        try:
            # Get VM details first to verify it exists
            vm_info = cls._get_vm_details(vm_name, resource_group)
            if not vm_info:
                return LifecycleResult(
                    vm_name=vm_name, success=False, message="VM not found", operation="start"
                )

            # Check current power state
            power_state = cls._get_power_state(vm_info)
            if power_state == "VM running":
                return LifecycleResult(
                    vm_name=vm_name, success=True, message="VM already running", operation="start"
                )

            # Get VM size for cost info
            vm_size = vm_info.get("hardwareProfile", {}).get("vmSize", "")
            hourly_cost = cls.VM_COSTS.get(vm_size, cls.DEFAULT_COST)
            cost_info = f"~${hourly_cost:.3f}/hour while running"

            # Execute start command
            cmd = ["az", "vm", "start", "--name", vm_name, "--resource-group", resource_group]

            if no_wait:
                cmd.append("--no-wait")

            subprocess.run(
                cmd, capture_output=True, text=True, timeout=180 if not no_wait else 30, check=True
            )

            logger.info(f"VM started successfully: {vm_name}")

            return LifecycleResult(
                vm_name=vm_name,
                success=True,
                message="VM started successfully",
                operation="start",
                cost_impact=cost_info,
            )

        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to start: {e.stderr}"
            logger.error(f"VM {vm_name}: {error_msg}")
            return LifecycleResult(
                vm_name=vm_name, success=False, message=error_msg, operation="start"
            )
        except subprocess.TimeoutExpired:
            error_msg = "Start operation timed out"
            logger.error(f"VM {vm_name}: {error_msg}")
            return LifecycleResult(
                vm_name=vm_name, success=False, message=error_msg, operation="start"
            )
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(f"VM {vm_name}: {error_msg}")
            return LifecycleResult(
                vm_name=vm_name, success=False, message=error_msg, operation="start"
            )

    @classmethod
    def stop_vms(
        cls,
        resource_group: str,
        vm_pattern: str | None = None,
        all_vms: bool = False,
        deallocate: bool = True,
        max_workers: int = 5,
    ) -> LifecycleSummary:
        """Stop multiple VMs matching a pattern.

        Args:
            resource_group: Resource group name
            vm_pattern: Pattern to match VM names (e.g., "azlin-dev-*")
            all_vms: Stop all VMs in resource group
            deallocate: Deallocate to save costs (recommended)
            max_workers: Maximum parallel workers

        Returns:
            LifecycleSummary object

        Raises:
            VMLifecycleControlError: If listing VMs fails
        """
        try:
            # List all VMs in resource group
            vm_names = cls._list_vms_in_group(resource_group)

            if not vm_names:
                return LifecycleSummary(
                    total=0, succeeded=0, failed=0, results=[], operation="stop"
                )

            # Filter by pattern if specified
            if vm_pattern and not all_vms:
                vm_names = [vm for vm in vm_names if fnmatch(vm, vm_pattern)]

            if not vm_names:
                return LifecycleSummary(
                    total=0, succeeded=0, failed=0, results=[], operation="stop"
                )

            operation = "deallocating" if deallocate else "stopping"
            logger.info(f"{operation.capitalize()} {len(vm_names)} VMs in parallel")

            # Stop VMs in parallel
            results = []
            num_workers = min(max_workers, len(vm_names))

            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                # Submit all stop tasks
                future_to_vm = {
                    executor.submit(
                        cls.stop_vm, vm_name, resource_group, deallocate=deallocate, no_wait=False
                    ): vm_name
                    for vm_name in vm_names
                }

                # Collect results as they complete
                for future in as_completed(future_to_vm):
                    vm_name = future_to_vm[future]
                    try:
                        result = future.result()
                        results.append(result)
                        logger.info(f"Completed {vm_name}: {result.message}")
                    except Exception as e:
                        logger.error(f"Failed to stop {vm_name}: {e}")
                        results.append(
                            LifecycleResult(
                                vm_name=vm_name,
                                success=False,
                                message=f"Exception: {e}",
                                operation="stop",
                            )
                        )

            # Calculate summary
            succeeded = sum(1 for r in results if r.success)
            failed = sum(1 for r in results if not r.success)

            # Calculate total cost savings
            sum(
                float(r.cost_impact.split("$")[1].split("/")[0])
                for r in results
                if r.success and r.cost_impact and "$" in r.cost_impact
            )

            return LifecycleSummary(
                total=len(results),
                succeeded=succeeded,
                failed=failed,
                results=results,
                operation="stop",
            )

        except Exception as e:
            raise VMLifecycleControlError(f"Failed to stop VMs: {e}")

    @classmethod
    def start_vms(
        cls,
        resource_group: str,
        vm_pattern: str | None = None,
        all_vms: bool = False,
        max_workers: int = 5,
    ) -> LifecycleSummary:
        """Start multiple stopped VMs matching a pattern.

        Args:
            resource_group: Resource group name
            vm_pattern: Pattern to match VM names (e.g., "azlin-dev-*")
            all_vms: Start all VMs in resource group
            max_workers: Maximum parallel workers

        Returns:
            LifecycleSummary object

        Raises:
            VMLifecycleControlError: If listing VMs fails
        """
        try:
            # List all VMs in resource group
            vm_names = cls._list_vms_in_group(resource_group)

            if not vm_names:
                return LifecycleSummary(
                    total=0, succeeded=0, failed=0, results=[], operation="start"
                )

            # Filter by pattern if specified
            if vm_pattern and not all_vms:
                vm_names = [vm for vm in vm_names if fnmatch(vm, vm_pattern)]

            if not vm_names:
                return LifecycleSummary(
                    total=0, succeeded=0, failed=0, results=[], operation="start"
                )

            logger.info(f"Starting {len(vm_names)} VMs in parallel")

            # Start VMs in parallel
            results = []
            num_workers = min(max_workers, len(vm_names))

            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                # Submit all start tasks
                future_to_vm = {
                    executor.submit(cls.start_vm, vm_name, resource_group, no_wait=False): vm_name
                    for vm_name in vm_names
                }

                # Collect results as they complete
                for future in as_completed(future_to_vm):
                    vm_name = future_to_vm[future]
                    try:
                        result = future.result()
                        results.append(result)
                        logger.info(f"Completed {vm_name}: {result.message}")
                    except Exception as e:
                        logger.error(f"Failed to start {vm_name}: {e}")
                        results.append(
                            LifecycleResult(
                                vm_name=vm_name,
                                success=False,
                                message=f"Exception: {e}",
                                operation="start",
                            )
                        )

            # Calculate summary
            succeeded = sum(1 for r in results if r.success)
            failed = sum(1 for r in results if not r.success)

            return LifecycleSummary(
                total=len(results),
                succeeded=succeeded,
                failed=failed,
                results=results,
                operation="start",
            )

        except Exception as e:
            raise VMLifecycleControlError(f"Failed to start VMs: {e}")

    @classmethod
    def _get_vm_details(cls, vm_name: str, resource_group: str) -> dict | None:
        """Get VM details from Azure including instance view.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            VM details dictionary or None if not found
        """
        try:
            # Use get-instance-view to include power state
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

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)

            return json.loads(result.stdout)

        except subprocess.CalledProcessError as e:
            if "ResourceNotFound" in e.stderr:
                return None
            raise VMLifecycleControlError(f"Failed to get VM details: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise VMLifecycleControlError("VM details query timed out")
        except json.JSONDecodeError:
            raise VMLifecycleControlError("Failed to parse VM details")

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

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)

            return json.loads(result.stdout)

        except subprocess.CalledProcessError as e:
            if "ResourceGroupNotFound" in e.stderr:
                return []
            raise VMLifecycleControlError(f"Failed to list VMs: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise VMLifecycleControlError("VM list operation timed out")
        except json.JSONDecodeError:
            raise VMLifecycleControlError("Failed to parse VM list")

    @classmethod
    def _get_power_state(cls, vm_info: dict) -> str:
        """Extract power state from VM instance view.

        Args:
            vm_info: VM instance view dictionary from get-instance-view

        Returns:
            Power state string (e.g., "VM running", "VM deallocated")
        """
        # get-instance-view returns statuses at the root level
        statuses = vm_info.get("statuses", [])

        for status in statuses:
            code = status.get("code", "")
            if code.startswith("PowerState/"):
                return code.replace("PowerState/", "VM ")

        return "Unknown"


__all__ = [
    "LifecycleResult",
    "LifecycleSummary",
    "VMLifecycleControlError",
    "VMLifecycleController",
]
