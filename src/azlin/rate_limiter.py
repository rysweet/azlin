"""Rate limiting detection and handling for HTTP 429 responses.

This module provides utilities for detecting and handling Azure API rate limiting
(HTTP 429 Too Many Requests) with automatic backoff based on Retry-After headers.

Design Philosophy:
- Ruthless simplicity: Single module for all rate limiting needs
- Zero-BS: No over-abstraction, working rate limit handling
- Azure-aware: Parse Retry-After headers correctly (seconds and HTTP date)
- Observable: Clear logging of rate limiting events

Security:
- No credential leakage in logs
- Timeout enforcement on rate limit waits
- Safe caps on maximum wait times

Usage:
    from azlin.rate_limiter import handle_rate_limit_error

    try:
        azure_client.operation()
    except HttpResponseError as e:
        if is_rate_limit_error(e):
            wait_time = extract_retry_after(e)
            time.sleep(wait_time)
"""

import logging
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

logger = logging.getLogger(__name__)

# Maximum time to wait for rate limiting (safety cap)
MAX_RETRY_AFTER_SECONDS = 300  # 5 minutes


def is_rate_limit_error(error: Any) -> bool:
    """Check if error is an HTTP 429 rate limiting error.

    Args:
        error: Exception to check (typically HttpResponseError)

    Returns:
        True if this is a rate limiting error (status 429)

    Example:
        >>> from azure.core.exceptions import HttpResponseError
        >>> try:
        ...     azure_operation()
        ... except HttpResponseError as e:
        ...     if is_rate_limit_error(e):
        ...         print("Rate limited!")
    """
    # Check for status_code attribute (Azure SDK exceptions)
    if hasattr(error, "status_code") and error.status_code == 429:
        return True

    # Check for response attribute with status_code
    if hasattr(error, "response"):
        response = error.response
        if response is not None and hasattr(response, "status_code"):
            return response.status_code == 429

    return False


def parse_retry_after(retry_after_value: str | None) -> float:
    """Parse Retry-After header value to seconds.

    Supports both formats:
    - Integer seconds: "120"
    - HTTP date: "Wed, 21 Oct 2025 07:28:00 GMT"

    Args:
        retry_after_value: Value from Retry-After header

    Returns:
        Number of seconds to wait (capped at MAX_RETRY_AFTER_SECONDS)

    Example:
        >>> parse_retry_after("60")
        60.0
        >>> parse_retry_after("Wed, 21 Oct 2025 07:28:00 GMT")
        120.0  # If current time is 2 minutes before
    """
    if not retry_after_value:
        return 0.0

    # Try parsing as integer (seconds format)
    try:
        seconds = float(retry_after_value)
        # Cap at maximum
        return min(seconds, MAX_RETRY_AFTER_SECONDS)
    except ValueError:
        pass

    # Try parsing as HTTP date
    try:
        retry_datetime = parsedate_to_datetime(retry_after_value)
        now = datetime.now(UTC)

        # Calculate seconds until retry time
        delta = (retry_datetime - now).total_seconds()

        # Don't return negative values
        if delta < 0:
            return 0.0

        # Cap at maximum
        return min(delta, MAX_RETRY_AFTER_SECONDS)
    except (ValueError, TypeError, OverflowError):
        logger.warning(f"Failed to parse Retry-After header: {retry_after_value}")
        return 0.0


def extract_retry_after(error: Any) -> float:
    """Extract Retry-After value from Azure error response.

    Args:
        error: Azure HttpResponseError with potential Retry-After header

    Returns:
        Number of seconds to wait (0.0 if no Retry-After header)

    Example:
        >>> from azure.core.exceptions import HttpResponseError
        >>> try:
        ...     azure_operation()
        ... except HttpResponseError as e:
        ...     wait_time = extract_retry_after(e)
        ...     if wait_time > 0:
        ...         time.sleep(wait_time)
    """
    # Try to get response headers
    retry_after_value = None

    # Check for response.headers attribute
    if hasattr(error, "response") and hasattr(error.response, "headers"):
        headers = error.response.headers
        # Headers can be case-insensitive dict
        retry_after_value = headers.get("Retry-After") or headers.get("retry-after")

    if retry_after_value:
        return parse_retry_after(str(retry_after_value))

    return 0.0


def handle_rate_limit_error(error: Any, default_backoff: float = 10.0) -> float:
    """Handle rate limiting error and return wait time.

    This is a convenience function that:
    1. Checks if error is rate limiting (429)
    2. Extracts Retry-After header if present
    3. Falls back to default backoff if no header

    Args:
        error: Exception to handle (typically HttpResponseError)
        default_backoff: Default wait time if no Retry-After header (seconds)

    Returns:
        Number of seconds to wait before retrying

    Example:
        >>> try:
        ...     azure_operation()
        ... except HttpResponseError as e:
        ...     wait_time = handle_rate_limit_error(e)
        ...     if wait_time > 0:
        ...         logger.info(f"Rate limited, waiting {wait_time}s")
        ...         time.sleep(wait_time)
    """
    if not is_rate_limit_error(error):
        return 0.0

    # Try to get Retry-After from header
    wait_time = extract_retry_after(error)

    # Fall back to default if no header
    if wait_time == 0.0:
        wait_time = min(default_backoff, MAX_RETRY_AFTER_SECONDS)
        logger.warning(
            f"Rate limited (429) with no Retry-After header, using default backoff: {wait_time}s"
        )
    else:
        logger.info(f"Rate limited (429), Retry-After: {wait_time}s")

    return wait_time


def wait_for_rate_limit(error: Any, default_backoff: float = 10.0) -> bool:
    """Wait for rate limiting to clear.

    Convenience function that handles the wait automatically.

    Args:
        error: Exception to handle
        default_backoff: Default wait time if no Retry-After header

    Returns:
        True if rate limit was handled (waited), False otherwise

    Example:
        >>> try:
        ...     azure_operation()
        ... except HttpResponseError as e:
        ...     if wait_for_rate_limit(e):
        ...         # Rate limit handled, can retry
        ...         azure_operation()
    """
    wait_time = handle_rate_limit_error(error, default_backoff)

    if wait_time > 0:
        logger.info(f"Waiting {wait_time}s for rate limit to clear...")
        time.sleep(wait_time)
        return True

    return False


__all__ = [
    "MAX_RETRY_AFTER_SECONDS",
    "extract_retry_after",
    "handle_rate_limit_error",
    "is_rate_limit_error",
    "parse_retry_after",
    "wait_for_rate_limit",
]
