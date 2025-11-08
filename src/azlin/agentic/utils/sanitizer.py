"""Secret sanitization for command outputs and logs.

Sanitizes sensitive information like connection strings, API keys, tokens,
and Azure secrets from command outputs and execution results.
"""

import re
from typing import Any


class SecretSanitizer:
    """Sanitizes secrets from strings and data structures.

    Provides pattern matching for common Azure secrets and credentials.

    Example:
        >>> sanitizer = SecretSanitizer()
        >>> output = "Connection: AccountKey=abc123xyz..."
        >>> clean = sanitizer.sanitize(output)
        >>> print(clean)
        "Connection: AccountKey=***REDACTED***"
    """

    def __init__(self):
        """Initialize sanitizer with secret patterns."""
        self.patterns = [
            # Azure Storage Account Keys
            (
                re.compile(
                    r"(AccountKey|account-key)[\s=:]+([A-Za-z0-9+/]{88}==?)",
                    re.IGNORECASE,
                ),
                r"\1=***REDACTED***",
            ),
            # Azure Connection Strings
            (
                re.compile(
                    r"(DefaultEndpointsProtocol=https?;.*?AccountKey=)([A-Za-z0-9+/]{88}==?)",
                    re.IGNORECASE,
                ),
                r"\1***REDACTED***",
            ),
            # Azure SAS Tokens
            (
                re.compile(r"(\?sv=[\d-]+&[^&]*sig=)([A-Za-z0-9%+/]+)", re.IGNORECASE),
                r"\1***REDACTED***",
            ),
            # Anthropic API Keys
            (
                re.compile(r"(sk-ant-)([a-zA-Z0-9-_]{95,})", re.IGNORECASE),
                r"\1***REDACTED***",
            ),
            # Generic API Keys
            (
                re.compile(
                    r"(api[-_]?key|apikey)[\s=:]+['\"]?([a-zA-Z0-9_\-]{20,})['\"]?",
                    re.IGNORECASE,
                ),
                r"\1=***REDACTED***",
            ),
            # Bearer Tokens
            (
                re.compile(r"(Bearer|bearer)[\s]+([a-zA-Z0-9_\-\.]{20,})", re.IGNORECASE),
                r"\1 ***REDACTED***",
            ),
            # Azure AD Tokens (JWT)
            (
                re.compile(
                    r"(eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)",
                    re.IGNORECASE,
                ),
                r"***REDACTED_JWT***",
            ),
            # Passwords in URLs
            (
                re.compile(r"(https?://[^:]+:)([^@]+)(@)", re.IGNORECASE),
                r"\1***REDACTED***\3",
            ),
            # Generic passwords
            (
                re.compile(
                    r"(password|pwd|passwd)[\s=:]+['\"]?([^\s'\"]{8,})['\"]?",
                    re.IGNORECASE,
                ),
                r"\1=***REDACTED***",
            ),
            # Azure Service Principal Secrets
            (
                re.compile(
                    r"(client[-_]?secret|clientsecret)[\s=:]+['\"]?([a-zA-Z0-9~._-]{34,})['\"]?",
                    re.IGNORECASE,
                ),
                r"\1=***REDACTED***",
            ),
            # SSH Private Keys
            (
                re.compile(
                    r"(-----BEGIN [A-Z ]+PRIVATE KEY-----)(.+?)(-----END [A-Z ]+PRIVATE KEY-----)",
                    re.DOTALL | re.IGNORECASE,
                ),
                r"\1\n***REDACTED***\n\3",
            ),
            # Azure Storage Connection String Components
            (
                re.compile(r"(SharedAccessSignature=)([^;\"'\s]+)", re.IGNORECASE),
                r"\1***REDACTED***",
            ),
        ]

    def sanitize(self, text: str | None) -> str | None:
        """Sanitize secrets from text.

        Args:
            text: Text to sanitize (may be None)

        Returns:
            Sanitized text with secrets replaced, or None if input was None

        Example:
            >>> sanitizer = SecretSanitizer()
            >>> text = "AccountKey=abc123xyz..."
            >>> clean = sanitizer.sanitize(text)
            >>> assert "abc123xyz" not in clean
        """
        if text is None:
            return None

        result = text
        for pattern, replacement in self.patterns:
            result = pattern.sub(replacement, result)

        return result

    def sanitize_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Sanitize secrets from dictionary recursively.

        Args:
            data: Dictionary to sanitize

        Returns:
            New dictionary with sanitized values

        Example:
            >>> sanitizer = SecretSanitizer()
            >>> data = {"key": "sk-ant-abc123..."}
            >>> clean = sanitizer.sanitize_dict(data)
            >>> assert "abc123" not in str(clean)
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.sanitize(value)
            elif isinstance(value, dict):
                result[key] = self.sanitize_dict(value)
            elif isinstance(value, list):
                result[key] = self.sanitize_list(value)
            else:
                result[key] = value
        return result

    def sanitize_list(self, data: list[Any]) -> list[Any]:
        """Sanitize secrets from list recursively.

        Args:
            data: List to sanitize

        Returns:
            New list with sanitized values

        Example:
            >>> sanitizer = SecretSanitizer()
            >>> data = ["AccountKey=abc123", {"key": "secret"}]
            >>> clean = sanitizer.sanitize_list(data)
            >>> assert "abc123" not in str(clean)
        """
        result = []
        for item in data:
            if isinstance(item, str):
                result.append(self.sanitize(item))
            elif isinstance(item, dict):
                result.append(self.sanitize_dict(item))
            elif isinstance(item, list):
                result.append(self.sanitize_list(item))
            else:
                result.append(item)
        return result


# Global sanitizer instance for convenience
_sanitizer = SecretSanitizer()


def sanitize_output(text: str | None) -> str | None:
    """Convenience function to sanitize text using global sanitizer.

    Args:
        text: Text to sanitize

    Returns:
        Sanitized text

    Example:
        >>> output = "Bearer eyJhbGciOi..."
        >>> clean = sanitize_output(output)
        >>> assert "eyJhbGciOi" not in clean
    """
    return _sanitizer.sanitize(text)
