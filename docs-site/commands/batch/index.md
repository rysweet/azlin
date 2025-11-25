# Batch Commands

Execute operations on multiple VMs simultaneously.

## Overview

Batch commands enable parallel operations across VM fleets using tag-based selection, pattern matching, or operating on all VMs at once.

## Available Commands

### VM Lifecycle

- [**azlin batch start**](start.md) - Start multiple VMs
- [**azlin batch stop**](stop.md) - Stop/deallocate multiple VMs

### Execution & Sync

- [**azlin batch command**](command.md) - Execute shell commands on multiple VMs
- [**azlin batch sync**](sync.md) - Sync home directory to multiple VMs

## Quick Start Examples

### Execute Commands

```bash
# Run command on all VMs
azlin batch command 'uptime' --all

# Run on tagged VMs
azlin batch command 'git pull' --tag 'env=dev'

# Run on pattern-matched VMs
azlin batch command 'docker ps' --vm-pattern 'web-*'
```

### Sync Files

```bash
# Sync to all VMs
azlin batch sync --all

# Sync to development VMs
azlin batch sync --tag 'env=dev'

# Dry-run first
azlin batch sync --all --dry-run
```

### Start/Stop VMs

```bash
# Start development VMs
azlin batch start --tag 'env=dev'

# Stop test VMs to save costs
azlin batch stop --vm-pattern 'test-*'

# Stop all VMs
azlin batch stop --all
```

## Selection Methods

### By Tag

```bash
# Filter by tag
azlin batch command 'hostname' --tag 'env=prod'
azlin batch sync --tag 'app=web'
```

Tags set via: `azlin tag my-vm --add env=prod`

### By Pattern

```bash
# Wildcard patterns
azlin batch command 'uptime' --vm-pattern 'api-*'
azlin batch sync --vm-pattern '*-test'
```

Patterns support: `*`, `?`, `[abc]`

### All VMs

```bash
# Every VM in resource group
azlin batch command 'df -h' --all
azlin batch sync --all
```

## Common Workflows

### Code Deployment

```bash
# 1. Sync code to all app servers
azlin batch sync --tag 'app=backend'

# 2. Restart services
azlin batch command 'systemctl restart myapp' --tag 'app=backend'

# 3. Verify
azlin batch command 'systemctl status myapp' --tag 'app=backend' --show-output
```

### Development Environment Setup

```bash
# 1. Prepare local sync directory
mkdir -p ~/.azlin/home/{.config,scripts}
cp ~/.vimrc ~/.azlin/home/
cp -r ~/useful-scripts ~/.azlin/home/scripts/

# 2. Sync to all dev VMs
azlin batch sync --tag 'env=dev'

# 3. Run setup script
azlin batch command '~/scripts/setup.sh' --tag 'env=dev'
```

### Cost Optimization

```bash
# Stop non-production VMs after hours
azlin batch stop --tag 'env=dev'
azlin batch stop --tag 'env=test'

# Start them in the morning
azlin batch start --tag 'env=dev'
azlin batch start --tag 'env=test'
```

### System Maintenance

```bash
# Update all VMs
azlin batch command 'sudo apt update && sudo apt upgrade -y' --all --timeout 900

# Check disk space
azlin batch command 'df -h' --all --show-output

# Clean temp files
azlin batch command 'sudo rm -rf /tmp/*' --all
```

## Performance Tuning

### Parallelism

All batch commands support `--max-workers`:

```bash
# More parallel (faster)
azlin batch sync --all --max-workers 20

# Sequential (safer)
azlin batch command 'critical-operation' --all --max-workers 1
```

Default: 10 parallel workers

### Timeouts

Commands support `--timeout` for long operations:

```bash
# Default: 300 seconds
azlin batch command 'npm install' --all --timeout 600
```

## Best Practices

### Test First

```bash
# Test on single VM
azlin connect test-vm --command 'mycommand'

# Then batch
azlin batch command 'mycommand' --all
```

### Use Dry-Run

```bash
# Always dry-run sync operations
azlin batch sync --all --dry-run
azlin batch sync --all
```

### Tag Organization

```bash
# Set meaningful tags
azlin tag web-01 --add env=prod --add app=frontend
azlin tag api-01 --add env=prod --add app=backend

# Then batch by tag
azlin batch sync --tag 'env=prod'
azlin batch command 'deploy.sh' --tag 'app=frontend'
```

### Resource Group Scope

```bash
# Operate in specific resource group
azlin batch command 'uptime' --all --rg production-rg
```

## Output Modes

### Summary (Default)

```
✓ vm-01: Success (0.3s)
✓ vm-02: Success (0.2s)
✗ vm-03: Failed (timeout)

2/3 succeeded
```

### Detailed (--show-output)

```
=== vm-01 ===
[command output]

=== vm-02 ===
[command output]

2/2 succeeded
```

## Related Commands

- [Fleet Overview](../fleet/index.md) - Distributed command orchestration
- [azlin w](../util/w.md) - Distributed user activity
- [azlin ps](../util/ps.md) - Distributed process listing
- [azlin top](../util/top.md) - Real-time distributed monitoring

## See Also

- [Fleet Management](../../batch/fleet.md)
- [Fleet Management](../../batch/fleet.md)
- [Tags](../../advanced/tags.md)
