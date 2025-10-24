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
import tempfile
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
    default_vm_size: str = (
        "Standard_E16as_v5"  # Memory-optimized: 128GB RAM, 16 vCPU, 12.5 Gbps network
    )
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
            default_vm_size=data.get("default_vm_size", "Standard_E16as_v5"),
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
    def _validate_config_path(cls, path: Path) -> Path:
        """Validate configuration file path for security.

        Ensures the path is within allowed directories to prevent path traversal attacks.

        Args:
            path: Path to validate (must be resolved)

        Returns:
            Validated path

        Raises:
            ConfigError: If path is outside allowed directories

        Security:
            - Resolves symlinks to prevent symlink attacks
            - Validates path is within ~/.azlin/ or current working directory
            - Prevents path traversal (../../etc/passwd)
            - Prevents absolute paths to sensitive locations (/etc/passwd)
        """
        # Ensure path is resolved (symlinks resolved, relative paths absolute)
        resolved_path = path.resolve()

        # Allowed directories:
        # 1. ~/.azlin/ (primary config directory)
        # 2. Current working directory (for testing/development)
        # 3. System temporary directory (for testing)
        allowed_dirs = [
            cls.DEFAULT_CONFIG_DIR.resolve(),
            Path.cwd().resolve(),
            Path(tempfile.gettempdir()).resolve(),  # Allow pytest tmp_path
        ]

        # Check if path is within any allowed directory
        for allowed_dir in allowed_dirs:
            try:
                resolved_path.relative_to(allowed_dir)
                # Path is within this allowed directory
                return resolved_path
            except ValueError:
                # Path is not within this directory, try next
                continue

        # Path is not within any allowed directory
        raise ConfigError(
            f"Config path outside allowed directories: {resolved_path}\n"
            f"Allowed directories:\n"
            f"  - {cls.DEFAULT_CONFIG_DIR}\n"
            f"  - {Path.cwd()}\n"
            "This restriction prevents path traversal attacks."
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
            path = Path(custom_path).expanduser().resolve()
            # Validate path for security
            path = cls._validate_config_path(path)
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
                config_path = Path(custom_path).expanduser().resolve()
                # Validate path for security
                config_path = cls._validate_config_path(config_path)
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
            VM size (defaults to Standard_E16as_v5)
        """
        if cli_value:
            return cli_value

        config = cls.load_config(custom_path)
        return config.default_vm_size

    @classmethod
    def _validate_session_mapping(
        cls, vm_name: str, session_name: str, existing_mappings: dict[str, str]
    ) -> None:
        """Validate session name mapping rules.

        Args:
            vm_name: VM name
            session_name: Session name to set
            existing_mappings: Existing session name mappings (excluding the one being set)

        Raises:
            ConfigError: If validation fails

        Validation Rules:
            1. No self-referential mappings (vm_name == session_name)
            2. No duplicate session names (session_name already maps to different VM)
            3. Azure naming rules (1-64 chars, alphanumeric + hyphen/underscore)
        """
        # Rule 1: No self-referential mappings
        if vm_name == session_name:
            raise ConfigError(
                f"Self-referential session name not allowed: {vm_name} -> {session_name}\n"
                f"Session name must be different from VM name to avoid connection ambiguity."
            )

        # Rule 2: No duplicate session names
        for existing_vm, existing_session in existing_mappings.items():
            if existing_session == session_name and existing_vm != vm_name:
                raise ConfigError(
                    f"Duplicate session name '{session_name}' already maps to VM '{existing_vm}'\n"
                    f"Cannot map '{vm_name}' -> '{session_name}' because session name must be unique."
                )

        # Rule 3: Azure naming rules (alphanumeric + hyphen/underscore, 1-64 chars)
        if not session_name or not re.match(r"^[a-zA-Z0-9_-]{1,64}$", session_name):
            raise ConfigError(
                f"Invalid session name format: {session_name}\n"
                f"Session names must be 1-64 characters: alphanumeric, hyphen, or underscore."
            )

        if not vm_name or not re.match(r"^[a-zA-Z0-9_-]{1,64}$", vm_name):
            raise ConfigError(
                f"Invalid VM name format: {vm_name}\n"
                f"VM names must be 1-64 characters: alphanumeric, hyphen, or underscore."
            )

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
            ConfigError: If validation fails or update fails
        """
        try:
            config = cls.load_config(custom_path)
        except ConfigError:
            # If config doesn't exist, create a new one
            config = AzlinConfig()

        if config.session_names is None:
            config.session_names = {}

        # Get existing mappings (excluding the one we're about to set)
        existing_mappings = {k: v for k, v in config.session_names.items() if k != vm_name}

        # Validate before saving
        cls._validate_session_mapping(vm_name, session_name, existing_mappings)

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
        cls, session_name: str, custom_path: str | None = None, resource_group: str | None = None
    ) -> str | None:
        """Get VM name by session name using hybrid resolution.

        Resolution priority:
        1. Azure VM tags (source of truth) - checks managed-by=azlin VMs
        2. Local config file (backward compatibility fallback)

        Args:
            session_name: Session name to look up
            custom_path: Custom config file path (optional)
            resource_group: Optional RG to limit tag search (None = all RGs)

        Returns:
            VM name or None if not found

        Note:
            Filters out self-referential entries (vm_name == session_name)
            and warns on duplicate session names pointing to different VMs.
        """
        # Priority 1: Check Azure tags first
        try:
            from azlin.tag_manager import TagManager

            vm_info = TagManager.get_vm_by_session(session_name, resource_group)
            if vm_info:
                logger.debug(
                    f"Resolved session '{session_name}' to VM '{vm_info.name}' via Azure tags"
                )
                return vm_info.name
        except Exception as e:
            logger.debug(f"Failed to resolve session via tags, falling back to config: {e}")

        # Priority 2: Fall back to local config file
        try:
            config = cls.load_config(custom_path)
            if config.session_names:
                # Track matches for duplicate detection
                matches = []

                # Reverse lookup: find VM name for this session name
                for vm_name, sess_name in config.session_names.items():
                    # Skip self-referential entries (invalid mappings)
                    if vm_name == sess_name:
                        logger.warning(
                            f"Ignoring invalid self-referential session mapping: {vm_name} -> {sess_name}"
                        )
                        continue

                    if sess_name == session_name:
                        matches.append(vm_name)

                # Warn on duplicates
                if len(matches) > 1:
                    logger.warning(
                        f"Duplicate session name '{session_name}' maps to multiple VMs: {matches}\n"
                        f"Using first match: {matches[0]}"
                    )
                    return matches[0]
                if len(matches) == 1:
                    logger.debug(
                        f"Resolved session '{session_name}' to VM '{matches[0]}' via local config"
                    )
                    return matches[0]

        except ConfigError:
            pass
        return None


__all__ = ["AzlinConfig", "ConfigError", "ConfigManager"]
