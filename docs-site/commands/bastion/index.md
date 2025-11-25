# Bastion Commands

Manage Azure Bastion hosts for secure VM connections.

## Overview

Azure Bastion provides secure RDP/SSH connectivity to VMs without exposing public IPs. These commands help you list, configure, and use Bastion hosts with azlin.

## Available Commands

- [**azlin bastion list**](list.md) - List Azure Bastion hosts
- [**azlin bastion status**](status.md) - Show Bastion host status
- [**azlin bastion configure**](configure.md) - Configure Bastion for a VM
- [**azlin bastion create**](create.md) - Create new Bastion host
- [**azlin bastion delete**](delete.md) - Delete Bastion host

## Quick Start

### List and Configure

```bash
# List Bastion hosts
azlin bastion list

# Configure VM to use Bastion
azlin bastion configure my-vm --bastion-name my-bastion --rg my-rg

# Connect (automatically uses Bastion)
azlin connect my-vm
```

### Check Status

```bash
# Show Bastion status
azlin bastion status my-bastion --rg my-rg
```

## Use Cases

### Secure Production Access

```bash
# Configure all production VMs to use Bastion
for vm in $(azlin list --tag 'env=prod' --name-only); do
  azlin bastion configure $vm --bastion-name prod-bastion --rg prod-rg
done
```

### Remove Public IPs

```bash
# Configure Bastion
azlin bastion configure secure-vm --bastion-name my-bastion --rg my-rg

# Remove public IP
az vm deallocate --name secure-vm --resource-group my-rg
az vm start --name secure-vm --resource-group my-rg

# Connect via Bastion
azlin connect secure-vm
```

## Related Commands

- [azlin connect](../vm/connect.md) - SSH to VM (uses Bastion if configured)
- [azlin code](../util/code.md) - VS Code via Bastion

## See Also

- [Azure Bastion Documentation](https://docs.microsoft.com/azure/bastion/)
- [Security Benefits](../../bastion/security.md)
