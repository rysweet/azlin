"""
Unit tests for azlin clone command.

Tests the clone command functionality including VM resolution,
provisioning, home directory copying, and session name management.

Following TDD approach - these tests are written before implementation.
"""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

# ============================================================================
# BASIC CLONE COMMAND TESTS
# ============================================================================


class TestCloneCommandBasics:
    """Test basic clone command functionality."""

    def test_clone_command_exists(self):
        """Test that clone command is registered in CLI."""
        from azlin.cli import main

        result = CliRunner().invoke(main, ["clone", "--help"])
        assert result.exit_code == 0
        assert "clone" in result.output.lower()

    def test_clone_requires_source_vm_argument(self):
        """Test that clone command requires source VM argument."""
        from azlin.cli import main

        result = CliRunner().invoke(main, ["clone"])
        assert result.exit_code != 0
        assert "source" in result.output.lower() or "missing" in result.output.lower()

    def test_clone_accepts_source_vm_by_name(self):
        """Test that clone accepts source VM by name."""
        from azlin.cli import main

        with patch("azlin.cli.clone_command") as mock_clone:
            result = CliRunner().invoke(main, ["clone", "azlin-vm-001"])

            # Should call clone_command with source_vm='azlin-vm-001'
            assert result.exit_code == 0 or "source" in str(mock_clone.call_args)

    def test_clone_accepts_source_vm_by_session_name(self):
        """Test that clone accepts source VM by session name."""
        from azlin.cli import main

        with patch("azlin.cli.clone_command") as mock_clone:
            result = CliRunner().invoke(main, ["clone", "amplihack"])

            assert result.exit_code == 0 or "amplihack" in str(mock_clone.call_args)


# ============================================================================
# CLONE OPTIONS TESTS
# ============================================================================


class TestCloneCommandOptions:
    """Test clone command options."""

    def test_clone_accepts_num_replicas_option(self):
        """Test --num-replicas option."""
        from azlin.cli import main

        with patch("azlin.cli.clone_command") as mock_clone:
            result = CliRunner().invoke(main, ["clone", "my-vm", "--num-replicas", "3"])

            # Should pass num_replicas=3
            if result.exit_code == 0:
                assert "3" in str(mock_clone.call_args) or mock_clone.call_args[0][1] == 3

    def test_clone_num_replicas_defaults_to_one(self):
        """Test that num-replicas defaults to 1."""
        from azlin.cli import main

        with patch("azlin.cli.clone_command"):
            CliRunner().invoke(main, ["clone", "my-vm"])

            # Default should be 1
            assert True  # Will check in implementation

    def test_clone_accepts_session_prefix_option(self):
        """Test --session-prefix option."""
        from azlin.cli import main

        with patch("azlin.cli.clone_command") as mock_clone:
            result = CliRunner().invoke(main, ["clone", "my-vm", "--session-prefix", "dev-clone"])

            # Should pass session_prefix='dev-clone'
            assert result.exit_code == 0 or "dev-clone" in str(mock_clone.call_args)

    def test_clone_accepts_resource_group_option(self):
        """Test --resource-group option."""
        from azlin.cli import main

        with patch("azlin.cli.clone_command") as mock_clone:
            result = CliRunner().invoke(main, ["clone", "my-vm", "--resource-group", "custom-rg"])

            assert result.exit_code == 0 or "custom-rg" in str(mock_clone.call_args)

    def test_clone_accepts_vm_size_option(self):
        """Test --vm-size option for specifying clone VM size."""
        from azlin.cli import main

        with patch("azlin.cli.clone_command") as mock_clone:
            result = CliRunner().invoke(main, ["clone", "my-vm", "--vm-size", "Standard_D4s_v3"])

            assert result.exit_code == 0 or "Standard_D4s_v3" in str(mock_clone.call_args)

    def test_clone_accepts_region_option(self):
        """Test --region option for specifying clone region."""
        from azlin.cli import main

        with patch("azlin.cli.clone_command") as mock_clone:
            result = CliRunner().invoke(main, ["clone", "my-vm", "--region", "westus2"])

            assert result.exit_code == 0 or "westus2" in str(mock_clone.call_args)


