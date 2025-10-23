"""Unit tests for config_auth module.

This test suite ensures:
1. Zero breaking changes - backward compatibility maintained
2. NO secrets stored in config files (P0 security control)
3. UUID validation for tenant_id, client_id, subscription_id
4. Test coverage >90%
5. Azure CLI delegation pattern continues to work
6. No stubs, TODOs, or placeholders
"""

import os
from unittest.mock import patch

import pytest

from azlin.config_auth import (
    AuthConfig,
    AuthConfigError,
    ValidationResult,
    load_auth_config,
    validate_auth_config,
)


class TestAuthConfig:
    """Tests for AuthConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = AuthConfig()
        assert config.auth_method == "az_cli"
        assert config.tenant_id is None
        assert config.client_id is None
        assert config.client_secret is None
        assert config.client_certificate_path is None
        assert config.subscription_id is None
        assert config.profile_name is None

    def test_service_principal_secret_config(self):
        """Test service principal with secret configuration."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_secret="secret-from-env",
            subscription_id="abcdef01-2345-6789-abcd-ef0123456789",
        )
        assert config.auth_method == "service_principal_secret"
        assert config.tenant_id == "12345678-1234-1234-1234-123456789abc"
        assert config.client_id == "87654321-4321-4321-4321-cba987654321"
        assert config.client_secret == "secret-from-env"
        assert config.subscription_id == "abcdef01-2345-6789-abcd-ef0123456789"

    def test_service_principal_cert_config(self):
        """Test service principal with certificate configuration."""
        config = AuthConfig(
            auth_method="service_principal_cert",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_certificate_path="/path/to/cert.pem",
            subscription_id="abcdef01-2345-6789-abcd-ef0123456789",
        )
        assert config.auth_method == "service_principal_cert"
        assert config.client_certificate_path == "/path/to/cert.pem"

    def test_managed_identity_config(self):
        """Test managed identity configuration."""
        config = AuthConfig(
            auth_method="managed_identity",
            subscription_id="abcdef01-2345-6789-abcd-ef0123456789",
        )
        assert config.auth_method == "managed_identity"
        assert config.tenant_id is None
        assert config.client_id is None


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result(self):
        """Test valid validation result."""
        result = ValidationResult(is_valid=True, errors=[], warnings=[])
        assert result.is_valid
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_invalid_result_with_errors(self):
        """Test invalid validation result with errors."""
        result = ValidationResult(
            is_valid=False, errors=["Invalid UUID format for tenant_id"], warnings=[]
        )
        assert not result.is_valid
        assert len(result.errors) == 1
        assert "Invalid UUID format" in result.errors[0]

    def test_valid_result_with_warnings(self):
        """Test valid result with warnings."""
        result = ValidationResult(
            is_valid=True, errors=[], warnings=["Certificate file permissions may be insecure"]
        )
        assert result.is_valid
        assert len(result.warnings) == 1
        assert "permissions" in result.warnings[0]


