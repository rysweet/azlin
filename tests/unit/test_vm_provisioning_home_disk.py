"""Unit tests for VM provisioning with separate /home disk feature.

This module tests the separate /home disk functionality including:
1. VMConfig defaults for home disk parameters
2. _create_home_disk() command construction
3. _attach_home_disk() command construction
4. _generate_cloud_init() with home disk support
5. CLI flag parsing for home disk options
6. Error handling for disk operations
7. NFS precedence logic (NFS disables home disk)

Test Philosophy:
- Comprehensive coverage following testing pyramid (60% unit)
- All tests FAIL initially (TDD approach)
- Mock Azure CLI calls to avoid real API usage
- Clear test names describing expected behavior
- Test valid cases, invalid cases, and edge cases

Testing Pyramid Distribution:
- 60% Unit tests (this file) - Fast, heavily mocked
- 30% Integration tests (separate file) - Multiple components
- 10% E2E tests (separate file) - Complete workflows
"""

from unittest.mock import Mock, patch

import pytest

from azlin.vm_provisioning import ProvisioningError, VMConfig, VMProvisioner


class TestVMConfigDefaults:
    """Test VMConfig dataclass defaults for home disk parameters.

    These tests verify that VMConfig has correct default values
    for home disk configuration fields.
    """

    def test_home_disk_enabled_default_is_true(self):
        """Test that home_disk_enabled defaults to True.

        Given: A new VMConfig instance without home_disk_enabled specified
        When: VMConfig is created with minimal required fields
        Then: home_disk_enabled should be True
        """
        config = VMConfig(name="test-vm", resource_group="test-rg", location="westus2")
        assert config.home_disk_enabled is True

    def test_home_disk_size_gb_default_is_100(self):
        """Test that home_disk_size_gb defaults to 100GB.

        Given: A new VMConfig instance without home_disk_size_gb specified
        When: VMConfig is created with minimal required fields
        Then: home_disk_size_gb should be 100
        """
        config = VMConfig(name="test-vm", resource_group="test-rg", location="westus2")
        assert config.home_disk_size_gb == 100

    def test_home_disk_sku_default_is_standard_lrs(self):
        """Test that home_disk_sku defaults to Standard_LRS.

        Given: A new VMConfig instance without home_disk_sku specified
        When: VMConfig is created with minimal required fields
        Then: home_disk_sku should be "Standard_LRS"
        """
        config = VMConfig(name="test-vm", resource_group="test-rg", location="westus2")
        assert config.home_disk_sku == "Standard_LRS"

    def test_custom_home_disk_size(self):
        """Test that custom home disk size can be specified.

        Given: A VMConfig with custom home_disk_size_gb
        When: VMConfig is created with home_disk_size_gb=200
        Then: home_disk_size_gb should be 200
        """
        config = VMConfig(
            name="test-vm", resource_group="test-rg", location="westus2", home_disk_size_gb=200
        )
        assert config.home_disk_size_gb == 200

    def test_disable_home_disk(self):
        """Test that home disk can be disabled.

        Given: A VMConfig with home_disk_enabled=False
        When: VMConfig is created
        Then: home_disk_enabled should be False
        """
        config = VMConfig(
            name="test-vm", resource_group="test-rg", location="westus2", home_disk_enabled=False
        )
        assert config.home_disk_enabled is False

    def test_custom_home_disk_sku(self):
        """Test that custom home disk SKU can be specified.

        Given: A VMConfig with custom home_disk_sku
        When: VMConfig is created with home_disk_sku="Premium_LRS"
        Then: home_disk_sku should be "Premium_LRS"
        """
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            home_disk_sku="Premium_LRS",
        )
        assert config.home_disk_sku == "Premium_LRS"


