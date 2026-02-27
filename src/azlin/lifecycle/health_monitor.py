"""Health Monitor - VM health checking via Azure CLI and SSH.

Philosophy:
- Ruthless simplicity: Direct Azure CLI + SSH checks
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

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

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
    """VM resource metrics from SSH."""

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
    """Monitors VM health via Azure CLI and SSH.

    Uses Azure CLI directly to get VM state (proven pattern from
    status_dashboard.py and vm_lifecycle_control.py) and SSH to
    check connectivity and gather metrics.

    Tracks SSH failure counts per VM and provides health status.

    Example:
        >>> monitor = HealthMonitor()
        >>> health = monitor.check_vm_health("my-vm")
        >>> print(f"VM state: {health.state}, SSH: {health.ssh_reachable}")
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
                raise HealthCheckError(
                    f"Azure CLI failed: {result.stderr.strip()}"
                )
            if not result.stdout.strip():
                return {}
            return json.loads(result.stdout)
        except subprocess.TimeoutExpired as e:
            raise HealthCheckError(f"Azure CLI timed out after {timeout}s") from e
        except json.JSONDecodeError as e:
            raise HealthCheckError(f"Failed to parse Azure CLI output: {e}") from e

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
            rg = self._get_resource_group()
            command = [
                "az", "vm", "get-instance-view",
                "--name", vm_name,
                "--resource-group", rg,
                "--output", "json",
            ]
            instance_view = self._run_az_command(command)

            # Extract power state from instance view statuses
            statuses = instance_view.get("instanceView", {}).get("statuses", [])
            # Also check root-level statuses (get-instance-view format varies)
            if not statuses:
                statuses = instance_view.get("statuses", [])

            for status in statuses:
                code = status.get("code", "")
                if code.startswith("PowerState/"):
                    state_str = code.replace("PowerState/", "")
                    state_map = {
                        "running": VMState.RUNNING,
                        "stopped": VMState.STOPPED,
                        "deallocated": VMState.DEALLOCATED,
                    }
                    return state_map.get(state_str.lower(), VMState.UNKNOWN)

            return VMState.UNKNOWN
        except HealthCheckError:
            raise
        except Exception as e:
            raise HealthCheckError(f"Failed to get VM state: {e}") from e

    def check_ssh_connectivity(self, vm_name: str, timeout: int = 10) -> bool:
        """Check if SSH is reachable by testing TCP port 22.

        Uses a lightweight SSH connection test rather than requiring
        full SSH client setup.

        Args:
            vm_name: VM name
            timeout: Connection timeout in seconds

        Returns:
            True if SSH is reachable, False otherwise
        """
        try:
            # Get VM's IP address
            ip = self._get_vm_ip(vm_name)
            if not ip:
                logger.debug(f"No IP found for {vm_name}")
                return False

            # Test SSH connectivity with a quick connection attempt
            from azlin.modules.ssh_connector import SSHConnector

            return SSHConnector._check_port_open(ip, 22, timeout=float(timeout))
        except Exception as e:
            logger.debug(f"SSH check failed for {vm_name}: {e}")
            return False

    def _get_vm_ip(self, vm_name: str) -> str | None:
        """Get VM IP address (public or private) for SSH checks.

        Args:
            vm_name: VM name

        Returns:
            IP address string or None
        """
        try:
            rg = self._get_resource_group()
            command = [
                "az", "vm", "list-ip-addresses",
                "--name", vm_name,
                "--resource-group", rg,
                "--output", "json",
            ]
            result = self._run_az_command(command)

            if not result or not isinstance(result, list) or len(result) == 0:
                return None

            vm_info = result[0]
            network = vm_info.get("virtualMachine", {}).get("network", {})

            # Try public IP first
            public_ips = network.get("publicIpAddresses", [])
            if public_ips:
                ip = public_ips[0].get("ipAddress")
                if ip:
                    return ip

            # Fall back to private IP
            private_ips = network.get("privateIpAddresses", [])
            if private_ips:
                ip = private_ips[0].get("ipAddress")
                if ip:
                    return ip

            return None
        except Exception as e:
            logger.debug(f"Failed to get IP for {vm_name}: {e}")
            return None

    def get_metrics(self, vm_name: str) -> VMMetrics | None:
        """Get VM resource metrics via SSH.

        Runs lightweight commands over SSH to gather CPU, memory, and
        disk usage percentages.

        Args:
            vm_name: VM name

        Returns:
            VMMetrics if successful, None if SSH fails
        """
        try:
            ip = self._get_vm_ip(vm_name)
            if not ip:
                return None

            # Find SSH key
            key_path = self._find_ssh_key()
            if not key_path:
                logger.debug("No SSH key found for metrics collection")
                return None

            from azlin.modules.ssh_connector import SSHConfig, SSHConnector

            config = SSHConfig(
                host=ip,
                user="azureuser",
                key_path=key_path,
            )

            # Single SSH command to get all metrics at once
            metrics_cmd = (
                "echo CPU=$(top -bn1 | grep 'Cpu(s)' | awk '{print $2}') && "
                "echo MEM=$(free | awk '/Mem:/{printf \"%.1f\", $3/$2*100}') && "
                "echo DISK=$(df / | awk 'NR==2{print $5}' | tr -d '%')"
            )

            try:
                output = SSHConnector.execute_remote_command(
                    config, metrics_cmd, timeout=15
                )
            except Exception as e:
                logger.debug(f"SSH metrics command failed for {vm_name}: {e}")
                return None

            # Parse output
            cpu = 0.0
            mem = 0.0
            disk = 0.0

            for line in output.strip().split("\n"):
                line = line.strip()
                if line.startswith("CPU="):
                    try:
                        cpu = float(line.split("=", 1)[1])
                    except (ValueError, IndexError):
                        pass
                elif line.startswith("MEM="):
                    try:
                        mem = float(line.split("=", 1)[1])
                    except (ValueError, IndexError):
                        pass
                elif line.startswith("DISK="):
                    try:
                        disk = float(line.split("=", 1)[1])
                    except (ValueError, IndexError):
                        pass

            return VMMetrics(cpu_percent=cpu, memory_percent=mem, disk_percent=disk)
        except Exception as e:
            logger.debug(f"Failed to get metrics for {vm_name}: {e}")
            return None

    def _find_ssh_key(self) -> Path | None:
        """Find the SSH key for connecting to VMs.

        Returns:
            Path to SSH key or None
        """
        # Check common azlin key locations
        candidates = [
            Path.home() / ".ssh" / "azlin_key",
            Path.home() / ".ssh" / "id_rsa",
            Path.home() / ".ssh" / "id_ed25519",
        ]
        for key_path in candidates:
            if key_path.exists():
                return key_path
        return None

    def check_vm_health(self, vm_name: str) -> HealthStatus:
        """Perform comprehensive health check on VM.

        Args:
            vm_name: VM name

        Returns:
            HealthStatus with current health state
        """
        # Get VM power state
        state = self.get_vm_state(vm_name)

        # Initialize values
        ssh_reachable = False
        metrics = None

        # Only check SSH if VM is running
        if state == VMState.RUNNING:
            ssh_reachable = self.check_ssh_connectivity(vm_name)

            if ssh_reachable:
                # Reset failure counter on success
                self._ssh_failure_counts[vm_name] = 0
                # Try to get metrics
                metrics = self.get_metrics(vm_name)
            else:
                # Increment failure counter
                current_failures = self._ssh_failure_counts.get(vm_name, 0)
                self._ssh_failure_counts[vm_name] = current_failures + 1
        else:
            # Not running, SSH not reachable
            ssh_reachable = False

        return HealthStatus(
            vm_name=vm_name,
            state=state,
            ssh_reachable=ssh_reachable,
            ssh_failures=self._ssh_failure_counts.get(vm_name, 0),
            last_check=datetime.now(UTC),
            metrics=metrics,
        )


__all__ = [
    "HealthCheckError",
    "HealthFailure",
    "HealthMonitor",
    "HealthStatus",
    "VMMetrics",
    "VMState",
]
