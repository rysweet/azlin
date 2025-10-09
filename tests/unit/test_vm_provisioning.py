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

import pytest
from unittest.mock import Mock, patch, MagicMock


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

        provisioner = VMProvisioner(
            name='test-vm',
            size='Standard_D2s_v3',
            region='eastus'
        )

        config = provisioner.build_vm_config()

        assert config.name == 'test-vm'
        assert config.hardware_profile.vm_size == 'Standard_D2s_v3'
        assert config.location == 'eastus'

    def test_uses_ubuntu_2204_image_by_default(self):
        """Test that Ubuntu 22.04 LTS is used by default."""
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner(name='test-vm', size='Standard_D2s_v3', region='eastus')
        config = provisioner.build_vm_config()

        assert config.storage_profile.image_reference.publisher == 'Canonical'
        assert '22_04' in config.storage_profile.image_reference.sku

    def test_configures_ssh_public_key_authentication(self):
        """Test that SSH public key authentication is configured."""
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner(
            name='test-vm',
            size='Standard_D2s_v3',
            region='eastus',
            ssh_public_key='ssh-rsa AAAAB...'
        )

        config = provisioner.build_vm_config()

        assert config.os_profile.linux_configuration.disable_password_authentication is True
        assert len(config.os_profile.linux_configuration.ssh.public_keys) > 0

    def test_disables_password_authentication(self):
        """Test that password authentication is disabled."""
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner(name='test-vm', size='Standard_D2s_v3', region='eastus')
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

        valid_sizes = [
            'Standard_D2s_v3',
            'Standard_D4s_v3',
            'Standard_D8s_v3',
            'Standard_B2s'
        ]

        for size in valid_sizes:
            provisioner = VMProvisioner(name='test-vm', size=size, region='eastus')
            assert provisioner.vm_size == size

    def test_rejects_invalid_vm_size(self):
        """Test that invalid VM sizes are rejected."""
        from azlin.vm_provisioning import VMProvisioner, InvalidVMSizeError

        with pytest.raises(InvalidVMSizeError):
            VMProvisioner(name='test-vm', size='InvalidSize', region='eastus')

    def test_lists_available_vm_sizes_for_region(self):
        """Test listing available VM sizes for a region."""
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner(name='test-vm', size='Standard_D2s_v3', region='eastus')
        sizes = provisioner.get_available_sizes()

        assert isinstance(sizes, list)
        assert len(sizes) > 0
        assert 'Standard_D2s_v3' in sizes


# ============================================================================
# REGION VALIDATION TESTS
# ============================================================================

class TestRegionValidation:
    """Test Azure region validation."""

    def test_accepts_valid_regions(self):
        """Test that valid Azure regions are accepted."""
        from azlin.vm_provisioning import VMProvisioner

        valid_regions = ['eastus', 'eastus2', 'westus', 'westus2', 'centralus']

        for region in valid_regions:
            provisioner = VMProvisioner(name='test-vm', size='Standard_D2s_v3', region=region)
            assert provisioner.region == region

    def test_rejects_invalid_region(self):
        """Test that invalid regions are rejected."""
        from azlin.vm_provisioning import VMProvisioner, InvalidRegionError

        with pytest.raises(InvalidRegionError):
            VMProvisioner(name='test-vm', size='Standard_D2s_v3', region='invalid-region')

    def test_lists_available_regions(self):
        """Test listing available Azure regions."""
        from azlin.vm_provisioning import VMProvisioner

        regions = VMProvisioner.get_available_regions()

        assert isinstance(regions, list)
        assert len(regions) > 0
        assert 'eastus' in regions


# ============================================================================
# NETWORK CONFIGURATION TESTS
# ============================================================================

