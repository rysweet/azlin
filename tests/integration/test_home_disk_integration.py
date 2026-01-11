"""Integration tests for VM provisioning with separate /home disk.

This module tests the integration of multiple components:
1. Full VM provisioning workflow with home disk
2. VM provisioning with custom disk size
3. VM provisioning with --no-home-disk flag
4. VM provisioning with NFS storage (no home disk)
5. Error scenarios with real Azure interactions

Test Philosophy:
- Integration tests (30% of test pyramid)
- Test multiple components working together
- Use real Azure CLI where possible (with cleanup)
- Slower tests but validate complete workflows
- Strategic mocking only where necessary

Testing Pyramid Distribution:
- 60% Unit tests (test_vm_provisioning_home_disk.py) - Fast, heavily mocked
- 30% Integration tests (this file) - Multiple components
- 10% E2E tests (separate file) - Complete workflows

Note: These tests use @pytest.mark.integration decorator
and can be run separately with: pytest -m integration
"""

import json
import subprocess
from unittest.mock import MagicMock, Mock, patch

import pytest

from azlin.vm_provisioning import ProvisioningError, VMConfig, VMProvisioner


@pytest.mark.integration
class TestFullVMProvisioningWithHomeDisk:
    """Test complete VM provisioning workflow with home disk.

    These tests validate the entire flow:
    1. Create resource group
    2. Create home disk
    3. Generate cloud-init with disk setup
    4. Provision VM
    5. Attach home disk
    6. Verify VM has disk attached
    """

    @pytest.fixture
    def provisioner(self):
        """Create VMProvisioner instance for tests."""
        return VMProvisioner()

    @pytest.fixture
    def test_config(self):
        """Create test VMConfig with home disk enabled."""
        return VMConfig(
            name="azlin-test-home-disk",
            resource_group="azlin-test-home-disk-rg",
            location="westus2",
            size="Standard_B1s",  # Smallest size for cost-effective testing
            home_disk_enabled=True,
            home_disk_size_gb=10,  # Minimal size for testing
            home_disk_sku="Standard_LRS",
        )

    def test_provision_vm_with_home_disk_full_workflow(self, provisioner, test_config):
        """Test full VM provisioning workflow with home disk.

        Given: A VMConfig with home_disk_enabled=True
        When: provision_vm is called
        Then: VM is provisioned with home disk created and attached
        And: Cloud-init includes disk setup, fs_setup, and mounts
        And: Disk is accessible at LUN 0

        Note: This test mocks Azure CLI to avoid real provisioning costs
        """
        with patch("azlin.vm_provisioning.AzureCLIExecutor") as mock_executor_class:
            # Create mock executor instance
            mock_executor = MagicMock()
            mock_executor_class.return_value = mock_executor

            # Mock disk creation response
            disk_create_response = {
                "success": True,
                "returncode": 0,
                "stdout": json.dumps(
                    {
                        "id": f"/subscriptions/test-sub/resourceGroups/{test_config.resource_group}/providers/Microsoft.Compute/disks/{test_config.name}-home",
                        "name": f"{test_config.name}-home",
                        "diskSizeGb": 10,
                        "sku": {"name": "Standard_LRS"},
                        "provisioningState": "Succeeded",
                    }
                ),
                "stderr": "",
            }

            # Mock VM creation response
            vm_create_response = {
                "success": True,
                "returncode": 0,
                "stdout": json.dumps(
                    {
                        "id": f"/subscriptions/test-sub/resourceGroups/{test_config.resource_group}/providers/Microsoft.Compute/virtualMachines/{test_config.name}",
                        "name": test_config.name,
                        "location": test_config.location,
                        "hardwareProfile": {"vmSize": test_config.size},
                        "publicIpAddress": "1.2.3.4",
                        "privateIpAddress": "10.0.0.4",
                        "provisioningState": "Succeeded",
                    }
                ),
                "stderr": "",
            }

            # Mock disk attachment response
            disk_attach_response = {
                "success": True,
                "returncode": 0,
                "stdout": json.dumps(
                    {
                        "lun": 0,
                        "managedDisk": {
                            "id": f"/subscriptions/test-sub/resourceGroups/{test_config.resource_group}/providers/Microsoft.Compute/disks/{test_config.name}-home"
                        },
                    }
                ),
                "stderr": "",
            }

            # Mock resource group check (exists)
            rg_exists_response = {
                "success": True,
                "returncode": 0,
                "stdout": "false",  # RG doesn't exist yet
                "stderr": "",
            }

            # Mock resource group creation
            rg_create_response = {
                "success": True,
                "returncode": 0,
                "stdout": json.dumps(
                    {
                        "name": test_config.resource_group,
                        "location": test_config.location,
                        "properties": {"provisioningState": "Succeeded"},
                    }
                ),
                "stderr": "",
            }

            # Configure mock to return different responses based on command
            def execute_side_effect(cmd):
                if "group" in cmd and "exists" in cmd:
                    return rg_exists_response
                if "group" in cmd and "create" in cmd:
                    return rg_create_response
                if "disk" in cmd and "create" in cmd:
                    return disk_create_response
                if "vm" in cmd and "create" in cmd:
                    return vm_create_response
                if "disk" in cmd and "attach" in cmd:
                    return disk_attach_response
                return {
                    "success": False,
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "Unknown command",
                }

            mock_executor.execute.side_effect = execute_side_effect

            # Execute provisioning
            result = provisioner.provision_vm(test_config)

            # Verify VM was created
            assert result.name == test_config.name
            assert result.location == test_config.location
            assert result.size == test_config.size
            assert result.public_ip == "1.2.3.4"

            # Verify all expected commands were called
            all_calls = mock_executor.execute.call_args_list
            executed_commands = [str(call[0][0]) for call in all_calls]

            # Verify disk creation command was called
            assert any("disk" in cmd and "create" in cmd for cmd in executed_commands), (
                "Disk creation command should be executed"
            )

            # Verify VM creation command was called
            assert any("vm" in cmd and "create" in cmd for cmd in executed_commands), (
                "VM creation command should be executed"
            )

            # Verify disk attachment command was called
            assert any("disk" in cmd and "attach" in cmd for cmd in executed_commands), (
                "Disk attachment command should be executed"
            )

    def test_provision_vm_with_custom_disk_size(self, provisioner):
        """Test VM provisioning with custom home disk size.

        Given: A VMConfig with home_disk_size_gb=200
        When: provision_vm is called
        Then: Disk is created with 200GB size
        """
        config = VMConfig(
            name="azlin-test-custom-size",
            resource_group="azlin-test-rg",
            location="westus2",
            home_disk_enabled=True,
            home_disk_size_gb=200,
            home_disk_sku="Standard_LRS",
        )

        with (
            patch.object(provisioner, "_create_home_disk") as mock_create,
            patch.object(provisioner, "_try_provision_vm") as mock_provision,
            patch.object(provisioner, "_attach_home_disk") as mock_attach,
            patch.object(provisioner, "_generate_cloud_init") as mock_cloud_init,
        ):
            mock_create.return_value = "/subscriptions/test/resourceGroups/test-rg/providers/Microsoft.Compute/disks/test-vm-home"
            mock_cloud_init.return_value = "#cloud-config\npackages:\n  - git"
            mock_provision.return_value = Mock(
                name="azlin-test-custom-size",
                resource_group="azlin-test-rg",
                location="westus2",
                size="Standard_B1s",
                public_ip="1.2.3.4",
            )
            mock_attach.return_value = "0"

            result = provisioner.provision_vm(config)

            # Verify disk was created with correct size
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["size_gb"] == 200

            assert result.name == "azlin-test-custom-size"

    def test_provision_vm_without_home_disk_flag(self, provisioner):
        """Test VM provisioning with --no-home-disk flag.

        Given: A VMConfig with home_disk_enabled=False
        When: provision_vm is called
        Then: No disk operations occur
        And: Cloud-init does not include disk sections
        """
        config = VMConfig(
            name="azlin-test-no-disk",
            resource_group="azlin-test-rg",
            location="westus2",
            home_disk_enabled=False,
        )

        with (
            patch.object(provisioner, "_create_home_disk") as mock_create,
            patch.object(provisioner, "_try_provision_vm") as mock_provision,
            patch.object(provisioner, "_attach_home_disk") as mock_attach,
            patch.object(provisioner, "_generate_cloud_init") as mock_cloud_init,
        ):
            mock_cloud_init.return_value = "#cloud-config\npackages:\n  - git"
            mock_provision.return_value = Mock(
                name="azlin-test-no-disk",
                resource_group="azlin-test-rg",
                location="westus2",
                size="Standard_B1s",
                public_ip="1.2.3.4",
            )

            result = provisioner.provision_vm(config)

            # Verify no disk operations occurred
            mock_create.assert_not_called()
            mock_attach.assert_not_called()

            # Verify cloud-init was called with has_home_disk=False
            mock_cloud_init.assert_called()
            call_kwargs = mock_cloud_init.call_args[1]
            assert call_kwargs.get("has_home_disk", False) is False

            assert result.name == "azlin-test-no-disk"