class TestCreateHomeDisk:
    """Test _create_home_disk() method for disk creation command construction.

    These tests verify that the Azure CLI command for creating
    a managed disk is constructed correctly.
    """

    def test_create_home_disk_command_structure(self):
        """Test that _create_home_disk constructs correct az disk create command.

        Given: A VMProvisioner instance
        When: _create_home_disk is called with standard parameters
        Then: Returns disk resource ID
        And: Executes correct az disk create command
        """
        provisioner = VMProvisioner()

        with patch.object(provisioner, "_execute_azure_command") as mock_exec:
            # Mock successful disk creation returning resource ID
            mock_exec.return_value = {
                "success": True,
                "stdout": '{"id": "/subscriptions/sub-id/resourceGroups/test-rg/providers/Microsoft.Compute/disks/test-vm-home-westus2"}',
                "stderr": "",
                "returncode": 0,
            }

            disk_id = provisioner._create_home_disk(
                vm_name="test-vm",
                resource_group="test-rg",
                location="westus2",
                size_gb=100,
                sku="Standard_LRS",
            )

            # Verify command was called with correct parameters
            mock_exec.assert_called_once()
            cmd = mock_exec.call_args[0][0]

            assert cmd[0] == "az"
            assert cmd[1] == "disk"
            assert cmd[2] == "create"
            assert "--name" in cmd
            assert "test-vm-home-westus2" in cmd
            assert "--resource-group" in cmd
            assert "test-rg" in cmd
            assert "--location" in cmd
            assert "westus2" in cmd
            assert "--size-gb" in cmd
            assert "100" in cmd
            assert "--sku" in cmd
            assert "Standard_LRS" in cmd
            assert "--output" in cmd
            assert "json" in cmd

            # Verify return value
            assert "/subscriptions/" in disk_id
            assert "test-vm-home-westus2" in disk_id

    def test_create_home_disk_with_custom_size(self):
        """Test _create_home_disk with custom disk size.

        Given: A VMProvisioner instance
        When: _create_home_disk is called with size_gb=200
        Then: Command includes --size-gb 200
        """
        provisioner = VMProvisioner()

        with patch.object(provisioner, "_execute_azure_command") as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "stdout": '{"id": "/subscriptions/sub-id/resourceGroups/test-rg/providers/Microsoft.Compute/disks/test-vm-home-westus2"}',
                "stderr": "",
                "returncode": 0,
            }

            provisioner._create_home_disk(
                vm_name="test-vm",
                resource_group="test-rg",
                location="westus2",
                size_gb=200,
                sku="Standard_LRS",
            )

            cmd = mock_exec.call_args[0][0]
            size_idx = cmd.index("--size-gb")
            assert cmd[size_idx + 1] == "200"

    def test_create_home_disk_with_premium_sku(self):
        """Test _create_home_disk with Premium_LRS SKU.

        Given: A VMProvisioner instance
        When: _create_home_disk is called with sku="Premium_LRS"
        Then: Command includes --sku Premium_LRS
        """
        provisioner = VMProvisioner()

        with patch.object(provisioner, "_execute_azure_command") as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "stdout": '{"id": "/subscriptions/sub-id/resourceGroups/test-rg/providers/Microsoft.Compute/disks/test-vm-home-westus2"}',
                "stderr": "",
                "returncode": 0,
            }

            provisioner._create_home_disk(
                vm_name="test-vm",
                resource_group="test-rg",
                location="westus2",
                size_gb=100,
                sku="Premium_LRS",
            )

            cmd = mock_exec.call_args[0][0]
            sku_idx = cmd.index("--sku")
            assert cmd[sku_idx + 1] == "Premium_LRS"

    def test_create_home_disk_failure_raises_error(self):
        """Test that _create_home_disk raises ProvisioningError on failure.

        Given: A VMProvisioner instance
        When: _create_home_disk fails (Azure CLI returns error)
        Then: Raises ProvisioningError with descriptive message
        """
        provisioner = VMProvisioner()

        with patch.object(provisioner, "_execute_azure_command") as mock_exec:
            mock_exec.return_value = {
                "success": False,
                "stdout": "",
                "stderr": "Error: QuotaExceeded - Disk quota exceeded",
                "returncode": 1,
            }

            with pytest.raises(ProvisioningError) as exc_info:
                provisioner._create_home_disk(
                    vm_name="test-vm",
                    resource_group="test-rg",
                    location="westus2",
                    size_gb=100,
                    sku="Standard_LRS",
                )

            assert "Failed to create home disk" in str(exc_info.value)
            assert "test-vm-home-westus2" in str(exc_info.value)

    def test_create_home_disk_naming_convention(self):
        """Test that home disk follows naming convention: {vm_name}-home.

        Given: A VMProvisioner instance
        When: _create_home_disk is called for VM "my-dev-vm"
        Then: Disk is named "my-dev-vm-home-westus2"
        """
        provisioner = VMProvisioner()

        with patch.object(provisioner, "_execute_azure_command") as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "stdout": '{"id": "/subscriptions/sub-id/resourceGroups/test-rg/providers/Microsoft.Compute/disks/my-dev-vm-home-westus2"}',
                "stderr": "",
                "returncode": 0,
            }

            provisioner._create_home_disk(
                vm_name="my-dev-vm",
                resource_group="test-rg",
                location="westus2",
                size_gb=100,
                sku="Standard_LRS",
            )

            cmd = mock_exec.call_args[0][0]
            name_idx = cmd.index("--name")
            assert cmd[name_idx + 1] == "my-dev-vm-home-westus2"


