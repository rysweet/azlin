"""Authentication configuration module.

This module provides configuration management for Azure authentication,
supporting multiple authentication methods while maintaining zero breaking
changes to existing workflows.

Security Features (P0):
- NO secrets stored in config files - client secrets ONLY from environment variables
- UUID validation for tenant_id, client_id, subscription_id
- Certificate file existence and permission validation
- Detects and rejects secrets in config files

Supported Authentication Methods:
- az_cli: Delegate to Azure CLI (default, maintains backward compatibility)
- service_principal_secret: Service principal with client secret
- service_principal_cert: Service principal with certificate
- managed_identity: Azure managed identity

Configuration Priority (highest to lowest):
1. CLI arguments
2. Environment variables
3. Profile config file (~/.azlin/auth_profiles.toml)
4. Fallback to az_cli method
"""

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomli  # type: ignore[import]
except ImportError:
    try:
        import tomllib as tomli  # type: ignore[import]
    except ImportError as e:
        raise ImportError("toml library not available. Install with: pip install tomli") from e

logger = logging.getLogger(__name__)


class AuthConfigError(Exception):
    """Raised when authentication configuration operations fail."""

    pass


@dataclass
class AuthConfig:
    """Authentication configuration dataclass.

    Attributes:
        auth_method: Authentication method - one of:
            - 'az_cli' (default)
            - 'service_principal_secret'
            - 'service_principal_cert'
            - 'managed_identity'
        tenant_id: Azure tenant ID (UUID format)
        client_id: Azure client/application ID (UUID format)
        client_secret: Client secret (ONLY from environment variables)
        client_certificate_path: Path to client certificate file
        subscription_id: Azure subscription ID (UUID format)
        profile_name: Name of the profile used (if any)
    """

    auth_method: str = "az_cli"
    tenant_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    client_certificate_path: str | None = None
    subscription_id: str | None = None
    profile_name: str | None = None


@dataclass
class ValidationResult:
    """Result of configuration validation.

    Attributes:
        is_valid: Whether the configuration is valid
        errors: List of validation error messages
        warnings: List of validation warning messages
    """

    is_valid: bool
    errors: list[str]
    warnings: list[str]


def _validate_uuid(value: str | None, field_name: str) -> list[str]:
    """Validate UUID format.

    Args:
        value: Value to validate
        field_name: Name of the field (for error messages)

    Returns:
        List of error messages (empty if valid)

    Security: Uses strict UUID regex pattern to prevent injection attacks
    """
    if value is None:
        return []

    # Handle empty string or whitespace-only
    if not value or not value.strip():
        return [f"Invalid {field_name}: empty or whitespace-only value"]

    # UUID pattern: 8-4-4-4-12 hexadecimal digits
    # Pattern is case-insensitive to accept both uppercase and lowercase
    uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"

    if not re.match(uuid_pattern, value.strip(), re.IGNORECASE):
        return [
            f"Invalid {field_name} format: must be a valid UUID "
            f"(e.g., 12345678-1234-1234-1234-123456789abc)"
        ]

    return []


def _check_certificate_file(cert_path: str) -> tuple[list[str], list[str]]:
    """Check certificate file existence and permissions.

    Args:
        cert_path: Path to certificate file

    Returns:
        Tuple of (errors, warnings)

    Security:
        - Validates file exists
        - Warns on insecure permissions (world-readable)
    """
    errors = []
    warnings = []

    path = Path(cert_path).expanduser()

    # Check file exists
    if not path.exists():
        errors.append(f"Certificate file not found: {cert_path}")
        return errors, warnings

    # Check permissions (should be 0600 or similar - owner only)
    try:
        stat = path.stat()
        mode = stat.st_mode & 0o777

        # Warn if group or others have any permissions
        if mode & 0o077:
            warnings.append(
                f"Certificate file has insecure permissions: {oct(mode)}. "
                f"Recommended: 0600 (owner read/write only)"
            )
    except Exception as e:
        warnings.append(f"Could not check certificate file permissions: {e}")

    return errors, warnings


