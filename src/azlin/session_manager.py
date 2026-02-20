"""Session save/load manager for azlin.

This module provides functionality to save and restore VM/tmux session configurations.
Users can save their current environment to ~/.azlin/sessions/<name>.toml and restore
it later, automatically provisioning missing VMs.

Philosophy:
- Reuse existing infrastructure (VMProvisioner, VMManager)
- TOML format for human-readable session files
- Security: File permissions 0600
- Minimal fields (no ephemeral data like IPs)
"""

import logging
import os
import tomllib  # Python 3.11+ (requires-python >= 3.11)
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import tomlkit  # For writing TOML (preserves formatting)

from azlin.remote_exec import TmuxSession
from azlin.vm_lifecycle_control import VMLifecycleController
from azlin.vm_manager import VMInfo, VMManager, VMManagerError
from azlin.vm_provisioning import VMConfig, VMProvisioner

logger = logging.getLogger(__name__)


class SessionManagerError(Exception):
    """Raised when session operations fail."""

    pass


@dataclass
class LoadResult:
    """Results from loading a session."""

    created_vms: list[str] = field(default_factory=list)  # New VMs provisioned
    existing_vms: list[str] = field(default_factory=list)  # VMs already running
    failed_vms: list[tuple[str, str]] = field(default_factory=list)  # (name, error)

    @property
    def total_vms(self) -> int:
        """Total number of VMs in session."""
        return len(self.created_vms) + len(self.existing_vms) + len(self.failed_vms)

    @property
    def success_count(self) -> int:
        """Number of successfully restored VMs."""
        return len(self.created_vms) + len(self.existing_vms)


@dataclass
class SessionConfig:
    """Saved session configuration."""

    name: str
    saved_at: str  # ISO 8601 timestamp
    resource_group: str
    vms: list[dict[str, Any]]  # VMInfo dicts + nested tmux sessions

    def to_toml(self) -> str:
        """Serialize to TOML string.

        Returns:
            TOML-formatted string
        """
        doc = tomlkit.document()

        # Session metadata
        session_table = tomlkit.table()
        session_table.add("name", self.name)
        session_table.add("saved_at", self.saved_at)
        session_table.add("resource_group", self.resource_group)
        doc.add("session", session_table)

        # VMs array of tables (use aot() for [[vms]] syntax)
        vms_array = tomlkit.aot()
        for vm_data in self.vms:
            vm_table = tomlkit.table()
            vm_table.add("name", vm_data["name"])
            vm_table.add("resource_group", vm_data["resource_group"])
            vm_table.add("location", vm_data["location"])
            vm_table.add("vm_size", vm_data.get("vm_size") or "Standard_E16as_v5")

            # Optional session name
            if vm_data.get("session_name"):
                vm_table.add("session_name", vm_data["session_name"])

            # Tmux sessions (nested array of tables)
            if vm_data.get("tmux_sessions"):
                tmux_array = tomlkit.array()
                for tmux in vm_data["tmux_sessions"]:
                    tmux_table = tomlkit.inline_table()
                    tmux_table.update(
                        {
                            "session_name": tmux["session_name"],
                            "windows": tmux["windows"],
                            "attached": tmux.get("attached", False),
                        }
                    )
                    tmux_array.append(tmux_table)
                vm_table.add("tmux_sessions", tmux_array)

            vms_array.append(vm_table)

        doc.add("vms", vms_array)

        return tomlkit.dumps(doc)

    @classmethod
    def from_toml(cls, toml_str: str) -> "SessionConfig":
        """Deserialize from TOML string.

        Args:
            toml_str: TOML-formatted string

        Returns:
            SessionConfig object
        """
        try:
            data = tomllib.loads(toml_str)
        except (tomllib.TOMLDecodeError, ValueError) as e:
            raise SessionManagerError(f"Invalid TOML format: {e}") from e

        # Validate required fields
        if "session" not in data:
            raise SessionManagerError("Missing [session] section in TOML")

        session = data["session"]
        for field_name in ["name", "saved_at", "resource_group"]:
            if field_name not in session:
                raise SessionManagerError(f"Missing required field: session.{field_name}")

        # Parse VMs
        vms = data.get("vms", [])
        if not vms:
            raise SessionManagerError("Session has no VMs")

        return cls(
            name=session["name"],
            saved_at=session["saved_at"],
            resource_group=session["resource_group"],
            vms=vms,
        )


