"""Security module for Azure authentication.

This module provides security controls for authentication operations:
- Log sanitization to mask secrets
- UUID validation for Azure IDs
- Secret detection in configuration
- Subprocess argument sanitization

Security Philosophy:
- Conservative approach: if it looks like a secret, mask it
- No external dependencies
- Fail-safe defaults
- Clear patterns and comprehensive coverage

P0 Security Controls:
- ALL secrets must be masked in logs
- ALL Azure IDs must be validated as UUIDs
- ALL configs must be checked for embedded secrets
"""

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ValidationResult:
    """Result of a validation operation.

    Attributes:
        valid: Whether the validation passed
        error: Error message if validation failed, None otherwise
    """

    valid: bool
    error: str | None


# Secret patterns for log sanitization
# These patterns match common secret formats that must be redacted
_SECRET_PATTERNS = [
    # Azure client secrets (environment variable format)
    (r"AZURE_CLIENT_SECRET\s*=\s*[^\s]+", "AZURE_CLIENT_SECRET=***REDACTED***"),
    # Bearer tokens (JWT format)
    (r"Bearer\s+[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+", "Bearer ***REDACTED***"),
    # PEM certificate blocks
    (
        r"-----BEGIN CERTIFICATE-----[\s\S]*?-----END CERTIFICATE-----",
        "-----BEGIN CERTIFICATE-----\n***REDACTED***\n-----END CERTIFICATE-----",
    ),
    # PEM private key blocks (generic)
    (
        r"-----BEGIN PRIVATE KEY-----[\s\S]*?-----END PRIVATE KEY-----",
        "-----BEGIN PRIVATE KEY-----\n***REDACTED***\n-----END PRIVATE KEY-----",
    ),
    # PEM RSA private key blocks
    (
        r"-----BEGIN RSA PRIVATE KEY-----[\s\S]*?-----END RSA PRIVATE KEY-----",
        "-----BEGIN RSA PRIVATE KEY-----\n***REDACTED***\n-----END RSA PRIVATE KEY-----",
    ),
    # Long hex strings (32+ chars, potential secrets/tokens)
    (r"\b[a-fA-F0-9]{32,}\b", "***REDACTED***"),
    # Long base64 strings (40+ chars, potential tokens)
    (r"\b[A-Za-z0-9+/]{40,}={0,2}\b", "***REDACTED***"),
    # JSON format: "key": "value"
    (
        r'"(client_secret|password|secret_key|api_key|access_token|auth_token|bearer_token|private_key)"\s*:\s*"([^"]+)"',
        r'"\1": "***REDACTED***"',
    ),
    # Key-value patterns with sensitive keys (key=value or key: value)
    (
        r"(client_secret|password|secret_key|api_key|access_token|auth_token|bearer_token|private_key)\s*[=:]\s*([^\s,}\]]+)",
        r"\1=***REDACTED***",
    ),
]


def sanitize_log(message: str) -> str:
    """Sanitize log message by masking secrets.

    Masks the following patterns:
    - Client secrets (AZURE_CLIENT_SECRET pattern)
    - Access tokens (Bearer tokens, JWT format)
    - Certificate contents (PEM blocks)
    - Private keys (PEM blocks)
    - Long hex strings (32+ characters, potential secrets)
    - Long base64 strings (40+ characters, potential tokens)
    - Key-value pairs with sensitive keys (password, secret, token, etc.)

    Args:
        message: The log message to sanitize

    Returns:
        Sanitized message with secrets replaced by '***REDACTED***'

    Security:
        Conservative approach - masks anything that might be a secret.
        Better to redact too much than to leak a secret.
    """
    if not message:
        return message

    sanitized = message

    # Apply all secret patterns
    for pattern, replacement in _SECRET_PATTERNS:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    return sanitized


def validate_uuid(value: str | None, field_name: str) -> ValidationResult:
    """Validate UUID format for Azure IDs.

    Azure uses UUIDs for tenant IDs, subscription IDs, client IDs, etc.
    This function validates that a value matches the standard UUID format:
    8-4-4-4-12 hexadecimal digits separated by hyphens.

    Args:
        value: The UUID string to validate
        field_name: Name of field for error messages (tenant_id, client_id, etc.)

    Returns:
        ValidationResult with valid=True if UUID is valid, False otherwise.
        If invalid, error field contains a descriptive message.

    Examples:
        >>> validate_uuid("12345678-1234-1234-1234-123456789abc", "tenant_id")
        ValidationResult(valid=True, error=None)

        >>> validate_uuid("invalid", "tenant_id")
        ValidationResult(valid=False, error="tenant_id: invalid UUID format")
    """
    if not value:
        return ValidationResult(
            valid=False, error=f"{field_name}: invalid UUID format (empty or None)"
        )

    # Strip whitespace and check if empty
    if not value.strip():
        return ValidationResult(
            valid=False, error=f"{field_name}: invalid UUID format (whitespace only)"
        )

    # Azure UUIDs are in format: 8-4-4-4-12 (hex digits with hyphens)
    # Case-insensitive validation
    uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"

    if re.match(uuid_pattern, value, re.IGNORECASE):
        return ValidationResult(valid=True, error=None)

    return ValidationResult(
        valid=False, error=f"{field_name}: invalid UUID format (expected: 8-4-4-4-12 hex digits)"
    )


