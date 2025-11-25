"""Secure session name validation and VM lookup."""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from azlin.modules.bastion_detector import BastionDetector
from azlin.modules.bastion_manager import BastionManager, BastionTunnel
from azlin.vm_manager import VMManager

from .exceptions import InvalidSessionNameError, MultipleSessionsError, SessionNotFoundError

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Constants
DEFAULT_SSH_USER = "azureuser"
DEFAULT_SSH_KEY = str(Path.home() / ".ssh" / "azlin_key")

# CRITICAL: This pattern is the ONLY allowed session name format
SESSION_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

# Additional restrictions
MAX_SESSION_NAME_LENGTH = 64
MIN_SESSION_NAME_LENGTH = 1


@dataclass
class VMSession:
    """VM session information with Bastion support."""

    name: str
    user: str
    key_path: str
    resource_group: str
    location: str | None = None

    # Connection routing
    public_ip: str | None = None
    bastion_tunnel: BastionTunnel | None = None

    def __post_init__(self):
        """Validate VMSession has at least one connection method."""
        if self.public_ip is None and self.bastion_tunnel is None:
            raise ValueError(f"VMSession '{self.name}' requires public IP or bastion tunnel")
        if self.public_ip is not None and self.bastion_tunnel is not None:
            raise ValueError("VMSession cannot have both public IP and bastion tunnel")

    @property
    def connection_type(self) -> str:
        """Get connection type.

        Returns:
            "bastion" if using bastion tunnel, "direct" if using public IP
        """
        return "bastion" if self.bastion_tunnel else "direct"

    @property
    def ssh_host(self) -> str:
        """Get SSH host for connection.

        Returns:
            127.0.0.1 for bastion tunnels, public_ip for direct connections

        Raises:
            ValueError: If no connection route available
        """
        if self.bastion_tunnel:
            return "127.0.0.1"
        if self.public_ip:
            return self.public_ip
        raise ValueError("No connection route available")

    @property
    def ssh_port(self) -> int:
        """Get SSH port for connection.

        Returns:
            Tunnel local_port for bastion connections, 22 for direct connections
        """
        if self.bastion_tunnel:
            return self.bastion_tunnel.local_port
        return 22


class SessionManager:
    """Validate session names and manage VM sessions."""

    @classmethod
    def validate_session_name(cls, session_name: str) -> str:
        """
        Validate session name with strict security rules.

        Args:
            session_name: User-provided session name

        Returns:
            Validated session name (unchanged if valid)

        Raises:
            InvalidSessionNameError: Session name is invalid

        Security:
            ONLY allows: a-z, A-Z, 0-9, hyphen, underscore
            NO shell metacharacters possible
        """
        if not session_name or not session_name.strip():
            raise InvalidSessionNameError("Session name cannot be empty")

        # Remove whitespace
        session_name = session_name.strip()

        # Check length
        if len(session_name) < MIN_SESSION_NAME_LENGTH:
            raise InvalidSessionNameError(f"Session name too short (min {MIN_SESSION_NAME_LENGTH})")

        if len(session_name) > MAX_SESSION_NAME_LENGTH:
            raise InvalidSessionNameError(f"Session name too long (max {MAX_SESSION_NAME_LENGTH})")

        # CRITICAL: Strict allowlist validation
        if not SESSION_NAME_PATTERN.match(session_name):
            raise InvalidSessionNameError(
                f"Invalid session name: '{session_name}'. "
                f"Only alphanumeric characters, hyphens, and underscores allowed."
            )

        return session_name

    @classmethod
    def parse_session_path(cls, arg: str) -> tuple[str | None, str]:
        """
        Parse session:path notation safely.

        Args:
            arg: Either "path" or "session:path"

        Returns:
            (session_name, path_str) tuple
            session_name is None for local paths

        Raises:
            InvalidSessionNameError: Session name is invalid

        Examples:
            "myfile.txt" -> (None, "myfile.txt")
            "vm1:~/data.txt" -> ("vm1", "~/data.txt")
            "evil;rm:file" -> InvalidSessionNameError
        """
        if ":" not in arg:
            # Local path
            return None, arg

        # Split on FIRST colon only
        parts = arg.split(":", 1)
        if len(parts) != 2:
            raise InvalidSessionNameError("Invalid session:path format. Use 'session:path'")

        session_name, path_str = parts

        # Validate session name BEFORE using it
        validated_session = cls.validate_session_name(session_name)

        # Validate path is not empty
        if not path_str or not path_str.strip():
            raise InvalidSessionNameError("Path cannot be empty in session:path")

        return validated_session, path_str

    @classmethod
    def get_vm_session(
        cls,
        session_name: str,
        resource_group: str,
        vm_manager: "type[VMManager]",
    ) -> tuple[VMSession, BastionManager | None]:
        """Get VM session by name with bastion support.

        Args:
            session_name: Validated session name
            resource_group: Azure resource group containing the VM
            vm_manager: VMManager class for VM operations

        Returns:
            Tuple of (VMSession, BastionManager | None)

        Raises:
            SessionNotFoundError: Session doesn't exist or no connection route available
            MultipleSessionsError: Ambiguous session name
        """

        # List VMs
        vms = vm_manager.list_vms(resource_group)

        # Filter by name (exact match or prefix)
        matching_vms = [
            vm for vm in vms if vm.name == session_name or vm.name.startswith(session_name)
        ]

        if len(matching_vms) == 0:
            raise SessionNotFoundError(f"No VM found matching session '{session_name}'")

        if len(matching_vms) > 1:
            vm_names = [vm.name for vm in matching_vms]
            raise MultipleSessionsError(
                f"Multiple VMs match '{session_name}': {', '.join(vm_names)}"
            )

        vm = matching_vms[0]

        # Validate VM is running
        if vm.power_state != "VM running":
            raise SessionNotFoundError(f"VM '{vm.name}' is not running (state: {vm.power_state})")

        # Check for public IP first (backward compatible path)
        if vm.public_ip:
            return (
                VMSession(
                    name=vm.name,
                    public_ip=vm.public_ip,
                    user=DEFAULT_SSH_USER,
                    key_path=DEFAULT_SSH_KEY,
                    resource_group=resource_group,
                    location=vm.location,
                    bastion_tunnel=None,
                ),
                None,
            )

        # No public IP - detect bastion
        bastion_info = BastionDetector.detect_bastion_for_vm(
            vm_name=vm.name,
            resource_group=resource_group,
            vm_location=vm.location,
        )

        if not bastion_info:
            raise SessionNotFoundError(
                f"VM '{vm.name}' has no public IP and no bastion is available"
            )

        # Create bastion tunnel
        # Get VM resource ID using VMManager
        vm_resource_id = VMManager.get_vm_resource_id(vm.name, resource_group)
        if not vm_resource_id:
            raise SessionNotFoundError(f"Could not get resource ID for VM: {vm.name}")

        bastion_manager = BastionManager()
        local_port = bastion_manager.get_available_port()

        tunnel = bastion_manager.create_tunnel(
            bastion_name=bastion_info["name"],
            resource_group=bastion_info["resource_group"],
            target_vm_id=vm_resource_id,
            local_port=local_port,
            remote_port=22,
            wait_for_ready=True,
        )

        return (
            VMSession(
                name=vm.name,
                public_ip=None,
                user=DEFAULT_SSH_USER,
                key_path=DEFAULT_SSH_KEY,
                resource_group=resource_group,
                location=vm.location,
                bastion_tunnel=tunnel,
            ),
            bastion_manager,
        )
