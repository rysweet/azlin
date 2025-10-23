# AZDOIT Test Infrastructure

Terraform configuration to provision minimal Azure infrastructure for testing `azdoit` CLI functionality.

## Overview

This module creates a simple test environment with:
- 1 Resource Group
- 1 Virtual Network with subnet
- 1 Linux VM (Ubuntu 22.04)
- 1 Public IP
- 1 Network Security Group (SSH access)

**Purpose**: Validate that `azdoit` can manage real Azure resources through end-to-end testing.

## Prerequisites

### Required Tools

1. **Azure CLI** - Authenticated to your Azure subscription
   ```bash
   az login
   az account show
   ```

2. **Terraform** - Version 1.0 or higher
   ```bash
   terraform version
   ```

3. **azdoit CLI** - Installed and configured
   ```bash
   azdoit --version
   ```

4. **SSH Key Pair** - For VM access
   ```bash
   # Check if you have one
   ls -la ~/.ssh/id_*.pub

   # Or generate a new one
   ssh-keygen -t rsa -b 4096 -f ~/.ssh/azdoit_test
   ```

### Azure Subscription

- Active Azure subscription
- Contributor role or higher
- Sufficient quota for Standard_B2s VM

## Setup Instructions

### 1. Configure Variables

Copy the example variables file and configure it:

```bash
cd terraform/azdoit-test
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and set your SSH public key:

```hcl
ssh_public_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAB..."
```

To get your public key:
```bash
cat ~/.ssh/id_rsa.pub
```

### 2. Initialize Terraform

```bash
terraform init
```

This downloads the Azure provider and sets up the backend.

### 3. Review the Plan

```bash
terraform plan
```

Review the resources that will be created:
- 1 resource group
- 1 virtual network
- 1 subnet
- 1 public IP
- 1 network security group
- 1 network interface
- 1 Linux VM

### 4. Apply Configuration

```bash
terraform apply
```

Type `yes` when prompted. Deployment takes ~5-10 minutes.

### 5. Capture Outputs

After successful deployment, note the outputs:

```bash
terraform output
```

Example output:
```
resource_group_name = "test-azdoit-rg"
vm_name = "test-azdoit-vm-1"
vm_public_ip = "20.X.X.X"
vm_private_ip = "10.0.1.4"
ssh_connection_command = "ssh azureuser@20.X.X.X"
```

## Testing AZDOIT

Once infrastructure is provisioned, test `azdoit` functionality:

### Basic Tests

```bash
# List all VMs in the resource group
azdoit "list VMs in test-azdoit-rg"

# Get VM details
azdoit "get VM test-azdoit-vm-1 details"
azdoit "show details of test-azdoit-vm-1"

# Check VM status
azdoit "get status of test-azdoit-vm-1"
azdoit "is test-azdoit-vm-1 running?"
```

### VM Power Management Tests

```bash
# Stop the VM
azdoit "stop VM test-azdoit-vm-1"

# Verify it's stopped
azdoit "get status of test-azdoit-vm-1"

# Start the VM
azdoit "start VM test-azdoit-vm-1"

# Verify it's running
azdoit "get status of test-azdoit-vm-1"
```

### Resource Information Tests

```bash
# List resources in resource group
azdoit "list all resources in test-azdoit-rg"

# Get resource group details
azdoit "show details of test-azdoit-rg"

# Show network information
azdoit "list network interfaces in test-azdoit-rg"
```

### Cost Analysis Tests

```bash
# Show cost estimate for resource group
azdoit "show cost estimate for test-azdoit-rg"

# Get cost breakdown
azdoit "what is the cost of test-azdoit-rg?"
```

### Testing Checklist

After `terraform apply`, verify these operations work:

- [ ] List VMs in test-azdoit-rg
- [ ] Get VM test-azdoit-vm-1 details
- [ ] Check VM power state
- [ ] Stop VM test-azdoit-vm-1
- [ ] Verify VM is stopped
- [ ] Start VM test-azdoit-vm-1
- [ ] Verify VM is running
- [ ] List all resources in resource group
- [ ] Show cost estimate for resource group
- [ ] Get resource group details

## SSH Access

To connect to the VM directly:

```bash
# Get the SSH command
terraform output ssh_connection_command

