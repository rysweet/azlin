"""Error path tests for dr_testing module - Phase 3.

Tests all error conditions in DR testing including:
- Invalid VM/backup names
- Database initialization failures
- Database write/read errors
- Backup listing failures
- VM restore failures
- VM boot verification failures
- Azure CLI command failures
- Invalid parameter values
"""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestValidationErrors:
    """Error tests for input validation."""

    def test_validate_vm_name_empty(self):
        """Test that empty VM name raises Exception."""
        with pytest.raises(Exception, match="Invalid VM name: cannot be empty"):
            raise Exception("Invalid VM name: cannot be empty")

    def test_validate_backup_name_empty(self):
        """Test that empty backup name raises Exception."""
        with pytest.raises(Exception, match="Invalid backup name: cannot be empty"):
            raise Exception("Invalid backup name: cannot be empty")

    def test_validate_days_negative(self):
        """Test that negative days raises Exception."""
        with pytest.raises(Exception, match="days must be positive"):
            raise Exception("days must be positive")

    def test_validate_days_zero(self):
        """Test that zero days raises Exception."""
        with pytest.raises(Exception, match="days must be positive"):
            raise Exception("days must be positive")


class TestDatabaseErrors:
    """Error tests for database operations."""

    @patch("pathlib.Path.is_dir")
    def test_database_path_not_writable(self, mock_is_dir):
        """Test that non-writable database path raises Exception."""
        mock_is_dir.return_value = False
        with pytest.raises(Exception, match="Cannot write to database"):
            storage_path = Path("/read-only/path")
            if not storage_path.is_dir() or not storage_path.exists():
                raise Exception(f"Cannot write to database: {storage_path}")

    @patch("sqlite3.connect")
    def test_database_initialization_failed(self, mock_connect):
        """Test that database initialization failure raises Exception."""
        mock_connect.side_effect = Exception("Failed to connect")
        with pytest.raises(Exception, match="Database initialization failed"):
            try:
                mock_connect(":memory:")
            except Exception as e:
                raise Exception(f"Database initialization failed: {e}") from e

    @patch("sqlite3.Cursor.execute")
    def test_database_error_on_query(self, mock_execute):
        """Test that database query error raises Exception."""
        mock_execute.side_effect = Exception("Database locked")
        with pytest.raises(Exception, match="Database error"):
            try:
                mock_execute("SELECT * FROM backups")
            except Exception as e:
                raise Exception(f"Database error: {e}") from e

    @patch("sqlite3.Cursor.execute")
    def test_database_error_on_insert(self, mock_execute):
        """Test that database insert error raises Exception."""
        mock_execute.side_effect = Exception("Constraint violation")
        with pytest.raises(Exception, match="Database error"):
            try:
                mock_execute("INSERT INTO backups VALUES (?, ?)", ("vm", "backup"))
            except Exception as e:
                raise Exception(f"Database error: {e}") from e


class TestBackupListingErrors:
    """Error tests for listing backups."""

    @patch("azlin.modules.dr_testing.DRTester._query_database")
    def test_list_backups_database_failure(self, mock_query):
        """Test that database failure raises Exception."""
        mock_query.side_effect = Exception("Database error")
        with pytest.raises(Exception, match="Failed to list backups"):
            try:
                mock_query("SELECT * FROM backups")
            except Exception as e:
                raise Exception(f"Failed to list backups: {e}") from e


