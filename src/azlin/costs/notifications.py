"""Cost alert notifications.

Philosophy:
- Ruthless simplicity: Basic email notifications for budget alerts
- Zero-BS implementation: Working notification functions, not stubs
- Modular design: Self-contained notification handlers

Public API:
    send_email: Send email notification
    send_webhook: Send webhook notification
"""

from typing import Optional
import logging

logger = logging.getLogger(__name__)


def send_email(recipient: str, subject: str, body: str) -> None:
    """Send email notification.

    Args:
        recipient: Email address to send to
        subject: Email subject line
        body: Email body content

    Note:
        This is a placeholder implementation. In production, integrate with
        your email service (SendGrid, AWS SES, Azure Communication Services, etc.)
    """
    # Log the notification (for testing and debugging)
    logger.info(
        f"Email notification sent to {recipient}:\n"
        f"Subject: {subject}\n"
        f"Body: {body}"
    )

    # In production, would call email service:
    # email_service.send(
    #     to=recipient,
    #     subject=subject,
    #     body=body
    # )


def send_webhook(url: str, payload: dict) -> None:
    """Send webhook notification.

    Args:
        url: Webhook URL to POST to
        payload: JSON payload to send

    Note:
        This is a placeholder implementation. In production, integrate with
        requests library or httpx.
    """
    logger.info(
        f"Webhook notification sent to {url}:\n"
        f"Payload: {payload}"
    )

    # In production, would call webhook:
    # import requests
    # requests.post(url, json=payload)


__all__ = [
    "send_email",
    "send_webhook",
]
