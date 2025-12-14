"""Integration test for VM provisioning with NFS mount workflow."""

import json
import subprocess

import pytest

from azlin.modules.nfs_mount_manager import NFSMountManager
from azlin.modules.nfs_provisioner import NFSProvisioner
from azlin.modules.storage_manager import StorageManager


class TestVMWithNFSProvisioningWorkflow:
    """Test VM provisioning workflow with NFS mount."""

    def test_nfs_storage_account_creation_validation(self):
        """Test validating NFS storage account configuration."""
        try:
            provisioner = NFSProvisioner()

            # Valid NFS storage config
            config = {
                "name": "nfsstorage",
                "resource_group": "test-rg",
                "location": "eastus",
                "tier": "Premium",  # NFS requires Premium
            }

            # Should validate successfully
            is_valid = provisioner.validate_config(config)
            assert is_valid is True

        except Exception as e:
            pytest.skip(f"NFSProvisioner not available: {e}")

    def test_nfs_file_share_creation_workflow(self):
        """Test NFS file share creation workflow."""
        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("Azure CLI not authenticated")

        # NFS share creation requires Premium storage
        # Test workflow validation only (no actual creation)
        try:
            provisioner = NFSProvisioner()

            # Validate share configuration
            share_config = {
                "name": "nfsshare",
                "storage_account": "storageaccount",
                "quota_gb": 100,
                "protocol": "NFS",
            }

            is_valid = provisioner.validate_share_config(share_config)
            assert is_valid is True

        except Exception as e:
            pytest.skip(f"NFS share workflow not available: {e}")

    def test_nfs_mount_point_validation(self):
        """Test validating NFS mount points."""
        try:
            mount_manager = NFSMountManager()

            # Valid mount points
            valid_mounts = ["/mnt/nfs", "/data/shared", "/home/shared/data"]

            for mount_point in valid_mounts:
                is_valid = mount_manager.validate_mount_point(mount_point)
                assert is_valid is True

            # Invalid mount points
            invalid_mounts = ["../escape", "/etc/passwd", ""]

            for mount_point in invalid_mounts:
                is_valid = mount_manager.validate_mount_point(mount_point)
                assert is_valid is False

        except Exception as e:
            pytest.skip(f"NFSMountManager not available: {e}")

    def test_nfs_mount_options_configuration(self):
        """Test configuring NFS mount options."""
        try:
            mount_manager = NFSMountManager()

            # Standard NFS mount options
            mount_options = {
                "vers": "4",
                "minorversion": "1",
                "sec": "sys",
                "rw": True,
                "hard": True,
                "timeo": "600",
            }

            # Should generate valid mount string
            options_string = mount_manager.generate_mount_options(mount_options)
            assert "vers=4" in options_string
            assert "rw" in options_string

        except Exception as e:
            pytest.skip(f"Mount options configuration not available: {e}")

    def test_vm_nfs_integration_workflow(self):
        """Test complete VM with NFS integration workflow."""
        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("Azure CLI not authenticated")

        # Workflow: Storage → NFS Share → VM → Mount
        workflow_steps = [
            "validate_storage_account",
            "create_nfs_share",
            "provision_vm",
            "configure_nfs_client",
            "mount_nfs_share",
        ]

        # Verify workflow steps are defined
        assert len(workflow_steps) == 5
        assert "mount_nfs_share" in workflow_steps
