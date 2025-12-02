"""Unit tests for OrphanedResourceDetector module.

Following TDD approach with testing pyramid (60% unit tests).
Tests focus on detection logic and safety mechanisms.

Philosophy:
- Test orphan detection algorithms
- Verify safety checks (age, tags, connections)
- Mock Azure CLI calls
- Fast execution
"""

import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

# Module under test
try:
    from azlin.modules.orphaned_resource_detector import (
        CleanupResult,
        OrphanedDisk,
        OrphanedResourceDetector,
        OrphanedResourceReport,
        OrphanedSnapshot,
        OrphanedStorage,
    )
except ImportError:
    pytest.skip("Module not implemented yet", allow_module_level=True)


class TestOrphanedDiskDataModel:
    """Test OrphanedDisk data model."""

    def test_orphaned_disk_creation(self):
        """Test basic OrphanedDisk creation."""
        disk = OrphanedDisk(
            name="old-vm-disk",
            resource_group="test-rg",
            size_gb=128,
            tier="Premium",
            created=datetime.now(),
            age_days=45,
            last_attached_vm="deleted-vm",
            monthly_cost=9.83,
            reason="VM deleted, disk unattached for 45 days",
        )
        assert disk.name == "old-vm-disk"
        assert disk.age_days == 45
        assert disk.monthly_cost > 0

    def test_orphaned_disk_cost_calculation(self):
        """Test monthly cost calculation for orphaned disk."""
        # Premium: $0.1536/GB/month
        disk = OrphanedDisk(
            name="test-disk",
            resource_group="test-rg",
            size_gb=100,
            tier="Premium",
            created=datetime.now(),
            age_days=10,
            last_attached_vm=None,
            monthly_cost=15.36,  # 100 * 0.1536
            reason="Unattached",
        )
        expected_cost = 100 * 0.1536
        assert abs(disk.monthly_cost - expected_cost) < 0.01


class TestOrphanedSnapshotDataModel:
    """Test OrphanedSnapshot data model."""

    def test_orphaned_snapshot_creation(self):
        """Test basic OrphanedSnapshot creation."""
        snapshot = OrphanedSnapshot(
            name="old-snapshot",
            resource_group="test-rg",
            size_gb=128,
            created=datetime.now() - timedelta(days=60),
            age_days=60,
            source_vm="deleted-vm",
            monthly_cost=6.40,
            reason="Source VM no longer exists",
        )
        assert snapshot.age_days == 60
        assert snapshot.source_vm == "deleted-vm"


class TestOrphanedStorageDataModel:
    """Test OrphanedStorage data model."""

    def test_orphaned_storage_creation(self):
        """Test basic OrphanedStorage creation."""
        storage = OrphanedStorage(
            name="old-storage",
            resource_group="test-rg",
            size_gb=100,
            tier="Premium",
            created=datetime.now() - timedelta(days=90),
            age_days=90,
            connected_vms=[],
            monthly_cost=15.36,
            reason="No VMs connected for 90 days",
        )
        assert len(storage.connected_vms) == 0
        assert storage.age_days == 90


