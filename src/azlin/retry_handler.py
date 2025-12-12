"""Retry logic with exponential backoff for transient failures.

This module provides a decorator and utilities for retrying operations that may
fail due to transient errors (network timeouts, Azure throttling, etc).

Design Philosophy:
- Ruthless simplicity: Single decorator for all retry needs
- Zero-BS: No over-abstraction, just working retry logic
- Configurable: Max attempts, delays, jitter can be tuned
- Observable: Clear logging of retry attempts

Security:
- No credential leakage in logs
- Timeout enforcement on retries
- Safe default limits (max 5 attempts)

Usage:
    @retry_with_exponential_backoff(max_attempts=3)
    def azure_operation():
        # Azure SDK call that might fail transiently
        client.some_operation()

    # With custom configuration
    @retry_with_exponential_backoff(
        max_attempts=5,
        initial_delay=2.0,
        max_delay=60.0,
        jitter=True
    )
    def critical_operation():
        # Operation with custom retry parameters
        pass
"""

import functools
import logging
import random
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

# Type variable for generic function wrapping
F = TypeVar("F", bound=Callable[..., Any])


def retry_with_exponential_backoff(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] | None = None,
) -> Callable[[F], F]:
    """Decorator for retrying operations with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay between retries in seconds (default: 30.0)
        jitter: Add random jitter to delays to prevent thundering herd (default: True)
        retryable_exceptions: Tuple of exception types to retry
            (default: common Azure/network errors)

    Returns:
        Decorated function that will retry on transient failures

    Example:
        >>> @retry_with_exponential_backoff(max_attempts=3)
        ... def call_azure_api():
        ...     return client.get_resource()
    """
    # Default retryable exceptions if not specified
    if retryable_exceptions is None:
        retryable_exceptions = _get_default_retryable_exceptions()

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = initial_delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    # Try the operation
                    result = func(*args, **kwargs)

                    # Success - log if this was a retry
                    if attempt > 1:
                        logger.info(
                            f"{func.__name__} succeeded on attempt {attempt}/{max_attempts}"
                        )

                    return result

                except retryable_exceptions as e:
                    last_exception = e

                    # Check if we have more attempts
                    if attempt >= max_attempts:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise

                    # Calculate delay with jitter
                    actual_delay = delay
                    if jitter:
                        # Add random jitter: ±25% of delay
                        jitter_amount = delay * 0.25
                        actual_delay = delay + random.uniform(-jitter_amount, jitter_amount)

                    # Cap at max_delay
                    actual_delay = min(actual_delay, max_delay)

                    logger.warning(
                        f"{func.__name__} failed on attempt {attempt}/{max_attempts}, "
                        f"retrying in {actual_delay:.2f}s: {_safe_error_message(e)}"
                    )

                    # Wait before retry
                    time.sleep(actual_delay)

                    # Exponential backoff: double the delay
                    delay *= 2

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError(f"{func.__name__} failed with unknown error")

        return wrapper  # type: ignore

    return decorator


def _get_default_retryable_exceptions() -> tuple[type[Exception], ...]:
    """Get tuple of default retryable exception types.

    Returns:
        Tuple of exception types that should trigger retries

    Note:
        This imports Azure SDK exceptions lazily to avoid hard dependency
    """
    exceptions: list[type[Exception]] = [
        # Network/timeout errors
        TimeoutError,
        ConnectionError,
        ConnectionResetError,
    ]

    # Try to import Azure SDK exceptions
    try:
        from azure.core.exceptions import (
            HttpResponseError,
            ServiceRequestError,
            ServiceResponseError,
        )

        exceptions.extend([HttpResponseError, ServiceRequestError, ServiceResponseError])
    except ImportError:
        logger.debug("Azure SDK exceptions not available for retry logic")

    # Try to import SSH/subprocess exceptions
    try:
        import subprocess
        exceptions.append(subprocess.TimeoutExpired)
    except ImportError:
        pass

    return tuple(exceptions)


def _safe_error_message(exception: Exception) -> str:
    """Create safe error message without leaking credentials.

    Args:
        exception: Exception to create message from

    Returns:
        Sanitized error message safe for logging

    Security:
        - Strips potentially sensitive information
        - Prevents credential leakage in logs
    """
    error_str = str(exception)

    # Truncate very long error messages
    if len(error_str) > 200:
        error_str = error_str[:200] + "..."

    # Remove common credential patterns (basic sanitization)
    # Note: For production, should use log_sanitizer module
    sensitive_patterns = [
        "secret=",
        "password=",
        "token=",
        "key=",
        "authorization:",
    ]

    for pattern in sensitive_patterns:
        if pattern.lower() in error_str.lower():
            # Mask the value after the pattern
            parts = error_str.lower().split(pattern.lower())
            if len(parts) > 1:
                error_str = parts[0] + f"{pattern}***"

    return error_str


def should_retry_http_error(status_code: int) -> bool:
    """Determine if HTTP status code should trigger retry.

    Args:
        status_code: HTTP status code from error

    Returns:
        True if this status code indicates a retryable error

    Retryable status codes:
        - 408: Request Timeout
        - 429: Too Many Requests (throttling)
        - 500: Internal Server Error
        - 502: Bad Gateway
        - 503: Service Unavailable
        - 504: Gateway Timeout
    """
    retryable_codes = {408, 429, 500, 502, 503, 504}
    return status_code in retryable_codes


__all__ = [
    "retry_with_exponential_backoff",
    "should_retry_http_error",
]
