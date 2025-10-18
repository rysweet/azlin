"""Unit tests for snapshot_manager module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from azlin.snapshot_manager import SnapshotInfo, SnapshotManager, SnapshotManagerError


class TestSnapshotInfo:
    """Tests for SnapshotInfo dataclass."""

    def test_snapshot_info_creation(self):
        """Test SnapshotInfo object creation."""
        snapshot = SnapshotInfo(
            name="azlin-test-snapshot-20251015-053000",
            vm_name="azlin-test",
            resource_group="test-rg",
            disk_name="azlin-test_OsDisk_1",
            size_gb=30,
            created_time="2025-10-15T05:30:00Z",
            location="eastus",
            provisioning_state="Succeeded",
        )
        assert snapshot.name == "azlin-test-snapshot-20251015-053000"
        assert snapshot.vm_name == "azlin-test"
        assert snapshot.size_gb == 30


class TestSnapshotManager:
    """Tests for SnapshotManager class."""

    @patch("azlin.snapshot_manager.subprocess.run")
    def test_create_snapshot_success(self, mock_run):
        """Test successful snapshot creation."""
        # Mock VM details
        vm_output = json.dumps(
            {
                "name": "azlin-test",
                "storageProfile": {
                    "osDisk": {
                        "name": "azlin-test_OsDisk_1",
                        "diskSizeGb": 30,
                        "managedDisk": {
                            "id": "/subscriptions/sub123/resourceGroups/test-rg/providers/Microsoft.Compute/disks/azlin-test_OsDisk_1"
                        },
                    }
                },
                "location": "eastus",
            }
        )

        # Mock snapshot creation - use a pattern that matches any timestamp
        snapshot_output = json.dumps(
            {
                "name": "azlin-test-snapshot-20251015-053000",
                "diskSizeGb": 30,
                "provisioningState": "Succeeded",
                "timeCreated": "2025-10-15T05:30:00Z",
            }
        )

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=vm_output, stderr=""),  # VM show
            MagicMock(returncode=0, stdout=snapshot_output, stderr=""),  # Snapshot create
        ]

        manager = SnapshotManager()
        snapshot = manager.create_snapshot("azlin-test", "test-rg")

        # Check that snapshot name starts with the VM name
        assert snapshot.name.startswith("azlin-test-snapshot-")
        assert snapshot.vm_name == "azlin-test"
        assert snapshot.size_gb == 30
        assert mock_run.call_count == 2

    @patch("azlin.snapshot_manager.subprocess.run")
    def test_create_snapshot_vm_not_found(self, mock_run):
        """Test snapshot creation when VM doesn't exist."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="ResourceNotFound")

        manager = SnapshotManager()
        with pytest.raises(SnapshotManagerError, match="VM .* not found"):
            manager.create_snapshot("nonexistent-vm", "test-rg")

    @patch("azlin.snapshot_manager.subprocess.run")
    def test_list_snapshots_success(self, mock_run):
        """Test successful snapshot listing."""
        mock_output = json.dumps(
            [
                {
                    "name": "azlin-test-snapshot-20251015-053000",
                    "diskSizeGb": 30,
                    "provisioningState": "Succeeded",
                    "timeCreated": "2025-10-15T05:30:00Z",
                    "location": "eastus",
                    "tags": {"azlin-vm": "azlin-test", "azlin-disk": "azlin-test_OsDisk_1"},
                },
                {
                    "name": "azlin-test-snapshot-20251014-120000",
                    "diskSizeGb": 30,
                    "provisioningState": "Succeeded",
                    "timeCreated": "2025-10-14T12:00:00Z",
                    "location": "eastus",
                    "tags": {"azlin-vm": "azlin-test", "azlin-disk": "azlin-test_OsDisk_1"},
                },
            ]
        )

        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output, stderr="")

        manager = SnapshotManager()
        snapshots = manager.list_snapshots("azlin-test", "test-rg")

        assert len(snapshots) == 2
        assert snapshots[0].name == "azlin-test-snapshot-20251015-053000"
        assert snapshots[1].name == "azlin-test-snapshot-20251014-120000"

    @patch("azlin.snapshot_manager.subprocess.run")
    def test_list_snapshots_empty(self, mock_run):
        """Test listing snapshots when none exist."""
        mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")

        manager = SnapshotManager()
        snapshots = manager.list_snapshots("azlin-test", "test-rg")

        assert len(snapshots) == 0

    @patch("azlin.snapshot_manager.subprocess.run")
    def test_delete_snapshot_success(self, mock_run):
        """Test successful snapshot deletion."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        manager = SnapshotManager()
        manager.delete_snapshot("azlin-test-snapshot-20251015-053000", "test-rg")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "az" in args
        assert "snapshot" in args
        assert "delete" in args
        assert "azlin-test-snapshot-20251015-053000" in args

    @patch("azlin.snapshot_manager.subprocess.run")
    def test_delete_snapshot_not_found(self, mock_run):
        """Test snapshot deletion when snapshot doesn't exist."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="ResourceNotFound")

        manager = SnapshotManager()
        with pytest.raises(SnapshotManagerError, match="Snapshot .* not found"):
            manager.delete_snapshot("nonexistent-snapshot", "test-rg")

    @patch("azlin.snapshot_manager.subprocess.run")
    def test_restore_snapshot_success(self, mock_run):
        """Test successful snapshot restoration."""
        # Mock snapshot details
        snapshot_output = json.dumps(
            {
                "name": "azlin-test-snapshot-20251015-053000",
                "diskSizeGb": 30,
                "id": "/subscriptions/sub123/resourceGroups/test-rg/providers/Microsoft.Compute/snapshots/azlin-test-snapshot-20251015-053000",
            }
        )

        # Mock VM details
        vm_output = json.dumps(
            {
                "name": "azlin-test",
                "storageProfile": {
                    "osDisk": {
                        "name": "azlin-test_OsDisk_1",
                        "managedDisk": {
                            "id": "/subscriptions/sub123/resourceGroups/test-rg/providers/Microsoft.Compute/disks/azlin-test_OsDisk_1"
                        },
                    }
                },
            }
        )

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=snapshot_output, stderr=""),  # Snapshot show
            MagicMock(returncode=0, stdout=vm_output, stderr=""),  # VM show
            MagicMock(returncode=0, stdout="", stderr=""),  # VM deallocate
            MagicMock(returncode=0, stdout="", stderr=""),  # Disk delete
            MagicMock(returncode=0, stdout="", stderr=""),  # Disk create from snapshot
            MagicMock(returncode=0, stdout="", stderr=""),  # VM update
            MagicMock(returncode=0, stdout="", stderr=""),  # VM start
        ]

        manager = SnapshotManager()
        manager.restore_snapshot("azlin-test", "azlin-test-snapshot-20251015-053000", "test-rg")

        assert mock_run.call_count == 7

    @patch("azlin.snapshot_manager.subprocess.run")
    def test_restore_snapshot_not_found(self, mock_run):
        """Test restoration when snapshot doesn't exist."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="ResourceNotFound")

        manager = SnapshotManager()
        with pytest.raises(SnapshotManagerError, match="Snapshot .* not found"):
            manager.restore_snapshot("azlin-test", "nonexistent-snapshot", "test-rg")

    def test_get_snapshot_cost_estimate(self):
        """Test cost estimation calculation."""
        manager = SnapshotManager()

        # 30 GB for 30 days at $0.05 per GB-month
        cost = manager.get_snapshot_cost_estimate(30, 30)
        assert cost == pytest.approx(1.50, rel=0.01)

        # 100 GB for 7 days
        cost = manager.get_snapshot_cost_estimate(100, 7)
        assert cost == pytest.approx(1.16, rel=0.01)

    def test_generate_snapshot_name(self):
        """Test snapshot name generation."""
        manager = SnapshotManager()
        name = manager._generate_snapshot_name("azlin-test")

        assert name.startswith("azlin-test-snapshot-")
        assert len(name) > len("azlin-test-snapshot-")

    @patch("azlin.snapshot_manager.subprocess.run")
    def test_create_snapshot_with_cost_warning(self, mock_run):
        """Test that snapshot creation shows cost estimate."""
        # Mock large disk (500 GB)
        vm_output = json.dumps(
            {
                "name": "azlin-large",
                "storageProfile": {
                    "osDisk": {
                        "name": "azlin-large_OsDisk_1",
                        "diskSizeGb": 500,
                        "managedDisk": {
                            "id": "/subscriptions/sub123/resourceGroups/test-rg/providers/Microsoft.Compute/disks/azlin-large_OsDisk_1"
                        },
                    }
                },
                "location": "eastus",
            }
        )

        mock_run.return_value = MagicMock(returncode=0, stdout=vm_output, stderr="")

        manager = SnapshotManager()

        # Just verify we can get the disk size for cost estimation
        # Cost warning would be shown in CLI layer
        with patch.object(manager, "create_snapshot") as mock_create:
            mock_create.return_value = SnapshotInfo(
                name="test-snapshot",
                vm_name="azlin-large",
                resource_group="test-rg",
                disk_name="azlin-large_OsDisk_1",
                size_gb=500,
                created_time="2025-10-15T05:30:00Z",
                location="eastus",
                provisioning_state="Succeeded",
            )

            snapshot = manager.create_snapshot("azlin-large", "test-rg")
            cost = manager.get_snapshot_cost_estimate(snapshot.size_gb, 30)
            assert cost > 0
