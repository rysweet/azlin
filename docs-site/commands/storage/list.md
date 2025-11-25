# azlin storage list

List all Azure Files NFS storage accounts in your resource group.

## Description

The `azlin storage list` command displays all NFS-enabled storage accounts with their key information:

- Storage account names
- Size and tier
- Number of connected VMs
- Monthly cost estimates
- Creation dates and status

This provides a quick overview of all storage resources in your environment.

## Usage

```bash
azlin storage list [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--resource-group, --rg TEXT` | Azure resource group |
| `-h, --help` | Show help message |

## Examples

### List All Storage

```bash
azlin storage list
```

**Output:**
```
Azure Files NFS Storage Accounts (azlin-rg)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Name              Size    Tier      VMs    Monthly Cost    Created
────────────────────────────────────────────────────────────────────────────
team-shared       200 GB  Premium    3     $30.60         2025-11-22
ml-training      1000 GB  Premium    1    $153.00         2025-11-20
backups          2000 GB  Standard   0     $36.80         2025-11-15
project-archive   500 GB  Standard   0     $ 9.20         2025-11-01

Total: 4 storage accounts
Total Monthly Cost: $229.60
Total Capacity: 3.7 TB
```

### List with Different Resource Group

```bash
azlin storage list --rg azlin-prod-rg
```

### Get Storage Names for Scripting

```bash
# Get just the names
azlin storage list --format names

# Output:
# team-shared
# ml-training
# backups
# project-archive
```

### Check Storage Across Multiple Resource Groups

```bash
# List storage in all resource groups
for rg in azlin-dev-rg azlin-staging-rg azlin-prod-rg; do
    echo "=== $rg ==="
    azlin storage list --rg $rg
    echo ""
done
```

## Common Use Cases

### Audit Storage Resources

```bash
# Review all storage accounts
azlin storage list

# Identify unused storage (0 VMs)
# Check high costs
# Find old storage accounts
```

### Cost Analysis

```bash
# Calculate total storage costs
azlin storage list | grep "Total Monthly Cost"

# Find most expensive storage
azlin storage list | sort -k6 -rn
```

### Find Storage for VM

```bash
# List storage to find which to mount
azlin storage list

# Mount on VM
azlin storage mount vm team-shared --vm my-dev-vm
```

### Cleanup Old Storage

```bash
# List all storage
azlin storage list

# Delete storage with 0 VMs that's over 30 days old
azlin storage delete project-archive
```

### Monitor Storage Growth

```bash
# Save current state
azlin storage list > storage-$(date +%Y%m%d).txt

# Compare weekly to track growth
# Compare monthly for cost trending
```

## Output Columns

| Column | Description |
|--------|-------------|
| Name | Storage account name |
| Size | Provisioned capacity in GB/TB |
| Tier | Premium or Standard performance tier |
| VMs | Number of VMs with mounted storage |
| Monthly Cost | Estimated monthly cost |
| Created | Creation date (YYYY-MM-DD) |

## Understanding the Output

### VM Count Column

- **0 VMs**: Storage not currently mounted (may contain data)
- **1-5 VMs**: Typical team usage
- **5+ VMs**: Large shared workspace

**Note**: 0 VMs doesn't mean empty - check with `azlin storage status <name>`

### Cost Column

Costs are based on provisioned capacity:
- **Premium**: $0.153/GB/month
- **Standard**: $0.0184/GB/month

Actual bill may vary by region and Azure discounts.

### Tier Selection

**Use Premium for**:
- Active development
- Shared team workspaces
- Database storage
- High-frequency access

**Use Standard for**:
- Backups and archives
- Infrequent access
- Cost-sensitive workloads
- Long-term storage

## Filtering and Sorting

### Filter by Tier

```bash
# Show only Premium storage
azlin storage list | grep Premium

# Show only Standard storage
azlin storage list | grep Standard
```

### Sort by Cost

```bash
# Sort by monthly cost (highest first)
azlin storage list | tail -n +4 | sort -k6 -rn
```

### Find Large Storage

```bash
# Find storage > 500 GB
azlin storage list | awk '$2 + 0 > 500'
```

### Find Unused Storage

```bash
# Find storage with 0 connected VMs
azlin storage list | awk '$4 == 0'
```

## Troubleshooting

### No Storage Accounts Found

**Output**: "No NFS storage accounts found in resource group"

**Possible causes**:
1. No storage created yet
2. Wrong resource group
3. Storage in different region

**Solutions**:
```bash
# Create first storage
azlin storage create myteam --size 100 --tier Premium

# Check different resource group
azlin storage list --rg azlin-dev-rg

# Verify current resource group
azlin context show
```

### Permission Denied

**Error**: "Insufficient permissions to list storage accounts"

**Solution**: Ensure you have Reader role:
```bash
# Test authentication
azlin auth test

# Re-authenticate
az login

# Verify permissions
az role assignment list --assignee $(az account show --query user.name -o tsv)
```

### Incomplete Information

**Warning**: "Some storage information unavailable"

**Cause**: Storage account in different subscription or region

**Solution**: Ensure storage is in current subscription:
```bash
# Check current subscription
az account show

# Switch if needed
az account set --subscription "My Subscription"
```

## Cost Optimization Tips

### Review Monthly

```bash
# Monthly storage audit
azlin storage list

# Check for:
# - Unused storage (0 VMs)
# - Over-provisioned storage (check usage with status)
# - Duplicate storage (similar names)
```

### Consolidate Storage

Instead of many small storage accounts, use fewer large ones:

```bash
# Bad: Multiple small storage accounts
# team-alice-dev (50 GB) = $7.65/mo
# team-bob-dev (50 GB) = $7.65/mo
# team-carol-dev (50 GB) = $7.65/mo
# Total: $22.95/mo

# Good: One shared storage
# team-shared (200 GB) = $30.60/mo (saves ~$2/mo)
# Bonus: Better collaboration
```

### Right-Size Capacity

```bash
# Check actual usage
azlin storage status team-shared | grep "Used:"

# If using < 50%, consider reducing size
# (requires data migration)
```

### Use Standard Tier When Possible

```bash
# Don't use Premium for backups
# Premium 1TB = $153/mo
# Standard 1TB = $18.84/mo
# Savings: $134.16/mo (87% cheaper)

azlin storage create backups --size 1000 --tier Standard
```

## Related Commands

- [azlin storage create](create.md) - Create new storage account
- [azlin storage status](status.md) - View detailed storage information
- [azlin storage mount](mount.md) - Mount storage on VM
- [azlin storage unmount](unmount.md) - Unmount storage
- [azlin storage delete](delete.md) - Delete storage account

## See Also

- [Storage Overview](../../storage/index.md) - Understanding storage architecture
- [Cost Management](../../monitoring/cost.md) - Cost tracking and optimization
- [Resource Management](../../advanced/quotas.md) - Quota and limits
