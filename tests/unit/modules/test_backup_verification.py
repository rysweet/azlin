"""Unit tests for VerificationManager module.

Tests for backup verification and integrity checking.

Testing pyramid:
- 60% Unit tests (fast, heavily mocked)
- 30% Integration tests (multiple components)
- 10% E2E tests (complete workflows)
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from azlin.modules.backup_verification import (
    VerificationError,
    VerificationManager,
    VerificationResult,
)


# ============================================================================
# UNIT TESTS (60% of test suite)
# ============================================================================


class TestVerificationResultDataclass:
    """Test VerificationResult dataclass structure."""

    def test_verification_result_success(self):
        """Test VerificationResult for successful verification."""
        now = datetime.now(UTC)
        result = VerificationResult(
            backup_name="vm1-backup-daily-20251201-100000",
            vm_name="test-vm",
            verified_at=now,
            success=True,
            disk_readable=True,
            size_matches=True,
            test_disk_created=True,
            test_disk_deleted=True,
            error_message=None,
            verification_time_seconds=45.2,
        )

        assert result.success is True
        assert result.disk_readable is True
        assert result.size_matches is True
        assert result.test_disk_created is True
        assert result.test_disk_deleted is True
        assert result.error_message is None
        assert result.verification_time_seconds == 45.2

    def test_verification_result_failure(self):
        """Test VerificationResult for failed verification."""
        now = datetime.now(UTC)
        result = VerificationResult(
            backup_name="vm1-backup-daily-20251201-100000",
            vm_name="test-vm",
            verified_at=now,
            success=False,
            disk_readable=False,
            size_matches=False,
            test_disk_created=True,
            test_disk_deleted=True,
            error_message="Test disk not readable",
            verification_time_seconds=30.5,
        )

        assert result.success is False
        assert result.disk_readable is False
        assert result.error_message == "Test disk not readable"


class TestVerificationManagerInit:
    """Test VerificationManager initialization."""

    def test_init_creates_database(self, tmp_path):
        """Test initialization creates SQLite database."""
        db_path = tmp_path / "verification.db"

        manager = VerificationManager(storage_path=db_path)

        assert db_path.exists()
        # Verify tables exist
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='verifications'"
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None

    def test_init_creates_indexes(self, tmp_path):
        """Test initialization creates database indexes."""
        db_path = tmp_path / "verification.db"

        manager = VerificationManager(storage_path=db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "idx_backup_name" in indexes
        assert "idx_vm_name" in indexes
        assert "idx_verified_at" in indexes
        assert "idx_success" in indexes


class TestVerifyBackup:
    """Test single backup verification."""

    @patch("subprocess.run")
    @patch("time.time")
    def test_verify_backup_success(self, mock_time, mock_run, tmp_path):
        """Test successful backup verification."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        # Mock timing
        mock_time.side_effect = [1000.0, 1045.2]  # 45.2 seconds elapsed

        # Mock Azure CLI responses
        def run_side_effect(cmd, *args, **kwargs):
            if "disk" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-disk", "diskSizeGb": 128, "provisioningState": "Succeeded"}',
                    stderr="",
                )
            elif "disk" in cmd and "show" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"diskSizeGb": 128, "diskState": "Attached"}',
                    stderr="",
                )
            elif "disk" in cmd and "delete" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=0, stdout="{}", stderr="")

        mock_run.side_effect = run_side_effect

        result = manager.verify_backup(
            snapshot_name="vm1-backup-daily-20251201-100000",
            resource_group="test-rg",
        )

        assert result.success is True
        assert result.disk_readable is True
        assert result.size_matches is True
        assert result.test_disk_created is True
        assert result.test_disk_deleted is True
        assert result.verification_time_seconds == 45.2

    @patch("subprocess.run")
    def test_verify_backup_disk_creation_fails(self, mock_run, tmp_path):
        """Test verification failure when test disk creation fails."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        # Mock disk creation failure
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="QuotaExceeded: Disk quota exceeded",
        )

        result = manager.verify_backup(
            snapshot_name="vm1-backup-daily-20251201-100000",
            resource_group="test-rg",
        )

        assert result.success is False
        assert result.test_disk_created is False
        assert "QuotaExceeded" in result.error_message

    @patch("subprocess.run")
    def test_verify_backup_disk_not_readable(self, mock_run, tmp_path):
        """Test verification failure when test disk is not readable."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        def run_side_effect(cmd, *args, **kwargs):
            if "disk" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-disk", "provisioningState": "Succeeded"}',
                    stderr="",
                )
            elif "disk" in cmd and "show" in cmd:
                return Mock(
                    returncode=1,
                    stdout="",
                    stderr="DiskNotAccessible",
                )
            elif "disk" in cmd and "delete" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=0, stdout="{}", stderr="")

        mock_run.side_effect = run_side_effect

        result = manager.verify_backup(
            snapshot_name="vm1-backup-daily-20251201-100000",
            resource_group="test-rg",
        )

        assert result.success is False
        assert result.test_disk_created is True
        assert result.disk_readable is False
        assert result.test_disk_deleted is True

    @patch("subprocess.run")
    def test_verify_backup_size_mismatch(self, mock_run, tmp_path):
        """Test verification failure when disk size doesn't match."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        def run_side_effect(cmd, *args, **kwargs):
            if "disk" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-disk", "diskSizeGb": 128}',
                    stderr="",
                )
            elif "disk" in cmd and "show" in cmd:
                # Return wrong size
                return Mock(
                    returncode=0,
                    stdout='{"diskSizeGb": 64, "diskState": "Attached"}',
                    stderr="",
                )
            elif "disk" in cmd and "delete" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=0, stdout="{}", stderr="")

        mock_run.side_effect = run_side_effect

        result = manager.verify_backup(
            snapshot_name="vm1-backup-daily-20251201-100000",
            resource_group="test-rg",
        )

        assert result.success is False
        assert result.size_matches is False

    @patch("subprocess.run")
    def test_verify_backup_cleanup_failure(self, mock_run, tmp_path):
        """Test verification when test disk cleanup fails."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        def run_side_effect(cmd, *args, **kwargs):
            if "disk" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-disk", "diskSizeGb": 128}',
                    stderr="",
                )
            elif "disk" in cmd and "show" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"diskSizeGb": 128, "diskState": "Attached"}',
                    stderr="",
                )
            elif "disk" in cmd and "delete" in cmd:
                return Mock(
                    returncode=1,
                    stdout="",
                    stderr="ResourceInUse",
                )
            return Mock(returncode=0, stdout="{}", stderr="")

        mock_run.side_effect = run_side_effect

        result = manager.verify_backup(
            snapshot_name="vm1-backup-daily-20251201-100000",
            resource_group="test-rg",
        )

        # Verification passes but cleanup failed
        assert result.success is True  # Backup itself is valid
        assert result.test_disk_deleted is False


