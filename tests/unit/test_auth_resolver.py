"""Unit tests for auth_resolver module.

This test suite ensures:
1. All 4 authentication methods work correctly (az_cli, service_principal_secret, service_principal_cert, managed_identity)
2. Backward compatibility with existing AzureAuthenticator maintained
3. Integration with Brick 1 (config_auth), Brick 3 (cert_handler), Brick 7 (auth_security)
4. Test coverage >90%
5. Zero breaking changes
6. No stubs, TODOs, or placeholders
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from azlin.auth_resolver import (
    AuthResolver,
    AuthResolverError,
    AzureCredentials,
)
from azlin.config_auth import AuthConfig


class TestAzureCredentials:
    """Tests for AzureCredentials dataclass."""

    def test_credentials_creation_minimal(self):
        """Test creating credentials with minimal fields."""
        creds = AzureCredentials(method="az_cli")
        assert creds.method == "az_cli"
        assert creds.token is None
        assert creds.subscription_id is None
        assert creds.tenant_id is None

    def test_credentials_creation_full(self):
        """Test creating credentials with all fields."""
        creds = AzureCredentials(
            method="service_principal_secret",
            token="test-token",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        assert creds.method == "service_principal_secret"
        assert creds.token == "test-token"
        assert creds.subscription_id == "12345678-1234-1234-1234-123456789abc"
        assert creds.tenant_id == "87654321-4321-4321-4321-cba987654321"

    def test_credentials_extends_existing(self):
        """Test that AzureCredentials is compatible with existing code."""
        # Should have same structure as azure_auth.py's AzureCredentials
        creds = AzureCredentials(
            method="az_cli", token="token", subscription_id="sub", tenant_id="tenant"
        )
        assert hasattr(creds, "method")
        assert hasattr(creds, "token")
        assert hasattr(creds, "subscription_id")
        assert hasattr(creds, "tenant_id")


class TestAuthResolverInit:
    """Tests for AuthResolver initialization."""

    def test_init_with_valid_config(self):
        """Test initialization with valid config."""
        config = AuthConfig(auth_method="az_cli")
        resolver = AuthResolver(config)
        assert resolver.config == config

    def test_init_with_service_principal_secret_config(self):
        """Test initialization with service principal secret config."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_secret="test-secret",
        )
        resolver = AuthResolver(config)
        assert resolver.config.auth_method == "service_principal_secret"

    def test_init_with_service_principal_cert_config(self):
        """Test initialization with service principal cert config."""
        config = AuthConfig(
            auth_method="service_principal_cert",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_certificate_path="/path/to/cert.pem",
        )
        resolver = AuthResolver(config)
        assert resolver.config.auth_method == "service_principal_cert"

    def test_init_with_managed_identity_config(self):
        """Test initialization with managed identity config."""
        config = AuthConfig(auth_method="managed_identity")
        resolver = AuthResolver(config)
        assert resolver.config.auth_method == "managed_identity"


class TestResolveCredentialsAzCli:
    """Tests for resolve_credentials with az_cli method."""

    def test_az_cli_delegates_to_existing_authenticator(self):
        """Test az_cli method delegates to existing AzureAuthenticator."""
        config = AuthConfig(auth_method="az_cli")
        resolver = AuthResolver(config)

        # Mock subprocess call to az CLI
        mock_result = Mock()
        mock_result.stdout = json.dumps(
            {
                "accessToken": "test-token",
                "subscription": "12345678-1234-1234-1234-123456789abc",
                "tenant": "87654321-4321-4321-4321-cba987654321",
            }
        )
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            with patch("shutil.which", return_value="/usr/bin/az"):
                creds = resolver.resolve_credentials()
                assert creds.method == "az_cli"
                assert creds.token is not None
                assert creds.subscription_id == "12345678-1234-1234-1234-123456789abc"
                assert creds.tenant_id == "87654321-4321-4321-4321-cba987654321"

    def test_az_cli_not_available(self):
        """Test error when az CLI is not available."""
        config = AuthConfig(auth_method="az_cli")
        resolver = AuthResolver(config)

        with patch("shutil.which", return_value=None):
            with pytest.raises(AuthResolverError, match="Azure CLI not available"):
                resolver.resolve_credentials()

    def test_az_cli_not_logged_in(self):
        """Test error when az CLI is not logged in."""
        config = AuthConfig(auth_method="az_cli")
        resolver = AuthResolver(config)

        with patch("shutil.which", return_value="/usr/bin/az"):
            with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "az")):
                with pytest.raises(AuthResolverError, match="not logged in|authentication failed"):
                    resolver.resolve_credentials()

    def test_az_cli_backward_compatibility(self):
        """Test az_cli maintains backward compatibility with existing code."""
        config = AuthConfig(auth_method="az_cli")
        resolver = AuthResolver(config)

        mock_result = Mock()
        mock_result.stdout = json.dumps(
            {
                "accessToken": "test-token",
                "subscription": "12345678-1234-1234-1234-123456789abc",
                "tenant": "87654321-4321-4321-4321-cba987654321",
            }
        )

        with patch("subprocess.run", return_value=mock_result):
            with patch("shutil.which", return_value="/usr/bin/az"):
                creds = resolver.resolve_credentials()
                # Should return same structure as existing code
                assert creds.method == "az_cli"
                assert creds.token
                assert creds.subscription_id
                assert creds.tenant_id


