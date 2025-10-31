"""Tests for security_audit module.

These tests verify the SecurityAuditLogger functionality including:
- Audit log creation with proper structure
- Secure file permissions (0600)
- Proper logging of bastion opt-out events
- Handling of missing or corrupted audit files
"""

import json
import os
import stat

import pytest

from azlin.security_audit import SecurityAuditLogger


class TestSecurityAuditLogger:
    """Test SecurityAuditLogger functionality."""

    @pytest.fixture
    def audit_file_path(self, tmp_path, monkeypatch):
        """Create temporary audit file path for testing."""
        audit_dir = tmp_path / ".azlin"
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_file = audit_dir / "security_audit.json"

        # Monkeypatch the AUDIT_FILE class attribute
        monkeypatch.setattr(SecurityAuditLogger, "AUDIT_FILE", audit_file)

        yield audit_file

        # Cleanup
        if audit_file.exists():
            audit_file.unlink()

    def test_log_bastion_opt_out_creates_file(self, audit_file_path):
        """Test that logging creates audit file if it doesn't exist."""
        assert not audit_file_path.exists()

        SecurityAuditLogger.log_bastion_opt_out(
            vm_name="test-vm",
            method="flag",
            user="testuser"
        )

        assert audit_file_path.exists()

    def test_log_bastion_opt_out_correct_structure(self, audit_file_path):
        """Test that audit entry has correct structure."""
        SecurityAuditLogger.log_bastion_opt_out(
            vm_name="test-vm",
            method="flag",
            user="testuser"
        )

        with open(audit_file_path) as f:
            audit_log = json.load(f)

        assert len(audit_log) == 1
        entry = audit_log[0]

        # Verify all required fields exist
        assert "timestamp" in entry
        assert "user" in entry
        assert "vm_name" in entry
        assert "method" in entry
        assert "security_impact" in entry

        # Verify field values
        assert entry["user"] == "testuser"
        assert entry["vm_name"] == "test-vm"
        assert entry["method"] == "flag"
        assert entry["security_impact"] == "VM will have public IP exposed to internet"
        assert entry["timestamp"].endswith("Z")  # UTC timestamp

    def test_log_bastion_opt_out_default_user(self, audit_file_path):
        """Test that default user is derived from environment."""
        SecurityAuditLogger.log_bastion_opt_out(
            vm_name="test-vm",
            method="flag",
            user=None  # Should use system user
        )

        with open(audit_file_path) as f:
            audit_log = json.load(f)

        entry = audit_log[0]
        # User should be set from environment or 'unknown'
        assert entry["user"] in [
            os.getenv("USER"),
            os.getenv("USERNAME"),
            "unknown"
        ]

    def test_log_bastion_opt_out_secure_permissions(self, audit_file_path):
        """Test that audit file has secure permissions (0600)."""
        SecurityAuditLogger.log_bastion_opt_out(
            vm_name="test-vm",
            method="flag",
            user="testuser"
        )

        # Get file permissions
        file_stat = os.stat(audit_file_path)
        file_mode = stat.filemode(file_stat.st_mode)

        # Should be -rw------- (0600)
        assert file_stat.st_mode & 0o777 == 0o600

    def test_log_bastion_opt_out_append_entries(self, audit_file_path):
        """Test that multiple logs are appended correctly."""
        # Log first entry
        SecurityAuditLogger.log_bastion_opt_out(
            vm_name="vm-1",
            method="flag",
            user="user1"
        )

        # Log second entry
        SecurityAuditLogger.log_bastion_opt_out(
            vm_name="vm-2",
            method="prompt_existing",
            user="user2"
        )

        # Log third entry
        SecurityAuditLogger.log_bastion_opt_out(
            vm_name="vm-3",
            method="prompt_create",
            user="user3"
        )

        with open(audit_file_path) as f:
            audit_log = json.load(f)

        assert len(audit_log) == 3
        assert audit_log[0]["vm_name"] == "vm-1"
        assert audit_log[0]["method"] == "flag"
        assert audit_log[1]["vm_name"] == "vm-2"
        assert audit_log[1]["method"] == "prompt_existing"
        assert audit_log[2]["vm_name"] == "vm-3"
        assert audit_log[2]["method"] == "prompt_create"

    def test_log_bastion_opt_out_valid_methods(self, audit_file_path):
        """Test all valid opt-out methods."""
        methods = ["flag", "prompt_existing", "prompt_create"]

        for i, method in enumerate(methods):
            SecurityAuditLogger.log_bastion_opt_out(
                vm_name=f"vm-{i}",
                method=method,
                user="testuser"
            )

        with open(audit_file_path) as f:
            audit_log = json.load(f)

        assert len(audit_log) == len(methods)
        for i, method in enumerate(methods):
            assert audit_log[i]["method"] == method

    def test_log_bastion_opt_out_handles_corrupted_file(self, audit_file_path):
        """Test that corrupted audit file is replaced with fresh log."""
        # Create corrupted audit file
        audit_file_path.write_text("not valid json {{{")

        # Should not raise exception, should start fresh
        SecurityAuditLogger.log_bastion_opt_out(
            vm_name="test-vm",
            method="flag",
            user="testuser"
        )

        with open(audit_file_path) as f:
            audit_log = json.load(f)

        # Should have only one entry (fresh start)
        assert len(audit_log) == 1
        assert audit_log[0]["vm_name"] == "test-vm"

    def test_get_audit_log_empty(self, audit_file_path):
        """Test get_audit_log returns empty list when no file exists."""
        assert not audit_file_path.exists()
        audit_log = SecurityAuditLogger.get_audit_log()
        assert audit_log == []

    def test_get_audit_log_with_entries(self, audit_file_path):
        """Test get_audit_log retrieves all entries."""
        # Add entries
        SecurityAuditLogger.log_bastion_opt_out(
            vm_name="vm-1",
            method="flag",
            user="user1"
        )
        SecurityAuditLogger.log_bastion_opt_out(
            vm_name="vm-2",
            method="prompt_existing",
            user="user2"
        )

        # Retrieve entries
        audit_log = SecurityAuditLogger.get_audit_log()

        assert len(audit_log) == 2
        assert audit_log[0]["vm_name"] == "vm-1"
        assert audit_log[1]["vm_name"] == "vm-2"

    def test_get_audit_log_handles_corrupted_file(self, audit_file_path):
        """Test get_audit_log returns empty list for corrupted file."""
        # Create corrupted file
        audit_file_path.write_text("not valid json {{{")

        audit_log = SecurityAuditLogger.get_audit_log()
        assert audit_log == []

    def test_audit_directory_creation(self, tmp_path, monkeypatch):
        """Test that audit directory is created if it doesn't exist."""
        audit_dir = tmp_path / "new_azlin_dir"
        audit_file = audit_dir / "security_audit.json"

        # Monkeypatch to non-existent directory
        monkeypatch.setattr(SecurityAuditLogger, "AUDIT_FILE", audit_file)

        assert not audit_dir.exists()

        SecurityAuditLogger.log_bastion_opt_out(
            vm_name="test-vm",
            method="flag",
            user="testuser"
        )

        assert audit_dir.exists()
        assert audit_file.exists()

        # Cleanup
        audit_file.unlink()
        audit_dir.rmdir()


