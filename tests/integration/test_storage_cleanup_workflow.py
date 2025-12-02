"""Integration tests for orphaned resource cleanup workflow.

Tests interaction between OrphanedResourceDetector, StorageManager, and safety mechanisms.

Testing pyramid: 30% integration tests
"""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

try:
    from azlin.modules.orphaned_resource_detector import OrphanedResourceDetector
    from azlin.modules.snapshot_manager import SnapshotManager
    from azlin.modules.storage_manager import StorageManager
except ImportError:
    pytest.skip("Modules not implemented yet", allow_module_level=True)


class TestCleanupRespectsSafety:
    """Test cleanup respects safety mechanisms."""

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    def test_cleanup_respects_azlin_keep_tag(self, mock_subprocess):
        """Test cleanup does not delete resources with azlin:keep tag."""
        # Mock disk list with protected resource
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout='[{"name": "protected-disk", "managedBy": null, "diskSizeGb": 128, "sku": {"tier": "Premium"}, "timeCreated": "2025-01-01T00:00:00", "tags": {"azlin:keep": "true"}}]',
        )

        # Scan for orphaned resources
        orphaned = OrphanedResourceDetector.scan_orphaned_disks(
            resource_group="test-rg", min_age_days=1
        )

        # Should find nothing (protected resource excluded)
        assert len(orphaned) == 0

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    def test_cleanup_removes_old_orphaned_disk(self, mock_subprocess):
        """Test cleanup removes genuinely orphaned disks."""
        # Mock disk list with old unattached disk
        old_date = (datetime.now() - timedelta(days=30)).isoformat()
        mock_subprocess.side_effect = [
            Mock(
                returncode=0,
                stdout=f'[{{"name": "old-disk", "managedBy": null, "diskSizeGb": 128, "sku": {{"tier": "Premium"}}, "timeCreated": "{old_date}", "tags": {{}}}}]',
            ),
            Mock(returncode=0),  # Delete command
        ]

        # Cleanup
        result = OrphanedResourceDetector.cleanup_orphaned(
            resource_group="test-rg", resource_type="disk", min_age_days=7, dry_run=False
        )

        # Should delete the disk
        assert len(result.deleted_disks) == 1
        assert "old-disk" in result.deleted_disks

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    def test_cleanup_respects_min_age_days(self, mock_subprocess):
        """Test cleanup respects minimum age requirement."""
        # Mock disk list with recent disk
        recent_date = (datetime.now() - timedelta(days=3)).isoformat()
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=f'[{{"name": "recent-disk", "managedBy": null, "diskSizeGb": 128, "sku": {{"tier": "Premium"}}, "timeCreated": "{recent_date}", "tags": {{}}}}]',
        )

        # Scan with min_age_days=7
        orphaned = OrphanedResourceDetector.scan_orphaned_disks(
            resource_group="test-rg", min_age_days=7
        )

        # Should find nothing (too recent)
        assert len(orphaned) == 0

    @patch("azlin.modules.orphaned_resource_detector.StorageManager")
    @patch("azlin.modules.orphaned_resource_detector.ConfigManager")
    def test_cleanup_respects_shared_storage_flag(self, mock_config, mock_storage_mgr):
        """Test cleanup does not delete shared storage."""
        mock_storage_mgr.list_storage.return_value = [
            Mock(
                name="shared-storage",
                size_gb=100,
                tier="Premium",
                created=datetime.now() - timedelta(days=60),
                connected_vms=[],
            )
        ]

        mock_config.is_shared_storage.return_value = True

        # Scan for orphaned storage
        orphaned = OrphanedResourceDetector.scan_orphaned_storage(
            resource_group="test-rg", min_age_days=30
        )

        # Should find nothing (shared storage excluded)
        assert len(orphaned) == 0


