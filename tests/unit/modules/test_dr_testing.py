"""Unit tests for DRTestManager module.

Tests for disaster recovery testing automation.

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

from azlin.modules.dr_testing import (
    DRTestConfig,
    DRTestError,
    DRTestManager,
    DRTestResult,
)


# ============================================================================
# UNIT TESTS (60% of test suite)
# ============================================================================


class TestDRTestConfigDataclass:
    """Test DRTestConfig dataclass structure."""

    def test_dr_test_config_defaults(self):
        """Test DRTestConfig with default values."""
        config = DRTestConfig(
            vm_name="test-vm",
            backup_name="vm1-backup-daily-20251201-100000",
            source_resource_group="test-rg",
            test_region="westus2",
            test_resource_group="test-rg-dr",
        )

        assert config.vm_name == "test-vm"
        assert config.backup_name == "vm1-backup-daily-20251201-100000"
        assert config.source_resource_group == "test-rg"
        assert config.test_region == "westus2"
        assert config.test_resource_group == "test-rg-dr"
        assert config.verify_boot is True
        assert config.verify_connectivity is True
        assert config.cleanup_after_test is True

    def test_dr_test_config_custom_verification(self):
        """Test DRTestConfig with custom verification settings."""
        config = DRTestConfig(
            vm_name="test-vm",
            backup_name="vm1-backup-daily-20251201-100000",
            source_resource_group="test-rg",
            test_region="westus2",
            test_resource_group="test-rg-dr",
            verify_boot=False,
            verify_connectivity=False,
            cleanup_after_test=False,
        )

        assert config.verify_boot is False
        assert config.verify_connectivity is False
        assert config.cleanup_after_test is False


class TestDRTestResultDataclass:
    """Test DRTestResult dataclass structure."""

    def test_dr_test_result_success(self):
        """Test DRTestResult for successful DR test."""
        now = datetime.now(UTC)
        result = DRTestResult(
            test_id=1,
            vm_name="test-vm",
            backup_name="vm1-backup-daily-20251201-100000",
            test_region="westus2",
            started_at=now,
            completed_at=now,
            success=True,
            restore_succeeded=True,
            boot_succeeded=True,
            connectivity_succeeded=True,
            cleanup_succeeded=True,
            rto_seconds=720.5,  # 12 minutes
            error_message=None,
        )

        assert result.success is True
        assert result.restore_succeeded is True
        assert result.boot_succeeded is True
        assert result.connectivity_succeeded is True
        assert result.cleanup_succeeded is True
        assert result.rto_seconds == 720.5
        assert result.error_message is None

    def test_dr_test_result_failure(self):
        """Test DRTestResult for failed DR test."""
        now = datetime.now(UTC)
        result = DRTestResult(
            test_id=1,
            vm_name="test-vm",
            backup_name="vm1-backup-daily-20251201-100000",
            test_region="westus2",
            started_at=now,
            completed_at=now,
            success=False,
            restore_succeeded=True,
            boot_succeeded=False,
            connectivity_succeeded=False,
            cleanup_succeeded=True,
            rto_seconds=None,
            error_message="VM failed to boot",
        )

        assert result.success is False
        assert result.boot_succeeded is False
        assert result.connectivity_succeeded is False
        assert result.error_message == "VM failed to boot"


class TestDRTestManagerInit:
    """Test DRTestManager initialization."""

    def test_init_creates_database(self, tmp_path):
        """Test initialization creates SQLite database."""
        db_path = tmp_path / "dr_tests.db"

        manager = DRTestManager(storage_path=db_path)

        assert db_path.exists()
        # Verify tables exist
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='dr_tests'"
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None

    def test_init_creates_indexes(self, tmp_path):
        """Test initialization creates database indexes."""
        db_path = tmp_path / "dr_tests.db"

        manager = DRTestManager(storage_path=db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "idx_vm_name_test" in indexes
        assert "idx_started_at" in indexes
        assert "idx_success_test" in indexes


class TestRunDRTest:
    """Test DR test execution."""

    @patch("subprocess.run")
    @patch("time.time")
    def test_run_dr_test_success(self, mock_time, mock_run, tmp_path):
        """Test successful DR test execution."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        # Mock RTO timing - 10 minutes
        # Create an iterator that alternates between start time and end time
        time_values = iter([1000.0, 1600.0] + [1600.0] * 100)  # Provide many values for logger calls
        mock_time.side_effect = lambda: next(time_values)

        # Mock Azure CLI responses for full restore workflow
        def run_side_effect(cmd, *args, **kwargs):
            if "disk" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-disk"}',
                    stderr="",
                )
            elif "vm" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-vm"}',
                    stderr="",
                )
            elif "vm" in cmd and "show" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"provisioningState": "Succeeded", "powerState": "VM running"}',
                    stderr="",
                )
            elif "ssh" in cmd:  # SSH connectivity test
                return Mock(returncode=0, stdout="", stderr="")
            elif "delete" in cmd:  # Cleanup
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=0, stdout="{}", stderr="")

        mock_run.side_effect = run_side_effect

        config = DRTestConfig(
            vm_name="test-vm",
            backup_name="vm1-backup-daily-20251201-100000",
            source_resource_group="test-rg",
            test_region="westus2",
            test_resource_group="test-rg-dr",
        )

        result = manager.run_dr_test(config)

        assert result.success is True
        assert result.restore_succeeded is True
        assert result.boot_succeeded is True
        assert result.connectivity_succeeded is True
        assert result.cleanup_succeeded is True
        assert result.rto_seconds == 600.0
        assert result.rto_seconds < 900  # Under 15-minute target

    @patch("subprocess.run")
    def test_run_dr_test_restore_failure(self, mock_run, tmp_path):
        """Test DR test failure during restore."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        # Mock restore failure
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="QuotaExceeded: VM quota exceeded in test region",
        )

        config = DRTestConfig(
            vm_name="test-vm",
            backup_name="vm1-backup-daily-20251201-100000",
            source_resource_group="test-rg",
            test_region="westus2",
            test_resource_group="test-rg-dr",
        )

        result = manager.run_dr_test(config)

        assert result.success is False
        assert result.restore_succeeded is False
        assert "QuotaExceeded" in result.error_message

    @patch("subprocess.run")
    @patch("time.time")
    def test_run_dr_test_boot_failure(self, mock_time, mock_run, tmp_path):
        """Test DR test failure when VM doesn't boot."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        time_values = iter([1000.0, 1600.0] + [1600.0] * 100)
        mock_time.side_effect = lambda: next(time_values)

        def run_side_effect(cmd, *args, **kwargs):
            if "disk" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-disk"}',
                    stderr="",
                )
            elif "vm" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-vm"}',
                    stderr="",
                )
            elif "vm" in cmd and "show" in cmd:
                # VM stuck in "Creating" state
                return Mock(
                    returncode=0,
                    stdout='{"provisioningState": "Creating", "powerState": "VM stopped"}',
                    stderr="",
                )
            elif "delete" in cmd:  # Cleanup
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=0, stdout="{}", stderr="")

        mock_run.side_effect = run_side_effect

        config = DRTestConfig(
            vm_name="test-vm",
            backup_name="vm1-backup-daily-20251201-100000",
            source_resource_group="test-rg",
            test_region="westus2",
            test_resource_group="test-rg-dr",
        )

        result = manager.run_dr_test(config)

        assert result.success is False
        assert result.restore_succeeded is True
        assert result.boot_succeeded is False
        assert result.cleanup_succeeded is True

    @patch("subprocess.run")
    @patch("time.time")
    def test_run_dr_test_connectivity_failure(self, mock_time, mock_run, tmp_path):
        """Test DR test failure when SSH connectivity fails."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        time_values = iter([1000.0, 1600.0] + [1600.0] * 100)
        mock_time.side_effect = lambda: next(time_values)

        def run_side_effect(cmd, *args, **kwargs):
            if "disk" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-disk"}',
                    stderr="",
                )
            elif "vm" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-vm"}',
                    stderr="",
                )
            elif "vm" in cmd and "show" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"provisioningState": "Succeeded", "powerState": "VM running"}',
                    stderr="",
                )
            elif "ssh" in cmd:  # SSH connectivity test fails
                return Mock(
                    returncode=255,
                    stdout="",
                    stderr="Connection refused",
                )
            elif "delete" in cmd:  # Cleanup
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=0, stdout="{}", stderr="")

        mock_run.side_effect = run_side_effect

        config = DRTestConfig(
            vm_name="test-vm",
            backup_name="vm1-backup-daily-20251201-100000",
            source_resource_group="test-rg",
            test_region="westus2",
            test_resource_group="test-rg-dr",
        )

        result = manager.run_dr_test(config)

        assert result.success is False
        assert result.restore_succeeded is True
        assert result.boot_succeeded is True
        assert result.connectivity_succeeded is False

    @patch("subprocess.run")
    @patch("time.time")
    def test_run_dr_test_skip_verification(self, mock_time, mock_run, tmp_path):
        """Test DR test with verification disabled."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        time_values = iter([1000.0, 1600.0] + [1600.0] * 100)
        mock_time.side_effect = lambda: next(time_values)

        def run_side_effect(cmd, *args, **kwargs):
            if "disk" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-disk"}',
                    stderr="",
                )
            elif "vm" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-vm"}',
                    stderr="",
                )
            elif "delete" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=0, stdout="{}", stderr="")

        mock_run.side_effect = run_side_effect

        config = DRTestConfig(
            vm_name="test-vm",
            backup_name="vm1-backup-daily-20251201-100000",
            source_resource_group="test-rg",
            test_region="westus2",
            test_resource_group="test-rg-dr",
            verify_boot=False,
            verify_connectivity=False,
        )

        result = manager.run_dr_test(config)

        assert result.success is True
        assert result.restore_succeeded is True
        # Boot and connectivity not verified (skipped)
        assert result.boot_succeeded is False
        assert result.connectivity_succeeded is False

    @patch("subprocess.run")
    @patch("time.time")
    def test_run_dr_test_cleanup_failure(self, mock_time, mock_run, tmp_path):
        """Test DR test when cleanup fails."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        time_values = iter([1000.0, 1600.0] + [1600.0] * 100)
        mock_time.side_effect = lambda: next(time_values)

        def run_side_effect(cmd, *args, **kwargs):
            if "disk" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-disk"}',
                    stderr="",
                )
            elif "vm" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-vm"}',
                    stderr="",
                )
            elif "vm" in cmd and "show" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"provisioningState": "Succeeded", "powerState": "VM running"}',
                    stderr="",
                )
            elif "ssh" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            elif "delete" in cmd:  # Cleanup fails
                return Mock(
                    returncode=1,
                    stdout="",
                    stderr="ResourceInUse",
                )
            return Mock(returncode=0, stdout="{}", stderr="")

        mock_run.side_effect = run_side_effect

        config = DRTestConfig(
            vm_name="test-vm",
            backup_name="vm1-backup-daily-20251201-100000",
            source_resource_group="test-rg",
            test_region="westus2",
            test_resource_group="test-rg-dr",
        )

        result = manager.run_dr_test(config)

        # Test passed but cleanup failed
        assert result.success is True
        assert result.restore_succeeded is True
        assert result.boot_succeeded is True
        assert result.connectivity_succeeded is True
        assert result.cleanup_succeeded is False

    @patch("subprocess.run")
    @patch("time.time")
    def test_run_dr_test_exceeds_rto_target(self, mock_time, mock_run, tmp_path):
        """Test DR test that exceeds RTO target."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        # Mock 20 minutes (1200 seconds) - exceeds 15-minute target
        time_values = iter([1000.0, 2200.0] + [2200.0] * 100)
        mock_time.side_effect = lambda: next(time_values)

        def run_side_effect(cmd, *args, **kwargs):
            if "disk" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-disk"}',
                    stderr="",
                )
            elif "vm" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-vm"}',
                    stderr="",
                )
            elif "vm" in cmd and "show" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"provisioningState": "Succeeded", "powerState": "VM running"}',
                    stderr="",
                )
            elif "ssh" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            elif "delete" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=0, stdout="{}", stderr="")

        mock_run.side_effect = run_side_effect

        config = DRTestConfig(
            vm_name="test-vm",
            backup_name="vm1-backup-daily-20251201-100000",
            source_resource_group="test-rg",
            test_region="westus2",
            test_resource_group="test-rg-dr",
        )

        result = manager.run_dr_test(config)

        assert result.success is True
        assert result.rto_seconds == 1200.0
        assert result.rto_seconds > 900  # Exceeds 15-minute target


