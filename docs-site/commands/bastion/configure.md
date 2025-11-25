# azlin bastion configure

Configure Bastion connection for a VM.

## Synopsis

```bash
azlin bastion configure VM_NAME [OPTIONS]
```

## Description

Creates a mapping between a VM and a Bastion host, so azlin will automatically use the Bastion when connecting to the VM via SSH.

This is useful for VMs without public IPs that require Azure Bastion for connectivity.

## Arguments

**VM_NAME** - VM name to configure (required)

## Options

| Option | Description |
|--------|-------------|
| `--bastion-name TEXT` | Bastion host name (required) |
| `--resource-group, --rg TEXT` | VM resource group |
| `--bastion-resource-group, --bastion-rg TEXT` | Bastion resource group (defaults to VM RG) |
| `--enable / --disable` | Enable or disable mapping |
| `-h, --help` | Show help message |

## Examples

### Basic Configuration

```bash
# Configure VM to use Bastion
azlin bastion configure my-vm --bastion-name my-bastion --rg my-rg
```

After configuration, `azlin connect my-vm` will automatically use the Bastion.

### Cross-Resource-Group

```bash
# Bastion in different resource group
azlin bastion configure my-vm \
  --bastion-name shared-bastion \
  --rg vm-rg \
  --bastion-rg bastion-rg
```

Useful when Bastion is shared across multiple resource groups.

### Disable Bastion

```bash
# Disable Bastion for direct SSH
azlin bastion configure my-vm --bastion-name my-bastion --rg my-rg --disable
```

Removes Bastion mapping, returns to direct SSH.

### Enable After Disabling

```bash
# Re-enable Bastion
azlin bastion configure my-vm --bastion-name my-bastion --rg my-rg --enable
```

## Use Cases

### Secure VM Access

```bash
# 1. List available Bastions
azlin bastion list

# 2. Configure VM
azlin bastion configure prod-vm --bastion-name prod-bastion --rg production

# 3. Connect (automatically uses Bastion)
azlin connect prod-vm
```

### Shared Bastion Infrastructure

```bash
# Multiple VMs using same Bastion
azlin bastion configure web-01 --bastion-name shared-bastion --rg my-rg
azlin bastion configure web-02 --bastion-name shared-bastion --rg my-rg
azlin bastion configure api-01 --bastion-name shared-bastion --rg my-rg
```

All VMs now accessible via the shared Bastion.

### Migration from Public to Private

```bash
# Before: VM has public IP
azlin connect my-vm  # Direct SSH

# Remove public IP, configure Bastion
azlin bastion configure my-vm --bastion-name my-bastion --rg my-rg

# After: Secure Bastion access
azlin connect my-vm  # Via Bastion
```

## How It Works

1. **Mapping Created** - Configuration stored in azlin
2. **Connect Command** - `azlin connect` detects mapping
3. **Bastion Tunnel** - Creates Azure Bastion tunnel
4. **SSH Connection** - SSH over tunnel to VM

## Configuration Storage

Bastion mappings are stored in:
- `~/.azlin/config.toml` - Per-VM Bastion configuration
- Persists across azlin sessions
- Can be edited manually if needed

## Troubleshooting

### Bastion Not Found

```bash
# Verify Bastion exists
azlin bastion list

# Check status
azlin bastion status my-bastion --rg my-rg
```

### Connection Fails

```bash
# Test Bastion directly
az network bastion ssh --name my-bastion --resource-group my-rg \
  --target-resource-id /subscriptions/.../resourceGroups/.../providers/Microsoft.Compute/virtualMachines/my-vm \
  --auth-type ssh-key --username azureuser --ssh-key ~/.ssh/id_rsa
```

### Wrong Resource Group

```bash
# Find Bastion's location
azlin bastion list | grep my-bastion

# Use correct resource groups
azlin bastion configure my-vm \
  --bastion-name my-bastion \
  --rg vm-rg \
  --bastion-rg correct-bastion-rg
```

### Remove Configuration

```bash
# Disable Bastion mapping
azlin bastion configure my-vm --bastion-name my-bastion --rg my-rg --disable

# Or edit ~/.azlin/config.toml manually
```

## Security Benefits

Using Bastion provides:

1. **No Public IPs** - VMs don't need public IP addresses
2. **Centralized Access** - Single secure entry point
3. **Azure Integration** - Native Azure security features
4. **Audit Logs** - Connection logging in Azure Monitor
5. **NSG Protection** - Network-level security rules

## Related Commands

- [azlin bastion list](list.md) - List Bastion hosts
- [azlin bastion status](status.md) - Check Bastion status
- [azlin connect](../vm/connect.md) - SSH to VM (uses configured Bastion)

## See Also

- [Bastion Overview](index.md)
- [Azure Bastion Documentation](https://docs.microsoft.com/azure/bastion/)
- [Security Benefits](../../bastion/security.md)
