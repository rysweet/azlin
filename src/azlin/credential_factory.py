"""Credential factory for Azure authentication.

This module creates Azure Identity SDK credential objects from authentication
configuration. It acts as a bridge between azlin's configuration models and
Azure SDK credential types.

Supported credential types:
- AzureCliCredential: Delegate to Azure CLI (default, backward compatible)
- ClientSecretCredential: Service principal with client secret
- CertificateCredential: Service principal with certificate
- ManagedIdentityCredential: Managed identity (system or user-assigned)

Security:
- No token storage - delegates to Azure Identity SDK
- Client secrets from environment variables only (SEC-001)
- Certificate validation before use (SEC-003, SEC-004)
- Log sanitization for all error messages (SEC-005, SEC-010)
"""

import os
from pathlib import Path
from typing import Any

from azure.identity import (
    AzureCliCredential,
    CertificateCredential,
    ClientSecretCredential,
    ManagedIdentityCredential,
)

from azlin.auth_models import (
    AuthConfig,
    AuthMethod,
    ManagedIdentityConfig,
    ServicePrincipalConfig,
)
from azlin.certificate_validator import CertificateValidator
from azlin.log_sanitizer import LogSanitizer


class CredentialFactoryError(Exception):
    """Raised when credential creation fails."""

    pass