class TestRunScheduledTests:
    """Test scheduled DR test execution."""

    @patch("azlin.modules.dr_testing.BackupManager.list_backups")
    @patch("azlin.modules.dr_testing.DRTestManager.run_dr_test")
    def test_run_scheduled_tests_success(self, mock_run_test, mock_list, tmp_path):
        """Test running scheduled DR tests for all VMs."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        # Mock backups from different VMs
        from azlin.modules.backup_manager import BackupInfo

        backups = [
            BackupInfo(
                snapshot_name=f"vm{i}-backup-daily-20251201-100000",
                vm_name=f"vm{i}",
                resource_group="test-rg",
                creation_time=datetime.now(UTC),
                retention_tier="daily",
            )
            for i in range(3)
        ]
        mock_list.return_value = backups

        # Mock successful DR tests
        mock_run_test.return_value = Mock(
            success=True,
            restore_succeeded=True,
            boot_succeeded=True,
            connectivity_succeeded=True,
        )

        results = manager.run_scheduled_tests(resource_group="test-rg")

        assert len(results) == 3
        assert all(r.success for r in results)

    @patch("azlin.modules.dr_testing.BackupManager.list_backups")
    def test_run_scheduled_tests_no_backups(self, mock_list, tmp_path):
        """Test scheduled tests when no backups exist."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        mock_list.return_value = []

        results = manager.run_scheduled_tests(resource_group="test-rg")

        assert results == []