class SessionManager:
    """Session save/load operations."""

    SESSIONS_DIR = Path.home() / ".azlin" / "sessions"

    # Security: Allowlist of VM fields that can be saved
    # NEVER include credentials, SSH keys, or sensitive data
    ALLOWED_VM_FIELDS = frozenset(
        {
            "name",
            "resource_group",
            "location",
            "vm_size",
            "session_name",
            "tmux_sessions",
        }
    )

    @classmethod
    def _ensure_sessions_dir(cls) -> None:
        """Ensure sessions directory exists with correct permissions."""
        cls.SESSIONS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)

    @classmethod
    def _validate_session_name(cls, name: str) -> None:
        """Validate session name (alphanumeric, hyphen, underscore only).

        Args:
            name: Session name to validate

        Raises:
            SessionManagerError: If name is invalid
        """
        if not name:
            raise SessionManagerError("Session name cannot be empty")

        if not all(c.isalnum() or c in ("-", "_") for c in name):
            raise SessionManagerError(
                f"Invalid session name: {name}\n"
                "Only alphanumeric characters, hyphens, and underscores allowed"
            )

    @classmethod
    def save_session(
        cls,
        session_name: str,
        vm_session_pairs: list[tuple[VMInfo, list[TmuxSession]]],
        resource_group: str,
    ) -> Path:
        """Save VM/session state to ~/.azlin/sessions/<name>.toml.

        Args:
            session_name: Name for the session
            vm_session_pairs: List of (VMInfo, list[TmuxSession]) tuples
            resource_group: Resource group name

        Returns:
            Path to saved session file

        Raises:
            SessionManagerError: If save fails
        """
        cls._validate_session_name(session_name)
        cls._ensure_sessions_dir()

        # Build session config
        vms_data: list[dict[str, Any]] = []
        for vm_info, tmux_sessions in vm_session_pairs:
            # Security: Only save allowlisted fields (prevent secrets exposure)
            vm_dict: dict[str, Any] = {
                "name": vm_info.name,
                "resource_group": vm_info.resource_group,
                "location": vm_info.location,
                "vm_size": vm_info.vm_size or "Standard_E16as_v5",
            }

            # Add optional fields if present (still from allowlist)
            if vm_info.session_name:
                vm_dict["session_name"] = vm_info.session_name

            # Add tmux sessions
            if tmux_sessions:
                vm_dict["tmux_sessions"] = [s.to_dict() for s in tmux_sessions]

            # Verify all keys are in allowlist (defensive programming)
            for key in vm_dict:
                if key not in cls.ALLOWED_VM_FIELDS:
                    logger.warning(
                        f"Field '{key}' not in ALLOWED_VM_FIELDS - potential security risk"
                    )

            vms_data.append(vm_dict)

        # Create session config
        session_config = SessionConfig(
            name=session_name,
            saved_at=datetime.now(UTC).isoformat(),
            resource_group=resource_group,
            vms=vms_data,
        )

        # Write to file with 0600 permissions
        session_file = cls.SESSIONS_DIR / f"{session_name}.toml"

        try:
            toml_content = session_config.to_toml()
            session_file.write_text(toml_content)
            os.chmod(session_file, 0o600)  # Owner read/write only
            logger.info(f"Saved session to {session_file}")
            return session_file

        except OSError as e:
            raise SessionManagerError(f"Failed to write session file {session_file}: {e}") from e
        except Exception as e:
            raise SessionManagerError(f"Failed to save session '{session_name}': {e}") from e

    @classmethod
    def load_session(cls, session_name: str) -> SessionConfig:
        """Load session from TOML file.

        Args:
            session_name: Name of the session to load

        Returns:
            SessionConfig object

        Raises:
            SessionManagerError: If load fails
        """
        cls._validate_session_name(session_name)

        session_file = cls.SESSIONS_DIR / f"{session_name}.toml"

        if not session_file.exists():
            # List available sessions
            available = cls.list_sessions()
            if available:
                available_names = ", ".join(available)
                raise SessionManagerError(
                    f"Session '{session_name}' not found.\nAvailable sessions: {available_names}"
                )
            raise SessionManagerError(
                f"Session '{session_name}' not found.\n"
                "No saved sessions found in ~/.azlin/sessions/"
            )

        try:
            toml_content = session_file.read_text()
            return SessionConfig.from_toml(toml_content)
        except SessionManagerError:
            raise  # Don't double-wrap our own errors
        except OSError as e:
            raise SessionManagerError(f"Failed to read session file {session_file}: {e}") from e

    @classmethod
    def list_sessions(cls) -> list[str]:
        """List all saved sessions.

        Returns:
            List of session names (without .toml extension)
        """
        if not cls.SESSIONS_DIR.exists():
            return []

        return [f.stem for f in cls.SESSIONS_DIR.glob("*.toml") if f.is_file()]

    @classmethod
    def restore_session(
        cls,
        session_config: SessionConfig,
        progress_callback: Callable[[str], None] | None = None,
    ) -> LoadResult:
        """Restore VMs from session config.

        Args:
            session_config: Session configuration to restore
            progress_callback: Optional callback for progress updates

        Returns:
            LoadResult with summary of created/existing/failed VMs

        Raises:
            SessionManagerError: If restore fails completely
        """
        result = LoadResult()

        # Check which VMs need to be created
        vms_to_create: list[VMConfig] = []

        for vm_data in session_config.vms:
            vm_name = vm_data["name"]
            rg = vm_data["resource_group"]

            # Check if VM exists
            try:
                existing_vm = VMManager.get_vm(vm_name, rg)

                if existing_vm:
                    # VM exists
                    if existing_vm.is_running():
                        result.existing_vms.append(vm_name)
                        logger.info(f"VM {vm_name} already running")
                    else:
                        # VM exists but stopped - start it
                        logger.info(f"VM {vm_name} exists but is stopped, starting...")
                        try:
                            lifecycle_result = VMLifecycleController.start_vm(
                                vm_name, rg, no_wait=False
                            )
                            if lifecycle_result.success:
                                result.existing_vms.append(vm_name)
                                logger.info(f"Started existing VM: {vm_name}")
                            else:
                                result.failed_vms.append(
                                    (vm_name, f"Failed to start VM: {lifecycle_result.message}")
                                )
                        except Exception as e:
                            result.failed_vms.append((vm_name, f"Failed to start VM: {e}"))
                            logger.error(f"Error starting VM {vm_name}: {e}")
                    continue

            except VMManagerError:
                # VM not found - will provision
                logger.debug(f"VM {vm_name} not found, will provision")
            except Exception as e:
                logger.warning(f"Error checking VM {vm_name}: {e}")
                result.failed_vms.append((vm_name, f"Failed to check VM status: {e}"))
                continue

            # VM doesn't exist - add to provision list
            vm_config = VMConfig(
                name=vm_name,
                resource_group=rg,
                location=vm_data["location"],
                size=vm_data.get("vm_size") or "Standard_E16as_v5",
                session_name=vm_data.get("session_name"),
            )
            vms_to_create.append(vm_config)

        # Provision missing VMs
        if vms_to_create:
            logger.info(f"Provisioning {len(vms_to_create)} missing VMs...")

            if progress_callback:
                progress_callback(f"Provisioning {len(vms_to_create)} VMs...")
                progress_callback("This will take 3-5 minutes per VM...")

            try:
                # Use VMProvisioner.provision_vm_pool for parallel provisioning
                provisioner = VMProvisioner()
                pool_result = provisioner.provision_vm_pool(
                    configs=vms_to_create,
                    progress_callback=progress_callback,
                    max_workers=min(5, len(vms_to_create)),  # Max 5 parallel
                )

                # Process successful provisions
                for vm_details in pool_result.successful:
                    result.created_vms.append(vm_details.name)
                    logger.info(f"Successfully provisioned: {vm_details.name}")

                # Process failures
                for failure in pool_result.failed:
                    result.failed_vms.append((failure.config.name, failure.error))
                    logger.error(f"Failed to provision {failure.config.name}: {failure.error}")

                # Process RG failures
                for rg_failure in pool_result.rg_failures:
                    # Find all VMs that depend on this RG
                    for vm_config in vms_to_create:
                        if (
                            vm_config.resource_group == rg_failure.rg_name
                            and vm_config.name not in result.created_vms
                        ):
                            result.failed_vms.append(
                                (
                                    vm_config.name,
                                    f"Resource group creation failed: {rg_failure.error}",
                                )
                            )

            except Exception as e:
                logger.error(f"VM provisioning failed: {e}")
                # Add all VMs to failed list if provisioner itself fails
                for vm_config in vms_to_create:
                    if vm_config.name not in result.created_vms:
                        result.failed_vms.append((vm_config.name, str(e)))

        return result


__all__ = ["LoadResult", "SessionConfig", "SessionManager", "SessionManagerError"]
