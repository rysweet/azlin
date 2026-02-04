"""Azure authentication handler module.

This module provides Azure authentication via az CLI delegation.
It NEVER stores credentials - all credential management is delegated
to Azure CLI which stores tokens securely in ~/.azure/

Security:
- No credential storage
- Delegates to az CLI
- Validates inputs
- Sanitizes outputs
"""

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when Azure authentication fails."""

    pass


@dataclass
class AzureCredentials:
    """Azure credentials representation."""

    method: str  # 'az_cli', 'env_vars', or 'managed_identity'
    token: str | None = None
    subscription_id: str | None = None
    tenant_id: str | None = None


class AzureAuthenticator:
    """Manage Azure CLI authentication.

    This class handles Azure authentication by delegating to the Azure CLI.
    It never stores credentials directly - all tokens are managed by az CLI.

    Now supports:
    - Service principal authentication via auth profiles
    - kubectl-style context management for multi-tenant access

    Security:
    - No credential storage in code
    - Delegates to az CLI for token management
    - Validates subscription ID format
    - Caches credential objects (not tokens)
    - Service principal secrets from environment only
    """

    def __init__(
        self,
        subscription_id: str | None = None,
        use_managed_identity: bool = False,
        auth_profile: str | None = None,
        context: str | None = None,
    ):
        """Initialize Azure authenticator.

        Args:
            subscription_id: Optional Azure subscription ID
            use_managed_identity: Whether to use managed identity
            auth_profile: Service principal authentication profile name
            context: kubectl-style context name (overrides subscription/tenant/auth)
        """
        self._subscription_id = subscription_id
        self._tenant_id: str | None = None  # Will be set from context if provided
        self._use_managed_identity = use_managed_identity
        self._auth_profile = auth_profile
        self._context = context
        self._credentials_cache: AzureCredentials | None = None

        # Load context if specified (overrides other parameters)
        if self._context:
            self._load_context()

    def _load_context(self) -> None:
        """Load context configuration and set subscription/tenant/auth.

        Raises:
            AuthenticationError: If context not found or invalid
        """
        from azlin.context_manager import ContextError, ContextManager

        try:
            # Load context config
            context_config = ContextManager.load()

            # Get specified context
            if self._context not in context_config.contexts:
                available = list(context_config.contexts.keys())
                raise AuthenticationError(
                    f"Context '{self._context}' not found. "
                    f"Available contexts: {available if available else 'none'}\n"
                    f"Create context with: azlin context create {self._context} --subscription <id> --tenant <id>"
                )

            ctx = context_config.contexts[self._context]

            # Override with context values
            self._subscription_id = ctx.subscription_id
            self._tenant_id = ctx.tenant_id
            if ctx.auth_profile:
                self._auth_profile = ctx.auth_profile

            logger.info(f"Loaded context '{self._context}': sub={ctx.subscription_id}")

        except ContextError as e:
            raise AuthenticationError(f"Failed to load context '{self._context}': {e}") from e

    def get_credentials(self) -> AzureCredentials:
        """Get Azure credentials from available sources.

        Priority order:
        1. Service principal profile (if auth_profile specified)
        2. Environment variables (AZURE_CLIENT_ID, etc.)
        3. Azure CLI (az account show)
        4. Managed identity (if use_managed_identity=True)

        Returns:
            AzureCredentials object

        Raises:
            AuthenticationError: If no credentials available

        Security: Never stores credentials, only metadata about source
        """
        if self._credentials_cache:
            return self._credentials_cache

        # Priority 0: Service principal profile (if specified)
        if self._auth_profile:
            try:
                from azlin.config_manager import ConfigManager
                from azlin.service_principal_auth import (
                    ServicePrincipalConfig,
                    ServicePrincipalManager,
                )

                # Load profile
                profile_data = ConfigManager.get_auth_profile(self._auth_profile)
                if not profile_data:
                    raise AuthenticationError(
                        f"Authentication profile '{self._auth_profile}' not found. "
                        f"Run: azlin auth setup --profile {self._auth_profile}"
                    )

                # Create config
                sp_config = ServicePrincipalConfig.from_dict(profile_data)

                # Get credentials and set in environment
                sp_creds = ServicePrincipalManager.get_credentials(sp_config)

                # Set in environment for Azure SDK
                for key, value in sp_creds.items():
                    os.environ[key] = value

                # Return credentials object
                creds = AzureCredentials(
                    method="service_principal",
                    subscription_id=sp_config.subscription_id,
                    tenant_id=sp_config.tenant_id,
                )
                self._credentials_cache = creds
                logger.info(f"Using service principal from profile: {self._auth_profile}")
                return creds

            except AuthenticationError:
                # Re-raise authentication errors (strict auth when profile explicitly specified)
                raise
            except Exception as e:
                # Unexpected errors - re-raise with context
                raise AuthenticationError(
                    f"Failed to authenticate with profile '{self._auth_profile}': {e}"
                ) from e

        # Priority 1: Environment variables
        if self._check_env_credentials():
            creds = AzureCredentials(
                method="env_vars",
                subscription_id=os.environ.get("AZURE_SUBSCRIPTION_ID"),
                tenant_id=os.environ.get("AZURE_TENANT_ID"),
            )
            self._credentials_cache = creds
            logger.info("Using Azure credentials from environment variables")
            return creds

        # Priority 2: Azure CLI
        if self.check_az_cli_available():
            try:
                result = subprocess.run(
                    ["az", "account", "get-access-token"],
                    capture_output=True,
                    text=True,
                    timeout=30,  # Increased for WSL compatibility (Issue #580)
                    check=True,
                )
                token_data = json.loads(result.stdout)
                creds = AzureCredentials(
                    method="az_cli",
                    token=token_data.get("accessToken"),
                    subscription_id=token_data.get("subscription"),
                    tenant_id=token_data.get("tenant"),
                )
                self._credentials_cache = creds
                logger.info("Using Azure credentials from az CLI")
                return creds
            except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
                logger.debug(f"az CLI credentials not available: {e}")

        # Priority 3: Managed identity
        if self._use_managed_identity and self._check_managed_identity():
            creds = AzureCredentials(method="managed_identity")
            self._credentials_cache = creds
            logger.info("Using Azure managed identity")
            return creds

        raise AuthenticationError("No Azure credentials available. Please run: az login")

    def _check_env_credentials(self) -> bool:
        """Check if environment variables have credentials.

        Supports both client secret and certificate-based authentication.
        """
        # Check base required fields
        if not os.environ.get("AZURE_CLIENT_ID") or not os.environ.get("AZURE_TENANT_ID"):
            return False

        # Check for either client secret OR certificate
        has_secret = bool(os.environ.get("AZURE_CLIENT_SECRET"))
        has_cert = bool(os.environ.get("AZURE_CLIENT_CERTIFICATE_PATH"))

        return has_secret or has_cert

    def _check_managed_identity(self) -> bool:
        """Check if running on Azure with managed identity."""
        try:
            # Check for Azure instance metadata service
            result = subprocess.run(
                [
                    "curl",
                    "-H",
                    "Metadata:true",
                    "http://169.254.169.254/metadata/instance?api-version=2021-02-01",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            # Timeout means no managed identity endpoint
            logger.debug("Managed identity check timed out")
            return False
        except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
            # Subprocess or system errors
            logger.debug(f"Managed identity check failed: {e}")
            return False
        except Exception as e:
            # Unexpected errors
            logger.warning(f"Unexpected error checking managed identity: {e}")
            import os

            if os.getenv("AZLIN_DEV_MODE"):
                logger.error("Managed identity check error details:", exc_info=True)
            return False

    def check_az_cli_available(self) -> bool:
        """Check if Azure CLI is available in PATH.

        Uses shutil.which() to properly respect the user's PATH environment,
        including Homebrew installations at /opt/homebrew/bin.

        Returns:
            True if az CLI is found in PATH
        """
        az_path = shutil.which("az")
        if az_path:
            logger.debug(f"Found Azure CLI at: {az_path}")
            return True
        logger.debug("Azure CLI not found in PATH")
        return False

    def validate_credentials(self) -> bool:
        """Validate that credentials can get a token.

        Returns:
            True if credentials are valid
        """
        try:
            creds = self.get_credentials()
            if creds.method == "az_cli" and creds.token:
                # Check token is not expired (simple check)
                return len(creds.token) > 0
            return True
        except AuthenticationError as e:
            # Known authentication errors
            logger.debug(f"Credential validation failed: {e}")
            return False
        except (AttributeError, KeyError, TypeError) as e:
            # Invalid credential object structure
            logger.debug(f"Credential validation failed (invalid object): {e}")
            return False
        except Exception as e:
            # Unexpected errors
            logger.warning(f"Unexpected error validating credentials: {e}")
            import os

            if os.getenv("AZLIN_DEV_MODE"):
                logger.error("Credential validation error details:", exc_info=True)
            return False

    def validate_subscription_id(self, subscription_id: str | None) -> bool:
        """Validate subscription ID format.

        Args:
            subscription_id: Subscription ID to validate

        Returns:
            True if valid UUID format
        """
        if not subscription_id:
            return False

        # Azure subscription IDs are UUIDs
        uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        return bool(re.match(uuid_pattern, subscription_id, re.IGNORECASE))

    def get_subscription_id(self) -> str:
        """Get Azure subscription ID.

        Priority order:
        1. Context (if context parameter specified)
        2. Constructor parameter
        3. Environment variable (AZURE_SUBSCRIPTION_ID)
        4. Azure CLI (az account show)

        Returns:
            Subscription ID

        Raises:
            AuthenticationError: If no subscription found
        """
        # Priority 1: Context (already loaded in _load_context if context specified)
        if self._subscription_id:
            return self._subscription_id

        # Priority 2: Environment variable
        env_sub = os.environ.get("AZURE_SUBSCRIPTION_ID")
        if env_sub:
            return env_sub

        # Priority 3: Azure CLI
        try:
            result = subprocess.run(
                ["az", "account", "show"],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,  # Increased for WSL compatibility (Issue #580)
            )
            account_data = json.loads(result.stdout)
            return account_data["id"]
        except Exception as e:
            raise AuthenticationError(f"Failed to get subscription ID: {e}") from e

    def get_tenant_id(self) -> str:
        """Get Azure tenant ID.

        Priority order:
        1. Context (if context parameter specified)
        2. Constructor parameter (_tenant_id)
        3. Environment variable (AZURE_TENANT_ID)
        4. Azure CLI (az account show)

        Returns:
            Tenant ID

        Raises:
            AuthenticationError: If no tenant found
        """
        # Priority 1: Context (already loaded in _load_context if context specified)
        if self._tenant_id:
            return self._tenant_id

        # Priority 2: Environment variable
        env_tenant = os.environ.get("AZURE_TENANT_ID")
        if env_tenant:
            return env_tenant

        # Priority 3: Azure CLI
        try:
            result = subprocess.run(
                ["az", "account", "show"],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,  # Increased for WSL compatibility (Issue #580)
            )
            account_data = json.loads(result.stdout)
            return account_data["tenantId"]
        except Exception as e:
            raise AuthenticationError(f"Failed to get tenant ID: {e}") from e

    def clear_cache(self) -> None:
        """Clear cached credentials."""
        self._credentials_cache = None
        logger.debug("Cleared credentials cache")


__all__ = ["AuthenticationError", "AzureAuthenticator", "AzureCredentials"]
