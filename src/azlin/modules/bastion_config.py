"""Bastion configuration management module.

This module handles Bastion configuration data structures including:
- VM-to-Bastion mappings
- Configuration persistence (TOML)
- Default Bastion settings
- Auto-detection preferences

Security:
- Config file permissions: 0600 (owner read/write only)
- Input validation for names and resource groups
- No secrets stored in config
"""

import logging
import os
import re
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomli  # type: ignore[import-not-found]
    import tomli_w  # type: ignore[import-not-found]
except ImportError:
    try:
        import tomllib as tomli  # type: ignore[import-not-found]

        import tomli_w  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError(
            "toml library not available. Install with: pip install tomli tomli-w"
        ) from e

logger = logging.getLogger(__name__)


class BastionConfigError(Exception):
    """Raised when Bastion configuration operations fail."""


@dataclass
class BastionMapping:
    """VM-to-Bastion mapping configuration.

    Maps a specific VM to a Bastion host for connection routing.
    """

    vm_name: str
    vm_resource_group: str
    bastion_name: str
    bastion_resource_group: str
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BastionMapping":
        """Create from dictionary."""
        return cls(
            vm_name=data["vm_name"],
            vm_resource_group=data["vm_resource_group"],
            bastion_name=data["bastion_name"],
            bastion_resource_group=data["bastion_resource_group"],
            enabled=data.get("enabled", True),
        )


