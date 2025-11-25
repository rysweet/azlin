# Batch Operations

Execute commands and manage multiple VMs simultaneously using powerful selection criteria.

## Overview

azlin's batch operations allow you to perform actions on multiple VMs at once, dramatically reducing the time needed to manage VM fleets. Instead of manually connecting to each VM or running commands one at a time, batch operations use parallel execution to complete tasks across your entire fleet in seconds.

**Key capabilities:**
- Execute shell commands on multiple VMs simultaneously
- Start/stop VMs in parallel for cost management
- Sync configuration and files across your fleet
- Filter VMs by tags, name patterns, or select all
- Control parallelism and timeouts
- View aggregated results

## When to Use Batch Operations

### Perfect For

- **Fleet-wide updates**: Update packages, restart services, or deploy configuration changes
- **Cost management**: Stop all development VMs at end of day, start them in the morning
- **Configuration synchronization**: Distribute dotfiles, scripts, or configuration to all VMs
- **Health checks**: Run diagnostic commands across your fleet
- **Emergency responses**: Quick shutdown of compromised VMs or rapid deployment of security patches

### Not Ideal For

- Single VM operations (use regular commands)
- Operations requiring different parameters per VM
- Interactive commands requiring user input

## VM Selection Methods

All batch commands support three ways to select target VMs:

### By Tag

Select VMs with specific Azure tags:

```bash
azlin batch command 'uptime' --tag env=dev
azlin batch stop --tag project=ml-training
azlin batch start --tag team=backend
```

**Use Case:** Organize VMs by environment, project, team, or purpose.

### By Name Pattern

Select VMs matching a glob pattern:

```bash
azlin batch command 'df -h' --vm-pattern 'web-*'
azlin batch stop --vm-pattern 'test-vm-*'
azlin batch start --vm-pattern '*-worker'
```

**Use Case:** Naming conventions for VM fleets (web-1, web-2, etc.).

### All VMs

Select every VM in the resource group:

```bash
azlin batch command 'uptime' --all
azlin batch sync --all
azlin batch stop --all --confirm
```

**Use Case:** Fleet-wide operations when you need to affect everything.

## Available Operations

### Command Execution

Execute any shell command across selected VMs:

```bash
azlin batch command 'git pull' --tag env=dev --show-output
```

**[Learn more about batch command →](command.md)**

### Start VMs

Start multiple stopped/deallocated VMs in parallel:

```bash
azlin batch start --tag env=dev
```

**Use Case:** Morning start of development environment, scaling up for load.

### Stop VMs

Stop and deallocate multiple VMs to save costs:

```bash
azlin batch stop --tag env=dev --confirm
```

**Use Case:** Evening shutdown of development VMs, emergency cost reduction.

### Sync Home Directory

Distribute files from `~/.azlin/home/` to multiple VMs:

```bash
azlin batch sync --tag project=myapp --dry-run
```

**Use Case:** Deploy configuration files, scripts, or dotfiles fleet-wide.

## Common Options

All batch commands support these options:

| Option | Description | Default |
|--------|-------------|---------|
| `--tag` | Filter by Azure tag (key=value) | None |
| `--vm-pattern` | Filter by name glob pattern | None |
| `--all` | Select all VMs in resource group | False |
| `--resource-group`, `--rg` | Target resource group | Current context |
| `--config` | Config file path | `~/.azlin/config.toml` |
| `--max-workers` | Parallel worker threads | 10 |

## Quick Start Examples

### Example 1: Update All Development VMs

```bash
# Update packages on all dev VMs
azlin batch command 'sudo apt update && sudo apt upgrade -y' \
  --tag env=dev \
  --show-output
```

### Example 2: Evening Cost Savings

```bash
# Stop all non-production VMs at end of day
azlin batch stop --tag env=dev --confirm
azlin batch stop --tag env=test --confirm
```

### Example 3: Deploy Configuration

```bash
# Sync new configuration to web servers
azlin batch sync --vm-pattern 'web-*' --dry-run
# Review what will be synced, then:
azlin batch sync --vm-pattern 'web-*'
```

### Example 4: Fleet Health Check

```bash
# Check disk space across all VMs
azlin batch command 'df -h' --all --show-output

# Check uptime and load
azlin batch command 'uptime' --all --show-output
```

### Example 5: Restart Services

```bash
# Restart nginx on all web servers
azlin batch command 'sudo systemctl restart nginx' \
  --vm-pattern 'web-*'
```

## Performance and Parallelism

### Default Behavior

By default, batch operations use **10 parallel workers**. This means azlin will:
- Process up to 10 VMs simultaneously
- Queue remaining VMs until workers are available
- Complete operations much faster than sequential execution

### Adjusting Parallelism

```bash
# High parallelism for large fleets (50 VMs)
azlin batch command 'uptime' --all --max-workers 20

# Conservative parallelism for resource-intensive operations
azlin batch command 'docker build .' --all --max-workers 5

# Sequential (one at a time)
azlin batch command 'important-operation' --all --max-workers 1
```

