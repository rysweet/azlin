"""Authentication resolver module.

This module determines the authentication method and resolves credentials for Azure operations.
It supports multiple authentication methods while maintaining backward compatibility with
existing Azure CLI delegation patterns.

Supported Authentication Methods:
- az_cli: Delegate to Azure CLI (default, maintains backward compatibility)
- service_principal_secret: Service principal with client secret
- service_principal_cert: Service principal with certificate
- managed_identity: Azure managed identity

Security Features (P0):
- Delegates to Azure SDK for credential management (no token storage)
- Validates certificates before use (via Brick 3: cert_handler)
- Validates UUIDs for Azure IDs (via Brick 7: auth_security)
- Sanitizes all log messages (via Brick 7: auth_security)
- Never logs credentials or secrets

Design Philosophy:
- Ruthless simplicity: delegate to Azure SDKs, don't reimplement
- Self-contained module with clear boundaries
- Fail fast on invalid config or credentials
- Quality over speed: robust error handling
"""

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass

from azure.identity import (
    CertificateCredential,
    ClientSecretCredential,
    ManagedIdentityCredential,
)

from azlin.auth_security import sanitize_log, validate_uuid
from azlin.cert_handler import validate_certificate
from azlin.config_auth import AuthConfig

logger = logging.getLogger(__name__)


class AuthResolverError(Exception):
    """Raised when authentication resolution fails."""

    pass


@dataclass
class AzureCredentials:
    """Azure credentials representation.

    This dataclass maintains compatibility with the existing AzureCredentials
    from azure_auth.py while supporting new authentication methods.

    Attributes:
        method: Authentication method used ('az_cli', 'service_principal_secret',
                'service_principal_cert', 'managed_identity')
        token: Access token (if available)
        subscription_id: Azure subscription ID
        tenant_id: Azure tenant ID
    """

    method: str
    token: str | None = None
    subscription_id: str | None = None
    tenant_id: str | None = None