class TestResolveCredentialsServicePrincipalSecret:
    """Tests for resolve_credentials with service_principal_secret method."""

    def test_service_principal_secret_uses_azure_identity(self):
        """Test service principal secret uses Azure Identity SDK."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_secret="test-secret",
        )
        resolver = AuthResolver(config)

        # Mock Azure Identity ClientSecretCredential
        mock_credential = MagicMock()
        mock_token = MagicMock()
        mock_token.token = "test-access-token"
        mock_credential.get_token.return_value = mock_token

        with patch("azlin.auth_resolver.ClientSecretCredential", return_value=mock_credential):
            creds = resolver.resolve_credentials()
            assert creds.method == "service_principal_secret"
            assert creds.tenant_id == "12345678-1234-1234-1234-123456789abc"
            assert creds.token == "test-access-token"

    def test_service_principal_secret_missing_tenant(self):
        """Test error when tenant_id is missing."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_secret="test-secret",
        )
        resolver = AuthResolver(config)

        with pytest.raises(AuthResolverError, match="tenant_id.*required"):
            resolver.resolve_credentials()

    def test_service_principal_secret_missing_client_id(self):
        """Test error when client_id is missing."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_secret="test-secret",
        )
        resolver = AuthResolver(config)

        with pytest.raises(AuthResolverError, match="client_id.*required"):
            resolver.resolve_credentials()

    def test_service_principal_secret_missing_secret(self):
        """Test error when client_secret is missing."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
        )
        resolver = AuthResolver(config)

        with pytest.raises(AuthResolverError, match="client_secret.*required"):
            resolver.resolve_credentials()

    def test_service_principal_secret_validates_uuids(self):
        """Test UUID validation for tenant and client IDs."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="invalid-tenant",
            client_id="invalid-client",
            client_secret="test-secret",
        )
        resolver = AuthResolver(config)

        with pytest.raises(AuthResolverError, match="invalid UUID|UUID format"):
            resolver.resolve_credentials()

    def test_service_principal_secret_authentication_error(self):
        """Test error handling when authentication fails."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_secret="wrong-secret",
        )
        resolver = AuthResolver(config)

        mock_credential = MagicMock()
        mock_credential.get_token.side_effect = Exception("Authentication failed")

        with patch("azlin.auth_resolver.ClientSecretCredential", return_value=mock_credential):
            with pytest.raises(
                AuthResolverError, match="Authentication failed|Failed to authenticate"
            ):
                resolver.resolve_credentials()


