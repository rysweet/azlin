"""Bastion tunnel management module.

This module handles Azure Bastion tunnel lifecycle including:
- Creating SSH tunnels through Bastion hosts
- Managing active tunnel processes
- Port allocation and health checking
- Tunnel cleanup and resource management

Security:
- Localhost-only binding (127.0.0.1)
- Ephemeral port allocation (50000-60000 range)
- Process cleanup on exit (atexit handlers)
- No shell=True for subprocess
- Input validation for resource IDs

Note: Delegates ALL Azure operations to `az network bastion tunnel` CLI.
"""

import atexit
import logging
import os
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


class BastionManagerError(Exception):
    """Raised when Bastion tunnel operations fail."""

    pass


@dataclass
class BastionTunnel:
    """Active Bastion tunnel information.

    Represents an active SSH tunnel through Azure Bastion.
    """

    bastion_name: str
    resource_group: str
    target_vm_id: str  # Full Azure resource ID
    local_port: int
    remote_port: int
    process: subprocess.Popen | None = None

    def is_active(self) -> bool:
        """Check if tunnel process is still running.

        Returns:
            True if tunnel is active, False otherwise
        """
        if not self.process:
            return False
        return self.process.poll() is None


class BastionManager:
    """Manage Azure Bastion tunnels.

    This class provides operations for:
    - Creating SSH tunnels through Bastion
    - Managing tunnel lifecycle
    - Port allocation and availability
    - Health checking and cleanup

    All Azure operations delegate to Azure CLI.
    """

    # Port range for tunnel allocation (ephemeral range)
    DEFAULT_PORT_START = 50000
    DEFAULT_PORT_END = 60000

    # Tunnel readiness timeout
    DEFAULT_TUNNEL_TIMEOUT = 30

    @staticmethod
    def _sanitize_tunnel_error(stderr: str) -> str:
        """Sanitize tunnel process error output to prevent information leakage.

        Args:
            stderr: Raw stderr from az network bastion tunnel

        Returns:
            Sanitized error message safe for user display
        """
        # Check for known safe error patterns
        if "ResourceNotFound" in stderr:
            return "Bastion or VM resource not found"
        if "AuthenticationFailed" in stderr or "Unauthorized" in stderr:
            return "Authentication failed"
        if "AuthorizationFailed" in stderr or "Forbidden" in stderr:
            return "Insufficient permissions"
        if "NetworkNotReachable" in stderr or "timeout" in stderr.lower():
            return "Network connectivity issue"
        if "PortInUse" in stderr or "Address already in use" in stderr:
            return "Local port already in use"
        # Generic message for unknown errors - log full details for debugging
        logger.debug(f"Tunnel error details: {stderr}")
        return "Tunnel creation failed"

    def __init__(self):
        """Initialize BastionManager.

        Sets up active tunnels tracking and cleanup handler.
        """
        self.active_tunnels: list[BastionTunnel] = []

        # Register cleanup handler for process exit
        atexit.register(self.close_all_tunnels)

    def __enter__(self) -> "BastionManager":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - cleanup tunnels."""
        self.close_all_tunnels()

    @staticmethod
    def _validate_vm_resource_id(vm_id: str) -> None:
        """Validate Azure VM resource ID format.

        Args:
            vm_id: VM resource ID to validate

        Raises:
            BastionManagerError: If format is invalid
        """
        # Azure resource ID format: /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines/{name}
        if not vm_id or not vm_id.startswith("/subscriptions/"):
            raise BastionManagerError(
                f"Invalid VM resource ID format: {vm_id}\n"
                f"Expected format: /subscriptions/{{sub}}/resourceGroups/{{rg}}/providers/Microsoft.Compute/virtualMachines/{{name}}"
            )

        if "Microsoft.Compute/virtualMachines" not in vm_id:
            raise BastionManagerError(
                f"Invalid VM resource ID: {vm_id}\nMust be a virtualMachines resource ID"
            )

    @staticmethod
    def _validate_port(port: int, field_name: str) -> None:
        """Validate port number.

        Args:
            port: Port number to validate
            field_name: Field name for error messages

        Raises:
            BastionManagerError: If port is invalid
        """
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise BastionManagerError(
                f"Invalid port number for {field_name}: {port}\nPort must be between 1 and 65535"
            )

    @staticmethod
    def _validate_inputs(
        bastion_name: str, resource_group: str, target_vm_id: str, local_port: int, remote_port: int
    ) -> None:
        """Validate all inputs for tunnel creation.

        Args:
            bastion_name: Bastion host name
            resource_group: Resource group
            target_vm_id: VM resource ID
            local_port: Local port
            remote_port: Remote port

        Raises:
            BastionManagerError: If validation fails
        """
        if not bastion_name:
            raise BastionManagerError("Bastion name cannot be empty")

        if not resource_group:
            raise BastionManagerError("Resource group cannot be empty")

        BastionManager._validate_vm_resource_id(target_vm_id)
        BastionManager._validate_port(local_port, "local_port")
        BastionManager._validate_port(remote_port, "remote_port")

        # Warn about privileged ports
        if local_port < 1024:
            logger.warning(
                f"Using privileged port {local_port}. This may require elevated permissions."
            )

    def get_available_port(
        self, start_port: int = DEFAULT_PORT_START, end_port: int = DEFAULT_PORT_END
    ) -> int:
        """Find an available local port for tunnel.

        Args:
            start_port: Start of port range (default: 50000)
            end_port: End of port range (default: 60000)

        Returns:
            Available port number

        Raises:
            BastionManagerError: If no ports available in range
        """
        for port in range(start_port, end_port + 1):
            try:
                # Try to bind to port to check availability
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind(("127.0.0.1", port))
                    # Port is available
                    return port
            except OSError:
                # Port in use, try next
                continue

        raise BastionManagerError(
            f"No available ports in range {start_port}-{end_port}. "
            f"Close existing tunnels or use different port range."
        )

    def create_tunnel(
        self,
        bastion_name: str,
        resource_group: str,
        target_vm_id: str,
        local_port: int,
        remote_port: int = 22,
        wait_for_ready: bool = True,
        timeout: int = DEFAULT_TUNNEL_TIMEOUT,
    ) -> BastionTunnel:
        """Create SSH tunnel through Azure Bastion.

        Args:
            bastion_name: Bastion host name
            resource_group: Resource group containing Bastion
            target_vm_id: Full Azure resource ID of target VM
            local_port: Local port for tunnel (127.0.0.1 only)
            remote_port: Remote port on VM (default: 22)
            wait_for_ready: Wait for tunnel to be ready (default: True)
            timeout: Timeout in seconds (default: 30)

        Returns:
            BastionTunnel object

        Raises:
            BastionManagerError: If tunnel creation fails

        Security:
            - Binds to 127.0.0.1 only (localhost)
            - No shell=True in subprocess
            - Process cleanup on exit
        """
        # Validate inputs
        self._validate_inputs(bastion_name, resource_group, target_vm_id, local_port, remote_port)

        logger.info(
            f"Creating Bastion tunnel: {bastion_name} -> {target_vm_id} "
            f"(127.0.0.1:{local_port} -> :{remote_port})"
        )

        # Build az command
        cmd = [
            "az",
            "network",
            "bastion",
            "tunnel",
            "--name",
            bastion_name,
            "--resource-group",
            resource_group,
            "--target-resource-id",
            target_vm_id,
            "--resource-port",
            str(remote_port),
            "--port",
            str(local_port),
        ]

        try:
            # Start tunnel process (no shell=True for security)
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Create tunnel object
            tunnel = BastionTunnel(
                bastion_name=bastion_name,
                resource_group=resource_group,
                target_vm_id=target_vm_id,
                local_port=local_port,
                remote_port=remote_port,
                process=process,
            )

            # Track active tunnel
            self.active_tunnels.append(tunnel)

            # Wait for tunnel to be ready if requested
            if wait_for_ready:
                self._wait_for_tunnel_ready(tunnel, timeout)

            logger.info(f"Bastion tunnel created on 127.0.0.1:{local_port}")
            return tunnel

        except OSError as e:
            if "Address already in use" in str(e):
                raise BastionManagerError(
                    f"Port {local_port} already in use. Choose different port or close existing tunnel."
                ) from e
            raise BastionManagerError(f"Failed to start tunnel process: {e}") from e
        except Exception as e:
            raise BastionManagerError(f"Failed to create Bastion tunnel: {e}") from e

    def _wait_for_tunnel_ready(self, tunnel: BastionTunnel, timeout: int) -> None:
        """Wait for tunnel to be ready for connections.

        Args:
            tunnel: Tunnel to check
            timeout: Timeout in seconds

        Raises:
            BastionManagerError: If tunnel fails to become ready
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check if process died
            if not tunnel.is_active():
                # Get error output
                stderr = ""
                if tunnel.process:
                    _, stderr_bytes = tunnel.process.communicate(timeout=1)
                    stderr = (
                        stderr_bytes
                        if isinstance(stderr_bytes, str)
                        else stderr_bytes.decode("utf-8", errors="ignore")
                    )

                # Parse error message
                if "ResourceNotFound" in stderr:
                    raise BastionManagerError(
                        f"Bastion host not found: {tunnel.bastion_name} in {tunnel.resource_group}"
                    )

                safe_error = self._sanitize_tunnel_error(stderr)
                raise BastionManagerError(f"Tunnel process failed: {safe_error}")

            # Try to connect to local port
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(1)
                    sock.connect(("127.0.0.1", tunnel.local_port))
                    # Connection successful - tunnel is ready
                    logger.debug(f"Tunnel ready on port {tunnel.local_port}")
                    return
            except (TimeoutError, ConnectionRefusedError, OSError):
                # Not ready yet, wait and retry
                time.sleep(1)
                continue

        raise BastionManagerError(
            f"Tunnel failed to become ready within {timeout} seconds. "
            f"Check Bastion host and VM connectivity."
        )

    def close_tunnel(self, tunnel: BastionTunnel) -> None:
        """Close Bastion tunnel and terminate process.

        Args:
            tunnel: Tunnel to close
        """
        if not tunnel.is_active():
            logger.debug(f"Tunnel on port {tunnel.local_port} already closed")
            # Remove from tracking
            if tunnel in self.active_tunnels:
                self.active_tunnels.remove(tunnel)
            return

        logger.info(f"Closing Bastion tunnel on 127.0.0.1:{tunnel.local_port}")

        try:
            # Terminate process gracefully
            if tunnel.process:
                tunnel.process.terminate()

                # Wait for termination (max 5 seconds)
                try:
                    tunnel.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if terminate doesn't work
                    logger.warning(f"Force killing tunnel process {tunnel.process.pid}")
                    tunnel.process.kill()
                    tunnel.process.wait(timeout=1)

        except Exception as e:
            logger.error(f"Error closing tunnel: {e}")
        finally:
            # Always remove from tracking
            if tunnel in self.active_tunnels:
                self.active_tunnels.remove(tunnel)

    def close_all_tunnels(self) -> None:
        """Close all active tunnels.

        Called automatically on exit via atexit handler.
        """
        if not self.active_tunnels:
            return

        logger.info(f"Closing {len(self.active_tunnels)} active tunnel(s)")

        # Copy list to avoid modification during iteration
        tunnels = list(self.active_tunnels)

        for tunnel in tunnels:
            self.close_tunnel(tunnel)

    def get_tunnel_by_port(self, local_port: int) -> BastionTunnel | None:
        """Find tunnel by local port.

        Args:
            local_port: Local port number

        Returns:
            BastionTunnel or None if not found
        """
        for tunnel in self.active_tunnels:
            if tunnel.local_port == local_port:
                return tunnel
        return None

    def list_active_tunnels(self) -> list[BastionTunnel]:
        """List all active tunnels.

        Returns:
            List of active BastionTunnel objects
        """
        return list(self.active_tunnels)

    def cleanup_inactive_tunnels(self) -> int:
        """Remove inactive tunnels from tracking.

        Returns:
            Number of tunnels removed
        """
        inactive_tunnels = [t for t in self.active_tunnels if not t.is_active()]

        for tunnel in inactive_tunnels:
            self.active_tunnels.remove(tunnel)
            logger.debug(f"Removed inactive tunnel on port {tunnel.local_port}")

        return len(inactive_tunnels)

    def check_tunnel_health(self, tunnel: BastionTunnel) -> bool:
        """Check if tunnel is healthy.

        Args:
            tunnel: Tunnel to check

        Returns:
            True if healthy, False otherwise
        """
        # Check if process is running
        if not tunnel.is_active():
            return False

        # Try to connect to local port
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(2)
                sock.connect(("127.0.0.1", tunnel.local_port))
                return True
        except (TimeoutError, ConnectionRefusedError, OSError):
            return False

    def wait_for_vm_boot(self, wait_seconds: int | None = None) -> None:
        """Wait for newly provisioned VM to finish booting.

        This method provides a configurable wait period for newly provisioned VMs
        to complete their boot process before attempting SSH connections through Bastion.
        This is necessary because Bastion tunnels can be established before the VM's
        SSH service is ready, leading to connection timeouts.

        Args:
            wait_seconds: Number of seconds to wait. If None, uses default (75s)
                         or AZLIN_VM_BOOT_WAIT environment variable.
                         Use 0 to skip the wait entirely.

        Raises:
            ValueError: If wait_seconds is negative
            KeyboardInterrupt: If user interrupts the wait

        Environment Variables:
            AZLIN_VM_BOOT_WAIT: Override default wait time (in seconds)

        Example:
            >>> manager = BastionManager()
            >>> manager.wait_for_vm_boot()  # Wait 75s (default)
            >>> manager.wait_for_vm_boot(wait_seconds=120)  # Wait 120s
            >>> manager.wait_for_vm_boot(wait_seconds=0)  # Skip wait
        """
        # Default wait time (75 seconds)
        default_wait = 75

        # Determine wait time
        if wait_seconds is None:
            # Check environment variable
            env_wait = os.environ.get("AZLIN_VM_BOOT_WAIT")
            if env_wait:
                try:
                    wait_seconds = int(env_wait)
                    logger.debug(f"Using AZLIN_VM_BOOT_WAIT={wait_seconds}s from environment")
                except ValueError:
                    logger.warning(
                        f"Invalid AZLIN_VM_BOOT_WAIT value '{env_wait}', using default {default_wait}s"
                    )
                    wait_seconds = default_wait
            else:
                wait_seconds = default_wait

        # Validate wait_seconds
        if wait_seconds < 0:
            raise ValueError("wait_seconds cannot be negative")

        # Security: Cap maximum wait time to prevent DoS
        max_wait = 3600  # 1 hour maximum
        if wait_seconds > max_wait:
            raise ValueError(
                f"wait_seconds cannot exceed {max_wait}s (1 hour). "
                f"If VM requires longer boot time, consider increasing SSH timeout instead."
            )

        # Warn for unusually long wait times
        if wait_seconds > 300:  # 5 minutes
            logger.warning(
                f"Using unusually long boot wait: {wait_seconds}s. "
                f"Consider verifying VM boot performance."
            )

        # Skip wait if 0
        if wait_seconds == 0:
            logger.debug("Skipping VM boot wait (wait_seconds=0)")
            return

        # Log start of wait
        logger.info(
            f"Waiting {wait_seconds}s for VM to complete boot initialization "
            f"(Bastion tunnel ready, but SSH service may still be starting)"
        )

        try:
            # Wait for the specified duration
            time.sleep(wait_seconds)

            # Log completion
            logger.info(f"VM boot wait complete ({wait_seconds}s elapsed)")

        except KeyboardInterrupt:
            logger.info("VM boot wait interrupted by user")
            raise


__all__ = ["BastionManager", "BastionManagerError", "BastionTunnel"]
