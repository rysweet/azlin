"""Unit tests for vm_lifecycle module."""

import json
import subprocess
from unittest.mock import Mock, patch

import pytest

from azlin.vm_lifecycle import (
    DeletionResult,
    DeletionSummary,
    VMLifecycleError,
    VMLifecycleManager,
)


class TestVMLifecycleManager:
    """Test VMLifecycleManager class."""

    # =========================================================================
    # VM Deletion Tests
    # =========================================================================

    @patch("azlin.vm_lifecycle.ConfigManager")
    @patch("azlin.vm_lifecycle.ConnectionTracker")
    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_delete_vm_success(self, mock_run, mock_tracker, mock_config):
        """Test successful VM deletion with all resources."""
        # Mock VM details response
        vm_info = {
            "name": "test-vm",
            "resourceGroup": "test-rg",
            "networkProfile": {
                "networkInterfaces": [
                    {
                        "id": "/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Network/networkInterfaces/test-nic"
                    }
                ]
            },
            "storageProfile": {
                "osDisk": {"name": "test-os-disk"},
                "dataDisks": [{"name": "test-data-disk"}],
            },
        }

        # Mock NIC details (no public IP)
        mock_run.side_effect = [
            # VM show
            Mock(returncode=0, stdout=json.dumps(vm_info), stderr=""),
            # VM delete
            Mock(returncode=0, stdout="", stderr=""),
            # NIC show (no public IP)
            Mock(returncode=0, stdout="", stderr=""),
            # NIC delete
            Mock(returncode=0, stdout="", stderr=""),
            # Disk delete (os disk)
            Mock(returncode=0, stdout="", stderr=""),
            # Disk delete (data disk)
            Mock(returncode=0, stdout="", stderr=""),
        ]

        result = VMLifecycleManager.delete_vm("test-vm", "test-rg", force=True)

        assert result.success is True
        assert result.vm_name == "test-vm"
        assert "VM: test-vm" in result.resources_deleted
        assert "NIC: test-nic" in result.resources_deleted

        # Verify cleanup calls
        mock_tracker.remove_connection.assert_called_once_with("test-vm")
        mock_config.delete_session_name.assert_called_once_with("test-vm")

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_delete_vm_not_found(self, mock_run):
        """Test deleting non-existent VM."""
        # Mock VM not found
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=3,
            cmd=["az", "vm", "show"],
            stderr="ResourceNotFound: VM not found",
        )

        result = VMLifecycleManager.delete_vm("nonexistent-vm", "test-rg", force=True)

        assert result.success is False
        assert result.vm_name == "nonexistent-vm"
        assert "VM not found" in result.message

    @patch("azlin.vm_lifecycle.ConfigManager")
    @patch("azlin.vm_lifecycle.ConnectionTracker")
    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_delete_vm_with_associated_resources(self, mock_run, mock_tracker, mock_config):
        """Test VM deletion with NICs, disks, and public IP."""
        # Mock VM with all resources
        vm_info = {
            "name": "test-vm",
            "resourceGroup": "test-rg",
            "networkProfile": {
                "networkInterfaces": [
                    {
                        "id": "/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Network/networkInterfaces/test-nic"
                    }
                ]
            },
            "storageProfile": {
                "osDisk": {"name": "test-os-disk"},
                "dataDisks": [],
            },
        }

        mock_run.side_effect = [
            # VM show
            Mock(returncode=0, stdout=json.dumps(vm_info), stderr=""),
            # NIC show (with public IP) - called during _collect_vm_resources
            Mock(
                returncode=0,
                stdout="/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Network/publicIPAddresses/test-ip",
                stderr="",
            ),
            # VM delete
            Mock(returncode=0, stdout="", stderr=""),
            # NIC delete
            Mock(returncode=0, stdout="", stderr=""),
            # Public IP delete
            Mock(returncode=0, stdout="", stderr=""),
            # OS Disk delete
            Mock(returncode=0, stdout="", stderr=""),
        ]

        result = VMLifecycleManager.delete_vm("test-vm", "test-rg", force=True)

        assert result.success is True
        assert "VM: test-vm" in result.resources_deleted
        assert "NIC: test-nic" in result.resources_deleted
        assert "Public IP: test-ip" in result.resources_deleted
        assert "Disk: test-os-disk" in result.resources_deleted

    @patch("azlin.vm_lifecycle.ConfigManager")
    @patch("azlin.vm_lifecycle.ConnectionTracker")
    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_delete_vm_connection_tracker_cleanup(self, mock_run, mock_tracker, mock_config):
        """Test that ConnectionTracker cleanup is called."""
        vm_info = {
            "name": "test-vm",
            "resourceGroup": "test-rg",
            "networkProfile": {"networkInterfaces": []},
            "storageProfile": {"osDisk": {}, "dataDisks": []},
        }

        mock_run.side_effect = [
            # VM show
            Mock(returncode=0, stdout=json.dumps(vm_info), stderr=""),
            # VM delete
            Mock(returncode=0, stdout="", stderr=""),
        ]

        VMLifecycleManager.delete_vm("test-vm", "test-rg", force=True)

        # Verify ConnectionTracker was called
        mock_tracker.remove_connection.assert_called_once_with("test-vm")

    @patch("azlin.vm_lifecycle.ConfigManager")
    @patch("azlin.vm_lifecycle.ConnectionTracker")
    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_delete_vm_session_name_cleanup(self, mock_run, mock_tracker, mock_config):
        """Test that ConfigManager session name cleanup is called."""
        vm_info = {
            "name": "test-vm",
            "resourceGroup": "test-rg",
            "networkProfile": {"networkInterfaces": []},
            "storageProfile": {"osDisk": {}, "dataDisks": []},
        }

        mock_run.side_effect = [
            # VM show
            Mock(returncode=0, stdout=json.dumps(vm_info), stderr=""),
            # VM delete
            Mock(returncode=0, stdout="", stderr=""),
        ]

        VMLifecycleManager.delete_vm("test-vm", "test-rg", force=True)

        # Verify ConfigManager was called
        mock_config.delete_session_name.assert_called_once_with("test-vm")

    @patch("azlin.vm_lifecycle.ConfigManager")
    @patch("azlin.vm_lifecycle.ConnectionTracker")
    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_delete_vm_nic_deletion_failure_continues(self, mock_run, mock_tracker, mock_config):
        """Test that VM deletion continues even if NIC deletion fails."""
        vm_info = {
            "name": "test-vm",
            "resourceGroup": "test-rg",
            "networkProfile": {
                "networkInterfaces": [
                    {
                        "id": "/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Network/networkInterfaces/test-nic"
                    }
                ]
            },
            "storageProfile": {"osDisk": {"name": "test-disk"}, "dataDisks": []},
        }

        mock_run.side_effect = [
            # VM show
            Mock(returncode=0, stdout=json.dumps(vm_info), stderr=""),
            # VM delete
            Mock(returncode=0, stdout="", stderr=""),
            # NIC show
            Mock(returncode=0, stdout="", stderr=""),
            # NIC delete fails
            subprocess.CalledProcessError(
                returncode=1, cmd=["az", "network", "nic", "delete"], stderr="NIC busy"
            ),
            # Disk delete succeeds
            Mock(returncode=0, stdout="", stderr=""),
        ]

        result = VMLifecycleManager.delete_vm("test-vm", "test-rg", force=True)

        # Should still succeed with VM and disk deletion
        assert result.success is True
        assert "VM: test-vm" in result.resources_deleted
        assert "Disk: test-disk" in result.resources_deleted
        # NIC should not be in deleted resources since it failed
        assert "NIC: test-nic" not in result.resources_deleted

    @patch("azlin.vm_lifecycle.ConfigManager")
    @patch("azlin.vm_lifecycle.ConnectionTracker")
    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_delete_vm_disk_auto_deleted(self, mock_run, mock_tracker, mock_config):
        """Test handling of disk that was auto-deleted by Azure."""
        vm_info = {
            "name": "test-vm",
            "resourceGroup": "test-rg",
            "networkProfile": {"networkInterfaces": []},
            "storageProfile": {"osDisk": {"name": "test-disk"}, "dataDisks": []},
        }

        mock_run.side_effect = [
            # VM show
            Mock(returncode=0, stdout=json.dumps(vm_info), stderr=""),
            # VM delete
            Mock(returncode=0, stdout="", stderr=""),
            # Disk delete (already deleted)
            subprocess.CalledProcessError(
                returncode=3, cmd=["az", "disk", "delete"], stderr="ResourceNotFound"
            ),
        ]

        result = VMLifecycleManager.delete_vm("test-vm", "test-rg", force=True)

        # Should succeed - disk auto-deletion is expected
        assert result.success is True
        assert "VM: test-vm" in result.resources_deleted

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_delete_vm_failure_on_vm_delete(self, mock_run):
        """Test failure when VM deletion itself fails."""
        vm_info = {
            "name": "test-vm",
            "resourceGroup": "test-rg",
            "networkProfile": {"networkInterfaces": []},
            "storageProfile": {"osDisk": {}, "dataDisks": []},
        }

        mock_run.side_effect = [
            # VM show
            Mock(returncode=0, stdout=json.dumps(vm_info), stderr=""),
            # VM delete fails
            subprocess.CalledProcessError(
                returncode=1, cmd=["az", "vm", "delete"], stderr="VM is locked"
            ),
        ]

        result = VMLifecycleManager.delete_vm("test-vm", "test-rg", force=True)

        assert result.success is False
        assert "Failed to delete VM" in result.message

    # =========================================================================
    # Batch Deletion Tests
    # =========================================================================

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_delete_all_vms_empty_group(self, mock_run):
        """Test deleting all VMs when resource group is empty."""
        # Mock empty VM list
        mock_run.return_value = Mock(returncode=0, stdout="[]", stderr="")

        summary = VMLifecycleManager.delete_all_vms("empty-rg", force=True)

        assert summary.total == 0
        assert summary.succeeded == 0
        assert summary.failed == 0
        assert len(summary.results) == 0

    @patch("azlin.vm_lifecycle.ConfigManager")
    @patch("azlin.vm_lifecycle.ConnectionTracker")
    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_delete_all_vms_with_prefix_filter(self, mock_run, mock_tracker, mock_config):
        """Test filtering VMs by prefix."""
        # Mock VM list with mixed prefixes
        mock_run.side_effect = [
            # List VMs
            Mock(returncode=0, stdout='["azlin-vm-1", "azlin-vm-2", "other-vm"]', stderr=""),
            # VM show for azlin-vm-1
            Mock(
                returncode=0,
                stdout=json.dumps(
                    {
                        "name": "azlin-vm-1",
                        "resourceGroup": "test-rg",
                        "networkProfile": {"networkInterfaces": []},
                        "storageProfile": {"osDisk": {}, "dataDisks": []},
                    }
                ),
                stderr="",
            ),
            # VM delete for azlin-vm-1
            Mock(returncode=0, stdout="", stderr=""),
            # VM show for azlin-vm-2
            Mock(
                returncode=0,
                stdout=json.dumps(
                    {
                        "name": "azlin-vm-2",
                        "resourceGroup": "test-rg",
                        "networkProfile": {"networkInterfaces": []},
                        "storageProfile": {"osDisk": {}, "dataDisks": []},
                    }
                ),
                stderr="",
            ),
            # VM delete for azlin-vm-2
            Mock(returncode=0, stdout="", stderr=""),
        ]

        summary = VMLifecycleManager.delete_all_vms("test-rg", force=True, vm_prefix="azlin")

        # Should only delete azlin VMs
        assert summary.total == 2
        assert summary.succeeded == 2
        assert summary.failed == 0

    @patch("azlin.vm_lifecycle.ConfigManager")
    @patch("azlin.vm_lifecycle.ConnectionTracker")
    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_delete_all_vms_parallel_execution(self, mock_run, mock_tracker, mock_config):
        """Test parallel deletion with ThreadPoolExecutor."""
        # Mock VM list
        mock_run.side_effect = [
            # List VMs
            Mock(returncode=0, stdout='["vm-1", "vm-2", "vm-3"]', stderr=""),
            # VM operations for each VM (show + delete per VM)
            Mock(
                returncode=0,
                stdout=json.dumps(
                    {
                        "name": "vm-1",
                        "resourceGroup": "test-rg",
                        "networkProfile": {"networkInterfaces": []},
                        "storageProfile": {"osDisk": {}, "dataDisks": []},
                    }
                ),
                stderr="",
            ),
            Mock(returncode=0, stdout="", stderr=""),
            Mock(
                returncode=0,
                stdout=json.dumps(
                    {
                        "name": "vm-2",
                        "resourceGroup": "test-rg",
                        "networkProfile": {"networkInterfaces": []},
                        "storageProfile": {"osDisk": {}, "dataDisks": []},
                    }
                ),
                stderr="",
            ),
            Mock(returncode=0, stdout="", stderr=""),
            Mock(
                returncode=0,
                stdout=json.dumps(
                    {
                        "name": "vm-3",
                        "resourceGroup": "test-rg",
                        "networkProfile": {"networkInterfaces": []},
                        "storageProfile": {"osDisk": {}, "dataDisks": []},
                    }
                ),
                stderr="",
            ),
            Mock(returncode=0, stdout="", stderr=""),
        ]

        summary = VMLifecycleManager.delete_all_vms("test-rg", force=True, max_workers=5)

        assert summary.total == 3
        assert summary.succeeded == 3
        assert summary.failed == 0

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_delete_all_vms_resource_group_not_found(self, mock_run):
        """Test handling of non-existent resource group."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=3,
            cmd=["az", "vm", "list"],
            stderr="ResourceGroupNotFound: Resource group not found",
        )

        summary = VMLifecycleManager.delete_all_vms("nonexistent-rg", force=True)

        # Should return empty summary instead of raising
        assert summary.total == 0
        assert summary.succeeded == 0
        assert summary.failed == 0

    # =========================================================================
    # Helper Method Tests
    # =========================================================================

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_get_vm_details_success(self, mock_run):
        """Test successful VM details retrieval."""
        vm_info = {
            "name": "test-vm",
            "resourceGroup": "test-rg",
            "location": "eastus",
        }

        mock_run.return_value = Mock(returncode=0, stdout=json.dumps(vm_info), stderr="")

        result = VMLifecycleManager._get_vm_details("test-vm", "test-rg")

        assert result == vm_info
        assert result["name"] == "test-vm"

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_get_vm_details_not_found(self, mock_run):
        """Test VM not found returns None."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=3, cmd=["az", "vm", "show"], stderr="ResourceNotFound: VM not found"
        )

        result = VMLifecycleManager._get_vm_details("nonexistent-vm", "test-rg")

        assert result is None

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_get_vm_details_timeout(self, mock_run):
        """Test VM details query timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["az", "vm", "show"], timeout=30)

        with pytest.raises(VMLifecycleError, match="timed out"):
            VMLifecycleManager._get_vm_details("test-vm", "test-rg")

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_get_vm_details_invalid_json(self, mock_run):
        """Test handling of invalid JSON response."""
        mock_run.return_value = Mock(returncode=0, stdout="invalid json", stderr="")

        with pytest.raises(VMLifecycleError, match="Failed to parse"):
            VMLifecycleManager._get_vm_details("test-vm", "test-rg")

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_list_vms_in_group_success(self, mock_run):
        """Test listing VMs in resource group."""
        vm_list = ["vm-1", "vm-2", "vm-3"]
        mock_run.return_value = Mock(returncode=0, stdout=json.dumps(vm_list), stderr="")

        result = VMLifecycleManager._list_vms_in_group("test-rg")

        assert result == vm_list
        assert len(result) == 3

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_list_vms_in_group_not_found(self, mock_run):
        """Test listing VMs when resource group not found."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=3,
            cmd=["az", "vm", "list"],
            stderr="ResourceGroupNotFound: Resource group not found",
        )

        result = VMLifecycleManager._list_vms_in_group("nonexistent-rg")

        assert result == []

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_list_vms_in_group_timeout(self, mock_run):
        """Test VM list timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["az", "vm", "list"], timeout=30)

        with pytest.raises(VMLifecycleError, match="timed out"):
            VMLifecycleManager._list_vms_in_group("test-rg")

    def test_collect_vm_resources_with_nics_and_disks(self):
        """Test collecting resources from VM info."""
        vm_info = {
            "networkProfile": {
                "networkInterfaces": [
                    {
                        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/networkInterfaces/nic-1"
                    },
                    {
                        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/networkInterfaces/nic-2"
                    },
                ]
            },
            "storageProfile": {
                "osDisk": {"name": "os-disk"},
                "dataDisks": [{"name": "data-disk-1"}, {"name": "data-disk-2"}],
            },
            "resourceGroup": "test-rg",
        }

        with patch.object(VMLifecycleManager, "_get_public_ip_from_nic", return_value=None):
            resources = VMLifecycleManager._collect_vm_resources(vm_info)

        # Should have 2 NICs, 1 OS disk, 2 data disks
        nic_resources = [r for r in resources if r[0] == "nic"]
        disk_resources = [r for r in resources if r[0] == "disk"]

        assert len(nic_resources) == 2
        assert len(disk_resources) == 3
        assert ("nic", "nic-1") in resources
        assert ("nic", "nic-2") in resources
        assert ("disk", "os-disk") in resources
        assert ("disk", "data-disk-1") in resources
        assert ("disk", "data-disk-2") in resources

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_collect_vm_resources_with_public_ip(self, mock_run):
        """Test collecting resources includes public IP."""
        vm_info = {
            "networkProfile": {
                "networkInterfaces": [
                    {
                        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/networkInterfaces/test-nic"
                    }
                ]
            },
            "storageProfile": {"osDisk": {}, "dataDisks": []},
            "resourceGroup": "test-rg",
        }

        # Mock public IP query
        mock_run.return_value = Mock(
            returncode=0,
            stdout="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/test-ip",
            stderr="",
        )

        resources = VMLifecycleManager._collect_vm_resources(vm_info)

        assert ("nic", "test-nic") in resources
        assert ("public-ip", "test-ip") in resources

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_get_public_ip_from_nic_success(self, mock_run):
        """Test getting public IP from NIC."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/test-ip",
            stderr="",
        )

        result = VMLifecycleManager._get_public_ip_from_nic("test-nic", "test-rg")

        assert result == "test-ip"

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_get_public_ip_from_nic_none(self, mock_run):
        """Test NIC with no public IP."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        result = VMLifecycleManager._get_public_ip_from_nic("test-nic", "test-rg")

        assert result is None

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_get_public_ip_from_nic_none_string(self, mock_run):
        """Test NIC with 'None' string response."""
        mock_run.return_value = Mock(returncode=0, stdout="None", stderr="")

        result = VMLifecycleManager._get_public_ip_from_nic("test-nic", "test-rg")

        assert result is None

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_get_public_ip_from_nic_error(self, mock_run):
        """Test handling of NIC query error."""
        mock_run.side_effect = Exception("Network error")

        result = VMLifecycleManager._get_public_ip_from_nic("test-nic", "test-rg")

        # Should return None on error (method catches all exceptions)
        assert result is None

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_delete_vm_resource_no_wait(self, mock_run):
        """Test VM deletion with no_wait flag."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        VMLifecycleManager._delete_vm_resource("test-vm", "test-rg", no_wait=True)

        # Verify --no-wait flag was passed
        call_args = mock_run.call_args[0][0]
        assert "--no-wait" in call_args
        assert call_args == [
            "az",
            "vm",
            "delete",
            "--name",
            "test-vm",
            "--resource-group",
            "test-rg",
            "--yes",
            "--no-wait",
        ]

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_delete_vm_resource_with_wait(self, mock_run):
        """Test VM deletion waits by default."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        VMLifecycleManager._delete_vm_resource("test-vm", "test-rg", no_wait=False)

        # Verify --no-wait flag was NOT passed
        call_args = mock_run.call_args[0][0]
        assert "--no-wait" not in call_args
        assert call_args == [
            "az",
            "vm",
            "delete",
            "--name",
            "test-vm",
            "--resource-group",
            "test-rg",
            "--yes",
        ]

    # =========================================================================
    # Data Class Tests
    # =========================================================================

    def test_deletion_result_creation(self):
        """Test DeletionResult creation."""
        result = DeletionResult(
            vm_name="test-vm",
            success=True,
            message="Deleted successfully",
            resources_deleted=["VM: test-vm", "NIC: test-nic"],
        )

        assert result.vm_name == "test-vm"
        assert result.success is True
        assert result.message == "Deleted successfully"
        assert len(result.resources_deleted) == 2

    def test_deletion_result_default_resources(self):
        """Test DeletionResult with default resources list."""
        result = DeletionResult(vm_name="test-vm", success=False, message="Failed")

        assert result.resources_deleted == []

    def test_deletion_summary_all_succeeded(self):
        """Test DeletionSummary.all_succeeded property."""
        results = [
            DeletionResult(vm_name="vm-1", success=True, message="OK"),
            DeletionResult(vm_name="vm-2", success=True, message="OK"),
            DeletionResult(vm_name="vm-3", success=True, message="OK"),
        ]

        summary = DeletionSummary(total=3, succeeded=3, failed=0, results=results)

        assert summary.all_succeeded is True

    def test_deletion_summary_not_all_succeeded(self):
        """Test DeletionSummary.all_succeeded with failures."""
        results = [
            DeletionResult(vm_name="vm-1", success=True, message="OK"),
            DeletionResult(vm_name="vm-2", success=False, message="Failed"),
            DeletionResult(vm_name="vm-3", success=True, message="OK"),
        ]

        summary = DeletionSummary(total=3, succeeded=2, failed=1, results=results)

        assert summary.all_succeeded is False

    def test_deletion_summary_get_failed_vms(self):
        """Test DeletionSummary.get_failed_vms method."""
        results = [
            DeletionResult(vm_name="vm-1", success=True, message="OK"),
            DeletionResult(vm_name="vm-2", success=False, message="Failed"),
            DeletionResult(vm_name="vm-3", success=True, message="OK"),
            DeletionResult(vm_name="vm-4", success=False, message="Failed"),
        ]

        summary = DeletionSummary(total=4, succeeded=2, failed=2, results=results)

        failed_vms = summary.get_failed_vms()

        assert len(failed_vms) == 2
        assert "vm-2" in failed_vms
        assert "vm-4" in failed_vms
        assert "vm-1" not in failed_vms
        assert "vm-3" not in failed_vms

    def test_vm_lifecycle_error(self):
        """Test VMLifecycleError exception."""
        error = VMLifecycleError("Test error message")

        assert str(error) == "Test error message"
        assert isinstance(error, Exception)


class TestResourceCleanupEdgeCases:
    """Test edge cases for resource cleanup."""

    @patch("azlin.vm_lifecycle.ConfigManager")
    @patch("azlin.vm_lifecycle.ConnectionTracker")
    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_cleanup_continues_on_tracker_error(self, mock_run, mock_tracker, mock_config):
        """Test that cleanup continues if ConnectionTracker fails."""
        vm_info = {
            "name": "test-vm",
            "resourceGroup": "test-rg",
            "networkProfile": {"networkInterfaces": []},
            "storageProfile": {"osDisk": {}, "dataDisks": []},
        }

        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vm_info), stderr=""),
            Mock(returncode=0, stdout="", stderr=""),
        ]

        # Mock tracker failure
        mock_tracker.remove_connection.side_effect = Exception("Tracker error")

        result = VMLifecycleManager.delete_vm("test-vm", "test-rg", force=True)

        # Should still succeed despite tracker error
        assert result.success is True
        # Should still try to clean up session name
        mock_config.delete_session_name.assert_called_once_with("test-vm")

    @patch("azlin.vm_lifecycle.ConfigManager")
    @patch("azlin.vm_lifecycle.ConnectionTracker")
    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_cleanup_continues_on_config_error(self, mock_run, mock_tracker, mock_config):
        """Test that cleanup continues if ConfigManager fails."""
        vm_info = {
            "name": "test-vm",
            "resourceGroup": "test-rg",
            "networkProfile": {"networkInterfaces": []},
            "storageProfile": {"osDisk": {}, "dataDisks": []},
        }

        mock_run.side_effect = [
            Mock(returncode=0, stdout=json.dumps(vm_info), stderr=""),
            Mock(returncode=0, stdout="", stderr=""),
        ]

        # Mock config failure
        mock_config.delete_session_name.side_effect = Exception("Config error")

        result = VMLifecycleManager.delete_vm("test-vm", "test-rg", force=True)

        # Should still succeed despite config error
        assert result.success is True
        # Should have tried both cleanups
        mock_tracker.remove_connection.assert_called_once_with("test-vm")
        mock_config.delete_session_name.assert_called_once_with("test-vm")


class TestCommandConstruction:
    """Test Azure CLI command construction."""

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_vm_show_command_structure(self, mock_run):
        """Test VM show command structure."""
        mock_run.return_value = Mock(returncode=0, stdout="{}", stderr="")

        VMLifecycleManager._get_vm_details("my-vm", "my-rg")

        call_args = mock_run.call_args[0][0]
        assert call_args == [
            "az",
            "vm",
            "show",
            "--name",
            "my-vm",
            "--resource-group",
            "my-rg",
            "--output",
            "json",
        ]

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_vm_list_command_structure(self, mock_run):
        """Test VM list command structure."""
        mock_run.return_value = Mock(returncode=0, stdout="[]", stderr="")

        VMLifecycleManager._list_vms_in_group("my-rg")

        call_args = mock_run.call_args[0][0]
        assert call_args == [
            "az",
            "vm",
            "list",
            "--resource-group",
            "my-rg",
            "--query",
            "[].name",
            "--output",
            "json",
        ]

    @patch("azlin.vm_lifecycle.subprocess.run")
    def test_nic_show_command_structure(self, mock_run):
        """Test NIC show command structure."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        VMLifecycleManager._get_public_ip_from_nic("my-nic", "my-rg")

        call_args = mock_run.call_args[0][0]
        assert call_args == [
            "az",
            "network",
            "nic",
            "show",
            "--name",
            "my-nic",
            "--resource-group",
            "my-rg",
            "--query",
            "ipConfigurations[0].publicIpAddress.id",
            "--output",
            "tsv",
        ]
