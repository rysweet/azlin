"""Unit tests for ReplicationManager module.

Tests for cross-region backup replication.

Testing pyramid:
- 60% Unit tests (fast, heavily mocked)
- 30% Integration tests (multiple components)
- 10% E2E tests (complete workflows)
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, call, patch

import pytest

from azlin.modules.backup_replication import (
    ReplicationError,
    ReplicationJob,
    ReplicationManager,
)


# ============================================================================
# UNIT TESTS (60% of test suite)
# ============================================================================


class TestReplicationJobDataclass:
    """Test ReplicationJob dataclass structure."""

    def test_replication_job_creation(self):
        """Test ReplicationJob creation with all fields."""
        now = datetime.now(UTC)
        job = ReplicationJob(
            source_snapshot="vm1-backup-daily-20251201-100000",
            target_snapshot="vm1-backup-daily-20251201-100000-westus2",
            source_region="eastus",
            target_region="westus2",
            source_resource_group="test-rg",
            target_resource_group="test-rg-westus2",
            status="completed",
            started_at=now,
            completed_at=now,
            error_message=None,
        )

        assert job.source_snapshot == "vm1-backup-daily-20251201-100000"
        assert job.target_snapshot == "vm1-backup-daily-20251201-100000-westus2"
        assert job.source_region == "eastus"
        assert job.target_region == "westus2"
        assert job.status == "completed"
        assert job.error_message is None

    def test_replication_job_with_error(self):
        """Test ReplicationJob with error state."""
        now = datetime.now(UTC)
        job = ReplicationJob(
            source_snapshot="vm1-backup-daily-20251201-100000",
            target_snapshot="vm1-backup-daily-20251201-100000-westus2",
            source_region="eastus",
            target_region="westus2",
            source_resource_group="test-rg",
            target_resource_group="test-rg-westus2",
            status="failed",
            started_at=now,
            completed_at=now,
            error_message="QuotaExceeded: Snapshot quota exceeded in target region",
        )

        assert job.status == "failed"
        assert "QuotaExceeded" in job.error_message


class TestReplicationManagerInit:
    """Test ReplicationManager initialization."""

    def test_init_creates_database(self, tmp_path):
        """Test initialization creates SQLite database."""
        db_path = tmp_path / "replication.db"

        manager = ReplicationManager(storage_path=db_path)

        assert db_path.exists()
        # Verify tables exist
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='replication_jobs'"
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None

    def test_init_with_existing_database(self, tmp_path):
        """Test initialization with existing database."""
        db_path = tmp_path / "replication.db"

        # Create manager twice
        manager1 = ReplicationManager(storage_path=db_path)
        manager2 = ReplicationManager(storage_path=db_path)

        # Should not raise error
        assert db_path.exists()

    def test_init_creates_indexes(self, tmp_path):
        """Test initialization creates database indexes."""
        db_path = tmp_path / "replication.db"

        manager = ReplicationManager(storage_path=db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "idx_snapshot" in indexes
        assert "idx_status" in indexes
        assert "idx_target_region" in indexes


class TestReplicateBackup:
    """Test single backup replication."""

    @patch("subprocess.run")
    def test_replicate_backup_success(self, mock_run, tmp_path):
        """Test successful backup replication."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        # Mock successful Azure CLI response
        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"id": "/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Compute/snapshots/vm1-backup-westus2", "provisioningState": "Succeeded"}',
            stderr="",
        )

        job = manager.replicate_backup(
            snapshot_name="vm1-backup-daily-20251201-100000",
            source_resource_group="test-rg",
            target_region="westus2",
        )

        assert job.status == "completed"
        assert job.source_snapshot == "vm1-backup-daily-20251201-100000"
        assert job.target_region == "westus2"
        assert job.error_message is None

    @patch("subprocess.run")
    def test_replicate_backup_failure(self, mock_run, tmp_path):
        """Test failed backup replication."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        # Mock Azure CLI error
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="QuotaExceeded: Snapshot quota exceeded",
        )

        with pytest.raises(ReplicationError, match="Snapshot quota exceeded"):
            manager.replicate_backup(
                snapshot_name="vm1-backup-daily-20251201-100000",
                source_resource_group="test-rg",
                target_region="westus2",
            )

    @patch("subprocess.run")
    def test_replicate_backup_custom_target_rg(self, mock_run, tmp_path):
        """Test replication with custom target resource group."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"id": "...", "provisioningState": "Succeeded"}',
            stderr="",
        )

        job = manager.replicate_backup(
            snapshot_name="vm1-backup-daily-20251201-100000",
            source_resource_group="test-rg",
            target_region="westus2",
            target_resource_group="test-rg-dr",
        )

        assert job.target_resource_group == "test-rg-dr"

        # Verify Azure CLI was called with correct target RG
        call_args = mock_run.call_args[0][0]
        assert "--resource-group" in call_args
        rg_index = call_args.index("--resource-group")
        assert call_args[rg_index + 1] == "test-rg-dr"

    @patch("subprocess.run")
    def test_replicate_backup_timeout(self, mock_run, tmp_path):
        """Test replication timeout handling."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        mock_run.side_effect = TimeoutError("Operation timed out")

        with pytest.raises(ReplicationError, match="timed out"):
            manager.replicate_backup(
                snapshot_name="vm1-backup-daily-20251201-100000",
                source_resource_group="test-rg",
                target_region="westus2",
            )

    @patch("subprocess.run")
    def test_replicate_backup_invalid_json_response(self, mock_run, tmp_path):
        """Test handling of invalid JSON response from Azure."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        mock_run.return_value = Mock(
            returncode=0,
            stdout="invalid json",
            stderr="",
        )

        with pytest.raises(ReplicationError, match="Failed to parse"):
            manager.replicate_backup(
                snapshot_name="vm1-backup-daily-20251201-100000",
                source_resource_group="test-rg",
                target_region="westus2",
            )