class TestValidateAuthConfig:
    """Tests for validate_auth_config function."""

    def test_validate_az_cli_method(self):
        """Test validation of az_cli auth method."""
        config = AuthConfig(auth_method="az_cli")
        result = validate_auth_config(config)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_validate_valid_uuids(self):
        """Test validation accepts valid UUIDs."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            subscription_id="abcdef01-2345-6789-abcd-ef0123456789",
            client_secret="secret",
        )
        result = validate_auth_config(config)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_validate_invalid_tenant_id_format(self):
        """Test validation rejects invalid tenant_id UUID format."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="not-a-valid-uuid",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_secret="secret",
        )
        result = validate_auth_config(config)
        assert not result.is_valid
        assert any("tenant_id" in err.lower() for err in result.errors)

    def test_validate_invalid_client_id_format(self):
        """Test validation rejects invalid client_id UUID format."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="INVALID-CLIENT-ID",
            client_secret="secret",
        )
        result = validate_auth_config(config)
        assert not result.is_valid
        assert any("client_id" in err.lower() for err in result.errors)

    def test_validate_invalid_subscription_id_format(self):
        """Test validation rejects invalid subscription_id UUID format."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            subscription_id="bad-subscription",
            client_secret="secret",
        )
        result = validate_auth_config(config)
        assert not result.is_valid
        assert any("subscription_id" in err.lower() for err in result.errors)

    def test_validate_uppercase_uuids_accepted(self):
        """Test validation accepts uppercase UUIDs."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789ABC",
            client_id="87654321-4321-4321-4321-CBA987654321",
            subscription_id="ABCDEF01-2345-6789-ABCD-EF0123456789",
            client_secret="secret",
        )
        result = validate_auth_config(config)
        assert result.is_valid

    def test_validate_mixed_case_uuids_accepted(self):
        """Test validation accepts mixed case UUIDs."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789AbC",
            client_id="87654321-4321-4321-4321-CbA987654321",
            client_secret="secret",
        )
        result = validate_auth_config(config)
        assert result.is_valid

    def test_validate_service_principal_secret_missing_tenant(self):
        """Test validation rejects service_principal_secret without tenant_id."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_secret="secret",
        )
        result = validate_auth_config(config)
        assert not result.is_valid
        assert any("tenant_id" in err.lower() for err in result.errors)

    def test_validate_service_principal_secret_missing_client_id(self):
        """Test validation rejects service_principal_secret without client_id."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_secret="secret",
        )
        result = validate_auth_config(config)
        assert not result.is_valid
        assert any("client_id" in err.lower() for err in result.errors)

    def test_validate_service_principal_secret_missing_secret(self):
        """Test validation rejects service_principal_secret without client_secret."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
        )
        result = validate_auth_config(config)
        assert not result.is_valid
        assert any("client_secret" in err.lower() for err in result.errors)

    def test_validate_service_principal_cert_missing_cert_path(self):
        """Test validation rejects service_principal_cert without certificate path."""
        config = AuthConfig(
            auth_method="service_principal_cert",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
        )
        result = validate_auth_config(config)
        assert not result.is_valid
        assert any("certificate" in err.lower() for err in result.errors)

    def test_validate_certificate_file_not_exists(self, tmp_path):
        """Test validation rejects non-existent certificate file."""
        config = AuthConfig(
            auth_method="service_principal_cert",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_certificate_path=str(tmp_path / "nonexistent.pem"),
        )
        result = validate_auth_config(config)
        assert not result.is_valid
        assert any(
            "not found" in err.lower() or "does not exist" in err.lower() for err in result.errors
        )

    def test_validate_certificate_file_exists(self, tmp_path):
        """Test validation accepts existing certificate file."""
        cert_path = tmp_path / "valid_cert.pem"
        cert_path.write_text("-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----")

        config = AuthConfig(
            auth_method="service_principal_cert",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_certificate_path=str(cert_path),
        )
        result = validate_auth_config(config)
        assert result.is_valid

    def test_validate_certificate_permissions_warning(self, tmp_path):
        """Test validation warns about insecure certificate permissions."""
        cert_path = tmp_path / "insecure_cert.pem"
        cert_path.write_text("-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----")
        cert_path.chmod(0o644)  # World-readable

        config = AuthConfig(
            auth_method="service_principal_cert",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_certificate_path=str(cert_path),
        )
        result = validate_auth_config(config)
        # Should be valid but with warnings
        assert result.is_valid or len(result.warnings) > 0
        if result.is_valid:
            assert any("permission" in warn.lower() for warn in result.warnings)

    def test_validate_invalid_auth_method(self):
        """Test validation rejects invalid auth method."""
        config = AuthConfig(auth_method="invalid_method")
        result = validate_auth_config(config)
        assert not result.is_valid
        assert any("auth_method" in err.lower() or "method" in err.lower() for err in result.errors)


class TestLoadAuthConfig:
    """Tests for load_auth_config function."""

    def test_load_default_az_cli(self):
        """Test loading default configuration falls back to az_cli."""
        config = load_auth_config()
        assert config.auth_method == "az_cli"
        assert config.tenant_id is None
        assert config.client_id is None

    def test_load_from_environment_variables(self):
        """Test loading configuration from environment variables."""
        env = {
            "AZURE_AUTH_METHOD": "service_principal_secret",
            "AZURE_TENANT_ID": "12345678-1234-1234-1234-123456789abc",
            "AZURE_CLIENT_ID": "87654321-4321-4321-4321-cba987654321",
            "AZURE_CLIENT_SECRET": "secret-from-env",
            "AZURE_SUBSCRIPTION_ID": "abcdef01-2345-6789-abcd-ef0123456789",
        }

        with patch.dict(os.environ, env, clear=False):
            config = load_auth_config()
            assert config.auth_method == "service_principal_secret"
            assert config.tenant_id == "12345678-1234-1234-1234-123456789abc"
            assert config.client_id == "87654321-4321-4321-4321-cba987654321"
            assert config.client_secret == "secret-from-env"
            assert config.subscription_id == "abcdef01-2345-6789-abcd-ef0123456789"

    def test_load_from_cli_args(self):
        """Test CLI arguments have highest priority."""
        cli_args = {
            "auth_method": "service_principal_cert",
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "client_id": "22222222-2222-2222-2222-222222222222",
            "client_certificate_path": "/cli/cert.pem",
            "subscription_id": "33333333-3333-3333-3333-333333333333",
        }

        config = load_auth_config(cli_args=cli_args)
        assert config.auth_method == "service_principal_cert"
        assert config.tenant_id == "11111111-1111-1111-1111-111111111111"
        assert config.client_id == "22222222-2222-2222-2222-222222222222"
        assert config.client_certificate_path == "/cli/cert.pem"

    def test_priority_cli_overrides_env(self):
        """Test CLI arguments override environment variables."""
        env = {
            "AZURE_TENANT_ID": "env-tenant-id",
            "AZURE_CLIENT_ID": "env-client-id",
        }
        cli_args = {
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "client_id": "22222222-2222-2222-2222-222222222222",
        }

        with patch.dict(os.environ, env, clear=False):
            config = load_auth_config(cli_args=cli_args)
            assert config.tenant_id == "11111111-1111-1111-1111-111111111111"
            assert config.client_id == "22222222-2222-2222-2222-222222222222"

    def test_load_from_profile_config(self, tmp_path):
        """Test loading configuration from profile config file."""
        config_dir = tmp_path / ".azlin"
        config_dir.mkdir()
        config_file = config_dir / "auth_profiles.toml"

        config_content = """
