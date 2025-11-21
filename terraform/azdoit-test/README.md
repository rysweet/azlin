# Azlin Test Infrastructure (azdoit-test)

## Overview

Terraform configuration for creating test VMs to validate azlin functionality.

## Prerequisites

1. **Terraform**: >= 1.0
2. **Azure CLI**: Authenticated (`az login`)
3. **SSH Key**: Public key for VM access

## Quick Start

```bash
# Initialize Terraform
terraform init

# Create test VM
terraform apply

# SSH into VM
ssh azureuser@<public_ip>

# Destroy when done
terraform destroy
```

## Regeneration

To recreate this infrastructure from scratch:

### Required Variables
- `admin_username`: VM admin user (default: "azureuser")
- `ssh_public_key`: Your SSH public key for authentication
- `vm_size`: Azure VM size (default: "Standard_B2s")
- `resource_group_name`: Azure resource group name
- `location`: Azure region

### Variable Sources
1. **Default values**: See `variables.tf`
2. **Override with**: `terraform.tfvars` or `-var` flags
3. **Example**:
   ```bash
   terraform apply \
     -var="ssh_public_key=$(cat ~/.ssh/id_rsa.pub)" \
     -var="location=eastus"
   ```

## Features

### Cloud-init Initialization
VMs are provisioned with automatic package installation via cloud-init:
- **Ripgrep**: Fast code search tool (`rg` command)
- Installation happens during first boot
- Logs: `/var/log/cloud-init-output.log`

### Verification
```bash
ssh azureuser@<vm-ip>
rg --version         # Verify ripgrep installed
cloud-init status    # Check initialization status
```

## Files

- `main.tf`: Infrastructure definitions
- `variables.tf`: Input variable schemas
- `outputs.tf`: Output values (IP addresses, etc.)
- `cloud-init.yml`: VM initialization script

## Testing

See `RIPGREP_TEST_PLAN.md` for comprehensive testing scenarios.
