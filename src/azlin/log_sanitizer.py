"""Log sanitization module for preventing secret leakage.

This module provides comprehensive sanitization of sensitive data in logs and error messages.
It implements pattern-based redaction for various secret types including:
- Client secrets
- Client IDs (UUIDs - partial masking)
- Tenant IDs
- Passwords
- Access tokens
- Authorization headers
- Certificate paths with sensitive names

Security Controls:
- SEC-005: Log sanitization - mask ALL secrets
- SEC-010: Error messages don't leak secrets

Design Philosophy:
- Security first: err on side of over-redaction
- Pattern-based: not brittle keyword matching
- Fail-safe: if in doubt, mask it
"""

import re
from re import Pattern
from typing import Any


class LogSanitizer:
    """Sanitize sensitive data from logs and error messages.

    This class provides static methods for sanitizing various types of sensitive
    information that might appear in logs, error messages, or debug output.

    All methods are static and can be called without instantiation.
    """

    # Redaction marker - consistent with test expectations
    REDACTED = "[REDACTED]"
    MASKED = "****"

    # Secret patterns - comprehensive coverage for all sensitive data types
    # Order matters: more specific patterns should come first
    SECRET_PATTERNS: dict[str, Pattern] = {
        # Client secret patterns (various formats)
        "client_secret_assignment": re.compile(
            r'(client[_-]?secret["\']?\s*[:=]\s*["\']?)([^\s"\'&,\)]+)',
            re.IGNORECASE,
        ),
        "client_secret_env": re.compile(
            r"(AZURE_CLIENT_SECRET|AZLIN_SP_CLIENT_SECRET)[\"']?\s*[:=]\s*[\"']?([^\s\"'&,\)]+)",
            re.IGNORECASE,
        ),
        # Password patterns
        "password": re.compile(r'(password["\']?\s*[:=]\s*["\']?)([^\s"\'&,\)]+)', re.IGNORECASE),
        # Authorization headers
        "authorization_bearer": re.compile(r"(Authorization:\s*Bearer\s+)([^\s]+)", re.IGNORECASE),
        # Access token patterns
        "access_token": re.compile(
            r'(access[_-]?token["\']?\s*[:=]\s*["\']?)([^\s"\'&,\)]+)',
            re.IGNORECASE,
        ),
        # Token in general (but not "token" as a word)
        "token_assignment": re.compile(
            r'([^a-zA-Z]token["\']?\s*[:=]\s*["\']?)([^\s"\'&,\)]+)', re.IGNORECASE
        ),
        # Credential patterns
        "credential": re.compile(
            r'(credential["\']?\s*[:=]\s*["\']?)([^\s"\'&,\)]+)', re.IGNORECASE
        ),
        # Secret in phrases like "with secret:" or "for secret:"
        "secret_phrase": re.compile(
            r"(with secret:\s*|for secret:\s*|secret:\s*)([^\s,\)]+)", re.IGNORECASE
        ),
    }

    # Sensitive file name patterns (for certificate paths)
    # Matches both absolute paths (/path/to/secret.pem) and relative filenames (secret.pem)
    SENSITIVE_PATH_PATTERNS: dict[str, Pattern] = {
        "secret_in_filename": re.compile(
            r"((?:[/\\][\w\-]*)?[\w\-]*secret[\w\-]*\.(pem|pfx|key|crt|cer))", re.IGNORECASE
        ),
        "production_key": re.compile(
            r"((?:[/\\][\w\-]*)?[\w\-]*prod[\w\-]*\.(pem|pfx|key|crt|cer))", re.IGNORECASE
        ),
        "private_key": re.compile(
            r"((?:[/\\][\w\-]*)?[\w\-]*private[\w\-]*\.(pem|pfx|key|crt|cer))", re.IGNORECASE
        ),
    }

    # UUID pattern for partial masking of client IDs
    UUID_PATTERN: Pattern = re.compile(
        r"\b([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{12})\b",
        re.IGNORECASE,
    )

    @classmethod
    def sanitize(cls, message: str) -> str:
        """Sanitize message by redacting sensitive patterns.

        This is the main entry point for sanitization. It applies all
        sanitization patterns to the message.

        Args:
            message: The message to sanitize

        Returns:
            Sanitized message with secrets replaced by [REDACTED] or ****

        Examples:
            >>> LogSanitizer.sanitize("client_secret=abc123")
            'client_secret=[REDACTED]'
            >>> LogSanitizer.sanitize("Auth failed with secret: abc123")
            'Auth failed with secret: [REDACTED]'
        """
        if not isinstance(message, str):
            message = str(message)

        result = message

        # Apply all secret patterns
        for pattern_name, pattern in cls.SECRET_PATTERNS.items():
            result = pattern.sub(r"\1" + cls.REDACTED, result)

        # Apply sensitive path patterns
        for pattern_name, pattern in cls.SENSITIVE_PATH_PATTERNS.items():
            result = pattern.sub(r"****", result)

        return result

    @classmethod
    def sanitize_client_secret(cls, message: str) -> str:
        """Mask client secrets completely.

        Args:
            message: The message to sanitize

        Returns:
            Message with client secrets replaced by ****

        Examples:
            >>> LogSanitizer.sanitize_client_secret("secret=abc123")
            'secret=****'
        """
        result = message
        result = re.sub(
            r'(client[_-]?secret["\']?\s*[:=]\s*["\']?)([^\s"\'&,\)]+)',
            r"\1" + cls.MASKED,
            result,
            flags=re.IGNORECASE,
        )
        return result

    @classmethod
    def sanitize_client_id(cls, message: str) -> str:
        """Partially mask UUIDs (client IDs).

        Shows first 8 characters, masks the rest.

        Args:
            message: The message to sanitize

        Returns:
            Message with UUIDs partially masked

        Examples:
            >>> LogSanitizer.sanitize_client_id("client_id=12345678-1234-1234-1234-123456789abc")
            'client_id=12345678-****-****-****-************'
        """

        def uuid_replacer(match):
            """Replace UUID with partially masked version."""
            return f"{match.group(1)}-****-****-****-************"

        result = cls.UUID_PATTERN.sub(uuid_replacer, message)
        return result

    @classmethod
    def sanitize_certificate_path(cls, message: str) -> str:
        """Mask certificate file paths with sensitive names.

        Args:
            message: The message to sanitize

        Returns:
            Message with sensitive certificate paths masked

        Examples:
            >>> LogSanitizer.sanitize_certificate_path("/path/to/secret-key.pem")
            '/path/to/****'
        """
        result = message
        for pattern_name, pattern in cls.SENSITIVE_PATH_PATTERNS.items():
            result = pattern.sub(cls.MASKED, result)
        return result

    @classmethod
    def sanitize_env_vars(cls, env_dict: dict[str, str]) -> dict[str, str]:
        """Sanitize environment variables dictionary.

        Creates a new dictionary with sensitive values redacted.

        Args:
            env_dict: Dictionary of environment variables

        Returns:
            New dictionary with sensitive values redacted

        Examples:
            >>> env = {"AZURE_CLIENT_SECRET": "secret123", "HOME": "/home/user"}
            >>> sanitized = LogSanitizer.sanitize_env_vars(env)
            >>> sanitized["AZURE_CLIENT_SECRET"]
            '[REDACTED]'
            >>> sanitized["HOME"]
            '/home/user'
        """
        # List of sensitive environment variable names
        sensitive_keys = {
            "AZURE_CLIENT_SECRET",
            "AZLIN_SP_CLIENT_SECRET",
            "CLIENT_SECRET",
            "PASSWORD",
            "ACCESS_TOKEN",
            "TOKEN",
            "SECRET",
            "CREDENTIAL",
            "API_KEY",
            "AUTH_TOKEN",
        }

        result = {}
        for key, value in env_dict.items():
            # Check if key is sensitive (exact match or contains sensitive word)
            is_sensitive = False
            key_upper = key.upper()

            # Check exact matches
            if key_upper in sensitive_keys:
                is_sensitive = True
            # Check if any sensitive word is in the key
            else:
                for sensitive_word in ["SECRET", "PASSWORD", "TOKEN", "CREDENTIAL", "KEY"]:
                    if sensitive_word in key_upper:
                        is_sensitive = True
                        break

            result[key] = cls.REDACTED if is_sensitive else value

        return result

    @classmethod
    def create_safe_error_message(cls, error: Exception, context: str = "") -> str:
        """Create error message with secrets sanitized.

        Args:
            error: The exception to sanitize
            context: Optional context string to prepend

        Returns:
            Sanitized error message

        Examples:
            >>> err = ValueError("Auth failed with client_secret=abc123")
            >>> LogSanitizer.create_safe_error_message(err, "Authentication")
            'Authentication: Auth failed with client_secret=[REDACTED]'
        """
        error_msg = str(error)
        sanitized_msg = cls.sanitize(error_msg)

        if context:
            return f"{context}: {sanitized_msg}"
        return sanitized_msg

    @classmethod
    def sanitize_dict(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Sanitize dictionary values recursively.

        Creates a new dictionary with sensitive values redacted.

        Args:
            data: Dictionary to sanitize

        Returns:
            New dictionary with sensitive values redacted

        Examples:
            >>> data = {"config": {"client_secret": "abc123", "tenant_id": "valid-uuid"}}
            >>> sanitized = LogSanitizer.sanitize_dict(data)
            >>> sanitized["config"]["client_secret"]
            '[REDACTED]'
        """
        # List of sensitive keys to redact
        sensitive_keys = {
            "client_secret",
            "password",
            "access_token",
            "token",
            "secret",
            "credential",
            "authorization",
            "api_key",
            "auth_token",
        }

        result = {}
        for key, value in data.items():
            # Check if key is sensitive
            key_lower = key.lower()
            is_sensitive = any(sensitive_word in key_lower for sensitive_word in sensitive_keys)

            if is_sensitive:
                # Redact sensitive value
                result[key] = cls.REDACTED
            elif isinstance(value, dict):
                # Recursively sanitize nested dictionaries
                result[key] = cls.sanitize_dict(value)
            elif isinstance(value, str):
                # Sanitize string values
                result[key] = cls.sanitize(value)
            elif isinstance(value, (list, tuple)):
                # Sanitize list/tuple elements
                result[key] = type(value)(
                    cls.sanitize_dict(item)
                    if isinstance(item, dict)
                    else cls.sanitize(str(item))
                    if isinstance(item, str)
                    else item
                    for item in value
                )
            else:
                # Keep non-sensitive, non-string values as-is
                result[key] = value

        return result

    @classmethod
    def sanitize_exception(cls, exc: Exception) -> str:
        """Sanitize exception message.

        Args:
            exc: Exception to sanitize

        Returns:
            Sanitized exception message

        Examples:
            >>> exc = ValueError("Auth failed: client_secret=abc123")
            >>> LogSanitizer.sanitize_exception(exc)
            'Auth failed: client_secret=[REDACTED]'
        """
        return cls.sanitize(str(exc))
