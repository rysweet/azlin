"""VM Connector Module.

This module provides functionality to connect to existing Azure VMs via SSH.
Supports connecting by VM name or direct IP address, with optional tmux sessions.
Integrates with Azure Bastion for private-only VMs.

Security:
- Input validation for VM names and IPs
- Secure SSH key handling
- No shell=True for subprocess
- Sanitized logging
- Bastion tunnels bound to localhost only
"""

import ipaddress
import logging
from dataclasses import dataclass
from pathlib import Path

import click

from azlin.config_manager import ConfigError, ConfigManager
from azlin.connection_tracker import ConnectionTracker
from azlin.modules.bastion_config import BastionConfig
from azlin.modules.bastion_detector import BastionDetector, BastionInfo
from azlin.modules.bastion_manager import BastionManager, BastionManagerError
from azlin.modules.ssh_connector import SSHConfig, SSHConnector
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
    ssh_key_path: Path | None = None
    location: str | None = None  # VM region for Bastion matching


class VMConnector:
    """Connect to existing Azure VMs via SSH.

    This class provides operations for:
    - Connecting to VM by name
    - Connecting to VM by IP address
    - Launching tmux sessions
    - Running remote commands
    """

    @staticmethod
    def _record_connection(vm_name: str) -> None:
        """Record successful VM connection, suppressing errors."""
        try:
            ConnectionTracker.record_connection(vm_name)
        except Exception as e:
            logger.warning(f"Failed to record connection for {vm_name}: {e}")

    @classmethod
    def connect(
        cls,
        vm_identifier: str,
        resource_group: str | None = None,
        use_tmux: bool = True,
        tmux_session: str | None = None,
        remote_command: str | None = None,
        ssh_user: str = "azureuser",
        ssh_key_path: Path | None = None,
        enable_reconnect: bool = True,
        max_reconnect_retries: int = 3,
        use_bastion: bool = False,
        bastion_name: str | None = None,
        bastion_resource_group: str | None = None,
        skip_prompts: bool = False,
    ) -> bool:
        """Connect to a VM via SSH (with optional Bastion routing).

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
            use_bastion: Force use of Bastion tunnel (default: False)
            bastion_name: Bastion host name (optional, auto-detected if not provided)
            bastion_resource_group: Bastion resource group (optional)
            skip_prompts: Skip all confirmation prompts (default: False)

        Returns:
            True if connection successful

        Raises:
            VMConnectorError: If connection fails

        Example:
            >>> # Connect by VM name
            >>> VMConnector.connect("my-vm", resource_group="my-rg")

            >>> # Force Bastion connection
            >>> VMConnector.connect("my-vm", resource_group="my-rg", use_bastion=True)

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
            raise VMConnectorError(f"SSH key error: {e}") from e

        # Bastion routing logic
        bastion_tunnel = None
        bastion_manager = None
        original_ip = conn_info.ip_address
        ssh_port = 22

        try:
            # Check if we should use Bastion
            should_use_bastion = use_bastion
            bastion_info = None

            if not should_use_bastion and not cls.is_valid_ip(vm_identifier):
                # Auto-detect Bastion if not connecting by IP
                bastion_info = cls._check_bastion_routing(
                    conn_info.vm_name,
                    conn_info.resource_group,
                    use_bastion,
                    conn_info.location,  # Pass VM location for region filtering
                    skip_prompts,
                )
                should_use_bastion = bastion_info is not None

            # If using Bastion, create tunnel
            if should_use_bastion:
                if not bastion_info:
                    if not bastion_name:
                        raise VMConnectorError(
                            "Bastion name required when using --use-bastion flag"
                        )
                    bastion_info = BastionInfo(
                        name=bastion_name,
                        resource_group=bastion_resource_group or resource_group or "",
                        location=None,
                    )

                bastion_manager, bastion_tunnel = cls._create_bastion_tunnel(
                    vm_name=conn_info.vm_name,
                    resource_group=conn_info.resource_group,
                    bastion_name=bastion_info["name"],
                    bastion_resource_group=bastion_info["resource_group"],
                )

                # Update connection info to use tunnel
                conn_info.ip_address = "127.0.0.1"
                ssh_port = bastion_tunnel.local_port

                logger.info(
                    f"Connecting through Bastion tunnel: {bastion_info['name']} "
                    f"(127.0.0.1:{ssh_port})"
                )

            # Route connection: remote command -> SSHConnector, interactive+reconnect -> SSHReconnectHandler, interactive -> TerminalLauncher
            if remote_command is not None:
                ssh_config = SSHConfig(
                    host=conn_info.ip_address,
                    user=conn_info.ssh_user,
                    key_path=conn_info.ssh_key_path,
                    port=ssh_port,
                    strict_host_key_checking=False,
                )

                try:
                    logger.info(f"Executing command on {conn_info.vm_name} ({original_ip})...")
                    exit_code = SSHConnector.connect(
                        config=ssh_config,
                        remote_command=remote_command,
                        auto_tmux=False,
                    )

                    if exit_code == 0:
                        cls._record_connection(conn_info.vm_name)

                    return exit_code == 0
                except Exception as e:
                    raise VMConnectorError(f"Remote command execution failed: {e}") from e

            elif enable_reconnect:
                ssh_config = SSHConfig(
                    host=conn_info.ip_address,
                    user=conn_info.ssh_user,
                    key_path=conn_info.ssh_key_path,
                    port=ssh_port,
                    strict_host_key_checking=False,
                )

                try:
                    logger.info(f"Connecting to {conn_info.vm_name} ({original_ip})...")
                    handler = SSHReconnectHandler(max_retries=max_reconnect_retries)
                    exit_code = handler.connect_with_reconnect(
                        config=ssh_config,
                        vm_name=conn_info.vm_name,
                        tmux_session=tmux_session or conn_info.vm_name if use_tmux else "azlin",
                        auto_tmux=use_tmux,
                    )

                    if exit_code == 0:
                        cls._record_connection(conn_info.vm_name)

                    return exit_code == 0
                except Exception as e:
                    raise VMConnectorError(f"SSH connection failed: {e}") from e

            else:
                terminal_config = TerminalConfig(
                    ssh_host=conn_info.ip_address,
                    ssh_user=conn_info.ssh_user,
                    ssh_key_path=conn_info.ssh_key_path,
                    ssh_port=ssh_port,
                    title=f"azlin - {conn_info.vm_name}",
                    tmux_session=tmux_session or conn_info.vm_name if use_tmux else None,
                )

                try:
                    logger.info(f"Connecting to {conn_info.vm_name} ({original_ip})...")
                    success = TerminalLauncher.launch(terminal_config)

                    if success:
                        cls._record_connection(conn_info.vm_name)

                    return success
                except TerminalLauncherError as e:
                    raise VMConnectorError(f"Failed to launch terminal: {e}") from e

        finally:
            # Cleanup: Note that bastion_manager handles cleanup via atexit
            # So we don't need to explicitly close tunnels here unless
            # we want immediate cleanup
            pass

    @classmethod
    def connect_by_name(
        cls,
        vm_name: str,
        resource_group: str | None = None,
        use_tmux: bool = True,
        tmux_session: str | None = None,
        remote_command: str | None = None,
        ssh_user: str = "azureuser",
        ssh_key_path: Path | None = None,
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
        tmux_session: str | None = None,
        remote_command: str | None = None,
        ssh_user: str = "azureuser",
        ssh_key_path: Path | None = None,
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
        if not cls.is_valid_ip(ip_address):
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
        resource_group: str | None,
        ssh_user: str,
        ssh_key_path: Path | None,
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
        if cls.is_valid_ip(vm_identifier):
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
                raise VMConnectorError(f"Config error: {e}") from e

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
                    f"VM is not running (state: {vm_info.power_state}). Connection may fail."
                )

            # Get IP address (public or private - Bastion routing will handle both)
            ip_address = vm_info.public_ip or vm_info.private_ip

            if not ip_address:
                raise VMConnectorError(f"VM {vm_name} has neither public nor private IP address.")

            # Log when VM is private-only (helps with debugging bastion connections)
            if not vm_info.public_ip and vm_info.private_ip:
                logger.info(
                    f"VM {vm_name} is private-only (no public IP), will use Bastion if available"
                )

            return ConnectionInfo(
                vm_name=vm_name,
                ip_address=ip_address,
                resource_group=resource_group,
                ssh_user=ssh_user,
                ssh_key_path=ssh_key_path,
                location=vm_info.location,  # Capture VM region for Bastion matching
            )

        except VMManagerError as e:
            raise VMConnectorError(f"Failed to get VM info: {e}") from e

    @classmethod
    def _check_bastion_routing(
        cls,
        vm_name: str,
        resource_group: str,
        force_bastion: bool,
        vm_location: str | None = None,
        skip_prompts: bool = False,
    ) -> BastionInfo | None:
        """Check if Bastion routing should be used for VM.

        Checks configuration and auto-detects Bastion hosts.

        Args:
            vm_name: VM name
            resource_group: Resource group
            force_bastion: Force use of Bastion
            vm_location: VM region for Bastion region filtering (optional)
            skip_prompts: Skip confirmation prompts (default: False)

        Returns:
            BastionInfo with bastion name, resource_group, and location if should use Bastion, None otherwise
        """
        # If forcing Bastion, skip checks
        if force_bastion:
            return None  # Caller will provide bastion_name

        # Load Bastion config
        try:
            config_path = ConfigManager.DEFAULT_CONFIG_DIR / "bastion_config.toml"
            bastion_config = BastionConfig.load(config_path)

            # Check if auto-detection is disabled
            if not bastion_config.auto_detect:
                logger.debug("Bastion auto-detection disabled in config")
                return None

            # Check for explicit mapping
            mapping = bastion_config.get_mapping(vm_name)
            if mapping:
                logger.info(f"Using configured Bastion mapping for {vm_name}")
                return BastionInfo(
                    name=mapping.bastion_name,
                    resource_group=mapping.bastion_resource_group,
                    location=None,
                )

        except Exception as e:
            logger.debug(f"Could not load Bastion config: {e}")

        # Auto-detect Bastion
        try:
            bastion_info: BastionInfo | None = BastionDetector.detect_bastion_for_vm(
                vm_name, resource_group, vm_location
            )

            if bastion_info:
                # Prompt user or auto-accept if skip_prompts (default changed to True for security by default)
                if skip_prompts:
                    logger.info("Skipping prompts, using Bastion (default)")
                    return bastion_info

                try:
                    if click.confirm(
                        f"Found Bastion host '{bastion_info['name']}'. Use it for connection?",
                        default=True,
                    ):
                        return bastion_info
                    logger.info("User declined Bastion connection, using direct connection")
                except click.exceptions.Abort:
                    # Non-interactive mode - use default (True)
                    logger.info("Non-interactive mode, using Bastion (default)")
                    return bastion_info

                logger.info("User declined Bastion connection, using direct connection")

        except Exception as e:
            logger.debug(f"Bastion detection failed: {e}")

        return None

    @classmethod
    def _create_bastion_tunnel(
        cls,
        vm_name: str,
        resource_group: str,
        bastion_name: str,
        bastion_resource_group: str,
    ) -> tuple:
        """Create Bastion tunnel for VM connection.

        Args:
            vm_name: VM name
            resource_group: VM resource group
            bastion_name: Bastion host name
            bastion_resource_group: Bastion resource group

        Returns:
            Tuple of (BastionManager, BastionTunnel)

        Raises:
            VMConnectorError: If tunnel creation fails
        """
        try:
            # Get VM resource ID
            vm_resource_id = VMManager.get_vm_resource_id(vm_name, resource_group)
            if not vm_resource_id:
                raise VMConnectorError(
                    f"Could not determine resource ID for VM: {vm_name}. "
                    f"Ensure Azure CLI is authenticated."
                )

            # Create bastion manager
            bastion_manager = BastionManager()

            # Find available port
            local_port = bastion_manager.get_available_port()

            # Create tunnel
            tunnel = bastion_manager.create_tunnel(
                bastion_name=bastion_name,
                resource_group=bastion_resource_group,
                target_vm_id=vm_resource_id,
                local_port=local_port,
                remote_port=22,
            )

            return (bastion_manager, tunnel)

        except BastionManagerError as e:
            raise VMConnectorError(f"Failed to create Bastion tunnel: {e}") from e
        except Exception as e:
            raise VMConnectorError(f"Unexpected error creating Bastion tunnel: {e}") from e

    @classmethod
    def is_valid_ip(cls, identifier: str) -> bool:
        """Check if string is a valid IP address.

        Uses Python's ipaddress module for proper validation.
        Supports both IPv4 and IPv6 addresses.

        Args:
            identifier: String to check

        Returns:
            True if valid IPv4 or IPv6 address

        Example:
            >>> VMConnector.is_valid_ip("192.168.1.1")
            True
            >>> VMConnector.is_valid_ip("2001:db8::1")
            True
            >>> VMConnector.is_valid_ip("my-vm-name")
            False
            >>> VMConnector.is_valid_ip("256.1.1.1")
            False
        """
        try:
            ipaddress.ip_address(identifier)
            return True
        except ValueError:
            return False


__all__ = ["ConnectionInfo", "VMConnector", "VMConnectorError"]
