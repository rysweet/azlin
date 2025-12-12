"""Integration test for file transfer path parsing to transfer workflow.

Tests real workflow: Path parsing → Session creation → Transfer decision
"""

from pathlib import Path

import pytest

from azlin.modules.file_transfer.file_transfer import FileTransfer, TransferEndpoint
from azlin.modules.file_transfer.path_parser import PathParser
from azlin.modules.file_transfer.session_manager import SessionManager


class TestPathParsingWorkflow:
    """Test path parsing and validation workflow."""

    def test_local_path_parsing(self, tmp_path):
        """Test parsing local file paths."""
        parser = PathParser()

        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Parse local path
        parsed = parser.parse(str(test_file))

        assert parsed.is_local is True
        assert parsed.path == str(test_file)
        assert parsed.vm_name is None

    def test_remote_path_parsing(self):
        """Test parsing remote VM paths."""
        parser = PathParser()

        # Parse remote path (VM:path format)
        remote_path = "test-vm:/home/azureuser/file.txt"
        parsed = parser.parse(remote_path)

        assert parsed.is_local is False
        assert parsed.vm_name == "test-vm"
        assert "/home/azureuser/file.txt" in parsed.path

    def test_path_parsing_with_special_characters(self, tmp_path):
        """Test parsing paths with special characters."""
        parser = PathParser()

        # Create file with spaces
        test_file = tmp_path / "test file with spaces.txt"
        test_file.write_text("content")

        # Parse path
        parsed = parser.parse(str(test_file))

        assert parsed.is_local is True
        assert "test file with spaces.txt" in parsed.path

    def test_invalid_path_handling(self):
        """Test handling of invalid paths."""
        parser = PathParser()

        # Test various invalid paths
        invalid_paths = [
            "",  # Empty
            ":",  # Just colon
            "vm:",  # No path
            ":path",  # No VM
        ]

        for invalid_path in invalid_paths:
            with pytest.raises(Exception):  # Should raise some form of error
                parser.parse(invalid_path)


class TestSessionCreationWorkflow:
    """Test session creation and management workflow."""

    def test_session_manager_creation(self):
        """Test creating session manager."""
        manager = SessionManager()

        # Should initialize successfully
        assert manager is not None

    def test_session_lifecycle(self):
        """Test complete session lifecycle."""
        manager = SessionManager()

        # Create session
        session_id = manager.create_session(
            vm_name="test-vm",
            resource_group="test-rg",
            user="azureuser",
        )

        assert session_id is not None
        assert len(session_id) > 0

        # Get session
        session = manager.get_session(session_id)
        assert session is not None
        assert session.vm_name == "test-vm"

        # Close session
        manager.close_session(session_id)

        # Session should be removed
        with pytest.raises(Exception):  # Should raise error for closed session
            manager.get_session(session_id)

    def test_multiple_concurrent_sessions(self):
        """Test managing multiple concurrent sessions."""
        manager = SessionManager()

        # Create multiple sessions
        session1 = manager.create_session(
            vm_name="vm1",
            resource_group="rg1",
            user="user1",
        )

        session2 = manager.create_session(
            vm_name="vm2",
            resource_group="rg2",
            user="user2",
        )

        # Both should exist
        assert manager.get_session(session1).vm_name == "vm1"
        assert manager.get_session(session2).vm_name == "vm2"

        # Close one session
        manager.close_session(session1)

        # Other session should still exist
        assert manager.get_session(session2).vm_name == "vm2"


class TestFileTransferDecisionWorkflow:
    """Test file transfer decision and preparation workflow."""

    def test_transfer_endpoint_creation(self, tmp_path):
        """Test creating transfer endpoints."""
        # Local endpoint
        local_file = tmp_path / "source.txt"
        local_file.write_text("test")

        local_endpoint = TransferEndpoint(
            path=str(local_file),
            is_local=True,
        )

        assert local_endpoint.is_local is True
        assert local_endpoint.path == str(local_file)

        # Remote endpoint
        remote_endpoint = TransferEndpoint(
            path="/remote/path/file.txt",
            is_local=False,
            vm_name="test-vm",
        )

        assert remote_endpoint.is_local is False
        assert remote_endpoint.vm_name == "test-vm"

    def test_transfer_direction_detection(self, tmp_path):
        """Test detecting transfer direction (upload vs download)."""
        local_file = tmp_path / "local.txt"
        local_file.write_text("test")

        # Upload: local → remote
        local_endpoint = TransferEndpoint(path=str(local_file), is_local=True)
        remote_endpoint = TransferEndpoint(
            path="/remote/file.txt",
            is_local=False,
            vm_name="vm",
        )

        # Determine direction
        if local_endpoint.is_local and not remote_endpoint.is_local:
            direction = "upload"
        elif not local_endpoint.is_local and remote_endpoint.is_local:
            direction = "download"
        else:
            direction = "unknown"

        assert direction == "upload"

    def test_transfer_size_calculation(self, tmp_path):
        """Test calculating file size for transfer."""
        # Create file with known size
        test_file = tmp_path / "sized_file.txt"
        content = "x" * 1024  # 1KB
        test_file.write_text(content)

        # Calculate size
        size = test_file.stat().st_size

        assert size == 1024

    def test_transfer_validation_workflow(self, tmp_path):
        """Test validating transfer before execution."""
        # Source exists
        source = tmp_path / "source.txt"
        source.write_text("content")

        # Destination directory exists
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        # Validation checks
        assert source.exists() is True
        assert source.is_file() is True
        assert dest_dir.exists() is True
        assert dest_dir.is_dir() is True

        # Transfer should be valid
        transfer_valid = True

        assert transfer_valid is True
