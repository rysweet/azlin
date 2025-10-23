"""Unit tests for service principal authentication module.

Test-Driven Development (TDD) approach - these tests are written BEFORE implementation.
Tests cover ServicePrincipalManager class with comprehensive scenarios including:
- Configuration loading and validation
- Credential retrieval patterns
- Certificate handling
- Error scenarios
- File permissions and security

All tests should FAIL initially until the implementation is complete.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from azlin.service_principal_auth import (
    ServicePrincipalConfig,
    ServicePrincipalError,
    ServicePrincipalManager,
)


class TestServicePrincipalConfig:
    """Test ServicePrincipalConfig dataclass."""

    def test_config_creation_with_client_secret(self):
        """Test creating SP config with client secret."""
        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="client_secret",
            client_secret="super-secret-value",
        )

        assert config.client_id == "12345678-1234-1234-1234-123456789012"
        assert config.tenant_id == "87654321-4321-4321-4321-210987654321"
        assert config.subscription_id == "abcdef00-0000-0000-0000-000000abcdef"
        assert config.auth_method == "client_secret"
        assert config.client_secret == "super-secret-value"
        assert config.certificate_path is None

    def test_config_creation_with_certificate(self):
        """Test creating SP config with certificate."""
        cert_path = Path("/home/user/.azlin/certs/sp-cert.pem")
        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="certificate",
            certificate_path=cert_path,
        )

        assert config.auth_method == "certificate"
        assert config.certificate_path == cert_path
        assert config.client_secret is None

    def test_config_to_dict_excludes_secret(self):
        """Test that to_dict() method excludes sensitive data by default."""
        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="client_secret",
            client_secret="super-secret-value",
        )

        config_dict = config.to_dict()

        assert "client_id" in config_dict
        assert "tenant_id" in config_dict
        assert "subscription_id" in config_dict
        assert "auth_method" in config_dict
        assert "client_secret" not in config_dict  # Should be excluded

    def test_config_to_dict_includes_secret_when_requested(self):
        """Test that to_dict() includes secret when explicitly requested."""
        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="client_secret",
            client_secret="super-secret-value",
        )

        config_dict = config.to_dict(include_secret=True)

        assert "client_secret" in config_dict
        assert config_dict["client_secret"] == "super-secret-value"

    def test_config_from_dict(self):
        """Test creating config from dictionary."""
        data = {
            "client_id": "12345678-1234-1234-1234-123456789012",
            "tenant_id": "87654321-4321-4321-4321-210987654321",
            "subscription_id": "abcdef00-0000-0000-0000-000000abcdef",
            "auth_method": "client_secret",
            "client_secret": "super-secret-value",
        }

        config = ServicePrincipalConfig.from_dict(data)

        assert config.client_id == data["client_id"]
        assert config.client_secret == data["client_secret"]

    def test_config_repr_masks_secret(self):
        """Test that __repr__ masks sensitive values."""
        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="client_secret",
            client_secret="super-secret-value",
        )

        repr_str = repr(config)

        assert "super-secret-value" not in repr_str
        assert "****" in repr_str or "[REDACTED]" in repr_str


class TestServicePrincipalManagerConfigLoading:
    """Test configuration loading and validation."""

    def test_load_config_from_default_location(self, tmp_path, monkeypatch):
        """Test loading SP config from default location."""
        # Set up mock home directory
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        azlin_dir = mock_home / ".azlin"
        azlin_dir.mkdir()

        # Create SP config file
        sp_config_file = azlin_dir / "sp-config.toml"
        sp_config_file.write_text(
            """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "client_secret"

[secrets]
# Secrets are stored in environment variables, not in config file
# Set AZLIN_SP_CLIENT_SECRET environment variable
"""
        )
        sp_config_file.chmod(0o600)

        monkeypatch.setenv("HOME", str(mock_home))
        monkeypatch.setenv("AZLIN_SP_CLIENT_SECRET", "secret-from-env")

        # Load config
        config = ServicePrincipalManager.load_config()

        assert config.client_id == "12345678-1234-1234-1234-123456789012"
        assert config.tenant_id == "87654321-4321-4321-4321-210987654321"
        assert config.subscription_id == "abcdef00-0000-0000-0000-000000abcdef"
        assert config.client_secret == "secret-from-env"

    def test_load_config_from_custom_path(self, tmp_path):
        """Test loading SP config from custom path."""
        config_file = tmp_path / "custom-sp-config.toml"
        config_file.write_text(
            """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "certificate"
