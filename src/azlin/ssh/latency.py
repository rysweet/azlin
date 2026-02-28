"""SSH latency measurement module.

This module measures SSH connection latency for Azure VMs in parallel.

Philosophy:
- Single responsibility: Measure SSH connection time only
- Self-contained and regeneratable
- Standard library preferred (subprocess over paramiko)
- Fail gracefully - one VM failure doesn't stop others

Public API (the "studs"):
    LatencyResult: Encapsulates measurement result
    SSHLatencyMeasurer: Core measurement logic
"""

import ipaddress
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass


@dataclass
class LatencyResult:
    """Result of SSH latency measurement.

    Attributes:
        vm_name: VM name
        success: Whether measurement succeeded
        latency_ms: Latency in milliseconds (None if failed)
        error_type: Error type if failed ("timeout", "connection", "vm_stopped", "unknown")
        error_message: Detailed error message
    """

    vm_name: str
    success: bool
    latency_ms: float | None = None
    error_type: str | None = None
    error_message: str | None = None

    def display_value(self) -> str:
        """Get display string for table.

        Returns:
            Formatted string for display:
            - "45ms" for successful measurements
            - "timeout" for timeouts
            - "error" for connection errors
            - "bastion" for Bastion-only VMs (no public IP)
            - "-" for unknown or N/A
        """
        if self.success and self.latency_ms is not None:
            return f"{round(self.latency_ms)}ms"
        if self.error_type == "timeout":
            return "timeout"
        if self.error_type == "connection":
            return "error"
        if self.error_type == "bastion":
            return "bastion"
        return "-"