class TestCleanupUpdatesMetrics:
    """Test cleanup updates cost and usage metrics."""

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    def test_cleanup_calculates_cost_savings(self, mock_subprocess):
        """Test cleanup calculates total cost saved."""
        old_date = (datetime.now() - timedelta(days=30)).isoformat()
        mock_subprocess.side_effect = [
            Mock(
                returncode=0,
                stdout=f'[{{"name": "disk1", "managedBy": null, "diskSizeGb": 100, "sku": {{"tier": "Premium"}}, "timeCreated": "{old_date}", "tags": {{}}}}]',
            ),
            Mock(returncode=0),  # Delete
        ]

        result = OrphanedResourceDetector.cleanup_orphaned(
            resource_group="test-rg", resource_type="disk", min_age_days=7, dry_run=False
        )

        # Should calculate savings: 100 GB Premium = ~$15.36/month
        assert result.total_cost_saved_per_month > 15.0
        assert result.total_cost_saved_per_month < 16.0

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    def test_cleanup_calculates_space_freed(self, mock_subprocess):
        """Test cleanup calculates total space freed."""
        old_date = (datetime.now() - timedelta(days=30)).isoformat()
        mock_subprocess.side_effect = [
            Mock(
                returncode=0,
                stdout=f'[{{"name": "disk1", "managedBy": null, "diskSizeGb": 128, "sku": {{"tier": "Premium"}}, "timeCreated": "{old_date}", "tags": {{}}}}, {{"name": "disk2", "managedBy": null, "diskSizeGb": 256, "sku": {{"tier": "Standard"}}, "timeCreated": "{old_date}", "tags": {{}}}}]',
            ),
            Mock(returncode=0),  # Delete disk1
            Mock(returncode=0),  # Delete disk2
        ]

        result = OrphanedResourceDetector.cleanup_orphaned(
            resource_group="test-rg", resource_type="disk", min_age_days=7, dry_run=False
        )

        # Should calculate total: 128 + 256 = 384 GB
        assert result.total_size_freed_gb == 384


class TestCleanupIntegrationWithSnapshotManager:
    """Test cleanup integration with SnapshotManager retention policies."""

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    @patch("azlin.modules.orphaned_resource_detector.SnapshotManager")
    def test_cleanup_respects_snapshot_retention_policy(self, mock_snapshot_mgr, mock_subprocess):
        """Test cleanup respects SnapshotManager retention policies."""
        # Mock snapshot list
        old_date = (datetime.now() - timedelta(days=40)).isoformat()
        mock_subprocess.side_effect = [
            Mock(
                returncode=0,
                stdout=f'[{{"name": "snapshot1", "diskSizeGb": 128, "timeCreated": "{old_date}", "tags": {{"source-vm": "vm1"}}}}]',
            ),
            Mock(returncode=0, stdout='[{"name": "vm1"}]'),  # VM still exists
        ]

        # Mock retention policy
        mock_snapshot_mgr.get_retention_policy.return_value = Mock(retain_count=5, retain_days=90)

        mock_snapshot_mgr.is_within_retention.return_value = True

        # Scan for orphaned snapshots
        orphaned = OrphanedResourceDetector.scan_orphaned_snapshots(
            resource_group="test-rg", min_age_days=30
        )

        # Should find nothing (within retention policy)
        assert len(orphaned) == 0

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    @patch("azlin.modules.orphaned_resource_detector.SnapshotManager")
    def test_cleanup_deletes_snapshots_beyond_retention(self, mock_snapshot_mgr, mock_subprocess):
        """Test cleanup deletes snapshots beyond retention policy."""
        # Mock old snapshot beyond retention
        old_date = (datetime.now() - timedelta(days=120)).isoformat()
        mock_subprocess.side_effect = [
            Mock(
                returncode=0,
                stdout=f'[{{"name": "old-snapshot", "diskSizeGb": 128, "timeCreated": "{old_date}", "tags": {{"source-vm": "deleted-vm"}}}}]',
            ),
            Mock(returncode=0, stdout="[]"),  # No VMs
            Mock(returncode=0),  # Delete
        ]

        mock_snapshot_mgr.is_within_retention.return_value = False

        result = OrphanedResourceDetector.cleanup_orphaned(
            resource_group="test-rg", resource_type="snapshot", min_age_days=30, dry_run=False
        )

        # Should delete the snapshot
        assert len(result.deleted_snapshots) == 1


