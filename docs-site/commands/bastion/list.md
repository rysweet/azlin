# azlin bastion list

**List Azure Bastion hosts in your subscription**

## Description

The `azlin bastion list` command shows all Azure Bastion hosts in your subscription, optionally filtered by resource group. This helps you identify available bastion hosts for secure VM connections without public IPs.

## Usage

```bash
azlin bastion list [OPTIONS]
```

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--resource-group, --rg TEXT` | Name | Filter by resource group (optional) |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### List All Bastion Hosts

```bash
# List all bastions in subscription
azlin bastion list
```

**Output:**
```
Azure Bastion Hosts

Name                Resource Group        Status      VNet              Region        SKU
corporate-bastion   production-rg        Running     corp-vnet         eastus        Standard
dev-bastion         development-rg       Running     dev-vnet          westus2       Basic
test-bastion        test-rg              Stopped     test-vnet         centralus     Basic

Total: 3 bastion hosts
```

### List by Resource Group

```bash
# List bastions in specific resource group
azlin bastion list --resource-group production-rg

# Short form
azlin bastion list --rg dev-rg
```

**Output:**
```
Azure Bastion Hosts (Resource Group: production-rg)

Name                Status      VNet              Region        SKU
corporate-bastion   Running     corp-vnet         eastus        Standard

Total: 1 bastion host
```

## Output Fields

- **Name** - Bastion host name
- **Resource Group** - Azure resource group containing the bastion
- **Status** - Running, Stopped, or other status
- **VNet** - Virtual network the bastion is deployed in
- **Region** - Azure region location
- **SKU** - Bastion SKU (Basic or Standard)

## Common Workflows

### Find Bastions for VM Connection

```bash
# List all bastions
azlin bastion list

# Configure VM to use bastion
azlin bastion configure my-vm --bastion-name corporate-bastion --rg production-rg
```

### Audit Bastion Deployment

```bash
# List all bastions across subscription
azlin bastion list

# Check each resource group
azlin bastion list --rg rg-1
azlin bastion list --rg rg-2
azlin bastion list --rg rg-3
```

### Cost Analysis

```bash
# List bastions to identify cost sources
azlin bastion list

# Bastion costs:
# - Basic SKU: ~$140/month ($0.19/hour)
# - Standard SKU: ~$290/month ($0.40/hour)
```

## Understanding Azure Bastion

Azure Bastion provides secure RDP/SSH connectivity to VMs without:
- Public IP addresses on VMs
- Jump boxes or VPN configuration
- Exposing management ports to internet

**Benefits:**
- Enhanced security
- Simplified network architecture
- Centralized access control
- No client software needed (browser-based)

**Costs:**
- Basic SKU: ~$140/month
- Standard SKU: ~$290/month
- Data transfer charges apply

## Troubleshooting

### No Bastions Listed

**Symptoms:** Empty list or "No bastion hosts found"

**Solutions:**
```bash
# Verify you're in correct subscription
az account show

# Check different resource groups
azlin bastion list --rg RESOURCE-GROUP-NAME

# Verify bastion exists in Azure Portal
# Navigate to: Azure Bastion → see list
```

### Bastion Not in Expected RG

**Symptoms:** Bastion missing from resource group list

**Solutions:**
```bash
# List all bastions (no filter)
azlin bastion list

# Search for bastion by name
azlin bastion list | grep BASTION-NAME

# Check Azure Portal for actual location
```

### Permission Issues

**Symptoms:** "Insufficient permissions" error

**Solutions:**
```bash
# Verify Azure permissions
az role assignment list --assignee $(az account show --query user.name -o tsv)

# Need Reader role or higher to list bastions
# Contact Azure admin for access
```

## Best Practices

### Document Bastion Locations

```bash
# Export bastion list for documentation
azlin bastion list > bastions-$(date +%Y%m%d).txt

# Share with team
cat bastions-*.txt
```

### Regular Audits

```bash
# Monthly bastion audit
azlin bastion list
# Review:
# - Are all bastions needed?
# - Are SKUs appropriate?
# - Check status (stop unused ones)
```

### Cost Optimization

```bash
# List bastions and check SKUs
azlin bastion list

# Consider:
# - Consolidate multiple bastions if possible
# - Use Basic SKU where Standard features not needed
# - Stop/delete unused bastions
```

## Integration with azlin connect

```bash
# List bastions
azlin bastion list

# Connect to VM via bastion
azlin connect my-vm --bastion-name corporate-bastion
```

## Related Commands

- [`azlin bastion status`](status.md) - Show bastion host status
- [`azlin bastion configure`](configure.md) - Configure bastion for VM
- [`azlin connect`](../vm/connect.md) - Connect to VM via SSH
- [`azlin new`](../vm/new.md) - Create VM with bastion support

## Source Code

- [bastion.py](https://github.com/rysweet/azlin/blob/main/src/azlin/bastion.py) - Bastion management logic
- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - CLI command definition

## See Also

- [All bastion commands](index.md)
- [Azure Bastion](../../bastion/index.md)
- [Security Benefits](../../bastion/security.md)
