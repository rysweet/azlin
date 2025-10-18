"""VM Log Viewer Module.

This module provides functionality to view logs from Azure VMs without requiring
direct SSH connection. Uses SSH-based command execution to retrieve logs via journalctl.

Features:
- System logs (journalctl)
- Boot logs (journalctl -b)
- Kernel logs (journalctl -k)
- Application logs (journalctl -u <service>)
- Real-time log following (journalctl -f)
- Time-based filtering (--since)
- Line limiting

Security:
- Input validation for VM names and parameters
- Secure SSH key handling
- Command sanitization via RemoteExecutor
- Timeout enforcement
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from azlin.modules.ssh_connector import SSHConfig, SSHConnector
from azlin.modules.ssh_keys import SSHKeyError, SSHKeyManager
from azlin.remote_exec import RemoteExecError, RemoteExecutor
from azlin.vm_manager import VMInfo, VMManager, VMManagerError

logger = logging.getLogger(__name__)


class LogViewerError(Exception):
    """Raised when log viewing operations fail."""

    pass


class LogType(Enum):
    """Types of logs that can be retrieved."""

    SYSTEM = "system"
    BOOT = "boot"
    APP = "app"
    KERNEL = "kernel"


@dataclass
class LogResult:
    """Result from log retrieval operation."""

    success: bool
    logs: str
    vm_name: str
    log_type: LogType
    line_count: int = 0
    error_message: str | None = None

    def __post_init__(self):
        """Calculate line count if not provided."""
        if self.line_count == 0 and self.logs:
            self.line_count = len(self.logs.splitlines())


class LogViewer:
    """View logs from Azure VMs via SSH.

    This class provides methods to retrieve different types of logs
    from running Azure VMs using SSH-based command execution.
    """

    # Valid time format patterns for validation
    TIME_PATTERNS: ClassVar[list[str]] = [
        r"^\d+ (second|minute|hour|day|week|month|year)s? ago$",
        r"^\d{4}-\d{2}-\d{2}$",
        r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$",
        r"^(yesterday|today|now)$",
    ]

    @classmethod
    def get_system_logs(
        cls,
        vm_name: str,
        resource_group: str,
        lines: int = 100,
        since: str | None = None,
        timeout: int = 30,
    ) -> LogResult:
        """Retrieve system logs from VM via journalctl.

        Args:
            vm_name: Name of the VM
            resource_group: Resource group containing the VM
            lines: Number of lines to retrieve (default: 100)
            since: Time filter (e.g., "1 hour ago", "2024-01-01")
            timeout: SSH timeout in seconds

        Returns:
            LogResult object with logs

        Raises:
            LogViewerError: If log retrieval fails
        """
        logger.debug(f"Retrieving system logs from {vm_name}")

        # Validate and get VM
        _vm, ssh_config = cls._prepare_connection(vm_name, resource_group)

        # Build journalctl command
        command = cls._build_journalctl_command(
            log_type=LogType.SYSTEM, lines=lines, since=since, service=None
        )

        # Execute command
        return cls._execute_log_command(
            ssh_config=ssh_config,
            command=command,
            vm_name=vm_name,
            log_type=LogType.SYSTEM,
            timeout=timeout,
        )

    @classmethod
    def get_boot_logs(
        cls,
        vm_name: str,
        resource_group: str,
        lines: int = 100,
        since: str | None = None,
        timeout: int = 30,
    ) -> LogResult:
        """Retrieve boot logs from VM via journalctl -b.

        Args:
            vm_name: Name of the VM
            resource_group: Resource group containing the VM
            lines: Number of lines to retrieve (default: 100)
            since: Time filter (e.g., "1 hour ago", "2024-01-01")
            timeout: SSH timeout in seconds

        Returns:
            LogResult object with logs

        Raises:
            LogViewerError: If log retrieval fails
        """
        logger.debug(f"Retrieving boot logs from {vm_name}")

        # Validate and get VM
        _vm, ssh_config = cls._prepare_connection(vm_name, resource_group)

        # Build journalctl command with boot flag
        command = cls._build_journalctl_command(
            log_type=LogType.BOOT, lines=lines, since=since, service=None
        )

        # Execute command
        return cls._execute_log_command(
            ssh_config=ssh_config,
            command=command,
            vm_name=vm_name,
            log_type=LogType.BOOT,
            timeout=timeout,
        )

    @classmethod
    def get_kernel_logs(
        cls,
        vm_name: str,
        resource_group: str,
        lines: int = 100,
        since: str | None = None,
        timeout: int = 30,
    ) -> LogResult:
        """Retrieve kernel logs from VM via journalctl -k.

        Args:
            vm_name: Name of the VM
            resource_group: Resource group containing the VM
            lines: Number of lines to retrieve (default: 100)
            since: Time filter (e.g., "1 hour ago", "2024-01-01")
            timeout: SSH timeout in seconds

        Returns:
            LogResult object with logs

        Raises:
            LogViewerError: If log retrieval fails
        """
        logger.debug(f"Retrieving kernel logs from {vm_name}")

        # Validate and get VM
        _vm, ssh_config = cls._prepare_connection(vm_name, resource_group)

        # Build journalctl command with kernel flag
        command = cls._build_journalctl_command(
            log_type=LogType.KERNEL, lines=lines, since=since, service=None
        )

        # Execute command
        return cls._execute_log_command(
            ssh_config=ssh_config,
            command=command,
            vm_name=vm_name,
            log_type=LogType.KERNEL,
            timeout=timeout,
        )

    @classmethod
    def get_app_logs(
        cls,
        vm_name: str,
        resource_group: str,
        service: str,
        lines: int = 100,
        since: str | None = None,
        timeout: int = 30,
    ) -> LogResult:
        """Retrieve application logs for a specific service.

        Args:
            vm_name: Name of the VM
            resource_group: Resource group containing the VM
            service: Service name (e.g., "nginx", "docker")
            lines: Number of lines to retrieve (default: 100)
            since: Time filter (e.g., "1 hour ago", "2024-01-01")
            timeout: SSH timeout in seconds

        Returns:
            LogResult object with logs

        Raises:
            LogViewerError: If log retrieval fails
        """
        logger.debug(f"Retrieving app logs for {service} from {vm_name}")

        # Validate and get VM
        _vm, ssh_config = cls._prepare_connection(vm_name, resource_group)

        # Build journalctl command with service filter
        command = cls._build_journalctl_command(
            log_type=LogType.APP, lines=lines, since=since, service=service
        )

        # Execute command
        return cls._execute_log_command(
            ssh_config=ssh_config,
            command=command,
            vm_name=vm_name,
            log_type=LogType.APP,
            timeout=timeout,
        )

    @classmethod
    def follow_logs(
        cls,
        vm_name: str,
        resource_group: str,
        log_type: LogType = LogType.SYSTEM,
        since: str | None = None,
        service: str | None = None,
    ) -> int:
        """Follow logs in real-time (like tail -f).

        Args:
            vm_name: Name of the VM
            resource_group: Resource group containing the VM
            log_type: Type of logs to follow
            since: Time filter (e.g., "1 hour ago")
            service: Service name (required for APP log type)

        Returns:
            Exit code from SSH connection

        Raises:
            LogViewerError: If connection setup fails
        """
        logger.debug(f"Following {log_type.value} logs from {vm_name}")

        # Validate and get VM
        _vm, ssh_config = cls._prepare_connection(vm_name, resource_group)

        # Build follow command
        command = cls._build_follow_command(log_type, since, service)

        # Connect with interactive SSH to stream logs
        return SSHConnector.connect(
            ssh_config=ssh_config, remote_command=command, tmux_session=None, auto_tmux=False
        )

    @classmethod
    def _prepare_connection(cls, vm_name: str, resource_group: str) -> tuple[VMInfo, SSHConfig]:
        """Prepare VM connection for log retrieval.

        Args:
            vm_name: Name of the VM
            resource_group: Resource group containing the VM

        Returns:
            Tuple of (VMInfo, SSHConfig)

        Raises:
            LogViewerError: If VM validation fails
        """
        try:
            # Get VM info
            vm = VMManager.get_vm(vm_name, resource_group)

            if not vm:
                raise LogViewerError(
                    f"VM '{vm_name}' not found in resource group '{resource_group}'"
                )

            # Check if VM is running
            if not vm.is_running():
                raise LogViewerError(f"VM '{vm_name}' is not running (status: {vm.power_state})")

            # Check if VM has public IP
            if not vm.public_ip:
                raise LogViewerError(f"VM '{vm_name}' has no public IP address")

            # Get SSH key
            ssh_key_pair = SSHKeyManager.ensure_key_exists()

            # Create SSH config
            ssh_config = SSHConfig(
                host=vm.public_ip, user="azureuser", key_path=ssh_key_pair.private_path
            )

            return vm, ssh_config

        except VMManagerError as e:
            raise LogViewerError(f"Failed to get VM info: {e}") from e
        except SSHKeyError as e:
            raise LogViewerError(f"Failed to get SSH key: {e}") from e

    @classmethod
    def _execute_log_command(
        cls, ssh_config: SSHConfig, command: str, vm_name: str, log_type: LogType, timeout: int = 30
    ) -> LogResult:
        """Execute log retrieval command via SSH.

        Args:
            ssh_config: SSH configuration
            command: Command to execute
            vm_name: VM name for result
            log_type: Type of log being retrieved
            timeout: SSH timeout in seconds

        Returns:
            LogResult object

        Raises:
            LogViewerError: If command execution fails
        """
        try:
            # Execute command via SSH
            result = RemoteExecutor.execute_command(
                ssh_config=ssh_config, command=command, timeout=timeout
            )

            if not result.success:
                raise LogViewerError(f"Failed to retrieve logs: {result.stderr or 'Unknown error'}")

            return LogResult(success=True, logs=result.stdout, vm_name=vm_name, log_type=log_type)

        except RemoteExecError as e:
            raise LogViewerError(f"SSH command failed: {e}") from e

    @classmethod
    def _build_journalctl_command(
        cls,
        log_type: LogType,
        lines: int = 100,
        since: str | None = None,
        service: str | None = None,
    ) -> str:
        """Build journalctl command based on parameters.

        Args:
            log_type: Type of logs to retrieve
            lines: Number of lines to retrieve
            since: Time filter
            service: Service name (for APP logs)

        Returns:
            journalctl command string

        Raises:
            LogViewerError: If invalid parameters
        """
        parts = ["journalctl", "--no-pager"]

        # Add type-specific flags
        if log_type == LogType.BOOT:
            parts.append("-b")  # Boot logs
        elif log_type == LogType.KERNEL:
            parts.append("-k")  # Kernel logs
        elif log_type == LogType.APP:
            if not service:
                raise LogViewerError("Service name required for application logs")
            parts.append(f"-u {service}")

        # Add line limit (not for follow mode)
        if lines > 0:
            parts.append(f"-n {lines}")

        # Add time filter
        if since:
            validated_since = cls._validate_time_string(since)
            parts.append(f"--since '{validated_since}'")

        return " ".join(parts)

    @classmethod
    def _build_follow_command(
        cls, log_type: LogType, since: str | None = None, service: str | None = None
    ) -> str:
        """Build journalctl follow command.

        Args:
            log_type: Type of logs to follow
            since: Time filter
            service: Service name (for APP logs)

        Returns:
            journalctl follow command string
        """
        parts = ["journalctl", "-f", "--no-pager"]

        # Add type-specific flags
        if log_type == LogType.BOOT:
            parts.append("-b")
        elif log_type == LogType.KERNEL:
            parts.append("-k")
        elif log_type == LogType.APP and service:
            parts.append(f"-u {service}")

        # Add time filter
        if since:
            validated_since = cls._validate_time_string(since)
            parts.append(f"--since '{validated_since}'")

        return " ".join(parts)

    @classmethod
    def _validate_time_string(cls, time_str: str) -> str:
        """Validate time string format.

        Args:
            time_str: Time string to validate

        Returns:
            Validated time string

        Raises:
            LogViewerError: If time format is invalid
        """
        if not time_str:
            return time_str

        # Reject obviously invalid formats first
        if any(char in time_str for char in [";", "&", "|", "`", "$", "(", ")"]):
            raise LogViewerError(
                f"Invalid time format: {time_str}. "
                "Examples: '1 hour ago', '2024-01-01', 'yesterday'"
            )

        # Check against known patterns
        for pattern in cls.TIME_PATTERNS:
            if re.match(pattern, time_str, re.IGNORECASE):
                return time_str

        # If no pattern matches, raise error
        raise LogViewerError(
            f"Invalid time format: {time_str}. "
            "Examples: '1 hour ago', '30 minutes ago', '2024-01-01', 'yesterday'"
        )


__all__ = ["LogResult", "LogType", "LogViewer", "LogViewerError"]
