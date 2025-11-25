# azlin stop

**Stop or deallocate Azure VMs to save costs**

## Description

The `azlin stop` command stops a running Azure VM, optionally deallocating it to eliminate compute charges. By default, VMs are deallocated (`--deallocate`) to maximize cost savings. Use `--no-deallocate` to keep resources allocated for faster restarts.

**Key distinction:**
- **Deallocated (default)**: No compute billing, storage charges only
- **Stopped (--no-deallocate)**: Full billing continues, faster restart

## Usage

```bash
azlin stop [OPTIONS] VM_NAME
```

## Arguments

| Argument | Description |
|----------|-------------|
| `VM_NAME` | Required. Name of the VM to stop |

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--resource-group, --rg TEXT` | Name | Resource group containing the VM (default: from config) |
| `--config PATH` | File | Path to custom config file (default: `~/.azlin/config.toml`) |
| `--deallocate / --no-deallocate` | Flag | Deallocate VM to save costs (default: yes) |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Basic Usage

```bash
# Stop and deallocate VM (default - saves costs)
azlin stop my-vm

# Stop VM with explicit resource group
azlin stop my-vm --rg my-resource-group

# Stop without deallocation (keeps billing, faster restart)
azlin stop my-vm --no-deallocate
```

### Cost Optimization Workflows

```bash
# End of day: Deallocate all dev VMs
azlin stop dev-vm1 --deallocate
azlin stop dev-vm2 --deallocate
azlin stop test-vm --deallocate

# Weekend: Stop VMs to save costs
azlin list --tag environment=dev | grep Running | while read vm _; do
    azlin stop $vm --deallocate
done

# Lunchtime: Quick stop (no deallocation for fast resume)
azlin stop my-vm --no-deallocate
# Later: Quick start
azlin start my-vm
```

### Scripting and Automation

```bash
# Stop multiple VMs in parallel
for vm in vm1 vm2 vm3; do
    azlin stop $vm --deallocate &
done
wait
echo "All VMs stopped"

# Conditional stop (only if running)
if azlin status --vm my-vm | grep -q "Running"; then
    azlin stop my-vm --deallocate
    echo "VM stopped"
else
    echo "VM already stopped"
fi

# Scheduled shutdown (cron job)
# Add to crontab: 0 18 * * 1-5 /path/to/script.sh
#!/bin/bash
azlin stop dev-vm --deallocate
azlin stop test-vm --deallocate
```

### Emergency Shutdown

```bash
# Immediate stop (don't wait for graceful shutdown)
azlin stop runaway-vm --deallocate

# Stop and verify
azlin stop my-vm --deallocate
azlin status --vm my-vm  # Should show "Deallocated"
```

## Deallocated vs. Stopped

### Deallocated (Default)

**Pros:**
- **No compute billing** - Only pay for storage (~90% cost reduction)
- **Maximum cost savings** - Ideal for off-hours, weekends
- **Same data preserved** - All disks and configurations intact

**Cons:**
- **Slower restart** - 2-5 minutes (resource re-allocation)
- **IP may change** - Dynamic public IPs are released (unless reserved)
- **No quota hold** - vCPUs freed for other workloads

**Best for:**
- Overnight shutdowns
- Weekend/holiday periods
- Development VMs not in active use
- Cost-sensitive workloads

### Stopped (--no-deallocate)

**Pros:**
- **Faster restart** - 30-60 seconds (resources still allocated)
- **IP preserved** - Public IP stays assigned
- **Quota held** - vCPUs remain allocated to you

**Cons:**
- **Full billing continues** - Compute charges still apply
- **Minimal cost savings** - Only save during brief stops
- **Wastes quota** - Blocks vCPUs from other uses

**Best for:**
- Short breaks (lunch, meetings)
- Testing restart behavior
- Troubleshooting scenarios

## Cost Impact Analysis

### Example: Standard_E32as_v5 (128GB RAM)

| State | Hourly Cost | Daily Cost (24h) | Monthly Cost (730h) |
|-------|-------------|------------------|---------------------|
| Running | $1.50 | $36.00 | $1,095 |
| Stopped (not deallocated) | $1.50 | $36.00 | $1,095 |
| Deallocated | $0.10 (storage) | $2.40 | $73 |

**Savings from deallocation:**
- **Per day**: $33.60 (93% reduction)
- **Per month**: $1,022 (93% reduction)

**Typical work schedule (8h/day, 5 days/week):**
- Running: 40 hours/week = $60/week
- Deallocated: 128 hours/week = $12.80/week
- **Weekly savings**: $47.20
- **Monthly savings**: ~$188

## Stop Time Expectations

| Operation | Typical Duration |
|-----------|-----------------|
| Stop (no deallocation) | 30-60 seconds |
| Stop with deallocation | 1-3 minutes |

## Troubleshooting

### Stop Operation Hangs

**Symptoms:** `azlin stop` command doesn't complete after 5+ minutes.

**Solutions:**
```bash
# Check VM status in Azure portal
# VM may be stuck in "Stopping" state

