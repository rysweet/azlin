"""Authentication data models for azlin.

This module defines all authentication-related data structures including:
- AuthMethod enum
- Configuration dataclasses (ServicePrincipalConfig, ManagedIdentityConfig, AuthConfig)
- Runtime context (AuthContext)
- Result types (ChainResult, CertificateValidation)

Security features:
- Frozen dataclasses for immutability
- UUID validation in __post_init__
- Secret masking in to_dict_masked()
- No plain text secret storage
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID


def validate_uuid(value: str, field_name: str) -> None:
    """Validate UUID format. Raises ValueError if invalid.

    Args:
        value: The string to validate as UUID
        field_name: Name of the field for error messages

    Raises:
        ValueError: If value is not a valid UUID format
    """
    if not value:
        raise ValueError(f"{field_name} must be valid UUID format, got empty string")

    try:
        UUID(value)
    except (ValueError, AttributeError) as e:
        raise ValueError(f"{field_name} must be valid UUID format, got: {value}") from e


class AuthMethod(StrEnum):
    """Authentication method enumeration.

    Defines the authentication methods supported by azlin:
    - AZURE_CLI: Use Azure CLI for authentication (default, backward compatible)
    - SERVICE_PRINCIPAL_SECRET: Service principal with client secret
    - SERVICE_PRINCIPAL_CERTIFICATE: Service principal with certificate
    - MANAGED_IDENTITY: Managed identity (system or user-assigned)
    """

    AZURE_CLI = "azure_cli"
    SERVICE_PRINCIPAL_SECRET = "sp_secret"  # noqa: S105 - Enum value, not a password
    SERVICE_PRINCIPAL_CERTIFICATE = "sp_cert"
    MANAGED_IDENTITY = "managed_identity"

    @property
    def is_service_principal(self) -> bool:
        """Check if this method is a service principal method."""
        return self in (
            AuthMethod.SERVICE_PRINCIPAL_SECRET,
            AuthMethod.SERVICE_PRINCIPAL_CERTIFICATE,
        )

    @property
    def requires_config(self) -> bool:
        """Check if this method requires configuration."""
        return self != AuthMethod.AZURE_CLI


@dataclass(frozen=True)
class ServicePrincipalConfig:
    """Service principal authentication configuration.

    Security:
    - No client_secret storage - must come from environment
    - tenant_id and client_id validated as UUIDs
    - certificate_path validated if provided
    - Frozen to prevent mutation
    """

    tenant_id: str
    client_id: str
    certificate_path: str | None = None
    use_certificate: bool = False

    def __post_init__(self):
        """Validate UUIDs for tenant_id and client_id."""
        validate_uuid(self.tenant_id, "tenant_id")
        validate_uuid(self.client_id, "client_id")

        # Validate certificate path if using certificate auth
        if self.use_certificate and not self.certificate_path:
            raise ValueError("certificate_path required when use_certificate=True")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns dict with all non-secret fields.
        Safe for logging and config file storage.
        """
        return {
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "certificate_path": self.certificate_path,
            "use_certificate": self.use_certificate,
        }

    def to_dict_masked(self) -> dict[str, Any]:
        """Convert to dictionary with sensitive values masked.

        Returns dict safe for logging with secrets replaced by "****".
        """
        result = self.to_dict()
        # Mask certificate path if it contains sensitive directory names
        if self.certificate_path:
            cert_path = Path(self.certificate_path)
            result["certificate_path"] = f"****/{cert_path.name}"
        return result


@dataclass(frozen=True)
class ManagedIdentityConfig:
    """Managed identity authentication configuration.

    Optional client_id for user-assigned managed identity.
    If None, uses system-assigned managed identity.
    """

    client_id: str | None = None

    def __post_init__(self):
        """Validate client_id format if provided."""
        if self.client_id is not None:
            validate_uuid(self.client_id, "client_id")


@dataclass(frozen=True)
class AuthConfig:
    """Complete authentication configuration.

    Combines authentication method with method-specific configuration.
    Validates consistency between method and config.

    Security:
    - Immutable (frozen)
    - Validates method-config consistency
    - No secret storage
    """

    method: AuthMethod
    service_principal: ServicePrincipalConfig | None = None
    managed_identity: ManagedIdentityConfig | None = None

    def __post_init__(self):
        """Validate configuration consistency."""
        # Service principal methods require SP config
        if self.method.is_service_principal:
            if not self.service_principal:
                raise ValueError(f"{self.method.value} requires service_principal configuration")

            # Certificate method requires certificate path
            if (
                self.method == AuthMethod.SERVICE_PRINCIPAL_CERTIFICATE
                and not self.service_principal.use_certificate
            ):
                raise ValueError("SERVICE_PRINCIPAL_CERTIFICATE requires use_certificate=True")

        # Managed identity requires MI config
        if self.method == AuthMethod.MANAGED_IDENTITY and not self.managed_identity:
            raise ValueError(f"{self.method.value} requires managed_identity configuration")

        # Azure CLI should not have SP or MI config
        if self.method == AuthMethod.AZURE_CLI and (
            self.service_principal or self.managed_identity
        ):
            raise ValueError(
                "AZURE_CLI method should not have service_principal or "
                "managed_identity configuration"
            )


@dataclass
class AuthContext:
    """Runtime authentication context.

    Mutable dataclass for tracking authentication state during operations.
    Unlike config classes, this is NOT frozen as it tracks runtime state.
    """

    method: AuthMethod
    subscription_id: str | None = None
    resource_group: str | None = None
    credentials: Any | None = None

    def __post_init__(self):
        """Validate subscription_id if provided."""
        if self.subscription_id is not None:
            validate_uuid(self.subscription_id, "subscription_id")


@dataclass(frozen=True)
class ChainResult:
    """Result of authentication chain attempt.

    Returned by authentication chain to indicate success/failure
    and which method succeeded.
    """

    success: bool
    method: AuthMethod | None = None
    credentials: Any | None = None
    error: str | None = None
