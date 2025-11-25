# azlin bastion create

Create Azure Bastion host for secure VM access.

## Synopsis

```bash
azlin bastion create [OPTIONS]
```

## Description

Creates Azure Bastion host in the resource group's VNet. Enables secure RDP/SSH access to VMs without public IPs.

## Examples

```bash
# Create Bastion with defaults
azlin bastion create

# Specify resource group
azlin bastion create --rg my-rg
```

## What Gets Created

- Bastion host
- Public IP for Bastion
- AzureBastionSubnet (if not exists)

## Cost

Basic SKU: ~$140/month (0.19/hour)
Standard SKU: ~$290/month (0.40/hour)

## Related Commands

- [azlin bastion status](status.md) - View status
- [azlin bastion configure](configure.md) - Configure VM to use Bastion