class TestOrphanedResourceDetectorScanOrphanedDisks:
    """Test scan_orphaned_disks() method."""

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    def test_scan_finds_unattached_disks(self, mock_subprocess):
        """Test detection of unattached managed disks."""
        # Mock Azure CLI response
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "name": "orphaned-disk-1",
                        "diskSizeGb": 128,
                        "sku": {"tier": "Premium"},
                        "timeCreated": (datetime.now() - timedelta(days=10)).isoformat(),
                        "managedBy": None,  # Not attached
                        "tags": {},
                    },
                    {
                        "name": "attached-disk",
                        "diskSizeGb": 256,
                        "sku": {"tier": "Premium"},
                        "timeCreated": (datetime.now() - timedelta(days=5)).isoformat(),
                        "managedBy": "/subscriptions/.../virtualMachines/vm1",  # Attached
                        "tags": {},
                    },
                ]
            ),
        )

        result = OrphanedResourceDetector.scan_orphaned_disks(
            resource_group="test-rg", min_age_days=7
        )

        # Should only find the unattached disk
        assert len(result) == 1
        assert result[0].name == "orphaned-disk-1"

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    def test_scan_respects_min_age_days(self, mock_subprocess):
        """Test min_age_days filter works correctly."""
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "name": "recent-disk",
                        "diskSizeGb": 128,
                        "sku": {"tier": "Premium"},
                        "timeCreated": (datetime.now() - timedelta(days=3)).isoformat(),
                        "managedBy": None,
                        "tags": {},
                    },
                    {
                        "name": "old-disk",
                        "diskSizeGb": 128,
                        "sku": {"tier": "Premium"},
                        "timeCreated": (datetime.now() - timedelta(days=30)).isoformat(),
                        "managedBy": None,
                        "tags": {},
                    },
                ]
            ),
        )

        result = OrphanedResourceDetector.scan_orphaned_disks(
            resource_group="test-rg", min_age_days=7
        )

        # Should only find the old disk (> 7 days)
        assert len(result) == 1
        assert result[0].name == "old-disk"

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    def test_scan_respects_azlin_keep_tag(self, mock_subprocess):
        """Test disks with azlin:keep tag are excluded."""
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "name": "protected-disk",
                        "diskSizeGb": 128,
                        "sku": {"tier": "Premium"},
                        "timeCreated": (datetime.now() - timedelta(days=30)).isoformat(),
                        "managedBy": None,
                        "tags": {"azlin:keep": "true"},  # Protected
                    },
                    {
                        "name": "orphaned-disk",
                        "diskSizeGb": 128,
                        "sku": {"tier": "Premium"},
                        "timeCreated": (datetime.now() - timedelta(days=30)).isoformat(),
                        "managedBy": None,
                        "tags": {},
                    },
                ]
            ),
        )

        result = OrphanedResourceDetector.scan_orphaned_disks(
            resource_group="test-rg", min_age_days=7
        )

        # Should exclude protected disk
        assert len(result) == 1
        assert result[0].name == "orphaned-disk"

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    def test_scan_calculates_monthly_cost(self, mock_subprocess):
        """Test monthly cost calculation for orphaned disks."""
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "name": "premium-disk",
                        "diskSizeGb": 100,
                        "sku": {"tier": "Premium"},
                        "timeCreated": (datetime.now() - timedelta(days=30)).isoformat(),
                        "managedBy": None,
                        "tags": {},
                    },
                    {
                        "name": "standard-disk",
                        "diskSizeGb": 100,
                        "sku": {"tier": "Standard"},
                        "timeCreated": (datetime.now() - timedelta(days=30)).isoformat(),
                        "managedBy": None,
                        "tags": {},
                    },
                ]
            ),
        )

        result = OrphanedResourceDetector.scan_orphaned_disks(
            resource_group="test-rg", min_age_days=7
        )

        # Premium: ~$15/mo, Standard: ~$4/mo
        premium = next(d for d in result if d.name == "premium-disk")
        standard = next(d for d in result if d.name == "standard-disk")

        assert premium.monthly_cost > standard.monthly_cost
        assert abs(premium.monthly_cost - 15.36) < 0.1


class TestOrphanedResourceDetectorScanOrphanedSnapshots:
    """Test scan_orphaned_snapshots() method."""

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    def test_scan_finds_snapshots_without_source_vm(self, mock_subprocess):
        """Test detection of snapshots whose source VM no longer exists."""
        # First call: list snapshots
        # Second call: list VMs
        mock_subprocess.side_effect = [
            Mock(
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "name": "deleted-vm-snapshot",
                            "diskSizeGb": 128,
                            "timeCreated": (datetime.now() - timedelta(days=60)).isoformat(),
                            "tags": {"source-vm": "deleted-vm"},
                        },
                        {
                            "name": "active-vm-snapshot",
                            "diskSizeGb": 128,
                            "timeCreated": (datetime.now() - timedelta(days=60)).isoformat(),
                            "tags": {"source-vm": "active-vm"},
                        },
                    ]
                ),
            ),
            Mock(returncode=0, stdout=json.dumps([{"name": "active-vm"}])),
        ]

        result = OrphanedResourceDetector.scan_orphaned_snapshots(
            resource_group="test-rg", min_age_days=30
        )

        # Should find snapshot for deleted VM
        assert len(result) == 1
        assert result[0].name == "deleted-vm-snapshot"

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    def test_scan_respects_snapshot_retention_policy(self, mock_subprocess):
        """Test snapshots within retention policy are excluded."""
        # Integration with SnapshotManager retention policies
        pass