class SSHLatencyMeasurer:
    """Measure SSH connection latency for VMs.

    Measures time to establish SSH connection (not Bastion tunnel).
    Uses ThreadPoolExecutor for parallel measurement.

    Implementation uses subprocess ssh command for reliability:
    - Simpler than paramiko (uses system SSH)
    - More reliable (handles edge cases like proxies, Kerberos)
    - Familiar behavior (same as manual SSH)
    - Standard library only
    """

    def __init__(self, timeout: float = 5.0, max_workers: int = 10):
        """Initialize latency measurer.

        Args:
            timeout: Connection timeout per VM (seconds)
            max_workers: Maximum parallel workers
        """
        self.timeout = timeout
        self.max_workers = max_workers

    def _validate_ssh_params(self, ssh_user: str, host: str) -> None:
        """Validate SSH parameters to prevent injection.

        Args:
            ssh_user: SSH username (must be alphanumeric + underscore/hyphen)
            host: IP address (must be valid IPv4 or IPv6)

        Raises:
            ValueError: If parameters are invalid
        """
        # SSH user must be alphanumeric + underscore/hyphen
        if not re.match(r"^[a-zA-Z0-9_-]+$", ssh_user):
            raise ValueError(f"Invalid SSH username: {ssh_user}")

        # Host must be valid IP address
        try:
            ipaddress.ip_address(host)
        except ValueError as e:
            raise ValueError(f"Invalid IP address: {host}") from e

    def measure_single(
        self, vm, ssh_user: str = "azureuser", ssh_key_path: str | None = None
    ) -> LatencyResult:
        """Measure latency for a single VM.

        Implementation uses subprocess ssh command:
        1. Start timer
        2. Execute: ssh -o ConnectTimeout=5 user@host "true"
        3. Measure elapsed time
        4. Return result with latency or error

        Args:
            vm: VM object with name, private_ip, and is_running() method
            ssh_user: SSH username
            ssh_key_path: Path to SSH private key

        Returns:
            LatencyResult with measurement or error
        """
        # Skip stopped VMs (should be filtered by caller, but handle gracefully)
        if not vm.is_running():
            return LatencyResult(
                vm_name=vm.name,
                success=False,
                error_type="vm_stopped",
                error_message="VM is not running",
            )

        # Use public_ip for direct SSH; Bastion-only VMs cannot be measured without a tunnel
        if vm.public_ip:
            host = vm.public_ip
        else:
            return LatencyResult(
                vm_name=vm.name,
                success=False,
                error_type="bastion",
                error_message="Bastion-only VM - SSH latency requires direct connection",
            )

        # Validate inputs at boundary to prevent injection
        try:
            self._validate_ssh_params(ssh_user, host)
        except ValueError as e:
            return LatencyResult(
                vm_name=vm.name, success=False, error_type="connection", error_message=str(e)
            )

        try:
            start_time = time.time()

            # Build SSH command
            cmd = [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                f"ConnectTimeout={int(self.timeout)}",
                "-o",
                "BatchMode=yes",
                "-o",
                "PasswordAuthentication=no",
            ]

            # Add SSH key if provided
            if ssh_key_path:
                cmd.extend(["-i", ssh_key_path])

            # Add user@host and command
            cmd.append(f"{ssh_user}@{host}")
            cmd.append("true")  # Just test connection, don't run command

            # Execute SSH command
            result = subprocess.run(cmd, capture_output=True, timeout=self.timeout, text=True)

            elapsed_ms = (time.time() - start_time) * 1000  # Convert to ms

            # Check return code
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "SSH connection failed"
                return LatencyResult(
                    vm_name=vm.name, success=False, error_type="connection", error_message=error_msg
                )

            # Success!
            return LatencyResult(vm_name=vm.name, success=True, latency_ms=elapsed_ms)

        except subprocess.TimeoutExpired:
            return LatencyResult(
                vm_name=vm.name,
                success=False,
                error_type="timeout",
                error_message=f"Connection timeout after {self.timeout} seconds",
            )

        except Exception as e:
            return LatencyResult(
                vm_name=vm.name, success=False, error_type="unknown", error_message=str(e)
            )

    def measure_at_port(
        self,
        vm_name: str,
        host: str,
        port: int,
        ssh_user: str = "azureuser",
        ssh_key_path: str | None = None,
    ) -> LatencyResult:
        """Measure SSH latency at an explicit host:port.

        Used for Bastion tunnel connections where the tunnel is already
        established at 127.0.0.1:local_port. Skips VM object lookup —
        caller supplies host/port directly.

        Args:
            vm_name: VM name (for result identification)
            host: Host to connect to (typically "127.0.0.1" for tunnels)
            port: Port to connect on (tunnel local port)
            ssh_user: SSH username
            ssh_key_path: Path to SSH private key

        Returns:
            LatencyResult with measurement or error
        """
        try:
            self._validate_ssh_params(ssh_user, host)
        except ValueError as e:
            return LatencyResult(
                vm_name=vm_name, success=False, error_type="connection", error_message=str(e)
            )

        try:
            start_time = time.time()
            cmd = [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                f"ConnectTimeout={int(self.timeout)}",
                "-o",
                "BatchMode=yes",
                "-o",
                "PasswordAuthentication=no",
                "-p",
                str(port),
            ]
            if ssh_key_path:
                cmd.extend(["-i", ssh_key_path])
            cmd.append(f"{ssh_user}@{host}")
            cmd.append("true")

            result = subprocess.run(cmd, capture_output=True, timeout=self.timeout, text=True)
            elapsed_ms = (time.time() - start_time) * 1000

            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "SSH connection failed"
                return LatencyResult(
                    vm_name=vm_name, success=False, error_type="connection", error_message=error_msg
                )

            return LatencyResult(vm_name=vm_name, success=True, latency_ms=elapsed_ms)

        except subprocess.TimeoutExpired:
            return LatencyResult(
                vm_name=vm_name,
                success=False,
                error_type="timeout",
                error_message=f"Connection timeout after {self.timeout} seconds",
            )
        except Exception as e:
            return LatencyResult(
                vm_name=vm_name, success=False, error_type="unknown", error_message=str(e)
            )

    def measure_batch(
        self, vms: list, ssh_user: str = "azureuser", ssh_key_path: str | None = None
    ) -> dict[str, LatencyResult]:
        """Measure latency for multiple VMs in parallel.

        Uses ThreadPoolExecutor to measure all VMs concurrently:
        1. Filter to running VMs only (skip stopped)
        2. Submit all measurement tasks to executor
        3. Collect results as they complete
        4. Return dict mapping VM name to result

        Args:
            vms: List of VM objects
            ssh_user: SSH username
            ssh_key_path: Path to SSH private key

        Returns:
            Dictionary mapping VM name to LatencyResult
        """
        results: dict[str, LatencyResult] = {}

        # Filter to running VMs only
        running_vms = [vm for vm in vms if vm.is_running()]

        if not running_vms:
            return results

        # Use ThreadPoolExecutor for parallel measurement
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_vm = {
                executor.submit(self.measure_single, vm, ssh_user, ssh_key_path): vm
                for vm in running_vms
            }

            # Collect results as they complete
            for future in as_completed(future_to_vm):
                vm = future_to_vm[future]
                result = future.result()
                results[vm.name] = result

        return results


__all__ = ["LatencyResult", "SSHLatencyMeasurer"]
