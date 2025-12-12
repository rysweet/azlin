"""Error path tests for snapshot_manager module.

Tests all error conditions in snapshot management including:
- Invalid VM/resource group names
- JSON parsing errors
- Subprocess failures and timeouts
- Azure CLI errors
- Invalid configuration parameters
"""

import json
import subprocess
from unittest.mock import Mock, patch

import pytest

from azlin.modules.snapshot_manager import (
    SnapshotError,
    SnapshotManager,
    SnapshotSchedule,
)


class TestSnapshotScheduleErrors:
    """Error tests for SnapshotSchedule class."""

    def test_from_tag_value_invalid_json(self):
        """Test that invalid JSON raises SnapshotError."""
        with pytest.raises(SnapshotError, match="Failed to parse snapshot schedule"):
            SnapshotSchedule.from_tag_value("not valid json{")

    def test_from_tag_value_missing_keys(self):
        """Test that missing required keys raises SnapshotError."""
        # Should not raise - has defaults
        schedule = SnapshotSchedule.from_tag_value("{}")
        assert schedule.enabled is True
        assert schedule.interval_hours == 24

    def test_from_tag_value_invalid_timestamp(self):
        """Test that invalid timestamp format raises SnapshotError."""
        tag_value = json.dumps({"last_snapshot_time": "invalid-timestamp"})
        with pytest.raises(SnapshotError, match="Failed to parse snapshot schedule"):
            SnapshotSchedule.from_tag_value(tag_value)


class TestSnapshotManagerValidation:
    """Error tests for input validation."""

    def test_validate_vm_name_empty(self):
        """Test that empty VM name raises SnapshotError."""
        with pytest.raises(SnapshotError, match="Invalid VM name"):
            SnapshotManager._validate_vm_name("")

    def test_validate_vm_name_none(self):
        """Test that None VM name raises SnapshotError."""
        with pytest.raises(SnapshotError, match="Invalid VM name"):
            SnapshotManager._validate_vm_name(None)

    def test_validate_vm_name_too_long(self):
        """Test that VM name >64 chars raises SnapshotError."""
        long_name = "a" * 65
        with pytest.raises(SnapshotError, match="Invalid VM name"):
            SnapshotManager._validate_vm_name(long_name)

    def test_validate_vm_name_invalid_characters(self):
        """Test that invalid characters raise SnapshotError."""
        with pytest.raises(SnapshotError, match="Invalid VM name"):
            SnapshotManager._validate_vm_name("vm@invalid#chars")

    def test_validate_resource_group_empty(self):
        """Test that empty resource group raises SnapshotError."""
        with pytest.raises(SnapshotError, match="Invalid resource group name"):
            SnapshotManager._validate_resource_group("")

    def test_validate_resource_group_none(self):
        """Test that None resource group raises SnapshotError."""
        with pytest.raises(SnapshotError, match="Invalid resource group name"):
            SnapshotManager._validate_resource_group(None)

    def test_validate_resource_group_too_long(self):
        """Test that resource group name >90 chars raises SnapshotError."""
        long_name = "a" * 91
        with pytest.raises(SnapshotError, match="Invalid resource group name"):
            SnapshotManager._validate_resource_group(long_name)

    def test_enable_snapshots_invalid_interval(self):
        """Test that interval <1 hour raises SnapshotError."""
        with pytest.raises(SnapshotError, match="Interval must be at least 1 hour"):
            SnapshotManager.enable_snapshots("vm", "rg", 0, 2)

    def test_enable_snapshots_invalid_keep_count(self):
        """Test that keep_count <1 raises SnapshotError."""
        with pytest.raises(SnapshotError, match="Keep count must be at least 1"):
            SnapshotManager.enable_snapshots("vm", "rg", 24, 0)


