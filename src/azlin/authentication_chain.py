"""Authentication chain with priority fallback.

This module implements the authentication chain pattern that tries multiple
authentication methods in priority order until one succeeds.

Priority Order:
1. Service Principal (if configured) - most explicit, highest priority
2. Azure CLI (default fallback) - backward compatible
3. Managed Identity (Azure-hosted environments) - lowest priority

Design Philosophy:
- Explicit configuration overrides auto-detection
- Azure CLI remains the default fallback (backward compatible)
- Fail-fast with clear error messages
- No retry logic (let Azure SDK handle retries)
"""

from azure.core.credentials import TokenCredential

from azlin.auth_models import AuthConfig, AuthMethod, ChainResult
from azlin.credential_factory import CredentialFactory, CredentialFactoryError
from azlin.log_sanitizer import LogSanitizer


class AuthenticationChainError(Exception):
    """Raised when authentication chain fails."""

    pass


class AuthenticationChain:
    """Execute authentication with priority-based fallback.

    The chain tries authentication methods in priority order:
    1. Configured method (if explicit config provided)
    2. Azure CLI fallback (if configured method fails)

    Security:
    - All errors sanitized to prevent secret leakage (SEC-005, SEC-010)
    - No token storage (delegates to Azure SDK)
    - Fail-fast on configuration errors
    """

    @staticmethod
    def authenticate(auth_config: AuthConfig) -> ChainResult:
        """Execute authentication chain with fallback.

        Args:
            auth_config: Authentication configuration

        Returns:
            ChainResult: Result with credentials or error

        Chain Logic:
        1. Try configured authentication method
        2. If that fails and it's not Azure CLI, fall back to Azure CLI
        3. If Azure CLI also fails, return failure

        Security:
        - All error messages sanitized
        - No secret leakage in chain result
        """
        # Try the configured method
        result = AuthenticationChain._try_method(auth_config)

        if result.success:
            return result

        # If configured method failed and it's not Azure CLI, try Azure CLI fallback
        if auth_config.method != AuthMethod.AZURE_CLI:
            # Create fallback config for Azure CLI
            fallback_config = AuthConfig(
                method=AuthMethod.AZURE_CLI,
                service_principal=None,
                managed_identity=None,
            )

            fallback_result = AuthenticationChain._try_method(fallback_config)

            if fallback_result.success:
                return fallback_result

            # Both methods failed - return the original error
            # (more useful than fallback error)
            return result

        # Only Azure CLI was tried and it failed
        return result

    @staticmethod
    def _try_method(auth_config: AuthConfig) -> ChainResult:
        """Try a single authentication method.

        Args:
            auth_config: Authentication configuration for this method

        Returns:
            ChainResult: Success with credentials or failure with error

        Security:
        - Catches all exceptions
        - Sanitizes error messages
        - No secret leakage
        """
        try:
            # Create credential using factory
            credentials = CredentialFactory.create_credential(auth_config)

            # Validate credentials work by requesting a token
            # This is a basic smoke test - doesn't validate subscription access
            if not AuthenticationChain._validate_credentials(credentials):
                error_msg = f"Credentials created but validation failed for method: {auth_config.method.value}"
                safe_error = LogSanitizer.sanitize(error_msg)
                return ChainResult(
                    success=False,
                    method=None,
                    credentials=None,
                    error=safe_error,
                )

            # Success - return credentials
            return ChainResult(
                success=True,
                method=auth_config.method,
                credentials=credentials,
                error=None,
            )

        except CredentialFactoryError as e:
            # Factory error - already sanitized
            return ChainResult(
                success=False,
                method=None,
                credentials=None,
                error=str(e),
            )
        except Exception as e:
            # Unexpected error - sanitize it
            safe_error = LogSanitizer.create_safe_error_message(
                e, f"Authentication failed for method {auth_config.method.value}"
            )
            return ChainResult(
                success=False,
                method=None,
                credentials=None,
                error=safe_error,
            )

    @staticmethod
    def _validate_credentials(credentials: TokenCredential) -> bool:
        """Validate credentials by attempting to get a token.

        This is a basic smoke test to ensure credentials are valid.
        It doesn't validate subscription access or permissions.

        Args:
            credentials: Azure Identity credential to validate

        Returns:
            True if credentials can obtain a token, False otherwise

        Note:
        - This is a lightweight check
        - Azure SDK will cache the token internally
        - No token storage in azlin
        """
        try:
            # Request token for Azure Resource Manager
            # This is the standard scope for Azure management operations
            token = credentials.get_token("https://management.azure.com/.default")

            # Check if we got a token
            if token and token.token:
                return True

            return False

        except (ValueError, TypeError, AttributeError) as e:
            # Invalid credential object or malformed token
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(f"Credential validation failed (invalid object): {e}")
            return False
        except Exception as e:
            # Azure SDK errors (ClientAuthenticationError, HttpResponseError, etc.)
            import logging
            import os

            logger = logging.getLogger(__name__)
            logger.debug(f"Token request failed: {e}")
            if os.getenv("AZLIN_DEV_MODE"):
                logger.error("Credential validation error details:", exc_info=True)
            return False

    @staticmethod
    def validate_subscription_access(
        credentials: TokenCredential, subscription_id: str | None
    ) -> bool:
        """Validate credentials have access to subscription.

        This is an extended validation that checks if credentials can
        access a specific subscription.

        Args:
            credentials: Azure Identity credential
            subscription_id: Subscription ID to validate

        Returns:
            True if credentials can access subscription, False otherwise

        Note:
        - This makes an actual Azure API call
        - Only call this when you need subscription validation
        - Basic credential validation (get_token) is usually sufficient
        """
        if not subscription_id:
            # Can't validate without subscription ID
            return True

        try:
            # Import here to avoid circular dependency
            from azure.mgmt.resource import SubscriptionClient

            # Create subscription client
            client = SubscriptionClient(credentials)

            # Try to get the subscription
            subscription = client.subscriptions.get(subscription_id)

            # If we can get the subscription, we have access
            return subscription is not None

        except ValueError as e:
            # Invalid subscription ID format
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(f"Subscription validation failed (invalid ID): {e}")
            return False
        except Exception as e:
            # Azure SDK errors (ResourceNotFoundError, AuthenticationError, etc.)
            import logging
            import os

            logger = logging.getLogger(__name__)
            logger.debug(f"Subscription access check failed: {e}")
            if os.getenv("AZLIN_DEV_MODE"):
                logger.error("Subscription validation error details:", exc_info=True)
            return False
