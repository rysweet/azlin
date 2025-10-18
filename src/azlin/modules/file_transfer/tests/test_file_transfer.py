"""Unit tests for file_transfer module."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from azlin.modules.file_transfer import (
    FileTransfer,
    InvalidTransferError,
    TransferEndpoint,
    TransferError,
    VMSession,
)


class TestTransferEndpoint:
    """Test TransferEndpoint class."""

    def test_local_endpoint_to_rsync_arg(self):
        """Should convert local endpoint to rsync argument"""
        endpoint = TransferEndpoint(path=Path("/home/user/test.txt"), session=None)
        assert endpoint.to_rsync_arg() == "/home/user/test.txt"

    def test_remote_endpoint_to_rsync_arg(self):
        """Should convert remote endpoint to rsync argument"""
        session = VMSession(
            name="test-vm",
            public_ip="1.2.3.4",
            user="azureuser",
            key_path="/home/user/.ssh/key",
            resource_group="test-rg",
        )
        endpoint = TransferEndpoint(path=Path("/home/azureuser/test.txt"), session=session)
        assert endpoint.to_rsync_arg() == "azureuser@1.2.3.4:/home/azureuser/test.txt"


class TestTransferValidation:
    """Test transfer validation."""

    def test_rejects_both_local_endpoints(self):
        """Should reject when both endpoints are local"""
        source = TransferEndpoint(path=Path("/home/user/test.txt"), session=None)
        dest = TransferEndpoint(path=Path("/home/user/dest.txt"), session=None)

        with pytest.raises(InvalidTransferError, match="Both source and destination are local"):
            FileTransfer.transfer(source, dest)


class TestIPAddressValidation:
    """Test IP address validation."""

    def test_accepts_valid_ipv4(self):
        """Should accept valid IPv4 addresses"""
        FileTransfer.validate_ip_address("192.168.1.1")
        FileTransfer.validate_ip_address("10.0.0.1")

    def test_accepts_valid_ipv6(self):
        """Should accept valid IPv6 addresses"""
        FileTransfer.validate_ip_address("::1")
        FileTransfer.validate_ip_address("2001:0db8:85a3:0000:0000:8a2e:0370:7334")

    def test_rejects_invalid_ip(self):
        """Should reject invalid IP addresses"""
        with pytest.raises(TransferError, match="Invalid IP address"):
            FileTransfer.validate_ip_address("not-an-ip")

        with pytest.raises(TransferError, match="Invalid IP address"):
            FileTransfer.validate_ip_address("999.999.999.999")


class TestRsyncCommandConstruction:
    """Test rsync command construction."""

    def test_builds_local_to_remote_command(self):
        """Should build correct command for local to remote transfer"""
        source = TransferEndpoint(path=Path("/home/user/test.txt"), session=None)

        session = VMSession(
            name="test-vm",
            public_ip="1.2.3.4",
            user="azureuser",
            key_path="/home/user/.ssh/key",
            resource_group="test-rg",
        )
        dest = TransferEndpoint(path=Path("/home/azureuser/test.txt"), session=session)

        cmd = FileTransfer.build_rsync_command(source, dest)

        assert cmd[0] == "rsync"
        assert "-avz" in cmd
        assert "--progress" in cmd
        assert "-e" in cmd
        # Verify SSH command is a single argument
        ssh_idx = cmd.index("-e")
        assert "ssh" in cmd[ssh_idx + 1]
        assert "/home/user/.ssh/key" in cmd[ssh_idx + 1]
        # Verify source and dest
        assert "/home/user/test.txt" in cmd
        assert "azureuser@1.2.3.4:/home/azureuser/test.txt" in cmd

    def test_builds_remote_to_local_command(self):
        """Should build correct command for remote to local transfer"""
        session = VMSession(
            name="test-vm",
            public_ip="1.2.3.4",
            user="azureuser",
            key_path="/home/user/.ssh/key",
            resource_group="test-rg",
        )
        source = TransferEndpoint(path=Path("/home/azureuser/test.txt"), session=session)
        dest = TransferEndpoint(path=Path("/home/user/test.txt"), session=None)

        cmd = FileTransfer.build_rsync_command(source, dest)

        assert "azureuser@1.2.3.4:/home/azureuser/test.txt" in cmd
        assert "/home/user/test.txt" in cmd

    def test_uses_argument_array_not_shell(self):
        """Should use argument array (no shell=True)"""
        source = TransferEndpoint(path=Path("/home/user/test.txt"), session=None)

        session = VMSession(
            name="test-vm",
            public_ip="1.2.3.4",
            user="azureuser",
            key_path="/home/user/.ssh/key",
            resource_group="test-rg",
        )
        dest = TransferEndpoint(path=Path("/home/azureuser/test.txt"), session=session)

        cmd = FileTransfer.build_rsync_command(source, dest)

        # Command should be a list
        assert isinstance(cmd, list)
        # All elements should be strings
        assert all(isinstance(arg, str) for arg in cmd)


class TestRsyncOutputParsing:
    """Test rsync output parsing."""

    def test_parses_basic_output(self):
        """Should parse basic rsync output"""
        output = """sending incremental file list
