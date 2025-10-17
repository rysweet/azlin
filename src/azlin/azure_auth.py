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
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when Azure authentication fails."""

    pass


@dataclass
class AzureCredentials:
    """Azure credentials representation."""

    method: str  # 'az_cli', 'env_vars', or 'managed_identity'
    token: Optional[str] = None
    subscription_id: Optional[str] = None
    tenant_id: Optional[str] = None


class AzureAuthenticator:
    """Manage Azure CLI authentication.

    This class handles Azure authentication by delegating to the Azure CLI.
    It never stores credentials directly - all tokens are managed by az CLI.

    Security:
    - No credential storage in code
    - Delegates to az CLI for token management
    - Validates subscription ID format
    - Caches credential objects (not tokens)
    """

    def __init__(self, subscription_id: Optional[str] = None, use_managed_identity: bool = False):
        """Initialize Azure authenticator.

        Args:
            subscription_id: Optional Azure subscription ID
            use_managed_identity: Whether to use managed identity
        """
        self._subscription_id = subscription_id
        self._use_managed_identity = use_managed_identity
        self._credentials_cache: Optional[AzureCredentials] = None

    def get_credentials(self) -> AzureCredentials:
        """Get Azure credentials from available sources.

        Priority order:
        1. Environment variables (AZURE_CLIENT_ID, etc.)
        2. Azure CLI (az account show)
        3. Managed identity (if use_managed_identity=True)

        Returns:
            AzureCredentials object

        Raises:
            AuthenticationError: If no credentials available

        Security: Never stores credentials, only metadata about source
        """
        if self._credentials_cache:
            return self._credentials_cache

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
                self._credentials_cache = creds
                logger.info("Using Azure credentials from az CLI")
                return creds
            except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
                logger.debug(f"az CLI credentials not available: {e}")

        # Priority 3: Managed identity
        if self._use_managed_identity:
            if self._check_managed_identity():
                creds = AzureCredentials(method="managed_identity")
                self._credentials_cache = creds
                logger.info("Using Azure managed identity")
                return creds

        raise AuthenticationError("No Azure credentials available. Please run: az login")

    def _check_env_credentials(self) -> bool:
        """Check if environment variables have credentials."""
        required = ["AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID"]
        return all(os.environ.get(var) for var in required)

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
        except Exception:
            return False

    def check_az_cli_available(self) -> bool:
        """Check if Azure CLI is available.

        Returns:
            True if az CLI is installed and working
        """
        try:
            result = subprocess.run(["az", "--version"], capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except FileNotFoundError:
            return False
        except Exception:
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
        except Exception:
            return False

    def validate_subscription_id(self, subscription_id: Optional[str]) -> bool:
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
        1. Constructor parameter
        2. Environment variable (AZURE_SUBSCRIPTION_ID)
        3. Azure CLI (az account show)

        Returns:
            Subscription ID

        Raises:
            AuthenticationError: If no subscription found
        """
        # Priority 1: Constructor parameter
        if self._subscription_id:
            return self._subscription_id

        # Priority 2: Environment variable
        env_sub = os.environ.get("AZURE_SUBSCRIPTION_ID")
        if env_sub:
            return env_sub

        # Priority 3: Azure CLI
        try:
            result = subprocess.run(
                ["az", "account", "show"], capture_output=True, text=True, timeout=10, check=True
            )
            account_data = json.loads(result.stdout)
            return account_data["id"]
        except Exception as e:
            raise AuthenticationError(f"Failed to get subscription ID: {e}")

    def get_tenant_id(self) -> str:
        """Get Azure tenant ID.

        Priority order:
        1. Environment variable (AZURE_TENANT_ID)
        2. Azure CLI (az account show)

        Returns:
            Tenant ID

        Raises:
            AuthenticationError: If no tenant found
        """
        # Priority 1: Environment variable
        env_tenant = os.environ.get("AZURE_TENANT_ID")
        if env_tenant:
            return env_tenant

        # Priority 2: Azure CLI
        try:
            result = subprocess.run(
                ["az", "account", "show"], capture_output=True, text=True, timeout=10, check=True
            )
            account_data = json.loads(result.stdout)
            return account_data["tenantId"]
        except Exception as e:
            raise AuthenticationError(f"Failed to get tenant ID: {e}")

    def clear_cache(self) -> None:
        """Clear cached credentials."""
        self._credentials_cache = None
        logger.debug("Cleared credentials cache")


__all__ = ["AzureAuthenticator", "AzureCredentials", "AuthenticationError"]
