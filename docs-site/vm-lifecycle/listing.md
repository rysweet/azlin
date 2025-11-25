# Listing VMs

View and manage your Azure VMs with the `azlin list` command - fast, informative, and feature-rich VM inventory.

## Quick Start

```bash
# List all running VMs in default resource group
azlin list

# Include stopped VMs
azlin list --all

# List with full VM names (no truncation)
azlin list --wide
```

## Overview

The `azlin list` command provides a comprehensive view of your VMs with:

- **Real-time status** - Power state, IP addresses, region
- **Resource details** - VM size, vCPUs, memory
- **Quota information** - Current usage vs. available quota
- **Tmux sessions** - Active tmux sessions per VM
- **Session names** - Custom labels for VMs
- **Tag filtering** - Filter by Azure tags
- **Multi-context support** - View VMs across multiple Azure contexts

## Command Reference

```bash
azlin list [OPTIONS]
```

### Display Options

| Option | Description | Default |
|--------|-------------|---------|
| `--all` | Include stopped/deallocated VMs | Running only |
| `-w, --wide` | Prevent VM name truncation | Truncate to fit |
| `--show-quota / --no-quota` | Show Azure vCPU quota info | Enabled |
| `--show-tmux / --no-tmux` | Show active tmux sessions | Enabled |

### Filtering Options

| Option | Description | Example |
|--------|-------------|---------|
| `--resource-group, --rg TEXT` | Specific resource group | `--rg production-rg` |
| `--tag TEXT` | Filter by tag (key or key=value) | `--tag env=dev` |
| `-a, --show-all-vms` | All VMs across all RGs (expensive) | `-a` |

### Multi-Context Options

| Option | Description | Example |
|--------|-------------|---------|
| `--all-contexts` | List VMs across all contexts | `--all-contexts` |
| `--contexts TEXT` | Contexts matching glob pattern | `--contexts "prod*"` |

## Output Format

The default output shows:

```
NAME              STATUS    IP ADDRESS       REGION    SIZE    vCPUs  SESSION
azlin-vm-12345    Running   20.51.23.145     eastus    l       32     my-project
dev-environment   Running   10.0.1.5         westus    m       16     backend-api
ml-training       Running   20.14.7.89       eastus2   xl      64     model-train
```

With `--wide` flag, names are not truncated:

```bash
azlin list --wide
```

```
NAME                      STATUS    IP ADDRESS       REGION    SIZE    vCPUs
very-long-vm-name-dev-01  Running   20.51.23.145     eastus    l       32
```

## Common Usage Patterns

### Basic Listing

```bash
# Running VMs in default resource group
azlin list

# All VMs including stopped
azlin list --all

# VMs in specific resource group
azlin list --rg my-team-resources
```

**Example output:**

```
╭─────────────────┬─────────┬──────────────────┬─────────┬──────┬───────╮
│ Name            │ Status  │ IP Address       │ Region  │ Size │ vCPUs │
├─────────────────┼─────────┼──────────────────┼─────────┼──────┼───────┤
│ azlin-vm-45678  │ Running │ 20.51.23.145     │ eastus  │ l    │ 32    │
│ dev-vm          │ Running │ 10.0.1.5         │ westus  │ m    │ 16    │
│ test-vm         │ Stopped │ -                │ eastus  │ s    │ 2     │
╰─────────────────┴─────────┴──────────────────┴─────────┴──────┴───────╯

Quota: 50/100 vCPUs used (50.0%)
```

### Filtering by Tags

```bash
# VMs with 'env' tag (any value)
azlin list --tag env

# VMs with specific tag value
azlin list --tag env=production

# VMs with project tag
azlin list --tag project=ml-pipeline

# Combine with --all to include stopped VMs
azlin list --tag team=backend --all
```

**Example output:**

```
╭──────────────┬─────────┬──────────────────┬─────────┬──────┬───────╮
│ Name         │ Status  │ IP Address       │ Region  │ Size │ vCPUs │
├──────────────┼─────────┼──────────────────┼─────────┼──────┼───────┤
│ prod-api-01  │ Running │ 20.51.23.145     │ eastus  │ m    │ 16    │
│ prod-api-02  │ Running │ 20.51.23.146     │ eastus  │ m    │ 16    │
│ prod-web-01  │ Running │ 20.51.23.147     │ westus  │ l    │ 32    │
╰──────────────┴─────────┴──────────────────┴─────────┴──────┴───────╯
```

### Quota Monitoring

```bash
# Default view includes quota
azlin list

# Hide quota information
azlin list --no-quota

# Show only quota across all VMs
azlin list --all --no-tmux
```

**Quota display:**

```
Quota: 80/200 vCPUs used (40.0%)
Quota: 15/30 Standard_E family vCPUs (50.0%)
```

!!! tip "Quota Management"
    When quota is low, consider:
    - Stopping unused VMs with `azlin stop`
    - Using different VM families
    - Requesting quota increase via Azure Portal

    **See:** [Quota Management Guide](../advanced/quotas.md)

### Tmux Session Information

```bash
# Default view includes tmux sessions
azlin list

# Hide tmux session info
azlin list --no-tmux

# Show session names
azlin list --show-tmux
```

**Output with tmux:**

