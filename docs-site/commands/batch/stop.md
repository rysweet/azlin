# azlin batch stop

**Stop/deallocate multiple VMs simultaneously**

## Description

The `azlin batch stop` command stops or deallocates multiple running VMs in parallel. By default, VMs are deallocated to stop billing for compute resources. This is ideal for shutting down development environments at end of day or reducing costs for idle workloads.

## Usage

```bash
azlin batch stop [OPTIONS]
```

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--tag TEXT` | Key=Value | Filter VMs by tag (format: `key=value`) |
| `--vm-pattern TEXT` | Pattern | Filter VMs by name pattern (glob syntax) |
| `--all` | Flag | Select all VMs in resource group |
| `--resource-group, --rg TEXT` | Name | Azure resource group |
| `--config PATH` | Path | Config file path |
| `--deallocate / --no-deallocate` | Bool | Deallocate to save costs (default: yes) |
| `--max-workers INTEGER` | Count | Maximum parallel workers (default: 10) |
| `--confirm` | Flag | Skip confirmation prompt |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Stop VMs by Tag

```bash
# Stop all dev environment VMs
azlin batch stop --tag 'env=dev'

# Stop all VMs for a project
azlin batch stop --tag 'project=webapp'
```

### Stop VMs by Name Pattern

```bash
# Stop all test VMs
azlin batch stop --vm-pattern 'test-*'

# Stop specific numbered VMs
azlin batch stop --vm-pattern 'worker-[6-10]'
```

### Stop All VMs

```bash
# Stop all VMs in resource group (with confirmation)
azlin batch stop --all

# Stop all without confirmation
azlin batch stop --all --confirm
```

### Stop Without Deallocate

```bash
# Just stop, don't deallocate (still incurs charges)
azlin batch stop --tag 'env=staging' --no-deallocate
```

### Custom Parallelism

```bash
# Stop with more workers
azlin batch stop --tag 'env=test' --max-workers 20

# Limit workers to avoid rate limiting
azlin batch stop --all --max-workers 5
```

## Deallocate vs Stop

**Deallocate (Default - Recommended):**
- Stops billing for compute
- Releases IP address (unless static)
- Faster to stop
- Slower to start again
- **Saves money**

**Stop Only (`--no-deallocate`):**
- Still charges for compute
- Keeps IP address
- Slower to stop
- Faster to start
- **More expensive**

**Recommendation:** Always use default deallocate unless you specifically need to preserve the IP address.

## Common Workflows

### End of Day Shutdown

```bash
# Stop all team VMs at end of day
azlin batch stop --tag 'team=engineering' --confirm
```

### Weekend Cost Savings

```bash
# Stop all non-production VMs on Friday evening
azlin batch stop --tag 'env=dev' --confirm
azlin batch stop --tag 'env=test' --confirm
azlin batch stop --tag 'env=staging' --confirm
```

### Project Completion

```bash
# Stop all VMs for completed project
azlin batch stop --tag 'project=old-project' --confirm
```

### Emergency Cost Control

```bash
# Quickly stop all VMs to control costs
azlin batch stop --all --confirm
```

## Output Example

```
Batch Stop VMs

Scanning for VMs...
Found 5 VMs matching criteria

VMs to stop (deallocate):
  dev-vm-1    (running)
  dev-vm-2    (running)
  dev-vm-3    (running)
  dev-vm-4    (running)
  dev-vm-5    (running)

Continue? [y/N]: y

Stopping VMs (max 10 parallel workers)...
✓ dev-vm-1 stopped (deallocated)
✓ dev-vm-2 stopped (deallocated)
✓ dev-vm-3 stopped (deallocated)
✓ dev-vm-4 stopped (deallocated)
✓ dev-vm-5 stopped (deallocated)

Batch stop complete!
  Total: 5 VMs
  Stopped: 5
  Failed: 0
  Time: 1m 45s

Estimated monthly savings: $450
```

## Troubleshooting

### No VMs Match Criteria

**Symptoms:** "No VMs found matching criteria"

**Solutions:**
```bash
# List running VMs
azlin list --status running

# Check tag syntax
azlin list --tag env=dev

