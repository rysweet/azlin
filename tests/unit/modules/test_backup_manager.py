"""Unit tests for BackupManager module.

Tests for automated backup management with retention policies.

Testing pyramid:
- 60% Unit tests (fast, heavily mocked)
- 30% Integration tests (multiple components)
- 10% E2E tests (complete workflows)
"""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from azlin.modules.backup_manager import (
    BackupError,
    BackupInfo,
    BackupManager,
    BackupSchedule,
)


# ============================================================================
# UNIT TESTS (60% of test suite)
# ============================================================================


class TestBackupScheduleDataclass:
    """Test BackupSchedule dataclass serialization/deserialization."""

    def test_backup_schedule_to_tag_value(self):
        """Test serialization to JSON tag value."""
        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
            last_daily=datetime(2025, 12, 1, 10, 0, 0, tzinfo=UTC),
            last_weekly=None,
            last_monthly=None,
            cross_region_enabled=True,
            target_region="westus2",
        )

        tag_value = schedule.to_tag_value()

        assert isinstance(tag_value, str)
        data = json.loads(tag_value)
        assert data["enabled"] is True
        assert data["daily_retention"] == 7
        assert data["weekly_retention"] == 4
        assert data["monthly_retention"] == 12
        assert data["cross_region_enabled"] is True
        assert data["target_region"] == "westus2"

    def test_backup_schedule_from_tag_value(self):
        """Test deserialization from JSON tag value."""
        tag_value = json.dumps({
            "enabled": True,
            "daily_retention": 7,
            "weekly_retention": 4,
            "monthly_retention": 12,
            "last_daily": "2025-12-01T10:00:00+00:00",
            "last_weekly": None,
            "last_monthly": None,
            "cross_region_enabled": True,
            "target_region": "westus2",
        })

        schedule = BackupSchedule.from_tag_value(tag_value)

        assert schedule.enabled is True
        assert schedule.daily_retention == 7
        assert schedule.weekly_retention == 4
        assert schedule.monthly_retention == 12
        assert schedule.cross_region_enabled is True
        assert schedule.target_region == "westus2"

    def test_backup_schedule_from_invalid_json(self):
        """Test error handling for invalid JSON."""
        with pytest.raises(BackupError, match="Failed to parse backup schedule"):
            BackupSchedule.from_tag_value("invalid json")

    def test_backup_schedule_from_missing_fields(self):
        """Test defaults for missing optional fields."""
        tag_value = json.dumps({
            "enabled": True,
            "daily_retention": 7,
        })

        schedule = BackupSchedule.from_tag_value(tag_value)

        assert schedule.enabled is True
        assert schedule.daily_retention == 7
        assert schedule.weekly_retention == 4  # Default
        assert schedule.monthly_retention == 12  # Default


class TestBackupInfoDataclass:
    """Test BackupInfo dataclass structure."""

    def test_backup_info_creation(self):
        """Test BackupInfo creation with all fields."""
        backup = BackupInfo(
            snapshot_name="vm1-backup-daily-20251201-100000",
            vm_name="vm1",
            resource_group="test-rg",
            creation_time=datetime(2025, 12, 1, 10, 0, 0, tzinfo=UTC),
            retention_tier="daily",
            replicated=True,
            verified=True,
            size_gb=128,
        )

        assert backup.snapshot_name == "vm1-backup-daily-20251201-100000"
        assert backup.vm_name == "vm1"
        assert backup.resource_group == "test-rg"
        assert backup.retention_tier == "daily"
        assert backup.replicated is True
        assert backup.verified is True
        assert backup.size_gb == 128

    def test_backup_info_defaults(self):
        """Test BackupInfo with minimal fields."""
        backup = BackupInfo(
            snapshot_name="vm1-backup-daily-20251201-100000",
            vm_name="vm1",
            resource_group="test-rg",
            creation_time=datetime(2025, 12, 1, 10, 0, 0, tzinfo=UTC),
            retention_tier="daily",
        )

        assert backup.replicated is False
        assert backup.verified is False
        assert backup.size_gb is None