```
╭──────────────────┬─────────┬──────────────┬─────────┬──────┬───────┬─────────────────╮
│ Name             │ Status  │ IP Address   │ Region  │ Size │ vCPUs │ Session         │
├──────────────────┼─────────┼──────────────┼─────────┼──────┼───────┼─────────────────┤
│ azlin-vm-12345   │ Running │ 20.51.23.145 │ eastus  │ l    │ 32    │ my-project (1)  │
│ dev-environment  │ Running │ 10.0.1.5     │ westus  │ m    │ 16    │ backend-api (2) │
╰──────────────────┴─────────┴──────────────┴─────────┴──────┴───────┴─────────────────╯
```

The number in parentheses shows active tmux sessions on that VM.

### Multi-Context Listing

```bash
# List VMs across all contexts
azlin list --all-contexts

# List VMs from production contexts
azlin list --contexts "prod*"

# List VMs from dev contexts with specific tag
azlin list --contexts "*-dev" --tag environment=staging --all
```

**Example output:**

```
Context: production-east
╭──────────────┬─────────┬──────────────┬─────────╮
│ Name         │ Status  │ IP Address   │ Region  │
├──────────────┼─────────┼──────────────┼─────────┤
│ prod-api-01  │ Running │ 20.51.23.145 │ eastus  │
╰──────────────┴─────────┴──────────────┴─────────╯

Context: production-west
╭──────────────┬─────────┬──────────────┬─────────╮
│ Name         │ Status  │ IP Address   │ Region  │
├──────────────┼─────────┼──────────────┼─────────┤
│ prod-web-01  │ Running │ 20.14.7.89   │ westus  │
╰──────────────┴─────────┴──────────────┴─────────╯
```

**See:** [Multi-Context Configuration](../advanced/multi-context.md)

### All VMs Across Subscription

```bash
# Scan ALL VMs in ALL resource groups (slow for large subscriptions)
azlin list --show-all-vms

# Short form
azlin list -a
```

!!! warning "Performance Impact"
    `--show-all-vms` scans every resource group in your subscription.
    This can take 30+ seconds for subscriptions with many resources.
    Use `--rg` for faster, targeted queries.

## Advanced Usage

### Combining Filters

```bash
# Production VMs that are running
azlin list --tag env=production --rg prod-rg

# All dev VMs including stopped
azlin list --tag env=dev --all

# Production contexts with team tag
azlin list --contexts "prod*" --tag team=platform --all
```

### Wide Display for Long Names

```bash
# Full names without truncation
azlin list --wide

# Useful for scripting/parsing
azlin list --wide --no-quota --no-tmux | grep "Running"
```

### Minimal Output

```bash
# Just names and status
azlin list --no-quota --no-tmux

# Include stopped VMs
azlin list --all --no-quota --no-tmux
```

## Session Name Integration

List shows session names set via `azlin session`:

```bash
# Set session name on VM
azlin session azlin-vm-12345 my-project

# List shows session name
azlin list
```

**Output:**

```
╭──────────────────┬─────────┬──────────────┬─────────┬─────────────╮
│ Name             │ Status  │ IP Address   │ Region  │ Session     │
├──────────────────┼─────────┼──────────────┼─────────┼─────────────┤
│ azlin-vm-12345   │ Running │ 20.51.23.145 │ eastus  │ my-project  │
╰──────────────────┴─────────┴──────────────┴─────────┴─────────────╯
```

**See:** [Session Management](sessions.md)

## Performance Optimization

For large VM fleets:

1. **Use specific resource groups:**
   ```bash
   azlin list --rg team-resources
   ```

2. **Filter by tags:**
   ```bash
   azlin list --tag project=active
   ```

3. **Disable quota checking:**
   ```bash
   azlin list --no-quota
   ```

4. **Context-specific queries:**
   ```bash
   azlin list --contexts "prod-east"
   ```

## Scripting & Automation

The list command is designed for both human readability and script parsing:

```bash
# Get just VM names (no headers)
azlin list --no-quota --no-tmux | tail -n +2 | awk '{print $1}'

# Count running VMs
azlin list | grep "Running" | wc -l

# Find VMs by pattern
azlin list --wide | grep "ml-"

# Export to file
azlin list --all > vm-inventory.txt
```

## Troubleshooting

### No VMs Shown

```bash
# Check resource group
azlin list --rg <your-rg>

# Include stopped VMs
azlin list --all

# Check all resource groups
azlin list --show-all-vms
```

### Quota Not Showing

```bash
# Explicitly enable quota
azlin list --show-quota

# Check Azure subscription access
az account show
```

### Slow Performance

```bash
# Use specific resource group
azlin list --rg <specific-rg>

# Disable quota/tmux checks
azlin list --no-quota --no-tmux

# Avoid --show-all-vms for large subscriptions
```

### Context Errors

```bash
# List available contexts
cat ~/.azlin/config.yaml

# Test specific context
azlin list --contexts "production"
```

## Related Commands

- [`azlin new`](creating.md) - Create new VMs
- [`azlin connect`](connecting.md) - Connect to VM
- [`azlin status`](start-stop.md) - Check VM status
- [`azlin session`](sessions.md) - Manage session names
- [`azlin tag`](../commands/vm/tag.md) - Manage VM tags

## Source Code

- [CLI Command](https://github.com/rysweet/azlin/blob/main/azlin/cli.py#L400)
- [List Logic](https://github.com/rysweet/azlin/blob/main/azlin/vm.py)
- [Quota Checking](https://github.com/rysweet/azlin/blob/main/azlin/quota.py)

---

*Last updated: 2025-11-24*