class TestNetworkConfiguration:
    """Test network configuration for VM."""

    def test_creates_public_ip_address(self):
        """Test that public IP address is created."""
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner(name='test-vm', size='Standard_D2s_v3', region='eastus')

        with patch('azure.mgmt.network.NetworkManagementClient') as mock_client:
            provisioner.create_network_resources()

            # Should create public IP
            mock_client.return_value.public_ip_addresses.begin_create_or_update.assert_called_once()

    def test_creates_network_interface(self):
        """Test that network interface is created."""
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner(name='test-vm', size='Standard_D2s_v3', region='eastus')

        with patch('azure.mgmt.network.NetworkManagementClient') as mock_client:
            provisioner.create_network_resources()

            # Should create NIC
            mock_client.return_value.network_interfaces.begin_create_or_update.assert_called_once()

    def test_creates_virtual_network_if_not_exists(self):
        """Test that virtual network is created if it doesn't exist."""
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner(name='test-vm', size='Standard_D2s_v3', region='eastus')

        with patch('azure.mgmt.network.NetworkManagementClient') as mock_client:
            # Simulate VNet doesn't exist
            mock_client.return_value.virtual_networks.get.side_effect = Exception('Not found')

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
            name='test-vm',
            size='Standard_D2s_v3',
            region='eastus',
            resource_group='azlin-rg'
        )

        with patch('azure.mgmt.resource.ResourceManagementClient') as mock_client:
            # Simulate RG doesn't exist
            mock_client.return_value.resource_groups.check_existence.return_value = False

            provisioner.ensure_resource_group()

            # Should create RG
            mock_client.return_value.resource_groups.create_or_update.assert_called_once()

    def test_uses_existing_resource_group(self):
        """Test that existing resource group is used."""
        from azlin.vm_provisioning import VMProvisioner

        provisioner = VMProvisioner(
            name='test-vm',
            size='Standard_D2s_v3',
            region='eastus',
            resource_group='existing-rg'
        )

        with patch('azure.mgmt.resource.ResourceManagementClient') as mock_client:
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

    @patch('azure.mgmt.compute.ComputeManagementClient')
    def test_provisions_vm_successfully(self, mock_compute_client):
        """Test successful VM provisioning."""
        from azlin.vm_provisioning import VMProvisioner

        # Mock VM creation
        mock_poller = Mock()
        mock_poller.result.return_value = Mock(
            name='test-vm',
            provisioning_state='Succeeded'
        )
        mock_compute_client.return_value.virtual_machines.begin_create_or_update.return_value = mock_poller

        provisioner = VMProvisioner(name='test-vm', size='Standard_D2s_v3', region='eastus')
        vm = provisioner.provision()

        assert vm is not None
        assert vm.name == 'test-vm'
        assert vm.provisioning_state == 'Succeeded'

    @patch('azure.mgmt.compute.ComputeManagementClient')
    def test_waits_for_vm_to_be_ready(self, mock_compute_client):
        """Test that provisioner waits for VM to be ready."""
        from azlin.vm_provisioning import VMProvisioner

        mock_poller = Mock()
        # Simulate long-running operation
        mock_poller.done.side_effect = [False, False, True]
        mock_poller.result.return_value = Mock(name='test-vm', provisioning_state='Succeeded')

        mock_compute_client.return_value.virtual_machines.begin_create_or_update.return_value = mock_poller

        provisioner = VMProvisioner(name='test-vm', size='Standard_D2s_v3', region='eastus')
        vm = provisioner.provision()

        # Should have called done() to check status
        assert mock_poller.done.call_count >= 1


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestVMProvisioningErrors:
    """Test error handling in VM provisioning."""

    @patch('azure.mgmt.compute.ComputeManagementClient')
    def test_handles_quota_exceeded_error(self, mock_compute_client):
        """Test handling of quota exceeded error."""
        from azlin.vm_provisioning import VMProvisioner, QuotaExceededError

        mock_compute_client.return_value.virtual_machines.begin_create_or_update.side_effect = Exception(
            'QuotaExceeded: Operation could not be completed as it results in exceeding quota'
        )

        provisioner = VMProvisioner(name='test-vm', size='Standard_D2s_v3', region='eastus')

        with pytest.raises(QuotaExceededError):
            provisioner.provision()

    @patch('azure.mgmt.compute.ComputeManagementClient')
    def test_handles_vm_creation_failure(self, mock_compute_client):
        """Test handling of VM creation failure."""
        from azlin.vm_provisioning import VMProvisioner, ProvisioningError

        mock_poller = Mock()
        mock_poller.result.return_value = Mock(
            name='test-vm',
            provisioning_state='Failed'
        )
        mock_compute_client.return_value.virtual_machines.begin_create_or_update.return_value = mock_poller

        provisioner = VMProvisioner(name='test-vm', size='Standard_D2s_v3', region='eastus')

        with pytest.raises(ProvisioningError):
            provisioner.provision()

    def test_handles_invalid_ssh_key(self):
        """Test handling of invalid SSH public key."""
        from azlin.vm_provisioning import VMProvisioner, InvalidSSHKeyError

        with pytest.raises(InvalidSSHKeyError):
            VMProvisioner(
                name='test-vm',
                size='Standard_D2s_v3',
                region='eastus',
                ssh_public_key='invalid-key-format'
            )


# ============================================================================
# VM STATE MANAGEMENT TESTS
# ============================================================================

class TestVMStateManagement:
    """Test VM state tracking and management."""

    def test_tracks_vm_provisioning_state(self):
        """Test tracking of VM provisioning state."""
        from azlin.vm_provisioning import VMProvisioner

        with patch('azure.mgmt.compute.ComputeManagementClient') as mock_client:
            provisioner = VMProvisioner(name='test-vm', size='Standard_D2s_v3', region='eastus')

            assert provisioner.state == 'not_started'

            # Start provisioning
            mock_poller = Mock()
            mock_poller.result.return_value = Mock(name='test-vm', provisioning_state='Succeeded')
            mock_client.return_value.virtual_machines.begin_create_or_update.return_value = mock_poller

            provisioner.provision()

            assert provisioner.state == 'succeeded'

    @patch('azure.mgmt.compute.ComputeManagementClient')
    def test_can_get_vm_ip_address_after_provisioning(self, mock_compute_client):
        """Test getting VM IP address after provisioning."""
        from azlin.vm_provisioning import VMProvisioner

        # Mock successful provisioning with IP
        mock_vm = Mock(name='test-vm', provisioning_state='Succeeded')
        mock_poller = Mock()
        mock_poller.result.return_value = mock_vm
        mock_compute_client.return_value.virtual_machines.begin_create_or_update.return_value = mock_poller

        with patch('azure.mgmt.network.NetworkManagementClient') as mock_network_client:
            mock_network_client.return_value.public_ip_addresses.get.return_value = Mock(
                ip_address='20.123.45.67'
            )

            provisioner = VMProvisioner(name='test-vm', size='Standard_D2s_v3', region='eastus')
            provisioner.provision()

            ip_address = provisioner.get_ip_address()
            assert ip_address == '20.123.45.67'
