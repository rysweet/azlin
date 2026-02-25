"""Lifecycle Manager - Configuration and daemon lifecycle management.

Philosophy:
- Ruthless simplicity: TOML config, basic CRUD
- Single responsibility: Configuration management only
- Standard library: No external deps except tomlkit
- Self-contained: Complete with validation

Public API (Studs):
    LifecycleManager - Main configuration manager
    MonitoringConfig - VM monitoring configuration
    MonitoringStatus - Current monitoring status
    LifecycleConfigError - Configuration errors
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

try:
    import tomlkit
except ImportError as e:
    raise ImportError("tomlkit library required. Install with: pip install tomlkit") from e

logger = logging.getLogger(__name__)

# Configuration file path
LIFECYCLE_CONFIG_PATH = Path.home() / ".azlin" / "lifecycle-config.toml"

# Valid restart policies
VALID_RESTART_POLICIES = ["never", "on-failure", "always"]

# Valid hook types
VALID_HOOK_TYPES = [
    "on_start",
    "on_stop",
    "on_failure",
    "on_restart",
    "on_destroy",
    "on_healthy",
]


class LifecycleConfigError(Exception):
    """Raised when lifecycle configuration operations fail."""

    pass


@dataclass
class MonitoringConfig:
    """VM monitoring configuration."""

    enabled: bool
    check_interval_seconds: int = 60
    restart_policy: str = "never"
    ssh_failure_threshold: int = 3
    health_check_timeout: int = 30
    hooks: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.restart_policy not in VALID_RESTART_POLICIES:
            raise LifecycleConfigError(
                f"Invalid restart policy: {self.restart_policy}. "
                f"Must be one of: {', '.join(VALID_RESTART_POLICIES)}"
            )
        if self.check_interval_seconds < 1:
            raise LifecycleConfigError("check_interval_seconds must be >= 1")
        if self.ssh_failure_threshold < 1:
            raise LifecycleConfigError("ssh_failure_threshold must be >= 1")
        if self.health_check_timeout < 1:
            raise LifecycleConfigError("health_check_timeout must be >= 1")


@dataclass
class MonitoringStatus:
    """Current monitoring status for a VM."""

    vm_name: str
    enabled: bool
    config: MonitoringConfig
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))


class LifecycleManager:
    """Manages VM lifecycle monitoring configuration.

    Handles CRUD operations for VM monitoring configuration stored in TOML.

    Example:
        >>> manager = LifecycleManager()
        >>> config = MonitoringConfig(enabled=True, restart_policy="on-failure")
        >>> manager.enable_monitoring("my-vm", config)
        >>> status = manager.get_monitoring_status("my-vm")
        >>> print(status.config.restart_policy)
        on-failure
    """

    def __init__(self, config_path: Path | None = None):
        """Initialize lifecycle manager.

        Args:
            config_path: Path to config file (default: ~/.azlin/lifecycle-config.toml)
        """
        self.config_path = config_path or LIFECYCLE_CONFIG_PATH
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize config file if it doesn't exist
        if not self.config_path.exists():
            self._create_default_config()

    def _create_default_config(self) -> None:
        """Create default configuration file."""
        default_config = {
            "vms": {},
            "daemon": {
                "pid_file": str(Path.home() / ".azlin" / "lifecycle-daemon.pid"),
                "log_file": str(Path.home() / ".azlin" / "lifecycle-daemon.log"),
                "log_level": "INFO",
            },
        }
        self._write_config(default_config)
        logger.info(f"Created default lifecycle config at {self.config_path}")

    def _read_config(self) -> dict:
        """Read configuration from TOML file."""
        try:
            with open(self.config_path) as f:
                return tomlkit.load(f)
        except Exception as e:
            raise LifecycleConfigError(f"Failed to read config: {e}") from e

    def _write_config(self, config: dict) -> None:
        """Write configuration to TOML file."""
        try:
            with open(self.config_path, "w") as f:
                tomlkit.dump(config, f)
            # Secure permissions (owner read/write only)
            self.config_path.chmod(0o600)
        except Exception as e:
            raise LifecycleConfigError(f"Failed to write config: {e}") from e

    def enable_monitoring(self, vm_name: str, config: MonitoringConfig) -> None:
        """Enable monitoring for a VM.

        Args:
            vm_name: VM name
            config: Monitoring configuration

        Raises:
            LifecycleConfigError: If configuration is invalid
        """
        full_config = self._read_config()

        if "vms" not in full_config:
            full_config["vms"] = {}

        # Convert config to dict
        vm_config = {
            "enabled": config.enabled,
            "check_interval_seconds": config.check_interval_seconds,
            "restart_policy": config.restart_policy,
            "ssh_failure_threshold": config.ssh_failure_threshold,
            "health_check_timeout": config.health_check_timeout,
            "hooks": config.hooks or {},
        }

        full_config["vms"][vm_name] = vm_config
        self._write_config(full_config)
        logger.info(f"Enabled monitoring for {vm_name}")

    def disable_monitoring(self, vm_name: str) -> None:
        """Disable monitoring for a VM.

        Args:
            vm_name: VM name

        Raises:
            LifecycleConfigError: If VM not found
        """
        full_config = self._read_config()

        if vm_name not in full_config.get("vms", {}):
            raise LifecycleConfigError(f"VM {vm_name} not configured for monitoring")

        del full_config["vms"][vm_name]
        self._write_config(full_config)
        logger.info(f"Disabled monitoring for {vm_name}")

    def get_monitoring_status(self, vm_name: str) -> MonitoringStatus:
        """Get monitoring status for a VM.

        Args:
            vm_name: VM name

        Returns:
            MonitoringStatus with current configuration

        Raises:
            LifecycleConfigError: If VM not configured
        """
        full_config = self._read_config()

        if vm_name not in full_config.get("vms", {}):
            raise LifecycleConfigError(f"VM {vm_name} not configured for monitoring")

        vm_config_dict = full_config["vms"][vm_name]

        # Reconstruct MonitoringConfig
        config = MonitoringConfig(
            enabled=vm_config_dict["enabled"],
            check_interval_seconds=vm_config_dict.get("check_interval_seconds", 60),
            restart_policy=vm_config_dict.get("restart_policy", "never"),
            ssh_failure_threshold=vm_config_dict.get("ssh_failure_threshold", 3),
            health_check_timeout=vm_config_dict.get("health_check_timeout", 30),
            hooks=vm_config_dict.get("hooks", {}),
        )

        return MonitoringStatus(
            vm_name=vm_name,
            enabled=config.enabled,
            config=config,
        )

    def update_config(self, vm_name: str, config: MonitoringConfig) -> None:
        """Update configuration for a VM.

        Args:
            vm_name: VM name
            config: New monitoring configuration

        Raises:
            LifecycleConfigError: If VM not configured
        """
        # Verify VM exists
        self.get_monitoring_status(vm_name)

        # Update is same as enable
        self.enable_monitoring(vm_name, config)
        logger.info(f"Updated configuration for {vm_name}")

    def list_monitored_vms(self) -> list[str]:
        """List all VMs with monitoring configured.

        Returns:
            List of VM names
        """
        full_config = self._read_config()
        return list(full_config.get("vms", {}).keys())

    def set_hook(self, vm_name: str, hook_type: str, script_path: str) -> None:
        """Set a lifecycle hook for a VM.

        Args:
            vm_name: VM name
            hook_type: Hook type (on_start, on_stop, etc.)
            script_path: Path to hook script

        Raises:
            LifecycleConfigError: If VM not configured or invalid hook type
        """
        if hook_type not in VALID_HOOK_TYPES:
            raise LifecycleConfigError(
                f"Invalid hook type: {hook_type}. Must be one of: {', '.join(VALID_HOOK_TYPES)}"
            )

        status = self.get_monitoring_status(vm_name)
        status.config.hooks[hook_type] = script_path
        self.update_config(vm_name, status.config)
        logger.info(f"Set {hook_type} hook for {vm_name}: {script_path}")

    def clear_hook(self, vm_name: str, hook_type: str) -> None:
        """Clear a lifecycle hook for a VM.

        Args:
            vm_name: VM name
            hook_type: Hook type to clear

        Raises:
            LifecycleConfigError: If VM not configured
        """
        status = self.get_monitoring_status(vm_name)
        status.config.hooks[hook_type] = ""
        self.update_config(vm_name, status.config)
        logger.info(f"Cleared {hook_type} hook for {vm_name}")


__all__ = [
    "LIFECYCLE_CONFIG_PATH",
    "VALID_HOOK_TYPES",
    "VALID_RESTART_POLICIES",
    "LifecycleConfigError",
    "LifecycleManager",
    "MonitoringConfig",
    "MonitoringStatus",
]