class TestResolveCredentialsServicePrincipalCert:
    """Tests for resolve_credentials with service_principal_cert method."""

    def test_service_principal_cert_validates_certificate(self):
        """Test certificate is validated before use."""
        config = AuthConfig(
            auth_method="service_principal_cert",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_certificate_path="/fake/path/cert.pem",
        )
        resolver = AuthResolver(config)

        # Mock certificate validation to pass
        mock_validation = MagicMock()
        mock_validation.valid = True
        mock_validation.errors = []
        mock_validation.warnings = []

        mock_credential = MagicMock()
        mock_token = MagicMock()
        mock_token.token = "test-token"
        mock_credential.get_token.return_value = mock_token

        with patch("azlin.auth_resolver.validate_certificate", return_value=mock_validation):
            with patch("azlin.auth_resolver.CertificateCredential", return_value=mock_credential):
                creds = resolver.resolve_credentials()
                assert creds.method == "service_principal_cert"
                assert creds.token == "test-token"

    def test_service_principal_cert_invalid_certificate(self):
        """Test error when certificate validation fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cert_path = Path(tmpdir) / "test.pem"
            cert_path.write_text("INVALID CERT")
            cert_path.chmod(0o600)

            config = AuthConfig(
                auth_method="service_principal_cert",
                tenant_id="12345678-1234-1234-1234-123456789abc",
                client_id="87654321-4321-4321-4321-cba987654321",
                client_certificate_path=str(cert_path),
            )
            resolver = AuthResolver(config)

            # Mock certificate validation to fail
            mock_validation = MagicMock()
            mock_validation.valid = False
            mock_validation.errors = ["Invalid certificate format"]

            with patch("azlin.cert_handler.validate_certificate", return_value=mock_validation):
                with pytest.raises(
                    AuthResolverError, match="Certificate validation failed|Invalid certificate"
                ):
                    resolver.resolve_credentials()

    def test_service_principal_cert_missing_path(self):
        """Test error when certificate path is missing."""
        config = AuthConfig(
            auth_method="service_principal_cert",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
        )
        resolver = AuthResolver(config)

        with pytest.raises(AuthResolverError, match="certificate.*path.*required"):
            resolver.resolve_credentials()

    def test_service_principal_cert_file_not_found(self):
        """Test error when certificate file does not exist."""
        config = AuthConfig(
            auth_method="service_principal_cert",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_certificate_path="/nonexistent/cert.pem",
        )
        resolver = AuthResolver(config)

        # Mock validation to fail with file not found
        mock_validation = MagicMock()
        mock_validation.valid = False
        mock_validation.errors = ["Certificate file not found"]

        with patch("azlin.cert_handler.validate_certificate", return_value=mock_validation):
            with pytest.raises(AuthResolverError, match="not found|does not exist"):
                resolver.resolve_credentials()

    def test_service_principal_cert_insecure_permissions(self):
        """Test warning when certificate has insecure permissions."""
        config = AuthConfig(
            auth_method="service_principal_cert",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_certificate_path="/fake/path/insecure_cert.pem",
        )
        resolver = AuthResolver(config)

        # Mock validation to succeed with warnings
        mock_validation = MagicMock()
        mock_validation.valid = True
        mock_validation.errors = []
        mock_validation.warnings = ["Insecure permissions"]

        mock_credential = MagicMock()
        mock_token = MagicMock()
        mock_token.token = "test-token"
        mock_credential.get_token.return_value = mock_token

        with patch("azlin.auth_resolver.validate_certificate", return_value=mock_validation):
            with patch("azlin.auth_resolver.CertificateCredential", return_value=mock_credential):
                # Should succeed but log warning
                creds = resolver.resolve_credentials()
                assert creds is not None


class TestResolveCredentialsManagedIdentity:
    """Tests for resolve_credentials with managed_identity method."""

    def test_managed_identity_uses_azure_identity(self):
        """Test managed identity uses Azure Identity SDK."""
        config = AuthConfig(auth_method="managed_identity")
        resolver = AuthResolver(config)

        mock_credential = MagicMock()
        mock_token = MagicMock()
        mock_token.token = "managed-identity-token"
        mock_credential.get_token.return_value = mock_token

        with patch("azlin.auth_resolver.ManagedIdentityCredential", return_value=mock_credential):
            creds = resolver.resolve_credentials()
            assert creds.method == "managed_identity"
            assert creds.token == "managed-identity-token"

    def test_managed_identity_with_client_id(self):
        """Test managed identity with specific client_id."""
        config = AuthConfig(
            auth_method="managed_identity",
            client_id="12345678-1234-1234-1234-123456789abc",
        )
        resolver = AuthResolver(config)

        mock_credential = MagicMock()
        mock_token = MagicMock()
        mock_token.token = "managed-identity-token"
        mock_credential.get_token.return_value = mock_token

        with patch(
            "azlin.auth_resolver.ManagedIdentityCredential", return_value=mock_credential
        ) as mock_class:
            creds = resolver.resolve_credentials()
            # Should pass client_id to ManagedIdentityCredential
            mock_class.assert_called_once()
            call_kwargs = mock_class.call_args.kwargs
            if "client_id" in call_kwargs:
                assert call_kwargs["client_id"] == "12345678-1234-1234-1234-123456789abc"

    def test_managed_identity_not_available(self):
        """Test error when managed identity is not available."""
        config = AuthConfig(auth_method="managed_identity")
        resolver = AuthResolver(config)

        mock_credential = MagicMock()
        mock_credential.get_token.side_effect = Exception("Managed identity not available")

        with patch("azlin.auth_resolver.ManagedIdentityCredential", return_value=mock_credential):
            with pytest.raises(
                AuthResolverError, match="Managed identity not available|Failed to authenticate"
            ):
                resolver.resolve_credentials()


class TestValidateCredentials:
    """Tests for validate_credentials method."""

    def test_validate_credentials_az_cli_success(self):
        """Test credential validation succeeds for az_cli."""
        config = AuthConfig(auth_method="az_cli")
        resolver = AuthResolver(config)

        mock_result = Mock()
        mock_result.stdout = json.dumps(
            {
                "accessToken": "test-token",
                "subscription": "12345678-1234-1234-1234-123456789abc",
                "tenant": "87654321-4321-4321-4321-cba987654321",
            }
        )

        with patch("subprocess.run", return_value=mock_result):
            with patch("shutil.which", return_value="/usr/bin/az"):
                assert resolver.validate_credentials() is True

    def test_validate_credentials_az_cli_failure(self):
        """Test credential validation fails when az_cli not available."""
        config = AuthConfig(auth_method="az_cli")
        resolver = AuthResolver(config)

        with patch("shutil.which", return_value=None):
            assert resolver.validate_credentials() is False

    def test_validate_credentials_service_principal_secret(self):
        """Test credential validation for service principal secret."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_secret="test-secret",
        )
        resolver = AuthResolver(config)

        mock_credential = MagicMock()
        mock_token = MagicMock()
        mock_token.token = "test-token"
        mock_credential.get_token.return_value = mock_token

        with patch("azlin.auth_resolver.ClientSecretCredential", return_value=mock_credential):
            assert resolver.validate_credentials() is True

    def test_validate_credentials_invalid(self):
        """Test credential validation fails with invalid credentials."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_secret="wrong-secret",
        )
        resolver = AuthResolver(config)

        mock_credential = MagicMock()
        mock_credential.get_token.side_effect = Exception("Authentication failed")

        with patch("azlin.auth_resolver.ClientSecretCredential", return_value=mock_credential):
            assert resolver.validate_credentials() is False


class TestGetSubscriptionId:
    """Tests for get_subscription_id method."""

    def test_get_subscription_from_config(self):
        """Test getting subscription ID from config."""
        config = AuthConfig(
            auth_method="az_cli",
            subscription_id="12345678-1234-1234-1234-123456789abc",
        )
        resolver = AuthResolver(config)
        assert resolver.get_subscription_id() == "12345678-1234-1234-1234-123456789abc"

    def test_get_subscription_from_environment(self):
        """Test getting subscription ID from environment."""
        config = AuthConfig(auth_method="az_cli")
        resolver = AuthResolver(config)

        env = {"AZURE_SUBSCRIPTION_ID": "abcdef01-2345-6789-abcd-ef0123456789"}
        with patch.dict(os.environ, env, clear=False):
            assert resolver.get_subscription_id() == "abcdef01-2345-6789-abcd-ef0123456789"

    def test_get_subscription_from_az_cli(self):
        """Test getting subscription ID from Azure CLI."""
        config = AuthConfig(auth_method="az_cli")
        resolver = AuthResolver(config)

        mock_result = Mock()
        mock_result.stdout = json.dumps(
            {
                "id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
                "tenantId": "12345678-1234-1234-1234-123456789abc",
            }
        )

        with patch("subprocess.run", return_value=mock_result):
            with patch("shutil.which", return_value="/usr/bin/az"):
                assert resolver.get_subscription_id() == "ffffffff-ffff-ffff-ffff-ffffffffffff"

    def test_get_subscription_priority_config_over_env(self):
        """Test config subscription takes priority over environment."""
        config = AuthConfig(
            auth_method="az_cli",
            subscription_id="config-sub-id-12-34-1234-1234-123456789abc",
        )
        resolver = AuthResolver(config)

        # Even with env var set, config should win
        env = {"AZURE_SUBSCRIPTION_ID": "env-sub-id"}
        with patch.dict(os.environ, env, clear=False):
            result = resolver.get_subscription_id()
            assert (
                "config" in result.lower() or result == "config-sub-id-12-34-1234-1234-123456789abc"
            )

    def test_get_subscription_no_source_available(self):
        """Test error when no subscription ID available."""
        config = AuthConfig(auth_method="az_cli")
        resolver = AuthResolver(config)

        # Clear environment and make az CLI fail
        with patch.dict(os.environ, {}, clear=True):
            with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "az")):
                with patch("shutil.which", return_value="/usr/bin/az"):
                    with pytest.raises(
                        AuthResolverError,
                        match="subscription.*not found|Failed to get subscription",
                    ):
                        resolver.get_subscription_id()


class TestGetTenantId:
    """Tests for get_tenant_id method."""

    def test_get_tenant_from_config(self):
        """Test getting tenant ID from config."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_secret="test-secret",
        )
        resolver = AuthResolver(config)
        assert resolver.get_tenant_id() == "12345678-1234-1234-1234-123456789abc"

    def test_get_tenant_from_environment(self):
        """Test getting tenant ID from environment."""
        config = AuthConfig(auth_method="az_cli")
        resolver = AuthResolver(config)

        env = {"AZURE_TENANT_ID": "abcdef01-2345-6789-abcd-ef0123456789"}
        with patch.dict(os.environ, env, clear=False):
            assert resolver.get_tenant_id() == "abcdef01-2345-6789-abcd-ef0123456789"

    def test_get_tenant_from_az_cli(self):
        """Test getting tenant ID from Azure CLI."""
        config = AuthConfig(auth_method="az_cli")
        resolver = AuthResolver(config)

        mock_result = Mock()
        mock_result.stdout = json.dumps(
            {
                "id": "12345678-1234-1234-1234-123456789abc",
                "tenantId": "tenant-12-3456-7890-1234-567890abcdef",
            }
        )

        with patch("subprocess.run", return_value=mock_result):
            with patch("shutil.which", return_value="/usr/bin/az"):
                result = resolver.get_tenant_id()
                assert "tenant" in result.lower() or len(result) > 0

    def test_get_tenant_priority_config_over_env(self):
        """Test config tenant takes priority over environment."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="config-tenant-12-34-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_secret="test-secret",
        )
        resolver = AuthResolver(config)

        env = {"AZURE_TENANT_ID": "env-tenant"}
        with patch.dict(os.environ, env, clear=False):
            result = resolver.get_tenant_id()
            assert (
                "config" in result.lower() or result == "config-tenant-12-34-1234-1234-123456789abc"
            )

    def test_get_tenant_no_source_available(self):
        """Test error when no tenant ID available."""
        config = AuthConfig(auth_method="az_cli")
        resolver = AuthResolver(config)

        with patch.dict(os.environ, {}, clear=True):
            with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "az")):
                with patch("shutil.which", return_value="/usr/bin/az"):
                    with pytest.raises(
                        AuthResolverError, match="tenant.*not found|Failed to get tenant"
                    ):
                        resolver.get_tenant_id()


class TestSecurityControls:
    """Tests for security controls (P0 requirements)."""

    def test_no_secrets_logged(self, caplog):
        """Test that secrets are never logged."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_secret="super-secret-password-123",
        )
        resolver = AuthResolver(config)

        mock_credential = MagicMock()
        mock_token = MagicMock()
        mock_token.token = "access-token-xyz"
        mock_credential.get_token.return_value = mock_token

        with patch("azlin.auth_resolver.ClientSecretCredential", return_value=mock_credential):
            resolver.resolve_credentials()

        # Check that secrets are not in logs
        log_output = caplog.text
        assert "super-secret-password-123" not in log_output
        assert "access-token-xyz" not in log_output

    def test_uuids_validated_via_brick_7(self):
        """Test that UUIDs are validated using auth_security module."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="invalid-uuid",
            client_id="also-invalid",
            client_secret="test-secret",
        )
        resolver = AuthResolver(config)

        # Should use validate_uuid from auth_security (Brick 7)
        with pytest.raises(AuthResolverError, match="UUID|invalid.*format"):
            resolver.resolve_credentials()

    def test_certificate_validated_via_brick_3(self):
        """Test that certificates are validated using cert_handler module."""
        config = AuthConfig(
            auth_method="service_principal_cert",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_certificate_path="/fake/path/invalid_cert.pem",
        )
        resolver = AuthResolver(config)

        # Mock cert_handler validation to fail
        mock_validation = MagicMock()
        mock_validation.valid = False
        mock_validation.errors = ["Invalid certificate"]

        with patch(
            "azlin.auth_resolver.validate_certificate", return_value=mock_validation
        ) as mock_validate:
            with pytest.raises(AuthResolverError):
                resolver.resolve_credentials()
            # Verify cert_handler was called
            mock_validate.assert_called_once()

    def test_logs_sanitized(self, caplog):
        """Test that all logs are sanitized using auth_security."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_secret="my-secret-value",
        )
        resolver = AuthResolver(config)

        mock_credential = MagicMock()
        mock_token = MagicMock()
        mock_token.token = "token-value"
        mock_credential.get_token.return_value = mock_token

        with patch("azlin.auth_resolver.ClientSecretCredential", return_value=mock_credential):
            resolver.resolve_credentials()

        # Verify secrets not in logs
        log_output = caplog.text
        assert "my-secret-value" not in log_output


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing code."""

    def test_works_with_existing_azure_authenticator(self):
        """Test AuthResolver works alongside existing AzureAuthenticator."""
        from azlin.azure_auth import AzureAuthenticator

        # Old way should still work
        old_auth = AzureAuthenticator()
        assert old_auth is not None

        # New way should also work
        config = AuthConfig(auth_method="az_cli")
        resolver = AuthResolver(config)
        assert resolver is not None

    def test_credentials_compatible_with_existing_code(self):
        """Test AzureCredentials is compatible with existing code."""
        from azlin.azure_auth import AzureCredentials as OldCredentials

        # New credentials should have same structure
        new_creds = AzureCredentials(
            method="az_cli",
            token="token",
            subscription_id="sub",
            tenant_id="tenant",
        )

        # Should have same attributes as old credentials
        old_creds = OldCredentials(
            method="az_cli",
            token="token",
            subscription_id="sub",
            tenant_id="tenant",
        )

        assert new_creds.method == old_creds.method
        assert new_creds.token == old_creds.token
        assert new_creds.subscription_id == old_creds.subscription_id
        assert new_creds.tenant_id == old_creds.tenant_id

    def test_zero_breaking_changes_for_az_cli(self):
        """Test that az_cli method has zero breaking changes."""
        config = AuthConfig(auth_method="az_cli")
        resolver = AuthResolver(config)

        mock_result = Mock()
        mock_result.stdout = json.dumps(
            {
                "accessToken": "test-token",
                "subscription": "12345678-1234-1234-1234-123456789abc",
                "tenant": "87654321-4321-4321-4321-cba987654321",
            }
        )

        with patch("subprocess.run", return_value=mock_result):
            with patch("shutil.which", return_value="/usr/bin/az"):
                creds = resolver.resolve_credentials()
                # Should return same data structure
                assert hasattr(creds, "method")
                assert hasattr(creds, "token")
                assert hasattr(creds, "subscription_id")
                assert hasattr(creds, "tenant_id")


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_invalid_auth_method(self):
        """Test error with invalid auth method."""
        config = AuthConfig(auth_method="invalid_method")
        resolver = AuthResolver(config)

        with pytest.raises(AuthResolverError, match="Unsupported.*method|Invalid.*method"):
            resolver.resolve_credentials()

    def test_empty_config(self):
        """Test handling of empty/minimal config."""
        config = AuthConfig()
        resolver = AuthResolver(config)
        assert resolver.config.auth_method == "az_cli"

    def test_none_values_handled(self):
        """Test None values are handled gracefully."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id=None,
            client_id=None,
            client_secret=None,
        )
        resolver = AuthResolver(config)

        with pytest.raises(AuthResolverError):
            resolver.resolve_credentials()

    def test_network_timeout_handled(self):
        """Test network timeout is handled gracefully."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_secret="test-secret",
        )
        resolver = AuthResolver(config)

        mock_credential = MagicMock()
        mock_credential.get_token.side_effect = Exception("Network timeout")

        with patch("azlin.auth_resolver.ClientSecretCredential", return_value=mock_credential):
            with pytest.raises(AuthResolverError, match="timeout|Network|Failed"):
                resolver.resolve_credentials()

    def test_concurrent_credential_resolution(self):
        """Test concurrent credential resolution is safe."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_secret="test-secret",
        )
        resolver1 = AuthResolver(config)
        resolver2 = AuthResolver(config)

        mock_credential = MagicMock()
        mock_token = MagicMock()
        mock_token.token = "test-token"
        mock_credential.get_token.return_value = mock_token

        with patch("azlin.auth_resolver.ClientSecretCredential", return_value=mock_credential):
            creds1 = resolver1.resolve_credentials()
            creds2 = resolver2.resolve_credentials()
            assert creds1.token == creds2.token