[profiles.production]
auth_method = "service_principal_secret"
tenant_id = "12345678-1234-1234-1234-123456789abc"
client_id = "87654321-4321-4321-4321-cba987654321"
subscription_id = "abcdef01-2345-6789-abcd-ef0123456789"

[profiles.development]
auth_method = "az_cli"
subscription_id = "dev-subscription-id"
"""
        config_file.write_text(config_content)
        config_file.chmod(0o600)

        with patch("azlin.config_auth.Path.home", return_value=tmp_path):
            config = load_auth_config(profile="production")
            assert config.auth_method == "service_principal_secret"
            assert config.tenant_id == "12345678-1234-1234-1234-123456789abc"
            assert config.client_id == "87654321-4321-4321-4321-cba987654321"
            assert config.profile_name == "production"

    def test_load_profile_not_found(self, tmp_path):
        """Test loading non-existent profile raises error."""
        config_dir = tmp_path / ".azlin"
        config_dir.mkdir()

        with patch("azlin.config_auth.Path.home", return_value=tmp_path):
            with pytest.raises(AuthConfigError, match="Profile.*not found"):
                load_auth_config(profile="nonexistent")

    def test_priority_cli_overrides_profile(self, tmp_path):
        """Test CLI arguments override profile configuration."""
        config_dir = tmp_path / ".azlin"
        config_dir.mkdir()
        config_file = config_dir / "auth_profiles.toml"

        config_content = """
[profiles.test]
auth_method = "service_principal_secret"
tenant_id = "profile-tenant-id"
client_id = "profile-client-id"
"""
        config_file.write_text(config_content)

        cli_args = {
            "tenant_id": "11111111-1111-1111-1111-111111111111",
        }

        with patch("azlin.config_auth.Path.home", return_value=tmp_path):
            config = load_auth_config(profile="test", cli_args=cli_args)
            assert config.tenant_id == "11111111-1111-1111-1111-111111111111"

    def test_priority_env_overrides_profile(self, tmp_path):
        """Test environment variables override profile configuration."""
        config_dir = tmp_path / ".azlin"
        config_dir.mkdir()
        config_file = config_dir / "auth_profiles.toml"

        config_content = """
[profiles.test]
auth_method = "service_principal_secret"
tenant_id = "profile-tenant-id"
client_id = "profile-client-id"
"""
        config_file.write_text(config_content)

        env = {
            "AZURE_CLIENT_ID": "env-client-id",
        }

        with patch("azlin.config_auth.Path.home", return_value=tmp_path):
            with patch.dict(os.environ, env, clear=False):
                config = load_auth_config(profile="test")
                assert config.client_id == "env-client-id"

    def test_client_secret_only_from_env(self, tmp_path):
        """Test client_secret is NEVER loaded from config file (P0 security)."""
        config_dir = tmp_path / ".azlin"
        config_dir.mkdir()
        config_file = config_dir / "auth_profiles.toml"

        # Attempt to put secret in config file (should be ignored/rejected)
        config_content = """