test.txt

sent 1,234 bytes  received 56 bytes  1,290.00 bytes/sec
total size is 1,000  speedup is 0.78
"""
        stats = FileTransfer.parse_rsync_output(output)
        assert stats["bytes"] == 1234
        assert stats["files"] > 0

    def test_handles_empty_output(self):
        """Should handle empty output gracefully"""
        stats = FileTransfer.parse_rsync_output("")
        assert stats["bytes"] == 0
        assert stats["files"] == 0

    def test_handles_output_without_bytes(self):
        """Should handle output without byte count"""
        output = """sending incremental file list
test.txt
"""
        stats = FileTransfer.parse_rsync_output(output)
        assert stats["files"] > 0


class TestTransferExecution:
    """Test transfer execution."""

    @patch("subprocess.run")
    def test_successful_transfer(self, mock_run: Mock):
        """Should execute transfer successfully"""
        # Mock subprocess.run
        mock_result = Mock()
        mock_result.stdout = "sent 1,234 bytes  received 56 bytes"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        source = TransferEndpoint(path=Path("/home/user/test.txt"), session=None)

        session = VMSession(
            name="test-vm",
            public_ip="1.2.3.4",
            user="azureuser",
            key_path="/home/user/.ssh/key",
            resource_group="test-rg",
        )
        dest = TransferEndpoint(path=Path("/home/azureuser/test.txt"), session=session)

        result = FileTransfer.transfer(source, dest)

        assert result.success is True
        assert result.duration_seconds > 0
        # Verify subprocess.run was called with correct parameters
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        # Verify shell=True is NOT used (check it's not in kwargs or is False)
        assert call_args.kwargs.get("shell", False) is False

    @patch("subprocess.run")
    def test_failed_transfer(self, mock_run: Mock):
        """Should handle failed transfers"""
        # Mock subprocess.run to raise CalledProcessError
        from subprocess import CalledProcessError

        mock_run.side_effect = CalledProcessError(
            returncode=1, cmd=["rsync"], stderr="Connection failed"
        )

        source = TransferEndpoint(path=Path("/home/user/test.txt"), session=None)

        session = VMSession(
            name="test-vm",
            public_ip="1.2.3.4",
            user="azureuser",
            key_path="/home/user/.ssh/key",
            resource_group="test-rg",
        )
        dest = TransferEndpoint(path=Path("/home/azureuser/test.txt"), session=session)

        result = FileTransfer.transfer(source, dest)

        assert result.success is False
        assert len(result.errors) > 0
        assert "rsync failed" in result.errors[0]

    @patch("subprocess.run")
    def test_timeout_handling(self, mock_run: Mock):
        """Should handle transfer timeouts"""
        from subprocess import TimeoutExpired

        mock_run.side_effect = TimeoutExpired(cmd=["rsync"], timeout=300)

        source = TransferEndpoint(path=Path("/home/user/test.txt"), session=None)

        session = VMSession(
            name="test-vm",
            public_ip="1.2.3.4",
            user="azureuser",
            key_path="/home/user/.ssh/key",
            resource_group="test-rg",
        )
        dest = TransferEndpoint(path=Path("/home/azureuser/test.txt"), session=session)

        with pytest.raises(TransferError, match="timed out"):
            FileTransfer.transfer(source, dest)
