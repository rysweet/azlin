"""Health Monitor - VM health checking via Azure CLI.

Philosophy:
- Ruthless simplicity: All data from Azure CLI, no SSH needed
- Single responsibility: Health checking only
- Uses proven patterns: Azure CLI (like status_dashboard.py)
- Self-contained: Complete with failure tracking

Public API (Studs):
    HealthMonitor - Main health checking service
    HealthStatus - Health check result
    VMState - VM power state enum
    VMMetrics - VM resource metrics
    HealthFailure - Failure event
    HealthCheckError - Health check errors
"""

import contextlib
import json
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


class VMState(StrEnum):
    """VM power states from Azure."""

    RUNNING = "running"
    STOPPED = "stopped"
    DEALLOCATED = "deallocated"
    UNKNOWN = "unknown"


class HealthCheckError(Exception):
    """Raised when health check operations fail."""

    pass


@dataclass
class VMMetrics:
    """VM resource metrics."""

    cpu_percent: float
    memory_percent: float
    disk_percent: float


@dataclass
class HealthFailure:
    """Health check failure event."""

    vm_name: str
    failure_count: int
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class HealthStatus:
    """Health check result for a VM."""

    vm_name: str
    state: VMState
    ssh_reachable: bool
    ssh_failures: int
    last_check: datetime
    metrics: VMMetrics | None = None


