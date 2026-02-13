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
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import click

from azlin.modules.azure_cli_helper import get_az_command

try:
    import tomli  # type: ignore[import]
except ImportError:
    # Fallback for older Python versions
    try:
        import tomllib as tomli  # type: ignore[import]
    except ImportError as e:
        raise ImportError("toml library not available. Install with: pip install tomli") from e

try:
    import tomlkit  # type: ignore[import]
except ImportError as e:
    raise ImportError("tomlkit library not available. Install with: pip install tomlkit") from e

logger = logging.getLogger(__name__)

# Common Azure regions for first-run wizard
COMMON_REGIONS = [
    "eastus",
    "eastus2",
    "westus2",
    "westus3",
    "centralus",
    "northcentralus",
    "southcentralus",
    "westcentralus",
]


class ConfigError(Exception):
    """Raised when configuration operations fail."""

    pass


def get_default_notification_command(platform: str | None = None) -> str:
    """Get platform-appropriate default notification command.

    Args:
        platform: Platform name (darwin, linux, wsl, windows, unknown).
                  If None, auto-detects platform using PrerequisiteChecker.

    Returns:
        str: Platform-appropriate notification command with {} placeholder.

    Examples:
        >>> get_default_notification_command("darwin")
        'osascript -e \\'display notification "{}" with title "Azlin"\\''

        >>> get_default_notification_command("linux")
        "notify-send 'Azlin' '{}'"

        >>> get_default_notification_command()  # Auto-detects platform
        'osascript -e \\'display notification "{}" with title "Azlin"\\''  # on macOS
    """
    # Auto-detect platform if not provided
    if platform is None:
        from azlin.modules.prerequisites import PrerequisiteChecker

        platform = PrerequisiteChecker.detect_platform()

    # Platform-specific notification commands
    # All commands must include {} as message placeholder
    platform_commands = {
        "darwin": 'osascript -e \'display notification "{}" with title "Azlin"\'',
        "macos": 'osascript -e \'display notification "{}" with title "Azlin"\'',  # Alias for darwin
        "linux": "notify-send 'Azlin' '{}'",
        "wsl": "powershell.exe -Command \"New-BurntToastNotification -Text '{}'\"",
        "windows": "powershell -Command \"New-BurntToastNotification -Text '{}'\"",
    }

    # Return platform-specific command or fallback
    return platform_commands.get(platform, "echo 'Notification: {}'")


