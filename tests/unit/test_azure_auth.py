"""
Unit tests for Azure authentication module.

Tests Azure credential detection, validation, and caching (TDD - RED phase).

Test Coverage:
- Credential detection via az CLI
- Credential detection via managed identity
- Credential detection via environment variables
- Token validation
- Credential caching
- Error handling for missing credentials
- Subscription ID detection
"""

from unittest.mock import Mock, patch

import pytest

# ============================================================================
# CREDENTIAL DETECTION TESTS
# ============================================================================


class TestAzureCredentialDetection:
    """Test Azure credential detection from various sources."""

    @patch("subprocess.run")
    def test_detects_az_cli_credentials(self, mock_run):
        """Test detection of az CLI credentials.

        RED PHASE: This test will fail - no implementation yet.
        """
        from azlin.azure_auth import AzureAuthenticator

        # Mock az CLI returning credentials
        mock_run.return_value = Mock(
            returncode=0, stdout='{"accessToken": "token123", "expiresOn": "2024-12-31"}', stderr=""
        )

        auth = AzureAuthenticator()
        credentials = auth.get_credentials()

        assert credentials is not None
        assert credentials.method == "az_cli"
        assert credentials.token is not None

    @patch(
        "os.environ",
        {
            "AZURE_CLIENT_ID": "client-id",
            "AZURE_CLIENT_SECRET": "secret",
            "AZURE_TENANT_ID": "tenant-id",
        },
    )
    def test_detects_environment_variable_credentials(self):
        """Test detection of credentials from environment variables."""
        from azlin.azure_auth import AzureAuthenticator

        auth = AzureAuthenticator()
        credentials = auth.get_credentials()

        assert credentials is not None
        assert credentials.method == "env_vars"

    @patch("subprocess.run")
    def test_detects_managed_identity(self, mock_run):
        """Test detection of Azure managed identity."""
        from azlin.azure_auth import AzureAuthenticator

        # Simulate being on Azure VM
        mock_run.return_value = Mock(returncode=0, stdout="instance metadata")

        auth = AzureAuthenticator(use_managed_identity=True)
        credentials = auth.get_credentials()

        assert credentials is not None
        assert credentials.method == "managed_identity"

    def test_credential_detection_priority_order(self):
        """Test that credentials are detected in priority order.

        Priority: env_vars > az_cli > managed_identity
        """
        from azlin.azure_auth import AzureAuthenticator

        with patch.dict(
            "os.environ",
            {
                "AZURE_CLIENT_ID": "client-id",
                "AZURE_CLIENT_SECRET": "secret",
                "AZURE_TENANT_ID": "tenant-id",
            },
        ):
            auth = AzureAuthenticator()
            credentials = auth.get_credentials()

            # Should prefer environment variables
            assert credentials.method == "env_vars"


# ============================================================================
# CREDENTIAL VALIDATION TESTS
# ============================================================================


class TestAzureCredentialValidation:
    """Test Azure credential validation."""

    @patch("azure.identity.DefaultAzureCredential")
    def test_validates_credential_can_get_token(self, mock_credential):
        """Test that credentials can successfully get a token."""
        from azlin.azure_auth import AzureAuthenticator

        mock_cred = Mock()
        mock_cred.get_token.return_value = Mock(token="valid-token", expires_on=9999999999)
        mock_credential.return_value = mock_cred

        auth = AzureAuthenticator()
        is_valid = auth.validate_credentials()

        assert is_valid is True

    @patch("azure.identity.DefaultAzureCredential")
    def test_detects_invalid_credentials(self, mock_credential):
        """Test detection of invalid credentials."""
        from azlin.azure_auth import AzureAuthenticator

        mock_cred = Mock()
        mock_cred.get_token.side_effect = Exception("Authentication failed")
        mock_credential.return_value = mock_cred

        auth = AzureAuthenticator()
        is_valid = auth.validate_credentials()

        assert is_valid is False

    def test_validates_subscription_id(self):
        """Test validation of subscription ID format."""
        from azlin.azure_auth import AzureAuthenticator

        auth = AzureAuthenticator()

        # Valid UUID format
        assert auth.validate_subscription_id("12345678-1234-1234-1234-123456789012") is True

        # Invalid formats
        assert auth.validate_subscription_id("invalid") is False
        assert auth.validate_subscription_id("") is False
        assert auth.validate_subscription_id(None) is False


# ============================================================================
# CREDENTIAL CACHING TESTS
# ============================================================================