class TestConfigureBackup:
    """Test backup configuration functionality."""

    @patch("azlin.modules.backup_manager.BackupManager._set_vm_tag")
    def test_configure_backup_with_defaults(self, mock_set_tag):
        """Test configuring backup with default retention."""
        BackupManager.configure_backup(
            vm_name="test-vm",
            resource_group="test-rg",
        )

        # Verify tag was set
        mock_set_tag.assert_called_once()
        call_args = mock_set_tag.call_args
        assert call_args[0][0] == "test-vm"
        assert call_args[0][1] == "test-rg"
        assert call_args[0][2] == BackupManager.BACKUP_SCHEDULE_TAG

        # Verify schedule in tag value
        tag_value = call_args[0][3]
        schedule_data = json.loads(tag_value)
        assert schedule_data["enabled"] is True
        assert schedule_data["daily_retention"] == 7
        assert schedule_data["weekly_retention"] == 4
        assert schedule_data["monthly_retention"] == 12

    @patch("azlin.modules.backup_manager.BackupManager._set_vm_tag")
    def test_configure_backup_with_custom_retention(self, mock_set_tag):
        """Test configuring backup with custom retention policies."""
        BackupManager.configure_backup(
            vm_name="test-vm",
            resource_group="test-rg",
            daily_retention=14,
            weekly_retention=8,
            monthly_retention=24,
        )

        tag_value = mock_set_tag.call_args[0][3]
        schedule_data = json.loads(tag_value)
        assert schedule_data["daily_retention"] == 14
        assert schedule_data["weekly_retention"] == 8
        assert schedule_data["monthly_retention"] == 24

    @patch("azlin.modules.backup_manager.BackupManager._set_vm_tag")
    def test_configure_backup_with_cross_region(self, mock_set_tag):
        """Test configuring backup with cross-region replication."""
        BackupManager.configure_backup(
            vm_name="test-vm",
            resource_group="test-rg",
            cross_region=True,
            target_region="westus2",
        )

        tag_value = mock_set_tag.call_args[0][3]
        schedule_data = json.loads(tag_value)
        assert schedule_data["cross_region_enabled"] is True
        assert schedule_data["target_region"] == "westus2"

    def test_configure_backup_invalid_vm_name(self):
        """Test error handling for invalid VM name."""
        with pytest.raises(BackupError, match="Invalid VM name"):
            BackupManager.configure_backup(
                vm_name="",
                resource_group="test-rg",
            )

    def test_configure_backup_invalid_resource_group(self):
        """Test error handling for invalid resource group."""
        with pytest.raises(BackupError, match="Invalid resource group"):
            BackupManager.configure_backup(
                vm_name="test-vm",
                resource_group="",
            )

    def test_configure_backup_invalid_retention(self):
        """Test error handling for invalid retention values."""
        with pytest.raises(BackupError, match="retention must be positive"):
            BackupManager.configure_backup(
                vm_name="test-vm",
                resource_group="test-rg",
                daily_retention=0,
            )

    def test_configure_backup_cross_region_without_target(self):
        """Test error handling for cross-region without target region."""
        with pytest.raises(BackupError, match="target_region required"):
            BackupManager.configure_backup(
                vm_name="test-vm",
                resource_group="test-rg",
                cross_region=True,
                target_region=None,
            )