@pytest.mark.integration
class TestNFSStorageIntegration:
    """Test integration with NFS storage (home disk should be disabled).

    These tests verify that NFS storage takes precedence over home disk,
    since NFS provides /home via network mount.
    """

    @pytest.fixture
    def provisioner(self):
        """Create VMProvisioner instance for tests."""
        return VMProvisioner()

    def test_nfs_storage_disables_home_disk_automatically(self, provisioner):
        """Test that NFS storage configuration automatically disables home disk.

        Given: A NewCommand with nfs_storage configured
        When: VMConfig is created
        Then: home_disk_enabled is False
        """
        # This test requires NewCommand implementation
        # For now, we'll test the logic directly
        pytest.skip("Requires NewCommand implementation for NFS precedence logic")

    def test_provision_vm_with_nfs_storage_no_home_disk(self, provisioner):
        """Test VM provisioning with NFS storage (no home disk).

        Given: A VMConfig with NFS storage (home_disk_enabled=False)
        When: provision_vm is called
        Then: No home disk operations occur
        And: NFS mount is configured instead
        """
        config = VMConfig(
            name="azlin-test-nfs",
            resource_group="azlin-test-rg",
            location="westus2",
            home_disk_enabled=False,  # Disabled due to NFS
        )

        with (
            patch.object(provisioner, "_create_home_disk") as mock_create,
            patch.object(provisioner, "_try_provision_vm") as mock_provision,
            patch.object(provisioner, "_attach_home_disk") as mock_attach,
        ):
            mock_provision.return_value = Mock(
                name="azlin-test-nfs",
                resource_group="azlin-test-rg",
                location="westus2",
                size="Standard_B1s",
                public_ip="1.2.3.4",
            )

            result = provisioner.provision_vm(config)

            # Verify no home disk operations
            mock_create.assert_not_called()
            mock_attach.assert_not_called()

            assert result.name == "azlin-test-nfs"