class TestSecurityAuditLoggerIntegration:
    """Integration tests for SecurityAuditLogger in realistic scenarios."""

    @pytest.fixture
    def audit_file_path(self, tmp_path, monkeypatch):
        """Create temporary audit file path for testing."""
        audit_dir = tmp_path / ".azlin"
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_file = audit_dir / "security_audit.json"

        monkeypatch.setattr(SecurityAuditLogger, "AUDIT_FILE", audit_file)

        yield audit_file

        # Cleanup
        if audit_file.exists():
            audit_file.unlink()

    def test_multiple_users_logging(self, audit_file_path):
        """Test multiple users logging opt-out decisions."""
        users = ["alice", "bob", "charlie"]

        for user in users:
            SecurityAuditLogger.log_bastion_opt_out(
                vm_name=f"{user}-vm",
                method="flag",
                user=user
            )

        audit_log = SecurityAuditLogger.get_audit_log()
        assert len(audit_log) == 3

        for i, user in enumerate(users):
            assert audit_log[i]["user"] == user
            assert audit_log[i]["vm_name"] == f"{user}-vm"

    def test_audit_trail_chronological(self, audit_file_path):
        """Test that audit entries maintain chronological order."""
        import time

        for i in range(3):
            SecurityAuditLogger.log_bastion_opt_out(
                vm_name=f"vm-{i}",
                method="flag",
                user="testuser"
            )
            time.sleep(0.1)  # Small delay to ensure different timestamps

        audit_log = SecurityAuditLogger.get_audit_log()

        # Verify entries are in chronological order
        timestamps = [entry["timestamp"] for entry in audit_log]
        assert timestamps == sorted(timestamps)