certificate_path = "/path/to/cert.pem"
"""
        )
        config_file.chmod(0o600)

        config = ServicePrincipalManager.load_config(str(config_file))

        assert config.auth_method == "certificate"
        assert config.certificate_path == Path("/path/to/cert.pem")

    def test_load_config_missing_file_raises_error(self, tmp_path):
        """Test that loading non-existent config raises error."""
        non_existent = tmp_path / "does-not-exist.toml"

        with pytest.raises(ServicePrincipalError, match="not found"):
            ServicePrincipalManager.load_config(str(non_existent))

    def test_load_config_invalid_toml_raises_error(self, tmp_path):
        """Test that invalid TOML syntax raises error."""
        config_file = tmp_path / "invalid.toml"
        config_file.write_text("this is not valid TOML [[[")

        with pytest.raises(ServicePrincipalError, match="Failed to parse"):
            ServicePrincipalManager.load_config(str(config_file))

    def test_load_config_missing_required_fields_raises_error(self, tmp_path):
        """Test that missing required fields raises validation error."""
        config_file = tmp_path / "incomplete.toml"
        config_file.write_text(
            """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
# Missing tenant_id and subscription_id
"""
        )

        with pytest.raises(ServicePrincipalError, match="Missing required field"):
            ServicePrincipalManager.load_config(str(config_file))

    def test_load_config_with_inline_secret_raises_error(self, tmp_path):
        """Test that inline secrets in config file are rejected."""
        config_file = tmp_path / "insecure.toml"
        config_file.write_text(
            """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "client_secret"
client_secret = "this-should-not-be-here"
"""
        )

        with pytest.raises(ServicePrincipalError, match="client_secret.*not allowed.*config file"):
            ServicePrincipalManager.load_config(str(config_file))


class TestServicePrincipalManagerCredentialRetrieval:
    """Test credential retrieval patterns."""

    def test_get_credentials_with_client_secret_from_env(self, tmp_path, monkeypatch):
        """Test retrieving credentials with client secret from environment."""
        config_file = tmp_path / "sp-config.toml"
        config_file.write_text(
            """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "client_secret"
"""
        )
        config_file.chmod(0o600)

        monkeypatch.setenv("AZLIN_SP_CLIENT_SECRET", "secret-from-env-var")

        config = ServicePrincipalManager.load_config(str(config_file))
        creds = ServicePrincipalManager.get_credentials(config)

        assert creds["AZURE_CLIENT_ID"] == "12345678-1234-1234-1234-123456789012"
        assert creds["AZURE_CLIENT_SECRET"] == "secret-from-env-var"
        assert creds["AZURE_TENANT_ID"] == "87654321-4321-4321-4321-210987654321"
        assert creds["AZURE_SUBSCRIPTION_ID"] == "abcdef00-0000-0000-0000-000000abcdef"

    def test_get_credentials_with_certificate(self, tmp_path):
        """Test retrieving credentials with certificate."""
        cert_file = tmp_path / "cert.pem"
        cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        cert_file.chmod(0o600)

        config_file = tmp_path / "sp-config.toml"
        config_file.write_text(
            f"""
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "certificate"
certificate_path = "{cert_file}"
"""
        )
        config_file.chmod(0o600)

        config = ServicePrincipalManager.load_config(str(config_file))
        creds = ServicePrincipalManager.get_credentials(config)

        assert creds["AZURE_CLIENT_ID"] == "12345678-1234-1234-1234-123456789012"
        assert creds["AZURE_CLIENT_CERTIFICATE_PATH"] == str(cert_file)
        assert "AZURE_CLIENT_SECRET" not in creds

    def test_get_credentials_missing_secret_raises_error(self, tmp_path, monkeypatch):
        """Test that missing client secret raises error."""
        config_file = tmp_path / "sp-config.toml"
        config_file.write_text(
            """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "client_secret"
