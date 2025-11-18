"""Autopilot configuration management.

This module provides configuration data models and persistence for autopilot.

Philosophy:
- File-based configuration (no external dependencies)
- Validation at creation time
- Safe defaults
- Standard library only

Public API:
    AutoPilotConfig: Configuration data model
    ConfigManager: Configuration persistence
    AutoPilotConfigError: Configuration errors
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AutoPilotConfigError(Exception):
    """Raised when configuration operations fail."""

    pass


@dataclass
class AutoPilotConfig:
    """Autopilot configuration.

    Attributes:
        enabled: Whether autopilot is enabled
        budget_monthly: Monthly budget in USD
        strategy: Cost optimization strategy (conservative, balanced, aggressive)
        work_hours: Work hours configuration
        idle_threshold_minutes: Minutes before VM considered idle
        cpu_threshold_percent: CPU threshold for underutilization
        cpu_observation_days: Days to observe before recommending downsize
        notifications: Notification configuration
        protected_tags: Tags that protect VMs from autopilot actions
        last_run: Last time autopilot ran
    """

    enabled: bool
    budget_monthly: int
    strategy: str
    work_hours: dict[str, Any] = field(
        default_factory=lambda: {
            "start": 9,
            "end": 17,
            "days": ["mon", "tue", "wed", "thu", "fri"],
        }
    )
    idle_threshold_minutes: int = 120
    cpu_threshold_percent: int = 20
    cpu_observation_days: int = 3
    notifications: dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": True,
            "channels": ["console"],
        }
    )
    protected_tags: list[str] = field(default_factory=lambda: ["production", "critical"])
    last_run: str | None = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        self._validate()

    def _validate(self) -> None:
        """Validate configuration values."""
        # Budget must be positive
        if self.budget_monthly <= 0:
            raise AutoPilotConfigError(f"Budget must be positive, got: {self.budget_monthly}")

        # Strategy must be valid
        valid_strategies = ["conservative", "balanced", "aggressive"]
        if self.strategy not in valid_strategies:
            raise AutoPilotConfigError(
                f"Invalid strategy: {self.strategy}. Must be one of: {valid_strategies}"
            )

        # Idle threshold must be reasonable (at least 30 minutes)
        if self.idle_threshold_minutes < 30:
            raise AutoPilotConfigError(
                f"Idle threshold must be at least 30 minutes, got: {self.idle_threshold_minutes}"
            )

        # CPU threshold must be 0-100
        if not 0 <= self.cpu_threshold_percent <= 100:
            raise AutoPilotConfigError(
                f"CPU threshold must be 0-100%, got: {self.cpu_threshold_percent}"
            )

        # Observation days must be positive
        if self.cpu_observation_days < 1:
            raise AutoPilotConfigError(
                f"CPU observation days must be at least 1, got: {self.cpu_observation_days}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary.

        Returns:
            Dictionary representation of configuration
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AutoPilotConfig":
        """Create configuration from dictionary.

        Args:
            data: Dictionary with configuration values

        Returns:
            AutoPilotConfig instance

        Raises:
            AutoPilotConfigError: If data is invalid
        """
        try:
            return cls(**data)
        except TypeError as e:
            raise AutoPilotConfigError(f"Invalid configuration data: {e}") from e


class ConfigManager:
    """Manage autopilot configuration persistence.

    This class provides methods for saving, loading, and updating
    autopilot configuration.
    """

    @staticmethod
    def get_default_config_path() -> Path:
        """Get default configuration file path.

        Returns:
            Path to default configuration file (~/.azlin/autopilot.json)
        """
        config_dir = Path.home() / ".azlin"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "autopilot.json"

    @staticmethod
    def save_config(config: AutoPilotConfig, config_path: Path | None = None) -> None:
        """Save configuration to file.

        Args:
            config: Configuration to save
            config_path: Path to save configuration (default: ~/.azlin/autopilot.json)

        Raises:
            AutoPilotConfigError: If save fails
        """
        if config_path is None:
            config_path = ConfigManager.get_default_config_path()

        try:
            # Ensure directory exists
            config_path.parent.mkdir(parents=True, exist_ok=True)

            # Write configuration
            with open(config_path, "w") as f:
                json.dump(config.to_dict(), f, indent=2)

            logger.info(f"Saved autopilot configuration to: {config_path}")

        except (OSError, json.JSONDecodeError) as e:
            raise AutoPilotConfigError(f"Failed to save configuration: {e}") from e

    @staticmethod
    def load_config(config_path: Path | None = None) -> AutoPilotConfig:
        """Load configuration from file.

        Args:
            config_path: Path to configuration file (default: ~/.azlin/autopilot.json)

        Returns:
            Loaded configuration

        Raises:
            AutoPilotConfigError: If load fails or file not found
        """
        if config_path is None:
            config_path = ConfigManager.get_default_config_path()

        if not config_path.exists():
            raise AutoPilotConfigError(
                f"Configuration file not found: {config_path}. "
                "Run 'azlin autopilot enable' to create configuration."
            )

        try:
            with open(config_path) as f:
                data = json.load(f)

            config = AutoPilotConfig.from_dict(data)
            logger.info(f"Loaded autopilot configuration from: {config_path}")
            return config

        except (OSError, json.JSONDecodeError) as e:
            raise AutoPilotConfigError(f"Failed to load configuration: {e}") from e

    @staticmethod
    def update_config(config_path: Path | None, updates: dict[str, Any]) -> AutoPilotConfig:
        """Update configuration with new values.

        Args:
            config_path: Path to configuration file
            updates: Dictionary of values to update

        Returns:
            Updated configuration

        Raises:
            AutoPilotConfigError: If update fails
        """
        # Load existing configuration
        config = ConfigManager.load_config(config_path)

        # Update values
        config_dict = config.to_dict()
        config_dict.update(updates)

        # Create new configuration (validates automatically)
        updated_config = AutoPilotConfig.from_dict(config_dict)

        # Save updated configuration
        ConfigManager.save_config(updated_config, config_path)

        return updated_config

    @staticmethod
    def delete_config(config_path: Path | None = None) -> None:
        """Delete configuration file.

        Args:
            config_path: Path to configuration file (default: ~/.azlin/autopilot.json)

        Raises:
            AutoPilotConfigError: If delete fails
        """
        if config_path is None:
            config_path = ConfigManager.get_default_config_path()

        if not config_path.exists():
            logger.warning(f"Configuration file does not exist: {config_path}")
            return

        try:
            config_path.unlink()
            logger.info(f"Deleted autopilot configuration: {config_path}")

        except OSError as e:
            raise AutoPilotConfigError(f"Failed to delete configuration: {e}") from e


__all__ = ["AutoPilotConfig", "AutoPilotConfigError", "ConfigManager"]