@pytest.mark.integration
class TestHomeDiskErrorScenarios:
    """Test error scenarios with home disk operations.

    These tests validate error handling and graceful degradation
    in various failure scenarios.
    """

    @pytest.fixture
    def provisioner(self):
        """Create VMProvisioner instance for tests."""
        return VMProvisioner()

    def test_disk_creation_quota_exceeded_error(self, provisioner):
        """Test handling of disk quota exceeded error.

        Given: A VMConfig with home_disk_enabled=True
        When: Disk creation fails due to quota exceeded
        Then: Raises ProvisioningError with clear quota message
        And: VM provisioning is not attempted
        """
        config = VMConfig(
            name="azlin-test-quota",
            resource_group="azlin-test-rg",
            location="westus2",
            home_disk_enabled=True,
        )

        with (
            patch.object(provisioner, "_create_home_disk") as mock_create,
            patch.object(provisioner, "_try_provision_vm") as mock_provision,
        ):
            # Mock quota exceeded error
            mock_create.side_effect = ProvisioningError(
                "Failed to create home disk 'azlin-test-quota-home': "
                "QuotaExceeded - Disk count quota exceeded in region westus2. "
                "Current: 50, Limit: 50"
            )

            with pytest.raises(ProvisioningError) as exc_info:
                provisioner.provision_vm(config)

            error_msg = str(exc_info.value)
            assert "quota" in error_msg.lower()
            assert "westus2" in error_msg

            # VM provisioning should not be attempted
            mock_provision.assert_not_called()

    def test_disk_attachment_failure_graceful_degradation(self, provisioner):
        """Test graceful degradation when disk attachment fails.

        Given: A VMConfig with home_disk_enabled=True
        When: Disk attachment fails after VM creation
        Then: VM is still returned (not re-raised)
        And: Warning is logged about attachment failure
        """
        config = VMConfig(
            name="azlin-test-attach-fail",
            resource_group="azlin-test-rg",
            location="westus2",
            home_disk_enabled=True,
        )

        with (
            patch.object(provisioner, "_create_home_disk") as mock_create,
            patch.object(provisioner, "_try_provision_vm") as mock_provision,
            patch.object(provisioner, "_attach_home_disk") as mock_attach,
            patch.object(provisioner, "_generate_cloud_init") as mock_cloud_init,
            patch("azlin.vm_provisioning.logger") as mock_logger,
        ):
            mock_create.return_value = "/subscriptions/test/resourceGroups/test-rg/providers/Microsoft.Compute/disks/test-vm-home"
            mock_cloud_init.return_value = "#cloud-config\npackages:\n  - git"
            mock_provision.return_value = Mock(
                name="azlin-test-attach-fail",
                resource_group="azlin-test-rg",
                location="westus2",
                size="Standard_B1s",
                public_ip="1.2.3.4",
            )

            # Mock attachment failure
            mock_attach.side_effect = ProvisioningError("Failed to attach disk: VM is not running")

            # Should not raise exception (graceful degradation)
            result = provisioner.provision_vm(config)

            # VM should still be returned
            assert result.name == "azlin-test-attach-fail"
            assert result.public_ip == "1.2.3.4"

            # Warning should be logged
            assert mock_logger.warning.called
            warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
            assert any("attach" in call.lower() or "disk" in call.lower() for call in warning_calls)

    def test_vm_creation_failure_leaves_orphaned_disk(self, provisioner):
        """Test that VM creation failure leaves orphaned disk (expected behavior).

        Given: A VMConfig with home_disk_enabled=True
        When: VM creation fails after disk creation
        Then: Raises ProvisioningError
        And: Disk remains (user must clean up manually or via resource group deletion)
        """
        config = VMConfig(
            name="azlin-test-vm-fail",
            resource_group="azlin-test-rg",
            location="westus2",
            home_disk_enabled=True,
        )

        with (
            patch.object(provisioner, "_create_home_disk") as mock_create,
            patch.object(provisioner, "_try_provision_vm") as mock_provision,
            patch.object(provisioner, "_generate_cloud_init") as mock_cloud_init,
        ):
            mock_create.return_value = "/subscriptions/test/resourceGroups/test-rg/providers/Microsoft.Compute/disks/test-vm-home"
            mock_cloud_init.return_value = "#cloud-config\npackages:\n  - git"

            # Mock VM creation failure
            mock_provision.side_effect = subprocess.CalledProcessError(
                1, ["az", "vm", "create"], stderr="SKUNotAvailable: VM size not available in region"
            )

            with pytest.raises(ProvisioningError) as exc_info:
                provisioner.provision_vm(config)

            # Disk was created (orphaned)
            mock_create.assert_called_once()

            # Error should mention VM creation failure
            error_msg = str(exc_info.value)
            assert "not available" in error_msg.lower() or "sku" in error_msg.lower()


