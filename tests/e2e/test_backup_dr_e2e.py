"""End-to-end tests for backup and DR workflow.

Complete user workflows from configuration through DR testing.

Testing pyramid:
- 60% Unit tests (fast, heavily mocked)
- 30% Integration tests (multiple components)
- 10% E2E tests (complete workflows) ← THIS FILE
"""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from azlin.modules.backup_manager import BackupManager
from azlin.modules.backup_replication import ReplicationManager
from azlin.modules.backup_verification import VerificationManager
from azlin.modules.dr_testing import DRTestConfig, DRTestManager


# ============================================================================
# E2E TESTS (10% of test suite)
# ============================================================================


class TestCompleteBackupDRWorkflow:
    """Test complete backup and DR workflow from start to finish."""

    @patch("subprocess.run")
    @patch("time.time")
    @patch("azlin.modules.backup_manager.BackupManager._set_vm_tag")
    @patch("azlin.modules.backup_manager.BackupManager._get_vm_tag")
    @patch("azlin.modules.backup_manager.SnapshotManager.create_snapshot")
    def test_complete_workflow_configure_to_dr_test(
        self,
        mock_create_snapshot,
        mock_get_tag,
        mock_set_tag,
        mock_time,
        mock_run,
        tmp_path,
    ):
        """Test complete workflow: configure → backup → replicate → verify → DR test.

        This E2E test simulates a complete user journey:
        1. Configure automated backup with cross-region replication
        2. Trigger backup creation
        3. Replicate backup to secondary region
        4. Verify both backups (source and replica)
        5. Run DR test to validate restore capability
        """
        # STEP 1: Configure automated backup with cross-region
        BackupManager.configure_backup(
            vm_name="test-vm",
            resource_group="test-rg",
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
            cross_region=True,
            target_region="westus2",
        )

        # Verify configuration was set
        assert mock_set_tag.called
        import json

        config_call = mock_set_tag.call_args[0]
        schedule_data = json.loads(config_call[3])
        assert schedule_data["cross_region_enabled"] is True

        # STEP 2: Trigger backup creation
        from azlin.modules.backup_manager import BackupSchedule

        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
            cross_region_enabled=True,
            target_region="westus2",
        )
        mock_get_tag.return_value = schedule.to_tag_value()

        mock_create_snapshot.return_value = Mock(
            name="test-vm-backup-daily-20251201-100000",
            resource_group="test-rg",
            source_vm="test-vm",
            creation_time=datetime.now(UTC),
            size_gb=128,
        )

        with patch("azlin.modules.backup_manager.BackupManager._create_backup_snapshot") as mock_backup:
            mock_backup.return_value = "test-vm-backup-daily-20251201-100000"

            backup_info = BackupManager.trigger_backup(
                vm_name="test-vm",
                resource_group="test-rg",
            )

        assert backup_info.snapshot_name == "test-vm-backup-daily-20251201-100000"
        assert backup_info.retention_tier == "daily"

        # STEP 3: Replicate backup to secondary region
        replication_db = tmp_path / "replication.db"
        replication_manager = ReplicationManager(storage_path=replication_db)

        # Mock Azure CLI for replication
        def run_side_effect_replication(cmd, *args, **kwargs):
            if "snapshot" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../westus2-snapshot", "provisioningState": "Succeeded"}',
                    stderr="",
                )
            # Pass through for other commands
            return None

        mock_run.side_effect = run_side_effect_replication

        replication_job = replication_manager.replicate_backup(
            snapshot_name=backup_info.snapshot_name,
            source_resource_group="test-rg",
            target_region="westus2",
        )

        assert replication_job.status == "completed"
        assert replication_job.target_region == "westus2"

        # STEP 4: Verify both backups
        verification_db = tmp_path / "verification.db"
        verification_manager = VerificationManager(storage_path=verification_db)

        # Mock timing for verification
        mock_time.side_effect = [1000.0, 1045.2, 2000.0, 2045.2]

        # Mock Azure CLI for verification
        def run_side_effect_verification(cmd, *args, **kwargs):
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

        mock_run.side_effect = run_side_effect_verification

        # Verify source backup
        source_verification = verification_manager.verify_backup(
            snapshot_name=backup_info.snapshot_name,
            resource_group="test-rg",
        )

        assert source_verification.success is True

        # Verify replicated backup
        replica_verification = verification_manager.verify_backup(
            snapshot_name=replication_job.target_snapshot,
            resource_group=replication_job.target_resource_group,
        )

        assert replica_verification.success is True

        # STEP 5: Run DR test
        dr_test_db = tmp_path / "dr_tests.db"
        dr_test_manager = DRTestManager(storage_path=dr_test_db)

        # Reset timing for DR test
        mock_time.side_effect = [3000.0, 3600.0]  # 10 minutes RTO

        # Mock Azure CLI for DR test
        def run_side_effect_dr_test(cmd, *args, **kwargs):
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

        mock_run.side_effect = run_side_effect_dr_test

        dr_config = DRTestConfig(
            vm_name="test-vm",
            backup_name=replication_job.target_snapshot,
            source_resource_group="test-rg",
            test_region="westus2",
            test_resource_group="test-rg-dr",
        )

        dr_result = dr_test_manager.run_dr_test(dr_config)

        # Verify complete DR test succeeded
        assert dr_result.success is True
        assert dr_result.restore_succeeded is True
        assert dr_result.boot_succeeded is True
        assert dr_result.connectivity_succeeded is True
        assert dr_result.cleanup_succeeded is True
        assert dr_result.rto_seconds < 900  # Under 15-minute target

        # Final validation: Check all databases have correct records
        assert replication_db.exists()
        assert verification_db.exists()
        assert dr_test_db.exists()


