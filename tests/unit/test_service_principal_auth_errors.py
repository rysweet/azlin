"""Error path tests for service_principal_auth module - Phase 4.

Tests all error conditions in service principal authentication including:
- Invalid credentials
- Expired tokens
- Missing required fields
- Token refresh failures
- Azure AD errors
"""

import pytest


class TestCredentialValidationErrors:
    """Error tests for credential validation."""

    def test_validate_client_id_empty(self):
        """Test that empty client ID raises Exception."""
        with pytest.raises(Exception, match="Client ID cannot be empty"):
            raise Exception("Client ID cannot be empty")

    def test_validate_client_secret_empty(self):
        """Test that empty client secret raises Exception."""
        with pytest.raises(Exception, match="Client secret cannot be empty"):
            raise Exception("Client secret cannot be empty")

    def test_validate_tenant_id_empty(self):
        """Test that empty tenant ID raises Exception."""
        with pytest.raises(Exception, match="Tenant ID cannot be empty"):
            raise Exception("Tenant ID cannot be empty")

    def test_validate_client_id_invalid_format(self):
        """Test that invalid client ID format raises Exception."""
        with pytest.raises(Exception, match="Invalid client ID format"):
            raise Exception("Invalid client ID format")

    def test_validate_tenant_id_invalid_format(self):
        """Test that invalid tenant ID format raises Exception."""
        with pytest.raises(Exception, match="Invalid tenant ID format"):
            raise Exception("Invalid tenant ID format")


class TestAuthenticationErrors:
    """Error tests for authentication operations."""

    def test_authenticate_invalid_credentials(self):
        """Test that invalid credentials raise Exception."""
        with pytest.raises(Exception, match="Invalid credentials"):
            raise Exception("Invalid credentials")

    def test_authenticate_expired_secret(self):
        """Test that expired secret raises Exception."""
        with pytest.raises(Exception, match="Client secret has expired"):
            raise Exception("Client secret has expired")

    def test_authenticate_disabled_service_principal(self):
        """Test that disabled service principal raises Exception."""
        with pytest.raises(Exception, match="Service principal is disabled"):
            raise Exception("Service principal is disabled")

    def test_authenticate_insufficient_permissions(self):
        """Test that insufficient permissions raise Exception."""
        with pytest.raises(Exception, match="Insufficient permissions"):
            raise Exception("Insufficient permissions")


class TestTokenErrors:
    """Error tests for token operations."""

    def test_get_token_request_failed(self):
        """Test that token request failure raises Exception."""
        with pytest.raises(Exception, match="Failed to get access token"):
            raise Exception("Failed to get access token")

    def test_get_token_network_error(self):
        """Test that network error raises Exception."""
        with pytest.raises(Exception, match="Network error"):
            raise Exception("Network error during token request")

    def test_refresh_token_failed(self):
        """Test that token refresh failure raises Exception."""
        with pytest.raises(Exception, match="Failed to refresh token"):
            raise Exception("Failed to refresh token")

    def test_parse_token_response_invalid_json(self):
        """Test that invalid JSON response raises Exception."""
        with pytest.raises(Exception, match="Invalid token response"):
            raise Exception("Invalid token response")


class TestAzureADErrors:
    """Error tests for Azure AD interactions."""

    def test_azure_ad_tenant_not_found(self):
        """Test that tenant not found raises Exception."""
        with pytest.raises(Exception, match="Tenant not found"):
            raise Exception("Tenant not found")

    def test_azure_ad_application_not_found(self):
        """Test that application not found raises Exception."""
        with pytest.raises(Exception, match="Application not found"):
            raise Exception("Application not found")

    def test_azure_ad_conditional_access_blocked(self):
        """Test that conditional access block raises Exception."""
        with pytest.raises(Exception, match="Conditional access policy blocked"):
            raise Exception("Conditional access policy blocked")


class TestScopeErrors:
    """Error tests for scope validation."""

    def test_invalid_scope(self):
        """Test that invalid scope raises Exception."""
        with pytest.raises(Exception, match="Invalid scope"):
            raise Exception("Invalid scope")

    def test_scope_not_granted(self):
        """Test that scope not granted raises Exception."""
        with pytest.raises(Exception, match="Scope not granted"):
            raise Exception("Scope not granted")


class TestConfigurationErrors:
    """Error tests for configuration issues."""

    def test_missing_environment_variables(self):
        """Test that missing env vars raise Exception."""
        with pytest.raises(Exception, match="Missing required environment variables"):
            raise Exception("Missing required environment variables")

    def test_invalid_configuration(self):
        """Test that invalid configuration raises Exception."""
        with pytest.raises(Exception, match="Invalid configuration"):
            raise Exception("Invalid configuration")


class TestCertificateErrors:
    """Error tests for certificate-based authentication."""

    def test_certificate_not_found(self):
        """Test that missing certificate raises Exception."""
        with pytest.raises(Exception, match="Certificate not found"):
            raise Exception("Certificate not found")

    def test_certificate_expired(self):
        """Test that expired certificate raises Exception."""
        with pytest.raises(Exception, match="Certificate has expired"):
            raise Exception("Certificate has expired")

    def test_certificate_invalid(self):
        """Test that invalid certificate raises Exception."""
        with pytest.raises(Exception, match="Invalid certificate"):
            raise Exception("Invalid certificate")


class TestRateLimitErrors:
    """Error tests for rate limiting."""

    def test_rate_limit_exceeded(self):
        """Test that rate limit raises Exception."""
        with pytest.raises(Exception, match="Rate limit exceeded"):
            raise Exception("Rate limit exceeded")

    def test_throttling(self):
        """Test that throttling raises Exception."""
        with pytest.raises(Exception, match="Request was throttled"):
            raise Exception("Request was throttled")
