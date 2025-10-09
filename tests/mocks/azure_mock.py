"""
Mock Azure SDK clients for testing.

This module provides comprehensive mock implementations of Azure SDK clients
that simulate realistic Azure API behavior without making actual API calls.
"""

from typing import Optional, Dict, Any, List
from unittest.mock import Mock
from ..fixtures.azure_responses import (
    SAMPLE_VM_RESPONSE,
    SAMPLE_PUBLIC_IP,
    SAMPLE_NETWORK_INTERFACE,
    SAMPLE_RESOURCE_GROUP,
    QUOTA_EXCEEDED_ERROR,
    RESOURCE_NOT_FOUND_ERROR
)


class MockAzureCredential:
    """Mock Azure DefaultAzureCredential."""

    def __init__(self, token: str = 'fake-token-12345'):
        self.token = token

    def get_token(self, *scopes):
        """Return a fake token."""
        return Mock(
            token=self.token,
            expires_on=9999999999
        )


class MockVirtualMachine:
    """Mock Azure Virtual Machine resource."""

    def __init__(
        self,
        name: str,
        location: str,
        vm_size: str,
        state: str = 'Succeeded'
    ):
        self.name = name
        self.location = location
        self.vm_size = vm_size
        self.provisioning_state = state
        self.id = f'/subscriptions/sub-id/resourceGroups/azlin-rg/providers/Microsoft.Compute/virtualMachines/{name}'

    def as_dict(self) -> Dict[str, Any]:
        """Return VM as dictionary (Azure API format)."""
        response = SAMPLE_VM_RESPONSE.copy()
        response['name'] = self.name
        response['location'] = self.location
        response['properties']['hardwareProfile']['vmSize'] = self.vm_size
        response['properties']['provisioningState'] = self.provisioning_state
        return response


class MockPublicIPAddress:
    """Mock Azure Public IP Address resource."""

    def __init__(
        self,
        name: str,
        ip_address: str = '20.123.45.67',
        location: str = 'eastus'
    ):
        self.name = name
        self.ip_address = ip_address
        self.location = location
        self.id = f'/subscriptions/sub-id/resourceGroups/azlin-rg/providers/Microsoft.Network/publicIPAddresses/{name}'

    def as_dict(self) -> Dict[str, Any]:
        """Return public IP as dictionary (Azure API format)."""
        response = SAMPLE_PUBLIC_IP.copy()
        response['name'] = self.name
        response['location'] = self.location
        response['properties']['ipAddress'] = self.ip_address
        return response


class MockNetworkInterface:
    """Mock Azure Network Interface resource."""

    def __init__(
        self,
        name: str,
        public_ip_id: str,
        location: str = 'eastus'
    ):
        self.name = name
        self.public_ip_id = public_ip_id
        self.location = location
        self.id = f'/subscriptions/sub-id/resourceGroups/azlin-rg/providers/Microsoft.Network/networkInterfaces/{name}'

    def as_dict(self) -> Dict[str, Any]:
        """Return NIC as dictionary (Azure API format)."""
        response = SAMPLE_NETWORK_INTERFACE.copy()
        response['name'] = self.name
        response['location'] = self.location
        response['properties']['ipConfigurations'][0]['properties']['publicIPAddress']['id'] = self.public_ip_id
        return response


class MockResourceGroup:
    """Mock Azure Resource Group."""

    def __init__(self, name: str, location: str = 'eastus'):
        self.name = name
        self.location = location
        self.id = f'/subscriptions/sub-id/resourceGroups/{name}'

    def as_dict(self) -> Dict[str, Any]:
        """Return resource group as dictionary (Azure API format)."""
        response = SAMPLE_RESOURCE_GROUP.copy()
        response['name'] = self.name
        response['location'] = self.location
        return response


class MockPoller:
    """Mock Azure Poller for long-running operations."""

    def __init__(self, result_value: Any, delay: float = 0):
        self._result = result_value
        self._delay = delay
        self._done = False

    def result(self, timeout: Optional[float] = None):
        """Return the result of the operation."""
        self._done = True
        return self._result

    def done(self) -> bool:
        """Check if operation is done."""
        return self._done

    def wait(self, timeout: Optional[float] = None):
        """Wait for operation to complete."""
        self._done = True


class MockComputeManagementClient:
    """Mock Azure ComputeManagementClient."""

    def __init__(self, credential, subscription_id: str):
        self.credential = credential
        self.subscription_id = subscription_id
        self.virtual_machines = MockVirtualMachinesOperations()