class TestTriggerBackup:
    """Test backup trigger functionality."""

    @patch("azlin.modules.backup_manager.BackupManager._get_vm_tag")
    @patch("azlin.modules.backup_manager.BackupManager._create_backup_snapshot")
    @patch("azlin.modules.backup_manager.BackupManager._set_vm_tag")
    def test_trigger_backup_daily_tier(self, mock_set_tag, mock_create, mock_get_tag):
        """Test triggering daily backup."""
        # Mock schedule retrieval
        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
        )
        mock_get_tag.return_value = schedule.to_tag_value()

        # Mock snapshot creation
        mock_create.return_value = "vm1-backup-daily-20251201-100000"

        # Trigger backup
        result = BackupManager.trigger_backup(
            vm_name="test-vm",
            resource_group="test-rg",
        )

        # Verify backup info returned
        assert result.snapshot_name == "vm1-backup-daily-20251201-100000"
        assert result.retention_tier == "daily"
        assert result.vm_name == "test-vm"

        # Verify schedule was updated
        mock_set_tag.assert_called()

    @patch("azlin.modules.backup_manager.BackupManager._get_vm_tag")
    def test_trigger_backup_no_schedule_configured(self, mock_get_tag):
        """Test error when no backup schedule configured."""
        mock_get_tag.return_value = None

        with pytest.raises(BackupError, match="No backup schedule configured"):
            BackupManager.trigger_backup(
                vm_name="test-vm",
                resource_group="test-rg",
            )

    @patch("azlin.modules.backup_manager.BackupManager._get_vm_tag")
    def test_trigger_backup_schedule_disabled(self, mock_get_tag):
        """Test error when backup schedule is disabled."""
        schedule = BackupSchedule(
            enabled=False,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
        )
        mock_get_tag.return_value = schedule.to_tag_value()

        with pytest.raises(BackupError, match="Backup schedule is disabled"):
            BackupManager.trigger_backup(
                vm_name="test-vm",
                resource_group="test-rg",
            )

    @patch("azlin.modules.backup_manager.BackupManager._get_vm_tag")
    @patch("azlin.modules.backup_manager.BackupManager._create_backup_snapshot")
    def test_trigger_backup_force_weekly_tier(self, mock_create, mock_get_tag):
        """Test forcing weekly tier backup."""
        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
        )
        mock_get_tag.return_value = schedule.to_tag_value()
        mock_create.return_value = "vm1-backup-weekly-20251201-100000"

        result = BackupManager.trigger_backup(
            vm_name="test-vm",
            resource_group="test-rg",
            force_tier="weekly",
        )

        assert result.retention_tier == "weekly"
        mock_create.assert_called_with("test-vm", "test-rg", "weekly")

    @patch("azlin.modules.backup_manager.BackupManager._get_vm_tag")
    def test_trigger_backup_invalid_tier(self, mock_get_tag):
        """Test error for invalid retention tier."""
        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
        )
        mock_get_tag.return_value = schedule.to_tag_value()

        with pytest.raises(BackupError, match="Invalid retention tier"):
            BackupManager.trigger_backup(
                vm_name="test-vm",
                resource_group="test-rg",
                force_tier="invalid",
            )


class TestDetermineTier:
    """Test automatic retention tier determination."""

    def test_determine_tier_first_backup_daily(self):
        """Test first backup is always daily tier."""
        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
            last_daily=None,
            last_weekly=None,
            last_monthly=None,
        )

        tier = BackupManager._determine_tier(schedule)

        assert tier == "daily"

    def test_determine_tier_first_of_week_is_weekly(self):
        """Test first backup of week is weekly tier."""
        # Last daily was yesterday (Saturday), today is Sunday
        now = datetime(2025, 12, 7, 10, 0, 0, tzinfo=UTC)  # Sunday
        last_daily = datetime(2025, 12, 6, 10, 0, 0, tzinfo=UTC)  # Saturday

        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
            last_daily=last_daily,
            last_weekly=None,
            last_monthly=None,
        )

        with patch("azlin.modules.backup_manager.datetime") as mock_datetime:
            mock_datetime.now.return_value = now
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            tier = BackupManager._determine_tier(schedule)

        assert tier == "weekly"

    def test_determine_tier_first_of_month_is_monthly(self):
        """Test first backup of month is monthly tier."""
        # Today is Dec 1st
        now = datetime(2025, 12, 1, 10, 0, 0, tzinfo=UTC)
        last_daily = datetime(2025, 11, 30, 10, 0, 0, tzinfo=UTC)

        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
            last_daily=last_daily,
            last_weekly=None,
            last_monthly=None,
        )

        with patch("azlin.modules.backup_manager.datetime") as mock_datetime:
            mock_datetime.now.return_value = now
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            tier = BackupManager._determine_tier(schedule)

        assert tier == "monthly"

    def test_determine_tier_daily_default(self):
        """Test daily tier is default for mid-week, mid-month."""
        # Today is Dec 5th (Friday, not Sunday, not 1st)
        now = datetime(2025, 12, 5, 10, 0, 0, tzinfo=UTC)
        last_daily = datetime(2025, 12, 4, 10, 0, 0, tzinfo=UTC)

        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
            last_daily=last_daily,
            last_weekly=None,
            last_monthly=None,
        )

        with patch("azlin.modules.backup_manager.datetime") as mock_datetime:
            mock_datetime.now.return_value = now
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            tier = BackupManager._determine_tier(schedule)

        assert tier == "daily"


