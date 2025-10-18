"""Configuration management module.

This module handles persistent configuration storage using TOML format.
Stores user preferences like default resource group, region, and VM size.

Security:
- Config file permissions: 0600 (owner read/write only)
- Path validation
- Input sanitization
"""

import logging
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    import tomli  # type: ignore[import]
    import tomli_w
except ImportError:
    # Fallback for older Python versions
    try:
        import tomllib as tomli  # type: ignore[import]

        import tomli_w
    except ImportError as e:
        raise ImportError(
            "toml library not available. Install with: pip install tomli tomli-w"
        ) from e

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when configuration operations fail."""

    pass


@dataclass
class AzlinConfig:
    """Azlin configuration data."""

    default_resource_group: str | None = None
    default_region: str = "westus2"  # westus2 has better capacity than eastus
    default_vm_size: str = "Standard_B2s"  # Widely available, affordable burstable VM
    last_vm_name: str | None = None
    notification_command: str = "imessR"
    session_names: dict[str, str] | None = None  # vm_name -> session_name mapping
    vm_storage: dict[str, str] | None = None  # vm_name -> storage_name mapping (for NFS)
    default_nfs_storage: str | None = None  # Default NFS storage for new VMs

    @property
    def resource_group(self) -> str | None:
        """Convenience property for default_resource_group."""
        return self.default_resource_group

    @property
    def region(self) -> str:
        """Convenience property for default_region."""
        return self.default_region

    @property
    def vm_size(self) -> str:
        """Convenience property for default_vm_size."""
        return self.default_vm_size

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        data = asdict(self)
        # Filter out None values as TOML doesn't support them
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AzlinConfig":
        """Create from dictionary."""
        return cls(
            default_resource_group=data.get("default_resource_group"),
            default_region=data.get("default_region", "westus2"),
            default_vm_size=data.get("default_vm_size", "Standard_B2s"),
            last_vm_name=data.get("last_vm_name"),
            notification_command=data.get("notification_command", "imessR"),
            session_names=data.get("session_names", {}),
            vm_storage=data.get("vm_storage", {}),
            default_nfs_storage=data.get("default_nfs_storage"),
        )


class ConfigManager:
    """Manage azlin configuration file.

    Configuration is stored at ~/.azlin/config.toml with secure permissions.
    """

    DEFAULT_CONFIG_DIR = Path.home() / ".azlin"
    DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.toml"

    @classmethod
    def _validate_config_path(cls, path: Path) -> None:
        """Validate that config path is within allowed directories.

        Args:
            path: Resolved path to validate

        Raises:
            ConfigError: If path is outside allowed directories

        Security:
            Prevents path traversal attacks by ensuring paths are contained
            within either ~/.azlin/ or the current working directory.
        """
        # Get allowed base directories
        allowed_dirs = [
            cls.DEFAULT_CONFIG_DIR.resolve(),  # ~/.azlin/
            Path.cwd().resolve(),  # Current working directory
        ]

        # Check if path is within any allowed directory
        for allowed_dir in allowed_dirs:
            try:
                # Check if path is relative to allowed_dir
                # This will raise ValueError if path is not relative to allowed_dir
                path.relative_to(allowed_dir)
                return  # Path is valid
            except ValueError:
                continue  # Try next allowed directory

        # Path is not within any allowed directory
        raise ConfigError(
            f"Config path outside allowed directories: {path}. "
            f"Allowed: {cls.DEFAULT_CONFIG_DIR} or current directory"
        )

    @classmethod
    def get_config_path(cls, custom_path: str | None = None) -> Path:
        """Get configuration file path.

        Args:
            custom_path: Custom config file path (optional)

        Returns:
            Path to config file

        Raises:
            ConfigError: If path is invalid or outside allowed directories
        """
        if custom_path:
            # Handle empty string as default path
            if not custom_path.strip():
                return cls.DEFAULT_CONFIG_FILE

            # Resolve path to handle symlinks and relative paths
            path = Path(custom_path).expanduser().resolve()

            # Validate path is within allowed directories
            cls._validate_config_path(path)

            # Check file exists after validation
            if not path.exists():
                raise ConfigError(f"Config file not found: {path}")

            return path

        return cls.DEFAULT_CONFIG_FILE

    @classmethod
    def ensure_config_dir(cls) -> Path:
        """Ensure config directory exists with secure permissions.

        Returns:
            Path to config directory

        Raises:
            ConfigError: If directory creation fails
        """
        try:
            cls.DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

            # Set secure permissions (owner only: rwx------)
            os.chmod(cls.DEFAULT_CONFIG_DIR, 0o700)

            logger.debug(f"Config directory ready: {cls.DEFAULT_CONFIG_DIR}")
            return cls.DEFAULT_CONFIG_DIR

        except Exception as e:
            raise ConfigError(f"Failed to create config directory: {e}") from e

    @classmethod
    def get_config(cls, custom_path: str | None = None) -> AzlinConfig:
        """Get configuration (alias for load_config).

        Args:
            custom_path: Custom config file path (optional)

        Returns:
            AzlinConfig object

        Raises:
            ConfigError: If loading fails
        """
        return cls.load_config(custom_path)

    @classmethod
    def load_config(cls, custom_path: str | None = None) -> AzlinConfig:
        """Load configuration from file.

        Args:
            custom_path: Custom config file path (optional)

        Returns:
            AzlinConfig object

        Raises:
            ConfigError: If loading fails
        """
        config_path = cls.get_config_path(custom_path)

        if not config_path.exists():
            logger.debug("Config file not found, using defaults")
            return AzlinConfig()

        try:
            # Verify file permissions
            stat = config_path.stat()
            mode = stat.st_mode & 0o777

            if mode & 0o077:  # Check if group/other have any permissions
                logger.warning(
                    f"Config file has insecure permissions: {oct(mode)}. Fixing to 0600..."
                )
                os.chmod(config_path, 0o600)

            # Load TOML
            with open(config_path, "rb") as f:
                data = tomli.load(f)  # type: ignore[attr-defined]

            logger.debug(f"Loaded config from: {config_path}")
            return AzlinConfig.from_dict(data)  # type: ignore[arg-type]

        except Exception as e:
            raise ConfigError(f"Failed to load config: {e}") from e

    @classmethod
    def save_config(cls, config: AzlinConfig, custom_path: str | None = None) -> None:
        """Save configuration to file.

        Args:
            config: Configuration to save
            custom_path: Custom config file path (optional)

        Raises:
            ConfigError: If saving fails or path is outside allowed directories
        """
        temp_path: Path | None = None
        try:
            # Determine config path
            if custom_path:
                # Resolve path to handle symlinks and relative paths
                config_path = Path(custom_path).expanduser().resolve()

                # Validate path is within allowed directories
                cls._validate_config_path(config_path)

                # Ensure parent directory exists
                config_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                # Ensure default directory exists
                cls.ensure_config_dir()
                config_path = cls.DEFAULT_CONFIG_FILE

            # Write TOML with secure permissions
            # Use temporary file and atomic rename for safety
            temp_path = config_path.with_suffix(".tmp")

            with open(temp_path, "wb") as f:
                tomli_w.dump(config.to_dict(), f)

            # Set secure permissions before moving
            os.chmod(temp_path, 0o600)

            # Atomic rename
            temp_path.replace(config_path)

            logger.debug(f"Saved config to: {config_path}")

        except ConfigError:
            # Re-raise ConfigError (including validation errors)
            raise
        except Exception as e:
            # Cleanup temp file on error
            if temp_path and temp_path.exists():
                temp_path.unlink()
            raise ConfigError(f"Failed to save config: {e}") from e

    @classmethod
    def update_config(cls, custom_path: str | None = None, **updates: Any) -> AzlinConfig:
        """Update configuration values.

        Args:
            custom_path: Custom config file path (optional)
            **updates: Configuration values to update

        Returns:
            Updated AzlinConfig

        Raises:
            ConfigError: If update fails
        """
        # Load existing config
        config = cls.load_config(custom_path)

        # Update values
        for key, value in updates.items():
            if hasattr(config, key):
                setattr(config, key, value)
            else:
                logger.warning(f"Unknown config key: {key}")

        # Save updated config
        cls.save_config(config, custom_path)

        return config

    @classmethod
    def get_resource_group(
        cls, cli_value: str | None = None, custom_path: str | None = None
    ) -> str | None:
        """Get resource group with CLI override.

        Args:
            cli_value: Resource group from CLI argument (takes precedence)
            custom_path: Custom config file path (optional)

        Returns:
            Resource group name or None
        """
        if cli_value:
            return cli_value

        config = cls.load_config(custom_path)
        return config.default_resource_group

    @classmethod
    def get_region(cls, cli_value: str | None = None, custom_path: str | None = None) -> str:
        """Get region with CLI override.

        Args:
            cli_value: Region from CLI argument (takes precedence)
            custom_path: Custom config file path (optional)

        Returns:
            Region name (defaults to eastus)
        """
        if cli_value:
            return cli_value

        config = cls.load_config(custom_path)
        return config.default_region

    @classmethod
    def get_vm_size(cls, cli_value: str | None = None, custom_path: str | None = None) -> str:
        """Get VM size with CLI override.

        Args:
            cli_value: VM size from CLI argument (takes precedence)
            custom_path: Custom config file path (optional)

        Returns:
            VM size (defaults to Standard_D2s_v3)
        """
        if cli_value:
            return cli_value

        config = cls.load_config(custom_path)
        return config.default_vm_size

    @classmethod
    def set_session_name(
        cls, vm_name: str, session_name: str, custom_path: str | None = None
    ) -> None:
        """Set session name for a VM.

        Args:
            vm_name: VM name
            session_name: Session name to set
            custom_path: Custom config file path (optional)

        Raises:
            ConfigError: If update fails
        """
        try:
            config = cls.load_config(custom_path)
        except ConfigError:
            # If config doesn't exist, create a new one
            config = AzlinConfig()

        if config.session_names is None:
            config.session_names = {}

        config.session_names[vm_name] = session_name
        cls.save_config(config, custom_path)

    @classmethod
    def get_session_name(cls, vm_name: str, custom_path: str | None = None) -> str | None:
        """Get session name for a VM.

        Args:
            vm_name: VM name
            custom_path: Custom config file path (optional)

        Returns:
            Session name or None if not set
        """
        try:
            config = cls.load_config(custom_path)
            if config.session_names:
                return config.session_names.get(vm_name)
        except ConfigError:
            pass
        return None

    @classmethod
    def delete_session_name(cls, vm_name: str, custom_path: str | None = None) -> bool:
        """Delete session name for a VM.

        Args:
            vm_name: VM name
            custom_path: Custom config file path (optional)

        Returns:
            True if deleted, False if not found

        Raises:
            ValueError: If vm_name format is invalid
        """
        # Validate vm_name format (defense in depth)
        # Azure VM naming: 1-64 characters, alphanumeric + hyphen/underscore
        if not vm_name or not re.match(r"^[a-zA-Z0-9_-]{1,64}$", vm_name):
            logger.warning(f"Invalid vm_name format: {vm_name}")
            raise ValueError(f"Invalid VM name format: {vm_name}")

        try:
            config = cls.load_config(custom_path)
            if config.session_names and vm_name in config.session_names:
                del config.session_names[vm_name]
                cls.save_config(config, custom_path)
                return True
        except ConfigError:
            pass
        return False

    @classmethod
    def get_vm_name_by_session(
        cls, session_name: str, custom_path: str | None = None
    ) -> str | None:
        """Get VM name by session name.

        Args:
            session_name: Session name to look up
            custom_path: Custom config file path (optional)

        Returns:
            VM name or None if not found
        """
        try:
            config = cls.load_config(custom_path)
            if config.session_names:
                # Reverse lookup: find VM name for this session name
                for vm_name, sess_name in config.session_names.items():
                    if sess_name == session_name:
                        return vm_name
        except ConfigError:
            pass
        return None


__all__ = ["AzlinConfig", "ConfigError", "ConfigManager"]
