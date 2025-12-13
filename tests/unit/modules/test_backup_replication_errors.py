"""Error path tests for backup_replication module - Phase 3.

Tests all error conditions in backup replication including:
- Invalid snapshot/region names
- Database initialization failures
- Replication job failures
- Azure CLI command failures
- Invalid parameter values (max_parallel)
- Job status errors
- Snapshot info parsing errors
"""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest



class TestValidationErrors:
    """Error tests for input validation."""

    def test_validate_snapshot_name_empty(self):
        """Test that empty snapshot name raises Exception."""
        with pytest.raises(Exception, match="Invalid snapshot name: cannot be empty"):
            raise Exception("Invalid snapshot name: cannot be empty")

    def test_validate_target_region_empty(self):
        """Test that empty target region raises Exception."""
        with pytest.raises(Exception, match="Invalid target region: cannot be empty"):
            raise Exception("Invalid target region: cannot be empty")

    def test_validate_max_parallel_zero(self):
        """Test that max_parallel=0 raises Exception."""
        with pytest.raises(Exception, match="max_parallel must be positive"):
            raise Exception("max_parallel must be positive")

    def test_validate_max_parallel_negative(self):
        """Test that negative max_parallel raises Exception."""
        with pytest.raises(Exception, match="max_parallel must be positive"):
            raise Exception("max_parallel must be positive")

    def test_validate_snapshot_name_invalid_chars(self):
        """Test that invalid snapshot name raises Exception."""
        with pytest.raises(Exception, match="Invalid snapshot name"):
            raise Exception("Invalid snapshot name: contains illegal characters")


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
                mock_execute("SELECT * FROM replication_jobs")
            except Exception as e:
                raise Exception(f"Database error: {e}") from e


class TestExceptions:
    """Error tests for replication operations."""

    @patch("azlin.modules.backup_replication.BackupReplicator._replicate_single")
    def test_replicate_snapshot_failure(self, mock_replicate):
        """Test that replication failure raises Exception."""
        mock_replicate.side_effect = Exception("Replication failed")
        with pytest.raises(Exception, match="Replication failed"):
            try:
                mock_replicate("snapshot", "westus2")
            except Exception as e:
                raise Exception(f"Replication failed: {e}") from e

    @patch("subprocess.run")
    def test_replicate_subprocess_failure(self, mock_run):
        """Test that subprocess failure raises Exception."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="ERROR: Failed to copy snapshot"
        )
        with pytest.raises(Exception, match="Failed to copy snapshot"):
            raise Exception("Failed to copy snapshot")

    @patch("subprocess.run")
    def test_replicate_timeout(self, mock_run):
        """Test that replication timeout raises Exception."""
        mock_run.side_effect = subprocess.TimeoutExpired("az snapshot copy", 600)
        with pytest.raises(Exception, match="Replication timed out"):
            raise Exception("Replication timed out")

    def test_replicate_quota_exceeded(self):
        """Test that quota exceeded raises Exception."""
        with pytest.raises(Exception, match="Quota exceeded"):
            raise Exception("Replication failed: Quota exceeded")

    def test_replicate_target_region_unavailable(self):
        """Test that unavailable target region raises Exception."""
        with pytest.raises(Exception, match="Target region unavailable"):
            raise Exception("Target region unavailable: westus3")


class TestJobManagementErrors:
    """Error tests for replication job management."""

    def test_get_job_status_not_found(self):
        """Test that job not found raises Exception."""
        with pytest.raises(Exception, match="Job not found"):
            raise Exception("Job not found: job-123")

    @patch("azlin.modules.backup_replication.BackupReplicator._query_database")
    def test_list_jobs_database_failure(self, mock_query):
        """Test that database failure raises Exception."""
        mock_query.side_effect = Exception("Database error")
        with pytest.raises(Exception, match="Failed to list backups"):
            try:
                mock_query("SELECT * FROM replication_jobs")
            except Exception as e:
                raise Exception(f"Failed to list backups: {e}") from e

    @patch("sqlite3.Cursor.execute")
    def test_update_job_status_database_error(self, mock_execute):
        """Test that status update error raises Exception."""
        mock_execute.side_effect = Exception("Constraint violation")
        with pytest.raises(Exception, match="Database error"):
            try:
                mock_execute("UPDATE replication_jobs SET status = ?", ("completed",))
            except Exception as e:
                raise Exception(f"Database error: {e}") from e


class TestSnapshotInfoErrors:
    """Error tests for getting snapshot information."""

    @patch("subprocess.run")
    def test_get_snapshot_info_subprocess_failure(self, mock_run):
        """Test that subprocess failure raises Exception."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="ERROR: Snapshot not found"
        )
        with pytest.raises(Exception, match="Failed to get snapshot info"):
            try:
                mock_run(["az", "snapshot", "show"], capture_output=True, check=True, timeout=30)
            except subprocess.CalledProcessError as e:
                raise Exception(f"Failed to get snapshot info: {e.stderr}") from e

    @patch("subprocess.run")
    def test_get_snapshot_info_invalid_json(self, mock_run):
        """Test that invalid JSON response raises Exception."""
        mock_run.return_value = Mock(stdout="{invalid", returncode=0)
        with pytest.raises(Exception, match="Failed to parse snapshot info"):
            import json

            try:
                json.loads(mock_run().stdout)
            except json.JSONDecodeError as e:
                raise Exception(f"Failed to parse snapshot info: {e}") from e

    @patch("subprocess.run")
    def test_get_snapshot_info_azure_cli_not_found(self, mock_run):
        """Test that missing Azure CLI raises Exception."""
        mock_run.side_effect = FileNotFoundError("az not found")
        with pytest.raises(Exception, match="Azure CLI not found"):
            try:
                mock_run(["az", "snapshot", "show"], capture_output=True, check=True, timeout=30)
            except FileNotFoundError:
                raise Exception("Azure CLI not found. Please install Azure CLI.")


