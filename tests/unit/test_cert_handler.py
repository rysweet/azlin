"""Unit tests for cert_handler module.

Tests certificate validation, permissions checks, and expiration monitoring.
Following TDD principles - these tests are written first and should initially fail.
"""

import os
import stat
import tempfile
from datetime import UTC, datetime, timedelta

import pytest

from azlin.cert_handler import (
    check_expiration,
    fix_certificate_permissions,
    validate_certificate,
)

# Sample valid PEM certificate (self-signed, expires in 2099)
VALID_CERT_PEM = """-----BEGIN CERTIFICATE-----
MIIDQDCCAiigAwIBAgIUFuBdAEnDMBPNyoJ9ZNidM6cZ4WEwDQYJKoZIhvcNAQEL
BQAwWTELMAkGA1UEBhMCVVMxDTALBgNVBAgMBFRlc3QxDTALBgNVBAcMBFRlc3Qx
ETAPBgNVBAoMCFRlc3QgT3JnMRkwFwYDVQQDDBB0ZXN0LmV4YW1wbGUuY29tMCAX
DTI0MDEwMTAwMDAwMFoYDzIwOTkxMjMxMDAwMDAwWjBZMQswCQYDVQQGEwJVUzEN
MAsGA1UECAwEVGVzdDENMAsGA1UEBwwEVGVzdDERMA8GA1UECgwIVGVzdCBPcmcx
GTAXBgNVBAMMEHRlc3QuZXhhbXBsZS5jb20wggEiMA0GCSqGSIb3DQEBAQUAA4IB
DwAwggEKAoIBAQDg6HBgreH7lcfjD5UvR3GMxYV6+02f0AizCtkRFSzfyIOvchAe
MmiRSSfmXpS+lkTyqkItMQiVDwl826ZasmNCdXoBqfSap8rrQPQv4G+KddH6TXLn
6aX22BwYMuFN52GHB1D3wREqJCpwNXiaz1zFpdiINeEMScrhZFh1te2VKlCheC4i
v1/nuKOas1bmBVS9LKjjaLeLSH85fN+pO4mZJ4esunl0rkPPXgHkjyyRhFf5riQH
EAcuA0XdfP68c0Smy/G4/ssIw18v79eWdUoNCjaxnc6XTBPATjKESVwqsoud7lDH
zKQxWJSCzJWoewo2l1EJI2NBlyYi/d+6AbzLAgMBAAEwDQYJKoZIhvcNAQELBQAD
ggEBAKSlZ/8rwyZdFJ2O+dsrCpGpzDBz0RfDAn/tM8+/3rkRVfvIF1zpA/5IOU+V
O6EvkCZ3FIueZ4icwVvferzx+zjjdjTIpQqu4zk3GxSCD/Ux3B5KzhZprWQ7tJAe
zoQYmKS8UOnFjgj4FmchE30jV+Mofz7WYTuypph4TWWJKbWjOv4OH+uWUYQ8xMnT
40eRQ7n1aooASJCkXek2+sbQ9Um+WBtNnKyP8kXNFBssTwZy5ubO9H0UtGXdMyrZ
fWrb1G0xEfH4K0xp+6mCNZgDZBiWPyEmERUeoi/ilrUlL9YR7nvbJYpUWEvE15ao
7O7lH1JMJO/c1IB51LxuhyzRQgI=
-----END CERTIFICATE-----
"""