class TestReplicateAllPending:
    """Test parallel replication of multiple backups."""

    @patch("azlin.modules.backup_replication.BackupManager.list_backups")
    @patch("azlin.modules.backup_replication.ReplicationManager.replicate_backup")
    def test_replicate_all_pending_success(self, mock_replicate, mock_list, tmp_path):
        """Test successful parallel replication of all pending backups."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        # Mock 3 unreplicated backups
        from azlin.modules.backup_manager import BackupInfo
        backups = [
            BackupInfo(
                snapshot_name=f"vm1-backup-daily-{i}",
                vm_name="test-vm",
                resource_group="test-rg",
                creation_time=datetime.now(UTC),
                retention_tier="daily",
                replicated=False,
            )
            for i in range(3)
        ]
        mock_list.return_value = backups

        # Mock successful replication
        mock_replicate.return_value = Mock(
            status="completed",
            error_message=None,
        )

        jobs = manager.replicate_all_pending(
            vm_name="test-vm",
            source_resource_group="test-rg",
            target_region="westus2",
        )

        assert len(jobs) == 3
        assert mock_replicate.call_count == 3

    @patch("azlin.modules.backup_replication.BackupManager.list_backups")
    def test_replicate_all_pending_no_backups(self, mock_list, tmp_path):
        """Test replication when no pending backups exist."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        mock_list.return_value = []

        jobs = manager.replicate_all_pending(
            vm_name="test-vm",
            source_resource_group="test-rg",
            target_region="westus2",
        )

        assert jobs == []

    @patch("azlin.modules.backup_replication.BackupManager.list_backups")
    @patch("azlin.modules.backup_replication.ReplicationManager.replicate_backup")
    def test_replicate_all_pending_partial_failure(self, mock_replicate, mock_list, tmp_path):
        """Test parallel replication with some failures."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        from azlin.modules.backup_manager import BackupInfo
        backups = [
            BackupInfo(
                snapshot_name=f"vm1-backup-daily-{i}",
                vm_name="test-vm",
                resource_group="test-rg",
                creation_time=datetime.now(UTC),
                retention_tier="daily",
                replicated=False,
            )
            for i in range(3)
        ]
        mock_list.return_value = backups

        # First succeeds, second fails, third succeeds
        mock_replicate.side_effect = [
            Mock(status="completed", error_message=None),
            ReplicationError("Quota exceeded"),
            Mock(status="completed", error_message=None),
        ]

        jobs = manager.replicate_all_pending(
            vm_name="test-vm",
            source_resource_group="test-rg",
            target_region="westus2",
        )

        # Should return 2 successful jobs
        assert len(jobs) == 2

    @patch("azlin.modules.backup_replication.BackupManager.list_backups")
    @patch("azlin.modules.backup_replication.ReplicationManager.replicate_backup")
    def test_replicate_all_pending_respects_max_parallel(self, mock_replicate, mock_list, tmp_path):
        """Test parallel replication respects max_parallel limit."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        from azlin.modules.backup_manager import BackupInfo
        backups = [
            BackupInfo(
                snapshot_name=f"vm1-backup-daily-{i}",
                vm_name="test-vm",
                resource_group="test-rg",
                creation_time=datetime.now(UTC),
                retention_tier="daily",
                replicated=False,
            )
            for i in range(10)
        ]
        mock_list.return_value = backups

        mock_replicate.return_value = Mock(status="completed")

        jobs = manager.replicate_all_pending(
            vm_name="test-vm",
            source_resource_group="test-rg",
            target_region="westus2",
            max_parallel=3,
        )

        # Should process all 10 backups in batches of 3
        assert len(jobs) == 10