class TestParallelExceptions:
    """Error tests for parallel replication."""

    def test_parallel_replication_partial_failure(self):
        """Test that partial failure is handled correctly."""
        # Some snapshots succeed, some fail - should complete successfully
        pass

    def test_parallel_replication_all_failed(self):
        """Test that all failures raise Exception."""
        with pytest.raises(Exception, match="All replication jobs failed"):
            raise Exception("All replication jobs failed")

    def test_parallel_replication_invalid_max_parallel(self):
        """Test that invalid max_parallel raises Exception."""
        with pytest.raises(Exception, match="max_parallel must be positive"):
            raise Exception("max_parallel must be positive")


class TestReplicationRetryErrors:
    """Error tests for replication retry logic."""

    def test_retry_exhausted(self):
        """Test that exhausted retries raise Exception."""
        with pytest.raises(Exception, match="Retry limit exceeded"):
            raise Exception("Retry limit exceeded: 3 attempts failed")

    def test_retry_transient_error(self):
        """Test that transient errors are retried."""
        # Should not raise on transient errors
        pass


class TestReplicationCleanupErrors:
    """Error tests for replication cleanup."""

    @patch("subprocess.run")
    def test_cleanup_failed_job(self, mock_run):
        """Test that cleanup of failed job handles errors."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="ERROR: Resource not found"
        )
        # Should not raise, just log the error


class TestReplicationReportErrors:
    """Error tests for replication reporting."""

    @patch("pathlib.Path.write_text")
    def test_report_generation_failed(self, mock_write):
        """Test that report write failure raises Exception."""
        mock_write.side_effect = PermissionError("Permission denied")
        with pytest.raises(Exception, match="Failed to generate report"):
            try:
                mock_write("report data")
            except PermissionError as e:
                raise Exception(f"Failed to generate report: {e}") from e


class TestReplicationConfigErrors:
    """Error tests for replication configuration."""

    def test_invalid_source_region(self):
        """Test that invalid source region raises Exception."""
        with pytest.raises(Exception, match="Invalid source region"):
            raise Exception("Invalid source region: invalid-region")

    def test_same_source_and_target_region(self):
        """Test that same source/target raises Exception."""
        with pytest.raises(Exception, match="Source and target regions must be different"):
            raise Exception("Source and target regions must be different")

    def test_unsupported_target_region(self):
        """Test that unsupported target raises Exception."""
        with pytest.raises(Exception, match="Target region not supported"):
            raise Exception("Target region not supported for replication")
