"""Configuration for retry logic.

This module provides configurable retry settings that can be tuned
for different environments and use cases.

Design Philosophy:
- Ruthless simplicity: Single configuration file
- Sensible defaults: Works out of the box
- Environment-aware: Can be overridden via env vars
"""

import os
from dataclasses import dataclass


@dataclass
class RetryConfig:
    """Retry configuration settings.

    These settings control retry behavior across azlin operations.
    """

    # Azure CLI operations
    azure_cli_max_attempts: int = 3
    azure_cli_initial_delay: float = 1.0
    azure_cli_max_delay: float = 30.0

    # SSH operations
    ssh_max_attempts: int = 3
    ssh_initial_delay: float = 2.0
    ssh_max_delay: float = 10.0

    # Remote command execution
    remote_command_max_attempts: int = 3
    remote_command_initial_delay: float = 1.0
    remote_command_max_delay: float = 30.0

    # Global settings
    jitter_enabled: bool = True

    @classmethod
    def from_environment(cls) -> "RetryConfig":
        """Load retry configuration from environment variables.

        Environment variables (all optional):
            AZLIN_RETRY_MAX_ATTEMPTS: Default max attempts (default: 3)
            AZLIN_RETRY_INITIAL_DELAY: Default initial delay in seconds (default: 1.0)
            AZLIN_RETRY_MAX_DELAY: Default max delay in seconds (default: 30.0)
            AZLIN_RETRY_JITTER_ENABLED: Enable jitter (default: true)

        Returns:
            RetryConfig with values from environment or defaults
        """
        # Get global defaults from environment
        default_max_attempts = int(os.getenv("AZLIN_RETRY_MAX_ATTEMPTS", "3"))
        default_initial_delay = float(os.getenv("AZLIN_RETRY_INITIAL_DELAY", "1.0"))
        default_max_delay = float(os.getenv("AZLIN_RETRY_MAX_DELAY", "30.0"))
        jitter_enabled = os.getenv("AZLIN_RETRY_JITTER_ENABLED", "true").lower() == "true"

        return cls(
            azure_cli_max_attempts=int(
                os.getenv("AZLIN_RETRY_AZURE_CLI_MAX_ATTEMPTS", str(default_max_attempts))
            ),
            azure_cli_initial_delay=float(
                os.getenv("AZLIN_RETRY_AZURE_CLI_INITIAL_DELAY", str(default_initial_delay))
            ),
            azure_cli_max_delay=float(
                os.getenv("AZLIN_RETRY_AZURE_CLI_MAX_DELAY", str(default_max_delay))
            ),
            ssh_max_attempts=int(
                os.getenv("AZLIN_RETRY_SSH_MAX_ATTEMPTS", str(default_max_attempts))
            ),
            ssh_initial_delay=float(
                os.getenv("AZLIN_RETRY_SSH_INITIAL_DELAY", "2.0")
            ),
            ssh_max_delay=float(os.getenv("AZLIN_RETRY_SSH_MAX_DELAY", "10.0")),
            remote_command_max_attempts=int(
                os.getenv("AZLIN_RETRY_REMOTE_COMMAND_MAX_ATTEMPTS", str(default_max_attempts))
            ),
            remote_command_initial_delay=float(
                os.getenv(
                    "AZLIN_RETRY_REMOTE_COMMAND_INITIAL_DELAY", str(default_initial_delay)
                )
            ),
            remote_command_max_delay=float(
                os.getenv("AZLIN_RETRY_REMOTE_COMMAND_MAX_DELAY", str(default_max_delay))
            ),
            jitter_enabled=jitter_enabled,
        )


# Global configuration instance (lazily loaded)
_config: RetryConfig | None = None


def get_retry_config() -> RetryConfig:
    """Get global retry configuration.

    Returns:
        RetryConfig instance (loaded from environment on first access)

    Example:
        >>> config = get_retry_config()
        >>> print(f"Max attempts: {config.azure_cli_max_attempts}")
    """
    global _config
    if _config is None:
        _config = RetryConfig.from_environment()
    return _config


def reset_retry_config() -> None:
    """Reset global retry configuration.

    Forces reload from environment on next access.
    Useful for testing or runtime configuration changes.
    """
    global _config
    _config = None


__all__ = ["RetryConfig", "get_retry_config", "reset_retry_config"]