"""
        )
        config_file.chmod(0o600)

        # Ensure environment variable is NOT set
        monkeypatch.delenv("AZLIN_SP_CLIENT_SECRET", raising=False)

        config = ServicePrincipalManager.load_config(str(config_file))

        with pytest.raises(ServicePrincipalError, match="AZLIN_SP_CLIENT_SECRET.*not set"):
            ServicePrincipalManager.get_credentials(config)


class TestServicePrincipalManagerCertificateHandling:
    """Test certificate handling and validation."""

    def test_validate_certificate_file_exists(self, tmp_path):
        """Test certificate file existence validation."""
        cert_file = tmp_path / "cert.pem"
        cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        cert_file.chmod(0o600)

        result = ServicePrincipalManager.validate_certificate(cert_file)
        assert result is True

    def test_validate_certificate_missing_file_raises_error(self, tmp_path):
        """Test that missing certificate file raises error."""
        non_existent = tmp_path / "missing.pem"

        with pytest.raises(ServicePrincipalError, match="Certificate file not found"):
            ServicePrincipalManager.validate_certificate(non_existent)

    def test_validate_certificate_wrong_permissions_raises_warning(self, tmp_path):
        """Test that certificate with wrong permissions raises warning and error (SEC-003: fail-fast)."""
        cert_file = tmp_path / "cert.pem"
        cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        cert_file.chmod(0o644)  # Too permissive

        # Should warn AND raise error (SEC-003 requires fail-fast on security violations)
        with pytest.warns(UserWarning, match="insecure permissions"):
            with pytest.raises(ServicePrincipalError, match="insecure permissions"):
                ServicePrincipalManager.validate_certificate(cert_file)

    def test_validate_certificate_checks_expiration(self, tmp_path):
        """Test that certificate expiration is checked."""
        # Create a certificate that expires in 15 days
        cert_file = tmp_path / "expiring-cert.pem"
        # This would need real certificate parsing in implementation
        cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        cert_file.chmod(0o600)

        # Mock certificate parsing to return expiration date
        with patch(
            "azlin.service_principal_auth.ServicePrincipalManager._get_certificate_expiration"
        ) as mock_expiry:
            from datetime import datetime, timedelta

            mock_expiry.return_value = datetime.now() + timedelta(days=15)

            with pytest.warns(UserWarning, match="expires in.*days"):
                ServicePrincipalManager.validate_certificate(cert_file)

    def test_validate_certificate_format(self, tmp_path):
        """Test that certificate format is validated."""
        cert_file = tmp_path / "invalid-cert.pem"
        cert_file.write_text("This is not a valid certificate")
        cert_file.chmod(0o600)

        with pytest.raises(ServicePrincipalError, match="Invalid certificate format"):
            ServicePrincipalManager.validate_certificate(cert_file)


class TestServicePrincipalManagerSaveConfig:
    """Test saving configuration securely."""

    def test_save_config_creates_file_with_secure_permissions(self, tmp_path):
        """Test that saved config has secure permissions (0600)."""
        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="certificate",
            certificate_path=Path("/path/to/cert.pem"),
        )

        config_file = tmp_path / "saved-config.toml"
        ServicePrincipalManager.save_config(config, str(config_file))

        # Verify file exists
        assert config_file.exists()

        # Verify permissions
        mode = config_file.stat().st_mode & 0o777
        assert mode == 0o600

    def test_save_config_does_not_include_secrets(self, tmp_path):
        """Test that saved config does not include inline secrets."""
        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="client_secret",
            client_secret="should-not-be-saved",
        )

        config_file = tmp_path / "saved-config.toml"
        ServicePrincipalManager.save_config(config, str(config_file))

        # Read back and verify secret VALUE is not present
        content = config_file.read_text()
        assert "should-not-be-saved" not in content  # Secret value must not be saved
        # It's OK for "client_secret" to appear in auth_method or comments, just not as a key with value
        assert 'client_secret = ' not in content  # No client_secret key-value pair
        assert "AZLIN_SP_CLIENT_SECRET" in content  # Should have instructions

    def test_save_config_atomic_write(self, tmp_path):
        """Test that config save uses atomic write (temp file + rename)."""
        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="certificate",
            certificate_path=Path("/path/to/cert.pem"),
        )

        config_file = tmp_path / "atomic-config.toml"

        # Patch os.rename to verify it's called
        with patch("os.rename") as mock_rename:
            with patch("pathlib.Path.write_text") as mock_write:
                ServicePrincipalManager.save_config(config, str(config_file))

                # Verify atomic write pattern
                assert mock_rename.called
                # Temp file should be created first
                temp_file_arg = mock_rename.call_args[0][0]
                assert ".tmp" in str(temp_file_arg) or "tmp" in str(temp_file_arg)


class TestServicePrincipalManagerValidation:
    """Test UUID and configuration validation."""

    @pytest.mark.parametrize(
        "uuid_value,expected",
        [
            ("12345678-1234-1234-1234-123456789012", True),
            ("87654321-4321-4321-4321-210987654321", True),
            ("abcdef00-0000-0000-0000-000000abcdef", True),
            ("not-a-uuid", False),
            ("12345678-1234-1234-1234", False),  # Too short
            ("12345678-1234-1234-1234-123456789012345", False),  # Too long
            ("", False),
            (None, False),
        ],
    )
    def test_validate_uuid_format(self, uuid_value, expected):
        """Test UUID format validation for tenant_id, client_id, subscription_id."""
        result = ServicePrincipalManager.validate_uuid(uuid_value)
        assert result == expected

    def test_validate_config_all_fields(self, tmp_path):
        """Test comprehensive config validation."""
        cert_file = tmp_path / "cert.pem"
        cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        cert_file.chmod(0o600)

        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="certificate",
            certificate_path=cert_file,
        )

        # Should not raise
        ServicePrincipalManager.validate_config(config)

    def test_validate_config_invalid_uuid_raises_error(self):
        """Test that invalid UUIDs are rejected."""
        config = ServicePrincipalConfig(
            client_id="not-a-uuid",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="certificate",
            certificate_path=Path("/path/to/cert.pem"),
        )

        with pytest.raises(ServicePrincipalError, match="Invalid UUID format.*client_id"):
            ServicePrincipalManager.validate_config(config)

    def test_validate_config_invalid_auth_method_raises_error(self):
        """Test that invalid auth methods are rejected."""
        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="invalid_method",
        )

        with pytest.raises(
            ServicePrincipalError, match="Invalid auth_method.*client_secret.*certificate"
        ):
            ServicePrincipalManager.validate_config(config)


class TestServicePrincipalManagerErrorHandling:
    """Test error scenarios and edge cases."""

    def test_load_config_with_path_traversal_blocked(self, tmp_path):
        """Test that path traversal attempts are blocked."""
        malicious_path = "../../etc/passwd"

        with pytest.raises(ServicePrincipalError, match="Invalid config path"):
            ServicePrincipalManager.load_config(malicious_path)

    def test_load_config_insecure_permissions_auto_fixes(self, tmp_path):
        """Test that insecure permissions are automatically fixed."""
        config_file = tmp_path / "insecure-perms.toml"
        config_file.write_text(
            """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "certificate"
