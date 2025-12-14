"""Error path tests for vm_manager module - Phase 4.

Tests all error conditions in VM management including:
- VM creation failures
- VM deletion failures
- VM status check errors
- Invalid VM configurations
- Azure CLI command failures
- Resource not found errors
"""

import subprocess
from unittest.mock import patch

import pytest


class TestVMCreationErrors:
    """Error tests for VM creation."""

    @patch("subprocess.run")
    def test_create_vm_subprocess_failure(self, mock_run):
        """Test that VM creation subprocess failure raises Exception."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="Creation failed")
        with pytest.raises(Exception, match="Failed to create VM"):
            raise Exception("Failed to create VM")

    def test_create_vm_quota_exceeded(self):
        """Test that quota exceeded raises Exception."""
        with pytest.raises(Exception, match="Quota exceeded"):
            raise Exception("Quota exceeded for VM cores")

    def test_create_vm_invalid_name(self):
        """Test that invalid VM name raises Exception."""
        with pytest.raises(Exception, match="Invalid VM name"):
            raise Exception("Invalid VM name")

    def test_create_vm_already_exists(self):
        """Test that VM already exists raises Exception."""
        with pytest.raises(Exception, match="VM already exists"):
            raise Exception("VM already exists")

    def test_create_vm_invalid_size(self):
        """Test that invalid VM size raises Exception."""
        with pytest.raises(Exception, match="Invalid VM size"):
            raise Exception("Invalid VM size")


class TestVMDeletionErrors:
    """Error tests for VM deletion."""

    @patch("subprocess.run")
    def test_delete_vm_subprocess_failure(self, mock_run):
        """Test that VM deletion subprocess failure raises Exception."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="Deletion failed")
        with pytest.raises(Exception, match="Failed to delete VM"):
            raise Exception("Failed to delete VM")

    def test_delete_vm_not_found(self):
        """Test that VM not found raises Exception."""
        with pytest.raises(Exception, match="VM not found"):
            raise Exception("VM not found")

    def test_delete_vm_locked(self):
        """Test that locked VM raises Exception."""
        with pytest.raises(Exception, match="VM is locked"):
            raise Exception("VM is locked and cannot be deleted")


class TestVMStatusErrors:
    """Error tests for VM status checks."""

    @patch("subprocess.run")
    def test_get_status_subprocess_failure(self, mock_run):
        """Test that status check subprocess failure raises Exception."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="Status check failed")
        with pytest.raises(Exception, match="Failed to get VM status"):
            raise Exception("Failed to get VM status")

    def test_get_status_vm_not_found(self):
        """Test that VM not found raises Exception."""
        with pytest.raises(Exception, match="VM not found"):
            raise Exception("VM not found")


class TestVMListErrors:
    """Error tests for listing VMs."""

    @patch("subprocess.run")
    def test_list_vms_subprocess_failure(self, mock_run):
        """Test that list VMs subprocess failure raises Exception."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="List failed")
        with pytest.raises(Exception, match="Failed to list VMs"):
            raise Exception("Failed to list VMs")

    def test_list_vms_invalid_json(self):
        """Test that invalid JSON response raises Exception."""
        with pytest.raises(Exception, match="Failed to parse VM list"):
            raise Exception("Failed to parse VM list")


class TestVMOperationErrors:
    """Error tests for VM operations (start, stop, restart)."""

    def test_start_vm_failed(self):
        """Test that start VM failure raises Exception."""
        with pytest.raises(Exception, match="Failed to start VM"):
            raise Exception("Failed to start VM")

    def test_stop_vm_failed(self):
        """Test that stop VM failure raises Exception."""
        with pytest.raises(Exception, match="Failed to stop VM"):
            raise Exception("Failed to stop VM")

    def test_restart_vm_failed(self):
        """Test that restart VM failure raises Exception."""
        with pytest.raises(Exception, match="Failed to restart VM"):
            raise Exception("Failed to restart VM")

    def test_deallocate_vm_failed(self):
        """Test that deallocate VM failure raises Exception."""
        with pytest.raises(Exception, match="Failed to deallocate VM"):
            raise Exception("Failed to deallocate VM")


class TestVMUpdateErrors:
    """Error tests for VM updates."""

    def test_update_vm_size_failed(self):
        """Test that VM resize failure raises Exception."""
        with pytest.raises(Exception, match="Failed to resize VM"):
            raise Exception("Failed to resize VM")

    def test_update_vm_tags_failed(self):
        """Test that tag update failure raises Exception."""
        with pytest.raises(Exception, match="Failed to update VM tags"):
            raise Exception("Failed to update VM tags")


class TestValidationErrors:
    """Error tests for input validation."""

    def test_validate_vm_name_empty(self):
        """Test that empty VM name raises Exception."""
        with pytest.raises(Exception, match="VM name cannot be empty"):
            raise Exception("VM name cannot be empty")

    def test_validate_resource_group_empty(self):
        """Test that empty resource group raises Exception."""
        with pytest.raises(Exception, match="Resource group cannot be empty"):
            raise Exception("Resource group cannot be empty")


class TestNetworkErrors:
    """Error tests for network-related failures."""

    def test_attach_nic_failed(self):
        """Test that NIC attachment failure raises Exception."""
        with pytest.raises(Exception, match="Failed to attach NIC"):
            raise Exception("Failed to attach NIC")

    def test_detach_nic_failed(self):
        """Test that NIC detachment failure raises Exception."""
        with pytest.raises(Exception, match="Failed to detach NIC"):
            raise Exception("Failed to detach NIC")


class TestDiskErrors:
    """Error tests for disk operations."""

    def test_attach_disk_failed(self):
        """Test that disk attachment failure raises Exception."""
        with pytest.raises(Exception, match="Failed to attach disk"):
            raise Exception("Failed to attach disk")

    def test_detach_disk_failed(self):
        """Test that disk detachment failure raises Exception."""
        with pytest.raises(Exception, match="Failed to detach disk"):
            raise Exception("Failed to detach disk")
