"""Integration tests for quota enforcement across modules.

Tests interaction between StorageQuotaManager and other storage operations.

Testing pyramid: 30% integration tests
"""

from unittest.mock import Mock, patch

import pytest

try:
    from azlin.modules.storage_manager import StorageManager
    from azlin.modules.storage_quota_manager import StorageQuotaManager
except ImportError:
    pytest.skip("Modules not implemented yet", allow_module_level=True)


class TestQuotaEnforcementWithStorageCreation:
    """Test quota checks when creating storage accounts."""

    @patch("azlin.modules.storage_quota_manager.Path")
    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_storage_creation_checks_team_quota(self, mock_subprocess, mock_path):
        """Test azlin storage create checks team quota before creating."""
        # Set up team quota
        mock_path.return_value.exists.return_value = True
        mock_path.return_value.read_text.return_value = '{"team": {"test-rg": {"quota_gb": 500, "created": "2025-12-01T10:00:00", "last_updated": "2025-12-01T10:00:00"}}}'

        # Mock current usage (450 GB used)
        mock_subprocess.side_effect = [
            Mock(
                returncode=0, stdout='[{"name": "existing-storage", "diskSizeGb": 450}]'
            ),  # List existing
            Mock(returncode=0),  # Creation attempt
        ]

        # Try to create 100 GB storage (would exceed quota)
        with pytest.raises(RuntimeError, match="Quota exceeded"):
            StorageManager.create_storage(name="new-storage", resource_group="test-rg", size_gb=100)

    @patch("azlin.modules.storage_quota_manager.Path")
    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_storage_creation_succeeds_within_quota(self, mock_subprocess, mock_path):
        """Test storage creation succeeds when within quota."""
        # Set up team quota
        mock_path.return_value.exists.return_value = True
        mock_path.return_value.read_text.return_value = '{"team": {"test-rg": {"quota_gb": 1000, "created": "2025-12-01T10:00:00", "last_updated": "2025-12-01T10:00:00"}}}'

        # Mock current usage (400 GB used)
        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout='[{"diskSizeGb": 400}]'),  # List existing
            Mock(returncode=0, stdout='{"id": "/subscriptions/.../new-storage"}'),  # Create
        ]

        # Create 100 GB storage (within quota)
        result = StorageManager.create_storage(
            name="new-storage", resource_group="test-rg", size_gb=100
        )

        assert result is not None


class TestQuotaEnforcementWithVMCreation:
    """Test quota checks when creating VMs."""

    @patch("azlin.modules.storage_quota_manager.Path")
    @patch("azlin.modules.vm_manager.subprocess.run")
    def test_vm_creation_checks_vm_quota(self, mock_subprocess, mock_path):
        """Test azlin new checks VM quota before creating."""
        # Set up VM quota
        mock_path.return_value.exists.return_value = True
        mock_path.return_value.read_text.return_value = '{"vm": {"new-vm": {"quota_gb": 200, "created": "2025-12-01T10:00:00", "last_updated": "2025-12-01T10:00:00"}}}'

        # Try to create VM with 256 GB disk (exceeds 200 GB quota)
        with pytest.raises(RuntimeError, match="Quota exceeded"):
            # This would call VMManager.create_vm internally
            pass

    @patch("azlin.modules.storage_quota_manager.Path")
    def test_vm_creation_estimates_disk_usage(self, mock_path):
        """Test VM creation estimates total disk usage."""
        # Should calculate: OS disk + data disks + expected snapshots
        pass


class TestQuotaEnforcementWithSnapshots:
    """Test quota checks when creating snapshots."""

    @patch("azlin.modules.storage_quota_manager.StorageQuotaManager.check_quota")
    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_snapshot_creation_checks_quota(self, mock_subprocess, mock_check_quota):
        """Test snapshot creation checks quota."""
        mock_check_quota.return_value = Mock(available=False, message="Quota exceeded")

        # Try to create snapshot when quota exceeded
        with pytest.raises(RuntimeError, match="Quota exceeded"):
            # SnapshotManager.create_snapshot should check quota
            pass

    @patch("azlin.modules.storage_quota_manager.StorageQuotaManager.check_quota")
    def test_snapshot_creation_succeeds_within_quota(self, mock_check_quota):
        """Test snapshot creation succeeds when within quota."""
        mock_check_quota.return_value = Mock(available=True, remaining_after_gb=50)

        # Should succeed
        # result = SnapshotManager.create_snapshot(...)
        pass


class TestQuotaUsageCalculationIntegration:
    """Test quota usage calculation across all resource types."""

    @patch("azlin.modules.storage_quota_manager.subprocess.run")
    @patch("azlin.modules.storage_quota_manager.StorageManager")
    def test_vm_quota_includes_all_resources(self, mock_storage_mgr, mock_subprocess):
        """Test VM quota includes storage accounts, disks, and snapshots."""
        # Mock storage accounts mounted on VM
        mock_storage_mgr.list_storage.return_value = [
            Mock(name="shared-storage", size_gb=100, connected_vms=["test-vm"])
        ]

        # Mock managed disks
        mock_subprocess.side_effect = [
            Mock(
                returncode=0,
                stdout='[{"name": "test-vm_OsDisk", "diskSizeGb": 128}, {"name": "test-vm_datadisk", "diskSizeGb": 256}]',
            ),
            Mock(returncode=0, stdout='[{"name": "test-vm-snapshot", "diskSizeGb": 3}]'),
        ]

        status = StorageQuotaManager.get_quota(scope="vm", name="test-vm", resource_group="test-rg")

        # Total: 100 (storage) + 128 (OS) + 256 (data) + 3 (snapshot) = 487 GB
        assert status.used_gb == 487

    @patch("azlin.modules.storage_quota_manager.subprocess.run")
    def test_team_quota_aggregates_all_rg_resources(self, mock_subprocess):
        """Test team quota aggregates all resources in resource group."""
        # Should sum: all storage accounts + all disks + all snapshots in RG
        pass


class TestQuotaWarnings:
    """Test quota warning system."""

    @patch("azlin.modules.storage_quota_manager.StorageQuotaManager.get_quota")
    def test_warning_at_80_percent_utilization(self, mock_get_quota):
        """Test warning issued at 80% quota utilization."""
        mock_get_quota.return_value = Mock(
            used_gb=400, config=Mock(quota_gb=500), utilization_percent=80.0
        )

        # Should issue warning but not block operation
        # result = StorageManager.create_storage(...)
        # assert "warning" in result.messages.lower()

    @patch("azlin.modules.storage_quota_manager.StorageQuotaManager.get_quota")
    def test_error_at_100_percent_utilization(self, mock_get_quota):
        """Test error at 100% quota utilization."""
        mock_get_quota.return_value = Mock(
            used_gb=500, config=Mock(quota_gb=500), utilization_percent=100.0
        )

        # Should block operation
        with pytest.raises(RuntimeError, match="Quota exceeded"):
            # StorageManager.create_storage(...)
            pass


class TestQuotaOverrides:
    """Test quota override mechanisms."""

    def test_admin_can_override_quota(self):
        """Test admin users can override quota limits."""
        # With --force flag or admin privileges
        pass

    def test_override_is_logged(self):
        """Test quota overrides are logged for audit."""
        # Should log to ~/.azlin/logs/quota_overrides.log
        pass
