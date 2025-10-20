"""IP address validation tests for file transfer."""

import pytest

from azlin.modules.file_transfer import FileTransfer, TransferError


class TestIPAddressValidation:
    """Test IP address validation using standards-based ipaddress module."""

    def test_accepts_valid_ipv4(self):
        """Should accept valid IPv4 addresses."""
        # Should not raise
        FileTransfer.validate_ip_address("192.168.1.1")
        FileTransfer.validate_ip_address("10.0.0.1")
        FileTransfer.validate_ip_address("172.16.0.1")
        FileTransfer.validate_ip_address("8.8.8.8")

    def test_accepts_valid_ipv6(self):
        """Should accept valid IPv6 addresses."""
        FileTransfer.validate_ip_address("2001:0db8:85a3::8a2e:0370:7334")
        FileTransfer.validate_ip_address("::1")
        FileTransfer.validate_ip_address("fe80::1")

    def test_rejects_invalid_format(self):
        """Should reject malformed IP addresses."""
        with pytest.raises(TransferError, match="Invalid IP"):
            FileTransfer.validate_ip_address("999.999.999.999")

    def test_rejects_empty_ip(self):
        """Should reject empty IP address."""
        with pytest.raises(TransferError):
            FileTransfer.validate_ip_address("")

    def test_rejects_hostname(self):
        """Should reject hostnames (not IP addresses)."""
        with pytest.raises(TransferError):
            FileTransfer.validate_ip_address("example.com")

    def test_rejects_leading_zeros(self):
        """Should reject IPs with leading zeros (octal ambiguity)."""
        with pytest.raises(TransferError):
            FileTransfer.validate_ip_address("192.168.001.001")

    def test_rejects_too_many_octets(self):
        """Should reject IPs with too many octets."""
        with pytest.raises(TransferError):
            FileTransfer.validate_ip_address("192.168.1.1.1")

    def test_rejects_too_few_octets(self):
        """Should reject IPs with too few octets."""
        with pytest.raises(TransferError):
            FileTransfer.validate_ip_address("192.168.1")

    def test_rejects_non_numeric(self):
        """Should reject IPs with non-numeric characters."""
        with pytest.raises(TransferError):
            FileTransfer.validate_ip_address("192.168.1.x")

    def test_rejects_special_characters(self):
        """Should reject IPs with special characters."""
        with pytest.raises(TransferError):
            FileTransfer.validate_ip_address("192.168.1.1; rm -rf /")

    def test_rejects_whitespace(self):
        """Should reject IPs with embedded whitespace."""
        with pytest.raises(TransferError):
            FileTransfer.validate_ip_address("192.168.1. 1")

    def test_rejects_url_format(self):
        """Should reject URL-like formats."""
        with pytest.raises(TransferError):
            FileTransfer.validate_ip_address("http://192.168.1.1")


class TestIPValidationIntegration:
    """Test IP validation in rsync command building."""

    def test_validates_ip_when_building_command(self):
        """Should validate IP address when building rsync command."""
        from pathlib import Path

        from azlin.modules.file_transfer import TransferEndpoint, VMSession

        # Create endpoints with invalid IP
        session = VMSession(
            name="test",
            public_ip="invalid_ip",  # Invalid
            user="testuser",
            key_path="/tmp/key",  # noqa: S108 - test file path
            resource_group="test-rg",
        )

        source = TransferEndpoint(Path("/tmp/source"), session=None)  # noqa: S108 - test path
        dest = TransferEndpoint(Path("/tmp/dest"), session=session)  # noqa: S108 - test path

        # Should raise TransferError when building command
        with pytest.raises(TransferError, match="Invalid IP"):
            FileTransfer.build_rsync_command(source, dest)