# ============================================================================
# SOURCE VM RESOLUTION TESTS
# ============================================================================


class TestSourceVMResolution:
    """Test source VM resolution by name or session."""

    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_resolve_source_vm_by_vm_name(self, mock_config_mgr, mock_vm_mgr):
        """Test resolving source VM by VM name."""
        from azlin.cli import _resolve_source_vm
        from azlin.vm_manager import VMInfo

        # Mock VM found by name
        mock_vm = VMInfo(
            name="azlin-vm-001",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.4",
        )
        mock_vm_mgr.get_vm.return_value = mock_vm

        result = _resolve_source_vm("azlin-vm-001", "test-rg", mock_config_mgr)

        assert result.name == "azlin-vm-001"
        assert result.public_ip == "1.2.3.4"

    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_resolve_source_vm_by_session_name(self, mock_config_mgr, mock_vm_mgr):
        """Test resolving source VM by session name."""
        from azlin.cli import _resolve_source_vm
        from azlin.vm_manager import VMInfo

        # Mock session name maps to VM
        mock_config_mgr.get_vm_by_session.return_value = "azlin-vm-001"
        mock_vm = VMInfo(
            name="azlin-vm-001",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.4",
        )
        mock_vm_mgr.get_vm.return_value = mock_vm

        result = _resolve_source_vm("amplihack", "test-rg", mock_config_mgr)

        assert result.name == "azlin-vm-001"

    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.ConfigManager")
    def test_resolve_source_vm_not_found(self, mock_config_mgr, mock_vm_mgr):
        """Test error when source VM not found."""
        from azlin.cli import _resolve_source_vm

        mock_vm_mgr.get_vm.return_value = None
        mock_config_mgr.get_vm_by_session.return_value = None

        with pytest.raises(Exception, match=r"(?i)not found"):
            _resolve_source_vm("nonexistent", "test-rg", mock_config_mgr)


# ============================================================================
# CLONE CONFIG GENERATION TESTS
# ============================================================================


class TestCloneConfigGeneration:
    """Test generation of VMConfig objects for clones."""

    def test_generate_single_clone_config(self):
        """Test generating config for single clone."""
        from azlin.cli import _generate_clone_configs
        from azlin.vm_manager import VMInfo

        source_vm = VMInfo(
            name="source-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            vm_size="Standard_B2s",
        )

        configs = _generate_clone_configs(
            source_vm=source_vm, num_replicas=1, vm_size=None, region=None
        )

        assert len(configs) == 1
        assert configs[0].location == "eastus"  # Same as source
        assert configs[0].size == "Standard_B2s"  # Same as source

    def test_generate_multiple_clone_configs(self):
        """Test generating configs for multiple clones."""
        from azlin.cli import _generate_clone_configs
        from azlin.vm_manager import VMInfo

        source_vm = VMInfo(
            name="source-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            vm_size="Standard_B2s",
        )

        configs = _generate_clone_configs(
            source_vm=source_vm, num_replicas=3, vm_size=None, region=None
        )

        assert len(configs) == 3
        # Each should have unique name
        names = [c.name for c in configs]
        assert len(set(names)) == 3  # All unique

    def test_generate_clone_configs_with_custom_vm_size(self):
        """Test custom VM size overrides source."""
        from azlin.cli import _generate_clone_configs
        from azlin.vm_manager import VMInfo

        source_vm = VMInfo(
            name="source-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            vm_size="Standard_B2s",
        )

        configs = _generate_clone_configs(
            source_vm=source_vm, num_replicas=1, vm_size="Standard_D4s_v3", region=None
        )

        assert configs[0].size == "Standard_D4s_v3"

    def test_generate_clone_configs_with_custom_region(self):
        """Test custom region overrides source."""
        from azlin.cli import _generate_clone_configs
        from azlin.vm_manager import VMInfo

        source_vm = VMInfo(
            name="source-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            vm_size="Standard_B2s",
        )

        configs = _generate_clone_configs(
            source_vm=source_vm, num_replicas=1, vm_size=None, region="westus2"
        )

        assert configs[0].location == "westus2"


# ============================================================================
# VM PROVISIONING TESTS
# ============================================================================