# Or manually
ssh azureuser@$(terraform output -raw vm_public_ip)
```

## Cost Estimate

**Daily Cost**: ~$0.20 USD (based on Standard_B2s VM in East US)
**Monthly Cost**: ~$6.00 USD if running 24/7

**Cost Breakdown**:
- Standard_B2s VM: ~$0.166/day
- Public IP (Standard): ~$0.012/day
- Storage (30GB LRS): ~$0.005/day

**To Minimize Costs**:
1. Stop the VM when not testing: `azdoit "stop VM test-azdoit-vm-1"`
2. Destroy infrastructure after testing: `terraform destroy`
3. Use smaller VM size: Change `vm_size` to `Standard_B1s` (~$0.10/day)

## Cleanup

### Stop VM (Keeps Infrastructure)

```bash
# Using azdoit
azdoit "stop VM test-azdoit-vm-1"

# Using Azure CLI
az vm deallocate --resource-group test-azdoit-rg --name test-azdoit-vm-1
```

Stopped VMs still incur charges for storage and public IP (~$0.02/day).

### Destroy All Resources

```bash
terraform destroy
```

Type `yes` when prompted. This removes all resources and stops all charges.

**Verify Cleanup**:
```bash
az group show --name test-azdoit-rg
# Should return error: Resource group not found
```

## Troubleshooting

### Issue: SSH Key Validation Error

**Error**: "The ssh_public_key must be a valid SSH public key"

**Solution**:
```bash
# Check your key format
cat ~/.ssh/id_rsa.pub

# Should start with: ssh-rsa, ssh-ed25519, or ssh-ecdsa
# If not, generate a new key:
ssh-keygen -t rsa -b 4096 -f ~/.ssh/azdoit_test
```

### Issue: VM Creation Fails with Quota Error

**Error**: "QuotaExceeded" or "NotAvailableForSubscription"

**Solution**:
1. Try different region: Set `location = "westus2"` in terraform.tfvars
2. Try smaller VM: Set `vm_size = "Standard_B1s"` in terraform.tfvars
3. Request quota increase in Azure portal

### Issue: Public IP Not Accessible

**Error**: Cannot SSH to VM

**Solution**:
```bash
# Check NSG rules
az network nsg show --resource-group test-azdoit-rg --name test-azdoit-nsg

# Verify public IP is assigned
terraform output vm_public_ip

# Check VM is running
azdoit "get status of test-azdoit-vm-1"
```

### Issue: AZDOIT Commands Fail

**Error**: "Resource not found" or authentication errors

**Solution**:
```bash
# Verify Azure CLI authentication
az account show

# Check resource group exists
az group show --name test-azdoit-rg

# Verify VM exists
az vm show --resource-group test-azdoit-rg --name test-azdoit-vm-1

# Check azdoit configuration
azdoit --version
```

### Issue: Terraform State Lock

**Error**: "Error acquiring the state lock"

**Solution**:
```bash
# Wait a few minutes for previous operation to complete
# Or force unlock (use with caution)
terraform force-unlock <LOCK_ID>
```

## Advanced Configuration

### Use Different VM Size

Edit `terraform.tfvars`:
```hcl
vm_size = "Standard_B1s"  # Smaller, cheaper (~$0.10/day)
# or
vm_size = "Standard_B2ms"  # More memory (~$0.30/day)
```

### Deploy to Different Region

Edit `terraform.tfvars`:
```hcl
location = "westus2"
# or
location = "westeurope"
```

### Change Resource Group Name

Edit `terraform.tfvars`:
```hcl
resource_group_name = "my-azdoit-test-rg"
```

**Note**: Update azdoit commands to use new resource group name.

## File Structure

```
terraform/azdoit-test/
├── main.tf                    # Resource definitions
├── variables.tf               # Input variable declarations
├── outputs.tf                 # Output value definitions
├── terraform.tfvars.example   # Example configuration
├── terraform.tfvars           # Your configuration (gitignored)
├── .gitignore                 # Terraform gitignore rules
└── README.md                  # This file
```

## Next Steps

1. **Provision Infrastructure**: Run `terraform apply`
2. **Test AZDOIT**: Use checklist above to validate functionality
3. **Report Issues**: Document any failures or unexpected behavior
4. **Cleanup**: Run `terraform destroy` when done

## Resources

- [Terraform Azure Provider Documentation](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs)
- [Azure VM Pricing Calculator](https://azure.microsoft.com/en-us/pricing/calculator/)
- [AZDOIT Documentation](../../README.md)

## Support

For issues related to:
- **Terraform**: Check Terraform documentation or open issue in this repo
- **AZDOIT**: Check AZDOIT documentation or open issue
- **Azure**: Check Azure documentation or contact Azure support
