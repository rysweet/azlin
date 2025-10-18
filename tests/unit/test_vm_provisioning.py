"""
Unit tests for VM provisioning module.

Tests VM configuration, provisioning, and resource management (TDD - RED phase).

Test Coverage:
- VM configuration building
- Size validation
- Region validation
- Ubuntu image selection
- Network configuration
- Resource group creation
- Error handling for quota limits
- VM state management
"""

from unittest.mock import Mock, patch

import pytest

# ============================================================================
# VM CONFIGURATION TESTS
# ============================================================================


class TestVMConfiguration:
    """Test VM configuration building."""

    def test_creates_vm_config_with_required_parameters(self):
        """Test creating VM config with required parameters.

        RED PHASE: This test will fail - no implementation yet.
        """
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner(name="test-vm", size="Standard_D2s_v3", region="eastus")

        config = provisioner.build_vm_config()

        assert config.name == "test-vm"
        assert config.hardware_profile.vm_size == "Standard_D2s_v3"
        assert config.location == "eastus"

    def test_uses_ubuntu_2204_image_by_default(self):
        """Test that Ubuntu 22.04 LTS is used by default."""
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner(name="test-vm", size="Standard_D2s_v3", region="eastus")
        config = provisioner.build_vm_config()

        assert config.storage_profile.image_reference.publisher == "Canonical"
        assert "22_04" in config.storage_profile.image_reference.sku

    def test_configures_ssh_public_key_authentication(self):
        """Test that SSH public key authentication is configured."""
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner(
            name="test-vm",
            size="Standard_D2s_v3",
            region="eastus",
            ssh_public_key="ssh-rsa AAAAB...",
        )

        config = provisioner.build_vm_config()

        assert config.os_profile.linux_configuration.disable_password_authentication is True
        assert len(config.os_profile.linux_configuration.ssh.public_keys) > 0

    def test_disables_password_authentication(self):
        """Test that password authentication is disabled."""
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner(name="test-vm", size="Standard_D2s_v3", region="eastus")
        config = provisioner.build_vm_config()

        assert config.os_profile.linux_configuration.disable_password_authentication is True


# ============================================================================
# VM SIZE VALIDATION TESTS
# ============================================================================


class TestVMSizeValidation:
    """Test VM size validation."""

    def test_accepts_valid_vm_sizes(self):
        """Test that valid VM sizes are accepted."""
        from azlin.vm_provisioning import VMProvisioner

        valid_sizes = ["Standard_D2s_v3", "Standard_D4s_v3", "Standard_D8s_v3", "Standard_B2s"]

        for size in valid_sizes:
            provisioner = VMProvisioner(name="test-vm", size=size, region="eastus")
            assert provisioner.vm_size == size

    def test_rejects_invalid_vm_size(self):
        """Test that invalid VM sizes are rejected."""
        from azlin.vm_provisioning import InvalidVMSizeError, VMProvisioner

        with pytest.raises(InvalidVMSizeError):
            VMProvisioner(name="test-vm", size="InvalidSize", region="eastus")

    def test_lists_available_vm_sizes_for_region(self):
        """Test listing available VM sizes for a region."""
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner(name="test-vm", size="Standard_D2s_v3", region="eastus")
        sizes = provisioner.get_available_sizes()

        assert isinstance(sizes, list)
        assert len(sizes) > 0
        assert "Standard_D2s_v3" in sizes


# ============================================================================
# REGION VALIDATION TESTS
# ============================================================================