def detect_secrets_in_config(config: dict) -> list[str]:
    """Detect if config contains embedded secrets (FORBIDDEN).

    Checks for:
    - Sensitive field names (client_secret, password, api_key, token, etc.)
    - Long base64 strings (40+ chars, potential secrets)
    - Long hex strings (32+ chars, potential secrets)
    - Private key content
    - Certificate content

    Args:
        config: Configuration dictionary to check

    Returns:
        List of field paths containing secrets (e.g., ["client_secret", "azure.password"])
        Empty list if no secrets detected.

    Security:
        Conservative approach - flags anything that might be a secret.
        Azure UUIDs (subscription_id, tenant_id) are explicitly allowed.

    Examples:
        >>> detect_secrets_in_config({"client_id": "abc"})
        []

        >>> detect_secrets_in_config({"client_secret": "secret123"})
        ['client_secret']

        >>> detect_secrets_in_config({"azure": {"password": "pass"}})
        ['azure.password']
    """
    secrets = []

    def _check_value(key_path: str, value: Any) -> None:
        """Recursively check a config value for secrets."""
        # Skip None and non-string values for field name checks
        key_lower = key_path.split(".")[-1].lower()
        sensitive_keys = {
            "client_secret",
            "password",
            "secret_key",
            "api_key",
            "access_token",
            "auth_token",
            "bearer_token",
            "private_key",
            "certificate",
            "secret",
            "token",
        }

        # Only flag sensitive field names if value is not None
        if value is not None:
            if key_lower in sensitive_keys:
                secrets.append(key_path)
                return

            # Check for partial matches (e.g., "my_password", "api_secret")
            for sensitive in sensitive_keys:
                if sensitive in key_lower:
                    secrets.append(key_path)
                    return

        # Check value patterns (only for string values)
        if not isinstance(value, str):
            return

        # Skip empty or very short values
        if len(value) < 20:
            return

        # Check if it's an Azure UUID (these are safe)
        uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        if re.match(uuid_pattern, value, re.IGNORECASE):
            return

        # Check for long base64 strings (potential tokens)
        base64_pattern = r"^[A-Za-z0-9+/]{40,}={0,2}$"
        if re.match(base64_pattern, value):
            secrets.append(key_path)
            return

        # Check for long hex strings (potential secrets)
        hex_pattern = r"^[a-fA-F0-9]{32,}$"
        if re.match(hex_pattern, value):
            secrets.append(key_path)
            return

    def _traverse(obj: Any, path: str = "") -> None:
        """Recursively traverse config structure."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_path = f"{path}.{key}" if path else key
                if isinstance(value, (dict, list)):
                    _traverse(value, new_path)
                else:
                    _check_value(new_path, value)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                new_path = f"{path}[{i}]"
                _traverse(item, new_path)

    _traverse(config)
    return secrets


def sanitize_subprocess_args(args: list[str]) -> list[str]:
    """Sanitize subprocess arguments for logging.

    Masks sensitive command-line arguments like:
    - --client-secret <value>
    - --password <value>
    - --secret <value>
    - --token <value>
    - --api-key <value>
    - --private-key <value>
    - -p <value> (short form)

    Also handles --flag=value format.

    Args:
        args: List of command-line arguments

    Returns:
        Sanitized argument list safe for logging

    Examples:
        >>> sanitize_subprocess_args(["az", "login", "--client-secret", "secret123"])
        ['az', 'login', '--client-secret', '***REDACTED***']

        >>> sanitize_subprocess_args(["command", "--secret=value"])
        ['command', '--secret=***REDACTED***']
    """
    if not args:
        return []

    # Sensitive flag patterns (both long and short forms)
    # Use exact matches to avoid false positives
    sensitive_flags = {
        "--client-secret",
        "--password",
        "--secret",
        "--token",
        "--api-key",
        "--auth-token",
        "--bearer-token",
        "--access-token",
        "--private-key",
        "--certificate",
        "-p",  # Common short form for password
    }

    # For partial matching, we need to be more specific to avoid false positives
    # These are substrings that indicate a sensitive flag
    sensitive_substrings = {
        "client-secret",
        "client_secret",
        "api-key",
        "api_key",
        "auth-token",
        "auth_token",
        "bearer-token",
        "bearer_token",
        "access-token",
        "access_token",
        "private-key",
        "private_key",
    }

    sanitized = []
    skip_next = False

    for i, arg in enumerate(args):
        if skip_next:
            # This is the value after a sensitive flag, redact it
            sanitized.append("***REDACTED***")
            skip_next = False
            continue

        arg_lower = arg.lower()

        # Check for --flag=value format
        if "=" in arg:
            flag, value = arg.split("=", 1)
            if flag.lower() in sensitive_flags:
                sanitized.append(f"{flag}=***REDACTED***")
                continue
            # Check for partial matches in flag name using specific substrings
            flag_part = flag.lstrip("-").replace("-", "_")
            if any(sens.replace("-", "_") in flag_part for sens in sensitive_substrings):
                sanitized.append(f"{flag}=***REDACTED***")
                continue

        # Check if this is a sensitive flag (flag followed by value)
        if arg_lower in sensitive_flags:
            sanitized.append(arg)
            skip_next = True  # Next arg is the sensitive value
            continue

        # Check for partial matches in flag name using specific substrings
        if arg.startswith("-"):
            arg_part = arg_lower.lstrip("-").replace("-", "_")
            if any(sens.replace("-", "_") in arg_part for sens in sensitive_substrings):
                sanitized.append(arg)
                skip_next = True
                continue

        # Safe argument, keep as-is
        sanitized.append(arg)

    return sanitized


__all__ = [
    "ValidationResult",
    "detect_secrets_in_config",
    "sanitize_log",
    "sanitize_subprocess_args",
    "validate_uuid",
]
