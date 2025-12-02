"""Health Monitor - VM health checking via Azure API and SSH.

Philosophy:
- Ruthless simplicity: Direct Azure API + SSH checks
- Single responsibility: Health checking only
- Standard library: Only Azure SDK and SSH for checks
- Self-contained: Complete with failure tracking

Public API (Studs):
    HealthMonitor - Main health checking service
    HealthStatus - Health check result
    VMState - VM power state enum
    VMMetrics - VM resource metrics
    HealthFailure - Failure event
    HealthCheckError - Health check errors
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class VMState(str, Enum):
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
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class HealthStatus:
    """Health check result for a VM."""
    vm_name: str
    state: VMState
    ssh_reachable: bool
    ssh_failures: int
    last_check: datetime
    metrics: Optional[VMMetrics] = None


class HealthMonitor:
    """Monitors VM health via Azure API and SSH.

    Tracks SSH failure counts per VM and provides health status.

    Example:
        >>> monitor = HealthMonitor()
        >>> health = monitor.check_vm_health("my-vm")
        >>> print(f"VM state: {health.state}, SSH: {health.ssh_reachable}")
    """

    def __init__(self):
        """Initialize health monitor."""
        self._ssh_failure_counts: Dict[str, int] = {}
        self._azure_client = None
        self._ssh_client = None

    def _get_azure_client(self):
        """Lazy-load Azure client."""
        if self._azure_client is None:
            # Import here to allow for mocking in tests
            import azlin.azure_client
            self._azure_client = azlin.azure_client.AzureClient()
        return self._azure_client

    def _get_ssh_client(self):
        """Lazy-load SSH client."""
        if self._ssh_client is None:
            # Import here to allow for mocking in tests
            import azlin.ssh_client
            self._ssh_client = azlin.ssh_client.SSHClient()
        return self._ssh_client

    def get_vm_state(self, vm_name: str) -> VMState:
        """Get VM power state from Azure.

        Args:
            vm_name: VM name

        Returns:
            VMState enum value

        Raises:
            HealthCheckError: If Azure API call fails
        """
        try:
            client = self._get_azure_client()
            state_str = client.get_vm_state(vm_name)

            # Map Azure states to our enum
            state_map = {
                "Running": VMState.RUNNING,
                "Stopped": VMState.STOPPED,
                "Deallocated": VMState.DEALLOCATED,
            }
            return state_map.get(state_str, VMState.UNKNOWN)
        except Exception as e:
            raise HealthCheckError(f"Failed to get VM state: {e}") from e

    def check_ssh_connectivity(self, vm_name: str, timeout: int = 30) -> bool:
        """Check if SSH is reachable.

        Args:
            vm_name: VM name
            timeout: Connection timeout in seconds

        Returns:
            True if SSH is reachable, False otherwise
        """
        try:
            client = self._get_ssh_client()
            return client.check_connectivity(vm_name, timeout=timeout)
        except (TimeoutError, Exception) as e:
            logger.debug(f"SSH check failed for {vm_name}: {e}")
            return False

    def get_metrics(self, vm_name: str) -> Optional[VMMetrics]:
        """Get VM resource metrics via SSH.

        Args:
            vm_name: VM name

        Returns:
            VMMetrics if successful, None if SSH fails
        """
        try:
            client = self._get_ssh_client()
            return client.get_metrics(vm_name)
        except Exception as e:
            logger.debug(f"Failed to get metrics for {vm_name}: {e}")
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
            last_check=datetime.utcnow(),
            metrics=metrics,
        )


__all__ = [
    "HealthMonitor",
    "HealthStatus",
    "VMState",
    "VMMetrics",
    "HealthFailure",
    "HealthCheckError",
]