class TestAzureCredentialCaching:
    """Test credential caching functionality."""

    @patch("azure.identity.DefaultAzureCredential")
    def test_caches_credentials_after_first_retrieval(self, mock_credential):
        """Test that credentials are cached after first retrieval."""
        from azlin.azure_auth import AzureAuthenticator

        mock_cred = Mock()
        mock_credential.return_value = mock_cred

        auth = AzureAuthenticator()

        # First call
        cred1 = auth.get_credentials()
        # Second call
        cred2 = auth.get_credentials()

        # Should return same instance
        assert cred1 is cred2

        # DefaultAzureCredential should only be called once
        assert mock_credential.call_count == 1

    def test_can_clear_credential_cache(self):
        """Test that credential cache can be cleared."""
        from azlin.azure_auth import AzureAuthenticator

        with patch("azure.identity.DefaultAzureCredential") as mock_credential:
            auth = AzureAuthenticator()

            # Get credentials
            auth.get_credentials()

            # Clear cache
            auth.clear_cache()

            # Get credentials again
            auth.get_credentials()

            # Should be called twice (once before clear, once after)
            assert mock_credential.call_count == 2


# ============================================================================
# SUBSCRIPTION DETECTION TESTS
# ============================================================================


class TestAzureSubscriptionDetection:
    """Test Azure subscription ID detection."""

    @patch("subprocess.run")
    def test_detects_subscription_from_az_cli(self, mock_run):
        """Test detecting subscription ID from az CLI."""
        from azlin.azure_auth import AzureAuthenticator

        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"id": "12345678-1234-1234-1234-123456789012", "name": "My Subscription"}',
            stderr="",
        )

        auth = AzureAuthenticator()
        subscription_id = auth.get_subscription_id()

        assert subscription_id == "12345678-1234-1234-1234-123456789012"

    @patch("os.environ", {"AZURE_SUBSCRIPTION_ID": "87654321-4321-4321-4321-210987654321"})
    def test_detects_subscription_from_env_var(self):
        """Test detecting subscription ID from environment variable."""
        from azlin.azure_auth import AzureAuthenticator

        auth = AzureAuthenticator()
        subscription_id = auth.get_subscription_id()

        assert subscription_id == "87654321-4321-4321-4321-210987654321"

    def test_accepts_subscription_id_in_constructor(self):
        """Test providing subscription ID directly."""
        from azlin.azure_auth import AzureAuthenticator

        auth = AzureAuthenticator(subscription_id="11111111-1111-1111-1111-111111111111")
        subscription_id = auth.get_subscription_id()

        assert subscription_id == "11111111-1111-1111-1111-111111111111"


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


class TestAzureAuthErrorHandling:
    """Test error handling in Azure authentication."""

    def test_raises_error_when_no_credentials_available(self):
        """Test error when no credentials can be found."""
        from azlin.azure_auth import AuthenticationError, AzureAuthenticator

        with patch("azure.identity.DefaultAzureCredential") as mock_credential:
            mock_credential.side_effect = Exception("No credentials found")

            auth = AzureAuthenticator()

            with pytest.raises(AuthenticationError):
                auth.get_credentials()

    @patch("subprocess.run")
    def test_handles_az_cli_not_installed(self, mock_run):
        """Test handling when az CLI is not installed."""
        from azlin.azure_auth import AzureAuthenticator

        # Simulate az CLI not found
        mock_run.side_effect = FileNotFoundError("az command not found")

        auth = AzureAuthenticator()

        # Should not raise, but return None or try other methods
        result = auth.check_az_cli_available()
        assert result is False

    def test_handles_expired_token(self):
        """Test handling of expired authentication tokens."""
        from azlin.azure_auth import AzureAuthenticator

        with patch("azure.identity.DefaultAzureCredential") as mock_credential:
            mock_cred = Mock()
            # Simulate expired token
            mock_cred.get_token.return_value = Mock(
                token="expired-token",
                expires_on=0,  # Already expired
            )
            mock_credential.return_value = mock_cred

            auth = AzureAuthenticator()

            # Should detect token is expired
            is_valid = auth.validate_credentials()
            assert is_valid is False


# ============================================================================
# TENANT ID DETECTION TESTS
# ============================================================================


class TestAzureTenantDetection:
    """Test Azure tenant ID detection."""

    @patch("subprocess.run")
    def test_detects_tenant_from_az_cli(self, mock_run):
        """Test detecting tenant ID from az CLI."""
        from azlin.azure_auth import AzureAuthenticator

        mock_run.return_value = Mock(returncode=0, stdout='{"tenantId": "tenant-12345"}', stderr="")

        auth = AzureAuthenticator()
        tenant_id = auth.get_tenant_id()

        assert tenant_id == "tenant-12345"

    @patch("os.environ", {"AZURE_TENANT_ID": "tenant-from-env"})
    def test_detects_tenant_from_env_var(self):
        """Test detecting tenant ID from environment variable."""
        from azlin.azure_auth import AzureAuthenticator

        auth = AzureAuthenticator()
        tenant_id = auth.get_tenant_id()

        assert tenant_id == "tenant-from-env"