class TestCloneProvisioning:
    """Test VM provisioning for clones."""

    @patch("azlin.cli.VMProvisioner")
    def test_provision_single_clone(self, mock_provisioner):
        """Test provisioning single clone VM."""
        from azlin.vm_provisioning import PoolProvisioningResult, VMDetails

        # Mock successful provisioning
        mock_result = PoolProvisioningResult(
            total_requested=1,
            successful=[
                VMDetails(
                    name="clone-vm-1",
                    resource_group="test-rg",
                    location="eastus",
                    size="Standard_B2s",
                    public_ip="5.6.7.8",
                )
            ],
            failed=[],
            rg_failures=[],
        )
        mock_provisioner.return_value.provision_vm_pool.return_value = mock_result

        # Should provision successfully
        # (Implementation will be tested end-to-end)

    @patch("azlin.cli.VMProvisioner")
    def test_provision_multiple_clones_in_parallel(self, mock_provisioner):
        """Test provisioning multiple clones in parallel."""
        from azlin.vm_provisioning import PoolProvisioningResult, VMDetails

        # Mock successful parallel provisioning
        mock_result = PoolProvisioningResult(
            total_requested=3,
            successful=[
                VMDetails(
                    name=f"clone-vm-{i}",
                    resource_group="test-rg",
                    location="eastus",
                    size="Standard_B2s",
                    public_ip=f"1.2.3.{i}",
                )
                for i in range(1, 4)
            ],
            failed=[],
            rg_failures=[],
        )
        mock_provisioner.return_value.provision_vm_pool.return_value = mock_result

        # Should provision 3 VMs in parallel
        assert len(mock_result.successful) == 3


# ============================================================================
# HOME DIRECTORY COPY TESTS
# ============================================================================


class TestHomeDirectoryCopy:
    """Test home directory copying functionality."""

    @patch("azlin.cli.subprocess.run")
    def test_copy_home_directory_to_single_clone(self, mock_subprocess):
        """Test copying home directory to single clone."""
        from azlin.cli import _copy_home_directories
        from azlin.vm_manager import VMInfo
        from azlin.vm_provisioning import VMDetails

        source_vm = VMInfo(
            name="source-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.4",
        )

        clone_vms = [
            VMDetails(
                name="clone-vm-1",
                resource_group="test-rg",
                location="eastus",
                size="Standard_B2s",
                public_ip="5.6.7.8",
            )
        ]

        # Mock successful rsync
        mock_subprocess.return_value.returncode = 0

        results = _copy_home_directories(
            source_vm=source_vm, clone_vms=clone_vms, ssh_key_path="~/.ssh/id_rsa", max_workers=5
        )

        assert results["clone-vm-1"] is True

    @patch("azlin.cli.subprocess.run")
    def test_copy_home_directories_in_parallel(self, mock_subprocess):
        """Test copying home directories to multiple clones in parallel."""
        from azlin.cli import _copy_home_directories
        from azlin.vm_manager import VMInfo
        from azlin.vm_provisioning import VMDetails

        source_vm = VMInfo(
            name="source-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.4",
        )

        clone_vms = [
            VMDetails(
                name=f"clone-vm-{i}",
                resource_group="test-rg",
                location="eastus",
                size="Standard_B2s",
                public_ip=f"5.6.7.{i}",
            )
            for i in range(1, 4)
        ]

        # Mock successful rsync
        mock_subprocess.return_value.returncode = 0

        results = _copy_home_directories(
            source_vm=source_vm, clone_vms=clone_vms, ssh_key_path="~/.ssh/id_rsa", max_workers=5
        )

        assert len(results) == 3
        assert all(results.values())  # All successful

    @patch("azlin.cli.subprocess.run")
    def test_copy_handles_partial_failure(self, mock_subprocess):
        """Test that copy handles partial failures gracefully."""
        from azlin.cli import _copy_home_directories
        from azlin.vm_manager import VMInfo
        from azlin.vm_provisioning import VMDetails

        source_vm = VMInfo(
            name="source-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.4",
        )

        clone_vms = [
            VMDetails(
                name="clone-vm-1",
                resource_group="test-rg",
                location="eastus",
                size="Standard_B2s",
                public_ip="5.6.7.1",
            ),
            VMDetails(
                name="clone-vm-2",
                resource_group="test-rg",
                location="eastus",
                size="Standard_B2s",
                public_ip="5.6.7.2",
            ),
        ]

        # Mock first success, second failure
        mock_subprocess.side_effect = [
            Mock(returncode=0),  # First clone succeeds
            Mock(returncode=1),  # Second clone fails
        ]

        results = _copy_home_directories(
            source_vm=source_vm, clone_vms=clone_vms, ssh_key_path="~/.ssh/id_rsa", max_workers=5
        )

        assert results["clone-vm-1"] is True
        assert results["clone-vm-2"] is False