class TestVerifyAllBackups:
    """Test parallel verification of multiple backups."""

    @patch("azlin.modules.backup_verification.BackupManager.list_backups")
    @patch("azlin.modules.backup_verification.VerificationManager.verify_backup")
    def test_verify_all_backups_success(self, mock_verify, mock_list, tmp_path):
        """Test successful parallel verification of all backups."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        # Mock 3 unverified backups
        from azlin.modules.backup_manager import BackupInfo

        backups = [
            BackupInfo(
                snapshot_name=f"vm1-backup-daily-{i}",
                vm_name="test-vm",
                resource_group="test-rg",
                creation_time=datetime.now(UTC),
                retention_tier="daily",
                verified=False,
            )
            for i in range(3)
        ]
        mock_list.return_value = backups

        # Mock successful verification
        mock_verify.return_value = Mock(
            success=True,
            disk_readable=True,
            size_matches=True,
            test_disk_created=True,
            test_disk_deleted=True,
        )

        results = manager.verify_all_backups(
            vm_name="test-vm",
            resource_group="test-rg",
        )

        assert len(results) == 3
        assert all(r.success for r in results)
        assert mock_verify.call_count == 3

    @patch("azlin.modules.backup_verification.BackupManager.list_backups")
    def test_verify_all_backups_no_backups(self, mock_list, tmp_path):
        """Test verification when no backups exist."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        mock_list.return_value = []

        results = manager.verify_all_backups(
            vm_name="test-vm",
            resource_group="test-rg",
        )

        assert results == []

    @patch("azlin.modules.backup_verification.BackupManager.list_backups")
    @patch("azlin.modules.backup_verification.VerificationManager.verify_backup")
    def test_verify_all_backups_partial_failure(self, mock_verify, mock_list, tmp_path):
        """Test parallel verification with some failures."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        from azlin.modules.backup_manager import BackupInfo

        backups = [
            BackupInfo(
                snapshot_name=f"vm1-backup-daily-{i}",
                vm_name="test-vm",
                resource_group="test-rg",
                creation_time=datetime.now(UTC),
                retention_tier="daily",
                verified=False,
            )
            for i in range(3)
        ]
        mock_list.return_value = backups

        # First succeeds, second fails, third succeeds
        mock_verify.side_effect = [
            Mock(success=True, disk_readable=True),
            Mock(success=False, disk_readable=False),
            Mock(success=True, disk_readable=True),
        ]

        results = manager.verify_all_backups(
            vm_name="test-vm",
            resource_group="test-rg",
        )

        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True

    @patch("azlin.modules.backup_verification.BackupManager.list_backups")
    @patch("azlin.modules.backup_verification.VerificationManager.verify_backup")
    def test_verify_all_backups_respects_max_parallel(self, mock_verify, mock_list, tmp_path):
        """Test parallel verification respects max_parallel limit."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        from azlin.modules.backup_manager import BackupInfo

        backups = [
            BackupInfo(
                snapshot_name=f"vm1-backup-daily-{i}",
                vm_name="test-vm",
                resource_group="test-rg",
                creation_time=datetime.now(UTC),
                retention_tier="daily",
                verified=False,
            )
            for i in range(10)
        ]
        mock_list.return_value = backups

        mock_verify.return_value = Mock(success=True)

        results = manager.verify_all_backups(
            vm_name="test-vm",
            resource_group="test-rg",
            max_parallel=2,
        )

        # Should process all 10 backups in batches of 2
        assert len(results) == 10