class TestRegionValidation:
    """Test Azure region validation."""

    def test_accepts_valid_regions(self):
        """Test that valid Azure regions are accepted."""
        from azlin.vm_provisioning import VMProvisioner

        valid_regions = ["eastus", "eastus2", "westus", "westus2", "centralus"]

        for region in valid_regions:
            provisioner = VMProvisioner(name="test-vm", size="Standard_D2s_v3", region=region)
            assert provisioner.region == region

    def test_rejects_invalid_region(self):
        """Test that invalid regions are rejected."""
        from azlin.vm_provisioning import InvalidRegionError, VMProvisioner

        with pytest.raises(InvalidRegionError):
            VMProvisioner(name="test-vm", size="Standard_D2s_v3", region="invalid-region")

    def test_lists_available_regions(self):
        """Test listing available Azure regions."""
        from azlin.vm_provisioning import VMProvisioner

        regions = VMProvisioner.get_available_regions()

        assert isinstance(regions, list)
        assert len(regions) > 0
        assert "eastus" in regions


# ============================================================================
# NETWORK CONFIGURATION TESTS
# ============================================================================


class TestNetworkConfiguration:
    """Test network configuration for VM."""

    def test_creates_public_ip_address(self):
        """Test that public IP address is created."""
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner(name="test-vm", size="Standard_D2s_v3", region="eastus")

        with patch("azure.mgmt.network.NetworkManagementClient") as mock_client:
            provisioner.create_network_resources()

            # Should create public IP
            mock_client.return_value.public_ip_addresses.begin_create_or_update.assert_called_once()

    def test_creates_network_interface(self):
        """Test that network interface is created."""
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner(name="test-vm", size="Standard_D2s_v3", region="eastus")

        with patch("azure.mgmt.network.NetworkManagementClient") as mock_client:
            provisioner.create_network_resources()

            # Should create NIC
            mock_client.return_value.network_interfaces.begin_create_or_update.assert_called_once()

    def test_creates_virtual_network_if_not_exists(self):
        """Test that virtual network is created if it doesn't exist."""
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner(name="test-vm", size="Standard_D2s_v3", region="eastus")

        with patch("azure.mgmt.network.NetworkManagementClient") as mock_client:
            # Simulate VNet doesn't exist
            mock_client.return_value.virtual_networks.get.side_effect = Exception("Not found")

            provisioner.create_network_resources()

            # Should create VNet
            mock_client.return_value.virtual_networks.begin_create_or_update.assert_called_once()


# ============================================================================
# RESOURCE GROUP TESTS
# ============================================================================


class TestResourceGroupManagement:
    """Test resource group creation and management."""

    def test_creates_resource_group_if_not_exists(self):
        """Test that resource group is created if it doesn't exist."""
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner(
            name="test-vm", size="Standard_D2s_v3", region="eastus", resource_group="azlin-rg"
        )

        with patch("azure.mgmt.resource.ResourceManagementClient") as mock_client:
            # Simulate RG doesn't exist
            mock_client.return_value.resource_groups.check_existence.return_value = False

            provisioner.ensure_resource_group()

            # Should create RG
            mock_client.return_value.resource_groups.create_or_update.assert_called_once()

    def test_uses_existing_resource_group(self):
        """Test that existing resource group is used."""
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner(
            name="test-vm", size="Standard_D2s_v3", region="eastus", resource_group="existing-rg"
        )

        with patch("azure.mgmt.resource.ResourceManagementClient") as mock_client:
            # Simulate RG exists
            mock_client.return_value.resource_groups.check_existence.return_value = True

            provisioner.ensure_resource_group()

            # Should NOT create RG
            mock_client.return_value.resource_groups.create_or_update.assert_not_called()


# ============================================================================
# VM PROVISIONING TESTS
# ============================================================================