class TestListBackups:
    """Test backup listing functionality."""

    @patch("azlin.modules.backup_manager.SnapshotManager.list_snapshots")
    def test_list_backups_all_tiers(self, mock_list_snapshots):
        """Test listing all backups across all tiers."""
        # Mock snapshot data
        mock_snapshots = [
            Mock(
                name="vm1-snapshot-20251201-100000",
                tags={"azlin:backup-tier": "daily"},
                creation_time=datetime(2025, 12, 1, 10, 0, 0, tzinfo=UTC),
                size_gb=128,
            ),
            Mock(
                name="vm1-snapshot-20251124-100000",
                tags={"azlin:backup-tier": "weekly"},
                creation_time=datetime(2025, 11, 24, 10, 0, 0, tzinfo=UTC),
                size_gb=128,
            ),
            Mock(
                name="vm1-snapshot-20251101-100000",
                tags={"azlin:backup-tier": "monthly"},
                creation_time=datetime(2025, 11, 1, 10, 0, 0, tzinfo=UTC),
                size_gb=128,
            ),
        ]
        mock_list_snapshots.return_value = mock_snapshots

        backups = BackupManager.list_backups(
            vm_name="test-vm",
            resource_group="test-rg",
        )

        assert len(backups) == 3
        assert backups[0].retention_tier == "daily"
        assert backups[1].retention_tier == "weekly"
        assert backups[2].retention_tier == "monthly"

    @patch("azlin.modules.backup_manager.SnapshotManager.list_snapshots")
    def test_list_backups_filter_by_tier(self, mock_list_snapshots):
        """Test filtering backups by retention tier."""
        mock_snapshots = [
            Mock(
                name="vm1-snapshot-20251201-100000",
                tags={"azlin:backup-tier": "daily"},
                creation_time=datetime(2025, 12, 1, 10, 0, 0, tzinfo=UTC),
                size_gb=128,
            ),
            Mock(
                name="vm1-snapshot-20251124-100000",
                tags={"azlin:backup-tier": "weekly"},
                creation_time=datetime(2025, 11, 24, 10, 0, 0, tzinfo=UTC),
                size_gb=128,
            ),
        ]
        mock_list_snapshots.return_value = mock_snapshots

        backups = BackupManager.list_backups(
            vm_name="test-vm",
            resource_group="test-rg",
            tier="weekly",
        )

        assert len(backups) == 1
        assert backups[0].retention_tier == "weekly"

    @patch("azlin.modules.backup_manager.SnapshotManager.list_snapshots")
    def test_list_backups_empty_result(self, mock_list_snapshots):
        """Test listing backups when none exist."""
        mock_list_snapshots.return_value = []

        backups = BackupManager.list_backups(
            vm_name="test-vm",
            resource_group="test-rg",
        )

        assert backups == []