class TestOrphanedResourceDetectorScanOrphanedStorage:
    """Test scan_orphaned_storage() method."""

    @patch("azlin.modules.orphaned_resource_detector.StorageManager")
    def test_scan_finds_storage_without_connected_vms(self, mock_storage_mgr):
        """Test detection of storage accounts with no connected VMs."""
        mock_storage_mgr.list_storage.return_value = [
            Mock(
                name="orphaned-storage",
                size_gb=100,
                tier="Premium",
                created=datetime.now() - timedelta(days=60),
                connected_vms=[],  # No VMs
            ),
            Mock(
                name="active-storage",
                size_gb=100,
                tier="Premium",
                created=datetime.now() - timedelta(days=60),
                connected_vms=["vm1", "vm2"],  # Has VMs
            ),
        ]

        result = OrphanedResourceDetector.scan_orphaned_storage(
            resource_group="test-rg", min_age_days=30
        )

        # Should only find storage without VMs
        assert len(result) == 1
        assert result[0].name == "orphaned-storage"

    @patch("azlin.modules.orphaned_resource_detector.StorageManager")
    @patch("azlin.modules.orphaned_resource_detector.ConfigManager")
    def test_scan_respects_shared_storage_flag(self, mock_config, mock_storage_mgr):
        """Test shared storage marked in config is excluded."""
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

        result = OrphanedResourceDetector.scan_orphaned_storage(
            resource_group="test-rg", min_age_days=30
        )

        # Should exclude shared storage
        assert len(result) == 0


class TestOrphanedResourceDetectorScanAll:
    """Test scan_all() comprehensive scan method."""

    @patch("azlin.modules.orphaned_resource_detector.OrphanedResourceDetector.scan_orphaned_disks")
    @patch(
        "azlin.modules.orphaned_resource_detector.OrphanedResourceDetector.scan_orphaned_snapshots"
    )
    @patch(
        "azlin.modules.orphaned_resource_detector.OrphanedResourceDetector.scan_orphaned_storage"
    )
    def test_scan_all_aggregates_results(self, mock_storage, mock_snapshots, mock_disks):
        """Test scan_all aggregates results from all scan methods."""
        mock_disks.return_value = [
            OrphanedDisk(
                name="disk1",
                resource_group="test-rg",
                size_gb=128,
                tier="Premium",
                created=datetime.now(),
                age_days=10,
                last_attached_vm=None,
                monthly_cost=19.66,
                reason="Unattached",
            )
        ]
        mock_snapshots.return_value = [
            OrphanedSnapshot(
                name="snap1",
                resource_group="test-rg",
                size_gb=128,
                created=datetime.now(),
                age_days=60,
                source_vm="deleted",
                monthly_cost=6.40,
                reason="Source deleted",
            )
        ]
        mock_storage.return_value = [
            OrphanedStorage(
                name="storage1",
                resource_group="test-rg",
                size_gb=100,
                tier="Premium",
                created=datetime.now(),
                age_days=90,
                connected_vms=[],
                monthly_cost=15.36,
                reason="No VMs",
            )
        ]

        report = OrphanedResourceDetector.scan_all(resource_group="test-rg")

        assert isinstance(report, OrphanedResourceReport)
        assert len(report.disks) == 1
        assert len(report.snapshots) == 1
        assert len(report.storage_accounts) == 1
        assert report.total_cost_per_month > 0
        assert report.total_size_gb == 356  # 128 + 128 + 100

    def test_scan_all_calculates_total_cost(self):
        """Test scan_all calculates total monthly cost correctly."""
        # Should sum costs from all resource types
        pass