@dataclass
class BastionConfig:
    """Bastion configuration management.

    Stores VM-to-Bastion mappings and connection preferences.
    Config stored at ~/.azlin/bastion_config.toml with secure permissions.
    """

    mappings: dict[str, BastionMapping] = field(default_factory=dict)
    default_bastion: tuple[str, str] | None = None  # (name, resource_group)
    auto_detect: bool = True  # Auto-detect Bastion availability
    prefer_bastion: bool = False  # Prefer Bastion over direct connection

    # Azure naming rules pattern
    AZURE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-]{1,64}$")
    MAX_NAME_LENGTH = 64

    @classmethod
    def _validate_name(cls, name: str, field_name: str) -> None:
        """Validate Azure resource name.

        Args:
            name: Name to validate
            field_name: Field name for error messages

        Raises:
            BastionConfigError: If name is invalid
        """
        if not name:
            raise BastionConfigError(f"{field_name} cannot be empty")

        if len(name) > cls.MAX_NAME_LENGTH:
            raise BastionConfigError(
                f"Name too long: {field_name} must be {cls.MAX_NAME_LENGTH} characters or less"
            )

        # Check for invalid characters
        if not cls.AZURE_NAME_PATTERN.match(name):
            raise BastionConfigError(
                f"Invalid characters in {field_name}: must contain only alphanumeric, "
                f"hyphen, underscore, or period characters"
            )

    def add_mapping(
        self,
        vm_name: str,
        vm_resource_group: str,
        bastion_name: str,
        bastion_resource_group: str,
    ) -> None:
        """Add VM-to-Bastion mapping.

        Args:
            vm_name: VM name
            vm_resource_group: VM resource group
            bastion_name: Bastion host name
            bastion_resource_group: Bastion resource group

        Raises:
            BastionConfigError: If validation fails
        """
        # Validate inputs
        self._validate_name(vm_name, "VM name")
        self._validate_name(vm_resource_group, "Resource group")
        self._validate_name(bastion_name, "Bastion name")
        self._validate_name(bastion_resource_group, "Resource group")

        mapping = BastionMapping(
            vm_name=vm_name,
            vm_resource_group=vm_resource_group,
            bastion_name=bastion_name,
            bastion_resource_group=bastion_resource_group,
        )

        self.mappings[vm_name] = mapping
        logger.debug(f"Added Bastion mapping: {vm_name} -> {bastion_name}")

    def remove_mapping(self, vm_name: str) -> None:
        """Remove VM-to-Bastion mapping.

        Args:
            vm_name: VM name
        """
        if vm_name in self.mappings:
            del self.mappings[vm_name]
            logger.debug(f"Removed Bastion mapping for: {vm_name}")

    def get_mapping(self, vm_name: str) -> BastionMapping | None:
        """Get Bastion mapping for VM.

        Args:
            vm_name: VM name

        Returns:
            BastionMapping or None if not found or disabled
        """
        mapping = self.mappings.get(vm_name)
        if mapping and mapping.enabled:
            return mapping
        return None

    def enable_mapping(self, vm_name: str) -> None:
        """Enable Bastion mapping for VM.

        Args:
            vm_name: VM name
        """
        if vm_name in self.mappings:
            self.mappings[vm_name].enabled = True
            logger.debug(f"Enabled Bastion mapping for: {vm_name}")

    def disable_mapping(self, vm_name: str) -> None:
        """Disable Bastion mapping for VM.

        Args:
            vm_name: VM name
        """
        if vm_name in self.mappings:
            self.mappings[vm_name].enabled = False
            logger.debug(f"Disabled Bastion mapping for: {vm_name}")

    def list_mappings(self, only_enabled: bool = False) -> list[BastionMapping]:
        """List all Bastion mappings.

        Args:
            only_enabled: Only return enabled mappings

        Returns:
            List of BastionMapping objects
        """
        mappings = list(self.mappings.values())
        if only_enabled:
            mappings = [m for m in mappings if m.enabled]
        return mappings

    def set_default_bastion(self, bastion_name: str, resource_group: str) -> None:
        """Set default Bastion host.

        Args:
            bastion_name: Bastion host name
            resource_group: Resource group
        """
        self._validate_name(bastion_name, "Bastion name")
        self._validate_name(resource_group, "Resource group")

        self.default_bastion = (bastion_name, resource_group)
        logger.debug(f"Set default Bastion: {bastion_name} in {resource_group}")

    def clear_default_bastion(self) -> None:
        """Clear default Bastion host."""
        self.default_bastion = None
        logger.debug("Cleared default Bastion")

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        data: dict[str, Any] = {
            "mappings": {name: mapping.to_dict() for name, mapping in self.mappings.items()},
            "auto_detect": self.auto_detect,
            "prefer_bastion": self.prefer_bastion,
        }

        if self.default_bastion:
            data["default_bastion"] = {
                "name": self.default_bastion[0],
                "resource_group": self.default_bastion[1],
            }

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BastionConfig":
        """Create config from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            BastionConfig object
        """
        config = cls(
            auto_detect=data.get("auto_detect", True),
            prefer_bastion=data.get("prefer_bastion", False),
        )

        # Load mappings
        mappings_data = data.get("mappings", {})
        for vm_name, mapping_data in mappings_data.items():
            mapping = BastionMapping.from_dict(mapping_data)
            config.mappings[vm_name] = mapping

        # Load default bastion
        default_bastion_data = data.get("default_bastion")
        if default_bastion_data:
            config.default_bastion = (
                default_bastion_data["name"],
                default_bastion_data["resource_group"],
            )

        return config

    def validate(self) -> bool:
        """Validate configuration.

        Returns:
            True if valid, False otherwise
        """
        try:
            # Validate all mappings
            for vm_name, mapping in self.mappings.items():
                self._validate_name(mapping.vm_name, "VM name")
                self._validate_name(mapping.vm_resource_group, "Resource group")
                self._validate_name(mapping.bastion_name, "Bastion name")
                self._validate_name(mapping.bastion_resource_group, "Resource group")

            # Validate default bastion
            if self.default_bastion:
                self._validate_name(self.default_bastion[0], "Bastion name")
                self._validate_name(self.default_bastion[1], "Resource group")

            return True
        except BastionConfigError:
            return False

    def save(self, config_path: Path) -> None:
        """Save configuration to file.

        Args:
            config_path: Path to config file

        Raises:
            BastionConfigError: If save fails
        """
        try:
            # Ensure parent directory exists
            config_path.parent.mkdir(parents=True, exist_ok=True)

            # Write TOML with secure permissions
            temp_path = config_path.with_suffix(".tmp")

            with open(temp_path, "wb") as f:
                tomli_w.dump(self.to_dict(), f)

            # Set secure permissions (owner read/write only)
            os.chmod(temp_path, 0o600)

            # Atomic rename
            temp_path.replace(config_path)

            logger.debug(f"Saved Bastion config to: {config_path}")

        except PermissionError as e:
            raise BastionConfigError(f"Permission denied writing config: {e}") from e
        except Exception as e:
            # Cleanup temp file on error
            if temp_path and temp_path.exists():
                temp_path.unlink()
            raise BastionConfigError(f"Failed to save config: {e}") from e

    @classmethod
    def load(cls, config_path: Path) -> "BastionConfig":
        """Load configuration from file.

        Args:
            config_path: Path to config file

        Returns:
            BastionConfig object (empty if file doesn't exist)

        Raises:
            BastionConfigError: If loading fails
        """
        if not config_path.exists():
            logger.debug(f"Config file not found: {config_path}, using empty config")
            return cls()

        try:
            # Check file permissions
            stat = config_path.stat()
            mode = stat.st_mode & 0o777

            if mode & 0o077:  # Group/other have permissions
                warnings.warn(
                    f"Config file has insecure permissions: {oct(mode)}. "
                    f"Recommend setting to 0600.",
                    UserWarning,
                    stacklevel=2,
                )

            # Load TOML
            with open(config_path, "rb") as f:
                data = tomli.load(f)

            logger.debug(f"Loaded Bastion config from: {config_path}")
            return cls.from_dict(data)

        except Exception as e:
            raise BastionConfigError(f"Failed to load config: {e}") from e

    def merge(self, other: "BastionConfig") -> None:
        """Merge another config into this one.

        Duplicate entries are overwritten by the other config.

        Args:
            other: Config to merge
        """
        # Merge mappings (overwrite duplicates)
        self.mappings.update(other.mappings)

        # Merge default bastion (other takes precedence)
        if other.default_bastion:
            self.default_bastion = other.default_bastion

        logger.debug("Merged Bastion configs")


__all__ = ["BastionConfig", "BastionConfigError", "BastionMapping"]