# Sample expired certificate (expires in 2020)
EXPIRED_CERT_PEM = """-----BEGIN CERTIFICATE-----
MIIDPjCCAiagAwIBAgIUQeS2CCCiebwIV7s/JotIV+I0P10wDQYJKoZIhvcNAQEL
BQAwWTELMAkGA1UEBhMCVVMxDTALBgNVBAgMBFRlc3QxDTALBgNVBAcMBFRlc3Qx
ETAPBgNVBAoMCFRlc3QgT3JnMRkwFwYDVQQDDBB0ZXN0LmV4YW1wbGUuY29tMB4X
DTIwMDEwMTAwMDAwMFoXDTIwMDEwMjAwMDAwMFowWTELMAkGA1UEBhMCVVMxDTAL
BgNVBAgMBFRlc3QxDTALBgNVBAcMBFRlc3QxETAPBgNVBAoMCFRlc3QgT3JnMRkw
FwYDVQQDDBB0ZXN0LmV4YW1wbGUuY29tMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A
MIIBCgKCAQEA4OhwYK3h+5XH4w+VL0dxjMWFevtNn9AIswrZERUs38iDr3IQHjJo
kUkn5l6UvpZE8qpCLTEIlQ8JfNumWrJjQnV6Aan0mqfK60D0L+BvinXR+k1y5+ml
9tgcGDLhTedhhwdQ98ERKiQqcDV4ms9cxaXYiDXhDEnK4WRYdbXtlSpQoXguIr9f
57ijmrNW5gVUvSyo42i3i0h/OXzfqTuJmSeHrLp5dK5Dz14B5I8skYRX+a4kBxAH
LgNF3Xz+vHNEpsvxuP7LCMNfL+/XlnVKDQo2sZ3Ol0wTwE4yhElcKrKLne5Qx8yk
MViUgsyVqHsKNpdRCSNjQZcmIv3fugG8ywIDAQABMA0GCSqGSIb3DQEBCwUAA4IB
AQDR/mJrzAAy1SSEy0aKSi/sEon21fHhpHaIR/eRMbMf+bgBabNIkSwaXpxqdqMU
T54VtMWTCd1/xOloRJKZPUv/o7w3JzNFDq1wDef+2nh8DqmMo86f/5Q4EXEZ5swu
308hfw8la790qenSwjEpu2upNoLdxNzg+IRciZuEwxgYzEzPeCe2B2kGzxdcFDIp
BqRhV5cxN3cu+7fxufNPgZcZm/8NlBfNbrirIVpac3xQTtV83GKJnbIhISDsz1HT
lhv9kvRQjmPrqY9BwLJozVOWm1hfPo9O28AONrL8PuoLKImNYfhiBGNFynniypCX
GAvottZ49l9nx3gqoWY7BDL+
-----END CERTIFICATE-----
"""

# Invalid certificate content
INVALID_CERT_CONTENT = """Not a real certificate at all!
This is just some random text.
It should fail validation."""


