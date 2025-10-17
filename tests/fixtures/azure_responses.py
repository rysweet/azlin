"""
Sample Azure API responses for testing.

This module provides realistic Azure API response data
for mocking Azure SDK calls in tests.
"""

from typing import Any

# ============================================================================
# VIRTUAL MACHINE RESPONSES
# ============================================================================

SAMPLE_VM_RESPONSE: dict[str, Any] = {
    "id": "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/azlin-rg/providers/Microsoft.Compute/virtualMachines/dev-vm",
    "name": "dev-vm",
    "location": "eastus",
    "type": "Microsoft.Compute/virtualMachines",
    "properties": {
        "vmId": "abcd1234-5678-90ab-cdef-1234567890ab",
        "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
        "storageProfile": {
            "imageReference": {
                "publisher": "Canonical",
                "offer": "0001-com-ubuntu-server-jammy",
                "sku": "22_04-lts",
                "version": "latest",
            },
            "osDisk": {
                "osType": "Linux",
                "name": "dev-vm-osdisk",
                "createOption": "FromImage",
                "caching": "ReadWrite",
                "managedDisk": {"storageAccountType": "Premium_LRS"},
                "diskSizeGB": 30,
            },
        },
        "osProfile": {
            "computerName": "dev-vm",
            "adminUsername": "azureuser",
            "linuxConfiguration": {
                "disablePasswordAuthentication": True,
                "ssh": {
                    "publicKeys": [
                        {
                            "path": "/home/azureuser/.ssh/authorized_keys",
                            "keyData": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC...",
                        }
                    ]
                },
            },
        },
        "networkProfile": {
            "networkInterfaces": [
                {
                    "id": "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/azlin-rg/providers/Microsoft.Network/networkInterfaces/dev-vm-nic",
                    "properties": {"primary": True},
                }
            ]
        },
        "provisioningState": "Succeeded",
    },
    "tags": {"created-by": "azlin", "environment": "development"},
}


VM_CREATING_RESPONSE: dict[str, Any] = {
    **SAMPLE_VM_RESPONSE,
    "properties": {**SAMPLE_VM_RESPONSE["properties"], "provisioningState": "Creating"},
}


VM_FAILED_RESPONSE: dict[str, Any] = {
    **SAMPLE_VM_RESPONSE,
    "properties": {**SAMPLE_VM_RESPONSE["properties"], "provisioningState": "Failed"},
}


# ============================================================================
# NETWORK RESPONSES
# ============================================================================

SAMPLE_NETWORK_INTERFACE: dict[str, Any] = {
    "id": "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/azlin-rg/providers/Microsoft.Network/networkInterfaces/dev-vm-nic",
    "name": "dev-vm-nic",
    "location": "eastus",
    "properties": {
        "provisioningState": "Succeeded",
        "ipConfigurations": [
            {
                "name": "ipconfig1",
                "properties": {
                    "privateIPAddress": "10.0.0.4",
                    "privateIPAllocationMethod": "Dynamic",
                    "publicIPAddress": {
                        "id": "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/azlin-rg/providers/Microsoft.Network/publicIPAddresses/dev-vm-ip"
                    },
                    "subnet": {
                        "id": "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/azlin-rg/providers/Microsoft.Network/virtualNetworks/azlin-vnet/subnets/default"
                    },
                    "primary": True,
                },
            }
        ],
        "primary": True,
    },
}


SAMPLE_PUBLIC_IP: dict[str, Any] = {
    "id": "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/azlin-rg/providers/Microsoft.Network/publicIPAddresses/dev-vm-ip",
    "name": "dev-vm-ip",
    "location": "eastus",
    "properties": {
        "provisioningState": "Succeeded",
        "ipAddress": "20.123.45.67",
        "publicIPAllocationMethod": "Static",
        "publicIPAddressVersion": "IPv4",
        "idleTimeoutInMinutes": 4,
    },
}


SAMPLE_VIRTUAL_NETWORK: dict[str, Any] = {
    "id": "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/azlin-rg/providers/Microsoft.Network/virtualNetworks/azlin-vnet",
    "name": "azlin-vnet",
    "location": "eastus",
    "properties": {
        "provisioningState": "Succeeded",
        "addressSpace": {"addressPrefixes": ["10.0.0.0/16"]},
        "subnets": [
            {
                "name": "default",
                "properties": {"addressPrefix": "10.0.0.0/24", "provisioningState": "Succeeded"},
            }
        ],
    },
}