def validate_auth_config(config: AuthConfig) -> ValidationResult:
    """Validate authentication configuration.

    Validates:
    - Auth method is supported
    - Required fields for each auth method
    - UUID format for IDs
    - Certificate file existence and permissions
    - No security violations

    Args:
        config: Configuration to validate

    Returns:
        ValidationResult with validation status, errors, and warnings

    Security:
        - Validates UUID formats to prevent injection
        - Checks certificate file permissions
        - Ensures required fields for each auth method
    """
    errors = []
    warnings = []

    # Validate auth method
    valid_methods = [
        "az_cli",
        "service_principal_secret",
        "service_principal_cert",
        "managed_identity",
    ]
    if config.auth_method not in valid_methods:
        errors.append(
            f"Invalid auth_method: {config.auth_method}. Must be one of: {', '.join(valid_methods)}"
        )

    # Method-specific validation
    if config.auth_method == "service_principal_secret":
        # Required fields
        if not config.tenant_id:
            errors.append("tenant_id is required for service_principal_secret")
        if not config.client_id:
            errors.append("client_id is required for service_principal_secret")
        if not config.client_secret:
            errors.append("client_secret is required for service_principal_secret")

    elif config.auth_method == "service_principal_cert":
        # Required fields
        if not config.tenant_id:
            errors.append("tenant_id is required for service_principal_cert")
        if not config.client_id:
            errors.append("client_id is required for service_principal_cert")
        if not config.client_certificate_path:
            errors.append("client_certificate_path is required for service_principal_cert")
        else:
            # Validate certificate file
            cert_errors, cert_warnings = _check_certificate_file(config.client_certificate_path)
            errors.extend(cert_errors)
            warnings.extend(cert_warnings)

    # UUID validation (for any method that provides these fields)
    errors.extend(_validate_uuid(config.tenant_id, "tenant_id"))
    errors.extend(_validate_uuid(config.client_id, "client_id"))
    errors.extend(_validate_uuid(config.subscription_id, "subscription_id"))

    # Determine validity
    is_valid = len(errors) == 0

    return ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)


def _load_from_profile(profile: str) -> dict[str, Any]:
    """Load configuration from profile file.

    Args:
        profile: Profile name to load

    Returns:
        Dictionary of configuration values from profile

    Raises:
        AuthConfigError: If profile not found or invalid

    Security:
        - Rejects profiles with client_secret in config file
        - Validates file permissions
    """
    config_dir = Path.home() / ".azlin"
    config_file = config_dir / "auth_profiles.toml"

    if not config_file.exists():
        raise AuthConfigError(
            f"Profile configuration file not found: {config_file}\n"
            f"Create profiles at: ~/.azlin/auth_profiles.toml"
        )

    try:
        # Check file permissions
        stat = config_file.stat()
        mode = stat.st_mode & 0o777
        if mode & 0o077:
            logger.warning(
                f"Profile config file has insecure permissions: {oct(mode)}. Fixing to 0600..."
            )
            config_file.chmod(0o600)

        # Load TOML
        with open(config_file, "rb") as f:
            data = tomli.load(f)  # type: ignore[attr-defined]

        # Find profile
        if "profiles" not in data:
            raise AuthConfigError("No profiles section found in auth_profiles.toml")

        if profile not in data["profiles"]:
            available = ", ".join(data["profiles"].keys())
            raise AuthConfigError(
                f"Profile '{profile}' not found in auth_profiles.toml\n"
                f"Available profiles: {available}"
            )

        profile_data = data["profiles"][profile]

        # SECURITY: Reject profiles with client_secret in config file
        if "client_secret" in profile_data:
            raise AuthConfigError(
                f"SECURITY VIOLATION: client_secret found in config file for profile '{profile}'\n"
                f"Client secrets must ONLY be provided via environment variables.\n"
                f"Remove 'client_secret' from {config_file}"
            )

        logger.debug(f"Loaded profile '{profile}' from {config_file}")
        return profile_data

    except AuthConfigError:
        raise
    except Exception as e:
        raise AuthConfigError(f"Failed to load profile '{profile}': {e}") from e


