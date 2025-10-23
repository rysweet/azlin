"""Security tests for auth_security module.

Tests log sanitization, UUID validation, secret detection, and subprocess arg sanitization.
All tests follow TDD principles with comprehensive coverage of security controls.
"""

from azlin.auth_security import (
    ValidationResult,
    detect_secrets_in_config,
    sanitize_log,
    sanitize_subprocess_args,
    validate_uuid,
)


class TestLogSanitization:
    """Test log sanitization for various secret patterns."""

    def test_sanitize_client_secret_env_var(self):
        """Test sanitizing AZURE_CLIENT_SECRET environment variable."""
        message = "Using AZURE_CLIENT_SECRET=abc123def456 for authentication"
        result = sanitize_log(message)
        assert "abc123def456" not in result
        assert "***REDACTED***" in result

    def test_sanitize_bearer_token(self):
        """Test sanitizing Bearer tokens."""
        message = "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc"
        result = sanitize_log(message)
        assert "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        assert "***REDACTED***" in result

    def test_sanitize_pem_certificate(self):
        """Test sanitizing PEM certificate blocks."""
        message = """Certificate:
-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAKZ5Z5Z5Z5Z5MA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV
BAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBX
-----END CERTIFICATE-----
Loaded successfully"""
        result = sanitize_log(message)
        assert "MIIDXTCCAkWgAwIBAgIJAKZ5Z5Z5Z5Z5MA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV" not in result
        assert "***REDACTED***" in result
        assert "Loaded successfully" in result

    def test_sanitize_private_key(self):
        """Test sanitizing private key blocks."""
        message = """Private key:
-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDZ1234567890ab
cdefghijklmnopqrstuvwxyz1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ1234
-----END PRIVATE KEY-----
Done"""
        result = sanitize_log(message)
        assert "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDZ1234567890ab" not in result
        assert "***REDACTED***" in result

    def test_sanitize_rsa_private_key(self):
        """Test sanitizing RSA private key blocks."""
        message = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA1234567890abcdefghijklmnopqrstuvwxyz