SAMPLE_SUBNET: dict[str, Any] = {
    "id": "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/azlin-rg/providers/Microsoft.Network/virtualNetworks/azlin-vnet/subnets/default",
    "name": "default",
    "properties": {"provisioningState": "Succeeded", "addressPrefix": "10.0.0.0/24"},
}


SAMPLE_NETWORK_SECURITY_GROUP: dict[str, Any] = {
    "id": "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/azlin-rg/providers/Microsoft.Network/networkSecurityGroups/azlin-nsg",
    "name": "azlin-nsg",
    "location": "eastus",
    "properties": {
        "provisioningState": "Succeeded",
        "securityRules": [
            {
                "name": "allow-ssh",
                "properties": {
                    "protocol": "Tcp",
                    "sourcePortRange": "*",
                    "destinationPortRange": "22",
                    "sourceAddressPrefix": "*",
                    "destinationAddressPrefix": "*",
                    "access": "Allow",
                    "priority": 1000,
                    "direction": "Inbound",
                },
            }
        ],
    },
}


# ============================================================================
# RESOURCE GROUP RESPONSES
# ============================================================================

SAMPLE_RESOURCE_GROUP: dict[str, Any] = {
    "id": "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/azlin-rg",
    "name": "azlin-rg",
    "location": "eastus",
    "properties": {"provisioningState": "Succeeded"},
    "tags": {"created-by": "azlin"},
}


# ============================================================================
# ERROR RESPONSES
# ============================================================================

QUOTA_EXCEEDED_ERROR = {
    "error": {
        "code": "QuotaExceeded",
        "message": "Operation could not be completed as it results in exceeding approved standardDSv3Family Cores quota.",
        "details": [
            {
                "code": "QuotaExceeded",
                "target": "standardDSv3Family",
                "message": "Current usage: 8, Limit: 10, Requested: 4",
            }
        ],
    }
}


RESOURCE_NOT_FOUND_ERROR = {
    "error": {
        "code": "ResourceNotFound",
        "message": "The Resource 'Microsoft.Compute/virtualMachines/non-existent-vm' under resource group 'azlin-rg' was not found.",
    }
}


INVALID_PARAMETER_ERROR = {
    "error": {
        "code": "InvalidParameter",
        "message": "The value 'InvalidSize' is not valid for parameter vmSize.",
        "details": [
            {
                "code": "InvalidParameter",
                "target": "vmSize",
                "message": "The provided VM size 'InvalidSize' is not available in location 'eastus'.",
            }
        ],
    }
}


AUTHENTICATION_FAILED_ERROR = {
    "error": {
        "code": "AuthenticationFailed",
        "message": "Authentication failed. The credentials provided are not valid.",
    }
}


SUBSCRIPTION_NOT_FOUND_ERROR = {
    "error": {
        "code": "SubscriptionNotFound",
        "message": "The subscription '12345678-1234-1234-1234-123456789012' could not be found.",
    }
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def create_vm_response(
    name: str = "test-vm",
    location: str = "eastus",
    vm_size: str = "Standard_D2s_v3",
    state: str = "Succeeded",
) -> dict[str, Any]:
    """Create a custom VM response with specified parameters.

    Args:
        name: VM name
        location: Azure region
        vm_size: VM size (SKU)
        state: Provisioning state

    Returns:
        Dict representing Azure VM API response
    """
    response = SAMPLE_VM_RESPONSE.copy()
    response["name"] = name
    response["location"] = location
    response["properties"]["hardwareProfile"]["vmSize"] = vm_size
    response["properties"]["provisioningState"] = state
    return response


def create_public_ip_response(
    name: str = "test-ip", ip_address: str = "20.123.45.67", location: str = "eastus"
) -> dict[str, Any]:
    """Create a custom public IP response with specified parameters.

    Args:
        name: Public IP resource name
        ip_address: IP address
        location: Azure region

    Returns:
        Dict representing Azure Public IP API response
    """
    response = SAMPLE_PUBLIC_IP.copy()
    response["name"] = name
    response["location"] = location
    response["properties"]["ipAddress"] = ip_address
    return response
