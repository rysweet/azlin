"""VM Connector Module.

This module provides functionality to connect to existing Azure VMs via SSH.
Supports connecting by VM name or direct IP address, with optional tmux sessions.

Security:
- Input validation for VM names and IPs
- Secure SSH key handling
- No shell=True for subprocess
- Sanitized logging
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from azlin.config_manager import ConfigError, ConfigManager
from azlin.modules.ssh_connector import SSHConfig
from azlin.modules.ssh_keys import SSHKeyError, SSHKeyManager
from azlin.modules.ssh_reconnect import SSHReconnectHandler
from azlin.terminal_launcher import TerminalConfig, TerminalLauncher, TerminalLauncherError
from azlin.vm_manager import VMManager, VMManagerError

logger = logging.getLogger(__name__)


class VMConnectorError(Exception):
    """Raised when VM connection operations fail."""

    pass


@dataclass
class ConnectionInfo:
    """VM connection information."""

    vm_name: str
    ip_address: str
    resource_group: str
    ssh_user: str = "azureuser"
    ssh_key_path: Optional[Path] = None


class VMConnector:
    """Connect to existing Azure VMs via SSH.

    This class provides operations for:
    - Connecting to VM by name
    - Connecting to VM by IP address
    - Launching tmux sessions
    - Running remote commands
    """

    @classmethod
    def connect(
        cls,
        vm_identifier: str,
        resource_group: Optional[str] = None,
        use_tmux: bool = True,
        tmux_session: Optional[str] = None,
        remote_command: Optional[str] = None,
        ssh_user: str = "azureuser",
        ssh_key_path: Optional[Path] = None,
        enable_reconnect: bool = True,
        max_reconnect_retries: int = 3,
    ) -> bool:
        """Connect to a VM via SSH.

        Args:
            vm_identifier: VM name or IP address
            resource_group: Resource group (required for VM name, optional for IP)
            use_tmux: Launch tmux session (default: True)
            tmux_session: Tmux session name (default: vm_identifier)
            remote_command: Command to run on VM (optional)
            ssh_user: SSH username (default: azureuser)
            ssh_key_path: Path to SSH private key (default: ~/.ssh/azlin_key)
            enable_reconnect: Enable auto-reconnect on disconnect (default: True)
            max_reconnect_retries: Maximum reconnection attempts (default: 3)

        Returns:
            True if connection successful

        Raises:
            VMConnectorError: If connection fails

        Example:
            >>> # Connect by VM name
            >>> VMConnector.connect("my-vm", resource_group="my-rg")

            >>> # Connect by IP
            >>> VMConnector.connect("20.1.2.3")

            >>> # Connect without tmux
            >>> VMConnector.connect("my-vm", resource_group="my-rg", use_tmux=False)

            >>> # Run command
            >>> VMConnector.connect("my-vm", resource_group="my-rg", remote_command="ls -la")

            >>> # Disable auto-reconnect
            >>> VMConnector.connect("my-vm", resource_group="my-rg", enable_reconnect=False)
        """
        # Get connection info
        conn_info = cls._resolve_connection_info(
            vm_identifier, resource_group, ssh_user, ssh_key_path
        )

        # Ensure SSH key exists
        try:
            ssh_keys = SSHKeyManager.ensure_key_exists(conn_info.ssh_key_path)
            conn_info.ssh_key_path = ssh_keys.private_path
        except SSHKeyError as e:
            raise VMConnectorError(f"SSH key error: {e}")

        # If reconnect is enabled and no remote command, use direct SSH with reconnect
        # Otherwise use terminal launcher (which opens new windows)
        if enable_reconnect and remote_command is None:
            # Use direct SSH connection with reconnect support
            ssh_config = SSHConfig(
                host=conn_info.ip_address,
                user=conn_info.ssh_user,
                key_path=conn_info.ssh_key_path,
                port=22,
                strict_host_key_checking=False,
            )

            try:
                logger.info(f"Connecting to {conn_info.vm_name} ({conn_info.ip_address})...")
                handler = SSHReconnectHandler(max_retries=max_reconnect_retries)
                exit_code = handler.connect_with_reconnect(
                    config=ssh_config,
                    vm_name=conn_info.vm_name,
                    tmux_session=tmux_session or conn_info.vm_name if use_tmux else "azlin",
                    auto_tmux=use_tmux,
                )
                return exit_code == 0
            except Exception as e:
                raise VMConnectorError(f"SSH connection failed: {e}")
        else:
            # Build terminal config for new window or remote command
            terminal_config = TerminalConfig(
                ssh_host=conn_info.ip_address,
                ssh_user=conn_info.ssh_user,
                ssh_key_path=conn_info.ssh_key_path,
                command=remote_command,
                title=f"azlin - {conn_info.vm_name}",
                tmux_session=tmux_session or conn_info.vm_name if use_tmux else None,
            )

            # Launch terminal
            try:
                logger.info(f"Connecting to {conn_info.vm_name} ({conn_info.ip_address})...")
                return TerminalLauncher.launch(terminal_config)
            except TerminalLauncherError as e:
                raise VMConnectorError(f"Failed to launch terminal: {e}")

    @classmethod
    def connect_by_name(
        cls,
        vm_name: str,
        resource_group: Optional[str] = None,
        use_tmux: bool = True,
        tmux_session: Optional[str] = None,
        remote_command: Optional[str] = None,
        ssh_user: str = "azureuser",
        ssh_key_path: Optional[Path] = None,
    ) -> bool:
        """Connect to a VM by name.

        Args:
            vm_name: VM name
            resource_group: Resource group (uses config default if not specified)
            use_tmux: Launch tmux session (default: True)
            tmux_session: Tmux session name (default: vm_name)
            remote_command: Command to run on VM (optional)
            ssh_user: SSH username (default: azureuser)
            ssh_key_path: Path to SSH private key (default: ~/.ssh/azlin_key)

        Returns:
            True if connection successful

        Raises:
            VMConnectorError: If VM not found or connection fails
        """
        return cls.connect(
            vm_identifier=vm_name,
            resource_group=resource_group,
            use_tmux=use_tmux,
            tmux_session=tmux_session,
            remote_command=remote_command,
            ssh_user=ssh_user,
            ssh_key_path=ssh_key_path,
        )

    @classmethod
    def connect_by_ip(
        cls,
        ip_address: str,
        use_tmux: bool = True,
        tmux_session: Optional[str] = None,
        remote_command: Optional[str] = None,
        ssh_user: str = "azureuser",
        ssh_key_path: Optional[Path] = None,
    ) -> bool:
        """Connect to a VM by IP address.

        Args:
            ip_address: VM public IP address
            use_tmux: Launch tmux session (default: True)
            tmux_session: Tmux session name (default: IP address)
            remote_command: Command to run on VM (optional)
            ssh_user: SSH username (default: azureuser)
            ssh_key_path: Path to SSH private key (default: ~/.ssh/azlin_key)

        Returns:
            True if connection successful

        Raises:
            VMConnectorError: If connection fails
        """
        # Validate IP address
        if not cls._is_valid_ip(ip_address):
            raise VMConnectorError(f"Invalid IP address: {ip_address}")

        return cls.connect(
            vm_identifier=ip_address,
            resource_group=None,
            use_tmux=use_tmux,
            tmux_session=tmux_session or ip_address,
            remote_command=remote_command,
            ssh_user=ssh_user,
            ssh_key_path=ssh_key_path,
        )

    @classmethod
    def _resolve_connection_info(
        cls,
        vm_identifier: str,
        resource_group: Optional[str],
        ssh_user: str,
        ssh_key_path: Optional[Path],
    ) -> ConnectionInfo:
        """Resolve VM connection information.

        Args:
            vm_identifier: VM name or IP address
            resource_group: Resource group (optional)
            ssh_user: SSH username
            ssh_key_path: SSH private key path

        Returns:
            ConnectionInfo object

        Raises:
            VMConnectorError: If VM not found or info cannot be resolved
        """
        # Check if identifier is an IP address
        if cls._is_valid_ip(vm_identifier):
            return ConnectionInfo(
                vm_name=vm_identifier,
                ip_address=vm_identifier,
                resource_group=resource_group or "unknown",
                ssh_user=ssh_user,
                ssh_key_path=ssh_key_path,
            )

        # Otherwise, treat as VM name - need to resolve IP
        vm_name = vm_identifier

        # Get resource group
        if not resource_group:
            try:
                config = ConfigManager.load_config()
                resource_group = config.default_resource_group
                if not resource_group:
                    raise VMConnectorError(
                        "Resource group required. Set default with:\n"
                        "  azlin config set default_resource_group <name>\n"
                        "Or specify with --resource-group option."
                    )
            except ConfigError as e:
                raise VMConnectorError(f"Config error: {e}")

        # Query VM details
        try:
            vm_info = VMManager.get_vm(vm_name, resource_group)
            if not vm_info:
                raise VMConnectorError(
                    f"VM not found: {vm_name} in resource group {resource_group}"
                )

            # Check if VM is running
            if not vm_info.is_running():
                logger.warning(
                    f"VM is not running (state: {vm_info.power_state}). " "Connection may fail."
                )

            # Get IP address
            if not vm_info.public_ip:
                raise VMConnectorError(
                    f"VM {vm_name} has no public IP address. "
                    "Ensure VM has a public IP configured."
                )

            return ConnectionInfo(
                vm_name=vm_name,
                ip_address=vm_info.public_ip,
                resource_group=resource_group,
                ssh_user=ssh_user,
                ssh_key_path=ssh_key_path,
            )

        except VMManagerError as e:
            raise VMConnectorError(f"Failed to get VM info: {e}")

    @classmethod
    def _is_valid_ip(cls, identifier: str) -> bool:
        """Check if string is a valid IP address.

        Args:
            identifier: String to check

        Returns:
            True if valid IPv4 address

        Example:
            >>> VMConnector._is_valid_ip("192.168.1.1")
            True
            >>> VMConnector._is_valid_ip("my-vm-name")
            False
        """
        # Simple IPv4 pattern
        ip_pattern = r"^(\d{1,3}\.){3}\d{1,3}$"
        if not re.match(ip_pattern, identifier):
            return False

        # Validate octets
        octets = identifier.split(".")
        for octet in octets:
            try:
                value = int(octet)
                if value < 0 or value > 255:
                    return False
            except ValueError:
                return False

        return True


__all__ = ["VMConnector", "VMConnectorError", "ConnectionInfo"]