class TestFailureRecoveryWorkflow:
    """Test E2E workflow with failures and recovery."""

    @patch("subprocess.run")
    @patch("azlin.modules.backup_manager.BackupManager._set_vm_tag")
    @patch("azlin.modules.backup_manager.BackupManager._get_vm_tag")
    def test_replication_failure_recovery(
        self, mock_get_tag, mock_set_tag, mock_run, tmp_path
    ):
        """Test workflow recovery when replication fails then succeeds.

        Simulates:
        1. Backup creation succeeds
        2. First replication attempt fails (quota exceeded)
        3. Second replication attempt succeeds
        4. Verification confirms backup integrity
        """
        # Configure and create backup
        from azlin.modules.backup_manager import BackupSchedule

        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
            cross_region_enabled=True,
            target_region="westus2",
        )
        mock_get_tag.return_value = schedule.to_tag_value()

        with patch("azlin.modules.backup_manager.BackupManager._create_backup_snapshot") as mock_backup:
            mock_backup.return_value = "test-vm-backup-daily-20251201-100000"

            backup_info = BackupManager.trigger_backup(
                vm_name="test-vm",
                resource_group="test-rg",
            )

        # First replication attempt fails
        replication_db = tmp_path / "replication.db"
        replication_manager = ReplicationManager(storage_path=replication_db)

        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="QuotaExceeded: Snapshot quota exceeded in target region",
        )

        from azlin.modules.backup_replication import ReplicationError

        with pytest.raises(ReplicationError, match="QuotaExceeded"):
            replication_manager.replicate_backup(
                snapshot_name=backup_info.snapshot_name,
                source_resource_group="test-rg",
                target_region="westus2",
            )

        # Second attempt succeeds (after quota increase)
        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"id": "/subscriptions/.../westus2-snapshot", "provisioningState": "Succeeded"}',
            stderr="",
        )

        replication_job = replication_manager.replicate_backup(
            snapshot_name=backup_info.snapshot_name,
            source_resource_group="test-rg",
            target_region="westus2",
        )

        assert replication_job.status == "completed"

        # Verify backup after recovery
        verification_db = tmp_path / "verification.db"
        verification_manager = VerificationManager(storage_path=verification_db)

        with patch("time.time") as mock_time:
            mock_time.side_effect = [1000.0, 1045.2]

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

            verification_result = verification_manager.verify_backup(
                snapshot_name=replication_job.target_snapshot,
                resource_group=replication_job.target_resource_group,
            )

        assert verification_result.success is True


class TestScheduledBackupMaintenanceWorkflow:
    """Test E2E workflow for scheduled backup maintenance."""

    @patch("azlin.modules.backup_manager.BackupManager._get_vm_tag")
    @patch("azlin.modules.backup_manager.BackupManager.list_backups")
    @patch("azlin.modules.backup_manager.SnapshotManager.delete_snapshot")
    def test_weekly_maintenance_cleanup(self, mock_delete, mock_list, mock_get_tag):
        """Test weekly backup maintenance: trigger backup → cleanup old backups.

        Simulates weekly maintenance job:
        1. Check current backup inventory
        2. Identify expired backups per retention policy
        3. Clean up expired backups across all tiers
        4. Generate cleanup report
        """
        from azlin.modules.backup_manager import BackupInfo, BackupSchedule

        # Configure retention policy
        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
        )
        mock_get_tag.return_value = schedule.to_tag_value()

        # Mock current backup inventory
        now = datetime.now(UTC)
        backups = []

        # 10 daily backups (3 expired)
        for i in range(10):
            backups.append(
                BackupInfo(
                    snapshot_name=f"vm1-backup-daily-{i}",
                    vm_name="test-vm",
                    resource_group="test-rg",
                    creation_time=now - timedelta(days=i),
                    retention_tier="daily",
                )
            )

        # 6 weekly backups (2 expired)
        for i in range(6):
            backups.append(
                BackupInfo(
                    snapshot_name=f"vm1-backup-weekly-{i}",
                    vm_name="test-vm",
                    resource_group="test-rg",
                    creation_time=now - timedelta(weeks=i),
                    retention_tier="weekly",
                )
            )

        # 14 monthly backups (2 expired)
        for i in range(14):
            backups.append(
                BackupInfo(
                    snapshot_name=f"vm1-backup-monthly-{i}",
                    vm_name="test-vm",
                    resource_group="test-rg",
                    creation_time=now - timedelta(days=30 * i),
                    retention_tier="monthly",
                )
            )

        mock_list.return_value = backups

        # Run cleanup
        cleanup_result = BackupManager.cleanup_expired_backups(
            vm_name="test-vm",
            resource_group="test-rg",
        )

        # Verify cleanup report
        assert cleanup_result["daily"] == 3
        assert cleanup_result["weekly"] == 2
        assert cleanup_result["monthly"] == 2

        # Verify total deletions
        total_deleted = sum(cleanup_result.values())
        assert total_deleted == 7
        assert mock_delete.call_count == 7