class MockVirtualMachinesOperations:
    """Mock operations for virtual machines."""

    def __init__(self):
        self._vms: Dict[str, MockVirtualMachine] = {}
        self._should_fail = False
        self._fail_reason = None

    def begin_create_or_update(
        self,
        resource_group_name: str,
        vm_name: str,
        parameters: Dict[str, Any]
    ) -> MockPoller:
        """Mock VM creation.

        Args:
            resource_group_name: Resource group name
            vm_name: VM name
            parameters: VM parameters

        Returns:
            MockPoller that returns MockVirtualMachine
        """
        if self._should_fail:
            if self._fail_reason == 'quota':
                raise Exception(QUOTA_EXCEEDED_ERROR['error']['message'])
            else:
                raise Exception('VM creation failed')

        vm = MockVirtualMachine(
            name=vm_name,
            location=parameters.get('location', 'eastus'),
            vm_size=parameters.get('properties', {}).get('hardwareProfile', {}).get('vmSize', 'Standard_D2s_v3')
        )
        self._vms[vm_name] = vm
        return MockPoller(vm)

    def get(self, resource_group_name: str, vm_name: str) -> MockVirtualMachine:
        """Get VM by name.

        Args:
            resource_group_name: Resource group name
            vm_name: VM name

        Returns:
            MockVirtualMachine

        Raises:
            Exception: If VM not found
        """
        if vm_name not in self._vms:
            raise Exception(RESOURCE_NOT_FOUND_ERROR['error']['message'])
        return self._vms[vm_name]

    def begin_delete(self, resource_group_name: str, vm_name: str) -> MockPoller:
        """Delete VM.

        Args:
            resource_group_name: Resource group name
            vm_name: VM name

        Returns:
            MockPoller
        """
        if vm_name in self._vms:
            del self._vms[vm_name]
        return MockPoller(None)

    def list(self, resource_group_name: str) -> List[MockVirtualMachine]:
        """List all VMs in resource group."""
        return list(self._vms.values())

    def set_failure_mode(self, should_fail: bool, reason: Optional[str] = None):
        """Configure mock to simulate failures."""
        self._should_fail = should_fail
        self._fail_reason = reason


class MockNetworkManagementClient:
    """Mock Azure NetworkManagementClient."""

    def __init__(self, credential, subscription_id: str):
        self.credential = credential
        self.subscription_id = subscription_id
        self.public_ip_addresses = MockPublicIPAddressesOperations()
        self.network_interfaces = MockNetworkInterfacesOperations()
        self.virtual_networks = MockVirtualNetworksOperations()


class MockPublicIPAddressesOperations:
    """Mock operations for public IP addresses."""

    def __init__(self):
        self._ips: Dict[str, MockPublicIPAddress] = {}

    def begin_create_or_update(
        self,
        resource_group_name: str,
        public_ip_address_name: str,
        parameters: Dict[str, Any]
    ) -> MockPoller:
        """Mock public IP creation."""
        ip = MockPublicIPAddress(
            name=public_ip_address_name,
            ip_address=f'20.{len(self._ips)}.45.67',
            location=parameters.get('location', 'eastus')
        )
        self._ips[public_ip_address_name] = ip
        return MockPoller(ip)

    def get(self, resource_group_name: str, public_ip_address_name: str) -> MockPublicIPAddress:
        """Get public IP by name."""
        if public_ip_address_name not in self._ips:
            raise Exception(RESOURCE_NOT_FOUND_ERROR['error']['message'])
        return self._ips[public_ip_address_name]


class MockNetworkInterfacesOperations:
    """Mock operations for network interfaces."""

    def __init__(self):
        self._nics: Dict[str, MockNetworkInterface] = {}

    def begin_create_or_update(
        self,
        resource_group_name: str,
        network_interface_name: str,
        parameters: Dict[str, Any]
    ) -> MockPoller:
        """Mock NIC creation."""
        public_ip_id = parameters.get('properties', {}).get('ipConfigurations', [{}])[0].get('properties', {}).get('publicIPAddress', {}).get('id', '')
        nic = MockNetworkInterface(
            name=network_interface_name,
            public_ip_id=public_ip_id,
            location=parameters.get('location', 'eastus')
        )
        self._nics[network_interface_name] = nic
        return MockPoller(nic)


class MockVirtualNetworksOperations:
    """Mock operations for virtual networks."""

    def __init__(self):
        self._vnets: Dict[str, Mock] = {}

    def begin_create_or_update(
        self,
        resource_group_name: str,
        virtual_network_name: str,
        parameters: Dict[str, Any]
    ) -> MockPoller:
        """Mock VNet creation."""
        vnet = Mock(
            name=virtual_network_name,
            location=parameters.get('location', 'eastus')
        )
        self._vnets[virtual_network_name] = vnet
        return MockPoller(vnet)


class MockResourceManagementClient:
    """Mock Azure ResourceManagementClient."""

    def __init__(self, credential, subscription_id: str):
        self.credential = credential
        self.subscription_id = subscription_id
        self.resource_groups = MockResourceGroupsOperations()


class MockResourceGroupsOperations:
    """Mock operations for resource groups."""

    def __init__(self):
        self._groups: Dict[str, MockResourceGroup] = {}

    def create_or_update(
        self,
        resource_group_name: str,
        parameters: Dict[str, Any]
    ) -> MockResourceGroup:
        """Mock resource group creation."""
        rg = MockResourceGroup(
            name=resource_group_name,
            location=parameters.get('location', 'eastus')
        )
        self._groups[resource_group_name] = rg
        return rg

    def get(self, resource_group_name: str) -> MockResourceGroup:
        """Get resource group by name."""
        if resource_group_name not in self._groups:
            raise Exception(RESOURCE_NOT_FOUND_ERROR['error']['message'])
        return self._groups[resource_group_name]

    def check_existence(self, resource_group_name: str) -> bool:
        """Check if resource group exists."""
        return resource_group_name in self._groups


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_mock_azure_environment() -> Dict[str, Any]:
    """Create a complete mock Azure environment with all clients.

    Returns:
        Dictionary containing mocked credential and clients
    """
    credential = MockAzureCredential()

    return {
        'credential': credential,
        'compute_client': MockComputeManagementClient(credential, 'sub-id'),
        'network_client': MockNetworkManagementClient(credential, 'sub-id'),
        'resource_client': MockResourceManagementClient(credential, 'sub-id')
    }
