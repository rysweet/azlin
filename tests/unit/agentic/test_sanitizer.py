"""Unit tests for secret sanitizer."""

from azlin.agentic.utils.sanitizer import SecretSanitizer, sanitize_output


class TestSecretSanitizer:
    """Test SecretSanitizer class."""

    def test_sanitize_azure_storage_account_key(self):
        """Test sanitizing Azure Storage account keys."""
        sanitizer = SecretSanitizer()
        text = "AccountKey=abc123xyz456def789ghi012jkl345mno678pqr901stu234vwx567yza890bcd123efg456===="
        result = sanitizer.sanitize(text)

        assert "abc123xyz456" not in result
        assert "***REDACTED***" in result

    def test_sanitize_connection_string(self):
        """Test sanitizing Azure connection strings."""
        sanitizer = SecretSanitizer()
        text = (
            "DefaultEndpointsProtocol=https;AccountName=myaccount;"
            "AccountKey=abc123xyz456def789ghi012jkl345mno678pqr901stu234vwx567yza890bcd123efg456====;"
            "EndpointSuffix=core.windows.net"
        )
        result = sanitizer.sanitize(text)

        assert "abc123xyz456" not in result
        assert "***REDACTED***" in result
        assert "AccountName=myaccount" in result  # Name is OK

    def test_sanitize_sas_token(self):
        """Test sanitizing SAS tokens."""
        sanitizer = SecretSanitizer()
        text = "https://myaccount.blob.core.windows.net/container?sv=2020-08-04&sig=abc123xyz456"
        result = sanitizer.sanitize(text)

        assert "abc123xyz456" not in result
        assert "***REDACTED***" in result

    def test_sanitize_anthropic_api_key(self):
        """Test sanitizing Anthropic API keys."""
        sanitizer = SecretSanitizer()
        text = "ANTHROPIC_API_KEY=sk-ant-api03-abc123xyz456def789ghi012jkl345mno678pqr901stu234vwx567yza890bcd123"
        result = sanitizer.sanitize(text)

        assert "abc123xyz456" not in result
        assert "sk-ant-***REDACTED***" in result

    def test_sanitize_generic_api_key(self):
        """Test sanitizing generic API keys."""
        sanitizer = SecretSanitizer()
        text = "api_key=abc123xyz456def789ghi012"
        result = sanitizer.sanitize(text)

        assert "abc123xyz456" not in result
        assert "api_key=***REDACTED***" in result

    def test_sanitize_bearer_token(self):
        """Test sanitizing Bearer tokens."""
        sanitizer = SecretSanitizer()
        text = (
            "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        )
        result = sanitizer.sanitize(text)

        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        assert "Bearer ***REDACTED***" in result

    def test_sanitize_jwt_token(self):
        """Test sanitizing JWT tokens."""
        sanitizer = SecretSanitizer()
        text = "Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        result = sanitizer.sanitize(text)

        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        assert "***REDACTED_JWT***" in result

    def test_sanitize_password_in_url(self):
        """Test sanitizing passwords in URLs."""
        sanitizer = SecretSanitizer()
        text = "https://user:password123@example.com/path"
        result = sanitizer.sanitize(text)

        assert "password123" not in result
        assert "***REDACTED***" in result

    def test_sanitize_generic_password(self):
        """Test sanitizing generic passwords."""
        sanitizer = SecretSanitizer()
        text = "password=MySecretPassword123"
        result = sanitizer.sanitize(text)

        assert "MySecretPassword123" not in result
        assert "password=***REDACTED***" in result

    def test_sanitize_client_secret(self):
        """Test sanitizing Azure service principal client secrets."""
        sanitizer = SecretSanitizer()
        text = "client_secret=abc123xyz456def789ghi012jkl345mno678"
        result = sanitizer.sanitize(text)

        assert "abc123xyz456" not in result
        assert "client_secret=***REDACTED***" in result

    def test_sanitize_ssh_private_key(self):
        """Test sanitizing SSH private keys."""
        sanitizer = SecretSanitizer()
        text = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA1234567890abcdef
-----END RSA PRIVATE KEY-----"""
        result = sanitizer.sanitize(text)

        assert "MIIEpAIBAAKCAQEA1234567890abcdef" not in result
        assert "***REDACTED***" in result
        assert "BEGIN RSA PRIVATE KEY" in result  # Headers preserved

    def test_sanitize_shared_access_signature(self):
        """Test sanitizing SharedAccessSignature."""
        sanitizer = SecretSanitizer()
        text = "BlobEndpoint=https://myaccount.blob.core.windows.net/;SharedAccessSignature=sv=2020-08-04&ss=bfqt&srt=sco&sp=rwdlacupx&se=2024-01-01T00:00:00Z&st=2023-01-01T00:00:00Z&spr=https&sig=abc123xyz456"
        result = sanitizer.sanitize(text)

        assert "abc123xyz456" not in result
        assert "SharedAccessSignature=***REDACTED***" in result

    def test_sanitize_none(self):
        """Test sanitizing None returns None."""
        sanitizer = SecretSanitizer()
        result = sanitizer.sanitize(None)
        assert result is None

    def test_sanitize_empty_string(self):
        """Test sanitizing empty string."""
        sanitizer = SecretSanitizer()
        result = sanitizer.sanitize("")
        assert result == ""

    def test_sanitize_no_secrets(self):
        """Test sanitizing text with no secrets."""
        sanitizer = SecretSanitizer()
        text = "This is normal text with no secrets"
        result = sanitizer.sanitize(text)
        assert result == text

    def test_sanitize_dict(self):
        """Test sanitizing dictionaries."""
        sanitizer = SecretSanitizer()
        data = {
            "connection_string": "AccountKey=abc123xyz456def789ghi012jkl345mno678pqr901stu234vwx567yza890bcd123efg456====",
            "safe_value": "This is safe",
            "nested": {
                "api_key": "sk-ant-api03-abc123xyz456def789ghi012jkl345mno678pqr901stu234vwx567yza890bcd123"
            },
        }
        result = sanitizer.sanitize_dict(data)

        assert "abc123xyz456" not in str(result)
        assert "***REDACTED***" in result["connection_string"]
        assert result["safe_value"] == "This is safe"
        assert "***REDACTED***" in result["nested"]["api_key"]

    def test_sanitize_list(self):
        """Test sanitizing lists."""
        sanitizer = SecretSanitizer()
        data = [
            "AccountKey=abc123xyz456def789ghi012jkl345mno678pqr901stu234vwx567yza890bcd123efg456====",
            "Normal text",
            {"api_key": "secret123456789012345678"},
        ]
        result = sanitizer.sanitize_list(data)

        assert "abc123xyz456" not in str(result)
        assert "***REDACTED***" in result[0]
        assert result[1] == "Normal text"
        assert "***REDACTED***" in result[2]["api_key"]

    def test_sanitize_nested_structures(self):
        """Test sanitizing deeply nested data structures."""
        sanitizer = SecretSanitizer()
        data = {
            "level1": {
                "level2": {
                    "level3": [
                        "AccountKey=abc123xyz456def789ghi012jkl345mno678pqr901stu234vwx567yza890bcd123efg456===="
                    ]
                }
            }
        }
        result = sanitizer.sanitize_dict(data)

        assert "abc123xyz456" not in str(result)
        assert "***REDACTED***" in result["level1"]["level2"]["level3"][0]

    def test_sanitize_output_convenience_function(self):
        """Test convenience function."""
        text = "AccountKey=abc123xyz456def789ghi012jkl345mno678pqr901stu234vwx567yza890bcd123efg456===="
        result = sanitize_output(text)

        assert "abc123xyz456" not in result
        assert "***REDACTED***" in result

    def test_sanitize_multiple_secrets_in_one_string(self):
        """Test sanitizing multiple different types of secrets."""
        sanitizer = SecretSanitizer()
        text = (
            "Connection: AccountKey=abc123xyz456def789ghi012jkl345mno678pqr901stu234vwx567yza890bcd123efg456==== "
            "and API: api_key=secret123456789012345678 "
            "Bearer: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        )
        result = sanitizer.sanitize(text)

        assert "abc123xyz456" not in result
        assert "secret123456789012345678" not in result
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        assert result.count("***REDACTED***") >= 3