class TestCleanupExpiredBackups:
    """Test backup cleanup functionality."""

    @patch("azlin.modules.backup_manager.BackupManager._get_vm_tag")
    @patch("azlin.modules.backup_manager.BackupManager.list_backups")
    @patch("azlin.modules.backup_manager.SnapshotManager.delete_snapshot")
    def test_cleanup_expired_daily_backups(self, mock_delete, mock_list, mock_get_tag):
        """Test cleanup of expired daily backups."""
        # Mock schedule with 7-day retention
        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
        )
        mock_get_tag.return_value = schedule.to_tag_value()

        # Mock 10 daily backups (3 should be deleted)
        now = datetime.now(UTC)
        backups = []
        for i in range(10):
            backups.append(BackupInfo(
                snapshot_name=f"vm1-backup-daily-{i}",
                vm_name="test-vm",
                resource_group="test-rg",
                creation_time=now - timedelta(days=i),
                retention_tier="daily",
            ))
        mock_list.return_value = backups

        result = BackupManager.cleanup_expired_backups(
            vm_name="test-vm",
            resource_group="test-rg",
        )

        # Should delete 3 oldest daily backups
        assert result["daily"] == 3
        assert mock_delete.call_count == 3

    @patch("azlin.modules.backup_manager.BackupManager._get_vm_tag")
    @patch("azlin.modules.backup_manager.BackupManager.list_backups")
    @patch("azlin.modules.backup_manager.SnapshotManager.delete_snapshot")
    def test_cleanup_expired_weekly_backups(self, mock_delete, mock_list, mock_get_tag):
        """Test cleanup of expired weekly backups."""
        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
        )
        mock_get_tag.return_value = schedule.to_tag_value()

        # Mock 6 weekly backups (2 should be deleted)
        now = datetime.now(UTC)
        backups = []
        for i in range(6):
            backups.append(BackupInfo(
                snapshot_name=f"vm1-backup-weekly-{i}",
                vm_name="test-vm",
                resource_group="test-rg",
                creation_time=now - timedelta(weeks=i),
                retention_tier="weekly",
            ))
        mock_list.return_value = backups

        result = BackupManager.cleanup_expired_backups(
            vm_name="test-vm",
            resource_group="test-rg",
        )

        assert result["weekly"] == 2

    @patch("azlin.modules.backup_manager.BackupManager._get_vm_tag")
    @patch("azlin.modules.backup_manager.BackupManager.list_backups")
    def test_cleanup_no_expired_backups(self, mock_list, mock_get_tag):
        """Test cleanup when no backups are expired."""
        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
        )
        mock_get_tag.return_value = schedule.to_tag_value()

        # Mock only 3 daily backups (all within retention)
        now = datetime.now(UTC)
        backups = []
        for i in range(3):
            backups.append(BackupInfo(
                snapshot_name=f"vm1-backup-daily-{i}",
                vm_name="test-vm",
                resource_group="test-rg",
                creation_time=now - timedelta(days=i),
                retention_tier="daily",
            ))
        mock_list.return_value = backups

        result = BackupManager.cleanup_expired_backups(
            vm_name="test-vm",
            resource_group="test-rg",
        )

        assert result["daily"] == 0
        assert result["weekly"] == 0
        assert result["monthly"] == 0


# ============================================================================
# BOUNDARY TESTS (Part of Unit Tests)
# ============================================================================


class TestBoundaryConditions:
    """Test edge cases and boundary conditions."""

    def test_backup_schedule_zero_retention(self):
        """Test zero retention values are rejected."""
        with pytest.raises(BackupError, match="retention must be positive"):
            BackupManager.configure_backup(
                vm_name="test-vm",
                resource_group="test-rg",
                daily_retention=0,
            )

    def test_backup_schedule_negative_retention(self):
        """Test negative retention values are rejected."""
        with pytest.raises(BackupError, match="retention must be positive"):
            BackupManager.configure_backup(
                vm_name="test-vm",
                resource_group="test-rg",
                weekly_retention=-1,
            )

    def test_backup_schedule_max_retention(self):
        """Test extremely large retention values."""
        # Should succeed - no upper limit enforced
        schedule = BackupSchedule(
            enabled=True,
            daily_retention=365,
            weekly_retention=52,
            monthly_retention=120,
        )

        assert schedule.daily_retention == 365
        assert schedule.weekly_retention == 52
        assert schedule.monthly_retention == 120

    def test_vm_name_empty_string(self):
        """Test empty VM name is rejected."""
        with pytest.raises(BackupError, match="Invalid VM name"):
            BackupManager.configure_backup(
                vm_name="",
                resource_group="test-rg",
            )

    def test_vm_name_max_length(self):
        """Test VM name at Azure 64-character limit."""
        # 64 characters is valid
        vm_name = "a" * 64
        with patch("azlin.modules.backup_manager.BackupManager._set_vm_tag"):
            BackupManager.configure_backup(
                vm_name=vm_name,
                resource_group="test-rg",
            )

    def test_vm_name_exceeds_max_length(self):
        """Test VM name exceeding 64-character limit."""
        # 65 characters should fail
        vm_name = "a" * 65
        with pytest.raises(BackupError, match="Invalid VM name"):
            BackupManager.configure_backup(
                vm_name=vm_name,
                resource_group="test-rg",
            )

    def test_resource_group_special_characters(self):
        """Test resource group with valid special characters."""
        # Azure allows: alphanumeric, underscore, hyphen, period, parentheses
        with patch("azlin.modules.backup_manager.BackupManager._set_vm_tag"):
            BackupManager.configure_backup(
                vm_name="test-vm",
                resource_group="my_rg-test.group(prod)",
            )

    def test_list_backups_no_tag_attribute(self):
        """Test handling snapshots without backup tags."""
        with patch("azlin.modules.backup_manager.SnapshotManager.list_snapshots") as mock_list:
            # Mock snapshot without tags
            mock_snapshot = Mock()
            mock_snapshot.tags = {}
            mock_list.return_value = [mock_snapshot]

            backups = BackupManager.list_backups(
                vm_name="test-vm",
                resource_group="test-rg",
            )

            # Should skip snapshots without backup tier tag
            assert len(backups) == 0