def _merge_config_sources(
    profile_data: dict[str, Any] | None,
    env_data: dict[str, Any],
    cli_data: dict[str, Any],
) -> dict[str, Any]:
    """Merge configuration from multiple sources.

    Priority order (highest to lowest):
    1. CLI arguments
    2. Environment variables
    3. Profile config file

    Args:
        profile_data: Configuration from profile file
        env_data: Configuration from environment variables
        cli_data: Configuration from CLI arguments

    Returns:
        Merged configuration dictionary
    """
    # Start with profile (lowest priority)
    merged = profile_data.copy() if profile_data else {}

    # Overlay environment variables
    for key, value in env_data.items():
        if value is not None:
            merged[key] = value

    # Overlay CLI arguments (highest priority)
    for key, value in cli_data.items():
        if value is not None:
            merged[key] = value

    return merged


def _load_from_environment() -> dict[str, Any]:
    """Load configuration from environment variables.

    Environment variables:
        AZURE_AUTH_METHOD: Authentication method
        AZURE_TENANT_ID: Tenant ID
        AZURE_CLIENT_ID: Client ID
        AZURE_CLIENT_SECRET: Client secret (this is the ONLY allowed source)
        AZURE_CLIENT_CERTIFICATE_PATH: Certificate file path
        AZURE_SUBSCRIPTION_ID: Subscription ID

    Returns:
        Dictionary of configuration values from environment
    """
    return {
        "auth_method": os.environ.get("AZURE_AUTH_METHOD"),
        "tenant_id": os.environ.get("AZURE_TENANT_ID"),
        "client_id": os.environ.get("AZURE_CLIENT_ID"),
        "client_secret": os.environ.get("AZURE_CLIENT_SECRET"),
        "client_certificate_path": os.environ.get("AZURE_CLIENT_CERTIFICATE_PATH"),
        "subscription_id": os.environ.get("AZURE_SUBSCRIPTION_ID"),
    }


def load_auth_config(
    profile: str | None = None, cli_args: dict[str, Any] | None = None
) -> AuthConfig:
    """Load and merge authentication configuration from all sources.

    Configuration is loaded with the following priority (highest to lowest):
    1. CLI arguments
    2. Environment variables
    3. Profile config file (if profile specified)
    4. Fallback to az_cli method

    Args:
        profile: Profile name to load from ~/.azlin/auth_profiles.toml
        cli_args: Configuration from CLI arguments (highest priority)

    Returns:
        AuthConfig object with merged configuration

    Raises:
        AuthConfigError: If configuration is invalid or profile not found

    Security:
        - Client secrets ONLY from environment variables
        - Rejects profiles with secrets in config file
        - Expands paths (e.g., ~/ to home directory)

    Examples:
        >>> # Default: Use az_cli
        >>> config = load_auth_config()

        >>> # Load from profile
        >>> config = load_auth_config(profile="production")

        >>> # CLI args override everything
        >>> config = load_auth_config(
        ...     profile="production",
        ...     cli_args={"tenant_id": "override-tenant"}
        ... )
    """
    # Initialize sources
    profile_data = None
    env_data = _load_from_environment()
    cli_data = cli_args if cli_args else {}

    # Load profile if specified
    if profile:
        profile_data = _load_from_profile(profile)

    # Merge sources (priority: CLI > env > profile)
    merged = _merge_config_sources(profile_data, env_data, cli_data)

    # Create config object
    config = AuthConfig(
        auth_method=merged.get("auth_method", "az_cli"),
        tenant_id=merged.get("tenant_id"),
        client_id=merged.get("client_id"),
        client_secret=merged.get("client_secret"),
        client_certificate_path=merged.get("client_certificate_path"),
        subscription_id=merged.get("subscription_id"),
        profile_name=profile,
    )

    # Expand certificate path if present
    if config.client_certificate_path:
        config.client_certificate_path = str(Path(config.client_certificate_path).expanduser())

    logger.debug(
        f"Loaded auth config: method={config.auth_method}, "
        f"profile={config.profile_name}, "
        f"has_tenant={config.tenant_id is not None}, "
        f"has_client={config.client_id is not None}"
    )

    return config


__all__ = [
    "AuthConfig",
    "AuthConfigError",
    "ValidationResult",
    "load_auth_config",
    "validate_auth_config",
]