# Try broader pattern
azlin batch stop --vm-pattern '*'
```

### Stop Fails for Some VMs

**Symptoms:** Some VMs fail to stop

**Solutions:**
```bash
# Check VM status
azlin status

# Retry failed VMs individually
azlin stop failed-vm-name

# Force stop if needed
azlin stop failed-vm-name --force
```

### VMs Still Billing After Stop

**Symptoms:** Costs remain high after stopping VMs

**Solutions:**
```bash
# Verify VMs are deallocated (not just stopped)
azlin status

# If stopped but not deallocated, deallocate them
azlin batch stop --all --deallocate --confirm

# Check for other resources (disks, IPs, etc.)
azlin cost --by-resource
```

## Best Practices

### Use Deallocate for Cost Savings

```bash
# Always use default deallocate
azlin batch stop --tag 'env=dev' --confirm

# Only use --no-deallocate if you need to preserve IP
azlin batch stop --tag 'special-case' --no-deallocate
```

### Tag-Based Automation

```bash
# Tag VMs for auto-shutdown
azlin tag my-vm --add auto-shutdown=weekends

# Stop them on schedule
# crontab: 0 18 * * 5 azlin batch stop --tag 'auto-shutdown=weekends' --confirm
```

### Pre-Stop Verification

```bash
#!/bin/bash
# Verify before stopping

echo "VMs to be stopped:"
azlin list --tag 'env=dev' --status running

read -p "Proceed with batch stop? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
  azlin batch stop --tag 'env=dev' --confirm
fi
```

### Cost Tracking

```bash
#!/bin/bash
# Track cost savings from stops

BEFORE=$(azlin cost --format json | jq '.total')
azlin batch stop --tag 'env=dev' --confirm
sleep 3600  # Wait 1 hour
AFTER=$(azlin cost --format json | jq '.total')

echo "Hourly savings: \$$(echo "$BEFORE - $AFTER" | bc)"
```

## Automation Examples

### Scheduled Weekend Shutdown

```bash
# Add to crontab
# Stop non-production VMs Friday 6 PM
# 0 18 * * 5 /path/to/weekend-shutdown.sh

#!/bin/bash
azlin batch stop --tag 'env=dev' --confirm
azlin batch stop --tag 'env=test' --confirm
azlin batch stop --tag 'env=staging' --confirm

echo "Weekend shutdown complete: $(date)" >> ~/azlin-shutdowns.log
```

### Nightly Development Shutdown

```bash
# Stop dev VMs every night at 8 PM
# 0 20 * * * azlin batch stop --tag 'team=engineering' --confirm
```

### Emergency Stop All

```bash
#!/bin/bash
# Emergency stop all VMs

echo "EMERGENCY: Stopping all VMs"
azlin batch stop --all --confirm

echo "Emergency stop completed: $(date)" | mail -s "Emergency VM Shutdown" admin@company.com
```

## Performance

| VMs | Workers | Stop Time |
|-----|---------|-----------|
| 5 VMs | 10 | 1-2 minutes |
| 10 VMs | 10 | 2-3 minutes |
| 20 VMs | 10 | 3-5 minutes |
| 20 VMs | 20 | 2-4 minutes |

*Deallocate is faster than stop-only*

## Cost Savings

Stopping and deallocating VMs can save significant costs:

| VM Size | Hourly Cost | Monthly Cost (24/7) | Monthly Savings (12h/day) |
|---------|-------------|---------------------|---------------------------|
| Standard_D2s_v5 | $0.096 | ~$70 | ~$35 |
| Standard_E16as_v5 | $1.008 | ~$730 | ~$365 |
| Standard_E32as_v5 | $2.016 | ~$1,460 | ~$730 |

## Related Commands

- [`azlin batch start`](start.md) - Start multiple VMs
- [`azlin stop`](../vm/stop.md) - Stop single VM
- [`azlin status`](../vm/status.md) - Check VM status
- [`azlin cost`](../util/cost.md) - View costs

## Source Code

- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - Command definition
- [batch.py](https://github.com/rysweet/azlin/blob/main/src/azlin/batch.py) - Batch operations logic

## See Also

- [All batch commands](index.md)
- [VM Lifecycle](../../vm-lifecycle/index.md)
- [Cost Tracking](../../monitoring/cost.md)