[profiles.insecure]
auth_method = "service_principal_secret"
tenant_id = "12345678-1234-1234-1234-123456789abc"
client_id = "87654321-4321-4321-4321-cba987654321"
client_secret = "THIS-SHOULD-BE-REJECTED"
"""
        config_file.write_text(config_content)

        with patch("azlin.config_auth.Path.home", return_value=tmp_path):
            # Loading this profile should either:
            # 1. Raise an error (security violation detected)
            # 2. Load but ignore the secret (with validation failing later)
            try:
                config = load_auth_config(profile="insecure")
                # If it loads, secret should NOT be set from file
                assert config.client_secret is None or config.client_secret == ""
            except AuthConfigError as e:
                # Or it should raise an error about secret in config
                assert "secret" in str(e).lower()

    def test_managed_identity_no_secrets_required(self):
        """Test managed identity doesn't require secrets."""
        env = {
            "AZURE_AUTH_METHOD": "managed_identity",
            "AZURE_SUBSCRIPTION_ID": "abcdef01-2345-6789-abcd-ef0123456789",
        }

        with patch.dict(os.environ, env, clear=False):
            config = load_auth_config()
            assert config.auth_method == "managed_identity"
            assert config.client_secret is None
            assert config.client_certificate_path is None

    def test_fallback_to_az_cli_on_empty_config(self):
        """Test fallback to az_cli when no configuration provided."""
        with patch.dict(os.environ, {}, clear=True):
            # Clear all AZURE_* env vars
            filtered_env = {k: v for k, v in os.environ.items() if not k.startswith("AZURE_")}
            with patch.dict(os.environ, filtered_env, clear=True):
                config = load_auth_config()
                assert config.auth_method == "az_cli"

    def test_certificate_path_expansion(self):
        """Test certificate path with tilde expansion."""
        cli_args = {
            "auth_method": "service_principal_cert",
            "tenant_id": "12345678-1234-1234-1234-123456789abc",
            "client_id": "87654321-4321-4321-4321-cba987654321",
            "client_certificate_path": "~/certs/mycert.pem",
        }

        config = load_auth_config(cli_args=cli_args)
        # Path should be expanded
        assert config.client_certificate_path
        assert not config.client_certificate_path.startswith("~")

    def test_load_with_subscription_only(self):
        """Test loading with only subscription_id specified."""
        cli_args = {
            "subscription_id": "abcdef01-2345-6789-abcd-ef0123456789",
        }

        config = load_auth_config(cli_args=cli_args)
        assert config.auth_method == "az_cli"  # Default method
        assert config.subscription_id == "abcdef01-2345-6789-abcd-ef0123456789"


