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

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from azlin.config_manager import ConfigError, ConfigManager
from azlin.connection_tracker import ConnectionTracker
from azlin.modules.bastion_detector import BastionInfo
from azlin.modules.bastion_manager import BastionManager, BastionTunnel
from azlin.modules.bastion_tunnel import (
    check_bastion_routing,
    create_bastion_tunnel,
)
from azlin.modules.connection_sanitizer import is_valid_ip, sanitize_for_logging
from azlin.modules.ssh_connector import SSHConfig, SSHConnector
from azlin.modules.ssh_key_fetch import auto_sync_key_to_vm, try_fetch_key_from_vault
from azlin.modules.ssh_keys import SSHKeyError, SSHKeyManager
from azlin.modules.ssh_reconnect import SSHReconnectHandler
from azlin.terminal_launcher import TerminalConfig, TerminalLauncher, TerminalLauncherError
from azlin.vm_manager import VMManager, VMManagerError

logger = logging.getLogger(__name__)


class VMConnectorError(Exception):
    """Raised when VM connection operations fail."""

    pass


def _ensure_tmux_socket_dir(
    host: str,
    port: int,
    user: str,
    key_path: Path | None,
) -> None:
    """Ensure tmux socket directory exists on VM via SSH.

    Ubuntu 25.10+ changed /tmp permissions, preventing tmux from creating
    /tmp/tmux-1000. This runs a quick idempotent fix over the existing SSH
    connection (or Bastion tunnel). Only creates the dir if it doesn't exist.
    """
    if not key_path:
        return

    script = (
        "[ -d /tmp/tmux-1000 ] && exit 0; "
        "sudo chmod 1777 /tmp && "
        "mkdir -p /tmp/tmux-1000 && "
        "chmod 700 /tmp/tmux-1000"
    )

    try:
        result = subprocess.run(
            [
                "ssh",
                "-i",
                str(key_path),
                "-p",
                str(port),
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "ConnectTimeout=5",
                "-o",
                "BatchMode=yes",
                f"{user}@{host}",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            logger.debug("tmux socket directory verified")
        else:
            logger.debug(f"tmux socket dir fix returned {result.returncode}: {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        logger.debug("tmux socket dir check timed out (non-fatal)")
    except Exception as e:
        logger.debug(f"tmux socket dir check failed (non-fatal): {e}")


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
            logger.warning(f"Failed to record connection for {sanitize_for_logging(vm_name)}: {e}")

    @staticmethod
    def is_valid_ip(identifier: str) -> bool:
        """Check if string is a valid IPv4 or IPv6 address."""
        return is_valid_ip(identifier)

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

        """
        # Get connection info
        conn_info = cls._resolve_connection_info(
            vm_identifier, resource_group, ssh_user, ssh_key_path
        )

        # Try to fetch SSH key from Key Vault
        vault_fetched = False
        if conn_info.ssh_key_path:
            vault_fetched = try_fetch_key_from_vault(
                vm_name=conn_info.vm_name,
                key_path=conn_info.ssh_key_path,
                resource_group=conn_info.resource_group,
            )

        # Auto-sync SSH key to VM if enabled and key was fetched from vault
        if vault_fetched:
            auto_sync_key_to_vm(
                conn_info_vm_name=conn_info.vm_name,
                conn_info_resource_group=conn_info.resource_group,
                conn_info_ssh_key_path=conn_info.ssh_key_path,
            )

        # Ensure SSH key exists (handles validation, permissions, and generation)
        key_existed_before = conn_info.ssh_key_path and conn_info.ssh_key_path.exists()
        try:
            ssh_keys = SSHKeyManager.ensure_key_exists(conn_info.ssh_key_path)
        except SSHKeyError as e:
            raise VMConnectorError(f"SSH key error: {e}") from e

        # Provide clear feedback about key source
        if vault_fetched:
            logger.info("Using SSH key retrieved from Key Vault")
        elif key_existed_before:
            logger.info("Using existing local SSH key")
        else:
            logger.info(f"Generated new SSH key for VM: {sanitize_for_logging(conn_info.vm_name)}")

        conn_info.ssh_key_path = ssh_keys.private_path

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
                bastion_info = check_bastion_routing(
                    conn_info.vm_name,
                    conn_info.resource_group,
                    use_bastion,
                    conn_info.location,
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

                bastion_manager, bastion_tunnel = create_bastion_tunnel(
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

            # Ensure tmux socket directory exists (Ubuntu 25.10+ fix)
            if use_tmux and remote_command is None:
                _ensure_tmux_socket_dir(
                    host=conn_info.ip_address,
                    port=ssh_port,
                    user=conn_info.ssh_user,
                    key_path=conn_info.ssh_key_path,
                )

            # Route connection based on mode
            return cls._execute_connection(
                conn_info=conn_info,
                original_ip=original_ip,
                ssh_port=ssh_port,
                use_tmux=use_tmux,
                tmux_session=tmux_session,
                remote_command=remote_command,
                enable_reconnect=enable_reconnect,
                max_reconnect_retries=max_reconnect_retries,
                bastion_manager=bastion_manager,
                bastion_tunnel=bastion_tunnel,
            )

        finally:
            # Cleanup Bastion tunnel if it was created
            if bastion_tunnel is not None and bastion_manager is not None:
                try:
                    bastion_manager.close_tunnel(bastion_tunnel)
                    logger.debug(f"Closed Bastion tunnel on port {bastion_tunnel.local_port}")
                except Exception as e:
                    logger.warning(
                        f"Failed to close Bastion tunnel: {e}. "
                        f"Tunnel will be cleaned up on process exit."
                    )

    @classmethod
    def _execute_connection(
        cls,
        conn_info: ConnectionInfo,
        original_ip: str,
        ssh_port: int,
        use_tmux: bool,
        tmux_session: str | None,
        remote_command: str | None,
        enable_reconnect: bool,
        max_reconnect_retries: int,
        bastion_manager: BastionManager | None,
        bastion_tunnel: BastionTunnel | None,
    ) -> bool:
        """Execute the SSH connection in the appropriate mode.

        Routes to: remote command, reconnect handler, or terminal launcher.
        """
        if remote_command is not None:
            return cls._connect_remote_command(conn_info, original_ip, ssh_port, remote_command)
        if enable_reconnect:
            return cls._connect_with_reconnect(
                conn_info,
                original_ip,
                ssh_port,
                use_tmux,
                tmux_session,
                max_reconnect_retries,
                bastion_manager,
                bastion_tunnel,
            )
        return cls._connect_terminal(conn_info, original_ip, ssh_port, use_tmux, tmux_session)

    @classmethod
    def _connect_remote_command(
        cls,
        conn_info: ConnectionInfo,
        original_ip: str,
        ssh_port: int,
        remote_command: str,
    ) -> bool:
        """Execute a remote command via SSH."""
        assert conn_info.ssh_key_path is not None  # Set by connect() before calling
        ssh_config = SSHConfig(
            host=conn_info.ip_address,
            user=conn_info.ssh_user,
            key_path=conn_info.ssh_key_path,
            port=ssh_port,
            strict_host_key_checking=False,
        )
        try:
            logger.info(
                f"Executing command on {sanitize_for_logging(conn_info.vm_name)} ({original_ip})..."
            )
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

    @classmethod
    def _connect_with_reconnect(
        cls,
        conn_info: ConnectionInfo,
        original_ip: str,
        ssh_port: int,
        use_tmux: bool,
        tmux_session: str | None,
        max_reconnect_retries: int,
        bastion_manager,
        bastion_tunnel,
    ) -> bool:
        """Connect via SSH with auto-reconnect support."""
        assert conn_info.ssh_key_path is not None  # Set by connect() before calling
        ssh_config = SSHConfig(
            host=conn_info.ip_address,
            user=conn_info.ssh_user,
            key_path=conn_info.ssh_key_path,
            port=ssh_port,
            strict_host_key_checking=False,
        )
        try:
            logger.info(
                f"Connecting to {sanitize_for_logging(conn_info.vm_name)} ({original_ip})..."
            )
            # Create cleanup callback for Bastion tunnel
            cleanup_callback = None
            if bastion_manager is not None and bastion_tunnel is not None:

                def cleanup_bastion_tunnel():
                    bastion_manager.close_tunnel(bastion_tunnel)

                cleanup_callback = cleanup_bastion_tunnel

            handler = SSHReconnectHandler(
                max_retries=max_reconnect_retries, cleanup_callback=cleanup_callback
            )
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

    @classmethod
    def _connect_terminal(
        cls,
        conn_info: ConnectionInfo,
        original_ip: str,
        ssh_port: int,
        use_tmux: bool,
        tmux_session: str | None,
    ) -> bool:
        """Connect via terminal launcher (no reconnect)."""
        assert conn_info.ssh_key_path is not None  # Set by connect() before calling
        terminal_config = TerminalConfig(
            ssh_host=conn_info.ip_address,
            ssh_user=conn_info.ssh_user,
            ssh_key_path=conn_info.ssh_key_path,
            ssh_port=ssh_port,
            title=f"azlin - {conn_info.vm_name}",
            tmux_session=tmux_session or conn_info.vm_name if use_tmux else None,
        )
        try:
            logger.info(
                f"Connecting to {sanitize_for_logging(conn_info.vm_name)} ({original_ip})..."
            )
            success = TerminalLauncher.launch(terminal_config)
            if success:
                cls._record_connection(conn_info.vm_name)
            return success
        except TerminalLauncherError as e:
            raise VMConnectorError(f"Failed to launch terminal: {e}") from e

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
        """Connect to a VM by name. Delegates to connect()."""
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
        """Connect to a VM by IP address. Delegates to connect()."""
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
        """Resolve VM identifier (name or IP) to ConnectionInfo."""
        if cls.is_valid_ip(vm_identifier):
            return ConnectionInfo(
                vm_name=vm_identifier,
                ip_address=vm_identifier,
                resource_group=resource_group or "unknown",
                ssh_user=ssh_user,
                ssh_key_path=ssh_key_path,
            )

        vm_name = vm_identifier

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

        try:
            vm_info = VMManager.get_vm(vm_name, resource_group)
            if not vm_info:
                raise VMConnectorError(
                    f"VM not found: {vm_name} in resource group {resource_group}"
                )

            if not vm_info.is_running():
                logger.warning(
                    f"VM is not running (state: {vm_info.power_state}). Connection may fail."
                )

            ip_address = vm_info.public_ip or vm_info.private_ip
            if not ip_address:
                raise VMConnectorError(f"VM {vm_name} has neither public nor private IP address.")

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
                location=vm_info.location,
            )

        except VMManagerError as e:
            raise VMConnectorError(f"Failed to get VM info: {e}") from e


__all__ = ["ConnectionInfo", "VMConnector", "VMConnectorError"]
