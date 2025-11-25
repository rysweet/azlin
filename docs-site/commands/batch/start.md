# azlin batch start

**Start multiple VMs simultaneously**

## Description

The `azlin batch start` command starts multiple stopped or deallocated VMs in parallel. This is useful for quickly spinning up entire development environments, test fleets, or production workloads.

## Usage

```bash
azlin batch start [OPTIONS]
```

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--tag TEXT` | Key=Value | Filter VMs by tag (format: `key=value`) |
| `--vm-pattern TEXT` | Pattern | Filter VMs by name pattern (glob syntax) |
| `--all` | Flag | Select all VMs in resource group |
| `--resource-group, --rg TEXT` | Name | Azure resource group |
| `--config PATH` | Path | Config file path |
| `--max-workers INTEGER` | Count | Maximum parallel workers (default: 10) |
| `--confirm` | Flag | Skip confirmation prompt |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Start VMs by Tag

```bash
# Start all dev environment VMs
azlin batch start --tag 'env=dev'

# Start all VMs for a project
azlin batch start --tag 'project=webapp'
```

### Start VMs by Name Pattern

```bash
# Start all test VMs
azlin batch start --vm-pattern 'test-*'

# Start specific numbered VMs
azlin batch start --vm-pattern 'worker-[1-5]'
```

### Start All VMs

```bash
# Start all VMs in resource group (with confirmation)
azlin batch start --all

# Start all without confirmation
azlin batch start --all --confirm
```

### Custom Parallelism

```bash
# Start with more workers for faster execution
azlin batch start --tag 'env=staging' --max-workers 20

# Limit workers to avoid rate limiting
azlin batch start --all --max-workers 5
```

## Common Workflows

### Morning Team Startup

```bash
# Start all team VMs at once
azlin batch start --tag 'team=engineering' --confirm
```

### Environment Spin-Up

```bash
# Start entire staging environment
azlin batch start --tag 'env=staging' --confirm

# Start entire test environment
azlin batch start --tag 'env=test' --confirm
```

### Cost-Saving Workflows

```bash
# Stop VMs at night (in stop.md)
# Start them in the morning
azlin batch start --tag 'auto-schedule=true' --confirm
```

### Project-Based Workflows

```bash
# Start all VMs for Project A
azlin batch start --tag 'project=project-a' --confirm

# Start all VMs for Project B
azlin batch start --tag 'project=project-b' --confirm
```

## Output Example

```
Batch Start VMs

Scanning for VMs...
Found 5 VMs matching criteria

VMs to start:
  dev-vm-1    (deallocated)
  dev-vm-2    (stopped)
  dev-vm-3    (deallocated)
  dev-vm-4    (stopped)
  dev-vm-5    (deallocated)

Continue? [y/N]: y

Starting VMs (max 10 parallel workers)...
✓ dev-vm-1 started
✓ dev-vm-2 started
✓ dev-vm-3 started
✓ dev-vm-4 started
✓ dev-vm-5 started

Batch start complete!
  Total: 5 VMs
  Started: 5
  Failed: 0
  Time: 2m 15s
```

## Troubleshooting

### No VMs Match Criteria

**Symptoms:** "No VMs found matching criteria"

**Solutions:**
```bash
# List VMs to verify tags/names
azlin list

# Check tag syntax
azlin list --tag env=dev

# Try broader pattern
azlin batch start --vm-pattern '*'
```

### Start Fails for Some VMs

**Symptoms:** Some VMs fail to start

**Solutions:**
```bash
# Check VM status
azlin status

# Check for quota limits
azlin list --show-quota

# Retry failed VMs individually
azlin start failed-vm-name
```

### Rate Limiting

**Symptoms:** "Too many requests" errors

**Solutions:**
```bash
# Reduce parallel workers
azlin batch start --all --max-workers 3

# Or start in batches
azlin batch start --vm-pattern 'vm-[1-5]'
azlin batch start --vm-pattern 'vm-[6-10]'
```

## Best Practices

### Use Tags for Organization

```bash
# Tag VMs by environment
azlin tag my-vm --add env=dev

# Tag VMs by team
azlin tag my-vm --add team=backend

# Then batch start by tag
azlin batch start --tag 'team=backend'
```

### Automation with Cron

```bash
# Start VMs every weekday at 8 AM
# 0 8 * * 1-5 azlin batch start --tag 'auto-schedule=true' --confirm

# Stop VMs every weekday at 6 PM
# 0 18 * * 1-5 azlin batch stop --tag 'auto-schedule=true' --confirm
```

### Pre-Meeting Preparation

```bash
#!/bin/bash
# Start demo environment before client meeting

echo "Starting demo environment..."
azlin batch start --tag 'env=demo' --confirm

echo "Waiting for VMs to be fully ready..."
sleep 60

echo "Demo environment ready!"
azlin list --tag 'env=demo'
```

## Performance

| VMs | Workers | Start Time |
|-----|---------|------------|
| 5 VMs | 10 | 2-3 minutes |
| 10 VMs | 10 | 3-4 minutes |
| 20 VMs | 10 | 5-7 minutes |
| 20 VMs | 20 | 4-5 minutes |

*Times assume VMs are already deallocated*

## Related Commands

- [`azlin batch stop`](stop.md) - Stop multiple VMs
- [`azlin start`](../vm/start.md) - Start single VM
- [`azlin status`](../vm/status.md) - Check VM status
- [`azlin list`](../vm/list.md) - List VMs

## Source Code

- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - Command definition
- [batch.py](https://github.com/rysweet/azlin/blob/main/src/azlin/batch.py) - Batch operations logic

## See Also

- [All batch commands](index.md)
- [VM Lifecycle](../../vm-lifecycle/index.md)
- [Cost Tracking](../../monitoring/cost.md)