**Guidelines:**
- **Light operations** (uptime, status checks): 10-20 workers
- **Medium operations** (package updates, file syncs): 5-10 workers
- **Heavy operations** (builds, migrations): 1-5 workers

### Timeouts

Commands have a default 300-second (5 minute) timeout:

```bash
# Quick operations
azlin batch command 'hostname' --all --timeout 30

# Long-running operations
azlin batch command 'apt full-upgrade -y' --all --timeout 1800
```

## Safety Features

### Confirmation Prompts

Stop operations require confirmation unless you use `--confirm`:

```bash
# Will prompt for confirmation
azlin batch stop --all

# Skip confirmation
azlin batch stop --all --confirm
```

### Dry Run Mode

Test sync operations before executing:

```bash
# See what would be synced
azlin batch sync --all --dry-run

# Actually sync
azlin batch sync --all
```

### Selection Preview

Batch commands show you which VMs will be affected before executing:

```
Selected VMs (3):
  - web-server-1
  - web-server-2
  - web-server-3

Continue? [y/N]:
```

## Best Practices

### 1. Use Tags for Organization

Create a tagging strategy for easy batch selection:

```bash
# Tag VMs during creation
azlin new --name web-1 --tags env=prod,role=web,team=backend

# Later, operate on groups
azlin batch stop --tag team=backend
azlin batch command 'git pull' --tag role=web
```

### 2. Test with Dry Run or Small Sets

Before affecting many VMs, test on a subset:

```bash
# Test on one VM with the pattern
azlin batch command 'systemctl restart app' --vm-pattern 'web-1'

# Then run on all
azlin batch command 'systemctl restart app' --vm-pattern 'web-*'
```

### 3. Use --show-output for Verification

Always use `--show-output` when you need to verify results:

```bash
azlin batch command 'systemctl status nginx' \
  --vm-pattern 'web-*' \
  --show-output
```

### 4. Adjust Parallelism for Network

If you see SSH timeouts or connection issues, reduce parallelism:

```bash
# Too many concurrent connections?
azlin batch command 'uptime' --all --max-workers 5
```

### 5. Combine with Fleet Management

For complex workflows, use fleet management:

```bash
# Simple batch operation
azlin batch command 'docker-compose up -d' --tag role=app

# Complex orchestration
azlin fleet run deploy-workflow --tag role=app
```

## Comparison: Batch vs Other Tools

### vs Individual Commands

```bash
# Without batch (slow, manual)
azlin connect web-1 -c 'git pull'
azlin connect web-2 -c 'git pull'
azlin connect web-3 -c 'git pull'

# With batch (fast, automatic)
azlin batch command 'git pull' --vm-pattern 'web-*' --show-output
```

### vs Fleet Management

```bash
# Batch: Simple, single command
azlin batch command 'uptime' --all

# Fleet: Complex, multi-step workflows
azlin fleet run health-check-workflow --all
```

**Use batch for:** Simple commands, start/stop, syncing files

**Use fleet for:** Multi-step processes, conditional logic, orchestration

### vs Ansible/Fabric

- **azlin batch**: Zero setup, works with azlin-provisioned VMs immediately
- **Ansible**: Requires inventory, playbooks, more powerful for complex scenarios
- **Fabric**: Python-based, requires script writing

## Troubleshooting

### "No VMs Selected" Error

**Cause:** Your filter (tag, pattern) matched no VMs.

**Solution:**
```bash
# Check what VMs exist
azlin list

# Verify tags
azlin list --format json | grep tags

# Try broader pattern
azlin batch command 'uptime' --vm-pattern 'web*' --show-output
```

### Timeout Errors

**Cause:** Command takes longer than timeout (default 300s).

**Solution:**
```bash
# Increase timeout for long operations
azlin batch command 'apt full-upgrade -y' \
  --all \
  --timeout 1800
```

### Connection Failures

**Cause:** SSH connectivity issues, stopped VMs, network problems.

**Solution:**
```bash
# Check VM status
azlin status

# Test individual connection
azlin connect problem-vm

# Reduce parallelism to avoid overwhelming network
azlin batch command 'uptime' --all --max-workers 5
```

### Partial Failures

**Cause:** Some VMs fail while others succeed.

**Solution:**
- Batch operations continue despite individual failures
- Review output to see which VMs failed
- Re-run on failed VMs only using specific patterns

## See Also

- **[Batch Command](command.md)** - Execute commands on multiple VMs
- **[Fleet Management](fleet.md)** - Complex orchestration workflows
- **[Parallel Execution](parallel.md)** - Understand parallelism and performance
- **[Selectors](selectors.md)** - Advanced VM selection techniques
- **[Tags Guide](../advanced/tags.md)** - VM tagging best practices
- **[Cost Optimization](../ai/autopilot.md)** - Automated cost management

---

*Documentation last updated: 2025-11-24*