class TestCheckReplicationStatus:
    """Test replication status checking."""

    def test_check_replication_status_completed(self, tmp_path):
        """Test checking status of completed replication."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        # Create a completed job
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        now = datetime.now(UTC).isoformat()
        cursor.execute(
            """
            INSERT INTO replication_jobs
            (source_snapshot, target_snapshot, source_region, target_region,
             source_resource_group, target_resource_group, status, started_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "vm1-backup-daily-20251201-100000",
                "vm1-backup-daily-20251201-100000-westus2",
                "eastus",
                "westus2",
                "test-rg",
                "test-rg",
                "completed",
                now,
                now,
            ),
        )
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()

        job = manager.check_replication_status(job_id)

        assert job.status == "completed"
        assert job.completed_at is not None

    def test_check_replication_status_in_progress(self, tmp_path):
        """Test checking status of in-progress replication."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        # Create an in-progress job
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        now = datetime.now(UTC).isoformat()
        cursor.execute(
            """
            INSERT INTO replication_jobs
            (source_snapshot, target_snapshot, source_region, target_region,
             source_resource_group, target_resource_group, status, started_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "vm1-backup-daily-20251201-100000",
                "vm1-backup-daily-20251201-100000-westus2",
                "eastus",
                "westus2",
                "test-rg",
                "test-rg",
                "in_progress",
                now,
            ),
        )
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()

        job = manager.check_replication_status(job_id)

        assert job.status == "in_progress"
        assert job.completed_at is None

    def test_check_replication_status_failed(self, tmp_path):
        """Test checking status of failed replication."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        # Create a failed job
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        now = datetime.now(UTC).isoformat()
        cursor.execute(
            """
            INSERT INTO replication_jobs
            (source_snapshot, target_snapshot, source_region, target_region,
             source_resource_group, target_resource_group, status, started_at,
             completed_at, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "vm1-backup-daily-20251201-100000",
                "vm1-backup-daily-20251201-100000-westus2",
                "eastus",
                "westus2",
                "test-rg",
                "test-rg",
                "failed",
                now,
                now,
                "QuotaExceeded",
            ),
        )
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()

        job = manager.check_replication_status(job_id)

        assert job.status == "failed"
        assert job.error_message == "QuotaExceeded"

    def test_check_replication_status_not_found(self, tmp_path):
        """Test checking status of non-existent job."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        with pytest.raises(ReplicationError, match="Job not found"):
            manager.check_replication_status(999999)


class TestListReplicationJobs:
    """Test listing replication jobs."""

    def test_list_replication_jobs_all(self, tmp_path):
        """Test listing all replication jobs."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        # Create multiple jobs
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        now = datetime.now(UTC).isoformat()
        for i in range(5):
            cursor.execute(
                """
                INSERT INTO replication_jobs
                (source_snapshot, target_snapshot, source_region, target_region,
                 source_resource_group, target_resource_group, status, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"vm1-backup-daily-{i}",
                    f"vm1-backup-daily-{i}-westus2",
                    "eastus",
                    "westus2",
                    "test-rg",
                    "test-rg",
                    "completed" if i % 2 == 0 else "failed",
                    now,
                ),
            )
        conn.commit()
        conn.close()

        jobs = manager.list_replication_jobs()

        assert len(jobs) == 5

    def test_list_replication_jobs_filter_by_vm(self, tmp_path):
        """Test filtering replication jobs by VM name."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        # Create jobs for different VMs
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        now = datetime.now(UTC).isoformat()
        for vm in ["vm1", "vm2"]:
            for i in range(2):
                cursor.execute(
                    """
                    INSERT INTO replication_jobs
                    (source_snapshot, target_snapshot, source_region, target_region,
                     source_resource_group, target_resource_group, status, started_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{vm}-backup-daily-{i}",
                        f"{vm}-backup-daily-{i}-westus2",
                        "eastus",
                        "westus2",
                        "test-rg",
                        "test-rg",
                        "completed",
                        now,
                    ),
                )
        conn.commit()
        conn.close()

        jobs = manager.list_replication_jobs(vm_name="vm1")

        assert len(jobs) == 2
        assert all("vm1" in job.source_snapshot for job in jobs)

    def test_list_replication_jobs_filter_by_status(self, tmp_path):
        """Test filtering replication jobs by status."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        # Create jobs with different statuses
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        now = datetime.now(UTC).isoformat()
        statuses = ["completed", "failed", "in_progress", "completed", "failed"]
        for i, status in enumerate(statuses):
            cursor.execute(
                """
                INSERT INTO replication_jobs
                (source_snapshot, target_snapshot, source_region, target_region,
                 source_resource_group, target_resource_group, status, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"vm1-backup-daily-{i}",
                    f"vm1-backup-daily-{i}-westus2",
                    "eastus",
                    "westus2",
                    "test-rg",
                    "test-rg",
                    status,
                    now,
                ),
            )
        conn.commit()
        conn.close()

        jobs = manager.list_replication_jobs(status="failed")

        assert len(jobs) == 2
        assert all(job.status == "failed" for job in jobs)

    def test_list_replication_jobs_empty(self, tmp_path):
        """Test listing when no jobs exist."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        jobs = manager.list_replication_jobs()

        assert jobs == []


# ============================================================================
# BOUNDARY TESTS (Part of Unit Tests)
# ============================================================================


class TestBoundaryConditions:
    """Test edge cases and boundary conditions."""

    @patch("subprocess.run")
    def test_replicate_backup_empty_snapshot_name(self, mock_run, tmp_path):
        """Test error for empty snapshot name."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        with pytest.raises(ReplicationError, match="Invalid snapshot name"):
            manager.replicate_backup(
                snapshot_name="",
                source_resource_group="test-rg",
                target_region="westus2",
            )

    @patch("subprocess.run")
    def test_replicate_backup_empty_target_region(self, mock_run, tmp_path):
        """Test error for empty target region."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        with pytest.raises(ReplicationError, match="Invalid target region"):
            manager.replicate_backup(
                snapshot_name="vm1-backup-daily-20251201-100000",
                source_resource_group="test-rg",
                target_region="",
            )

    def test_replicate_all_pending_max_parallel_zero(self, tmp_path):
        """Test error for zero max_parallel value."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        with pytest.raises(ReplicationError, match="max_parallel must be positive"):
            manager.replicate_all_pending(
                vm_name="test-vm",
                source_resource_group="test-rg",
                target_region="westus2",
                max_parallel=0,
            )

    def test_replicate_all_pending_max_parallel_negative(self, tmp_path):
        """Test error for negative max_parallel value."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        with pytest.raises(ReplicationError, match="max_parallel must be positive"):
            manager.replicate_all_pending(
                vm_name="test-vm",
                source_resource_group="test-rg",
                target_region="westus2",
                max_parallel=-1,
            )

    @patch("azlin.modules.backup_replication.BackupManager.list_backups")
    @patch("azlin.modules.backup_replication.ReplicationManager.replicate_backup")
    def test_replicate_all_pending_max_parallel_high(self, mock_replicate, mock_list, tmp_path):
        """Test handling of extremely high max_parallel value."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        from azlin.modules.backup_manager import BackupInfo
        backups = [
            BackupInfo(
                snapshot_name=f"vm1-backup-daily-{i}",
                vm_name="test-vm",
                resource_group="test-rg",
                creation_time=datetime.now(UTC),
                retention_tier="daily",
                replicated=False,
            )
            for i in range(3)
        ]
        mock_list.return_value = backups

        mock_replicate.return_value = Mock(status="completed")

        # max_parallel=100 should work (will be limited by actual backup count)
        jobs = manager.replicate_all_pending(
            vm_name="test-vm",
            source_resource_group="test-rg",
            target_region="westus2",
            max_parallel=100,
        )

        assert len(jobs) == 3


# ============================================================================
# ERROR HANDLING TESTS (Part of Unit Tests)
# ============================================================================


class TestErrorHandling:
    """Test error handling and exception cases."""

    def test_init_database_permission_error(self, tmp_path):
        """Test error handling when database file is not writable."""
        db_path = tmp_path / "readonly.db"
        db_path.touch()
        db_path.chmod(0o444)  # Read-only

        with pytest.raises(ReplicationError, match="Cannot write to database"):
            ReplicationManager(storage_path=db_path)

    @patch("subprocess.run")
    def test_replicate_backup_azure_cli_not_found(self, mock_run, tmp_path):
        """Test error when Azure CLI is not available."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        mock_run.side_effect = FileNotFoundError("az command not found")

        with pytest.raises(ReplicationError, match="Azure CLI not found"):
            manager.replicate_backup(
                snapshot_name="vm1-backup-daily-20251201-100000",
                source_resource_group="test-rg",
                target_region="westus2",
            )

    def test_check_replication_status_database_corruption(self, tmp_path):
        """Test error handling for corrupted database."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        # Corrupt the database
        with open(db_path, "wb") as f:
            f.write(b"corrupted data")

        with pytest.raises(ReplicationError, match="Database error"):
            manager.check_replication_status(1)

    @patch("azlin.modules.backup_replication.BackupManager.list_backups")
    def test_replicate_all_pending_list_backups_fails(self, mock_list, tmp_path):
        """Test error handling when listing backups fails."""
        db_path = tmp_path / "replication.db"
        manager = ReplicationManager(storage_path=db_path)

        mock_list.side_effect = Exception("Azure API error")

        with pytest.raises(ReplicationError, match="Failed to list backups"):
            manager.replicate_all_pending(
                vm_name="test-vm",
                source_resource_group="test-rg",
                target_region="westus2",
            )
