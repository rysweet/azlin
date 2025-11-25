# azlin storage status

Show detailed information about a storage account including usage, connected VMs, and costs.

## Description

The `azlin storage status` command displays comprehensive information about an Azure Files NFS storage account:

- Storage size and usage statistics
- Performance tier and capabilities
- List of VMs currently connected
- Monthly cost estimates
- Network and access information

## Usage

```bash
azlin storage status NAME [OPTIONS]
```

## Arguments

- `NAME` - Storage account name (required)

## Options

| Option | Description |
|--------|-------------|
| `--resource-group, --rg TEXT` | Azure resource group |
| `-h, --help` | Show help message |

## Examples

### View Storage Status

```bash
azlin storage status team-shared
```

**Output:**
```
Storage Account: team-shared
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Configuration:
  Resource Group: azlin-rg
  Region: eastus
  Tier: Premium
  Protocol: NFS v4.1

Size & Usage:
  Provisioned: 200 GB
  Used: 47.3 GB (23.7%)
  Available: 152.7 GB

Performance:
  Max IOPS: 100,000
  Max Throughput: 10 GB/s
  Latency: < 5 ms

Connected VMs (3):
  ✓ alice-vm    (mounted 2 days ago)
  ✓ bob-vm      (mounted 2 days ago)
  ✓ carol-vm    (mounted 1 day ago)

Network:
  Endpoint: team-shared.file.core.windows.net
  VNet: azlin-vnet
  Access: Private (VNet only)

Cost Estimate:
  Monthly: $30.60 (200 GB × $0.153/GB)
  Daily: $1.02

Created: 2025-11-22 09:15:33 UTC
Status: ● Online
```

### Check Storage in Different Resource Group

```bash
azlin storage status prod-storage --rg azlin-prod-rg
```

### View Multiple Storage Accounts

```bash
# Check status of all storage
for storage in $(azlin storage list --format names); do
    echo "=== $storage ==="
    azlin storage status $storage
    echo ""
done
```

## Common Use Cases

### Monitor Storage Usage

```bash
# Check if storage is filling up
azlin storage status ml-training

# If usage > 80%, consider expanding:
# azlin storage resize ml-training --size 1000
```

### Verify VM Connections

```bash
# See which VMs are using storage
azlin storage status team-dev

# If a VM shouldn't be connected:
# azlin storage unmount --vm old-vm
```

### Cost Analysis

```bash
# Check monthly costs for all storage
for storage in team-dev ml-training backups; do
    azlin storage status $storage | grep "Monthly:"
done
```

### Pre-Deletion Check

```bash
# Verify storage is safe to delete
azlin storage status old-project

# If no VMs connected and no important data:
# azlin storage delete old-project
```

## Output Fields

### Configuration Section

| Field | Description |
|-------|-------------|
| Resource Group | Azure resource group containing storage |
| Region | Azure region where storage is located |
| Tier | Premium or Standard performance tier |
| Protocol | NFS version (v4.1) |

### Size & Usage Section

| Field | Description |
|-------|-------------|
| Provisioned | Total allocated storage capacity |
| Used | Currently used space |
| Available | Free space remaining |
| Percentage | Usage percentage |

### Performance Section

| Field | Description |
|-------|-------------|
| Max IOPS | Maximum input/output operations per second |
| Max Throughput | Maximum data transfer rate |
| Latency | Typical response time |

### Connected VMs Section

Lists all VMs with active mounts showing:
- VM name
- Mount duration
- Mount health status

### Network Section

| Field | Description |
|-------|-------------|
| Endpoint | NFS connection endpoint |
| VNet | Virtual network for access |
| Access | Public or private access type |

### Cost Estimate Section

| Field | Description |
|-------|-------------|
| Monthly | Estimated monthly cost |
| Daily | Estimated daily cost |

**Note**: Costs are based on provisioned capacity, not actual usage.

## Troubleshooting

### Storage Not Found

**Error**: "Storage account 'myteam' not found"

**Solution**: Check storage name and resource group:
```bash
# List all storage accounts
azlin storage list

# Check with explicit resource group
azlin storage status myteam --rg azlin-rg
```

### No Permission to View Status

**Error**: "Insufficient permissions"

**Solution**: Ensure you have Reader role on storage account:
```bash
# Test authentication
azlin auth test

# Re-authenticate if needed
az login
```

### Usage Statistics Unavailable

**Warning**: "Usage statistics unavailable"

**Cause**: Statistics collection is delayed or disabled

**Solution**: Wait a few minutes and retry. Statistics update every 5-10 minutes.

## Understanding Storage Metrics

### Usage Percentage Thresholds

| Usage | Status | Action |
|-------|--------|--------|
| 0-60% | Healthy | Normal operation |
| 60-80% | Monitor | Plan for expansion |
| 80-90% | Warning | Expand soon |
| 90-100% | Critical | Expand immediately |

### Performance Impact

Storage performance degrades when:
- Usage > 90% (reduced IOPS)
- Many concurrent connections (> 100 VMs)
- High latency operations (large files)

### Cost Optimization

To reduce storage costs:

1. **Right-size capacity**: Don't over-provision
```bash
# Check actual usage
azlin storage status myteam | grep "Used:"

# Resize if over-provisioned (requires migration)
```

2. **Use Standard tier** for infrequent access
```bash
# Create Standard tier for backups
azlin storage create backups --tier Standard --size 1000
```

3. **Delete unused storage**
```bash
# Find storage with no connected VMs
azlin storage list
# Delete unused
azlin storage delete old-storage
```

## Related Commands

- [azlin storage list](list.md) - List all storage accounts
- [azlin storage create](create.md) - Create new storage
- [azlin storage mount](mount.md) - Mount storage on VM
- [azlin storage unmount](unmount.md) - Unmount from VM
- [azlin storage delete](delete.md) - Delete storage account

## See Also

- [Storage Overview](../../storage/index.md) - Understanding storage
- [Cost Management](../../monitoring/cost.md) - Cost tracking
- [Status Monitoring](../../storage/status.md) - Detailed monitoring guide
