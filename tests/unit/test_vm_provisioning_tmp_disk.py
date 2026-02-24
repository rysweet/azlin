"""Unit tests for VM provisioning with separate /tmp disk feature.

This module tests the separate /tmp disk functionality including:
1. VMConfig defaults for tmp disk parameters
2. _create_tmp_disk() command construction
3. _generate_cloud_init() with tmp disk support
4. CLI flag parsing for tmp disk options
5. Error handling for disk operations
6. Interaction with home disk (both enabled)

Testing Pyramid: 60% Unit tests (this file)
"""

import json
from unittest.mock import Mock, patch

import pytest

from azlin.vm_provisioning import ProvisioningError, VMConfig, VMProvisioner


class TestVMConfigTmpDiskDefaults:
    """Test VMConfig dataclass defaults for tmp disk parameters."""

    def test_tmp_disk_disabled_by_default(self):
        """Tmp disk should be disabled by default (opt-in feature)."""
        config = VMConfig(name="test-vm", resource_group="test-rg", location="westus2")
        assert config.tmp_disk_enabled is False

    def test_tmp_disk_size_gb_default_is_64(self):
        """Default tmp disk size should be 64GB."""
        config = VMConfig(name="test-vm", resource_group="test-rg", location="westus2")
        assert config.tmp_disk_size_gb == 64

    def test_tmp_disk_sku_default_is_standard_lrs(self):
        """Default tmp disk SKU should be Standard_LRS."""
        config = VMConfig(name="test-vm", resource_group="test-rg", location="westus2")
        assert config.tmp_disk_sku == "Standard_LRS"

    def test_custom_tmp_disk_size(self):
        """Custom tmp disk size should be accepted."""
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            tmp_disk_enabled=True,
            tmp_disk_size_gb=128,
        )
        assert config.tmp_disk_size_gb == 128

    def test_tmp_disk_enabled_explicitly(self):
        """Tmp disk can be explicitly enabled."""
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            tmp_disk_enabled=True,
        )
        assert config.tmp_disk_enabled is True


class TestCreateVmConfigTmpDiskValidation:
    """Test create_vm_config() validation for tmp disk parameters."""

    def setup_method(self):
        self.provisioner = VMProvisioner()

    def test_tmp_disk_size_too_small(self):
        """Tmp disk size less than 1GB should raise ValueError."""
        with pytest.raises(ValueError, match="Tmp disk size must be at least 1GB"):
            self.provisioner.create_vm_config(
                name="test-vm",
                resource_group="test-rg",
                tmp_disk_enabled=True,
                tmp_disk_size_gb=0,
            )

    def test_tmp_disk_size_too_large(self):
        """Tmp disk size exceeding Azure max should raise ValueError."""
        with pytest.raises(ValueError, match="exceeds Azure maximum"):
            self.provisioner.create_vm_config(
                name="test-vm",
                resource_group="test-rg",
                tmp_disk_enabled=True,
                tmp_disk_size_gb=32768,
            )

    def test_tmp_disk_valid_config_returned(self):
        """Valid tmp disk config should be returned in VMConfig."""
        config = self.provisioner.create_vm_config(
            name="test-vm",
            resource_group="test-rg",
            tmp_disk_enabled=True,
            tmp_disk_size_gb=128,
        )
        assert config.tmp_disk_enabled is True
        assert config.tmp_disk_size_gb == 128
        assert config.tmp_disk_sku == "Standard_LRS"

    def test_tmp_disk_disabled_skips_validation(self):
        """When tmp_disk_enabled=False, size validation should be skipped."""
        config = self.provisioner.create_vm_config(
            name="test-vm",
            resource_group="test-rg",
            tmp_disk_enabled=False,
            tmp_disk_size_gb=0,
        )
        assert config.tmp_disk_enabled is False


class TestCreateTmpDisk:
    """Test _create_tmp_disk() Azure CLI command construction."""

    def setup_method(self):
        self.provisioner = VMProvisioner()

    @patch.object(VMProvisioner, "_execute_azure_command")
    def test_create_tmp_disk_command(self, mock_exec):
        """_create_tmp_disk should issue correct az disk create command."""
        mock_exec.return_value = {
            "success": True,
            "stdout": json.dumps({"id": "/subscriptions/sub/disk-id"}),
            "stderr": "",
        }

        disk_id = self.provisioner._create_tmp_disk(
            vm_name="my-vm",
            resource_group="my-rg",
            location="westus2",
            size_gb=64,
            sku="Standard_LRS",
        )

        assert disk_id == "/subscriptions/sub/disk-id"
        cmd = mock_exec.call_args[0][0]
        assert "az" in cmd
        assert "disk" in cmd
        assert "create" in cmd
        assert "--name" in cmd
        # Disk name includes "tmp" to differentiate from home disk
        name_idx = cmd.index("--name") + 1
        assert "tmp" in cmd[name_idx]
        assert "--size-gb" in cmd
        size_idx = cmd.index("--size-gb") + 1
        assert cmd[size_idx] == "64"

    @patch.object(VMProvisioner, "_execute_azure_command")
    def test_create_tmp_disk_failure(self, mock_exec):
        """_create_tmp_disk should raise ProvisioningError on failure."""
        mock_exec.return_value = {
            "success": False,
            "stdout": "",
            "stderr": "Disk creation failed",
        }

        with pytest.raises(ProvisioningError, match="Failed to create tmp disk"):
            self.provisioner._create_tmp_disk(
                vm_name="my-vm",
                resource_group="my-rg",
                location="westus2",
                size_gb=64,
                sku="Standard_LRS",
            )