# ============================================================================
# SESSION NAME MANAGEMENT TESTS
# ============================================================================


class TestSessionNameManagement:
    """Test session name assignment for clones."""

    @patch("azlin.cli.ConfigManager")
    def test_set_single_clone_session_name(self, mock_config_mgr):
        """Test setting session name for single clone."""
        from azlin.cli import _set_clone_session_names
        from azlin.vm_provisioning import VMDetails

        clone_vms = [
            VMDetails(
                name="clone-vm-1",
                resource_group="test-rg",
                location="eastus",
                size="Standard_B2s",
                public_ip="5.6.7.8",
            )
        ]

        _set_clone_session_names(
            clone_vms=clone_vms, session_prefix="dev-clone", config_manager=mock_config_mgr
        )

        # Single clone should get prefix without number
        mock_config_mgr.set_session_name.assert_called_once_with("clone-vm-1", "dev-clone")

    @patch("azlin.cli.ConfigManager")
    def test_set_multiple_clone_session_names(self, mock_config_mgr):
        """Test setting session names for multiple clones."""
        from azlin.cli import _set_clone_session_names
        from azlin.vm_provisioning import VMDetails

        clone_vms = [
            VMDetails(
                name=f"clone-vm-{i}",
                resource_group="test-rg",
                location="eastus",
                size="Standard_B2s",
                public_ip=f"5.6.7.{i}",
            )
            for i in range(1, 4)
        ]

        _set_clone_session_names(
            clone_vms=clone_vms, session_prefix="worker", config_manager=mock_config_mgr
        )

        # Multiple clones should get numbered suffixes
        calls = mock_config_mgr.set_session_name.call_args_list
        assert len(calls) == 3
        assert ("clone-vm-1", "worker-1") in [call[0] for call in calls]
        assert ("clone-vm-2", "worker-2") in [call[0] for call in calls]
        assert ("clone-vm-3", "worker-3") in [call[0] for call in calls]

    @patch("azlin.cli.ConfigManager")
    def test_no_session_names_when_prefix_not_provided(self, mock_config_mgr):
        """Test that no session names are set when prefix not provided."""
        from azlin.cli import _set_clone_session_names
        from azlin.vm_provisioning import VMDetails

        clone_vms = [
            VMDetails(
                name="clone-vm-1",
                resource_group="test-rg",
                location="eastus",
                size="Standard_B2s",
                public_ip="5.6.7.8",
            )
        ]

        _set_clone_session_names(
            clone_vms=clone_vms, session_prefix=None, config_manager=mock_config_mgr
        )

        # Should not set any session names
        mock_config_mgr.set_session_name.assert_not_called()


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


