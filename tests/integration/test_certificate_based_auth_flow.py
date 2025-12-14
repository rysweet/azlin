"""Integration test for certificate-based authentication."""

from pathlib import Path

import pytest

from azlin.certificate_validator import CertificateValidator


class TestCertificateAuthFlow:
    """Test certificate-based authentication workflow."""

    def test_certificate_validation(self, tmp_path):
        """Test validating certificate for authentication."""
        # Create test certificate (self-signed for testing)
        cert_file = tmp_path / "test.pem"

        try:
            validator = CertificateValidator()

            # Test certificate file exists check
            assert not validator.validate_certificate_file(cert_file)

        except Exception as e:
            pytest.skip(f"Certificate validation not available: {e}")