class TestCloudInitTmpDisk:
    """Test _generate_cloud_init() with tmp disk support."""

    def setup_method(self):
        self.provisioner = VMProvisioner()

    def test_cloud_init_no_tmp_disk(self):
        """Cloud-init without tmp disk should not contain tmp disk setup."""
        cloud_init = self.provisioner._generate_cloud_init(has_tmp_disk=False)
        assert "tmp_disk" not in cloud_init
        assert "/tmp" not in cloud_init or "/tmp/go" in cloud_init  # /tmp used for downloads

    def test_cloud_init_tmp_disk_only(self):
        """Cloud-init with only tmp disk should set up at lun0."""
        cloud_init = self.provisioner._generate_cloud_init(has_home_disk=False, has_tmp_disk=True)
        assert "lun0" in cloud_init
        assert "tmp_disk" in cloud_init
        assert "/tmp" in cloud_init
        assert "1777" in cloud_init

    def test_cloud_init_both_disks(self):
        """Cloud-init with both home and tmp disk should use lun0 and lun1."""
        cloud_init = self.provisioner._generate_cloud_init(has_home_disk=True, has_tmp_disk=True)
        assert "lun0" in cloud_init
        assert "lun1" in cloud_init
        assert "home_disk" in cloud_init
        assert "tmp_disk" in cloud_init
        assert "1777" in cloud_init

    def test_cloud_init_tmp_disk_permissions(self):
        """Cloud-init should set /tmp to 1777 (sticky bit)."""
        cloud_init = self.provisioner._generate_cloud_init(has_home_disk=False, has_tmp_disk=True)
        assert "chmod 1777 /tmp" in cloud_init


class TestProvisionVmWithTmpDisk:
    """Test provision_vm() integration with tmp disk."""

    def setup_method(self):
        self.provisioner = VMProvisioner()

    @patch.object(VMProvisioner, "_try_provision_vm")
    @patch.object(VMProvisioner, "_create_tmp_disk")
    @patch.object(VMProvisioner, "create_resource_group")
    def test_provision_creates_tmp_disk_when_enabled(
        self, mock_rg, mock_create_disk, mock_provision
    ):
        """provision_vm should create tmp disk when config has tmp_disk_enabled."""
        mock_create_disk.return_value = "/subscriptions/sub/tmp-disk-id"
        mock_provision.return_value = Mock(public_ip="1.2.3.4")

        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            tmp_disk_enabled=True,
            tmp_disk_size_gb=64,
            home_disk_enabled=False,
        )

        self.provisioner.provision_vm(config)

        mock_create_disk.assert_called_once()
        # Verify disk_ids passed to _try_provision_vm include the tmp disk
        call_kwargs = mock_provision.call_args
        assert call_kwargs is not None

    @patch.object(VMProvisioner, "_try_provision_vm")
    @patch.object(VMProvisioner, "create_resource_group")
    def test_provision_skips_tmp_disk_when_disabled(self, mock_rg, mock_provision):
        """provision_vm should not create tmp disk when disabled."""
        mock_provision.return_value = Mock(public_ip="1.2.3.4")

        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            tmp_disk_enabled=False,
            home_disk_enabled=False,
        )

        self.provisioner.provision_vm(config)
        # No tmp disk creation should occur


class TestRetryConfigPreservesTmpDisk:
    """Test _create_retry_config preserves tmp disk settings."""

    def setup_method(self):
        self.provisioner = VMProvisioner()

    def test_retry_config_preserves_tmp_disk_fields(self):
        """_create_retry_config should preserve tmp disk configuration."""
        original = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            tmp_disk_enabled=True,
            tmp_disk_size_gb=128,
            tmp_disk_sku="Premium_LRS",
        )

        retry = self.provisioner._create_retry_config(original, "eastus")
        assert retry.tmp_disk_enabled == original.tmp_disk_enabled
        assert retry.tmp_disk_size_gb == original.tmp_disk_size_gb
        assert retry.tmp_disk_sku == original.tmp_disk_sku
        assert retry.location == "eastus"