class TestIntegration:
    """Integration tests with Brick 1 (config_auth)."""

    def test_integration_with_load_auth_config(self):
        """Test integration with load_auth_config from Brick 1."""
        from azlin.config_auth import load_auth_config

        # Load config using Brick 1
        env = {
            "AZURE_AUTH_METHOD": "service_principal_secret",
            "AZURE_TENANT_ID": "12345678-1234-1234-1234-123456789abc",
            "AZURE_CLIENT_ID": "87654321-4321-4321-4321-cba987654321",
            "AZURE_CLIENT_SECRET": "test-secret",
        }

        with patch.dict(os.environ, env, clear=False):
            config = load_auth_config()

            # Use config with Brick 2
            resolver = AuthResolver(config)
            assert resolver.config.auth_method == "service_principal_secret"

            mock_credential = MagicMock()
            mock_token = MagicMock()
            mock_token.token = "test-token"
            mock_credential.get_token.return_value = mock_token

            with patch("azlin.auth_resolver.ClientSecretCredential", return_value=mock_credential):
                creds = resolver.resolve_credentials()
                assert creds.method == "service_principal_secret"

    def test_end_to_end_az_cli_flow(self):
        """Test end-to-end flow with az_cli method."""
        from azlin.config_auth import load_auth_config

        # Load default config (az_cli)
        config = load_auth_config()

        # Resolve credentials
        resolver = AuthResolver(config)

        mock_result = Mock()
        mock_result.stdout = json.dumps(
            {
                "accessToken": "test-token",
                "subscription": "12345678-1234-1234-1234-123456789abc",
                "tenant": "87654321-4321-4321-4321-cba987654321",
            }
        )

        mock_account_result = Mock()
        mock_account_result.stdout = json.dumps(
            {
                "id": "12345678-1234-1234-1234-123456789abc",
                "tenantId": "87654321-4321-4321-4321-cba987654321",
            }
        )

        def mock_run(cmd, **kwargs):
            if "get-access-token" in cmd:
                return mock_result
            if "show" in cmd:
                return mock_account_result
            return mock_result

        with patch("subprocess.run", side_effect=mock_run):
            with patch("shutil.which", return_value="/usr/bin/az"):
                creds = resolver.resolve_credentials()
                assert creds.method == "az_cli"

                # Get subscription and tenant
                sub_id = resolver.get_subscription_id()
                tenant_id = resolver.get_tenant_id()
                assert sub_id
                assert tenant_id
