# azlin bastion status

Show status of a Bastion host.

## Synopsis

```bash
azlin bastion status NAME [OPTIONS]
```

## Description

Display detailed status information for a specific Azure Bastion host including provisioning state, SKU, configuration, and connectivity details.

## Arguments

**NAME** - Bastion host name (required)

## Options

| Option | Description |
|--------|-------------|
| `--resource-group, --rg TEXT` | Resource group (required) |
| `-h, --help` | Show help message |

## Examples

### Check Bastion Status

```bash
# Show Bastion status
azlin bastion status my-bastion --rg my-rg
```

**Output:**
```
Bastion: my-bastion
Resource Group: my-rg
Status: Succeeded
SKU: Standard
Public IP: 20.1.2.3
Virtual Network: my-vnet
Subnet: AzureBastionSubnet
```

### Verify Connectivity

```bash
# Check if Bastion is ready
azlin bastion status prod-bastion --rg production-rg
```

Use before configuring VMs to ensure Bastion is operational.

### Troubleshoot Issues

```bash
# Check Bastion that's having problems
azlin bastion status problem-bastion --rg my-rg
```

Status will show provisioning state and any errors.

## Status Fields

### Provisioning State

- **Succeeded** - Bastion is operational
- **Creating** - Bastion is being created
- **Updating** - Bastion is being updated
- **Failed** - Provisioning failed
- **Deleting** - Bastion is being deleted

### SKU Levels

- **Basic** - Standard connectivity, 2-20 instances
- **Standard** - Premium features, up to 50 instances

### Configuration Details

- **Public IP** - Bastion's public endpoint
- **Virtual Network** - Connected VNet
- **Subnet** - AzureBastionSubnet (required)
- **Scale Units** - Number of instances

## Use Cases

### Pre-Configuration Check

```bash
# Verify Bastion exists before configuring VM
azlin bastion status my-bastion --rg my-rg
azlin bastion configure my-vm --bastion-name my-bastion --rg my-rg
```

### Health Monitoring

```bash
# Check Bastion health
azlin bastion status my-bastion --rg my-rg
```

Ensure Bastion is in "Succeeded" state for VM connections.

### Troubleshooting

```bash
# Diagnose connection issues
azlin bastion status my-bastion --rg my-rg
```

Check for provisioning errors or misconfigurations.

## Troubleshooting

### Bastion Not Found

```bash
# List all Bastions
azlin bastion list

# Check specific resource group
azlin bastion list --rg my-rg
```

### Failed Status

If status shows "Failed":

1. Check Azure Portal for detailed error messages
2. Verify subnet configuration (must be named "AzureBastionSubnet")
3. Ensure subnet has sufficient IP addresses (/26 or larger)
4. Check NSG rules allow Bastion traffic

### Incorrect Resource Group

```bash
# Find Bastion's resource group
azlin bastion list | grep my-bastion
```

Then use correct resource group:

```bash
azlin bastion status my-bastion --rg correct-rg
```

## Related Commands

- [azlin bastion list](list.md) - List all Bastion hosts
- [azlin bastion configure](configure.md) - Configure VM to use Bastion
- [azlin connect](../vm/connect.md) - SSH to VM (uses Bastion if configured)

## See Also

- [Bastion Overview](index.md)
- [Azure Bastion Documentation](https://docs.microsoft.com/azure/bastion/)
- [Security Benefits](../../bastion/security.md)