class TestVMProvisioning:
    """Test actual VM provisioning."""

    @patch("azure.mgmt.compute.ComputeManagementClient")
    def test_provisions_vm_successfully(self, mock_compute_client):
        """Test successful VM provisioning."""
        from azlin.vm_provisioning import VMProvisioner

        # Mock VM creation
        mock_poller = Mock()
        mock_poller.result.return_value = Mock(name="test-vm", provisioning_state="Succeeded")
        mock_compute_client.return_value.virtual_machines.begin_create_or_update.return_value = (
            mock_poller
        )

        provisioner = VMProvisioner(name="test-vm", size="Standard_D2s_v3", region="eastus")
        vm = provisioner.provision()

        assert vm is not None
        assert vm.name == "test-vm"
        assert vm.provisioning_state == "Succeeded"

    @patch("azure.mgmt.compute.ComputeManagementClient")
    def test_waits_for_vm_to_be_ready(self, mock_compute_client):
        """Test that provisioner waits for VM to be ready."""
        from azlin.vm_provisioning import VMProvisioner

        mock_poller = Mock()
        # Simulate long-running operation
        mock_poller.done.side_effect = [False, False, True]
        mock_poller.result.return_value = Mock(name="test-vm", provisioning_state="Succeeded")

        mock_compute_client.return_value.virtual_machines.begin_create_or_update.return_value = (
            mock_poller
        )

        provisioner = VMProvisioner(name="test-vm", size="Standard_D2s_v3", region="eastus")
        provisioner.provision()

        # Should have called done() to check status
        assert mock_poller.done.call_count >= 1


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


class TestVMProvisioningErrors:
    """Test error handling in VM provisioning."""

    @patch("azure.mgmt.compute.ComputeManagementClient")
    def test_handles_quota_exceeded_error(self, mock_compute_client):
        """Test handling of quota exceeded error."""
        from azlin.vm_provisioning import QuotaExceededError, VMProvisioner

        mock_compute_client.return_value.virtual_machines.begin_create_or_update.side_effect = (
            Exception(
                "QuotaExceeded: Operation could not be completed as it results in exceeding quota"
            )
        )

        provisioner = VMProvisioner(name="test-vm", size="Standard_D2s_v3", region="eastus")

        with pytest.raises(QuotaExceededError):
            provisioner.provision()

    @patch("azure.mgmt.compute.ComputeManagementClient")
    def test_handles_vm_creation_failure(self, mock_compute_client):
        """Test handling of VM creation failure."""
        from azlin.vm_provisioning import ProvisioningError, VMProvisioner

        mock_poller = Mock()
        mock_poller.result.return_value = Mock(name="test-vm", provisioning_state="Failed")
        mock_compute_client.return_value.virtual_machines.begin_create_or_update.return_value = (
            mock_poller
        )

        provisioner = VMProvisioner(name="test-vm", size="Standard_D2s_v3", region="eastus")

        with pytest.raises(ProvisioningError):
            provisioner.provision()

    def test_handles_invalid_ssh_key(self):
        """Test handling of invalid SSH public key."""
        from azlin.vm_provisioning import InvalidSSHKeyError, VMProvisioner

        with pytest.raises(InvalidSSHKeyError):
            VMProvisioner(
                name="test-vm",
                size="Standard_D2s_v3",
                region="eastus",
                ssh_public_key="invalid-key-format",
            )


# ============================================================================
# VM STATE MANAGEMENT TESTS
# ============================================================================


class TestVMStateManagement:
    """Test VM state tracking and management."""

    def test_tracks_vm_provisioning_state(self):
        """Test tracking of VM provisioning state."""
        from azlin.vm_provisioning import VMProvisioner

        with patch("azure.mgmt.compute.ComputeManagementClient") as mock_client:
            provisioner = VMProvisioner(name="test-vm", size="Standard_D2s_v3", region="eastus")

            assert provisioner.state == "not_started"

            # Start provisioning
            mock_poller = Mock()
            mock_poller.result.return_value = Mock(name="test-vm", provisioning_state="Succeeded")
            mock_client.return_value.virtual_machines.begin_create_or_update.return_value = (
                mock_poller
            )

            provisioner.provision()

            assert provisioner.state == "succeeded"

    @patch("azure.mgmt.compute.ComputeManagementClient")
    def test_can_get_vm_ip_address_after_provisioning(self, mock_compute_client):
        """Test getting VM IP address after provisioning."""
        from azlin.vm_provisioning import VMProvisioner

        # Mock successful provisioning with IP
        mock_vm = Mock(name="test-vm", provisioning_state="Succeeded")
        mock_poller = Mock()
        mock_poller.result.return_value = mock_vm
        mock_compute_client.return_value.virtual_machines.begin_create_or_update.return_value = (
            mock_poller
        )

        with patch("azure.mgmt.network.NetworkManagementClient") as mock_network_client:
            mock_network_client.return_value.public_ip_addresses.get.return_value = Mock(
                ip_address="20.123.45.67"
            )

            provisioner = VMProvisioner(name="test-vm", size="Standard_D2s_v3", region="eastus")
            provisioner.provision()

            ip_address = provisioner.get_ip_address()
            assert ip_address == "20.123.45.67"