class TestGetTestHistory:
    """Test DR test history retrieval."""

    def test_get_test_history_all(self, tmp_path):
        """Test retrieving all DR test history."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        # Create test records
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        now = datetime.now(UTC).isoformat()
        for i in range(5):
            cursor.execute(
                """
                INSERT INTO dr_tests
                (vm_name, backup_name, test_region, started_at, completed_at,
                 success, restore_succeeded, boot_succeeded, connectivity_succeeded,
                 cleanup_succeeded, rto_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"vm{i}",
                    f"vm{i}-backup-daily-20251201-100000",
                    "westus2",
                    now,
                    now,
                    True,
                    True,
                    True,
                    True,
                    True,
                    600.0,
                ),
            )
        conn.commit()
        conn.close()

        history = manager.get_test_history()

        assert len(history) == 5

    def test_get_test_history_filter_by_vm(self, tmp_path):
        """Test filtering test history by VM name."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        # Create test records for different VMs
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        now = datetime.now(UTC).isoformat()
        for vm in ["vm1", "vm2"]:
            for i in range(3):
                cursor.execute(
                    """
                    INSERT INTO dr_tests
                    (vm_name, backup_name, test_region, started_at, completed_at,
                     success, restore_succeeded, boot_succeeded, connectivity_succeeded,
                     cleanup_succeeded, rto_seconds)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        vm,
                        f"{vm}-backup-{i}",
                        "westus2",
                        now,
                        now,
                        True,
                        True,
                        True,
                        True,
                        True,
                        600.0,
                    ),
                )
        conn.commit()
        conn.close()

        history = manager.get_test_history(vm_name="vm1")

        assert len(history) == 3
        assert all(h.vm_name == "vm1" for h in history)