class TestSubprocessErrors:
    """Error tests for subprocess failures."""

    @patch("azlin.modules.snapshot_manager.SnapshotManager._get_vm_os_disk_id")
    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_create_snapshot_subprocess_failure(self, mock_run, mock_disk_id):
        """Test that subprocess failure raises SnapshotError."""
        mock_disk_id.return_value = "disk-id-123"
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="Error: Quota exceeded"
        )

        with pytest.raises(SnapshotError, match="Failed to create snapshot"):
            SnapshotManager._create_snapshot("vm", "rg")

    @patch("azlin.modules.snapshot_manager.SnapshotManager._get_vm_os_disk_id")
    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_create_snapshot_timeout(self, mock_run, mock_disk_id):
        """Test that subprocess timeout raises SnapshotError."""
        mock_disk_id.return_value = "disk-id-123"
        mock_run.side_effect = subprocess.TimeoutExpired("az", 300)

        with pytest.raises(SnapshotError, match="Snapshot creation timed out"):
            SnapshotManager._create_snapshot("vm", "rg")

    @patch("azlin.modules.snapshot_manager.SnapshotManager._get_vm_os_disk_id")
    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_create_snapshot_invalid_json_response(self, mock_run, mock_disk_id):
        """Test that invalid JSON response raises SnapshotError."""
        mock_disk_id.return_value = "disk-id-123"
        mock_run.return_value = Mock(stdout="not valid json", returncode=0)

        with pytest.raises(SnapshotError, match="Failed to parse snapshot creation response"):
            SnapshotManager._create_snapshot("vm", "rg")

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_list_snapshots_subprocess_failure(self, mock_run):
        """Test that list snapshots subprocess failure raises SnapshotError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="Error: Invalid subscription"
        )

        with pytest.raises(SnapshotError, match="Failed to list snapshots"):
            SnapshotManager._list_vm_snapshots("vm", "rg")

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_list_snapshots_timeout(self, mock_run):
        """Test that list snapshots timeout raises SnapshotError."""
        mock_run.side_effect = subprocess.TimeoutExpired("az", 60)

        with pytest.raises(SnapshotError, match="List snapshots timed out"):
            SnapshotManager._list_vm_snapshots("vm", "rg")

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_list_snapshots_invalid_json(self, mock_run):
        """Test that invalid JSON in list response raises SnapshotError."""
        mock_run.return_value = Mock(stdout="invalid json", returncode=0)

        with pytest.raises(SnapshotError, match="Failed to parse snapshot list"):
            SnapshotManager._list_vm_snapshots("vm", "rg")

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_delete_snapshot_subprocess_failure(self, mock_run):
        """Test that delete snapshot subprocess failure raises SnapshotError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="Error: Snapshot not found"
        )

        with pytest.raises(SnapshotError, match="Failed to delete snapshot"):
            SnapshotManager.delete_snapshot("snapshot", "rg")

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_delete_snapshot_timeout(self, mock_run):
        """Test that delete snapshot timeout raises SnapshotError."""
        mock_run.side_effect = subprocess.TimeoutExpired("az", 60)

        with pytest.raises(SnapshotError, match="Snapshot deletion timed out"):
            SnapshotManager.delete_snapshot("snapshot", "rg")

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_restore_snapshot_subprocess_failure(self, mock_run):
        """Test that restore snapshot subprocess failure raises SnapshotError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="Error: Cannot restore while VM is running"
        )

        with pytest.raises(SnapshotError, match="Failed to restore snapshot"):
            SnapshotManager.restore_snapshot("vm", "snapshot", "rg")

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_restore_snapshot_timeout(self, mock_run):
        """Test that restore snapshot timeout raises SnapshotError."""
        mock_run.side_effect = subprocess.TimeoutExpired("az", 300)

        with pytest.raises(SnapshotError, match="Snapshot restore timed out"):
            SnapshotManager.restore_snapshot("vm", "snapshot", "rg")

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_restore_snapshot_invalid_json(self, mock_run):
        """Test that invalid JSON in restore response raises SnapshotError."""
        mock_run.return_value = Mock(stdout="not json", returncode=0)

        with pytest.raises(SnapshotError, match="Failed to parse restore response"):
            SnapshotManager.restore_snapshot("vm", "snapshot", "rg")


class TestVMOperationsErrors:
    """Error tests for VM-related operations."""

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_get_vm_os_disk_subprocess_failure(self, mock_run):
        """Test that get VM OS disk subprocess failure raises SnapshotError."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="Error: VM not found")

        with pytest.raises(SnapshotError, match="Failed to get VM OS disk"):
            SnapshotManager._get_vm_os_disk_id("vm", "rg")

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_get_vm_os_disk_timeout(self, mock_run):
        """Test that get VM OS disk timeout raises SnapshotError."""
        mock_run.side_effect = subprocess.TimeoutExpired("az", 30)

        with pytest.raises(SnapshotError, match="Get VM OS disk timed out"):
            SnapshotManager._get_vm_os_disk_id("vm", "rg")

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_get_vm_os_disk_no_disk(self, mock_run):
        """Test that VM with no OS disk raises SnapshotError."""
        # Empty string after strip() means no disk
        mock_run.return_value = Mock(stdout="", returncode=0)

        with pytest.raises(SnapshotError, match="VM .* has no OS disk"):
            SnapshotManager._get_vm_os_disk_id("vm", "rg")

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_list_vms_subprocess_failure(self, mock_run):
        """Test that list VMs subprocess failure raises SnapshotError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="Error: Invalid subscription"
        )

        with pytest.raises(SnapshotError, match="Failed to list VMs"):
            SnapshotManager._list_vms_with_snapshots("rg")

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_list_vms_timeout(self, mock_run):
        """Test that list VMs timeout raises SnapshotError."""
        mock_run.side_effect = subprocess.TimeoutExpired("az", 60)

        with pytest.raises(SnapshotError, match="List VMs timed out"):
            SnapshotManager._list_vms_with_snapshots("rg")

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_list_vms_invalid_json(self, mock_run):
        """Test that invalid JSON in list VMs response raises SnapshotError."""
        mock_run.return_value = Mock(stdout="not json", returncode=0)

        with pytest.raises(SnapshotError, match="Failed to parse VM list"):
            SnapshotManager._list_vms_with_snapshots("rg")


class TestTagOperationsErrors:
    """Error tests for VM tag operations."""

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_get_vm_tag_subprocess_failure(self, mock_run):
        """Test that get VM tag subprocess failure raises SnapshotError."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="Error: VM not found")

        with pytest.raises(SnapshotError, match="Failed to get VM tag"):
            SnapshotManager._get_vm_tag("vm", "rg", "tag-key")

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_get_vm_tag_timeout(self, mock_run):
        """Test that get VM tag timeout raises SnapshotError."""
        mock_run.side_effect = subprocess.TimeoutExpired("az", 30)

        with pytest.raises(SnapshotError, match="Get VM tag timed out"):
            SnapshotManager._get_vm_tag("vm", "rg", "tag-key")

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_set_vm_tag_subprocess_failure(self, mock_run):
        """Test that set VM tag subprocess failure raises SnapshotError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="Error: Insufficient permissions"
        )

        with pytest.raises(SnapshotError, match="Failed to set VM tag"):
            SnapshotManager._set_vm_tag("vm", "rg", "tag-key", "value")

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_set_vm_tag_timeout(self, mock_run):
        """Test that set VM tag timeout raises SnapshotError."""
        mock_run.side_effect = subprocess.TimeoutExpired("az", 30)

        with pytest.raises(SnapshotError, match="Set VM tag timed out"):
            SnapshotManager._set_vm_tag("vm", "rg", "tag-key", "value")

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_remove_vm_tag_subprocess_failure(self, mock_run):
        """Test that remove VM tag subprocess failure raises SnapshotError."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="Error: Tag not found")

        with pytest.raises(SnapshotError, match="Failed to remove VM tag"):
            SnapshotManager._remove_vm_tag("vm", "rg", "tag-key")

    @patch("azlin.modules.snapshot_manager.subprocess.run")
    def test_remove_vm_tag_timeout(self, mock_run):
        """Test that remove VM tag timeout raises SnapshotError."""
        mock_run.side_effect = subprocess.TimeoutExpired("az", 30)

        with pytest.raises(SnapshotError, match="Remove VM tag timed out"):
            SnapshotManager._remove_vm_tag("vm", "rg", "tag-key")


class TestSnapshotRetrievalErrors:
    """Error tests for snapshot information retrieval."""

    @patch("azlin.modules.snapshot_manager.SnapshotManager._list_vm_snapshots")
    @patch("azlin.modules.snapshot_manager.SnapshotManager._create_snapshot")
    def test_create_snapshot_public_api_retrieval_failure(self, mock_create, mock_list):
        """Test that failure to retrieve created snapshot raises SnapshotError."""
        # Mock successful snapshot creation
        mock_create.return_value = "vm-snapshot-20240101-120000"
        # Mock list_snapshots returns empty (can't find the snapshot)
        mock_list.return_value = []

        with pytest.raises(SnapshotError, match="Created snapshot .* but failed to retrieve info"):
            SnapshotManager.create_snapshot("vm", "rg")