# ============================================================================
# AI CLI TOOLS INSTALLATION TESTS (TDD - RED PHASE)
# ============================================================================


class TestAICLIToolsInstallation:
    """Test AI CLI tools installation in cloud-init.

    Issue #9: Install AI CLI tools by default.
    These tests follow TDD principles - they will FAIL until implementation is complete.
    """

    def test_cloud_init_includes_github_copilot_cli(self):
        """Test that cloud-init includes GitHub Copilot CLI installation.

        RED PHASE: This test will fail - GitHub Copilot CLI not yet installed.
        """
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        # Should install GitHub Copilot CLI as azureuser
        assert "npm install -g @github/copilot" in cloud_init
        assert "su - azureuser" in cloud_init or "runuser -l azureuser" in cloud_init

    def test_cloud_init_includes_openai_codex_cli(self):
        """Test that cloud-init includes OpenAI Codex CLI installation.

        RED PHASE: This test will fail - OpenAI Codex CLI not yet installed.
        """
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        # Should install OpenAI Codex CLI as azureuser
        assert "npm install -g @openai/codex" in cloud_init

    def test_cloud_init_includes_claude_code_cli(self):
        """Test that cloud-init includes Claude Code CLI installation.

        RED PHASE: This test will fail - Claude Code CLI not yet installed.
        """
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        # Should install Claude Code CLI as azureuser
        assert "npm install -g @anthropic-ai/claude-code" in cloud_init

    def test_ai_cli_tools_installed_after_npm_configuration(self):
        """Test that AI CLI tools are installed after npm user-local config.

        RED PHASE: This test will fail - installation order not correct.
        """
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        # Find positions in cloud-init script
        npm_config_pos = cloud_init.find("NPM_PACKAGES=")
        github_copilot_pos = cloud_init.find("npm install -g @github/copilot")
        openai_codex_pos = cloud_init.find("npm install -g @openai/codex")
        claude_code_pos = cloud_init.find("npm install -g @anthropic-ai/claude-code")

        # AI CLI tools should be installed after npm configuration
        assert npm_config_pos != -1, "npm configuration not found"
        assert github_copilot_pos > npm_config_pos, (
            "GitHub Copilot should be installed after npm config"
        )
        assert openai_codex_pos > npm_config_pos, (
            "OpenAI Codex should be installed after npm config"
        )
        assert claude_code_pos > npm_config_pos, "Claude Code should be installed after npm config"

    def test_ai_cli_tools_installed_as_azureuser(self):
        """Test that AI CLI tools are installed as azureuser, not root.

        RED PHASE: This test will fail - tools not installed as azureuser.
        """
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        # Should run npm install as azureuser to use user-local npm config
        # Look for the AI CLI installation section
        lines = cloud_init.split("\n")

        found_ai_install_section = False
        for i, line in enumerate(lines):
            if "AI CLI tools" in line or "@github/copilot" in line:
                found_ai_install_section = True
                # Check that we're in a su/runuser context for azureuser
                # Look backwards to find the su command
                context = "\n".join(lines[max(0, i - 5) : i + 10])
                assert "su - azureuser" in context or "runuser -l azureuser" in context, (
                    f"AI CLI tools should be installed as azureuser, not root. Context:\n{context}"
                )
                break

        assert found_ai_install_section, "AI CLI tools installation section not found"

    def test_ai_cli_tools_use_user_local_npm(self):
        """Test that AI CLI tools use user-local npm configuration.

        RED PHASE: This test will fail - global install might use sudo or system npm.
        """
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        # Should NOT use sudo for npm install (user-local config handles this)
        assert "sudo npm install -g @github/copilot" not in cloud_init
        assert "sudo npm install -g @openai/codex" not in cloud_init
        assert "sudo npm install -g @anthropic-ai/claude-code" not in cloud_init


