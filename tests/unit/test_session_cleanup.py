"""Unit tests for session cleanup on VM deletion."""

from unittest.mock import patch

import pytest

from azlin.config_manager import ConfigManager
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

    @patch("azlin.vm_lifecycle.ConfigManager")
    @patch("azlin.vm_lifecycle.ConnectionTracker")
    @patch.object(VMLifecycleManager, "_delete_vm_resource")
    @patch.object(VMLifecycleManager, "_get_vm_details")
    def test_vm_deletion_failure_skips_session_cleanup(
        self,
        mock_get_vm_details,
        mock_delete_vm_resource,
        mock_connection_tracker,
        mock_config_manager,
    ):
        """Test that session cleanup is skipped when VM deletion fails.

        This addresses the code review feedback to test the scenario where
        VM deletion fails before cleanup is attempted.
        """
        # Setup mocks
        vm_name = "test-vm"
        resource_group = "test-rg"

        mock_get_vm_details.return_value = {
            "name": vm_name,
            "resourceGroup": resource_group,
            "networkProfile": {"networkInterfaces": []},
            "storageProfile": {"osDisk": {"name": "test-disk"}, "dataDisks": []},
        }

        # Make VM resource deletion fail
        mock_delete_vm_resource.side_effect = Exception("Azure API error")

        # Execute
        result = VMLifecycleManager.delete_vm(vm_name, resource_group, force=True)

        # Verify - deletion should fail
        assert result.success is False

        # Session cleanup should NOT be called since deletion failed
        mock_config_manager.delete_session_name.assert_not_called()
        mock_connection_tracker.remove_connection.assert_not_called()


class TestVMNameValidation:
    """Tests for VM name validation in session cleanup."""

    def test_delete_session_name_validates_format(self, tmp_path):
        """Test that delete_session_name validates VM name format."""
        # Test invalid formats
        invalid_names = [
            "",  # Empty
            "a" * 65,  # Too long (>64 chars)
            "vm-with-special-char!",  # Invalid character
            "vm name with spaces",  # Spaces not allowed
            "../../../etc/passwd",  # Path traversal attempt
            "vm\nmalicious",  # Newline character
        ]

        for invalid_name in invalid_names:
            with pytest.raises(ValueError, match="Invalid VM name format"):
                ConfigManager.delete_session_name(invalid_name)

    def test_delete_session_name_accepts_valid_names(self, tmp_path):
        """Test that delete_session_name accepts valid Azure VM names."""
        # Test valid formats
        valid_names = [
            "vm1",
            "test-vm",
            "my_vm_123",
            "VM-WITH-CAPS",
            "a" * 64,  # Max length (64 chars)
        ]

        for valid_name in valid_names:
            # Should not raise ValueError
            # May return False (not found) but shouldn't raise
            result = ConfigManager.delete_session_name(valid_name)
            assert isinstance(result, bool)