@dataclass
class AzlinConfig:
    """Azlin configuration data."""

    default_resource_group: str | None = None
    default_region: str = "westus2"  # westus2 has better capacity than eastus
    default_vm_size: str = (
        "Standard_E16as_v5"  # Memory-optimized: 128GB RAM, 16 vCPU, 12.5 Gbps network
    )
    last_vm_name: str | None = None
    notification_command: str | None = None  # Will use default_factory, set in __post_init__
    session_names: dict[str, str] | None = None  # vm_name -> session_name mapping
    vm_storage: dict[str, str] | None = None  # vm_name -> storage_name mapping (for NFS)
    default_nfs_storage: str | None = None  # Default NFS storage for new VMs
    github_runner_fleets: dict[str, dict[str, Any]] | None = None  # pool_name -> fleet config

    # SSH key synchronization settings (Issue #419)
    ssh_auto_sync_keys: bool = True  # Auto-sync SSH keys from Key Vault to VM
    ssh_sync_timeout: int = 30  # Timeout for key sync operations (seconds)
    ssh_sync_method: str = "auto"  # auto, run-command, ssh, skip

    # SSH auto-sync for new VMs (Issue #492)
    ssh_auto_sync_age_threshold: int = (
        600  # seconds (10 minutes) - skip auto-sync for VMs younger than this
    )
    ssh_auto_sync_skip_new_vms: bool = True  # Skip auto-sync for new VMs to avoid timeouts

    # Resource group discovery settings (Issue #419)
    resource_group_auto_detect: bool = True  # Auto-detect resource groups
    resource_group_cache_ttl: int = 900  # Cache TTL in seconds (15 minutes)
    resource_group_query_timeout: int = 30  # Azure query timeout (seconds)
    resource_group_fallback_to_default: bool = True  # Use default RG on failure

    # Bastion detection settings (Issue #608)
    bastion_detection_timeout: int = 60  # Timeout for Bastion detection in seconds (WSL2 needs 60s)

    def __post_init__(self):
        """Set platform-appropriate default for notification_command if None."""
        if self.notification_command is None:
            self.notification_command = get_default_notification_command()

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
        """Create from dictionary.

        Applies platform-appropriate notification_command default only when:
        - notification_command is missing from data, OR
        - notification_command is empty string

        Preserves existing custom notification commands (including "imessR")
        for backward compatibility.
        """
        # Get notification_command from data
        notification_cmd = data.get("notification_command")

        # Apply default only if missing or empty
        if not notification_cmd:
            notification_cmd = None  # Will be set by __post_init__

        return cls(
            default_resource_group=data.get("default_resource_group"),
            default_region=data.get("default_region", "westus2"),
            default_vm_size=data.get("default_vm_size", "Standard_E16as_v5"),
            last_vm_name=data.get("last_vm_name"),
            notification_command=notification_cmd,
            session_names=data.get("session_names", {}),
            vm_storage=data.get("vm_storage", {}),
            default_nfs_storage=data.get("default_nfs_storage"),
            # SSH key sync settings
            ssh_auto_sync_keys=data.get("ssh_auto_sync_keys", True),
            ssh_sync_timeout=data.get("ssh_sync_timeout", 30),
            ssh_sync_method=data.get("ssh_sync_method", "auto"),
            # SSH auto-sync for new VMs (Issue #492)
            ssh_auto_sync_age_threshold=data.get("ssh_auto_sync_age_threshold", 600),
            ssh_auto_sync_skip_new_vms=data.get("ssh_auto_sync_skip_new_vms", True),
            # Resource group discovery settings
            resource_group_auto_detect=data.get("resource_group_auto_detect", True),
            resource_group_cache_ttl=data.get("resource_group_cache_ttl", 900),
            resource_group_query_timeout=data.get("resource_group_query_timeout", 30),
            resource_group_fallback_to_default=data.get("resource_group_fallback_to_default", True),
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
        # CRITICAL: Prevent tests from modifying production config (Issue #279)
        if os.getenv("AZLIN_TEST_MODE") == "true" and custom_path is None:
            raise ConfigError(
                "Cannot save to production config during tests. "
                "Tests must use custom_path with tmp_path fixture. "
                "This protects ~/.azlin/config.toml from being overwritten."
            )

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
            # Use tomlkit to preserve comments and formatting
            # Use temporary file and atomic rename for safety
            temp_path = config_path.with_suffix(".tmp")

            # Load existing file if it exists (preserves comments/formatting)
            if config_path.exists():
                with open(config_path) as f:
                    doc = tomlkit.load(f)
                # Update values from config
                config_dict = config.to_dict()
                for key, value in config_dict.items():
                    doc[key] = value
            else:
                # Create new document
                doc = tomlkit.document()
                for key, value in config.to_dict().items():
                    doc[key] = value

            # Write to temp file
            with open(temp_path, "w") as f:
                tomlkit.dump(doc, f)

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
        # Rule 1: Allow self-referential mappings for custom-named VMs (Issue #385)
        # When vm_name == session_name, this is actually unambiguous and correct
        # for custom-named VMs like "amplihack" where the name IS the identifier
        if vm_name == session_name:
            logger.debug(
                f"Self-referential session name (custom-named VM): {vm_name} -> {session_name}"
            )
            # Don't save to config (redundant), but don't raise error either
            return

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
        """Get VM name by session name using hybrid resolution with fallback.

        Resolution priority:
        1. VM cache (fast lookup with 15-minute TTL)
        2. Azure VM tags (source of truth) - checks managed-by=azlin VMs
        2.5. Azure VM tags fallback - checks azlin-session WITHOUT managed-by requirement
        3. Local config file (backward compatibility fallback)

        Args:
            session_name: Session name to look up
            custom_path: Custom config file path (optional)
            resource_group: Optional RG to limit tag search (None = all RGs)

        Returns:
            VM name or None if not found

        Note:
            Priority 2.5 handles VMs with azlin-session tag but missing managed-by=azlin.
            This supports transition scenarios where session tags exist but managed-by
            tags haven't been applied yet.

            Filters out self-referential entries (vm_name == session_name)
            and warns on duplicate session names pointing to different VMs.
        """
        # Priority 1: Check VM cache first (fast path)
        try:
            from azlin.vm_cache import VMCache

            cache = VMCache()
            vm_name = cache.get(session_name)
            if vm_name:
                logger.debug(f"Resolved session '{session_name}' to VM '{vm_name}' via cache")
                return vm_name
        except Exception as e:
            logger.debug(f"Failed to check cache, continuing with tag/config lookup: {e}")

        # Priority 2: Check Azure tags (managed-by=azlin VMs)
        try:
            from azlin.tag_manager import TagManager

            vm_info = TagManager.get_vm_by_session(session_name, resource_group)
            if vm_info:
                logger.debug(
                    f"Resolved session '{session_name}' to VM '{vm_info.name}' via Azure tags"
                )
                # Update cache for future lookups
                try:
                    from azlin.vm_cache import VMCache

                    cache = VMCache()
                    cache.set(session_name, vm_info.name)
                    logger.debug(f"Cached session '{session_name}' -> '{vm_info.name}'")
                except Exception as cache_error:
                    logger.debug(f"Failed to update cache: {cache_error}")
                return vm_info.name
        except Exception as e:
            logger.debug(f"Failed to resolve session via tags, falling back to config: {e}")

        # Priority 2.5: Fallback - Check Azure tags WITHOUT managed-by requirement
        # This handles VMs that have azlin-session tag but not managed-by=azlin
        try:
            from azlin.tag_manager import TagManager

            vm_info = TagManager.find_vm_by_session_tag_fallback(session_name, resource_group)
            if vm_info:
                logger.info(
                    f"Resolved session '{session_name}' to VM '{vm_info.name}' "
                    f"via fallback (azlin-session tag without managed-by)"
                )
                # Update cache for future lookups
                try:
                    from azlin.vm_cache import VMCache

                    cache = VMCache()
                    cache.set(session_name, vm_info.name)
                    logger.debug(f"Cached session '{session_name}' -> '{vm_info.name}'")
                except Exception as cache_error:
                    logger.debug(f"Failed to update cache: {cache_error}")
                return vm_info.name
        except Exception as e:
            logger.debug(f"Fallback tag search failed, continuing to config: {e}")

        # Priority 3: Fall back to local config file
        try:
            config = cls.load_config(custom_path)
            if config.session_names:
                # Track matches for duplicate detection
                matches = []

                # Reverse lookup: find VM name for this session name
                for vm_name, sess_name in config.session_names.items():
                    # Allow self-referential entries (custom-named VMs, Issue #385)
                    # if vm_name == sess_name, it's valid and should match when searching for that session
                    if sess_name == session_name:
                        matches.append(vm_name)

                # Warn on duplicates
                if len(matches) > 1:
                    logger.warning(
                        f"Duplicate session name '{session_name}' maps to multiple VMs: {matches}\n"
                        f"Using first match: {matches[0]}"
                    )
                    vm_name = matches[0]
                elif len(matches) == 1:
                    logger.debug(
                        f"Resolved session '{session_name}' to VM '{matches[0]}' via local config"
                    )
                    vm_name = matches[0]
                else:
                    return None

                # Update cache for future lookups
                try:
                    from azlin.vm_cache import VMCache

                    cache = VMCache()
                    cache.set(session_name, vm_name)
                    logger.debug(f"Cached session '{session_name}' -> '{vm_name}'")
                except Exception as cache_error:
                    logger.debug(f"Failed to update cache: {cache_error}")
                return vm_name

        except ConfigError as e:
            logger.debug(f"Config error while finding resource group: {e}")
            pass
        return None

    @classmethod
    def get_auth_profile(
        cls, profile_name: str = "default", custom_path: str | None = None
    ) -> dict[str, Any] | None:
        """Get authentication profile configuration.

        Args:
            profile_name: Profile name to retrieve
            custom_path: Custom config file path (optional)

        Returns:
            Profile configuration dict or None if not found
        """
        try:
            config_path = cls.get_config_path(custom_path)
            if not config_path.exists():
                return None

            # Load TOML
            with open(config_path, "rb") as f:
                data = tomli.load(f)  # type: ignore[attr-defined]

            auth_config = data.get("auth", {})
            profiles = auth_config.get("profiles", {})
            return profiles.get(profile_name)

        except FileNotFoundError:
            # Config file doesn't exist
            import logging

            logger = logging.getLogger(__name__)
            logger.debug("Config file not found when loading auth profile")
            return None

        except (OSError, PermissionError) as e:
            # File system errors
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to read config file for auth profile: {e}")
            return None

        except Exception as e:
            # TOML parsing errors or unexpected issues
            import logging
            import os

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to load auth profile {profile_name}: {e}")
            if os.getenv("AZLIN_DEV_MODE"):
                logger.error("Auth profile load error details:", exc_info=True)
            return None

    @classmethod
    def set_auth_profile(
        cls, profile_name: str, config: dict[str, Any], custom_path: str | None = None
    ) -> None:
        """Save authentication profile configuration.

        Args:
            profile_name: Profile name
            config: Profile configuration dict
            custom_path: Custom config file path (optional)

        Raises:
            ConfigError: If save fails
        """
        try:
            config_path = (
                cls.get_config_path(custom_path) if custom_path else cls.DEFAULT_CONFIG_FILE
            )

            # Load existing config or create new
            if config_path.exists():
                with open(config_path, "rb") as f:
                    data = tomli.load(f)  # type: ignore[attr-defined]
            else:
                data = {}

            # Ensure auth section exists
            if "auth" not in data:
                data["auth"] = {}
            if "profiles" not in data["auth"]:
                data["auth"]["profiles"] = {}

            # Set profile
            data["auth"]["profiles"][profile_name] = config

            # Save with tomlkit (preserves comments)
            cls.ensure_config_dir()
            temp_path = config_path.with_suffix(".tmp")

            # Convert dict to tomlkit document
            doc = tomlkit.item(data)

            with open(temp_path, "w") as f:
                tomlkit.dump(doc, f)

            # Set secure permissions
            os.chmod(temp_path, 0o600)

            # Atomic rename
            temp_path.replace(config_path)

        except Exception as e:
            raise ConfigError(f"Failed to save auth profile: {e}") from e

    @classmethod
    def delete_auth_profile(cls, profile_name: str, custom_path: str | None = None) -> bool:
        """Delete authentication profile.

        Args:
            profile_name: Profile name to delete
            custom_path: Custom config file path (optional)

        Returns:
            True if profile was deleted, False if not found

        Raises:
            ConfigError: If delete fails
        """
        try:
            config_path = (
                cls.get_config_path(custom_path) if custom_path else cls.DEFAULT_CONFIG_FILE
            )

            if not config_path.exists():
                return False

            # Load config
            with open(config_path, "rb") as f:
                data = tomli.load(f)  # type: ignore[attr-defined]

            auth_config = data.get("auth", {})
            profiles = auth_config.get("profiles", {})

            if profile_name not in profiles:
                return False

            # Delete profile
            del profiles[profile_name]

            # Save with tomlkit (preserves comments)
            temp_path = config_path.with_suffix(".tmp")

            # Convert dict to tomlkit document
            doc = tomlkit.item(data)

            with open(temp_path, "w") as f:
                tomlkit.dump(doc, f)

            os.chmod(temp_path, 0o600)
            temp_path.replace(config_path)

            return True

        except Exception as e:
            raise ConfigError(f"Failed to delete auth profile: {e}") from e

    @classmethod
    def list_auth_profiles(cls, custom_path: str | None = None) -> list[str]:
        """List all authentication profile names.

        Args:
            custom_path: Custom config file path (optional)

        Returns:
            List of profile names
        """
        try:
            config_path = (
                cls.get_config_path(custom_path) if custom_path else cls.DEFAULT_CONFIG_FILE
            )

            if not config_path.exists():
                return []

            # Load config
            with open(config_path, "rb") as f:
                data = tomli.load(f)  # type: ignore[attr-defined]

            auth_config = data.get("auth", {})
            profiles = auth_config.get("profiles", {})

            return list(profiles.keys())

        except FileNotFoundError:
            # Config file doesn't exist - no profiles
            import logging

            logger = logging.getLogger(__name__)
            logger.debug("Config file not found when listing auth profiles")
            return []

        except (OSError, PermissionError) as e:
            # File system errors
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to read config file for auth profiles: {e}")
            return []

        except Exception as e:
            # TOML parsing errors or unexpected issues
            import logging
            import os

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to list auth profiles: {e}")
            if os.getenv("AZLIN_DEV_MODE"):
                logger.error("Auth profile list error details:", exc_info=True)
            return []

    # ============================================================================
    # FIRST-RUN CONFIGURATION WIZARD (Issue #197)
    # ============================================================================

    @classmethod
    def validate_resource_group_name(cls, name: str) -> bool:
        """Validate resource group name format.

        Azure resource group naming rules:
        - 1-90 characters
        - Alphanumeric, underscore, hyphen, period, parentheses
        - Cannot end with period

        Args:
            name: Resource group name to validate

        Returns:
            True if valid

        Raises:
            ConfigError: If name is invalid

        Security:
            - Uses regex whitelist validation
            - Prevents command injection
            - Prevents path traversal
        """
        if not name:
            raise ConfigError("Resource group name cannot be empty")

        if len(name) > 90:
            raise ConfigError(f"Resource group name too long: {len(name)} characters (max 90)")

        # Azure resource group naming rules: alphanumeric, underscore, hyphen, period, parentheses
        # Must not end with period
        if not re.match(r"^[a-zA-Z0-9_\-\.\(\)]+$", name):
            raise ConfigError(
                f"Invalid resource group name: {name}\n"
                "Resource group names must contain only:\n"
                "  - Letters (a-z, A-Z)\n"
                "  - Numbers (0-9)\n"
                "  - Underscores (_)\n"
                "  - Hyphens (-)\n"
                "  - Periods (.)\n"
                "  - Parentheses ()"
            )

        if name.endswith("."):
            raise ConfigError("Resource group name cannot end with a period")

        return True

    @classmethod
    def needs_configuration(cls, custom_path: str | None = None) -> bool:
        """Check if first-run configuration is needed.

        Configuration is needed if:
        - Config file doesn't exist
        - Config file is empty
        - default_resource_group is missing or None

        Args:
            custom_path: Custom config file path (optional)

        Returns:
            True if wizard should run, False if config is complete
        """
        # CRITICAL: Skip wizard in test mode (Issue #279)
        if os.getenv("AZLIN_TEST_MODE") == "true":
            logger.debug("Test mode active, skipping first-run wizard check")
            return False

        try:
            if custom_path:
                config_path = Path(custom_path).expanduser().resolve()
                # Allow checking non-existent paths without validation error
                if not config_path.exists():
                    return True
                config_path = cls._validate_config_path(config_path)
            else:
                config_path = cls.DEFAULT_CONFIG_FILE

            # Config file doesn't exist
            if not config_path.exists():
                logger.debug("Config file does not exist, wizard needed")
                return True

            # Try to load config
            config = cls.load_config(custom_path)

            # Check if resource group is set
            if not config.default_resource_group:
                logger.debug("Resource group not configured, wizard needed")
                return True

            logger.debug("Configuration complete, wizard not needed")
            return False

        except ConfigError as e:
            logger.debug(f"Config error, wizard needed: {e}")
            return True

    @classmethod
    def needs_first_run_setup(cls, custom_path: str | None = None) -> bool:
        """Alias for needs_configuration() for backward compatibility.

        Args:
            custom_path: Custom config file path (optional)

        Returns:
            True if wizard should run, False if config is complete
        """
        return cls.needs_configuration(custom_path)

    @classmethod
    def create_resource_group(cls, name: str, region: str) -> None:
        """Create Azure resource group.

        Args:
            name: Resource group name
            region: Azure region

        Raises:
            ConfigError: If creation fails

        Security:
            - Validates inputs before subprocess call
            - Uses list-based subprocess args (no shell=True)
            - Sanitizes error messages
        """
        # Validate inputs
        cls.validate_resource_group_name(name)

        if region not in COMMON_REGIONS:
            # Allow any region but log warning
            logger.warning(f"Region '{region}' not in common regions list")

        try:
            logger.debug(f"Creating resource group: {name} in {region}")

            # Use list-based args for security (no shell=True)
            result = subprocess.run(
                [
                    "az",
                    "group",
                    "create",
                    "--name",
                    name,
                    "--location",
                    region,
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )

            logger.debug(f"Resource group created successfully: {name}")

        except subprocess.CalledProcessError as e:
            # Sanitize error message (don't expose full command)
            error_msg = e.stderr.strip() if e.stderr else "Unknown error"
            raise ConfigError(f"Failed to create resource group '{name}': {error_msg}") from e
        except subprocess.TimeoutExpired as e:
            raise ConfigError(f"Timeout creating resource group '{name}' (>60s)") from e

    @classmethod
    def prompt_region_selection(cls, current_default: str) -> str:
        """Prompt user to select Azure region.

        Args:
            current_default: Current default region

        Returns:
            Selected region name

        Security:
            - Uses whitelist validation (COMMON_REGIONS)
            - Prevents arbitrary input
        """
        click.echo()
        click.echo(click.style("Configure Default Region", fg="cyan", bold=True))
        click.echo()
        click.echo("Common Azure regions:")

        # Display regions with numbers
        for i, region in enumerate(COMMON_REGIONS, 1):
            default_marker = " [DEFAULT]" if region == current_default else ""
            click.echo(f"  {i}. {region}{default_marker}")

        click.echo()
        click.echo("Enter region name or number from list above")

        while True:
            region_input = click.prompt(
                "Region",
                default=current_default,
                show_default=True,
            )

            # Check if input is a number
            try:
                idx = int(region_input)
                if 1 <= idx <= len(COMMON_REGIONS):
                    selected_region = COMMON_REGIONS[idx - 1]
                    logger.debug(f"Selected region by number: {selected_region}")
                    return selected_region
                click.echo(
                    click.style(
                        f"Invalid number. Please enter 1-{len(COMMON_REGIONS)}",
                        fg="red",
                    )
                )
                continue
            except ValueError:
                # Not a number, treat as region name
                pass

            # Validate region name
            region_lower = region_input.lower().strip()

            # Check if it's in common regions
            if region_lower in COMMON_REGIONS:
                logger.debug(f"Selected region by name: {region_lower}")
                return region_lower

            # Allow any valid-looking region name (alphanumeric only)
            if re.match(r"^[a-z0-9]+$", region_lower):
                click.echo(
                    click.style(
                        f"Warning: '{region_lower}' not in common regions list",
                        fg="yellow",
                    )
                )
                if click.confirm("Use this region anyway?", default=False):
                    logger.debug(f"Selected custom region: {region_lower}")
                    return region_lower
            else:
                click.echo(
                    click.style(
                        f"Invalid region format: {region_input}\n"
                        "Region names must be alphanumeric (e.g., 'eastus', 'westus2')",
                        fg="red",
                    )
                )

    @classmethod
    def prompt_vm_size_selection(cls, current_default: str) -> str:
        """Prompt user to select VM size using tiers.

        Args:
            current_default: Current default VM size

        Returns:
            Selected VM size

        Security:
            - Uses VMSizeTiers whitelist
            - Validates VM size format
        """
        from azlin.vm_size_tiers import VMSizeTiers

        click.echo()
        click.echo(click.style("Configure Default VM Size", fg="cyan", bold=True))
        click.echo()
        click.echo("Select VM size tier:")
        click.echo()

        # Display tier information
        tiers = ["s", "m", "l", "xl"]
        for tier in tiers:
            tier_info = VMSizeTiers.get_tier_info(tier)
            default_marker = ""
            if str(tier_info["size"]) == current_default:
                default_marker = " [CURRENT]"
            elif tier == VMSizeTiers.get_default_tier():
                default_marker = " [DEFAULT]"

            click.echo(f"  {tier}{default_marker}:")
            click.echo(f"    {tier_info['description']}")
            click.echo(f"    Cost: ~${tier_info['monthly_cost']}/month")
            click.echo()

        while True:
            tier_input = click.prompt(
                "VM Size Tier (s/m/l/xl)",
                default=VMSizeTiers.get_default_tier(),
                show_default=True,
            )

            tier_lower = tier_input.lower().strip()

            try:
                vm_size = VMSizeTiers.get_vm_size_from_tier(tier_lower)
                logger.debug(f"Selected VM size: {vm_size} (tier: {tier_lower})")
                return vm_size
            except Exception as e:
                click.echo(click.style(f"Invalid tier: {e}", fg="red"))
                click.echo()

    @classmethod
    def prompt_resource_group_selection(cls, available_groups: list[str]) -> str | None:
        """Prompt user to select or create resource group.

        Args:
            available_groups: List of existing resource group names

        Returns:
            Resource group name or None if user wants to create new

        Raises:
            ConfigError: If validation fails
        """
        click.echo()
        click.echo(click.style("Configure Default Resource Group", fg="cyan", bold=True))
        click.echo()

        if available_groups:
            click.echo("Existing resource groups:")
            for i, rg in enumerate(available_groups[:10], 1):  # Show max 10
                click.echo(f"  {i}. {rg}")

            if len(available_groups) > 10:
                click.echo(f"  ... and {len(available_groups) - 10} more")

            click.echo()
            click.echo("Options:")
            click.echo("  - Enter a number to select existing resource group")
            click.echo("  - Enter a name to create new resource group")
            click.echo()

            choice = click.prompt("Resource Group", type=str)

            # Check if it's a number (selecting existing)
            try:
                idx = int(choice)
                if 1 <= idx <= len(available_groups):
                    selected_rg = available_groups[idx - 1]
                    logger.debug(f"Selected existing resource group: {selected_rg}")
                    return selected_rg
                click.echo(
                    click.style(
                        f"Invalid number. Please enter 1-{len(available_groups)}",
                        fg="red",
                    )
                )
                return cls.prompt_resource_group_selection(available_groups)
            except ValueError:
                # Not a number, treat as new resource group name
                pass

            # Validate new resource group name
            try:
                cls.validate_resource_group_name(choice)
                logger.debug(f"Will create new resource group: {choice}")
                return choice
            except ConfigError as e:
                click.echo(click.style(f"Invalid name: {e}", fg="red"))
                return cls.prompt_resource_group_selection(available_groups)
        else:
            # No existing groups, prompt for new name
            click.echo("No existing resource groups found.")
            click.echo("Please enter a name for new resource group:")
            click.echo()

            while True:
                rg_name = click.prompt("Resource Group Name", type=str)

                try:
                    cls.validate_resource_group_name(rg_name)
                    logger.debug(f"Will create new resource group: {rg_name}")
                    return rg_name
                except ConfigError as e:
                    click.echo(click.style(f"Invalid name: {e}", fg="red"))
                    click.echo()

    @classmethod
    def prompt_configuration_summary(
        cls, resource_group: str | None, region: str, vm_size: str
    ) -> bool:
        """Display configuration summary and request confirmation.

        Args:
            resource_group: Resource group name (None if will be created per-VM)
            region: Azure region
            vm_size: VM size

        Returns:
            True if user confirms, False otherwise
        """
        click.echo()
        click.echo(click.style("=" * 60, fg="cyan"))
        click.echo(click.style("Configuration Summary", fg="cyan", bold=True))
        click.echo(click.style("=" * 60, fg="cyan"))
        click.echo()
        click.echo(
            f"  Resource Group: {click.style(resource_group or 'None', fg='green', bold=True)}"
        )
        click.echo(f"  Region:         {click.style(region, fg='green', bold=True)}")
        click.echo(f"  VM Size:        {click.style(vm_size, fg='green', bold=True)}")
        click.echo()

        # Show what this config will be used for
        click.echo("This configuration will be saved to:")
        click.echo(f"  {cls.DEFAULT_CONFIG_FILE}")
        click.echo()
        click.echo("It will be used as defaults for all azlin commands.")
        click.echo()

        return click.confirm("Save this configuration?", default=True)

    @classmethod
    def save_wizard_config(
        cls, config_data: dict[str, Any], custom_path: str | None = None
    ) -> None:
        """Save wizard configuration data to file.

        Helper method used by tests to save configuration directly.

        Args:
            config_data: Configuration dictionary
            custom_path: Custom config file path (optional)

        Raises:
            ConfigError: If save fails
        """
        config = AzlinConfig.from_dict(config_data)
        cls.save_config(config, custom_path)

    @classmethod
    def format_config_summary(cls, config_data: dict[str, Any]) -> str:
        """Format configuration summary as string.

        Helper method used by tests to format configuration.

        Args:
            config_data: Configuration dictionary

        Returns:
            Formatted summary string
        """
        resource_group = config_data.get("resource_group") or config_data.get(
            "default_resource_group"
        )
        region = config_data.get("region") or config_data.get("default_region")
        vm_size = config_data.get("vm_size") or config_data.get("default_vm_size")

        return f"""Configuration Summary:
  Resource Group: {resource_group}
  Region: {region}
  VM Size: {vm_size}
"""

    @classmethod
    def prompt_confirmation(cls, config_data: dict[str, Any]) -> bool:
        """Prompt user to confirm configuration.

        Helper method used by tests for confirmation prompts.

        Args:
            config_data: Configuration dictionary to confirm

        Returns:
            True if confirmed, False otherwise
        """
        summary = cls.format_config_summary(config_data)
        click.echo()
        click.echo(summary)
        return click.confirm("Save this configuration?", default=True)

    @classmethod
    def validate_region(cls, region: str) -> bool:
        """Validate region format.

        Args:
            region: Region name to validate

        Returns:
            True if valid

        Raises:
            ConfigError: If region is invalid

        Security:
            - Validates alphanumeric format
            - Prevents injection attacks
        """
        if not region:
            raise ConfigError("Region cannot be empty")

        # Azure regions are lowercase alphanumeric
        if not re.match(r"^[a-z0-9]+$", region.lower()):
            raise ConfigError(
                f"Invalid Azure region format: {region}\n"
                "Region names must be alphanumeric (e.g., 'eastus', 'westus2')"
            )

        return True

    @classmethod
    def validate_vm_size(cls, vm_size: str) -> bool:
        """Validate VM size format.

        Args:
            vm_size: VM size to validate

        Returns:
            True if valid

        Raises:
            ConfigError: If VM size is invalid
        """
        if not vm_size:
            raise ConfigError("VM size cannot be empty")

        # Azure VM sizes follow pattern: Standard_X##[a-z]*_v#
        if not re.match(r"^Standard_[A-Z]\d+[a-z]*_v\d+$", vm_size):
            raise ConfigError(
                f"Invalid VM size format: {vm_size}\n"
                "VM size must match Azure format (e.g., 'Standard_E16as_v5')"
            )

        return True

    @classmethod
    def prompt_resource_group_setup(cls, custom_path: str | None = None) -> dict[str, Any]:
        """Prompt for resource group setup.

        Helper method used by tests for resource group prompts.

        Args:
            custom_path: Custom config file path (optional)

        Returns:
            Dictionary with action and resource_group_name keys
        """
        # Try to list existing resource groups
        available_groups: list[str] = []
        try:
            result = subprocess.run(
                [get_az_command(), "group", "list", "--query", "[].name", "-o", "tsv"],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            available_groups = [
                line.strip() for line in result.stdout.strip().split("\n") if line.strip()
            ]
        except Exception as e:
            logger.debug(f"Failed to list resource groups: {e}")
            pass

        resource_group = cls.prompt_resource_group_selection(available_groups)

        # Determine action
        if resource_group in available_groups:
            return {"action": "use_existing", "resource_group_name": resource_group}
        return {"action": "create_new", "resource_group_name": resource_group}

    @classmethod
    def prompt_region_setup(cls, custom_path: str | None = None) -> dict[str, Any]:
        """Prompt for region setup.

        Helper method used by tests for region prompts.

        Args:
            custom_path: Custom config file path (optional)

        Returns:
            Dictionary with region and available_regions keys
        """
        try:
            config = cls.load_config(custom_path)
            current_default = config.default_region
        except ConfigError:
            current_default = "westus2"

        region = cls.prompt_region_selection(current_default)

        return {"region": region, "available_regions": COMMON_REGIONS}

    @classmethod
    def prompt_vm_size_setup(cls, custom_path: str | None = None) -> dict[str, Any]:
        """Prompt for VM size setup.

        Helper method used by tests for VM size prompts.

        Args:
            custom_path: Custom config file path (optional)

        Returns:
            Dictionary with tier, vm_size, and pricing_info keys
        """
        from azlin.vm_size_tiers import VMSizeTiers

        try:
            config = cls.load_config(custom_path)
            current_default = config.default_vm_size
        except ConfigError:
            current_default = "Standard_E16as_v5"

        vm_size = cls.prompt_vm_size_selection(current_default)

        # Determine tier from vm_size
        tier = "l"  # Default
        for tier_key, tier_info in VMSizeTiers.TIER_MAP.items():
            if tier_info["size"] == vm_size:
                tier = tier_key
                break

        # Get pricing info
        try:
            tier_info = VMSizeTiers.get_tier_info(tier)
            pricing_info = {"hourly": float(tier_info["monthly_cost"]) / 730}
        except (KeyError, ValueError, TypeError) as e:
            # Missing or invalid cost data
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(f"Failed to get pricing info for tier {tier}: {e}")
            pricing_info = {"hourly": 0.0}
        except Exception as e:
            # Unexpected errors
            import logging
            import os

            logger = logging.getLogger(__name__)
            logger.warning(f"Unexpected error getting pricing info: {e}")
            if os.getenv("AZLIN_DEV_MODE"):
                logger.error("Pricing info error details:", exc_info=True)
            pricing_info = {"hourly": 0.0}

        return {"tier": tier, "vm_size": vm_size, "pricing_info": pricing_info}

    @classmethod
    def run_first_run_wizard(
        cls, custom_path: str | None = None, return_dict: bool = False
    ) -> dict[str, Any] | AzlinConfig:
        """Run first-run configuration wizard.

        Interactive wizard that prompts for:
        1. Resource group (select existing or create new)
        2. Default region
        3. Default VM size (tier-based)
        4. Summary and confirmation

        Args:
            custom_path: Custom config file path (optional)
            return_dict: If True, return dict format (for tests), else return AzlinConfig

        Returns:
            Dictionary with success/config/cancelled keys (if return_dict=True)
            or AzlinConfig object (if return_dict=False)

        Raises:
            ConfigError: If wizard fails or user cancels
            KeyboardInterrupt: If user presses Ctrl+C

        Security:
            - All inputs validated before use
            - No shell=True in subprocess calls
            - Config file created with 0600 permissions
        """
        try:
            # Display welcome message
            click.echo()
            click.echo(click.style("=" * 60, fg="cyan", bold=True))
            click.echo(click.style("Welcome to azlin - First-Run Setup", fg="cyan", bold=True))
            click.echo(click.style("=" * 60, fg="cyan", bold=True))
            click.echo()
            click.echo("Let's configure your default settings for VM provisioning.")
            click.echo()

            # Load existing config or create new
            try:
                config = cls.load_config(custom_path)
                click.echo(click.style("Found existing config, updating...", fg="yellow"))
            except ConfigError:
                config = AzlinConfig()
                click.echo(click.style("Creating new configuration...", fg="green"))

            # STEP 1: Resource Group Selection
            available_groups: list[str] = []
            try:
                # Try to list existing resource groups
                result = subprocess.run(
                    [get_az_command(), "group", "list", "--query", "[].name", "-o", "tsv"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30,
                )
                available_groups = [
                    line.strip() for line in result.stdout.strip().split("\n") if line.strip()
                ]
                logger.debug(f"Found {len(available_groups)} existing resource groups")
            except Exception as e:
                logger.debug(f"Could not list resource groups: {e}")
                click.echo(
                    click.style(
                        "Note: Could not list existing resource groups. You can create a new one.",
                        fg="yellow",
                    )
                )

            resource_group = cls.prompt_resource_group_selection(available_groups)

            # Check if user provided a resource group
            if resource_group is None:
                raise ConfigError("Resource group is required for azlin configuration")

            # Check if resource group exists, if not create it
            if resource_group not in available_groups:
                # Need to select region first to create resource group
                temp_region = cls.prompt_region_selection(config.default_region)

                click.echo()
                click.echo(f"Resource group '{resource_group}' does not exist. Creating...")

                try:
                    cls.create_resource_group(resource_group, temp_region)
                    click.echo(
                        click.style(
                            f"Resource group '{resource_group}' created successfully!",
                            fg="green",
                        )
                    )
                    # Use the region we just created the RG in
                    region = temp_region
                except ConfigError as e:
                    click.echo(click.style(f"Error: {e}", fg="red"))
                    raise ConfigError(f"Failed to create resource group: {e}") from e
            else:
                # Resource group exists, prompt for region
                region = cls.prompt_region_selection(config.default_region)

            # STEP 2: VM Size Selection
            vm_size = cls.prompt_vm_size_selection(config.default_vm_size)

            # STEP 3: Summary and Confirmation
            confirmed = cls.prompt_configuration_summary(resource_group, region, vm_size)

            if not confirmed:
                click.echo()
                click.echo(click.style("Configuration cancelled.", fg="yellow"))
                raise ConfigError("User cancelled configuration")

            # STEP 4: Save Configuration
            config.default_resource_group = resource_group
            config.default_region = region
            config.default_vm_size = vm_size

            try:
                cls.save_config(config, custom_path)
            except Exception as e:
                logger.error(f"Failed to save configuration: {e}")
                raise ConfigError(f"Failed to save configuration: {e}") from e

            click.echo()
            click.echo(click.style("Configuration saved successfully!", fg="green", bold=True))
            click.echo()
            click.echo(f"Config file: {custom_path if custom_path else cls.DEFAULT_CONFIG_FILE}")
            click.echo()
            click.echo("You can now use azlin commands with these defaults.")
            click.echo("Run 'azlin new' to create your first VM!")
            click.echo()

            # Return format depends on caller
            if return_dict:
                return {
                    "success": True,
                    "config": {
                        "default_resource_group": resource_group,
                        "default_region": region,
                        "default_vm_size": vm_size,
                    },
                }
            return config

        except KeyboardInterrupt:
            click.echo()
            click.echo()
            click.echo(click.style("Configuration cancelled by user.", fg="yellow"))
            if return_dict:
                return {"success": False, "cancelled": True}
            raise ConfigError("User cancelled configuration") from None
        except ConfigError as e:
            # If user cancelled, return appropriate format
            if "cancelled" in str(e).lower() and return_dict:
                return {"success": False, "cancelled": True}
            raise


__all__ = ["AzlinConfig", "ConfigError", "ConfigManager", "get_default_notification_command"]