# Force stop via Azure CLI
az vm stop --name my-vm --resource-group my-rg --force

# Check for Azure service issues
az vm get-instance-view --name my-vm --resource-group my-rg
```

### VM Not Found

**Symptoms:** "VM not found" or "Resource not found" error.

**Solutions:**
```bash
# List all VMs to verify name
azlin list --all

# Check if using correct resource group
azlin stop my-vm --rg correct-resource-group

# Verify VM exists
azlin status --vm my-vm
```

### Cannot Deallocate

**Symptoms:** "Cannot deallocate VM" or "Operation not allowed" error.

**Possible causes:**
- VM is part of availability set with specific constraints
- VM has extensions that prevent deallocation
- Azure policy restrictions

**Solutions:**
```bash
# Try stop without deallocation
azlin stop my-vm --no-deallocate

# Check VM constraints
az vm show --name my-vm --resource-group my-rg --query "[availabilitySet, extensions]"

# Contact Azure support if persistent
```

### Data Loss Concerns

**Question:** Will I lose data when stopping/deallocating a VM?

**Answer:** No! All data is preserved:
- **OS disk**: Fully preserved
- **Data disks**: Fully preserved
- **VM configuration**: Fully preserved
- **Network settings**: Fully preserved
- **Only lost**: Ephemeral (temporary) disk data if using temp storage

```bash
# Safe to stop - no data loss
azlin stop my-vm --deallocate

# Later: Start and resume exactly where you left off
azlin start my-vm
```

## Best Practices

### Daily Development Workflow

```bash
# Morning: Start VMs
azlin start dev-vm
azlin start test-vm

# Evening: Stop VMs (save costs overnight)
azlin stop dev-vm --deallocate
azlin stop test-vm --deallocate
```

### Weekend/Holiday Savings

```bash
# Friday evening: Stop all development VMs
azlin list --tag environment=dev | while read vm status _; do
    if [ "$status" = "Running" ]; then
        azlin stop $vm --deallocate
    fi
done

# Monday morning: Start what you need
azlin start my-dev-vm
```

### Production VMs

**Caution:** Do NOT stop production VMs unless intentional:

```bash
# Always check environment tag before stopping
azlin list --vm my-vm
# Verify tag shows environment=dev or environment=test

# Production VMs should stay running
azlin list --tag environment=production  # These should NOT be stopped
```

### Cost Monitoring

```bash
# Check which VMs are costing money
azlin list  # Running VMs = billing

# Review stopped VMs for potential deletion
azlin list --all | grep Deallocated

# Cost savings calculation
# Stopped (deallocated) VMs = ~93% savings vs. running
```

## Automation Examples

### Cron Job for Scheduled Shutdown

```bash
# /etc/cron.d/azlin-shutdown
# Stop dev VMs at 6 PM on weekdays
0 18 * * 1-5 user azlin stop dev-vm1 --deallocate
0 18 * * 1-5 user azlin stop dev-vm2 --deallocate

# Start dev VMs at 8 AM on weekdays
0 8 * * 1-5 user azlin start dev-vm1
0 8 * * 1-5 user azlin start dev-vm2
```

### GitHub Actions Workflow

```yaml
name: Stop Dev VMs Nightly

on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM UTC daily

jobs:
  stop-vms:
    runs-on: ubuntu-latest
    steps:
      - name: Stop development VMs
        run: |
          azlin stop dev-vm-1 --deallocate
          azlin stop dev-vm-2 --deallocate
        env:
          AZURE_CREDENTIALS: ${{ secrets.AZURE_CREDENTIALS }}
```

### Azure Automation

```bash
# Use Azure Automation + azlin for scheduled start/stop
# 1. Create Azure Automation account
# 2. Install azlin in automation runbook
# 3. Schedule daily start/stop
```

## Related Commands

- [`azlin start`](start.md) - Start stopped VM
- [`azlin status`](status.md) - Check VM power state
- [`azlin list`](list.md) - List VMs and their states
- [`azlin destroy`](destroy.md) - Permanently delete VM

## Source Code

- [vm_lifecycle_control.py](https://github.com/rysweet/azlin/blob/main/src/azlin/vm_lifecycle_control.py) - Start/stop logic
- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - CLI command definition

## See Also

- [All VM commands](index.md)
- [Cost Tracking](../../monitoring/cost.md)
- [VM Lifecycle](../../vm-lifecycle/index.md)
- [Azure VM Billing Documentation](https://docs.microsoft.com/azure/virtual-machines/states-billing)
