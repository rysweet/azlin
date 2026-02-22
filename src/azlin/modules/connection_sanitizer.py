"""Connection parameter sanitization and validation.

Extracted from vm_connector.py (Issue #597) to reduce module size.
Provides input sanitization for logging and IP address validation.

Security:
- Prevents log injection via control character removal
- Validates IP addresses using Python's ipaddress module

Public API:
    sanitize_for_logging: Sanitize string for safe logging
    is_valid_ip: Check if string is a valid IP address
"""

import ipaddress
import re


def sanitize_for_logging(value: str) -> str:
    """Sanitize string for safe logging.

    Prevents log injection by removing control characters and newlines.

    Args:
        value: String to sanitize

    Returns:
        Sanitized string safe for logging
    """
    # Strip ANSI escape sequences
    value = re.sub(r"\x1b\[[\d;]*[a-zA-Z]", "", value)
    # Strip other control characters (except space)
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    return value.encode("ascii", "replace").decode("ascii").replace("\n", " ").replace("\r", " ")


def is_valid_ip(identifier: str) -> bool:
    """Check if string is a valid IP address.

    Uses Python's ipaddress module for proper validation.
    Supports both IPv4 and IPv6 addresses.

    Args:
        identifier: String to check

    Returns:
        True if valid IPv4 or IPv6 address

    Example:
        >>> is_valid_ip("192.168.1.1")
        True
        >>> is_valid_ip("2001:db8::1")
        True
        >>> is_valid_ip("my-vm-name")
        False
        >>> is_valid_ip("256.1.1.1")
        False
    """
    try:
        ipaddress.ip_address(identifier)
        return True
    except ValueError:
        return False


__all__ = ["is_valid_ip", "sanitize_for_logging"]
