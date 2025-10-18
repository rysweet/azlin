"""
SSH Reconnect Module

Handles automatic reconnection when SSH sessions disconnect.

Features:
- Detect SSH disconnect vs normal exit
- Prompt user to reconnect
- Configurable retry attempts
- Graceful error handling
"""

import logging

import click

from azlin.modules.ssh_connector import SSHConfig, SSHConnector

logger = logging.getLogger(__name__)


def is_disconnect_exit_code(exit_code: int) -> bool:
    """
    Determine if exit code indicates a disconnect vs normal exit.

    Args:
        exit_code: SSH process exit code

    Returns:
        True if exit code indicates disconnect

    SSH Exit Codes:
    - 0: Normal exit
    - 1: Generic errors (may indicate disconnect)
    - 130: Interrupted by user (Ctrl+C)
    - 255: SSH error (connection lost, network issue, etc.)

    Example:
        >>> is_disconnect_exit_code(255)
        True
        >>> is_disconnect_exit_code(0)
        False
    """
    # Exit codes that indicate potential disconnect
    disconnect_codes = {
        1,  # Generic error that might be disconnect
        255,  # SSH protocol error / connection lost
    }

    return exit_code in disconnect_codes


def should_attempt_reconnect(vm_name: str) -> bool:
    """
    Prompt user whether to reconnect to VM.

    Args:
        vm_name: Name of the VM that disconnected

    Returns:
        True if user wants to reconnect

    Example:
        >>> should_attempt_reconnect("my-vm")
        Your session to my-vm was disconnected, do you want to reconnect? [Y/n]: y
        True
    """
    message = f"Your session to {vm_name} was disconnected, do you want to reconnect?"
    return click.confirm(message, default=True)


class SSHReconnectHandler:
    """
    Handle SSH reconnection with configurable retry logic.

    Features:
    - Automatic reconnection on disconnect
    - User confirmation before reconnect
    - Configurable retry attempts
    - Detection of disconnect vs normal exit

    Example:
        >>> config = SSHConfig(...)
        >>> handler = SSHReconnectHandler(max_retries=3)
        >>> exit_code = handler.connect_with_reconnect(config, vm_name="my-vm")
    """

    def __init__(self, max_retries: int = 3):
        """
        Initialize reconnect handler.

        Args:
            max_retries: Maximum number of reconnection attempts (default: 3)
        """
        self.max_retries = max_retries

    def connect_with_reconnect(
        self, config: SSHConfig, vm_name: str, tmux_session: str = "azlin", auto_tmux: bool = True
    ) -> int:
        """
        Connect to VM with automatic reconnection on disconnect.

        Args:
            config: SSH configuration
            vm_name: VM name (used in prompts)
            tmux_session: tmux session name
            auto_tmux: Automatically start/attach tmux session

        Returns:
            Final SSH exit code

        Example:
            >>> config = SSHConfig(...)
            >>> handler = SSHReconnectHandler()
            >>> exit_code = handler.connect_with_reconnect(config, "my-vm")
        """
        attempt = 0

        while attempt <= self.max_retries:
            # Connect to SSH
            logger.info(
                f"Connecting to {vm_name} (attempt {attempt + 1}/{self.max_retries + 1})..."
            )

            exit_code = SSHConnector.connect(
                config=config, tmux_session=tmux_session, auto_tmux=auto_tmux
            )

            # Check if this was a disconnect
            if not is_disconnect_exit_code(exit_code):
                # Normal exit or user interrupt - don't reconnect
                if exit_code == 0:
                    logger.info("SSH session ended normally")
                elif exit_code == 130:
                    logger.info("SSH session interrupted by user")
                else:
                    logger.warning(f"SSH session ended with code {exit_code}")
                return exit_code

            # This was a disconnect
            logger.warning(f"SSH connection to {vm_name} lost (exit code: {exit_code})")

            # Check if we've exhausted retries
            if attempt >= self.max_retries:
                logger.error(
                    f"Maximum reconnection attempts ({self.max_retries}) reached. Giving up."
                )
                return exit_code

            # Prompt user to reconnect
            if not should_attempt_reconnect(vm_name):
                logger.info("User declined reconnection")
                return exit_code

            # User wants to reconnect
            logger.info(f"Attempting to reconnect to {vm_name}...")
            attempt += 1

        # Should never reach here, but return last exit code just in case
        return exit_code


__all__ = ["SSHReconnectHandler", "is_disconnect_exit_code", "should_attempt_reconnect"]