@pytest.fixture
def temp_cert_file():
    """Create a temporary certificate file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pem") as f:
        cert_path = f.name
    yield cert_path
    # Cleanup
    if os.path.exists(cert_path):
        os.unlink(cert_path)


@pytest.fixture
def valid_cert_0600(temp_cert_file):
    """Create a valid certificate with 0600 permissions."""
    with open(temp_cert_file, "w") as f:
        f.write(VALID_CERT_PEM)
    os.chmod(temp_cert_file, 0o600)
    return temp_cert_file


@pytest.fixture
def valid_cert_0400(temp_cert_file):
    """Create a valid certificate with 0400 permissions."""
    with open(temp_cert_file, "w") as f:
        f.write(VALID_CERT_PEM)
    os.chmod(temp_cert_file, 0o400)
    return temp_cert_file


@pytest.fixture
def cert_wrong_perms(temp_cert_file):
    """Create a certificate with incorrect permissions (0644)."""
    with open(temp_cert_file, "w") as f:
        f.write(VALID_CERT_PEM)
    os.chmod(temp_cert_file, 0o644)
    return temp_cert_file


@pytest.fixture
def expired_cert_0600(temp_cert_file):
    """Create an expired certificate with correct permissions."""
    with open(temp_cert_file, "w") as f:
        f.write(EXPIRED_CERT_PEM)
    os.chmod(temp_cert_file, 0o600)
    return temp_cert_file


@pytest.fixture
def invalid_cert_0600(temp_cert_file):
    """Create an invalid certificate file with correct permissions."""
    with open(temp_cert_file, "w") as f:
        f.write(INVALID_CERT_CONTENT)
    os.chmod(temp_cert_file, 0o600)
    return temp_cert_file


class TestValidateCertificate:
    """Test certificate validation functionality."""

    def test_validate_nonexistent_file(self):
        """Test validation of non-existent certificate file."""
        result = validate_certificate("/nonexistent/path/cert.pem")

        assert not result.valid
        assert result.cert_path == "/nonexistent/path/cert.pem"
        assert len(result.errors) > 0
        assert any(
            "not found" in err.lower() or "does not exist" in err.lower() for err in result.errors
        )

    def test_validate_cert_with_correct_perms_0600(self, valid_cert_0600):
        """Test validation of certificate with 0600 permissions."""
        result = validate_certificate(valid_cert_0600)

        assert result.valid
        assert result.cert_path == valid_cert_0600
        assert result.permissions == 0o600
        assert len(result.errors) == 0
        assert result.expiration_date is not None

    def test_validate_cert_with_correct_perms_0400(self, valid_cert_0400):
        """Test validation of certificate with 0400 permissions."""
        result = validate_certificate(valid_cert_0400)

        assert result.valid
        assert result.cert_path == valid_cert_0400
        assert result.permissions == 0o400
        assert len(result.errors) == 0
        assert result.expiration_date is not None

    def test_validate_cert_with_wrong_perms(self, cert_wrong_perms):
        """Test validation fails for certificate with incorrect permissions."""
        result = validate_certificate(cert_wrong_perms)

        assert not result.valid
        assert result.permissions == 0o644
        assert len(result.errors) > 0
        assert any("permission" in err.lower() for err in result.errors)
        assert any("0600" in err or "0400" in err for err in result.errors)

    def test_validate_cert_too_permissive_0666(self, temp_cert_file):
        """Test rejection of certificate with 0666 permissions."""
        with open(temp_cert_file, "w") as f:
            f.write(VALID_CERT_PEM)
        os.chmod(temp_cert_file, 0o666)  # noqa: S103 - intentionally testing rejection of permissive perms

        result = validate_certificate(temp_cert_file)

        assert not result.valid
        assert result.permissions == 0o666
        assert len(result.errors) > 0
        assert any("permission" in err.lower() for err in result.errors)

    def test_validate_cert_too_permissive_0644(self, temp_cert_file):
        """Test rejection of certificate with 0644 permissions."""
        with open(temp_cert_file, "w") as f:
            f.write(VALID_CERT_PEM)
        os.chmod(temp_cert_file, 0o644)

        result = validate_certificate(temp_cert_file)

        assert not result.valid
        assert any("permission" in err.lower() for err in result.errors)

    def test_validate_invalid_cert_format(self, invalid_cert_0600):
        """Test validation fails for invalid certificate format."""
        result = validate_certificate(invalid_cert_0600)

        assert not result.valid
        assert len(result.errors) > 0
        assert any(
            "format" in err.lower() or "invalid" in err.lower() or "parse" in err.lower()
            for err in result.errors
        )

    def test_validate_expired_cert(self, expired_cert_0600):
        """Test validation of expired certificate."""
        result = validate_certificate(expired_cert_0600)

        # Should parse successfully but have warnings about expiration
        assert result.valid  # Certificate itself is valid, just expired
        assert result.expiration_date is not None
        assert result.days_until_expiry is not None
        assert result.days_until_expiry < 0  # Negative means expired
        assert len(result.warnings) > 0
        assert any("expired" in warn.lower() for warn in result.warnings)

    def test_validate_cert_empty_file(self, temp_cert_file):
        """Test validation fails for empty certificate file."""
        # Create empty file
        with open(temp_cert_file, "w") as f:
            f.write("")
        os.chmod(temp_cert_file, 0o600)

        result = validate_certificate(temp_cert_file)

        assert not result.valid
        assert len(result.errors) > 0

    def test_cert_validation_dataclass_structure(self, valid_cert_0600):
        """Test that CertValidation has expected structure."""
        result = validate_certificate(valid_cert_0600)

        # Check all required fields exist
        assert hasattr(result, "valid")
        assert hasattr(result, "cert_path")
        assert hasattr(result, "permissions")
        assert hasattr(result, "expiration_date")
        assert hasattr(result, "days_until_expiry")
        assert hasattr(result, "errors")
        assert hasattr(result, "warnings")

        # Check types
        assert isinstance(result.valid, bool)
        assert isinstance(result.cert_path, str)
        assert isinstance(result.permissions, int)
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)


class TestCheckExpiration:
    """Test certificate expiration checking functionality."""

    def test_check_expiration_valid_cert(self, valid_cert_0600):
        """Test checking expiration on a valid certificate."""
        result = check_expiration(valid_cert_0600)

        assert result.cert_path == valid_cert_0600
        assert result.expiration_date is not None
        assert result.days_until_expiry is not None
        assert result.days_until_expiry > 0  # Not expired
        assert not result.is_expired

    def test_check_expiration_expired_cert(self, expired_cert_0600):
        """Test checking expiration on an expired certificate."""
        result = check_expiration(expired_cert_0600)

        assert result.expiration_date is not None
        assert result.days_until_expiry is not None
        assert result.days_until_expiry < 0  # Expired
        assert result.is_expired

    def test_check_expiration_warning_threshold(self, expired_cert_0600):
        """Test warning when certificate expires soon (within 30 days)."""
        # We need to create a cert that expires soon
        # For testing purposes, we'll check the logic with the expired cert
        # since we can't easily create a cert expiring in exactly 29 days
        result = check_expiration(expired_cert_0600)

        # Should have warning flag for expiration
        assert hasattr(result, "needs_warning")
        assert result.needs_warning  # Expired cert definitely needs warning

    def test_check_expiration_nonexistent_file(self):
        """Test checking expiration on non-existent file."""
        with pytest.raises(FileNotFoundError):
            check_expiration("/nonexistent/cert.pem")

    def test_check_expiration_invalid_cert(self, invalid_cert_0600):
        """Test checking expiration on invalid certificate."""
        with pytest.raises((ValueError, Exception)):
            check_expiration(invalid_cert_0600)

    def test_expiration_status_dataclass_structure(self, valid_cert_0600):
        """Test that ExpirationStatus has expected structure."""
        result = check_expiration(valid_cert_0600)

        # Check all required fields exist
        assert hasattr(result, "cert_path")
        assert hasattr(result, "expiration_date")
        assert hasattr(result, "days_until_expiry")
        assert hasattr(result, "is_expired")
        assert hasattr(result, "needs_warning")

        # Check types
        assert isinstance(result.cert_path, str)
        assert isinstance(result.is_expired, bool)
        assert isinstance(result.needs_warning, bool)


class TestFixCertificatePermissions:
    """Test certificate permissions fixing functionality."""

    def test_fix_permissions_already_correct_0600(self, valid_cert_0600):
        """Test fixing permissions when already 0600 (no change needed)."""
        result = fix_certificate_permissions(valid_cert_0600)

        assert not result  # False because no change was needed

        # Verify permissions unchanged
        perms = stat.S_IMODE(os.stat(valid_cert_0600).st_mode)
        assert perms == 0o600

    def test_fix_permissions_already_correct_0400(self, valid_cert_0400):
        """Test fixing permissions when already 0400 (no change needed)."""
        result = fix_certificate_permissions(valid_cert_0400)

        assert not result  # False because no change was needed

        # Verify permissions unchanged
        perms = stat.S_IMODE(os.stat(valid_cert_0400).st_mode)
        assert perms == 0o400

    def test_fix_permissions_too_permissive(self, cert_wrong_perms):
        """Test fixing overly permissive permissions."""
        # Verify initial state
        perms = stat.S_IMODE(os.stat(cert_wrong_perms).st_mode)
        assert perms == 0o644

        result = fix_certificate_permissions(cert_wrong_perms)

        assert result  # True because permissions were fixed

        # Verify permissions now 0600
        new_perms = stat.S_IMODE(os.stat(cert_wrong_perms).st_mode)
        assert new_perms == 0o600

    def test_fix_permissions_world_readable(self, temp_cert_file):
        """Test fixing world-readable permissions."""
        with open(temp_cert_file, "w") as f:
            f.write(VALID_CERT_PEM)
        os.chmod(temp_cert_file, 0o644)

        result = fix_certificate_permissions(temp_cert_file)

        assert result  # Permissions were fixed

        new_perms = stat.S_IMODE(os.stat(temp_cert_file).st_mode)
        assert new_perms == 0o600

    def test_fix_permissions_nonexistent_file(self):
        """Test fixing permissions on non-existent file."""
        with pytest.raises(FileNotFoundError):
            fix_certificate_permissions("/nonexistent/cert.pem")

    def test_fix_permissions_preserves_0400(self, valid_cert_0400):
        """Test that 0400 permissions are not changed to 0600."""
        original_perms = stat.S_IMODE(os.stat(valid_cert_0400).st_mode)
        assert original_perms == 0o400

        result = fix_certificate_permissions(valid_cert_0400)

        assert not result  # No change needed

        # Verify 0400 preserved (not changed to 0600)
        new_perms = stat.S_IMODE(os.stat(valid_cert_0400).st_mode)
        assert new_perms == 0o400


class TestIntegrationScenarios:
    """Integration tests for real-world scenarios."""

    def test_full_validation_workflow_valid_cert(self, valid_cert_0600):
        """Test complete workflow with a valid certificate."""
        # Step 1: Validate
        validation = validate_certificate(valid_cert_0600)
        assert validation.valid

        # Step 2: Check expiration
        expiration = check_expiration(valid_cert_0600)
        assert not expiration.is_expired

        # Step 3: Try to fix permissions (should be no-op)
        fixed = fix_certificate_permissions(valid_cert_0600)
        assert not fixed  # No change needed

    def test_full_validation_workflow_needs_fixing(self, cert_wrong_perms):
        """Test complete workflow with certificate needing permission fix."""
        # Step 1: Validate (should fail)
        validation = validate_certificate(cert_wrong_perms)
        assert not validation.valid
        assert any("permission" in err.lower() for err in validation.errors)

        # Step 2: Fix permissions
        fixed = fix_certificate_permissions(cert_wrong_perms)
        assert fixed

        # Step 3: Re-validate (should pass now)
        validation2 = validate_certificate(cert_wrong_perms)
        assert validation2.valid

    def test_multiple_validation_checks(self, valid_cert_0600):
        """Test that validation can be called multiple times safely."""
        result1 = validate_certificate(valid_cert_0600)
        result2 = validate_certificate(valid_cert_0600)

        assert result1.valid == result2.valid
        assert result1.permissions == result2.permissions
        assert result1.cert_path == result2.cert_path


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_unreadable_file(self, temp_cert_file):
        """Test validation of unreadable certificate file."""
        with open(temp_cert_file, "w") as f:
            f.write(VALID_CERT_PEM)
        os.chmod(temp_cert_file, 0o000)  # No permissions at all

        result = validate_certificate(temp_cert_file)

        # Should fail validation
        assert not result.valid
        # Cleanup
        os.chmod(temp_cert_file, 0o600)

    def test_certificate_expiring_soon(self, temp_cert_file):
        """Test warning for certificate expiring within 30 days."""
        # Create a certificate expiring in 15 days
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, "test.example.com"),
            ]
        )

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(UTC) - timedelta(days=1))
            .not_valid_after(datetime.now(UTC) + timedelta(days=15))
            .sign(private_key, hashes.SHA256())
        )

        cert_pem = cert.public_bytes(serialization.Encoding.PEM)

        with open(temp_cert_file, "wb") as f:
            f.write(cert_pem)
        os.chmod(temp_cert_file, 0o600)

        result = validate_certificate(temp_cert_file)

        # Should be valid but with warning
        assert result.valid
        assert len(result.warnings) > 0
        assert any("expires soon" in warn.lower() for warn in result.warnings)
        assert result.days_until_expiry is not None
        assert 0 < result.days_until_expiry < 30


class TestSecurityRequirements:
    """Test P0 security requirements."""

    def test_reject_group_readable_0640(self, temp_cert_file):
        """Test rejection of group-readable certificate."""
        with open(temp_cert_file, "w") as f:
            f.write(VALID_CERT_PEM)
        os.chmod(temp_cert_file, 0o640)

        result = validate_certificate(temp_cert_file)

        assert not result.valid
        assert any("permission" in err.lower() for err in result.errors)

    def test_reject_world_readable_0644(self, temp_cert_file):
        """Test rejection of world-readable certificate."""
        with open(temp_cert_file, "w") as f:
            f.write(VALID_CERT_PEM)
        os.chmod(temp_cert_file, 0o644)

        result = validate_certificate(temp_cert_file)

        assert not result.valid
        assert any("permission" in err.lower() for err in result.errors)

    def test_reject_world_writable_0666(self, temp_cert_file):
        """Test rejection of world-writable certificate."""
        with open(temp_cert_file, "w") as f:
            f.write(VALID_CERT_PEM)
        os.chmod(temp_cert_file, 0o666)  # noqa: S103 - intentionally testing rejection of permissive perms

        result = validate_certificate(temp_cert_file)

        assert not result.valid
        assert any("permission" in err.lower() for err in result.errors)

    def test_only_0600_or_0400_allowed(self, temp_cert_file):
        """Test that ONLY 0600 and 0400 permissions are accepted."""
        # Test various permission combinations
        invalid_perms = [0o644, 0o640, 0o666, 0o777, 0o700, 0o440, 0o444]

        for perm in invalid_perms:
            # Ensure file is writable first
            os.chmod(temp_cert_file, 0o600)
            with open(temp_cert_file, "w") as f:
                f.write(VALID_CERT_PEM)
            os.chmod(temp_cert_file, perm)

            result = validate_certificate(temp_cert_file)
            assert not result.valid, f"Permission {oct(perm)} should be rejected"
            assert any("permission" in err.lower() for err in result.errors)

    def test_pem_format_validation(self, temp_cert_file):
        """Test that PEM format is strictly validated."""
        invalid_formats = [
            "random text",
            "-----BEGIN CERTIFICATE-----\ninvalid\n-----END CERTIFICATE-----",
            "",
            "BEGIN CERTIFICATE\nno proper markers\nEND CERTIFICATE",
        ]

        for invalid_content in invalid_formats:
            with open(temp_cert_file, "w") as f:
                f.write(invalid_content)
            os.chmod(temp_cert_file, 0o600)

            result = validate_certificate(temp_cert_file)
            assert not result.valid, f"Invalid format should be rejected: {invalid_content[:50]}"

    def test_fail_fast_on_invalid_cert(self, invalid_cert_0600):
        """Test that validation fails fast on invalid certificate."""
        result = validate_certificate(invalid_cert_0600)

        # Should fail immediately, not crash
        assert not result.valid
        assert len(result.errors) > 0