class TestGetVerificationReport:
    """Test verification report generation."""

    def test_get_verification_report_all_success(self, tmp_path):
        """Test report when all verifications succeeded."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        # Create verification records
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        now = datetime.now(UTC)
        for i in range(10):
            verified_at = (now - timedelta(days=i)).isoformat()
            cursor.execute(
                """
                INSERT INTO verifications
                (backup_name, vm_name, verified_at, success, disk_readable,
                 size_matches, test_disk_created, test_disk_deleted, verification_time_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"vm1-backup-{i}",
                    "test-vm",
                    verified_at,
                    True,
                    True,
                    True,
                    True,
                    True,
                    45.2,
                ),
            )
        conn.commit()
        conn.close()

        report = manager.get_verification_report(vm_name="test-vm", days=7)

        assert report["total_verified"] == 7  # Last 7 days
        assert report["success_rate"] == 1.0  # 100%
        assert report["failures"] == []
        assert report["last_verified"] is not None

    def test_get_verification_report_with_failures(self, tmp_path):
        """Test report with some failed verifications."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        # Create mixed verification records
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        now = datetime.now(UTC).isoformat()
        # 7 successful, 3 failed
        for i in range(10):
            success = i < 7
            cursor.execute(
                """
                INSERT INTO verifications
                (backup_name, vm_name, verified_at, success, disk_readable,
                 size_matches, test_disk_created, test_disk_deleted,
                 error_message, verification_time_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"vm1-backup-{i}",
                    "test-vm",
                    now,
                    success,
                    success,
                    success,
                    True,
                    True,
                    None if success else "Disk not readable",
                    45.2,
                ),
            )
        conn.commit()
        conn.close()

        report = manager.get_verification_report(vm_name="test-vm", days=7)

        assert report["total_verified"] == 10
        assert report["success_rate"] == 0.7  # 70%
        assert len(report["failures"]) == 3

    def test_get_verification_report_no_data(self, tmp_path):
        """Test report with no verification data."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        report = manager.get_verification_report(days=7)

        assert report["total_verified"] == 0
        assert report["success_rate"] == 0.0
        assert report["failures"] == []
        assert report["last_verified"] is None

    def test_get_verification_report_filter_by_vm(self, tmp_path):
        """Test report filtering by VM name."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        # Create verifications for different VMs
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        now = datetime.now(UTC).isoformat()
        for vm in ["vm1", "vm2"]:
            for i in range(5):
                cursor.execute(
                    """
                    INSERT INTO verifications
                    (backup_name, vm_name, verified_at, success, disk_readable,
                     size_matches, test_disk_created, test_disk_deleted, verification_time_seconds)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (f"{vm}-backup-{i}", vm, now, True, True, True, True, True, 45.2),
                )
        conn.commit()
        conn.close()

        report = manager.get_verification_report(vm_name="vm1", days=7)

        assert report["total_verified"] == 5


# ============================================================================
# BOUNDARY TESTS (Part of Unit Tests)
# ============================================================================


class TestBoundaryConditions:
    """Test edge cases and boundary conditions."""

    @patch("subprocess.run")
    def test_verify_backup_empty_snapshot_name(self, mock_run, tmp_path):
        """Test error for empty snapshot name."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        with pytest.raises(VerificationError, match="Invalid snapshot name"):
            manager.verify_backup(
                snapshot_name="",
                resource_group="test-rg",
            )

    @patch("subprocess.run")
    def test_verify_backup_empty_resource_group(self, mock_run, tmp_path):
        """Test error for empty resource group."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        with pytest.raises(VerificationError, match="Invalid resource group"):
            manager.verify_backup(
                snapshot_name="vm1-backup-daily-20251201-100000",
                resource_group="",
            )

    def test_verify_all_backups_max_parallel_zero(self, tmp_path):
        """Test error for zero max_parallel value."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        with pytest.raises(VerificationError, match="max_parallel must be positive"):
            manager.verify_all_backups(
                vm_name="test-vm",
                resource_group="test-rg",
                max_parallel=0,
            )

    def test_get_verification_report_zero_days(self, tmp_path):
        """Test error for zero days value."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        with pytest.raises(VerificationError, match="days must be positive"):
            manager.get_verification_report(days=0)

    def test_get_verification_report_negative_days(self, tmp_path):
        """Test error for negative days value."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        with pytest.raises(VerificationError, match="days must be positive"):
            manager.get_verification_report(days=-1)

    @patch("subprocess.run")
    @patch("time.time")
    def test_verify_backup_very_slow(self, mock_time, mock_run, tmp_path):
        """Test verification timing for extremely slow operations."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        # Mock 15 minutes (900 seconds) elapsed
        mock_time.side_effect = [1000.0, 1900.0]

        def run_side_effect(cmd, *args, **kwargs):
            if "disk" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-disk", "diskSizeGb": 128}',
                    stderr="",
                )
            elif "disk" in cmd and "show" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"diskSizeGb": 128, "diskState": "Attached"}',
                    stderr="",
                )
            elif "disk" in cmd and "delete" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=0, stdout="{}", stderr="")

        mock_run.side_effect = run_side_effect

        result = manager.verify_backup(
            snapshot_name="vm1-backup-daily-20251201-100000",
            resource_group="test-rg",
        )

        assert result.success is True
        assert result.verification_time_seconds == 900.0


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

        with pytest.raises(VerificationError, match="Cannot write to database"):
            VerificationManager(storage_path=db_path)

    @patch("subprocess.run")
    def test_verify_backup_azure_cli_not_found(self, mock_run, tmp_path):
        """Test error when Azure CLI is not available."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        mock_run.side_effect = FileNotFoundError("az command not found")

        with pytest.raises(VerificationError, match="Azure CLI not found"):
            manager.verify_backup(
                snapshot_name="vm1-backup-daily-20251201-100000",
                resource_group="test-rg",
            )

    @patch("subprocess.run")
    def test_verify_backup_timeout(self, mock_run, tmp_path):
        """Test handling of verification timeout."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        mock_run.side_effect = TimeoutError("Disk creation timed out")

        result = manager.verify_backup(
            snapshot_name="vm1-backup-daily-20251201-100000",
            resource_group="test-rg",
        )

        assert result.success is False
        assert "timed out" in result.error_message.lower()

    def test_get_verification_report_database_corruption(self, tmp_path):
        """Test error handling for corrupted database."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        # Corrupt the database
        with open(db_path, "wb") as f:
            f.write(b"corrupted data")

        with pytest.raises(VerificationError, match="Database error"):
            manager.get_verification_report(days=7)

    @patch("azlin.modules.backup_verification.BackupManager.list_backups")
    def test_verify_all_backups_list_backups_fails(self, mock_list, tmp_path):
        """Test error handling when listing backups fails."""
        db_path = tmp_path / "verification.db"
        manager = VerificationManager(storage_path=db_path)

        mock_list.side_effect = Exception("Azure API error")

        with pytest.raises(VerificationError, match="Failed to list backups"):
            manager.verify_all_backups(
                vm_name="test-vm",
                resource_group="test-rg",
            )
