"""Unit tests for session cleanup on VM deletion."""

from unittest.mock import patch

from azlin.vm_lifecycle import DeletionResult, VMLifecycleManager


class TestSessionCleanup:
    """Tests for session name cleanup during VM deletion."""

    @patch("azlin.vm_lifecycle.ConfigManager")
    @patch("azlin.vm_lifecycle.ConnectionTracker")
    @patch.object(VMLifecycleManager, "_delete_vm_resource")
    @patch.object(VMLifecycleManager, "_get_vm_details")
    def test_delete_vm_removes_session_name(
        self,
        mock_get_vm_details,
        mock_delete_vm_resource,
        mock_connection_tracker,
        mock_config_manager,
    ):
        """Test that delete_vm calls ConfigManager.delete_session_name."""
        # Setup mocks
        vm_name = "test-vm"
        resource_group = "test-rg"

        mock_get_vm_details.return_value = {
            "name": vm_name,
            "resourceGroup": resource_group,
            "networkProfile": {"networkInterfaces": []},
            "storageProfile": {"osDisk": {"name": "test-disk"}, "dataDisks": []},
        }

        # Execute
        result = VMLifecycleManager.delete_vm(vm_name, resource_group, force=True)

        # Verify
        assert result.success is True
        mock_connection_tracker.remove_connection.assert_called_once_with(vm_name)
        mock_config_manager.delete_session_name.assert_called_once_with(vm_name)

    @patch("azlin.vm_lifecycle.ConfigManager")
    @patch("azlin.vm_lifecycle.ConnectionTracker")
    @patch.object(VMLifecycleManager, "_delete_vm_resource")
    @patch.object(VMLifecycleManager, "_get_vm_details")
    def test_delete_vm_handles_session_cleanup_error(
        self,
        mock_get_vm_details,
        mock_delete_vm_resource,
        mock_connection_tracker,
        mock_config_manager,
    ):
        """Test that delete_vm continues even if session cleanup fails."""
        # Setup mocks
        vm_name = "test-vm"
        resource_group = "test-rg"

        mock_get_vm_details.return_value = {
            "name": vm_name,
            "resourceGroup": resource_group,
            "networkProfile": {"networkInterfaces": []},
            "storageProfile": {"osDisk": {"name": "test-disk"}, "dataDisks": []},
        }

        # Make session cleanup fail
        mock_config_manager.delete_session_name.side_effect = Exception("Config error")

        # Execute
        result = VMLifecycleManager.delete_vm(vm_name, resource_group, force=True)

        # Verify - deletion should still succeed
        assert result.success is True
        mock_config_manager.delete_session_name.assert_called_once_with(vm_name)

    @patch("azlin.vm_lifecycle.ConfigManager")
    @patch("azlin.vm_lifecycle.ConnectionTracker")
    @patch.object(VMLifecycleManager, "_delete_vm_resource")
    @patch.object(VMLifecycleManager, "_get_vm_details")
    def test_delete_vm_not_found_skips_cleanup(
        self,
        mock_get_vm_details,
        mock_delete_vm_resource,
        mock_connection_tracker,
        mock_config_manager,
    ):
        """Test that session cleanup is skipped when VM is not found."""
        # Setup mocks
        vm_name = "missing-vm"
        resource_group = "test-rg"

        mock_get_vm_details.return_value = None

        # Execute
        result = VMLifecycleManager.delete_vm(vm_name, resource_group, force=True)

        # Verify
        assert result.success is False
        assert result.message == "VM not found"
        mock_connection_tracker.remove_connection.assert_not_called()
        mock_config_manager.delete_session_name.assert_not_called()

    @patch("azlin.vm_lifecycle.ConfigManager")
    @patch.object(VMLifecycleManager, "delete_vm")
    @patch.object(VMLifecycleManager, "_list_vms_in_group")
    def test_delete_all_vms_cleans_sessions_via_delete_vm(
        self, mock_list_vms, mock_delete_vm, mock_config_manager
    ):
        """Test that delete_all_vms cleans sessions via calling delete_vm."""
        # Setup mocks
        resource_group = "test-rg"
        vm_names = ["vm1", "vm2", "vm3"]

        mock_list_vms.return_value = vm_names
        mock_delete_vm.return_value = DeletionResult(
            vm_name="test", success=True, message="Deleted", resources_deleted=[]
        )

        # Execute
        summary = VMLifecycleManager.delete_all_vms(resource_group, force=True)

        # Verify delete_vm was called for each VM (which handles session cleanup)
        assert mock_delete_vm.call_count == len(vm_names)
        assert summary.succeeded == len(vm_names)