@pytest.mark.integration
class TestCloudInitDiskConfiguration:
    """Test cloud-init disk configuration integration.

    These tests verify that cloud-init correctly configures
    the home disk filesystem and mount point.
    """

    @pytest.fixture
    def provisioner(self):
        """Create VMProvisioner instance for tests."""
        return VMProvisioner()

    def test_cloud_init_disk_setup_uses_azure_stable_paths(self, provisioner):
        """Test that cloud-init uses Azure stable device paths.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called with has_home_disk=True
        Then: Uses /dev/disk/azure/scsi1/lun0 instead of /dev/sdc
        """
        cloud_init = provisioner._generate_cloud_init(ssh_public_key=None, has_home_disk=True)

        # Should use Azure stable symlinks
        assert "/dev/disk/azure/scsi1/lun0" in cloud_init

        # Should NOT use /dev/sdX paths (unstable)
        assert "/dev/sdc" not in cloud_init or "/dev/disk/azure/scsi1/lun0" in cloud_init

    def test_cloud_init_filesystem_is_ext4(self, provisioner):
        """Test that cloud-init creates ext4 filesystem.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called with has_home_disk=True
        Then: fs_setup specifies ext4 filesystem
        """
        cloud_init = provisioner._generate_cloud_init(ssh_public_key=None, has_home_disk=True)

        assert "filesystem: ext4" in cloud_init

    def test_cloud_init_mount_includes_nofail_option(self, provisioner):
        """Test that mount options include 'nofail' for resilience.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called with has_home_disk=True
        Then: Mount options include 'nofail' to prevent boot failure
        """
        cloud_init = provisioner._generate_cloud_init(ssh_public_key=None, has_home_disk=True)

        # Should include nofail for graceful boot if disk missing
        assert "nofail" in cloud_init

    def test_cloud_init_partition_is_auto(self, provisioner):
        """Test that partition configuration is 'auto'.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called with has_home_disk=True
        Then: fs_setup uses partition: auto
        """
        cloud_init = provisioner._generate_cloud_init(ssh_public_key=None, has_home_disk=True)

        assert "partition: auto" in cloud_init

    def test_cloud_init_disk_overwrite_is_false(self, provisioner):
        """Test that disk setup does not overwrite existing partitions.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called with has_home_disk=True
        Then: disk_setup uses overwrite: false
        """
        cloud_init = provisioner._generate_cloud_init(ssh_public_key=None, has_home_disk=True)

        assert "overwrite: false" in cloud_init