class TestCleanupDryRunMode:
    """Test dry-run mode behavior."""

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    def test_dry_run_shows_what_would_be_deleted(self, mock_subprocess):
        """Test dry-run shows resources without deleting."""
        old_date = (datetime.now() - timedelta(days=30)).isoformat()
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=f'[{{"name": "disk1", "managedBy": null, "diskSizeGb": 128, "sku": {{"tier": "Premium"}}, "timeCreated": "{old_date}", "tags": {{}}}}]',
        )

        result = OrphanedResourceDetector.cleanup_orphaned(
            resource_group="test-rg", resource_type="disk", min_age_days=7, dry_run=True
        )

        # Should report what would be deleted
        assert result.dry_run is True
        assert len(result.deleted_disks) == 0  # Nothing actually deleted

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    def test_dry_run_default_is_true(self, mock_subprocess):
        """Test cleanup defaults to dry_run=True for safety."""
        old_date = (datetime.now() - timedelta(days=30)).isoformat()
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=f'[{{"name": "disk1", "managedBy": null, "diskSizeGb": 128, "sku": {{"tier": "Premium"}}, "timeCreated": "{old_date}", "tags": {{}}}}]',
        )

        result = OrphanedResourceDetector.cleanup_orphaned(
            resource_group="test-rg",
            resource_type="disk",
            min_age_days=7,
            # No dry_run parameter - should default to True
        )

        assert result.dry_run is True


class TestCleanupErrorHandling:
    """Test cleanup error handling and partial failures."""

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    def test_cleanup_continues_after_individual_failures(self, mock_subprocess):
        """Test cleanup continues after individual resource failures."""
        old_date = (datetime.now() - timedelta(days=30)).isoformat()
        mock_subprocess.side_effect = [
            Mock(
                returncode=0,
                stdout=f'[{{"name": "disk1", "managedBy": null, "diskSizeGb": 128, "sku": {{"tier": "Premium"}}, "timeCreated": "{old_date}", "tags": {{}}}}, {{"name": "disk2", "managedBy": null, "diskSizeGb": 256, "sku": {{"tier": "Standard"}}, "timeCreated": "{old_date}", "tags": {{}}}}]',
            ),
            Mock(returncode=1, stderr="Disk1 not found"),  # First delete fails
            Mock(returncode=0),  # Second delete succeeds
        ]

        result = OrphanedResourceDetector.cleanup_orphaned(
            resource_group="test-rg", resource_type="disk", min_age_days=7, dry_run=False
        )

        # Should delete disk2 despite disk1 failure
        assert len(result.deleted_disks) == 1
        assert "disk2" in result.deleted_disks
        # Should track the error
        assert len(result.errors) == 1

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    def test_cleanup_handles_azure_cli_errors_gracefully(self, mock_subprocess):
        """Test cleanup handles Azure CLI errors gracefully."""
        mock_subprocess.return_value = Mock(
            returncode=1, stderr="Azure error: Resource group not found"
        )

        result = OrphanedResourceDetector.cleanup_orphaned(
            resource_group="nonexistent-rg", resource_type="disk", min_age_days=7, dry_run=False
        )

        # Should return result with error
        assert len(result.errors) > 0
        assert len(result.deleted_disks) == 0


class TestCleanupAuditLogging:
    """Test cleanup operations are logged for audit."""

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    @patch("azlin.modules.orphaned_resource_detector.Path")
    def test_cleanup_logs_deletions(self, mock_path, mock_subprocess):
        """Test cleanup logs all deletions."""
        # Should log to ~/.azlin/logs/cleanup_audit.log
        # Format: timestamp | resource_type | resource_name | size_gb | cost_saved
        pass

    def test_cleanup_log_includes_dry_run_flag(self):
        """Test cleanup log indicates dry-run vs actual deletion."""
        # Dry-run should be clearly marked in logs
        pass
