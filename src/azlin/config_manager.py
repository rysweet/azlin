"""Configuration management module.

This module handles persistent configuration storage using TOML format.
Stores user preferences like default resource group, region, and VM size.

Security:
- Config file permissions: 0600 (owner read/write only)
- Path validation
- Input sanitization
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

try:
    import tomli
    import tomli_w
except ImportError:
    # Fallback for older Python versions
    try:
        import tomllib as tomli
        import tomli_w
    except ImportError:
        raise ImportError("toml library not available. Install with: pip install tomli tomli-w")

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when configuration operations fail."""
    pass


@dataclass
class AzlinConfig:
    """Azlin configuration data."""
    default_resource_group: Optional[str] = None
    default_region: str = "eastus"
    default_vm_size: str = "Standard_D2s_v3"
    last_vm_name: Optional[str] = None
    notification_command: str = "imessR"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AzlinConfig':
        """Create from dictionary."""
        return cls(
            default_resource_group=data.get('default_resource_group'),
            default_region=data.get('default_region', 'eastus'),
            default_vm_size=data.get('default_vm_size', 'Standard_D2s_v3'),
            last_vm_name=data.get('last_vm_name'),
            notification_command=data.get('notification_command', 'imessR')
        )


class ConfigManager:
    """Manage azlin configuration file.

    Configuration is stored at ~/.azlin/config.toml with secure permissions.
    """

    DEFAULT_CONFIG_DIR = Path.home() / ".azlin"
    DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.toml"

    @classmethod
    def get_config_path(cls, custom_path: Optional[str] = None) -> Path:
        """Get configuration file path.

        Args:
            custom_path: Custom config file path (optional)

        Returns:
            Path to config file
        """
        if custom_path:
            path = Path(custom_path).expanduser().resolve()
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
            raise ConfigError(f"Failed to create config directory: {e}")

    @classmethod
    def load_config(cls, custom_path: Optional[str] = None) -> AzlinConfig:
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
                    f"Config file has insecure permissions: {oct(mode)}. "
                    "Fixing to 0600..."
                )
                os.chmod(config_path, 0o600)

            # Load TOML
            with open(config_path, 'rb') as f:
                data = tomli.load(f)

            logger.debug(f"Loaded config from: {config_path}")
            return AzlinConfig.from_dict(data)

        except Exception as e:
            raise ConfigError(f"Failed to load config: {e}")

    @classmethod
    def save_config(
        cls,
        config: AzlinConfig,
        custom_path: Optional[str] = None
    ) -> None:
        """Save configuration to file.

        Args:
            config: Configuration to save
            custom_path: Custom config file path (optional)

        Raises:
            ConfigError: If saving fails
        """
        try:
            # Ensure directory exists
            cls.ensure_config_dir()

            config_path = cls.get_config_path(custom_path) if custom_path else cls.DEFAULT_CONFIG_FILE

            # Write TOML with secure permissions
            # Use temporary file and atomic rename for safety
            temp_path = config_path.with_suffix('.tmp')

            with open(temp_path, 'wb') as f:
                tomli_w.dump(config.to_dict(), f)

            # Set secure permissions before moving
            os.chmod(temp_path, 0o600)

            # Atomic rename
            temp_path.replace(config_path)

            logger.debug(f"Saved config to: {config_path}")

        except Exception as e:
            # Cleanup temp file on error
            if temp_path.exists():
                temp_path.unlink()
            raise ConfigError(f"Failed to save config: {e}")

    @classmethod
    def update_config(
        cls,
        custom_path: Optional[str] = None,
        **updates: Any
    ) -> AzlinConfig:
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
        cls,
        cli_value: Optional[str] = None,
        custom_path: Optional[str] = None
    ) -> Optional[str]:
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
    def get_region(
        cls,
        cli_value: Optional[str] = None,
        custom_path: Optional[str] = None
    ) -> str:
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
    def get_vm_size(
        cls,
        cli_value: Optional[str] = None,
        custom_path: Optional[str] = None
    ) -> str:
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


__all__ = ['ConfigManager', 'AzlinConfig', 'ConfigError']
