# azlin ip check

Check IP address classification and connectivity for VMs.

## Synopsis

```bash
azlin ip check [VM_NAME]
azlin ip check --all
```

## Description

Diagnoses VM IP configuration and connectivity:
- Public vs private IP
- Bastion requirement
- Connectivity status
- Network configuration

## Options

| Option | Description |
|--------|-------------|
| `--all` | Check all VMs |
| `-h, --help` | Show help |

## Examples

### Check single VM
```bash
azlin ip check my-vm
```

### Check all VMs
```bash
azlin ip check --all
```

## Output Example

```
IP Diagnostics: my-vm

IP Configuration:
  Public IP:  20.123.45.67
  Private IP: 10.0.1.4
  Classification: Public (direct SSH)

Connectivity:
  SSH (port 22): ✓ Open
  HTTP (port 80): ✓ Open
  HTTPS (port 443): ✓ Open

Network:
  VNet: my-vnet
  Subnet: default
  NSG: my-nsg

Status: ✓ VM is directly accessible via SSH
```

## Troubleshooting Guide

### No public IP

```
IP Configuration:
  Public IP: None
  Private IP: 10.0.1.4
  Classification: Private (requires Bastion)

Status: ⚠ VM requires Azure Bastion for access
```

**Solution**: Use Bastion or assign public IP
```bash
# Use Bastion
azlin bastion setup
azlin connect my-vm

# Or assign public IP (if allowed by policy)
```

### Port blocked

```
Connectivity:
  SSH (port 22): ✗ Blocked
```

**Solution**: Check NSG rules
```bash
az network nsg rule list --nsg-name my-nsg -g my-rg
```

## Related Commands

- [azlin bastion](../bastion/index.md) - Bastion setup
- [azlin connect](../vm/connect.md) - Connect to VM
- [azlin status](../vm/status.md) - VM status
