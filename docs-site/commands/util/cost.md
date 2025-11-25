# azlin cost

Show cost estimates for VMs based on size and uptime.

## Usage

```bash
azlin cost [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--by-vm` | Show per-VM breakdown |
| `--from TEXT` | Start date (YYYY-MM-DD) |
| `--to TEXT` | End date (YYYY-MM-DD) |
| `--estimate` | Show monthly cost estimate |
| `--resource-group, --rg TEXT` | Resource group |
| `-h, --help` | Show help message |

## Examples

### Total Cost Summary

```bash
azlin cost
```

**Output:**
```
Cost Summary (azlin-rg)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Period: 2025-11-01 to 2025-11-24 (24 days)

Total VMs: 5
Running: 3
Stopped: 2

Estimated Cost: $145.80
  VM Compute: $132.40
  Storage: $8.20
  Network: $5.20

Daily Average: $6.08
```

### Per-VM Breakdown

```bash
azlin cost --by-vm
```

**Output:**
```
VM Cost Breakdown
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VM Name          Size              Hours  Daily   Period Total
────────────────────────────────────────────────────────────────────
alice-vm         Standard_D2s_v3   576    $2.40   $57.60
bob-vm           Standard_D4s_v3   480    $4.80   $115.20
carol-vm         Standard_D2s_v3   240    $1.20   $28.80
dev-vm           Standard_B2s      0      $0.00   $0.00 (stopped)
test-vm          Standard_B2s      0      $0.00   $0.00 (stopped)

Total: $201.60
```

### Monthly Estimate

```bash
azlin cost --estimate
```

**Output:**
```
Monthly Cost Estimate
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Based on current configuration:

alice-vm:     $72.00/month (running 24/7)
bob-vm:       $144.00/month (running 24/7)
carol-vm:     $36.00/month (running 12hrs/day)
dev-vm:       $0.00/month (stopped)
test-vm:      $0.00/month (stopped)

Total Estimate: $252.00/month

Note: Estimates based on pay-as-you-go pricing
```

### Custom Date Range

```bash
azlin cost --from 2025-11-01 --to 2025-11-30 --by-vm
```

## Common Use Cases

### Weekly Cost Review

```bash
# Check last 7 days
azlin cost --from $(date -d '7 days ago' +%Y-%m-%d) --to $(date +%Y-%m-%d)
```

### Find Expensive VMs

```bash
# Sort by cost
azlin cost --by-vm | sort -k6 -rn
```

### Budget Planning

```bash
# Get monthly projections
azlin cost --estimate
```

### Cost Optimization

```bash
# Identify VMs to stop
azlin cost --by-vm | grep "stopped"
```

## Cost-Saving Tips

### Stop Unused VMs

```bash
# Find idle VMs
azlin w | grep "0 users"

# Stop them to save costs
azlin stop idle-vm-1 idle-vm-2
```

### Use Smaller VM Sizes

```bash
# Check if you can downsize
azlin list --format detailed

# Resize to save money
# (requires VM stop, resize, restart - contact support)
```

### Delete Old VMs

```bash
# Find old VMs
azlin list

# Delete unused ones
azlin destroy old-vm-1 old-vm-2
```

## Understanding VM Costs

**Typical Azure VM Costs (Pay-as-you-go)**:

| VM Size | vCPUs | RAM | Cost/Hour | Daily (24hr) | Monthly |
|---------|-------|-----|-----------|--------------|---------|
| Standard_B1s | 1 | 1 GB | $0.01 | $0.24 | $7.30 |
| Standard_B2s | 2 | 4 GB | $0.04 | $0.96 | $29.20 |
| Standard_D2s_v3 | 2 | 8 GB | $0.10 | $2.40 | $73.00 |
| Standard_D4s_v3 | 4 | 16 GB | $0.20 | $4.80 | $146.00 |
| Standard_D8s_v3 | 8 | 32 GB | $0.40 | $9.60 | $292.00 |

**Additional Costs**:
- **Storage**: ~$0.05/GB/month for disks
- **Network**: ~$0.05-0.10/GB for outbound data
- **Bastion**: ~$140/month if using Azure Bastion

**Cost Reduction**:
- Stop VMs when not in use (saves 100% of compute)
- Use Reserved Instances for long-term VMs (save 30-50%)
- Use Spot Instances for dev/test (save up to 90%)

## Notes

- Costs are estimates based on Azure pay-as-you-go pricing
- Actual costs may vary by region and Azure discounts
- Storage costs continue even when VMs are stopped
- Network egress charges apply for data transfer

## Related Commands

- [azlin list](../vm/list.md) - List all VMs
- [azlin stop](../vm/stop.md) - Stop VMs to save costs
- [azlin destroy](../vm/destroy.md) - Delete VMs
- [azlin w](w.md) - Check VM activity
