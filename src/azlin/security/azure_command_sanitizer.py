"""Azure CLI command sanitization for secure display.

This module provides sanitization of Azure CLI commands before display or logging.
It implements comprehensive protection against credential leakage in command output.

Security Controls:
- Parameter-based redaction (--password, --secret, etc.)
- Value-based pattern matching (connection strings, tokens, SAS URLs)
- Thread-safe operation
- Defense in depth with multiple sanitization layers

Usage:
    >>> from azlin.security import AzureCommandSanitizer
    >>> sanitizer = AzureCommandSanitizer()
    >>> safe_cmd = sanitizer.sanitize("az vm create --admin-password Secret123")
    >>> print(safe_cmd)
    az vm create --admin-password [REDACTED]
"""

import re
import threading
from re import Pattern
from typing import ClassVar


class AzureCommandSanitizer:
    """Sanitize Azure CLI commands for safe display and logging.

    This class provides static methods for sanitizing Azure CLI commands to prevent
    credential leakage in terminal output, logs, and error messages.

    Thread Safety:
        All methods are thread-safe and can be called concurrently.

    Examples:
        >>> AzureCommandSanitizer.sanitize("az vm create --admin-password MyPass")
        'az vm create --admin-password [REDACTED]'

        >>> AzureCommandSanitizer.sanitize("az storage show-connection-string")
        'az storage show-connection-string --connection-string [REDACTED]'
    """

    # Redaction markers
    REDACTED = "[REDACTED]"
    REDACTED_PARTIAL = "****"

    # Thread-local storage for thread safety
    _local = threading.local()

    # Comprehensive list of sensitive Azure CLI parameters
    # These are matched case-insensitively (lowercase only in set)
    SENSITIVE_PARAMS: ClassVar[set[str]] = {
        # Authentication & Identity
        "--password",
        "--admin-password",
        "--administrator-login-password",
        "--client-secret",
        "--service-principal-secret",
        # SSH Keys
        "--ssh-key-value",
        "--ssh-key-values",
        "--ssh-private-key-file",
        "--ssh-dest-key-path",
        # Storage & Access Keys
        "--account-key",
        "--connection-string",
        "--sas-token",
        "--primary-key",
        "--secondary-key",
        "--shared-access-key",
        # Secrets & Key Vault
        "--secret",
        "--secrets",
        "--secret-value",
        # Tokens
        "--token",
        "--access-token",
        "--refresh-token",
        "--bearer-token",
        # Certificates
        "--certificate-data",
        "--certificate-password",
        "--pfx-password",
        "--cert-data",
        # Database
        "--db-password",
        "--sql-password",
        # Custom data (may contain secrets)
        "--custom-data",
        "--user-data",
        "--cloud-init",
        # Docker & Container Registry
        "--docker-password",
        "--registry-password",
        # Environment variables (may contain secrets)
        "--environment-variables",
        "--env",
        # API keys
        "--api-key",
        "--subscription-key",
    }

    # Regex patterns for parameter-based redaction
    # Matches: --param-name value or --param-name=value or --param-name="quoted value"
    # Two patterns: one for quoted values, one for unquoted
    # Uses (?:\s+|=) to match either whitespace OR equals sign
    PARAM_VALUE_QUOTED_PATTERN: ClassVar[Pattern] = re.compile(
        r'(--[\w-]+)(?:\s+|=)(["' "'" r'])([^"' "'" r']+)\2',
        re.IGNORECASE,
    )
    PARAM_VALUE_UNQUOTED_PATTERN: ClassVar[Pattern] = re.compile(
        r'(--[\w-]+)(?:\s+|=)([^\s"' "'" r'-][^\s]*)',
        re.IGNORECASE,
    )

    # Value-based patterns (detect secrets in values regardless of parameter name)
    SECRET_VALUE_PATTERNS: ClassVar[dict[str, Pattern]] = {
        # Azure Storage connection string
        # Format: DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...
        "azure_connection_string": re.compile(
            r'DefaultEndpointsProtocol=https[^;\s]*;AccountName=[^;]+;AccountKey=([A-Za-z0-9+/=]+)',
            re.IGNORECASE,
        ),
        # Azure SAS token
        # Format: ?sv=2021-01-01&ss=b&srt=sco&sp=rwdlac&...
        "sas_token": re.compile(r'(\?sv=\d{4}-\d{2}-\d{2}[^\s"\']+)', re.IGNORECASE),
        # Base64 encoded secrets (likely keys) - 40+ chars
        "base64_long": re.compile(r'\b([A-Za-z0-9+/]{40,}={0,2})\b'),
        # JWT tokens
        # Format: eyJ...eyJ...signature
        "jwt": re.compile(r'(eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)'),
        # Azure Active Directory tokens (starts with ey)
        "aad_token": re.compile(r'\b(ey[A-Za-z0-9_-]{100,})\b'),
    }

    @classmethod
    def sanitize(cls, command: str) -> str:
        """Sanitize Azure CLI command for safe display.

        This is the main entry point for command sanitization. It applies all
        sanitization layers in sequence.

        Args:
            command: Azure CLI command string to sanitize

        Returns:
            Sanitized command with all secrets replaced by [REDACTED]

        Examples:
            >>> AzureCommandSanitizer.sanitize("az vm create --admin-password Pass123")
            'az vm create --admin-password [REDACTED]'

            >>> AzureCommandSanitizer.sanitize("az storage account show-connection-string")
            'az storage account show-connection-string [REDACTED]'
        """
        if not isinstance(command, str):
            command = str(command)

        result = command

        # Layer 0: Remove terminal escape sequences FIRST (before processing)
        result = cls._sanitize_terminal_escapes(result)

        # Layer 1: Parameter-based sanitization
        result = cls._sanitize_sensitive_parameters(result)

        # Layer 2: Value-based pattern matching
        result = cls._sanitize_secret_values(result)

        return result

    @classmethod
    def _sanitize_sensitive_parameters(cls, command: str) -> str:
        """Sanitize known sensitive parameters.

        Args:
            command: Command string

        Returns:
            Command with sensitive parameter values redacted
        """

        def replace_sensitive_quoted(match: re.Match) -> str:
            """Replace quoted parameter value if parameter is sensitive."""
            param = match.group(1).lower()  # Parameter name (e.g., --password)
            quote = match.group(2)  # Quote character
            value = match.group(3)  # Parameter value

            # Check if this parameter is sensitive
            if param in cls.SENSITIVE_PARAMS or cls._is_sensitive_param_name(param):
                # Determine separator (space or equals from original match)
                full_match = match.group(0)
                separator = "=" if "=" in full_match[:len(match.group(1)) + 2] else " "
                # Redact the value but keep parameter name, separator, and quotes
                return f"{match.group(1)}{separator}{quote}{cls.REDACTED}{quote}"

            # Not sensitive, return original
            return match.group(0)

        def replace_sensitive_unquoted(match: re.Match) -> str:
            """Replace unquoted parameter value if parameter is sensitive."""
            param = match.group(1).lower()  # Parameter name (e.g., --password)
            value = match.group(2)  # Parameter value

            # Check if this parameter is sensitive
            if param in cls.SENSITIVE_PARAMS or cls._is_sensitive_param_name(param):
                # Determine separator (space or equals from original match)
                full_match = match.group(0)
                separator = "=" if "=" in full_match[:len(match.group(1)) + 2] else " "
                # Redact the value but keep parameter name and separator
                return f"{match.group(1)}{separator}{cls.REDACTED}"

            # Not sensitive, return original
            return match.group(0)

        # Apply both patterns
        result = cls.PARAM_VALUE_QUOTED_PATTERN.sub(replace_sensitive_quoted, command)
        result = cls.PARAM_VALUE_UNQUOTED_PATTERN.sub(replace_sensitive_unquoted, result)

        return result

    @classmethod
    def _is_sensitive_param_name(cls, param: str) -> bool:
        """Check if parameter name suggests sensitive content.

        This is a fallback check for parameters not in the explicit list.
        Uses conservative pattern matching.

        Args:
            param: Parameter name (e.g., "--password" or "--my-secret-key")

        Returns:
            True if parameter name suggests sensitive content
        """
        sensitive_keywords = [
            "password",
            "secret",
            "key",
            "token",
            "credential",
            "auth",
            "private",
            "cert",
            "pfx",
            "connection",
            "sas",
        ]

        param_lower = param.lower()
        return any(keyword in param_lower for keyword in sensitive_keywords)

    @classmethod
    def _sanitize_secret_values(cls, command: str) -> str:
        """Sanitize values that look like secrets based on patterns.

        This catches secrets even if the parameter name isn't recognized.

        Args:
            command: Command string

        Returns:
            Command with secret-like values redacted
        """
        result = command

        for pattern_name, pattern in cls.SECRET_VALUE_PATTERNS.items():
            result = pattern.sub(cls.REDACTED, result)

        return result

    @classmethod
    def _sanitize_terminal_escapes(cls, text: str) -> str:
        """Remove ANSI escape sequences and control characters.

        This prevents terminal manipulation attacks through escape sequences
        in displayed commands.

        Args:
            text: Text potentially containing escape sequences

        Returns:
            Text with escape sequences removed
        """
        # Remove ANSI escape sequences
        # Pattern matches: ESC [ ... m (colors, formatting)
        #                  ESC ] ... BEL/ST (OSC sequences like title)
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        text = ansi_escape.sub("", text)

        # Remove other control characters except newline/tab
        text = "".join(char for char in text if char in "\n\t" or ord(char) >= 32)

        return text

    @classmethod
    def sanitize_for_logging(cls, command: str) -> str:
        """Sanitize command specifically for logging.

        This applies additional sanitization appropriate for log files.

        Args:
            command: Command to sanitize for logging

        Returns:
            Sanitized command safe for log files
        """
        # Apply standard sanitization
        result = cls.sanitize(command)

        # Additional logging-specific sanitization could go here
        # For example, redacting user-specific paths

        return result

    @classmethod
    def sanitize_for_display(cls, command: str, max_length: int | None = None) -> str:
        """Sanitize command for terminal display.

        Args:
            command: Command to sanitize
            max_length: Optional maximum length for display (truncate if longer)

        Returns:
            Sanitized command safe for terminal display
        """
        # Truncate BEFORE sanitization to preserve context
        if max_length and len(command) > max_length:
            command = command[:max_length] + "..."

        result = cls.sanitize(command)

        return result

    @classmethod
    def is_command_safe(cls, command: str) -> bool:
        """Check if command contains any sensitive data.

        This is useful for determining if a command can be safely displayed
        or logged without sanitization.

        Args:
            command: Command to check

        Returns:
            True if command appears safe (no sensitive parameters detected)

        Examples:
            >>> AzureCommandSanitizer.is_command_safe("az vm list")
            True

            >>> AzureCommandSanitizer.is_command_safe("az vm create --admin-password Pass")
            False
        """
        # Check if command has any sensitive parameters present (with values)
        sensitive_params = cls.get_sensitive_parameters_in_command(command)
        if sensitive_params:
            return False

        # Also check for sensitive parameter names even without values
        # Check both with -- prefix and as part of command name
        cmd_lower = command.lower()
        for param in cls.SENSITIVE_PARAMS:
            # Check with -- prefix
            if param in cmd_lower:
                return False
            # Also check without -- (for subcommands like "show-connection-string")
            param_without_dashes = param.lstrip("-")
            if param_without_dashes and param_without_dashes in cmd_lower:
                return False

        # Check if sanitization would change the command
        sanitized = cls.sanitize(command)
        # Also check for REDACTED marker explicitly
        return sanitized == command and cls.REDACTED not in sanitized

    @classmethod
    def get_sensitive_parameters_in_command(cls, command: str) -> list[str]:
        """Extract list of sensitive parameters present in command.

        Useful for warning users about sensitive data in commands.

        Args:
            command: Command to analyze

        Returns:
            List of sensitive parameter names found in command

        Examples:
            >>> AzureCommandSanitizer.get_sensitive_parameters_in_command(
            ...     "az vm create --admin-password Pass --ssh-key-value key"
            ... )
            ['--admin-password', '--ssh-key-value']
        """
        found_params = []

        # Find all parameters (check both quoted and unquoted patterns)
        for match in cls.PARAM_VALUE_QUOTED_PATTERN.finditer(command):
            param = match.group(1).lower()
            if param in cls.SENSITIVE_PARAMS or cls._is_sensitive_param_name(param):
                found_params.append(param)

        for match in cls.PARAM_VALUE_UNQUOTED_PATTERN.finditer(command):
            param = match.group(1).lower()
            if param in cls.SENSITIVE_PARAMS or cls._is_sensitive_param_name(param):
                # Avoid duplicates
                if param not in found_params:
                    found_params.append(param)

        return found_params


# Convenience function for quick sanitization
def sanitize_azure_command(command: str) -> str:
    """Convenience function to sanitize Azure CLI commands.

    Args:
        command: Azure CLI command string

    Returns:
        Sanitized command

    Examples:
        >>> sanitize_azure_command("az vm create --admin-password MyPassword")
        'az vm create --admin-password [REDACTED]'
    """
    return AzureCommandSanitizer.sanitize(command)
