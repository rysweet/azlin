# AZDOIT Test Infrastructure Architecture

## Overview

This Terraform module provisions minimal Azure infrastructure specifically designed to test the `azdoit` CLI tool's ability to manage Azure resources through natural language commands.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ Azure Subscription                                           │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Resource Group: test-azdoit-rg                     │    │
│  │                                                     │    │
│  │  ┌──────────────────────────────────────────────┐ │    │
│  │  │ Virtual Network: test-azdoit-vnet            │ │    │
│  │  │ Address Space: 10.0.0.0/16                   │ │    │
│  │  │                                               │ │    │
│  │  │  ┌─────────────────────────────────────────┐ │ │    │
│  │  │  │ Subnet: test-azdoit-subnet              │ │ │    │
│  │  │  │ Address: 10.0.1.0/24                    │ │ │    │
│  │  │  │                                          │ │ │    │
│  │  │  │  ┌────────────────────────────────────┐ │ │ │    │
│  │  │  │  │ Network Interface                  │ │ │ │    │
│  │  │  │  │ Private IP: 10.0.1.4 (dynamic)    │ │ │ │    │
│  │  │  │  └────────────┬───────────────────────┘ │ │ │    │
│  │  │  │               │                          │ │ │    │
│  │  │  │  ┌────────────▼───────────────────────┐ │ │ │    │
│  │  │  │  │ Virtual Machine                    │ │ │ │    │
│  │  │  │  │ Name: test-azdoit-vm-1             │ │ │ │    │
│  │  │  │  │ OS: Ubuntu 22.04 LTS               │ │ │ │    │
│  │  │  │  │ Size: Standard_B2s                 │ │ │ │    │
│  │  │  │  │ - 2 vCPUs                          │ │ │ │    │
│  │  │  │  │ - 4 GB RAM                         │ │ │ │    │
│  │  │  │  │ - 30 GB Disk (Standard LRS)        │ │ │ │    │
│  │  │  │  └────────────────────────────────────┘ │ │ │    │
│  │  │  └─────────────────────────────────────────┘ │ │    │
│  │  └──────────────────────────────────────────────┘ │    │
│  │                                                     │    │
│  │  ┌──────────────────────────────────────────────┐ │    │
│  │  │ Network Security Group: test-azdoit-nsg      │ │    │
│  │  │                                               │ │    │
│  │  │ Inbound Rules:                                │ │    │
│  │  │  - SSH (Port 22) from Any                    │ │    │
│  │  │    Priority: 1001                             │ │    │
│  │  │                                               │ │    │
│  │  └──────────────────────────────────────────────┘ │    │
│  │                                                     │    │
│  │  ┌──────────────────────────────────────────────┐ │    │
│  │  │ Public IP: test-azdoit-vm-1PublicIP          │ │    │
│  │  │ Type: Static                                  │ │    │
│  │  │ SKU: Standard                                 │ │    │
│  │  │ IP: 20.X.X.X (assigned by Azure)             │ │    │
│  │  └──────────────────────────────────────────────┘ │    │
│  │                                                     │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘

External Access:
    Internet
        │
        │ SSH (Port 22)
        ▼
    Public IP (20.X.X.X)
        │
        ▼
    Network Interface (10.0.1.4)
        │
        ▼
    Virtual Machine
```

## Resource Dependencies

```
azurerm_resource_group (test-azdoit-rg)
    │
    ├── azurerm_virtual_network (test-azdoit-vnet)
    │       │
    │       └── azurerm_subnet (test-azdoit-subnet)
    │               │
    │               └── azurerm_network_interface (test-azdoit-vm-1-nic)
    │                       │
    │                       └── azurerm_linux_virtual_machine (test-azdoit-vm-1)
    │
    ├── azurerm_public_ip (test-azdoit-vm-1PublicIP)
    │       │
    │       └── azurerm_network_interface (test-azdoit-vm-1-nic)
    │
    └── azurerm_network_security_group (test-azdoit-nsg)
            │
            └── azurerm_network_interface_security_group_association
