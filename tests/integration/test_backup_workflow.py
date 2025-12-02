"""Integration tests for backup workflow.

Tests the complete backup workflow integrating multiple modules.

Testing pyramid:
- 60% Unit tests (fast, heavily mocked)
- 30% Integration tests (multiple components) ← THIS FILE
- 10% E2E tests (complete workflows)
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

from azlin.modules.backup_manager import BackupManager, BackupSchedule
from azlin.modules.backup_replication import ReplicationManager
from azlin.modules.backup_verification import VerificationManager

# ============================================================================
# INTEGRATION TESTS (30% of test suite)
# ============================================================================


class TestBackupToReplicationWorkflow:
    """Test integration between BackupManager and ReplicationManager."""

    @patch("azlin.modules.backup_manager.SnapshotManager.create_snapshot")
    @patch("subprocess.run")
    def test_backup_then_replicate(self, mock_run, mock_create_snapshot, tmp_path):
        """Test complete workflow: create backup → replicate to secondary region."""
        # Configure backup with cross-region enabled
        with patch("azlin.modules.backup_manager.BackupManager._set_vm_tag"):
            BackupManager.configure_backup(
                vm_name="test-vm",
                resource_group="test-rg",
                cross_region=True,
                target_region="westus2",
            )

        # Mock snapshot creation
        mock_create_snapshot.return_value = Mock(
            name="test-vm-snapshot-20251201-100000",
            resource_group="test-rg",
            source_vm="test-vm",
            creation_time=datetime.now(UTC),
            size_gb=128,
        )

        # Mock backup trigger
        with patch("azlin.modules.backup_manager.BackupManager._get_vm_tag") as mock_get_tag:
            schedule = BackupSchedule(
                enabled=True,
                daily_retention=7,
                weekly_retention=4,
                monthly_retention=12,
                cross_region_enabled=True,
                target_region="westus2",
            )
            mock_get_tag.return_value = schedule.to_tag_value()

            with patch(
                "azlin.modules.backup_manager.BackupManager._create_backup_snapshot"
            ) as mock_backup:
                mock_backup.return_value = "test-vm-backup-daily-20251201-100000"

                # Trigger backup
                backup_info = BackupManager.trigger_backup(
                    vm_name="test-vm",
                    resource_group="test-rg",
                )

        assert backup_info.snapshot_name == "test-vm-backup-daily-20251201-100000"

        # Now replicate to secondary region
        db_path = tmp_path / "replication.db"
        replication_manager = ReplicationManager(storage_path=db_path)

        # Mock Azure CLI for replication
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
        assert replication_job.target_region == "westus2"


class TestBackupToVerificationWorkflow:
    """Test integration between BackupManager and VerificationManager."""

    @patch("azlin.modules.backup_manager.BackupManager._create_backup_snapshot")
    @patch("azlin.modules.backup_manager.BackupManager._get_vm_tag")
    @patch("subprocess.run")
    @patch("time.time")
    def test_backup_then_verify(
        self, mock_time, mock_run, mock_get_tag, mock_create_backup, tmp_path
    ):
        """Test complete workflow: create backup → verify integrity."""
        # Mock backup creation
        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
        )
        mock_get_tag.return_value = schedule.to_tag_value()
        mock_create_backup.return_value = "test-vm-backup-daily-20251201-100000"

        # Trigger backup
        with patch("azlin.modules.backup_manager.BackupManager._set_vm_tag"):
            backup_info = BackupManager.trigger_backup(
                vm_name="test-vm",
                resource_group="test-rg",
            )

        assert backup_info.snapshot_name == "test-vm-backup-daily-20251201-100000"

        # Now verify the backup
        db_path = tmp_path / "verification.db"
        verification_manager = VerificationManager(storage_path=db_path)

        # Mock timing and Azure CLI for verification
        mock_time.side_effect = [1000.0, 1045.2]

        def run_side_effect(cmd, *args, **kwargs):
            if "disk" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-disk", "diskSizeGb": 128}',
                    stderr="",
                )
            if "disk" in cmd and "show" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"diskSizeGb": 128, "diskState": "Attached"}',
                    stderr="",
                )
            if "disk" in cmd and "delete" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=0, stdout="{}", stderr="")

        mock_run.side_effect = run_side_effect

        verification_result = verification_manager.verify_backup(
            snapshot_name=backup_info.snapshot_name,
            resource_group="test-rg",
        )

        assert verification_result.success is True
        assert verification_result.backup_name == backup_info.snapshot_name


class TestReplicationToVerificationWorkflow:
    """Test integration between ReplicationManager and VerificationManager."""

    @patch("subprocess.run")
    @patch("time.time")
    def test_replicate_then_verify_both_regions(self, mock_time, mock_run, tmp_path):
        """Test workflow: replicate backup → verify in both regions."""
        # Replicate backup
        replication_db = tmp_path / "replication.db"
        replication_manager = ReplicationManager(storage_path=replication_db)

        def run_side_effect_replication(cmd, *args, **kwargs):
            if "snapshot" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../westus2-snapshot", "provisioningState": "Succeeded"}',
                    stderr="",
                )
            return Mock(returncode=0, stdout="{}", stderr="")

        mock_run.side_effect = run_side_effect_replication

        replication_job = replication_manager.replicate_backup(
            snapshot_name="test-vm-backup-daily-20251201-100000",
            source_resource_group="test-rg",
            target_region="westus2",
        )

        assert replication_job.status == "completed"

        # Verify both source and replicated backups
        verification_db = tmp_path / "verification.db"
        verification_manager = VerificationManager(storage_path=verification_db)

        mock_time.side_effect = [1000.0, 1045.2, 2000.0, 2045.2]

        def run_side_effect_verification(cmd, *args, **kwargs):
            if "disk" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-disk", "diskSizeGb": 128}',
                    stderr="",
                )
            if "disk" in cmd and "show" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"diskSizeGb": 128, "diskState": "Attached"}',
                    stderr="",
                )
            if "disk" in cmd and "delete" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=0, stdout="{}", stderr="")

        mock_run.side_effect = run_side_effect_verification

        # Verify source backup
        source_result = verification_manager.verify_backup(
            snapshot_name="test-vm-backup-daily-20251201-100000",
            resource_group="test-rg",
        )

        # Verify replicated backup
        replicated_result = verification_manager.verify_backup(
            snapshot_name=replication_job.target_snapshot,
            resource_group=replication_job.target_resource_group,
        )

        assert source_result.success is True
        assert replicated_result.success is True


class TestBackupCleanupWithReplicationTracking:
    """Test backup cleanup considers replication status."""

    @patch("azlin.modules.backup_manager.BackupManager._get_vm_tag")
    @patch("azlin.modules.backup_manager.BackupManager.list_backups")
    @patch("azlin.modules.backup_manager.SnapshotManager.delete_snapshot")
    def test_cleanup_only_replicated_backups(self, mock_delete, mock_list, mock_get_tag, tmp_path):
        """Test cleanup only deletes backups that are replicated."""
        # Configure backup with cross-region
        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
            cross_region_enabled=True,
            target_region="westus2",
        )
        mock_get_tag.return_value = schedule.to_tag_value()

        # Mock backups - some replicated, some not
        from azlin.modules.backup_manager import BackupInfo

        now = datetime.now(UTC)
        backups = []
        for i in range(10):
            backups.append(
                BackupInfo(
                    snapshot_name=f"vm1-backup-daily-{i}",
                    vm_name="test-vm",
                    resource_group="test-rg",
                    creation_time=now - timedelta(days=i),
                    retention_tier="daily",
                    replicated=(i < 8),  # First 8 are replicated
                )
            )
        mock_list.return_value = backups

        # Cleanup should only delete replicated backups beyond retention
        result = BackupManager.cleanup_expired_backups(
            vm_name="test-vm",
            resource_group="test-rg",
        )

        # Should delete oldest replicated backups (beyond 7-day retention)
        assert result["daily"] == 1  # Only 1 replicated backup beyond retention
        mock_delete.assert_called_once()


class TestMultiStepBackupRetentionPolicyEnforcement:
    """Test retention policy enforcement across backup tiers."""

    @patch("azlin.modules.backup_manager.BackupManager._get_vm_tag")
    @patch("azlin.modules.backup_manager.BackupManager.list_backups")
    @patch("azlin.modules.backup_manager.SnapshotManager.delete_snapshot")
    def test_retention_policy_across_tiers(self, mock_delete, mock_list, mock_get_tag):
        """Test cleanup enforces retention separately for each tier."""
        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
        )
        mock_get_tag.return_value = schedule.to_tag_value()

        from azlin.modules.backup_manager import BackupInfo

        now = datetime.now(UTC)
        backups = []

        # 10 daily backups (3 should be deleted)
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

        # 6 weekly backups (2 should be deleted)
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

        # 15 monthly backups (3 should be deleted)
        for i in range(15):
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

        result = BackupManager.cleanup_expired_backups(
            vm_name="test-vm",
            resource_group="test-rg",
        )

        # Verify correct number deleted per tier
        assert result["daily"] == 3
        assert result["weekly"] == 2
        assert result["monthly"] == 3


class TestParallelReplicationBatching:
    """Test parallel replication with proper batching."""

    @patch("azlin.modules.backup_replication.BackupManager.list_backups")
    @patch("subprocess.run")
    def test_parallel_replication_respects_batching(self, mock_run, mock_list, tmp_path):
        """Test parallel replication processes in batches correctly."""
        db_path = tmp_path / "replication.db"
        replication_manager = ReplicationManager(storage_path=db_path)

        # Mock 10 unreplicated backups
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

        # Mock successful replication
        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"id": "/subscriptions/.../snapshot", "provisioningState": "Succeeded"}',
            stderr="",
        )

        # Replicate with batch size of 3
        jobs = replication_manager.replicate_all_pending(
            vm_name="test-vm",
            source_resource_group="test-rg",
            target_region="westus2",
            max_parallel=3,
        )

        # Should process all 10 in batches
        assert len(jobs) == 10
        # Verify Azure CLI was called 10 times
        assert mock_run.call_count == 10


class TestParallelVerificationBatching:
    """Test parallel verification with proper batching."""

    @patch("azlin.modules.backup_verification.BackupManager.list_backups")
    @patch("subprocess.run")
    @patch("time.time")
    def test_parallel_verification_respects_batching(
        self, mock_time, mock_run, mock_list, tmp_path
    ):
        """Test parallel verification processes in batches correctly."""
        db_path = tmp_path / "verification.db"
        verification_manager = VerificationManager(storage_path=db_path)

        # Mock 10 unverified backups
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

        # Mock timing (10 verifications)
        mock_time.side_effect = [1000.0 + i * 50 for i in range(20)]

        # Mock successful verification
        def run_side_effect(cmd, *args, **kwargs):
            if "disk" in cmd and "create" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "/subscriptions/.../test-disk", "diskSizeGb": 128}',
                    stderr="",
                )
            if "disk" in cmd and "show" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"diskSizeGb": 128, "diskState": "Attached"}',
                    stderr="",
                )
            if "disk" in cmd and "delete" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=0, stdout="{}", stderr="")

        mock_run.side_effect = run_side_effect

        # Verify with batch size of 2
        results = verification_manager.verify_all_backups(
            vm_name="test-vm",
            resource_group="test-rg",
            max_parallel=2,
        )

        # Should process all 10 in batches
        assert len(results) == 10
        assert all(r.success for r in results)


class TestBackupScheduleUpdatePropagation:
    """Test schedule updates propagate correctly through workflow."""

    @patch("azlin.modules.backup_manager.BackupManager._set_vm_tag")
    @patch("azlin.modules.backup_manager.BackupManager._get_vm_tag")
    def test_schedule_update_affects_next_backup(self, mock_get_tag, mock_set_tag):
        """Test updating backup schedule affects subsequent backups."""
        # Initial configuration
        BackupManager.configure_backup(
            vm_name="test-vm",
            resource_group="test-rg",
            daily_retention=7,
        )

        # Get initial schedule
        initial_schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
        )
        mock_get_tag.return_value = initial_schedule.to_tag_value()

        # Update schedule
        BackupManager.configure_backup(
            vm_name="test-vm",
            resource_group="test-rg",
            daily_retention=14,  # Changed to 14 days
        )

        # Verify new schedule was set
        last_call = mock_set_tag.call_args_list[-1]
        tag_value = last_call[0][3]
        import json

        schedule_data = json.loads(tag_value)
        assert schedule_data["daily_retention"] == 14