# ============================================================================
# PYTHON 3.12+ INSTALLATION TESTS (TDD - RED PHASE)
# ============================================================================


class TestPython312Installation:
    """Test Python 3.12+ installation in cloud-init.

    Issue #53: Update default Python version to 3.12+
    These tests follow TDD principles - they will FAIL until implementation is complete.
    """

    def test_cloud_init_installs_python_312_or_greater(self):
        """Test that cloud-init installs Python 3.12 or greater.

        RED PHASE: This test will fail - Python 3.12 not yet installed.
        """
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        # Should install Python 3.12 or 3.13
        assert "python3.12" in cloud_init or "python3.13" in cloud_init

    def test_cloud_init_uses_deadsnakes_ppa(self):
        """Test that cloud-init uses deadsnakes PPA for Python 3.12+.

        RED PHASE: This test will fail - deadsnakes PPA not configured.
        """
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        # Should add deadsnakes PPA
        assert "deadsnakes/ppa" in cloud_init
        assert "add-apt-repository" in cloud_init

    def test_cloud_init_installs_python312_venv_and_dev(self):
        """Test that cloud-init installs python3.12-venv and python3.12-dev.

        RED PHASE: This test will fail - venv and dev packages not installed.
        """
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        # Should install venv and dev packages
        assert "python3.12-venv" in cloud_init or "python3.13-venv" in cloud_init
        assert "python3.12-dev" in cloud_init or "python3.13-dev" in cloud_init

    def test_cloud_init_configures_python3_alternatives(self):
        """Test that cloud-init configures python3 to point to Python 3.12+.

        RED PHASE: This test will fail - alternatives not configured.
        """
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        # Should configure alternatives to make python3.12 the default
        assert "update-alternatives" in cloud_init
        assert "python3" in cloud_init

    def test_cloud_init_installs_pip_for_python312(self):
        """Test that cloud-init ensures pip works with Python 3.12+.

        RED PHASE: This test will fail - pip not configured for Python 3.12.
        """
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        # Should install pip for python3.12 or ensure ensurepip works
        # Either explicit python3.12-distutils or get-pip.py
        has_pip_setup = (
            "python3.12-distutils" in cloud_init
            or "python3.13-distutils" in cloud_init
            or "get-pip.py" in cloud_init
            or "ensurepip" in cloud_init
        )
        assert has_pip_setup, "pip must be configured for Python 3.12+"

    def test_python312_installed_before_other_python_tools(self):
        """Test that Python 3.12 is installed before tools that depend on it.

        RED PHASE: This test will fail - installation order not correct.
        """
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        # Find positions in cloud-init script
        python312_install_pos = cloud_init.find("python3.12")
        if python312_install_pos == -1:
            python312_install_pos = cloud_init.find("python3.13")

        astral_uv_pos = cloud_init.find("astral-uv")

        # Python 3.12 should be installed before astral-uv
        assert python312_install_pos != -1, "Python 3.12+ installation not found"
        assert astral_uv_pos != -1, "astral-uv installation not found"
        assert python312_install_pos < astral_uv_pos, (
            "Python 3.12+ should be installed before astral-uv"
        )