class CredentialFactory:
    """Factory for creating Azure Identity credentials.

    Maps AuthConfig to appropriate Azure Identity SDK credential types.
    Enforces security controls and validates configuration before creating credentials.

    Philosophy:
    - Ruthless simplicity: delegate to Azure SDK, don't reinvent
    - Security first: no token storage, validate everything
    - Fail-fast: catch configuration errors immediately
    """

    @staticmethod
    def create_credential(auth_config: AuthConfig) -> Any:
        """Create Azure Identity credential from configuration.

        Args:
            auth_config: Authentication configuration

        Returns:
            Azure Identity credential object (TokenCredential)

        Raises:
            CredentialFactoryError: If credential creation fails
            ValueError: If configuration is invalid

        Security:
        - SEC-001: Secrets from environment only
        - SEC-003/004: Certificate validation
        - SEC-005/010: Log sanitization
        """
        try:
            # Route to appropriate credential factory method
            if auth_config.method == AuthMethod.AZURE_CLI:
                return CredentialFactory._create_cli_credential()

            elif auth_config.method == AuthMethod.SERVICE_PRINCIPAL_SECRET:
                if not auth_config.service_principal:
                    raise CredentialFactoryError(
                        "SERVICE_PRINCIPAL_SECRET requires service_principal configuration"
                    )
                return CredentialFactory._create_sp_secret_credential(
                    auth_config.service_principal
                )

            elif auth_config.method == AuthMethod.SERVICE_PRINCIPAL_CERTIFICATE:
                if not auth_config.service_principal:
                    raise CredentialFactoryError(
                        "SERVICE_PRINCIPAL_CERTIFICATE requires service_principal configuration"
                    )
                return CredentialFactory._create_sp_cert_credential(
                    auth_config.service_principal
                )

            elif auth_config.method == AuthMethod.MANAGED_IDENTITY:
                return CredentialFactory._create_managed_identity_credential(
                    auth_config.managed_identity
                )

            else:
                raise CredentialFactoryError(
                    f"Unsupported authentication method: {auth_config.method}"
                )

        except Exception as e:
            # Sanitize error messages to prevent secret leakage
            safe_error = LogSanitizer.create_safe_error_message(
                e, "Credential creation failed"
            )
            raise CredentialFactoryError(safe_error) from e

    @staticmethod
    def _create_cli_credential() -> AzureCliCredential:
        """Create Azure CLI credential.

        This preserves existing azlin behavior - delegate authentication to az CLI.

        Returns:
            AzureCliCredential: Credential that uses Azure CLI

        Raises:
            CredentialFactoryError: If Azure CLI is not available

        Backward Compatibility:
        This is the default authentication method, unchanged from existing behavior.
        """
        try:
            credential = AzureCliCredential()
            return credential
        except Exception as e:
            safe_error = LogSanitizer.sanitize_exception(e)
            raise CredentialFactoryError(
                f"Failed to create Azure CLI credential. "
                f"Is Azure CLI installed and authenticated? Error: {safe_error}"
            ) from e

    @staticmethod
    def _create_sp_secret_credential(
        config: ServicePrincipalConfig,
    ) -> ClientSecretCredential:
        """Create service principal credential with client secret.

        Security (SEC-001): Client secret MUST come from environment variables:
        - AZURE_CLIENT_SECRET (standard Azure SDK variable)
        - AZLIN_SP_CLIENT_SECRET (azlin-specific alternative)

        Args:
            config: Service principal configuration

        Returns:
            ClientSecretCredential: Credential with client secret

        Raises:
            CredentialFactoryError: If client secret not found in environment
        """
        # Get client secret from environment (SEC-001: no secret storage)
        client_secret = os.getenv("AZURE_CLIENT_SECRET") or os.getenv(
            "AZLIN_SP_CLIENT_SECRET"
        )

        if not client_secret:
            raise CredentialFactoryError(
                "Client secret not found in environment. "
                "Set AZURE_CLIENT_SECRET or AZLIN_SP_CLIENT_SECRET environment variable."
            )

        try:
            credential = ClientSecretCredential(
                tenant_id=config.tenant_id,
                client_id=config.client_id,
                client_secret=client_secret,
            )
            return credential
        except Exception as e:
            # Sanitize error to prevent secret leakage (SEC-005, SEC-010)
            safe_error = LogSanitizer.sanitize_exception(e)
            raise CredentialFactoryError(
                f"Failed to create service principal credential: {safe_error}"
            ) from e

    @staticmethod
    def _create_sp_cert_credential(
        config: ServicePrincipalConfig,
    ) -> CertificateCredential:
        """Create service principal credential with certificate.

        Security:
        - SEC-003: Validates certificate permissions (0600/0400)
        - SEC-004: Checks certificate expiration (warns if <30 days)

        Args:
            config: Service principal configuration with certificate

        Returns:
            CertificateCredential: Credential with certificate

        Raises:
            CredentialFactoryError: If certificate validation fails
        """
        if not config.certificate_path:
            raise CredentialFactoryError(
                "Certificate path required for certificate-based authentication"
            )

        cert_path = Path(config.certificate_path)

        # Validate certificate (SEC-003, SEC-004)
        validation = CertificateValidator.validate_certificate(cert_path)

        if not validation.valid:
            error_messages = "; ".join(validation.errors)
            raise CredentialFactoryError(
                f"Certificate validation failed: {error_messages}"
            )

        # Warn about expiration but don't fail
        if validation.expiration_status == "expiring_soon" and validation.warnings:
            import warnings

            for warning in validation.warnings:
                warnings.warn(warning, UserWarning, stacklevel=2)

        # Create certificate credential
        try:
            credential = CertificateCredential(
                tenant_id=config.tenant_id,
                client_id=config.client_id,
                certificate_path=str(cert_path),
            )
            return credential
        except Exception as e:
            safe_error = LogSanitizer.sanitize_exception(e)
            raise CredentialFactoryError(
                f"Failed to create certificate credential: {safe_error}"
            ) from e

    @staticmethod
    def _create_managed_identity_credential(
        config: ManagedIdentityConfig | None = None,
    ) -> ManagedIdentityCredential:
        """Create managed identity credential.

        Supports both system-assigned and user-assigned managed identities:
        - System-assigned: No client_id (default)
        - User-assigned: Requires client_id

        Args:
            config: Optional managed identity configuration

        Returns:
            ManagedIdentityCredential: Credential for managed identity

        Raises:
            CredentialFactoryError: If credential creation fails
        """
        try:
            if config and config.client_id:
                # User-assigned managed identity
                credential = ManagedIdentityCredential(client_id=config.client_id)
            else:
                # System-assigned managed identity
                credential = ManagedIdentityCredential()

            return credential
        except Exception as e:
            safe_error = LogSanitizer.sanitize_exception(e)
            raise CredentialFactoryError(
                f"Failed to create managed identity credential: {safe_error}"
            ) from e
