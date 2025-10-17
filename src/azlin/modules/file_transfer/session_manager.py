"""Secure session name validation and VM lookup."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .exceptions import InvalidSessionNameError, MultipleSessionsError, SessionNotFoundError

# CRITICAL: This pattern is the ONLY allowed session name format
SESSION_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

# Additional restrictions
MAX_SESSION_NAME_LENGTH = 64
MIN_SESSION_NAME_LENGTH = 1


@dataclass
class VMSession:
    """VM session information."""

    name: str
    public_ip: str
    user: str
    key_path: str
    resource_group: str


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
    def parse_session_path(cls, arg: str) -> tuple[Optional[str], str]:
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
        vm_manager,  # VMManager class
    ) -> VMSession:
        """
        Get VM session by name.

        Args:
            session_name: Validated session name
            resource_group: Azure resource group containing the VM
            vm_manager: VMManager class for VM operations

        Returns:
            VMSession with SSH details

        Raises:
            SessionNotFoundError: Session doesn't exist
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
        if vm.power_state != "running":
            raise SessionNotFoundError(f"VM '{vm.name}' is not running (state: {vm.power_state})")

        # Validate IP exists
        if not vm.public_ip:
            raise SessionNotFoundError(f"VM '{vm.name}' has no public IP")

        return VMSession(
            name=vm.name,
            public_ip=vm.public_ip,
            user="azureuser",
            key_path=str(Path.home() / ".ssh" / "azlin_key"),
            resource_group=resource_group,
        )