class AuthResolver:
    """Resolve authentication method and get credentials.

    This class determines the appropriate authentication method based on
    configuration and resolves credentials accordingly. It integrates with:
    - Brick 1 (config_auth): Load configuration
    - Brick 3 (cert_handler): Validate certificates
    - Brick 7 (auth_security): Validate UUIDs and sanitize logs

    For az_cli method, it delegates to the existing AzureAuthenticator pattern
    to maintain backward compatibility.
    """

    def __init__(self, config: AuthConfig):
        """Initialize AuthResolver with configuration.

        Args:
            config: Authentication configuration from load_auth_config()
        """
        self.config = config

    def resolve_credentials(self) -> AzureCredentials:
        """Get Azure credentials based on auth method.

        Routes to appropriate credential provider:
        - az_cli: Delegate to Azure CLI (existing pattern)
        - service_principal_secret: Use ClientSecretCredential
        - service_principal_cert: Use CertificateCredential
        - managed_identity: Use ManagedIdentityCredential

        Returns:
            AzureCredentials object with authentication details

        Raises:
            AuthResolverError: If authentication fails or config is invalid

        Security:
            - Validates UUIDs before use
            - Validates certificates before use
            - Sanitizes all log messages
            - Never logs secrets
        """
        method = self.config.auth_method

        logger.debug(sanitize_log(f"Resolving credentials for method: {method}"))

        if method == "az_cli":
            return self._resolve_az_cli()
        if method == "service_principal_secret":
            return self._resolve_service_principal_secret()
        if method == "service_principal_cert":
            return self._resolve_service_principal_cert()
        if method == "managed_identity":
            return self._resolve_managed_identity()
        raise AuthResolverError(
            f"Unsupported authentication method: {method}. "
            f"Supported methods: az_cli, service_principal_secret, "
            f"service_principal_cert, managed_identity"
        )

    def _resolve_az_cli(self) -> AzureCredentials:
        """Resolve credentials using Azure CLI.

        Delegates to Azure CLI following the existing pattern from
        azure_auth.py to maintain backward compatibility.

        Returns:
            AzureCredentials with az_cli method

        Raises:
            AuthResolverError: If Azure CLI is not available or not logged in
        """
        # Check if az CLI is available
        az_path = shutil.which("az")
        if not az_path:
            raise AuthResolverError(
                "Azure CLI not available. Install from: https://docs.microsoft.com/cli/azure/install-azure-cli"
            )

        logger.debug(f"Found Azure CLI at: {az_path}")

        # Get access token from az CLI
        try:
            result = subprocess.run(
                ["az", "account", "get-access-token"],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            token_data = json.loads(result.stdout)

            creds = AzureCredentials(
                method="az_cli",
                token=token_data.get("accessToken"),
                subscription_id=token_data.get("subscription"),
                tenant_id=token_data.get("tenant"),
            )

            logger.info("Successfully resolved credentials using Azure CLI")
            return creds

        except subprocess.CalledProcessError as e:
            raise AuthResolverError("Azure CLI authentication failed. Please run: az login") from e
        except json.JSONDecodeError as e:
            raise AuthResolverError("Failed to parse Azure CLI response") from e
        except Exception as e:
            raise AuthResolverError(f"Unexpected error resolving Azure CLI credentials: {e}") from e

    def _resolve_service_principal_secret(self) -> AzureCredentials:
        """Resolve credentials using service principal with client secret.

        Uses Azure Identity SDK's ClientSecretCredential.

        Returns:
            AzureCredentials with service_principal_secret method

        Raises:
            AuthResolverError: If required fields missing or authentication fails

        Security:
            - Validates tenant_id and client_id as UUIDs
            - Never logs client_secret
        """
        # Validate required fields
        if not self.config.tenant_id:
            raise AuthResolverError(
                "tenant_id is required for service_principal_secret authentication"
            )
        if not self.config.client_id:
            raise AuthResolverError(
                "client_id is required for service_principal_secret authentication"
            )
        if not self.config.client_secret:
            raise AuthResolverError(
                "client_secret is required for service_principal_secret authentication"
            )

        # Validate UUIDs using Brick 7 (auth_security)
        tenant_validation = validate_uuid(self.config.tenant_id, "tenant_id")
        if not tenant_validation.valid:
            raise AuthResolverError(tenant_validation.error)

        client_validation = validate_uuid(self.config.client_id, "client_id")
        if not client_validation.valid:
            raise AuthResolverError(client_validation.error)

        logger.debug(
            sanitize_log(
                f"Authenticating with service principal: tenant={self.config.tenant_id}, "
                f"client={self.config.client_id}"
            )
        )

        try:
            # Use Azure Identity SDK
            credential = ClientSecretCredential(
                tenant_id=self.config.tenant_id,
                client_id=self.config.client_id,
                client_secret=self.config.client_secret,
            )

            # Get token to validate credentials
            token_response = credential.get_token("https://management.azure.com/.default")

            creds = AzureCredentials(
                method="service_principal_secret",
                token=token_response.token,
                subscription_id=self.config.subscription_id,
                tenant_id=self.config.tenant_id,
            )

            logger.info("Successfully resolved credentials using service principal secret")
            return creds

        except Exception as e:
            # Sanitize error message
            error_msg = sanitize_log(str(e))
            raise AuthResolverError(
                f"Failed to authenticate with service principal: {error_msg}"
            ) from e

    def _resolve_service_principal_cert(self) -> AzureCredentials:
        """Resolve credentials using service principal with certificate.

        Uses Azure Identity SDK's CertificateCredential. Validates certificate
        using Brick 3 (cert_handler) before use.

        Returns:
            AzureCredentials with service_principal_cert method

        Raises:
            AuthResolverError: If required fields missing, certificate invalid,
                             or authentication fails

        Security:
            - Validates certificate using cert_handler (Brick 3)
            - Validates tenant_id and client_id as UUIDs
            - Warns on insecure certificate permissions
        """
        # Validate required fields
        if not self.config.tenant_id:
            raise AuthResolverError(
                "tenant_id is required for service_principal_cert authentication"
            )
        if not self.config.client_id:
            raise AuthResolverError(
                "client_id is required for service_principal_cert authentication"
            )
        if not self.config.client_certificate_path:
            raise AuthResolverError(
                "client_certificate_path is required for service_principal_cert authentication"
            )

        # Validate UUIDs using Brick 7 (auth_security)
        tenant_validation = validate_uuid(self.config.tenant_id, "tenant_id")
        if not tenant_validation.valid:
            raise AuthResolverError(tenant_validation.error)

        client_validation = validate_uuid(self.config.client_id, "client_id")
        if not client_validation.valid:
            raise AuthResolverError(client_validation.error)

        # Validate certificate using Brick 3 (cert_handler)
        cert_validation = validate_certificate(self.config.client_certificate_path)
        if not cert_validation.valid:
            errors = "; ".join(cert_validation.errors)
            raise AuthResolverError(f"Certificate validation failed: {errors}")

        # Log warnings if any
        for warning in cert_validation.warnings:
            logger.warning(sanitize_log(warning))

        logger.debug(
            sanitize_log(
                f"Authenticating with service principal certificate: "
                f"tenant={self.config.tenant_id}, client={self.config.client_id}, "
                f"cert={self.config.client_certificate_path}"
            )
        )

        try:
            # Use Azure Identity SDK
            credential = CertificateCredential(
                tenant_id=self.config.tenant_id,
                client_id=self.config.client_id,
                certificate_path=self.config.client_certificate_path,
            )

            # Get token to validate credentials
            token_response = credential.get_token("https://management.azure.com/.default")

            creds = AzureCredentials(
                method="service_principal_cert",
                token=token_response.token,
                subscription_id=self.config.subscription_id,
                tenant_id=self.config.tenant_id,
            )

            logger.info("Successfully resolved credentials using service principal certificate")
            return creds

        except Exception as e:
            # Sanitize error message
            error_msg = sanitize_log(str(e))
            raise AuthResolverError(
                f"Failed to authenticate with service principal certificate: {error_msg}"
            ) from e

    def _resolve_managed_identity(self) -> AzureCredentials:
        """Resolve credentials using managed identity.

        Uses Azure Identity SDK's ManagedIdentityCredential. This method
        is used when running on Azure resources with managed identity enabled
        (e.g., Azure VMs, App Service, Functions).

        Returns:
            AzureCredentials with managed_identity method

        Raises:
            AuthResolverError: If managed identity not available or authentication fails

        Security:
            - Validates client_id if provided
            - No secrets required (managed by Azure)
        """
        # Validate client_id if provided (user-assigned managed identity)
        if self.config.client_id:
            client_validation = validate_uuid(self.config.client_id, "client_id")
            if not client_validation.valid:
                raise AuthResolverError(client_validation.error)

        logger.debug("Authenticating with managed identity")

        try:
            # Use Azure Identity SDK
            # If client_id provided, use user-assigned managed identity
            if self.config.client_id:
                credential = ManagedIdentityCredential(client_id=self.config.client_id)
                logger.debug(f"Using user-assigned managed identity: {self.config.client_id}")
            else:
                credential = ManagedIdentityCredential()
                logger.debug("Using system-assigned managed identity")

            # Get token to validate credentials
            token_response = credential.get_token("https://management.azure.com/.default")

            creds = AzureCredentials(
                method="managed_identity",
                token=token_response.token,
                subscription_id=self.config.subscription_id,
                tenant_id=self.config.tenant_id,
            )

            logger.info("Successfully resolved credentials using managed identity")
            return creds

        except Exception as e:
            # Sanitize error message
            error_msg = sanitize_log(str(e))
            raise AuthResolverError(
                f"Failed to authenticate with managed identity: {error_msg}. "
                f"Ensure you are running on an Azure resource with managed identity enabled."
            ) from e

    def validate_credentials(self) -> bool:
        """Validate that credentials work (can get token).

        Attempts to resolve credentials and returns True if successful,
        False otherwise. Does not raise exceptions.

        Returns:
            True if credentials are valid, False otherwise
        """
        try:
            creds = self.resolve_credentials()
            # If we got credentials with a token, they're valid
            if creds.token:
                return True
            # For methods that might not have token immediately, just
            # getting credentials without error means they're valid
            return True
        except Exception as e:
            logger.debug(sanitize_log(f"Credential validation failed: {e}"))
            return False

    def get_subscription_id(self) -> str:
        """Get subscription ID from config or Azure.

        Priority order:
        1. Config (from load_auth_config)
        2. Environment variable (AZURE_SUBSCRIPTION_ID)
        3. Azure CLI (az account show)

        Returns:
            Subscription ID

        Raises:
            AuthResolverError: If no subscription ID available
        """
        # Priority 1: Config
        if self.config.subscription_id:
            return self.config.subscription_id

        # Priority 2: Environment variable
        env_sub = os.environ.get("AZURE_SUBSCRIPTION_ID")
        if env_sub:
            return env_sub

        # Priority 3: Azure CLI
        if self.config.auth_method == "az_cli" or shutil.which("az"):
            try:
                result = subprocess.run(
                    ["az", "account", "show"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
                account_data = json.loads(result.stdout)
                return account_data["id"]
            except Exception as e:
                raise AuthResolverError(f"Failed to get subscription ID from Azure CLI: {e}") from e

        raise AuthResolverError(
            "Subscription ID not found. Please set AZURE_SUBSCRIPTION_ID "
            "environment variable or configure it in your profile."
        )

    def get_tenant_id(self) -> str:
        """Get tenant ID from config or Azure.

        Priority order:
        1. Config (from load_auth_config)
        2. Environment variable (AZURE_TENANT_ID)
        3. Azure CLI (az account show)

        Returns:
            Tenant ID

        Raises:
            AuthResolverError: If no tenant ID available
        """
        # Priority 1: Config
        if self.config.tenant_id:
            return self.config.tenant_id

        # Priority 2: Environment variable
        env_tenant = os.environ.get("AZURE_TENANT_ID")
        if env_tenant:
            return env_tenant

        # Priority 3: Azure CLI
        if self.config.auth_method == "az_cli" or shutil.which("az"):
            try:
                result = subprocess.run(
                    ["az", "account", "show"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
                account_data = json.loads(result.stdout)
                return account_data["tenantId"]
            except Exception as e:
                raise AuthResolverError(f"Failed to get tenant ID from Azure CLI: {e}") from e

        raise AuthResolverError(
            "Tenant ID not found. Please set AZURE_TENANT_ID "
            "environment variable or configure it in your profile."
        )


__all__ = [
    "AuthResolver",
    "AuthResolverError",
    "AzureCredentials",
]