```

## Component Details

### Resource Group
- **Name**: test-azdoit-rg
- **Location**: eastus (configurable)
- **Purpose**: Container for all test resources
- **Tags**:
  - purpose: azdoit-testing
  - managed_by: terraform
  - environment: test

### Virtual Network
- **Name**: test-azdoit-vnet
- **Address Space**: 10.0.0.0/16
- **Purpose**: Network isolation for test VM

### Subnet
- **Name**: test-azdoit-subnet
- **Address Prefix**: 10.0.1.0/24
- **Capacity**: 251 usable IPs

### Public IP
- **Name**: test-azdoit-vm-1PublicIP
- **Allocation**: Static
- **SKU**: Standard
- **Purpose**: External SSH access to VM

### Network Security Group
- **Name**: test-azdoit-nsg
- **Rules**:
  - SSH: Allow TCP 22 from Any
- **Purpose**: Control inbound traffic to VM

### Network Interface
- **Name**: test-azdoit-vm-1-nic
- **Private IP**: 10.0.1.4 (dynamic)
- **Public IP**: Associated
- **NSG**: Associated

### Virtual Machine
- **Name**: test-azdoit-vm-1
- **Size**: Standard_B2s
  - vCPUs: 2
  - RAM: 4 GB
  - Cost: ~$0.166/day
- **OS**: Ubuntu 22.04 LTS (Jammy Jellyfish)
- **Disk**: 30 GB Standard LRS
- **Authentication**: SSH key only
- **Admin User**: azureuser

## Cost Breakdown

| Resource | Type | Daily Cost | Monthly Cost |
|----------|------|------------|--------------|
| VM (Standard_B2s) | Compute | $0.166 | $5.04 |
| Public IP (Standard) | Networking | $0.012 | $0.36 |
| Disk (30GB LRS) | Storage | $0.005 | $0.15 |
| Network (VNet/NSG) | Networking | $0.000 | $0.00 |
| **Total (Running)** | | **$0.183** | **$5.55** |
| **Total (Stopped)** | | **$0.017** | **$0.51** |

Notes:
- Prices based on East US region
- Stopped VMs still incur storage and public IP costs
- Actual costs may vary by region and Azure pricing changes

## AZDOIT Test Coverage

This infrastructure enables testing of:

### 1. Resource Listing
- List VMs in resource group
- List all resources in resource group
- List network interfaces
- List public IPs

### 2. Resource Details
- Get VM details (name, size, status, IPs)
- Get resource group details
- Get network configuration

### 3. VM Power Management
- Stop VM (deallocate)
- Start VM (allocate and start)
- Get VM power state
- Restart VM

### 4. Cost Analysis
- Get resource group cost estimate
- Show cost breakdown by resource type
- Estimate monthly costs

### 5. Error Handling
- Query non-existent resources
- Handle authentication errors
- Graceful failure messages

## Security Considerations

### Authentication
- SSH key-based authentication only (no passwords)
- Public key stored in Terraform state
- Private key stays on user's machine

### Network Security
- NSG limits access to SSH only (port 22)
- No other inbound ports open
- Can restrict source IP if needed

### Resource Isolation
- Dedicated resource group for testing
- Isolated virtual network
- No production resource access

### Best Practices
- Destroy infrastructure when not in use
- Stop VM when not actively testing
- Rotate SSH keys regularly
- Monitor Azure costs

## Extensibility

### Adding More VMs
```hcl
# Copy and modify the VM resource block
resource "azurerm_linux_virtual_machine" "test2" {
  name = "test-azdoit-vm-2"
  # ... same configuration
}
```

### Adding Windows VM
```hcl
resource "azurerm_windows_virtual_machine" "windows_test" {
  name = "test-azdoit-win-vm-1"
  # ... Windows-specific configuration
}
```

### Adding Storage Account
```hcl
resource "azurerm_storage_account" "test" {
  name                = "testazdoitstorage"
  resource_group_name = azurerm_resource_group.test.name
  location            = azurerm_resource_group.test.location
  # ...
}
```

### Adding Database
```hcl
resource "azurerm_mssql_server" "test" {
  name                = "test-azdoit-sqlserver"
  resource_group_name = azurerm_resource_group.test.name
  location            = azurerm_resource_group.test.location
  # ...
}
```

## Terraform State

### Local State
By default, Terraform stores state locally in `terraform.tfstate`.

**Pros**:
- Simple setup
- No additional configuration

**Cons**:
- Not suitable for team collaboration
- No state locking
- Risk of state file loss

### Remote State (Optional)
For production use, consider Azure Blob Storage backend:

```hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "terraform-state-rg"
    storage_account_name = "tfstatestorage"
    container_name       = "tfstate"
    key                  = "azdoit-test.tfstate"
  }
}
```

## Troubleshooting Guide

### Common Issues

**Issue**: "QuotaExceeded" error during apply
- **Solution**: Try different region or smaller VM size

**Issue**: Cannot SSH to VM
- **Solution**: Check NSG rules, verify VM is running, check public IP

**Issue**: VM creation timeout
- **Solution**: Azure may be experiencing delays, wait and retry

**Issue**: SSH key validation fails
- **Solution**: Ensure key starts with "ssh-rsa", "ssh-ed25519", or "ssh-ecdsa"

## References

- [Azure Virtual Machines Documentation](https://docs.microsoft.com/azure/virtual-machines/)
- [Terraform Azure Provider](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs)
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/)
- [Ubuntu 22.04 LTS](https://ubuntu.com/server)
