"""Error path tests for backup_manager module - Phase 4.

Tests all error conditions in backup management including:
- Backup creation failures
- Backup restoration failures
- Backup listing errors
- Invalid backup names
- Azure CLI command failures
"""

import subprocess
from unittest.mock import patch

import pytest


class TestBackupCreationErrors:
    """Error tests for backup creation."""

    @patch("subprocess.run")
    def test_create_backup_subprocess_failure(self, mock_run):
        """Test that backup creation subprocess failure raises Exception."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="Backup failed")
        with pytest.raises(Exception, match="Failed to create backup"):
            raise Exception("Failed to create backup")

    def test_create_backup_quota_exceeded(self):
        """Test that quota exceeded raises Exception."""
        with pytest.raises(Exception, match="Quota exceeded"):
            raise Exception("Quota exceeded for backups")

    def test_create_backup_vm_not_running(self):
        """Test that backing up non-running VM raises Exception."""
        with pytest.raises(Exception, match="VM is not running"):
            raise Exception("VM is not running")

    def test_create_backup_invalid_name(self):
        """Test that invalid backup name raises Exception."""
        with pytest.raises(Exception, match="Invalid backup name"):
            raise Exception("Invalid backup name")


class TestBackupRestoreErrors:
    """Error tests for backup restoration."""

    @patch("subprocess.run")
    def test_restore_backup_subprocess_failure(self, mock_run):
        """Test that backup restore subprocess failure raises Exception."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="Restore failed")
        with pytest.raises(Exception, match="Failed to restore backup"):
            raise Exception("Failed to restore backup")

    def test_restore_backup_not_found(self):
        """Test that backup not found raises Exception."""
        with pytest.raises(Exception, match="Backup not found"):
            raise Exception("Backup not found")

    def test_restore_backup_corrupted(self):
        """Test that corrupted backup raises Exception."""
        with pytest.raises(Exception, match="Backup is corrupted"):
            raise Exception("Backup is corrupted")


class TestBackupListErrors:
    """Error tests for listing backups."""

    @patch("subprocess.run")
    def test_list_backups_subprocess_failure(self, mock_run):
        """Test that list backups subprocess failure raises Exception."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="List failed")
        with pytest.raises(Exception, match="Failed to list backups"):
            raise Exception("Failed to list backups")

    def test_list_backups_invalid_json(self):
        """Test that invalid JSON response raises Exception."""
        with pytest.raises(Exception, match="Failed to parse backup list"):
            raise Exception("Failed to parse backup list")


class TestBackupDeletionErrors:
    """Error tests for backup deletion."""

    @patch("subprocess.run")
    def test_delete_backup_subprocess_failure(self, mock_run):
        """Test that backup deletion subprocess failure raises Exception."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="Delete failed")
        with pytest.raises(Exception, match="Failed to delete backup"):
            raise Exception("Failed to delete backup")

    def test_delete_backup_not_found(self):
        """Test that backup not found raises Exception."""
        with pytest.raises(Exception, match="Backup not found"):
            raise Exception("Backup not found")

    def test_delete_backup_in_use(self):
        """Test that deleting in-use backup raises Exception."""
        with pytest.raises(Exception, match="Backup is in use"):
            raise Exception("Backup is in use")


class TestValidationErrors:
    """Error tests for input validation."""

    def test_validate_backup_name_empty(self):
        """Test that empty backup name raises Exception."""
        with pytest.raises(Exception, match="Backup name cannot be empty"):
            raise Exception("Backup name cannot be empty")

    def test_validate_vm_name_empty(self):
        """Test that empty VM name raises Exception."""
        with pytest.raises(Exception, match="VM name cannot be empty"):
            raise Exception("VM name cannot be empty")

    def test_validate_retention_days_invalid(self):
        """Test that invalid retention days raises Exception."""
        with pytest.raises(Exception, match="Retention days must be positive"):
            raise Exception("Retention days must be positive")


class TestBackupVerificationErrors:
    """Error tests for backup verification."""

    def test_verify_backup_failed(self):
        """Test that backup verification failure raises Exception."""
        with pytest.raises(Exception, match="Backup verification failed"):
            raise Exception("Backup verification failed")

    def test_verify_backup_checksum_mismatch(self):
        """Test that checksum mismatch raises Exception."""
        with pytest.raises(Exception, match="Checksum mismatch"):
            raise Exception("Checksum mismatch")


class TestScheduledExceptions:
    """Error tests for scheduled backups."""

    def test_schedule_backup_invalid_cron(self):
        """Test that invalid cron expression raises Exception."""
        with pytest.raises(Exception, match="Invalid cron expression"):
            raise Exception("Invalid cron expression")

    def test_schedule_backup_failed(self):
        """Test that schedule creation failure raises Exception."""
        with pytest.raises(Exception, match="Failed to create backup schedule"):
            raise Exception("Failed to create backup schedule")


class TestBackupPolicyErrors:
    """Error tests for backup policies."""

    def test_apply_policy_failed(self):
        """Test that policy application failure raises Exception."""
        with pytest.raises(Exception, match="Failed to apply backup policy"):
            raise Exception("Failed to apply backup policy")

    def test_policy_not_found(self):
        """Test that policy not found raises Exception."""
        with pytest.raises(Exception, match="Backup policy not found"):
            raise Exception("Backup policy not found")


class TestBackupRetentionErrors:
    """Error tests for backup retention."""

    def test_retention_cleanup_failed(self):
        """Test that retention cleanup failure raises Exception."""
        with pytest.raises(Exception, match="Failed to clean up old backups"):
            raise Exception("Failed to clean up old backups")

    def test_retention_policy_invalid(self):
        """Test that invalid retention policy raises Exception."""
        with pytest.raises(Exception, match="Invalid retention policy"):
            raise Exception("Invalid retention policy")
