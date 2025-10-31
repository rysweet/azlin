"""Security module for azlin.

This module provides security utilities for protecting sensitive data in azlin:

- AzureCommandSanitizer: Sanitize Azure CLI commands before display/logging
- Command parameter redaction
- Value-based secret detection
- Thread-safe operation

Example:
    >>> from azlin.security import AzureCommandSanitizer
    >>> safe = AzureCommandSanitizer.sanitize("az vm create --admin-password Secret")
    >>> print(safe)
    az vm create --admin-password [REDACTED]
"""

from azlin.security.azure_command_sanitizer import (
    AzureCommandSanitizer,
    sanitize_azure_command,
)

__all__ = [
    "AzureCommandSanitizer",
    "sanitize_azure_command",
]