class TestGetSuccessRate:
    """Test DR test success rate calculation."""

    def test_get_success_rate_100_percent(self, tmp_path):
        """Test success rate calculation with all successful tests."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        # Create all successful test records
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        now = datetime.now(UTC).isoformat()
        for i in range(10):
            cursor.execute(
                """
                INSERT INTO dr_tests
                (vm_name, backup_name, test_region, started_at, completed_at,
                 success, restore_succeeded, boot_succeeded, connectivity_succeeded,
                 cleanup_succeeded, rto_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "test-vm",
                    f"backup-{i}",
                    "westus2",
                    now,
                    now,
                    True,
                    True,
                    True,
                    True,
                    True,
                    600.0,
                ),
            )
        conn.commit()
        conn.close()

        success_rate = manager.get_success_rate(vm_name="test-vm", days=30)

        assert success_rate == 1.0  # 100%

    def test_get_success_rate_partial(self, tmp_path):
        """Test success rate calculation with some failures."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        # Create mixed test records (70% success)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        now = datetime.now(UTC).isoformat()
        for i in range(10):
            success = i < 7  # First 7 succeed, last 3 fail
            cursor.execute(
                """
                INSERT INTO dr_tests
                (vm_name, backup_name, test_region, started_at, completed_at,
                 success, restore_succeeded, boot_succeeded, connectivity_succeeded,
                 cleanup_succeeded, rto_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "test-vm",
                    f"backup-{i}",
                    "westus2",
                    now,
                    now,
                    success,
                    True,
                    success,
                    success,
                    True,
                    600.0 if success else None,
                ),
            )
        conn.commit()
        conn.close()

        success_rate = manager.get_success_rate(vm_name="test-vm", days=30)

        assert success_rate == 0.7  # 70%

    def test_get_success_rate_no_tests(self, tmp_path):
        """Test success rate when no tests exist."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        success_rate = manager.get_success_rate(days=30)

        assert success_rate == 0.0


# ============================================================================
# BOUNDARY TESTS (Part of Unit Tests)
# ============================================================================


class TestBoundaryConditions:
    """Test edge cases and boundary conditions."""

    def test_run_dr_test_empty_vm_name(self, tmp_path):
        """Test error for empty VM name."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        config = DRTestConfig(
            vm_name="",
            backup_name="vm1-backup-daily-20251201-100000",
            source_resource_group="test-rg",
            test_region="westus2",
            test_resource_group="test-rg-dr",
        )

        with pytest.raises(DRTestError, match="Invalid VM name"):
            manager.run_dr_test(config)

    def test_run_dr_test_empty_backup_name(self, tmp_path):
        """Test error for empty backup name."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        config = DRTestConfig(
            vm_name="test-vm",
            backup_name="",
            source_resource_group="test-rg",
            test_region="westus2",
            test_resource_group="test-rg-dr",
        )

        with pytest.raises(DRTestError, match="Invalid backup name"):
            manager.run_dr_test(config)

    def test_get_test_history_zero_days(self, tmp_path):
        """Test error for zero days value."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        with pytest.raises(DRTestError, match="days must be positive"):
            manager.get_test_history(days=0)

    def test_get_success_rate_zero_days(self, tmp_path):
        """Test error for zero days value."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        with pytest.raises(DRTestError, match="days must be positive"):
            manager.get_success_rate(days=0)


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

        with pytest.raises(DRTestError, match="Cannot write to database"):
            DRTestManager(storage_path=db_path)

    @patch("subprocess.run")
    def test_run_dr_test_azure_cli_not_found(self, mock_run, tmp_path):
        """Test error when Azure CLI is not available."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        mock_run.side_effect = FileNotFoundError("az command not found")

        config = DRTestConfig(
            vm_name="test-vm",
            backup_name="vm1-backup-daily-20251201-100000",
            source_resource_group="test-rg",
            test_region="westus2",
            test_resource_group="test-rg-dr",
        )

        with pytest.raises(DRTestError, match="Azure CLI not found"):
            manager.run_dr_test(config)

    def test_get_test_history_database_corruption(self, tmp_path):
        """Test error handling for corrupted database."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        # Corrupt the database
        with open(db_path, "wb") as f:
            f.write(b"corrupted data")

        with pytest.raises(DRTestError, match="Database error"):
            manager.get_test_history(days=30)

    @patch("azlin.modules.dr_testing.BackupManager.list_backups")
    def test_run_scheduled_tests_list_backups_fails(self, mock_list, tmp_path):
        """Test error handling when listing backups fails."""
        db_path = tmp_path / "dr_tests.db"
        manager = DRTestManager(storage_path=db_path)

        mock_list.side_effect = Exception("Azure API error")

        with pytest.raises(DRTestError, match="Failed to list backups"):
            manager.run_scheduled_tests(resource_group="test-rg")