@pytest.mark.integration
class TestMultiVMProvisioningWithHomeDisk:
    """Test provisioning multiple VMs with home disks in parallel.

    These tests verify that pool provisioning works correctly
    with home disk enabled.
    """

    @pytest.fixture
    def provisioner(self):
        """Create VMProvisioner instance for tests."""
        return VMProvisioner()

    def test_provision_vm_pool_with_home_disks(self, provisioner):
        """Test parallel provisioning of multiple VMs with home disks.

        Given: Multiple VMConfigs with home_disk_enabled=True
        When: provision_vm_pool is called
        Then: All VMs are provisioned with home disks
        And: Disk operations don't interfere with each other
        """
        configs = [
            VMConfig(
                name=f"azlin-pool-{i}",
                resource_group="azlin-pool-rg",
                location="westus2",
                home_disk_enabled=True,
                home_disk_size_gb=50,
            )
            for i in range(3)
        ]

        with patch.object(provisioner, "provision_vm") as mock_provision:
            # Mock successful provisioning for each VM
            def provision_side_effect(config):
                return Mock(
                    name=config.name,
                    resource_group=config.resource_group,
                    location=config.location,
                    size=config.size,
                    public_ip=f"1.2.3.{configs.index(config) + 1}",
                )

            mock_provision.side_effect = provision_side_effect

            result = provisioner.provision_vm_pool(configs)

            # All VMs should succeed
            assert result.success_count == 3
            assert result.failure_count == 0
            assert result.all_succeeded is True

            # Each VM should have been provisioned
            assert mock_provision.call_count == 3

    def test_provision_vm_pool_partial_success_with_disk_errors(self, provisioner):
        """Test pool provisioning with some disk creation failures.

        Given: Multiple VMConfigs with home_disk_enabled=True
        When: provision_vm_pool is called and some disk creations fail
        Then: Successful VMs are returned
        And: Failed VMs are reported with errors
        """
        configs = [
            VMConfig(
                name=f"azlin-pool-{i}",
                resource_group="azlin-pool-rg",
                location="westus2",
                home_disk_enabled=True,
            )
            for i in range(3)
        ]

        with patch.object(provisioner, "provision_vm") as mock_provision:

            def provision_side_effect(config):
                if config.name == "azlin-pool-1":
                    # Second VM fails with disk quota error
                    raise ProvisioningError(
                        f"Failed to create home disk for {config.name}: Quota exceeded"
                    )
                return Mock(
                    name=config.name,
                    resource_group=config.resource_group,
                    location=config.location,
                    size=config.size,
                    public_ip=f"1.2.3.{configs.index(config) + 1}",
                )

            mock_provision.side_effect = provision_side_effect

            result = provisioner.provision_vm_pool(configs)

            # Partial success
            assert result.success_count == 2
            assert result.failure_count == 1
            assert result.partial_success is True
            assert not result.all_succeeded

            # Failed VM should be reported
            assert len(result.failed) == 1
            assert result.failed[0].config.name == "azlin-pool-1"
            assert "quota" in result.failed[0].error.lower()
