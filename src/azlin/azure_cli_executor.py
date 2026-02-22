"""Standardized Azure CLI subprocess execution with retry logic.

Provides run_az_command() — a thin wrapper around subprocess.run that adds
automatic retry with exponential backoff for transient Azure CLI failures
(CalledProcessError, TimeoutExpired). Uses the existing retry_handler
infrastructure so retry behavior is consistent across the codebase.

Usage:
    from azlin.azure_cli_executor import run_az_command

    # Drop-in replacement for subprocess.run(["az", ...], ...)
    result = run_az_command(["az", "vm", "list", "--output", "json"])

    # With custom timeout and retry attempts
    result = run_az_command(["az", "vm", "create", ...], timeout=300, max_attempts=5)
"""

import logging
import subprocess

from azlin.retry_config import get_retry_config
from azlin.retry_handler import retry_with_exponential_backoff

logger = logging.getLogger(__name__)


def run_az_command(
    cmd: list[str],
    *,
    timeout: int = 30,
    max_attempts: int | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Execute an Azure CLI command with retry logic.

    Drop-in replacement for subprocess.run(["az", ...]) that adds automatic
    retry with exponential backoff on transient failures.

    Args:
        cmd: Command list starting with "az", e.g. ["az", "vm", "list"]
        timeout: Subprocess timeout in seconds (default: 30)
        max_attempts: Number of retry attempts (default: from RetryConfig)
        check: If True, raise CalledProcessError on non-zero exit (default: True)

    Returns:
        subprocess.CompletedProcess with stdout/stderr

    Raises:
        subprocess.CalledProcessError: After retries exhausted (when check=True)
        subprocess.TimeoutExpired: After retries exhausted
    """
    config = get_retry_config()
    attempts = max_attempts or config.azure_cli_max_attempts

    @retry_with_exponential_backoff(
        max_attempts=attempts,
        initial_delay=config.azure_cli_initial_delay,
        max_delay=config.azure_cli_max_delay,
        retryable_exceptions=(subprocess.CalledProcessError, subprocess.TimeoutExpired),
    )
    def _run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)

    return _run()


__all__ = ["run_az_command"]