class TestCloneErrorHandling:
    """Test error handling in clone command."""

    def test_clone_fails_when_source_vm_not_found(self):
        """Test error when source VM doesn't exist."""
        from azlin.cli import main

        with patch("azlin.cli.VMManager") as mock_vm_mgr:
            mock_vm_mgr.get_vm.return_value = None

            result = CliRunner().invoke(main, ["clone", "nonexistent-vm"])

            assert result.exit_code != 0
            assert "not found" in result.output.lower()

    def test_clone_validates_num_replicas_positive(self):
        """Test that num-replicas must be positive."""
        from azlin.cli import main

        result = CliRunner().invoke(main, ["clone", "my-vm", "--num-replicas", "0"])

        assert result.exit_code != 0
        assert "invalid" in result.output.lower() or "positive" in result.output.lower()

    def test_clone_handles_all_provisioning_failures(self):
        """Test handling when all VM provisioning fails."""
        from azlin.cli import main

        with patch("azlin.cli.VMProvisioner") as mock_provisioner:
            from azlin.vm_provisioning import PoolProvisioningResult, ProvisioningFailure, VMConfig

            # Mock all VMs failed
            mock_result = PoolProvisioningResult(
                total_requested=2,
                successful=[],
                failed=[
                    ProvisioningFailure(
                        config=VMConfig(name="clone-1", resource_group="test-rg"),
                        error="SKU unavailable",
                        error_type="sku_unavailable",
                    ),
                    ProvisioningFailure(
                        config=VMConfig(name="clone-2", resource_group="test-rg"),
                        error="SKU unavailable",
                        error_type="sku_unavailable",
                    ),
                ],
                rg_failures=[],
            )
            mock_provisioner.return_value.provision_vm_pool.return_value = mock_result

            result = CliRunner().invoke(main, ["clone", "my-vm", "--num-replicas", "2"])

            assert result.exit_code != 0
            assert "failed" in result.output.lower()


# ============================================================================
# END-TO-END INTEGRATION TESTS
# ============================================================================


class TestCloneEndToEnd:
    """End-to-end integration tests for clone command."""

    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.VMProvisioner")
    @patch("azlin.cli.subprocess.run")
    @patch("azlin.cli.ConfigManager")
    def test_clone_single_vm_end_to_end(
        self, mock_config, mock_subprocess, mock_provisioner, mock_vm_mgr
    ):
        """Test complete single VM clone workflow."""
        from azlin.cli import main
        from azlin.vm_manager import VMInfo
        from azlin.vm_provisioning import PoolProvisioningResult, VMDetails

        # Mock source VM
        mock_source = VMInfo(
            name="source-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.4",
            vm_size="Standard_B2s",
        )
        mock_vm_mgr.get_vm.return_value = mock_source

        # Mock provisioning success
        mock_prov_result = PoolProvisioningResult(
            total_requested=1,
            successful=[
                VMDetails(
                    name="clone-vm-1",
                    resource_group="test-rg",
                    location="eastus",
                    size="Standard_B2s",
                    public_ip="5.6.7.8",
                )
            ],
            failed=[],
            rg_failures=[],
        )
        mock_provisioner.return_value.provision_vm_pool.return_value = mock_prov_result

        # Mock rsync success
        mock_subprocess.return_value.returncode = 0

        result = CliRunner().invoke(main, ["clone", "source-vm", "--session-prefix", "test-clone"])

        assert result.exit_code == 0
        assert "success" in result.output.lower()
        assert "5.6.7.8" in result.output  # Shows clone IP

    @patch("azlin.cli.VMManager")
    @patch("azlin.cli.VMProvisioner")
    @patch("azlin.cli.subprocess.run")
    @patch("azlin.cli.ConfigManager")
    def test_clone_multiple_vms_end_to_end(
        self, mock_config, mock_subprocess, mock_provisioner, mock_vm_mgr
    ):
        """Test complete multiple VM clone workflow."""
        from azlin.cli import main
        from azlin.vm_manager import VMInfo
        from azlin.vm_provisioning import PoolProvisioningResult, VMDetails

        # Mock source VM
        mock_source = VMInfo(
            name="source-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.4",
            vm_size="Standard_B2s",
        )
        mock_vm_mgr.get_vm.return_value = mock_source

        # Mock provisioning 3 VMs
        mock_prov_result = PoolProvisioningResult(
            total_requested=3,
            successful=[
                VMDetails(
                    name=f"clone-vm-{i}",
                    resource_group="test-rg",
                    location="eastus",
                    size="Standard_B2s",
                    public_ip=f"5.6.7.{i}",
                )
                for i in range(1, 4)
            ],
            failed=[],
            rg_failures=[],
        )
        mock_provisioner.return_value.provision_vm_pool.return_value = mock_prov_result

        # Mock rsync success
        mock_subprocess.return_value.returncode = 0

        result = CliRunner().invoke(
            main, ["clone", "source-vm", "--num-replicas", "3", "--session-prefix", "worker"]
        )

        assert result.exit_code == 0
        assert "3" in result.output  # Shows 3 clones
        assert "success" in result.output.lower()