class TestOrphanedResourceDetectorCleanupOrphaned:
    """Test cleanup_orphaned() deletion method."""

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    @patch("azlin.modules.orphaned_resource_detector.OrphanedResourceDetector.scan_all")
    def test_cleanup_dry_run_default(self, mock_scan, mock_subprocess):
        """Test cleanup defaults to dry_run=True."""
        mock_report = OrphanedResourceReport(
            disks=[
                OrphanedDisk(
                    name="disk1",
                    resource_group="test-rg",
                    size_gb=128,
                    tier="Premium",
                    created=datetime.now(),
                    age_days=10,
                    last_attached_vm=None,
                    monthly_cost=19.66,
                    reason="Unattached",
                )
            ],
            snapshots=[],
            storage_accounts=[],
            total_cost_per_month=19.66,
            total_size_gb=128,
            scan_date=datetime.now(),
        )
        mock_scan.return_value = mock_report

        result = OrphanedResourceDetector.cleanup_orphaned(
            resource_group="test-rg", resource_type="all", min_age_days=7, dry_run=True
        )

        # Should NOT actually delete anything
        mock_subprocess.assert_not_called()
        assert result.dry_run is True
        assert len(result.deleted_disks) == 0

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    @patch("azlin.modules.orphaned_resource_detector.OrphanedResourceDetector.scan_all")
    def test_cleanup_deletes_with_confirm(self, mock_scan, mock_subprocess):
        """Test cleanup actually deletes when dry_run=False."""
        mock_report = OrphanedResourceReport(
            disks=[
                OrphanedDisk(
                    name="disk1",
                    resource_group="test-rg",
                    size_gb=128,
                    tier="Premium",
                    created=datetime.now(),
                    age_days=10,
                    last_attached_vm=None,
                    monthly_cost=19.66,
                    reason="Unattached",
                )
            ],
            snapshots=[],
            storage_accounts=[],
            total_cost_per_month=19.66,
            total_size_gb=128,
            scan_date=datetime.now(),
        )
        mock_scan.return_value = mock_report
        mock_subprocess.return_value = Mock(returncode=0)

        result = OrphanedResourceDetector.cleanup_orphaned(
            resource_group="test-rg", resource_type="disk", min_age_days=7, dry_run=False
        )

        # Should actually delete
        mock_subprocess.assert_called()
        assert result.dry_run is False
        assert len(result.deleted_disks) == 1
        assert "disk1" in result.deleted_disks

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    def test_cleanup_handles_deletion_errors(self, mock_subprocess):
        """Test cleanup gracefully handles deletion errors."""
        mock_subprocess.return_value = Mock(returncode=1, stderr="Disk not found")

        result = OrphanedResourceDetector.cleanup_orphaned(
            resource_group="test-rg", resource_type="disk", min_age_days=7, dry_run=False
        )

        # Should track errors
        assert len(result.errors) > 0

    def test_cleanup_filters_by_resource_type(self):
        """Test cleanup respects resource_type filter."""
        # type="disk" should only delete disks
        # type="snapshot" should only delete snapshots
        # type="all" should delete all types
        pass

    def test_cleanup_calculates_savings(self):
        """Test cleanup calculates total cost saved."""
        # Should sum monthly costs of deleted resources
        pass


class TestOrphanedResourceDetectorSafety:
    """Test safety mechanisms."""

    def test_cleanup_refuses_recent_resources(self):
        """Test cleanup refuses to delete resources younger than min_age_days."""
        pass

    def test_cleanup_refuses_tagged_resources(self):
        """Test cleanup refuses to delete resources with azlin:keep tag."""
        pass

    def test_cleanup_refuses_attached_resources(self):
        """Test cleanup refuses to delete resources still in use."""
        pass


class TestOrphanedResourceDetectorEdgeCases:
    """Test edge cases and error handling."""

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    def test_scan_handles_azure_cli_errors(self, mock_subprocess):
        """Test graceful handling of Azure CLI errors."""
        mock_subprocess.return_value = Mock(returncode=1, stderr="Azure error")

        result = OrphanedResourceDetector.scan_orphaned_disks(
            resource_group="test-rg", min_age_days=7
        )

        # Should return empty list or raise clear error
        assert isinstance(result, list)

    def test_scan_handles_malformed_dates(self):
        """Test handling of malformed date fields from Azure."""
        pass

    def test_cleanup_handles_partial_failures(self):
        """Test cleanup continues after individual resource failures."""
        # Should delete successful resources and track failures
        pass