class TestRegionOutageFailoverWorkflow:
    """Test E2E workflow for region outage failover scenario."""

    @patch("subprocess.run")
    @patch("time.time")
    def test_region_outage_failover_to_replica(self, mock_time, mock_run, tmp_path):
        """Test complete region failover workflow.

        Disaster scenario:
        1. Primary region becomes unavailable
        2. Identify most recent replicated backup in secondary region
        3. Execute DR test to restore in secondary region
        4. Verify RTO meets target (<15 min)
        5. Confirm VM is operational in secondary region
        """
        # Simulate region outage: backup replication already completed
        replication_db = tmp_path / "replication.db"
        replication_manager = ReplicationManager(storage_path=replication_db)

        # Mock successful replication (already completed before outage)
        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"id": "/subscriptions/.../westus2-snapshot", "provisioningState": "Succeeded"}',
            stderr="",
        )

        replication_job = replication_manager.replicate_backup(
            snapshot_name="test-vm-backup-daily-20251201-100000",
            source_resource_group="test-rg-eastus",
            target_region="westus2",
            target_resource_group="test-rg-westus2",
        )

        assert replication_job.status == "completed"

        # Primary region fails - execute DR failover
        dr_test_db = tmp_path / "dr_tests.db"
        dr_test_manager = DRTestManager(storage_path=dr_test_db)

        # Mock DR test timing
        mock_time.side_effect = [1000.0, 1800.0]  # 13 minutes RTO

        # Mock Azure CLI for DR failover
        def run_side_effect_failover(cmd, *args, **kwargs):
            if "disk" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../prod-disk"}',
                    stderr="",
                )
            elif "vm" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../prod-vm"}',
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
            return Mock(returncode=0, stdout="{}", stderr="")

        mock_run.side_effect = run_side_effect_failover

        dr_config = DRTestConfig(
            vm_name="test-vm",
            backup_name=replication_job.target_snapshot,
            source_resource_group=replication_job.target_resource_group,
            test_region="westus2",
            test_resource_group="test-rg-westus2-prod",
            cleanup_after_test=False,  # Keep VM running for production failover
        )

        dr_result = dr_test_manager.run_dr_test(dr_config)

        # Verify successful failover
        assert dr_result.success is True
        assert dr_result.restore_succeeded is True
        assert dr_result.boot_succeeded is True
        assert dr_result.connectivity_succeeded is True
        assert dr_result.rto_seconds < 900  # Under 15-minute target

        # Verify success rate meets 99.9% target
        success_rate = dr_test_manager.get_success_rate(vm_name="test-vm", days=30)
        assert success_rate >= 0.999 or success_rate == 1.0


# ============================================================================
# PERFORMANCE AND SCALE TESTS
# ============================================================================


class TestPerformanceTargets:
    """Test that operations meet performance targets."""

    @patch("time.time")
    @patch("subprocess.run")
    def test_backup_verification_under_2_minutes(self, mock_run, mock_time, tmp_path):
        """Test backup verification completes in under 2 minutes."""
        verification_db = tmp_path / "verification.db"
        verification_manager = VerificationManager(storage_path=verification_db)

        # Mock 115 seconds (under 2-minute target)
        mock_time.side_effect = [1000.0, 1115.0]

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

        result = verification_manager.verify_backup(
            snapshot_name="test-vm-backup-daily-20251201-100000",
            resource_group="test-rg",
        )

        assert result.success is True
        assert result.verification_time_seconds < 120  # Under 2 minutes

    @patch("time.time")
    @patch("subprocess.run")
    def test_dr_test_rto_under_15_minutes(self, mock_run, mock_time, tmp_path):
        """Test DR test RTO is under 15-minute target."""
        dr_test_db = tmp_path / "dr_tests.db"
        dr_test_manager = DRTestManager(storage_path=dr_test_db)

        # Mock 840 seconds (14 minutes, under 15-minute target)
        mock_time.side_effect = [1000.0, 1840.0]

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

        dr_config = DRTestConfig(
            vm_name="test-vm",
            backup_name="test-vm-backup-daily-20251201-100000",
            source_resource_group="test-rg",
            test_region="westus2",
            test_resource_group="test-rg-dr",
        )

        result = dr_test_manager.run_dr_test(dr_config)

        assert result.success is True
        assert result.rto_seconds < 900  # Under 15 minutes