class TestAttachHomeDisk:
    """Test _attach_home_disk() method for disk attachment command construction.

    These tests verify that the Azure CLI command for attaching
    a managed disk to a VM is constructed correctly.
    """

    def test_attach_home_disk_command_structure(self):
        """Test that _attach_home_disk constructs correct az vm disk attach command.

        Given: A VMProvisioner instance
        When: _attach_home_disk is called with disk resource ID
        Then: Returns LUN number
        And: Executes correct az vm disk attach command
        """
        provisioner = VMProvisioner()

        with patch.object(provisioner, "_execute_azure_command") as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "stdout": '{"lun": 0}',
                "stderr": "",
                "returncode": 0,
            }

            disk_id = "/subscriptions/sub-id/resourceGroups/test-rg/providers/Microsoft.Compute/disks/test-vm-home-westus2"
            lun = provisioner._attach_home_disk(
                vm_name="test-vm", resource_group="test-rg", disk_id=disk_id
            )

            # Verify command was called with correct parameters
            mock_exec.assert_called_once()
            cmd = mock_exec.call_args[0][0]

            assert cmd[0] == "az"
            assert cmd[1] == "vm"
            assert cmd[2] == "disk"
            assert cmd[3] == "attach"
            assert "--vm-name" in cmd
            assert "test-vm" in cmd
            assert "--resource-group" in cmd
            assert "test-rg" in cmd
            assert "--ids" in cmd or "--disk" in cmd  # Either flag works
            assert disk_id in cmd
            assert "--output" in cmd
            assert "json" in cmd

            # Verify return value
            assert lun == "0"

    def test_attach_home_disk_failure_raises_error(self):
        """Test that _attach_home_disk raises ProvisioningError on failure.

        Given: A VMProvisioner instance
        When: _attach_home_disk fails (Azure CLI returns error)
        Then: Raises ProvisioningError with descriptive message
        """
        provisioner = VMProvisioner()

        with patch.object(provisioner, "_execute_azure_command") as mock_exec:
            mock_exec.return_value = {
                "success": False,
                "stdout": "",
                "stderr": "Error: VM not found",
                "returncode": 1,
            }

            disk_id = "/subscriptions/sub-id/resourceGroups/test-rg/providers/Microsoft.Compute/disks/test-vm-home-westus2"

            with pytest.raises(ProvisioningError) as exc_info:
                provisioner._attach_home_disk(
                    vm_name="test-vm", resource_group="test-rg", disk_id=disk_id
                )

            assert "Failed to attach home disk" in str(exc_info.value)
            assert "test-vm" in str(exc_info.value)

    def test_attach_home_disk_returns_lun(self):
        """Test that _attach_home_disk returns LUN number from Azure response.

        Given: A VMProvisioner instance
        When: _attach_home_disk succeeds
        Then: Returns LUN number as string
        """
        provisioner = VMProvisioner()

        with patch.object(provisioner, "_execute_azure_command") as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "stdout": '{"lun": 0}',
                "stderr": "",
                "returncode": 0,
            }

            disk_id = "/subscriptions/sub-id/resourceGroups/test-rg/providers/Microsoft.Compute/disks/test-vm-home-westus2"
            lun = provisioner._attach_home_disk(
                vm_name="test-vm", resource_group="test-rg", disk_id=disk_id
            )

            assert lun == "0"
            assert isinstance(lun, str)


