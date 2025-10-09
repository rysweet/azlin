"""
Notification Handler Module

Send optional imessR notifications on completion.

Security Requirements:
- No credential storage
- Safe subprocess execution
- Graceful degradation if imessR not available
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class NotificationConfig:
    """Notification configuration."""
    enabled: bool
    message: str
    recipient: Optional[str] = None  # For future use


@dataclass
class NotificationResult:
    """Notification send result."""
    sent: bool
    message: str
    error: Optional[str] = None


class NotificationHandler:
    """
    Send completion notifications via imessR.

    Features:
    - Graceful degradation if imessR not available
    - No errors if disabled
    - Safe subprocess execution
    """

    @classmethod
    def _get_notification_command(cls) -> str:
        """Get notification command from config."""
        try:
            # Import here to avoid circular dependency
            from azlin.config_manager import ConfigManager
            config = ConfigManager.load_config()
            return config.notification_command
        except Exception:
            # Fallback to default if config not available
            return "imessR"

    @classmethod
    def send_notification(
        cls,
        message: str,
        recipient: Optional[str] = None
    ) -> NotificationResult:
        """
        Send notification if imessR available.

        Args:
            message: Notification message
            recipient: Optional recipient (for future use)

        Returns:
            NotificationResult: Send result

        Security:
        - Checks for imessR availability first
        - Uses subprocess with argument list
        - Gracefully handles failures

        Example:
            >>> result = NotificationHandler.send_notification(
            ...     "VM provisioning complete"
            ... )
            >>> if result.sent:
            ...     print("Notification sent")
        """
        # Check if imessR is available
        if not cls.is_imessr_available():
            logger.debug("imessR not available, skipping notification")
            return NotificationResult(
                sent=False,
                message="imessR not available",
                error=None
            )

        # Send notification
        try:
            notification_cmd = cls._get_notification_command()
            logger.debug(f"Sending notification via {notification_cmd}: {message}")

            # Build command
            args = [notification_cmd, message]

            # Execute notification command
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=10,
                check=True
            )

            logger.info("Notification sent successfully")

            return NotificationResult(
                sent=True,
                message=message,
                error=None
            )

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            logger.warning(f"Failed to send notification: {error_msg}")

            return NotificationResult(
                sent=False,
                message=message,
                error=error_msg
            )

        except subprocess.TimeoutExpired:
            logger.warning("Notification timed out")

            return NotificationResult(
                sent=False,
                message=message,
                error="Timeout"
            )

        except Exception as e:
            logger.warning(f"Notification failed: {type(e).__name__}: {e}")

            return NotificationResult(
                sent=False,
                message=message,
                error=str(e)
            )

    @classmethod
    def is_imessr_available(cls) -> bool:
        """
        Check if notification command is installed.

        Returns:
            bool: True if notification command is available

        Security: Uses shutil.which (safe)

        Example:
            >>> if NotificationHandler.is_imessr_available():
            ...     print("Notification command is installed")
        """
        notification_cmd = cls._get_notification_command()
        result = shutil.which(notification_cmd)
        available = result is not None

        if available:
            logger.debug(f"{notification_cmd} found at {result}")
        else:
            logger.debug(f"{notification_cmd} not found in PATH")

        return available

    @classmethod
    def send_completion_notification(
        cls,
        vm_name: str,
        vm_ip: str,
        success: bool = True
    ) -> NotificationResult:
        """
        Send VM provisioning completion notification.

        Args:
            vm_name: Name of the VM
            vm_ip: IP address of the VM
            success: Whether provisioning succeeded

        Returns:
            NotificationResult: Send result

        Example:
            >>> NotificationHandler.send_completion_notification(
            ...     "azlin-vm-123",
            ...     "20.12.34.56",
            ...     success=True
            ... )
        """
        if success:
            message = (
                f"azlin: VM {vm_name} ready at {vm_ip}"
            )
        else:
            message = (
                f"azlin: VM {vm_name} provisioning failed"
            )

        return cls.send_notification(message)

    @classmethod
    def send_error_notification(cls, error_message: str) -> NotificationResult:
        """
        Send error notification.

        Args:
            error_message: Error description

        Returns:
            NotificationResult: Send result

        Example:
            >>> NotificationHandler.send_error_notification(
            ...     "VM provisioning failed: quota exceeded"
            ... )
        """
        message = f"azlin error: {error_message}"
        return cls.send_notification(message)


# Convenience functions for CLI use
def notify(message: str) -> bool:
    """
    Send notification (convenience function).

    Args:
        message: Notification message

    Returns:
        bool: True if sent successfully

    Example:
        >>> from azlin.modules.notifications import notify
        >>> if notify("VM is ready"):
        ...     print("Notification sent")
    """
    result = NotificationHandler.send_notification(message)
    return result.sent


def notify_completion(vm_name: str, vm_ip: str) -> bool:
    """
    Send completion notification (convenience function).

    Args:
        vm_name: VM name
        vm_ip: VM IP address

    Returns:
        bool: True if sent successfully

    Example:
        >>> from azlin.modules.notifications import notify_completion
        >>> notify_completion("my-vm", "20.12.34.56")
    """
    result = NotificationHandler.send_completion_notification(
        vm_name, vm_ip, success=True
    )
    return result.sent


def notify_error(error_message: str) -> bool:
    """
    Send error notification (convenience function).

    Args:
        error_message: Error message

    Returns:
        bool: True if sent successfully

    Example:
        >>> from azlin.modules.notifications import notify_error
        >>> notify_error("Provisioning failed")
    """
    result = NotificationHandler.send_error_notification(error_message)
    return result.sent


def is_notification_available() -> bool:
    """
    Check if notifications are available (convenience function).

    Returns:
        bool: True if imessR is available

    Example:
        >>> from azlin.modules.notifications import is_notification_available
        >>> if is_notification_available():
        ...     print("Notifications enabled")
    """
    return NotificationHandler.is_imessr_available()