# ============================================================================
# ERROR HANDLING TESTS (Part of Unit Tests)
# ============================================================================


class TestErrorHandling:
    """Test error handling and exception cases."""

    @patch("azlin.modules.backup_manager.BackupManager._set_vm_tag")
    def test_configure_backup_tag_operation_fails(self, mock_set_tag):
        """Test error when VM tag operation fails."""
        mock_set_tag.side_effect = Exception("Azure API error")

        with pytest.raises(Exception, match="Azure API error"):
            BackupManager.configure_backup(
                vm_name="test-vm",
                resource_group="test-rg",
            )

    @patch("azlin.modules.backup_manager.BackupManager._get_vm_tag")
    @patch("azlin.modules.backup_manager.BackupManager._create_backup_snapshot")
    def test_trigger_backup_snapshot_creation_fails(self, mock_create, mock_get_tag):
        """Test error handling when snapshot creation fails."""
        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
        )
        mock_get_tag.return_value = schedule.to_tag_value()
        mock_create.side_effect = Exception("Snapshot creation failed")

        with pytest.raises(Exception, match="Snapshot creation failed"):
            BackupManager.trigger_backup(
                vm_name="test-vm",
                resource_group="test-rg",
            )

    @patch("azlin.modules.backup_manager.SnapshotManager.list_snapshots")
    def test_list_backups_api_error(self, mock_list):
        """Test error handling when listing snapshots fails."""
        mock_list.side_effect = Exception("Azure API timeout")

        with pytest.raises(Exception, match="Azure API timeout"):
            BackupManager.list_backups(
                vm_name="test-vm",
                resource_group="test-rg",
            )

    @patch("azlin.modules.backup_manager.BackupManager._get_vm_tag")
    @patch("azlin.modules.backup_manager.BackupManager.list_backups")
    @patch("azlin.modules.backup_manager.SnapshotManager.delete_snapshot")
    def test_cleanup_partial_failure(self, mock_delete, mock_list, mock_get_tag):
        """Test cleanup continues after individual deletion failure."""
        schedule = BackupSchedule(
            enabled=True,
            daily_retention=7,
            weekly_retention=4,
            monthly_retention=12,
        )
        mock_get_tag.return_value = schedule.to_tag_value()

        # Mock 10 expired backups
        now = datetime.now(UTC)
        backups = []
        for i in range(10):
            backups.append(BackupInfo(
                snapshot_name=f"vm1-backup-daily-{i}",
                vm_name="test-vm",
                resource_group="test-rg",
                creation_time=now - timedelta(days=i),
                retention_tier="daily",
            ))
        mock_list.return_value = backups

        # First deletion fails, others succeed
        mock_delete.side_effect = [
            Exception("Delete failed"),
            None,
            None,
        ]

        result = BackupManager.cleanup_expired_backups(
            vm_name="test-vm",
            resource_group="test-rg",
        )

        # Should continue and delete remaining backups
        assert result["daily"] == 2  # 2 succeeded out of 3 attempted