class TestGenerateCloudInitWithHomeDisk:
    """Test _generate_cloud_init() with home disk support.

    These tests verify that cloud-init includes disk setup sections
    when has_home_disk=True and excludes them when False.
    """

    def test_generate_cloud_init_with_home_disk_includes_disk_setup(self):
        """Test that cloud-init includes disk_setup section when has_home_disk=True.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called with has_home_disk=True
        Then: Returns cloud-init containing disk_setup section
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init(ssh_public_key=None, has_home_disk=True)

        assert "disk_setup:" in cloud_init
        assert "/dev/disk/azure/scsi1/lun0" in cloud_init or "/dev/sdc" in cloud_init
        assert "table_type: gpt" in cloud_init
        assert "layout: true" in cloud_init
        assert "overwrite: false" in cloud_init

    def test_generate_cloud_init_with_home_disk_includes_fs_setup(self):
        """Test that cloud-init includes fs_setup section when has_home_disk=True.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called with has_home_disk=True
        Then: Returns cloud-init containing fs_setup section with ext4 filesystem
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init(ssh_public_key=None, has_home_disk=True)

        assert "fs_setup:" in cloud_init
        assert "filesystem: ext4" in cloud_init
        assert (
            "device: /dev/disk/azure/scsi1/lun0-part1" in cloud_init
            or "device: /dev/sdc1" in cloud_init
        )
        assert "partition: auto" in cloud_init

    def test_generate_cloud_init_with_home_disk_includes_mounts(self):
        """Test that cloud-init includes mounts section when has_home_disk=True.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called with has_home_disk=True
        Then: Returns cloud-init containing mounts section for /home
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init(ssh_public_key=None, has_home_disk=True)

        assert "mounts:" in cloud_init
        assert "/home" in cloud_init
        assert "ext4" in cloud_init
        assert "defaults,nofail" in cloud_init or "defaults" in cloud_init

    def test_generate_cloud_init_without_home_disk_excludes_disk_sections(self):
        """Test that cloud-init excludes disk sections when has_home_disk=False.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called with has_home_disk=False
        Then: Returns cloud-init without disk_setup, fs_setup, or mounts sections
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init(ssh_public_key=None, has_home_disk=False)

        assert "disk_setup:" not in cloud_init
        assert "fs_setup:" not in cloud_init
        # Note: mounts might still exist for other purposes, but not for /home
        if "mounts:" in cloud_init:
            assert "/home" not in cloud_init

    def test_generate_cloud_init_default_behavior_no_home_disk(self):
        """Test that _generate_cloud_init defaults to has_home_disk=False.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called without has_home_disk parameter
        Then: Returns cloud-init without disk sections (backwards compatible)
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init(ssh_public_key=None)

        assert "disk_setup:" not in cloud_init
        assert "fs_setup:" not in cloud_init

    def test_generate_cloud_init_with_home_disk_and_ssh_key(self):
        """Test that cloud-init includes both SSH key and disk setup.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called with both ssh_public_key and has_home_disk=True
        Then: Returns cloud-init containing both ssh_authorized_keys and disk sections
        """
        provisioner = VMProvisioner()
        ssh_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC... test@example.com"
        cloud_init = provisioner._generate_cloud_init(ssh_public_key=ssh_key, has_home_disk=True)

        # Both features should be present
        assert "ssh_authorized_keys:" in cloud_init
        assert ssh_key in cloud_init
        assert "disk_setup:" in cloud_init
        assert "fs_setup:" in cloud_init
        assert "mounts:" in cloud_init

    def test_generate_cloud_init_disk_device_path_uses_azure_symlink(self):
        """Test that cloud-init uses Azure stable device symlinks.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called with has_home_disk=True
        Then: Uses /dev/disk/azure/scsi1/lun0 instead of /dev/sdc
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init(ssh_public_key=None, has_home_disk=True)

        # Prefer Azure stable paths over /dev/sdX which can change
        assert "/dev/disk/azure/scsi1/lun0" in cloud_init
        # Partition should reference lun0-part1
        assert "/dev/disk/azure/scsi1/lun0-part1" in cloud_init

    def test_generate_cloud_init_mount_options_include_nofail(self):
        """Test that mount options include 'nofail' for resilience.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called with has_home_disk=True
        Then: Mount options include 'nofail' to prevent boot failure if disk missing
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init(ssh_public_key=None, has_home_disk=True)

        # Should have nofail option for graceful degradation
        assert "nofail" in cloud_init


class TestProvisionVMWithHomeDisk:
    """Test VM provisioning integration with home disk creation and attachment.

    These tests verify the complete workflow:
    1. Create home disk before VM provisioning
    2. Provision VM with home disk-aware cloud-init
    3. Disk is attached DURING VM creation (not after) via --attach-data-disks
    4. Error handling with graceful degradation
    """

    def test_provision_vm_with_home_disk_enabled(self, mock_azure_cli_in_ci):
        """Test that provision_vm creates disk and passes disk_id to _try_provision_vm.

        Given: A VMConfig with home_disk_enabled=True
        When: provision_vm is called
        Then: Creates home disk and passes disk_id to _try_provision_vm

        Note: Disk is now attached DURING VM creation via --attach-data-disks flag,
        not after VM creation. This ensures cloud-init can find the disk during boot.

        Runs with real Azure CLI locally, mocked in CI.
        """

        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            home_disk_enabled=True,
            home_disk_size_gb=100,
            home_disk_sku="Standard_LRS",
        )

        with (
            patch.object(provisioner, "_create_home_disk") as mock_create,
            patch.object(provisioner, "_try_provision_vm") as mock_provision,
        ):
            # Mock successful operations
            disk_id = "/subscriptions/sub-id/resourceGroups/test-rg/providers/Microsoft.Compute/disks/test-vm-home-westus2"
            mock_create.return_value = disk_id
            mock_vm = Mock()
            mock_vm.name = "test-vm"
            mock_vm.resource_group = "test-rg"
            mock_vm.location = "westus2"
            mock_vm.size = "Standard_D2s_v3"
            mock_vm.public_ip = "1.2.3.4"
            mock_provision.return_value = mock_vm

            result = provisioner.provision_vm(config)

            # Verify home disk was created before VM
            mock_create.assert_called_once_with(
                vm_name="test-vm",
                resource_group="test-rg",
                location="westus2",
                size_gb=100,
                sku="Standard_LRS",
            )

            # Verify VM was provisioned with disk_id parameter
            mock_provision.assert_called_once()
            call_kwargs = mock_provision.call_args[1]
            assert call_kwargs.get("disk_id") == disk_id
            assert call_kwargs.get("has_home_disk") is True

            assert result.name == "test-vm"

    def test_provision_vm_without_home_disk_skips_disk_operations(self, mock_azure_cli_in_ci):
        """Test that provision_vm skips disk operations when home_disk_enabled=False.

        Given: A VMConfig with home_disk_enabled=False
        When: provision_vm is called
        Then: Does not create or attach home disk

        Note: _generate_cloud_init() is called inside _try_provision_vm() which is mocked,
        so we don't assert on cloud-init generation here.

        Runs with real Azure CLI locally, mocked in CI.
        """

        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm", resource_group="test-rg", location="westus2", home_disk_enabled=False
        )

        with (
            patch.object(provisioner, "_create_home_disk") as mock_create,
            patch.object(provisioner, "_try_provision_vm") as mock_provision,
            patch.object(provisioner, "_attach_home_disk") as mock_attach,
        ):
            mock_vm = Mock()
            mock_vm.name = "test-vm"
            mock_vm.resource_group = "test-rg"
            mock_vm.location = "westus2"
            mock_vm.size = "Standard_D2s_v3"
            mock_vm.public_ip = "1.2.3.4"
            mock_provision.return_value = mock_vm

            result = provisioner.provision_vm(config)

            # Verify disk operations were NOT called
            mock_create.assert_not_called()
            mock_attach.assert_not_called()

            # Verify VM was provisioned
            mock_provision.assert_called_once()

            assert result.name == "test-vm"

    def test_provision_vm_home_disk_creation_failure_stops_provisioning(self, mock_azure_cli_in_ci):
        """Test that VM provisioning stops if home disk creation fails.

        Given: A VMConfig with home_disk_enabled=True
        When: Home disk creation fails
        Then: Raises ProvisioningError without attempting VM creation

        Runs with real Azure CLI locally, mocked in CI.
        """

        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm", resource_group="test-rg", location="westus2", home_disk_enabled=True
        )

        with (
            patch.object(provisioner, "_create_home_disk") as mock_create,
            patch.object(provisioner, "_try_provision_vm") as mock_provision,
        ):
            # Mock disk creation failure
            mock_create.side_effect = ProvisioningError("Disk quota exceeded")

            with pytest.raises(ProvisioningError) as exc_info:
                provisioner.provision_vm(config)

            assert "Disk quota exceeded" in str(exc_info.value)

            # Verify VM provisioning was never attempted
            mock_provision.assert_not_called()

    def test_provision_vm_with_home_disk_passes_disk_id_to_try_provision(
        self, mock_azure_cli_in_ci
    ):
        """Test that provision_vm correctly passes disk_id for --attach-data-disks flag.

        Given: A VMConfig with home_disk_enabled=True
        When: provision_vm is called
        Then: _try_provision_vm is called with disk_id parameter
        And: disk_id is the resource ID from _create_home_disk

        Note: The disk is attached during VM creation (not after) via the
        --attach-data-disks flag in az vm create. This ensures cloud-init
        can find the disk during boot for disk_setup/fs_setup/mounts.

        Runs with real Azure CLI locally, mocked in CI.
        """

        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm", resource_group="test-rg", location="westus2", home_disk_enabled=True
        )

        with (
            patch.object(provisioner, "_create_home_disk") as mock_create,
            patch.object(provisioner, "_try_provision_vm") as mock_provision,
        ):
            disk_id = "/subscriptions/sub-id/resourceGroups/test-rg/providers/Microsoft.Compute/disks/test-vm-home-westus2"
            mock_create.return_value = disk_id
            mock_vm = Mock()
            mock_vm.name = "test-vm"
            mock_vm.resource_group = "test-rg"
            mock_vm.location = "westus2"
            mock_vm.size = "Standard_D2s_v3"
            mock_vm.public_ip = "1.2.3.4"
            mock_provision.return_value = mock_vm

            result = provisioner.provision_vm(config)

            assert result.name == "test-vm"

            # Verify _try_provision_vm was called with disk_id parameter
            mock_provision.assert_called_once()
            call_kwargs = mock_provision.call_args[1]
            assert "disk_id" in call_kwargs
            assert call_kwargs["disk_id"] == disk_id


class TestCLIHomeDiskFlags:
    """Test CLI flag parsing for home disk options.

    These tests verify that the NewCommand properly handles
    --home-disk-size and --no-home-disk flags.
    """

    def test_new_command_accepts_home_disk_size_flag(self):
        """Test that NewCommand accepts --home-disk-size flag.

        Given: azlin new command invocation
        When: --home-disk-size 200 is provided
        Then: VMConfig is created with home_disk_size_gb=200
        """
        from azlin.cli import CLIOrchestrator

        orchestrator = CLIOrchestrator(home_disk_size=200)
        assert orchestrator.home_disk_size == 200

    def test_new_command_accepts_no_home_disk_flag(self):
        """Test that NewCommand accepts --no-home-disk flag.

        Given: azlin new command invocation
        When: --no-home-disk is provided
        Then: VMConfig is created with home_disk_enabled=False
        """
        from azlin.cli import CLIOrchestrator

        orchestrator = CLIOrchestrator(no_home_disk=True)
        assert orchestrator.no_home_disk is True

    def test_new_command_home_disk_enabled_by_default(self):
        """Test that home disk is enabled by default.

        Given: azlin new command invocation without disk flags
        When: No --no-home-disk flag is provided
        Then: VMConfig is created with home_disk_enabled=True
        """
        from azlin.cli import CLIOrchestrator

        orchestrator = CLIOrchestrator()
        # Default values: no_home_disk=False, home_disk_size=None (will use 100 default)
        assert orchestrator.no_home_disk is False
        assert orchestrator.home_disk_size is None


class TestNFSPrecedenceLogic:
    """Test that NFS storage takes precedence over home disk.

    These tests verify that when NFS storage is enabled,
    home disk is automatically disabled (NFS provides /home).
    """

    def test_nfs_storage_disables_home_disk(self):
        """Test that NFS storage automatically disables home disk.

        Given: A NewCommand with both nfs_storage and home disk configured
        When: Command determines home disk configuration
        Then: home_disk_enabled is False (NFS takes precedence)
        """
        from unittest.mock import Mock, patch

        from azlin.cli import CLIOrchestrator

        orchestrator = CLIOrchestrator(nfs_storage="my-nfs-storage")

        # Mock dependencies for _provision_vm
        with (
            patch.object(orchestrator, "_check_bastion_availability") as mock_bastion,
            patch.object(orchestrator.provisioner, "create_vm_config") as mock_create_config,
            patch.object(orchestrator.provisioner, "provision_vm") as mock_provision,
        ):
            mock_bastion.return_value = (False, None)
            mock_vm = Mock()
            mock_vm.public_ip = "1.2.3.4"
            mock_provision.return_value = mock_vm

            # Call _provision_vm which should compute home_disk_enabled=False
            orchestrator._provision_vm("test-vm", "test-rg", "ssh-key")

            # Verify create_vm_config was called with home_disk_enabled=False
            mock_create_config.assert_called_once()
            call_kwargs = mock_create_config.call_args[1]
            assert call_kwargs["home_disk_enabled"] is False

    def test_no_nfs_flag_allows_home_disk(self):
        """Test that --no-nfs flag allows home disk.

        Given: A NewCommand with --no-nfs flag
        When: No NFS storage is configured
        Then: home_disk_enabled remains True (unless --no-home-disk specified)
        """
        from unittest.mock import Mock, patch

        from azlin.cli import CLIOrchestrator

        orchestrator = CLIOrchestrator(no_nfs=True)

        # Mock dependencies for _provision_vm
        with (
            patch.object(orchestrator, "_check_bastion_availability") as mock_bastion,
            patch.object(orchestrator.provisioner, "create_vm_config") as mock_create_config,
            patch.object(orchestrator.provisioner, "provision_vm") as mock_provision,
        ):
            mock_bastion.return_value = (False, None)
            mock_vm = Mock()
            mock_vm.public_ip = "1.2.3.4"
            mock_provision.return_value = mock_vm

            # Call _provision_vm which should compute home_disk_enabled=True
            orchestrator._provision_vm("test-vm", "test-rg", "ssh-key")

            # Verify create_vm_config was called with home_disk_enabled=True
            mock_create_config.assert_called_once()
            call_kwargs = mock_create_config.call_args[1]
            assert call_kwargs["home_disk_enabled"] is True

    def test_explicit_no_home_disk_overrides_nfs_logic(self):
        """Test that --no-home-disk always disables home disk.

        Given: A NewCommand with --no-home-disk flag
        When: Command determines configuration
        Then: home_disk_enabled is False (regardless of NFS)
        """
        from unittest.mock import Mock, patch

        from azlin.cli import CLIOrchestrator

        # Even with no_nfs=True, no_home_disk=True should disable home disk
        orchestrator = CLIOrchestrator(no_nfs=True, no_home_disk=True)

        # Mock dependencies for _provision_vm
        with (
            patch.object(orchestrator, "_check_bastion_availability") as mock_bastion,
            patch.object(orchestrator.provisioner, "create_vm_config") as mock_create_config,
            patch.object(orchestrator.provisioner, "provision_vm") as mock_provision,
        ):
            mock_bastion.return_value = (False, None)
            mock_vm = Mock()
            mock_vm.public_ip = "1.2.3.4"
            mock_provision.return_value = mock_vm

            # Call _provision_vm which should compute home_disk_enabled=False
            orchestrator._provision_vm("test-vm", "test-rg", "ssh-key")

            # Verify create_vm_config was called with home_disk_enabled=False
            mock_create_config.assert_called_once()
            call_kwargs = mock_create_config.call_args[1]
            assert call_kwargs["home_disk_enabled"] is False


class TestHomeDiskSizeValidation:
    """Test home disk size validation in create_vm_config.

    These tests verify that disk size validation catches invalid
    sizes before VM provisioning begins.
    """

    def test_home_disk_size_validation_too_small(self):
        """Test that home disk size < 1GB raises ValueError.

        Given: A VMProvisioner instance
        When: create_vm_config is called with home_disk_size_gb=0
        Then: Raises ValueError with "at least 1GB" message
        """
        provisioner = VMProvisioner()

        with pytest.raises(ValueError, match="at least 1GB"):
            provisioner.create_vm_config(
                name="test-vm",
                resource_group="test-rg",
                location="westus2",
                home_disk_enabled=True,
                home_disk_size_gb=0,  # Invalid - too small
            )

    def test_home_disk_size_validation_too_large(self):
        """Test that home disk size > 32TB raises ValueError.

        Given: A VMProvisioner instance
        When: create_vm_config is called with home_disk_size_gb=40000 (> 32TB)
        Then: Raises ValueError with "exceeds Azure maximum" message
        """
        provisioner = VMProvisioner()

        with pytest.raises(ValueError, match="exceeds Azure maximum"):
            provisioner.create_vm_config(
                name="test-vm",
                resource_group="test-rg",
                location="westus2",
                home_disk_enabled=True,
                home_disk_size_gb=40000,  # Invalid - exceeds 32TB limit
            )

    def test_home_disk_size_validation_minimum_valid(self):
        """Test that home disk size = 1GB is valid.

        Given: A VMProvisioner instance
        When: create_vm_config is called with home_disk_size_gb=1
        Then: Returns VMConfig successfully (no exception)
        """
        provisioner = VMProvisioner()

        config = provisioner.create_vm_config(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            home_disk_enabled=True,
            home_disk_size_gb=1,  # Minimum valid size
        )

        assert config.home_disk_size_gb == 1

    def test_home_disk_size_validation_maximum_valid(self):
        """Test that home disk size = 32767GB (32TB) is valid.

        Given: A VMProvisioner instance
        When: create_vm_config is called with home_disk_size_gb=32767
        Then: Returns VMConfig successfully (no exception)
        """
        provisioner = VMProvisioner()

        config = provisioner.create_vm_config(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            home_disk_enabled=True,
            home_disk_size_gb=32767,  # Maximum valid size (32TB)
        )

        assert config.home_disk_size_gb == 32767

    def test_home_disk_disabled_skips_size_validation(self):
        """Test that size validation is skipped when home_disk_enabled=False.

        Given: A VMProvisioner instance
        When: create_vm_config is called with home_disk_enabled=False and invalid size
        Then: Returns VMConfig successfully (validation skipped)
        """
        provisioner = VMProvisioner()

        # Should not raise even with invalid size, since home disk is disabled
        config = provisioner.create_vm_config(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            home_disk_enabled=False,
            home_disk_size_gb=0,  # Invalid, but home disk disabled
        )

        assert config.home_disk_enabled is False
        assert config.home_disk_size_gb == 0


class TestHomeDiskErrorHandling:
    """Test error handling for home disk operations.

    These tests verify that disk operation errors are handled
    gracefully with clear error messages.
    """

    def test_create_home_disk_quota_error(self):
        """Test that disk quota errors are handled clearly.

        Given: A VMProvisioner instance
        When: Disk creation fails due to quota exceeded
        Then: Raises ProvisioningError with quota-specific message
        """
        provisioner = VMProvisioner()

        with patch.object(provisioner, "_execute_azure_command") as mock_exec:
            mock_exec.return_value = {
                "success": False,
                "stdout": "",
                "stderr": "QuotaExceeded: Disk count quota exceeded in region westus2",
                "returncode": 1,
            }

            with pytest.raises(ProvisioningError) as exc_info:
                provisioner._create_home_disk(
                    vm_name="test-vm",
                    resource_group="test-rg",
                    location="westus2",
                    size_gb=100,
                    sku="Standard_LRS",
                )

            error_msg = str(exc_info.value)
            assert "quota" in error_msg.lower()
            assert "westus2" in error_msg

    def test_attach_home_disk_vm_not_found_error(self):
        """Test that VM not found errors are handled clearly.

        Given: A VMProvisioner instance
        When: Disk attachment fails because VM doesn't exist
        Then: Raises ProvisioningError with VM-specific message
        """
        provisioner = VMProvisioner()

        with patch.object(provisioner, "_execute_azure_command") as mock_exec:
            mock_exec.return_value = {
                "success": False,
                "stdout": "",
                "stderr": "ResourceNotFound: VM 'test-vm' not found",
                "returncode": 1,
            }

            disk_id = "/subscriptions/sub-id/resourceGroups/test-rg/providers/Microsoft.Compute/disks/test-vm-home-westus2"

            with pytest.raises(ProvisioningError) as exc_info:
                provisioner._attach_home_disk(
                    vm_name="test-vm", resource_group="test-rg", disk_id=disk_id
                )

            error_msg = str(exc_info.value)
            assert "not found" in error_msg.lower()
            assert "test-vm" in error_msg

    def test_attach_home_disk_disk_not_found_error(self):
        """Test that disk not found errors are handled clearly.

        Given: A VMProvisioner instance
        When: Disk attachment fails because disk doesn't exist
        Then: Raises ProvisioningError with disk-specific message
        """
        provisioner = VMProvisioner()

        with patch.object(provisioner, "_execute_azure_command") as mock_exec:
            mock_exec.return_value = {
                "success": False,
                "stdout": "",
                "stderr": "ResourceNotFound: Disk 'test-vm-home-westus2' not found",
                "returncode": 1,
            }

            disk_id = "/subscriptions/sub-id/resourceGroups/test-rg/providers/Microsoft.Compute/disks/test-vm-home-westus2"

            with pytest.raises(ProvisioningError) as exc_info:
                provisioner._attach_home_disk(
                    vm_name="test-vm", resource_group="test-rg", disk_id=disk_id
                )

            error_msg = str(exc_info.value)
            assert "not found" in error_msg.lower() or "ResourceNotFound" in error_msg