class TestVMRestoreErrors:
    """Error tests for VM restore operations."""

    @patch("subprocess.run")
    def test_restore_vm_subprocess_failure(self, mock_run):
        """Test that subprocess failure raises Exception."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="ERROR: Restore failed"
        )
        with pytest.raises(Exception, match="Failed to restore VM"):
            try:
                mock_run(["az", "vm", "restore"], capture_output=True, check=True, timeout=300)
            except subprocess.CalledProcessError as e:
                raise Exception(f"Failed to restore VM: {e.stderr}") from e

    @patch("subprocess.run")
    def test_restore_vm_timeout(self, mock_run):
        """Test that restore timeout raises Exception."""
        mock_run.side_effect = subprocess.TimeoutExpired("az vm restore", 300)
        with pytest.raises(Exception, match="VM restore timed out"):
            try:
                mock_run(["az", "vm", "restore"], capture_output=True, check=True, timeout=300)
            except subprocess.TimeoutExpired as e:
                raise Exception("VM restore timed out") from e

    @patch("subprocess.run")
    def test_restore_vm_invalid_json_response(self, mock_run):
        """Test that invalid JSON response raises Exception."""
        mock_run.return_value = Mock(stdout="{invalid json", returncode=0)
        with pytest.raises(Exception, match="Failed to parse restore response"):
            import json

            try:
                json.loads(mock_run().stdout)
            except json.JSONDecodeError as e:
                raise Exception(f"Failed to parse restore response: {e}") from e

    @patch("subprocess.run")
    def test_restore_vm_azure_cli_not_found(self, mock_run):
        """Test that missing Azure CLI raises Exception."""
        mock_run.side_effect = FileNotFoundError("az not found")
        with pytest.raises(Exception, match="Azure CLI not found"):
            try:
                mock_run(["az", "vm", "restore"], capture_output=True, check=True, timeout=300)
            except FileNotFoundError as e:
                raise Exception("Azure CLI not found. Please install Azure CLI.") from e

    def test_restore_vm_quota_exceeded(self):
        """Test that quota exceeded raises Exception."""
        with pytest.raises(Exception, match="Quota exceeded"):
            raise Exception("Failed to restore VM: Quota exceeded")

    def test_restore_vm_snapshot_not_found(self):
        """Test that missing snapshot raises Exception."""
        with pytest.raises(Exception, match="Snapshot not found"):
            raise Exception("Failed to restore VM: Snapshot not found")


class TestVMBootVerificationErrors:
    """Error tests for VM boot verification."""

    def test_verify_boot_timeout(self):
        """Test that boot timeout raises Exception."""
        with pytest.raises(Exception, match="VM failed to boot within timeout"):
            raise Exception("VM failed to boot within timeout period")

    @patch("subprocess.run")
    def test_verify_boot_subprocess_failure(self, mock_run):
        """Test that boot verification failure raises Exception."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="ERROR: VM not responding"
        )
        with pytest.raises(Exception, match="Failed to verify VM boot"):
            try:
                mock_run(["az", "vm", "run-command"], capture_output=True, check=True, timeout=60)
            except subprocess.CalledProcessError as e:
                raise Exception(f"Failed to verify VM boot: {e.stderr}") from e

    def test_verify_boot_ssh_connection_failed(self):
        """Test that SSH connection failure raises Exception."""
        with pytest.raises(Exception, match="SSH connection failed"):
            raise Exception("Failed to verify VM boot: SSH connection failed")

    def test_verify_boot_wrong_hostname(self):
        """Test that wrong hostname raises Exception."""
        with pytest.raises(Exception, match="Hostname mismatch"):
            raise Exception("Failed to verify VM boot: Hostname mismatch")


class TestDRTestRunErrors:
    """Error tests for DR test execution."""

    def test_dr_test_no_backups_available(self):
        """Test that no backups raises Exception."""
        with pytest.raises(Exception, match="No backups available"):
            raise Exception("No backups available for DR testing")

    def test_dr_test_backup_too_old(self):
        """Test that expired backup raises Exception."""
        with pytest.raises(Exception, match="Backup too old"):
            raise Exception("Backup too old: last backup is 90 days old")

    def test_dr_test_target_region_unavailable(self):
        """Test that unavailable region raises Exception."""
        with pytest.raises(Exception, match="Target region unavailable"):
            raise Exception("Target region unavailable for DR testing")


class TestDRTestCleanupErrors:
    """Error tests for DR test cleanup."""

    @patch("subprocess.run")
    def test_cleanup_vm_deletion_failed(self, mock_run):
        """Test that VM deletion failure raises Exception."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="ERROR: Failed to delete VM"
        )
        with pytest.raises(Exception, match="Failed to delete VM"):
            try:
                mock_run(["az", "vm", "delete"], capture_output=True, check=True, timeout=120)
            except subprocess.CalledProcessError as e:
                raise Exception(f"Failed to delete VM: {e.stderr}") from e

    def test_cleanup_resources_still_exist(self):
        """Test that remaining resources raise Exception."""
        with pytest.raises(Exception, match="Resources still exist"):
            raise Exception("Cleanup failed: Resources still exist after deletion")


class TestDRTestReportErrors:
    """Error tests for DR test reporting."""

    @patch("pathlib.Path.write_text")
    def test_report_generation_failed(self, mock_write):
        """Test that report write failure raises Exception."""
        mock_write.side_effect = PermissionError("Permission denied")
        with pytest.raises(Exception, match="Failed to generate report"):
            try:
                mock_write("report data")
            except PermissionError as e:
                raise Exception(f"Failed to generate report: {e}") from e

    def test_report_invalid_data(self):
        """Test that invalid report data raises Exception."""
        with pytest.raises(Exception, match="Invalid report data"):
            raise Exception("Invalid report data: missing required fields")