class HealthMonitor:
    """Monitors VM health via Azure CLI.

    Uses Azure CLI to get VM state and VM Agent health from the instance
    view (single API call), then gathers metrics via az vm run-command
    for running VMs in parallel.

    Works with all VM types including Bastion-only VMs (no public IP)
    since it goes through Azure's management plane, not SSH.

    Example:
        >>> monitor = HealthMonitor(resource_group="my-rg")
        >>> health = monitor.check_vm_health("my-vm")
        >>> print(f"VM state: {health.state}, Agent: {health.ssh_reachable}")
    """

    def __init__(self, resource_group: str | None = None):
        """Initialize health monitor.

        Args:
            resource_group: Azure resource group. If None, will be
                resolved from config when needed.
        """
        self._ssh_failure_counts: dict[str, int] = {}
        self._resource_group = resource_group

    def _get_resource_group(self) -> str:
        """Get resource group, resolving from config if needed."""
        if self._resource_group:
            return self._resource_group

        from azlin.config_manager import ConfigManager

        rg = ConfigManager.get_resource_group(None, None)
        if not rg:
            raise HealthCheckError("No resource group configured")
        self._resource_group = rg
        return rg

    def _run_az_command(self, command: list[str], timeout: int = 30) -> dict:
        """Run an Azure CLI command and return parsed JSON.

        Args:
            command: Azure CLI command as list of strings
            timeout: Command timeout in seconds

        Returns:
            Parsed JSON output

        Raises:
            HealthCheckError: If command fails
        """
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if result.returncode != 0:
                raise HealthCheckError(f"Azure CLI failed: {result.stderr.strip()}")
            if not result.stdout.strip():
                return {}
            return json.loads(result.stdout)
        except subprocess.TimeoutExpired as e:
            raise HealthCheckError(f"Azure CLI timed out after {timeout}s") from e
        except json.JSONDecodeError as e:
            raise HealthCheckError(f"Failed to parse Azure CLI output: {e}") from e

    def _get_instance_view(self, vm_name: str) -> dict:
        """Get VM instance view from Azure CLI.

        Returns the full instance view which contains both power state
        and VM Agent health status in a single API call.

        Args:
            vm_name: VM name

        Returns:
            Instance view dictionary

        Raises:
            HealthCheckError: If Azure CLI call fails
        """
        rg = self._get_resource_group()
        command = [
            "az",
            "vm",
            "get-instance-view",
            "--name",
            vm_name,
            "--resource-group",
            rg,
            "--output",
            "json",
        ]
        return self._run_az_command(command)

    def _extract_power_state(self, instance_view: dict) -> VMState:
        """Extract VM power state from instance view.

        Args:
            instance_view: Instance view from Azure CLI

        Returns:
            VMState enum value
        """
        # Check nested instanceView first, then root-level statuses
        statuses = instance_view.get("instanceView", {}).get("statuses", [])
        if not statuses:
            statuses = instance_view.get("statuses", [])

        for status in statuses:
            code = status.get("code", "")
            if code.startswith("PowerState/"):
                state_str = code.replace("PowerState/", "").lower()
                state_map = {
                    "running": VMState.RUNNING,
                    "stopped": VMState.STOPPED,
                    "deallocated": VMState.DEALLOCATED,
                }
                return state_map.get(state_str, VMState.UNKNOWN)

        return VMState.UNKNOWN

    def _extract_agent_healthy(self, instance_view: dict) -> bool:
        """Extract VM Agent health from instance view.

        The VM Agent status is the best indicator of OS health for
        Bastion-only VMs where direct SSH port checks don't work.

        Args:
            instance_view: Instance view from Azure CLI

        Returns:
            True if VM Agent reports "Ready", False otherwise
        """
        vm_agent = instance_view.get("instanceView", {}).get("vmAgent", {})
        if not vm_agent:
            vm_agent = instance_view.get("vmAgent", {})

        agent_statuses = vm_agent.get("statuses", [])
        for status in agent_statuses:
            display = status.get("displayStatus", "")
            if display == "Ready":
                return True

        return False

    def get_vm_state(self, vm_name: str) -> VMState:
        """Get VM power state from Azure CLI.

        Args:
            vm_name: VM name

        Returns:
            VMState enum value

        Raises:
            HealthCheckError: If Azure CLI call fails
        """
        try:
            instance_view = self._get_instance_view(vm_name)
            return self._extract_power_state(instance_view)
        except HealthCheckError:
            raise
        except Exception as e:
            raise HealthCheckError(f"Failed to get VM state: {e}") from e

    def check_ssh_connectivity(self, vm_name: str, timeout: int = 10) -> bool:
        """Check if VM is healthy using VM Agent status.

        Uses VM Agent health from Azure instance view instead of direct
        SSH port checks. This works for all VM types including
        Bastion-only VMs with no public IP.

        Args:
            vm_name: VM name
            timeout: Unused (kept for API compatibility)

        Returns:
            True if VM Agent is healthy, False otherwise
        """
        try:
            instance_view = self._get_instance_view(vm_name)
            return self._extract_agent_healthy(instance_view)
        except Exception as e:
            logger.debug(f"Agent health check failed for {vm_name}: {e}")
            return False

    def get_metrics(self, vm_name: str) -> VMMetrics | None:
        """Get VM resource metrics via az vm run-command.

        Uses Azure's management plane to execute commands on the VM,
        which works regardless of SSH/Bastion configuration.

        Args:
            vm_name: VM name

        Returns:
            VMMetrics if successful, None on failure
        """
        try:
            rg = self._get_resource_group()
            metrics_script = (
                "echo CPU=$(top -bn1 | grep 'Cpu(s)' | awk '{print $2}') && "
                "echo MEM=$(free | awk '/Mem:/{printf \"%.1f\", $3/$2*100}') && "
                "echo DISK=$(df / | awk 'NR==2{print $5}' | tr -d '%')"
            )
            command = [
                "az",
                "vm",
                "run-command",
                "invoke",
                "--name",
                vm_name,
                "--resource-group",
                rg,
                "--command-id",
                "RunShellScript",
                "--scripts",
                metrics_script,
                "--output",
                "json",
            ]

            result = self._run_az_command(command, timeout=60)

            # Parse the run-command output
            values = result.get("value", [])
            if not values:
                return None

            message = values[0].get("message", "")
            # Extract stdout section from message
            stdout = ""
            if "[stdout]" in message:
                stdout = message.split("[stdout]")[1]
                if "[stderr]" in stdout:
                    stdout = stdout.split("[stderr]")[0]

            cpu = 0.0
            mem = 0.0
            disk = 0.0

            for line in stdout.strip().split("\n"):
                line = line.strip()
                if line.startswith("CPU="):
                    with contextlib.suppress(ValueError, IndexError):
                        cpu = float(line.split("=", 1)[1])
                elif line.startswith("MEM="):
                    with contextlib.suppress(ValueError, IndexError):
                        mem = float(line.split("=", 1)[1])
                elif line.startswith("DISK="):
                    with contextlib.suppress(ValueError, IndexError):
                        disk = float(line.split("=", 1)[1])

            return VMMetrics(cpu_percent=cpu, memory_percent=mem, disk_percent=disk)
        except Exception as e:
            logger.debug(f"Failed to get metrics for {vm_name}: {e}")
            return None

    def check_vm_health(self, vm_name: str) -> HealthStatus:
        """Perform comprehensive health check on VM.

        Gets state and agent health from a single instance view call,
        then gathers metrics via run-command for running VMs.

        Args:
            vm_name: VM name

        Returns:
            HealthStatus with current health state
        """
        try:
            instance_view = self._get_instance_view(vm_name)
        except HealthCheckError:
            raise
        except Exception as e:
            raise HealthCheckError(f"Failed to get instance view: {e}") from e

        # Extract state and agent health from the same instance view
        state = self._extract_power_state(instance_view)
        agent_healthy = (
            self._extract_agent_healthy(instance_view) if state == VMState.RUNNING else False
        )

        metrics = None

        if state == VMState.RUNNING and agent_healthy:
            self._ssh_failure_counts[vm_name] = 0
            metrics = self.get_metrics(vm_name)
        elif state == VMState.RUNNING:
            current_failures = self._ssh_failure_counts.get(vm_name, 0)
            self._ssh_failure_counts[vm_name] = current_failures + 1

        return HealthStatus(
            vm_name=vm_name,
            state=state,
            ssh_reachable=agent_healthy,
            ssh_failures=self._ssh_failure_counts.get(vm_name, 0),
            last_check=datetime.now(UTC),
            metrics=metrics,
        )

    def check_all_vms_health(
        self, vm_names: list[str], max_workers: int = 5
    ) -> list[tuple[str, HealthStatus | None, str | None]]:
        """Check health for multiple VMs in parallel.

        Args:
            vm_names: List of VM names to check
            max_workers: Max parallel workers

        Returns:
            List of (vm_name, health_status_or_none, error_or_none)
        """
        results: list[tuple[str, HealthStatus | None, str | None]] = []
        num_workers = min(max_workers, len(vm_names))

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_to_vm = {executor.submit(self.check_vm_health, name): name for name in vm_names}

            for future in as_completed(future_to_vm):
                vm_name = future_to_vm[future]
                try:
                    status = future.result()
                    results.append((vm_name, status, None))
                except HealthCheckError as e:
                    results.append((vm_name, None, str(e)))
                except Exception as e:
                    results.append((vm_name, None, f"Unexpected: {e}"))

        # Sort by original order
        name_order = {name: i for i, name in enumerate(vm_names)}
        results.sort(key=lambda r: name_order.get(r[0], 999))

        return results


__all__ = [
    "HealthCheckError",
    "HealthFailure",
    "HealthMonitor",
    "HealthStatus",
    "VMMetrics",
    "VMState",
]