-----END RSA PRIVATE KEY-----"""
        result = sanitize_log(message)
        assert "MIIEpAIBAAKCAQEA1234567890abcdefghijklmnopqrstuvwxyz" not in result
        assert "***REDACTED***" in result

    def test_sanitize_long_hex_string(self):
        """Test sanitizing long hex strings (potential secrets)."""
        message = "Token: a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8"
        result = sanitize_log(message)
        assert "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8" not in result
        assert "***REDACTED***" in result

    def test_sanitize_long_base64_string(self):
        """Test sanitizing long base64 strings (potential tokens)."""
        message = "Access token: dGhpc2lzYWxvbmdiYXNlNjRzdHJpbmd0aGF0Y291bGRiZWF0b2tlbg=="
        result = sanitize_log(message)
        assert "dGhpc2lzYWxvbmdiYXNlNjRzdHJpbmd0aGF0Y291bGRiZWF0b2tlbg==" not in result
        assert "***REDACTED***" in result

    def test_sanitize_password_field(self):
        """Test sanitizing password fields."""
        message = "Connecting with password=SuperSecret123!"
        result = sanitize_log(message)
        assert "SuperSecret123!" not in result
        assert "***REDACTED***" in result

    def test_sanitize_secret_key_field(self):
        """Test sanitizing secret_key fields."""
        message = "Config: secret_key=my-secret-key-value-123"
        result = sanitize_log(message)
        assert "my-secret-key-value-123" not in result
        assert "***REDACTED***" in result

    def test_sanitize_multiple_secrets(self):
        """Test sanitizing multiple secrets in one message."""
        message = "Auth with client_secret=abc123 and password=xyz789"
        result = sanitize_log(message)
        assert "abc123" not in result
        assert "xyz789" not in result
        assert result.count("***REDACTED***") == 2

    def test_sanitize_preserves_safe_content(self):
        """Test that safe content is preserved."""
        message = "Processing VM: my-vm-name in subscription 12345678-1234-1234-1234-123456789abc"
        result = sanitize_log(message)
        assert "Processing VM: my-vm-name" in result
        assert "12345678-1234-1234-1234-123456789abc" in result

    def test_sanitize_empty_string(self):
        """Test sanitizing empty string."""
        result = sanitize_log("")
        assert result == ""

    def test_sanitize_no_secrets(self):
        """Test that messages without secrets are unchanged."""
        message = "Successfully connected to Azure"
        result = sanitize_log(message)
        assert result == message

    def test_sanitize_client_secret_equals_format(self):
        """Test client_secret=value format."""
        message = "Using client_secret=a1b2c3d4e5f6"
        result = sanitize_log(message)
        assert "a1b2c3d4e5f6" not in result
        assert "***REDACTED***" in result

    def test_sanitize_azure_environment_variables(self):
        """Test sanitizing various Azure environment variable formats."""
        message = "Env: AZURE_CLIENT_SECRET=secret123, AZURE_TENANT_ID=tenant-id"
        result = sanitize_log(message)
        assert "secret123" not in result
        assert "***REDACTED***" in result
        assert "tenant-id" in result  # Tenant ID is not a secret

    def test_sanitize_json_with_secrets(self):
        """Test sanitizing JSON containing secrets."""
        message = '{"client_id": "abc", "client_secret": "secret123", "tenant_id": "xyz"}'
        result = sanitize_log(message)
        assert "secret123" not in result
        assert "***REDACTED***" in result


class TestUUIDValidation:
    """Test UUID validation for Azure IDs."""

    def test_validate_valid_uuid_lowercase(self):
        """Test validating valid lowercase UUID."""
        result = validate_uuid("12345678-1234-1234-1234-123456789abc", "test_id")
        assert result.valid is True
        assert result.error is None

    def test_validate_valid_uuid_uppercase(self):
        """Test validating valid uppercase UUID."""
        result = validate_uuid("12345678-1234-1234-1234-123456789ABC", "test_id")
        assert result.valid is True
        assert result.error is None

    def test_validate_valid_uuid_mixed_case(self):
        """Test validating valid mixed case UUID."""
        result = validate_uuid("12345678-1234-AbCd-1234-123456789aBc", "test_id")
        assert result.valid is True
        assert result.error is None

    def test_validate_invalid_uuid_missing_hyphens(self):
        """Test validating UUID without hyphens."""
        result = validate_uuid("12345678123412341234123456789abc", "tenant_id")
        assert result.valid is False
        assert "tenant_id" in result.error
        assert "invalid UUID format" in result.error

    def test_validate_invalid_uuid_wrong_length(self):
        """Test validating UUID with wrong length."""
        result = validate_uuid("1234-1234-1234-1234", "subscription_id")
        assert result.valid is False
        assert "subscription_id" in result.error

    def test_validate_invalid_uuid_non_hex_chars(self):
        """Test validating UUID with non-hex characters."""
        result = validate_uuid("12345678-1234-1234-1234-12345678GHIJ", "client_id")
        assert result.valid is False
        assert "client_id" in result.error

    def test_validate_invalid_uuid_wrong_segment_lengths(self):
        """Test validating UUID with wrong segment lengths."""
        result = validate_uuid("123-12345-1234-1234-123456789abc", "test_id")
        assert result.valid is False

    def test_validate_empty_string(self):
        """Test validating empty string."""
        result = validate_uuid("", "test_id")
        assert result.valid is False
        assert "test_id" in result.error

    def test_validate_none_value(self):
        """Test validating None value."""
        result = validate_uuid(None, "test_id")
        assert result.valid is False
        assert "test_id" in result.error

    def test_validate_whitespace(self):
        """Test validating whitespace."""
        result = validate_uuid("   ", "test_id")
        assert result.valid is False

    def test_validate_uuid_with_whitespace(self):
        """Test validating UUID with leading/trailing whitespace."""
        result = validate_uuid(" 12345678-1234-1234-1234-123456789abc ", "test_id")
        assert result.valid is False  # Should not auto-trim

    def test_validate_special_characters(self):
        """Test validating UUID with special characters."""
        result = validate_uuid("12345678-1234-1234-1234-123456789ab$", "test_id")
        assert result.valid is False

    def test_field_name_in_error_message(self):
        """Test that field name appears in error message."""
        result = validate_uuid("invalid", "subscription_id")
        assert result.valid is False
        assert "subscription_id" in result.error


class TestSecretDetection:
    """Test secret detection in configuration."""

    def test_detect_client_secret_field(self):
        """Test detecting client_secret field (FORBIDDEN)."""
        config = {"client_id": "abc", "client_secret": "secret123"}
        secrets = detect_secrets_in_config(config)
        assert "client_secret" in secrets

    def test_detect_password_field(self):
        """Test detecting password field."""
        config = {"username": "user", "password": "pass123"}
        secrets = detect_secrets_in_config(config)
        assert "password" in secrets

    def test_detect_secret_key_field(self):
        """Test detecting secret_key field."""
        config = {"api_key": "key123", "secret_key": "secret123"}
        secrets = detect_secrets_in_config(config)
        assert "secret_key" in secrets

    def test_detect_api_key_field(self):
        """Test detecting api_key field."""
        config = {"api_key": "key123"}
        secrets = detect_secrets_in_config(config)
        assert "api_key" in secrets

    def test_detect_token_field(self):
        """Test detecting token field."""
        config = {"access_token": "token123"}
        secrets = detect_secrets_in_config(config)
        assert "access_token" in secrets

    def test_detect_auth_token_field(self):
        """Test detecting auth_token field."""
        config = {"auth_token": "token123"}
        secrets = detect_secrets_in_config(config)
        assert "auth_token" in secrets

    def test_detect_bearer_token_field(self):
        """Test detecting bearer_token field."""
        config = {"bearer_token": "token123"}
        secrets = detect_secrets_in_config(config)
        assert "bearer_token" in secrets

    def test_detect_long_base64_value(self):
        """Test detecting long base64 strings as potential secrets."""
        config = {"data": "dGhpc2lzYWxvbmdiYXNlNjRzdHJpbmd0aGF0Y291bGRiZWFzZWNyZXR0b2tlbg=="}
        secrets = detect_secrets_in_config(config)
        assert "data" in secrets

    def test_detect_long_hex_value(self):
        """Test detecting long hex strings as potential secrets."""
        config = {"token": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8"}
        secrets = detect_secrets_in_config(config)
        assert "token" in secrets

    def test_detect_nested_secrets(self):
        """Test detecting secrets in nested dictionaries."""
        config = {"azure": {"credentials": {"client_secret": "secret123"}}}
        secrets = detect_secrets_in_config(config)
        assert "azure.credentials.client_secret" in secrets

    def test_detect_multiple_secrets(self):
        """Test detecting multiple secrets."""
        config = {
            "client_secret": "secret123",
            "password": "pass123",
            "api_key": "key123",
        }
        secrets = detect_secrets_in_config(config)
        assert len(secrets) == 3
        assert "client_secret" in secrets
        assert "password" in secrets
        assert "api_key" in secrets

    def test_no_secrets_in_safe_config(self):
        """Test that safe config has no detected secrets."""
        config = {
            "client_id": "12345678-1234-1234-1234-123456789abc",
            "tenant_id": "87654321-4321-4321-4321-cba987654321",
            "subscription_id": "11111111-2222-3333-4444-555555555555",
            "resource_group": "my-rg",
        }
        secrets = detect_secrets_in_config(config)
        assert len(secrets) == 0

    def test_detect_secrets_empty_config(self):
        """Test detecting secrets in empty config."""
        secrets = detect_secrets_in_config({})
        assert len(secrets) == 0

    def test_detect_secrets_with_short_values(self):
        """Test that short values are not flagged as secrets."""
        config = {"name": "test", "count": 5, "enabled": True}
        secrets = detect_secrets_in_config(config)
        assert len(secrets) == 0

    def test_detect_private_key_field(self):
        """Test detecting private_key field."""
        config = {"private_key": "-----BEGIN PRIVATE KEY-----\nMII..."}
        secrets = detect_secrets_in_config(config)
        assert "private_key" in secrets

    def test_detect_certificate_field(self):
        """Test detecting certificate field."""
        config = {"certificate": "-----BEGIN CERTIFICATE-----\nMII..."}
        secrets = detect_secrets_in_config(config)
        assert "certificate" in secrets

    def test_safe_azure_ids_not_detected(self):
        """Test that Azure UUIDs are not detected as secrets."""
        config = {
            "subscription_id": "12345678-1234-1234-1234-123456789abc",
            "tenant_id": "87654321-4321-4321-4321-cba987654321",
        }
        secrets = detect_secrets_in_config(config)
        assert len(secrets) == 0

    def test_detect_secrets_with_list_values(self):
        """Test detecting secrets in list values."""
        config = {
            "credentials": [
                {"username": "user1", "password": "pass1"},
                {"username": "user2", "api_key": "key2"},
            ]
        }
        secrets = detect_secrets_in_config(config)
        assert "credentials[0].password" in secrets
        assert "credentials[1].api_key" in secrets

    def test_detect_partial_match_in_field_name(self):
        """Test detecting partial matches like my_password, api_secret."""
        config = {
            "my_password": "secret123",
            "api_secret": "key456",
            "auth_token_value": "token789",
        }
        secrets = detect_secrets_in_config(config)
        assert "my_password" in secrets
        assert "api_secret" in secrets
        assert "auth_token_value" in secrets

    def test_detect_long_hex_string_in_value(self):
        """Test detecting long hex string in config value."""
        config = {"data_token": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8"}
        secrets = detect_secrets_in_config(config)
        assert "data_token" in secrets


class TestSubprocessArgSanitization:
    """Test subprocess argument sanitization for logging."""

    def test_sanitize_client_secret_flag(self):
        """Test sanitizing --client-secret flag."""
        args = ["az", "login", "--client-secret", "secret123", "--tenant-id", "tenant"]
        result = sanitize_subprocess_args(args)
        assert "secret123" not in result
        assert result[result.index("--client-secret") + 1] == "***REDACTED***"
        assert "tenant" in result

    def test_sanitize_password_flag(self):
        """Test sanitizing --password flag."""
        args = ["ssh", "-p", "22", "--password", "mypassword", "user@host"]
        result = sanitize_subprocess_args(args)
        assert "mypassword" not in result
        assert result[result.index("--password") + 1] == "***REDACTED***"

    def test_sanitize_secret_flag(self):
        """Test sanitizing --secret flag."""
        args = ["command", "--secret", "topsecret"]
        result = sanitize_subprocess_args(args)
        assert "topsecret" not in result
        assert result[result.index("--secret") + 1] == "***REDACTED***"

    def test_sanitize_token_flag(self):
        """Test sanitizing --token flag."""
        args = ["api-call", "--token", "bearer-token-123"]
        result = sanitize_subprocess_args(args)
        assert "bearer-token-123" not in result
        assert result[result.index("--token") + 1] == "***REDACTED***"

    def test_sanitize_api_key_flag(self):
        """Test sanitizing --api-key flag."""
        args = ["curl", "--api-key", "key123"]
        result = sanitize_subprocess_args(args)
        assert "key123" not in result
        assert result[result.index("--api-key") + 1] == "***REDACTED***"

    def test_sanitize_auth_token_flag(self):
        """Test sanitizing --auth-token flag."""
        args = ["command", "--auth-token", "token123"]
        result = sanitize_subprocess_args(args)
        assert "token123" not in result

    def test_sanitize_equals_format(self):
        """Test sanitizing --secret=value format."""
        args = ["command", "--client-secret=secret123", "--other=safe"]
        result = sanitize_subprocess_args(args)
        assert "secret123" not in result
        assert "--client-secret=***REDACTED***" in result
        assert "--other=safe" in result

    def test_sanitize_multiple_secrets(self):
        """Test sanitizing multiple secret flags."""
        args = ["az", "login", "--client-secret", "secret1", "--password", "secret2"]
        result = sanitize_subprocess_args(args)
        assert "secret1" not in result
        assert "secret2" not in result
        assert result.count("***REDACTED***") == 2

    def test_sanitize_preserves_safe_args(self):
        """Test that safe arguments are preserved."""
        args = ["az", "vm", "list", "--resource-group", "my-rg"]
        result = sanitize_subprocess_args(args)
        assert result == args

    def test_sanitize_empty_args(self):
        """Test sanitizing empty argument list."""
        result = sanitize_subprocess_args([])
        assert result == []

    def test_sanitize_no_sensitive_args(self):
        """Test sanitizing args with no sensitive data."""
        args = ["ls", "-la", "/tmp"]
        result = sanitize_subprocess_args(args)
        assert result == args

    def test_sanitize_uppercase_flags(self):
        """Test sanitizing uppercase secret flags."""
        args = ["command", "--CLIENT-SECRET", "secret123"]
        result = sanitize_subprocess_args(args)
        assert "secret123" not in result

    def test_sanitize_short_flags(self):
        """Test sanitizing short flag formats."""
        args = ["command", "-p", "password123"]
        result = sanitize_subprocess_args(args)
        assert "password123" not in result

    def test_sanitize_private_key_flag(self):
        """Test sanitizing --private-key flag."""
        args = ["ssh", "--private-key", "/path/to/key"]
        result = sanitize_subprocess_args(args)
        # File paths should be redacted too
        assert result[result.index("--private-key") + 1] == "***REDACTED***"

    def test_sanitize_certificate_flag(self):
        """Test sanitizing --certificate flag."""
        args = ["command", "--certificate", "cert-value"]
        result = sanitize_subprocess_args(args)
        assert "cert-value" not in result

    def test_sanitize_mixed_case_secret_flag(self):
        """Test sanitizing mixed case secret flags."""
        args = ["command", "--Client-Secret", "secret123"]
        result = sanitize_subprocess_args(args)
        assert "secret123" not in result

    def test_sanitize_underscore_format_flag(self):
        """Test sanitizing underscore format flags."""
        args = ["command", "--client_secret", "secret123"]
        result = sanitize_subprocess_args(args)
        assert "secret123" not in result

    def test_sanitize_access_token_equals_format(self):
        """Test sanitizing access-token with equals format."""
        args = ["curl", "--access-token=token123"]
        result = sanitize_subprocess_args(args)
        assert "token123" not in result
        assert "--access-token=***REDACTED***" in result


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_validation_result_valid(self):
        """Test ValidationResult for valid case."""
        result = ValidationResult(valid=True, error=None)
        assert result.valid is True
        assert result.error is None

    def test_validation_result_invalid(self):
        """Test ValidationResult for invalid case."""
        result = ValidationResult(valid=False, error="Test error")
        assert result.valid is False
        assert result.error == "Test error"

    def test_validation_result_repr(self):
        """Test ValidationResult string representation."""
        result = ValidationResult(valid=False, error="Test error")
        repr_str = repr(result)
        assert "valid=False" in repr_str
        assert "Test error" in repr_str


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_sanitize_log_with_unicode(self):
        """Test sanitizing log with unicode characters."""
        message = "User: 用户 with client_secret=secret123"
        result = sanitize_log(message)
        assert "用户" in result
        assert "secret123" not in result

    def test_sanitize_log_with_newlines(self):
        """Test sanitizing log with newlines."""
        message = "Line 1\nclient_secret=secret123\nLine 3"
        result = sanitize_log(message)
        assert "secret123" not in result
        assert "Line 1" in result
        assert "Line 3" in result

    def test_detect_secrets_with_none_values(self):
        """Test detecting secrets with None values."""
        config = {"client_id": "abc", "password": None}
        secrets = detect_secrets_in_config(config)
        # None values should not be flagged as secrets
        assert "password" not in secrets

    def test_detect_secrets_with_numeric_values(self):
        """Test detecting secrets with numeric values."""
        config = {"port": 22, "timeout": 30}
        secrets = detect_secrets_in_config(config)
        assert len(secrets) == 0

    def test_sanitize_subprocess_args_last_arg_is_flag(self):
        """Test sanitizing when last arg is a secret flag without value."""
        args = ["command", "--client-secret"]
        result = sanitize_subprocess_args(args)
        # Should handle gracefully without index error
        assert "--client-secret" in result

    def test_validate_uuid_all_zeros(self):
        """Test validating all-zeros UUID."""
        result = validate_uuid("00000000-0000-0000-0000-000000000000", "test_id")
        assert result.valid is True

    def test_validate_uuid_all_fs(self):
        """Test validating all-Fs UUID."""
        result = validate_uuid("ffffffff-ffff-ffff-ffff-ffffffffffff", "test_id")
        assert result.valid is True

    def test_sanitize_log_performance_large_message(self):
        """Test sanitizing very large log message."""
        large_message = "Safe content " * 1000 + "client_secret=secret123"
        result = sanitize_log(large_message)
        assert "secret123" not in result
        assert "Safe content" in result

    def test_detect_secrets_deeply_nested(self):
        """Test detecting secrets in deeply nested config."""
        config = {"level1": {"level2": {"level3": {"level4": {"client_secret": "secret123"}}}}}
        secrets = detect_secrets_in_config(config)
        assert "level1.level2.level3.level4.client_secret" in secrets