certificate_path = "/path/to/cert.pem"
"""
        )
        config_file.chmod(0o644)  # Insecure permissions

        with pytest.warns(UserWarning, match="insecure permissions.*fixing"):
            config = ServicePrincipalManager.load_config(str(config_file))

        # Verify permissions were fixed
        mode = config_file.stat().st_mode & 0o777
        assert mode == 0o600

    def test_get_credentials_logs_dont_leak_secrets(self, tmp_path, monkeypatch, caplog):
        """Test that log messages don't leak secrets."""
        config_file = tmp_path / "sp-config.toml"
        config_file.write_text(
            """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "client_secret"
"""
        )
        config_file.chmod(0o600)

        monkeypatch.setenv("AZLIN_SP_CLIENT_SECRET", "super-secret-value")

        with caplog.at_level("DEBUG"):
            config = ServicePrincipalManager.load_config(str(config_file))
            ServicePrincipalManager.get_credentials(config)

            # Check that secret is not in logs
            for record in caplog.records:
                assert "super-secret-value" not in record.message
                if "secret" in record.message.lower():
                    assert "****" in record.message or "[REDACTED]" in record.message

    def test_environment_cleanup_after_operation(self, tmp_path, monkeypatch):
        """Test that environment variables are cleaned up after operations."""
        config_file = tmp_path / "sp-config.toml"
        config_file.write_text(
            """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "client_secret"
"""
        )
        config_file.chmod(0o600)

        monkeypatch.setenv("AZLIN_SP_CLIENT_SECRET", "secret-value")

        # Use context manager pattern
        with ServicePrincipalManager.credential_context(str(config_file)) as creds:
            assert "AZURE_CLIENT_SECRET" in os.environ
            assert os.environ["AZURE_CLIENT_SECRET"] == "secret-value"

        # After context manager exits, credentials should be removed
        assert "AZURE_CLIENT_SECRET" not in os.environ