class TestSecurityControls:
    """Tests for P0 security controls."""

    def test_no_secrets_in_config_file_validation(self, tmp_path):
        """Test validation detects and rejects secrets in config files."""
        config_dir = tmp_path / ".azlin"
        config_dir.mkdir()
        config_file = config_dir / "auth_profiles.toml"

        config_content = """
[profiles.bad]
auth_method = "service_principal_secret"
tenant_id = "12345678-1234-1234-1234-123456789abc"
client_id = "87654321-4321-4321-4321-cba987654321"
client_secret = "secret-in-file-bad"
"""
        config_file.write_text(config_content)

        with patch("azlin.config_auth.Path.home", return_value=tmp_path):
            # Should detect secret in config file
            with pytest.raises(AuthConfigError, match="secret.*config file"):
                load_auth_config(profile="bad")

    def test_uuid_validation_regex_pattern(self):
        """Test UUID validation uses correct regex pattern."""
        valid_uuids = [
            "12345678-1234-1234-1234-123456789abc",
            "ABCDEF01-2345-6789-ABCD-EF0123456789",
            "aBcDeF01-2345-6789-aBcD-eF0123456789",
            "00000000-0000-0000-0000-000000000000",
            "ffffffff-ffff-ffff-ffff-ffffffffffff",
        ]

        for uuid in valid_uuids:
            config = AuthConfig(
                auth_method="service_principal_secret",
                tenant_id=uuid,
                client_id=uuid,
                subscription_id=uuid,
                client_secret="secret",
            )
            result = validate_auth_config(config)
            assert result.is_valid, f"UUID {uuid} should be valid"

    def test_uuid_validation_rejects_invalid_formats(self):
        """Test UUID validation rejects various invalid formats."""
        invalid_uuids = [
            "not-a-uuid",
            "12345678-1234-1234-1234",  # Too short
            "12345678-1234-1234-1234-123456789abc-extra",  # Too long
            "12345678_1234_1234_1234_123456789abc",  # Wrong separator
            "12345678-1234-1234-1234-123456789abg",  # Invalid hex char (g)
            "",  # Empty
            "12345678123412341234123456789abc",  # No separators
        ]

        for uuid in invalid_uuids:
            config = AuthConfig(
                auth_method="service_principal_secret",
                tenant_id=uuid,
                client_id="87654321-4321-4321-4321-cba987654321",
                client_secret="secret",
            )
            result = validate_auth_config(config)
            assert not result.is_valid, f"UUID {uuid} should be invalid"

    def test_certificate_file_permissions_check(self, tmp_path):
        """Test certificate file permissions are validated."""
        cert_path = tmp_path / "cert.pem"
        cert_path.write_text("MOCK CERT")

        # Test secure permissions (0600)
        cert_path.chmod(0o600)
        config = AuthConfig(
            auth_method="service_principal_cert",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_certificate_path=str(cert_path),
        )
        result = validate_auth_config(config)
        assert result.is_valid

        # Test insecure permissions (0644 - world readable)
        cert_path.chmod(0o644)
        result = validate_auth_config(config)
        # Should either warn or reject
        assert len(result.warnings) > 0 or not result.is_valid


class TestBackwardCompatibility:
    """Tests for backward compatibility (zero breaking changes)."""

    def test_existing_az_cli_workflow_unchanged(self):
        """Test existing az_cli workflow continues to work unchanged."""
        # This is the default behavior that must not break
        config = load_auth_config()
        assert config.auth_method == "az_cli"

        # Validate it
        result = validate_auth_config(config)
        assert result.is_valid

    def test_no_config_file_required(self):
        """Test that no config file is required for basic operation."""
        # Default behavior should work without any config files
        config = load_auth_config()
        assert config is not None
        assert config.auth_method == "az_cli"

    def test_subscription_id_from_env_maintained(self):
        """Test existing pattern of reading subscription from env."""
        env = {
            "AZURE_SUBSCRIPTION_ID": "abcdef01-2345-6789-abcd-ef0123456789",
        }

        with patch.dict(os.environ, env, clear=False):
            config = load_auth_config()
            assert config.subscription_id == "abcdef01-2345-6789-abcd-ef0123456789"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_none_values_handled(self):
        """Test None values are handled gracefully."""
        config = AuthConfig(
            auth_method="az_cli",
            tenant_id=None,
            client_id=None,
        )
        result = validate_auth_config(config)
        assert result.is_valid

    def test_empty_string_values_rejected(self):
        """Test empty strings are treated as invalid."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="",
            client_id="",
            client_secret="",
        )
        result = validate_auth_config(config)
        assert not result.is_valid

    def test_whitespace_values_rejected(self):
        """Test whitespace-only values are rejected."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="   ",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_secret="secret",
        )
        result = validate_auth_config(config)
        assert not result.is_valid

    def test_cli_args_none_handling(self):
        """Test cli_args=None is handled correctly."""
        config = load_auth_config(cli_args=None)
        assert config is not None

    def test_cli_args_empty_dict(self):
        """Test cli_args={} is handled correctly."""
        config = load_auth_config(cli_args={})
        assert config is not None

    def test_profile_name_preserved_in_config(self, tmp_path):
        """Test profile name is preserved in loaded config."""
        config_dir = tmp_path / ".azlin"
        config_dir.mkdir()
        config_file = config_dir / "auth_profiles.toml"

        config_content = """
[profiles.myprofile]
auth_method = "az_cli"
"""
        config_file.write_text(config_content)

        with patch("azlin.config_auth.Path.home", return_value=tmp_path):
            config = load_auth_config(profile="myprofile")
            assert config.profile_name == "myprofile"

    def test_multiple_validation_errors(self):
        """Test multiple validation errors are all reported."""
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="invalid-tenant",
            client_id="invalid-client",
            subscription_id="invalid-sub",
            client_secret=None,  # Missing
        )
        result = validate_auth_config(config)
        assert not result.is_valid
        # Should have multiple errors
        assert len(result.errors) >= 3
