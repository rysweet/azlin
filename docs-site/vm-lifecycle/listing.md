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

- **OS identification** - Distro icon + name/version (e.g., 🟠 Ubuntu 25.10)
- **Real-time status** - Power state, IP addresses, region
- **Resource details** - VM size, vCPUs, memory
- **Quota information** - Current usage vs. available quota
- **Tmux sessions** - Active tmux sessions per VM
- **Session names** - Custom labels for VMs
- **Tag filtering** - Filter by Azure tags
- **Filter disclosure** - Reports how many VMs its filters hid, and how to see them
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
SESSION          OS                STATUS    IP               REGION   CPU  Mem
🟠 my-project    Ubuntu 25.10      Running   20.51.23.145     eastus    32  64GB
🟠 backend-api   Ubuntu 22.04 LTS  Running   10.0.1.5 (Bast)  westus    16  32GB
🟠 model-train   Ubuntu 24.04 LTS  Running   20.14.7.89       eastus2   64  128GB
```

The OS column shows the detected operating system. The Session column includes an
OS icon prefix (🟠 Ubuntu, 🪟 Windows, 🐧 generic Linux, 🔴 Debian, 🎩 RHEL).

With `--wide` flag, names are not truncated:

```bash
azlin list --wide
```

```
NAME                      STATUS    IP ADDRESS       REGION    SIZE    vCPUs
very-long-vm-name-dev-01  Running   20.51.23.145     eastus    l       32
```

## What the Default Listing Hides

`azlin list` shows **running VMs only** by default. It reports what it left out.

```bash
azlin list
```

```
Total: 2 VMs | 2 running | 4 hidden (stopped/deallocated)
Hidden VMs still bill for attached storage. Run 'azlin list --all' to include them.
```

The `Total:` line gains a clause for each filter that dropped rows — the default
running-only filter, `--tag`, or `--vm-pattern`:

```
Total: 0 VMs | 0 running | 4 hidden (stopped/deallocated) | 2 excluded by --vm-pattern
```

When nothing was dropped the footer is exactly what it always was, and the
remedy line is not printed at all.

This matters for cost, not just for completeness. A deallocated VM stops billing
for compute but **keeps its attached managed disks**, and those disks bill at
full rate indefinitely. Before this disclosure existed, a resource group could
hold terabytes of Premium SSD attached to machines the default listing never
mentioned.

To see them:

```bash
azlin list --all
```

!!! warning "`--all` and `-a` are different flags"
    `--all` includes **stopped and deallocated VMs** in the current resource
    group. `-a` / `--show-all-vms` scans **all resource groups** and is still
    running-only. Reaching for `-a` when you meant `--all` gives you a wider
    listing with the same blind spot. Combine them (`azlin list --all -a`) for
    every VM in every resource group.

**See:** [Filter Disclosure](filter-disclosure.md) for the JSON and CSV
representations, the exact counter semantics, and scripting recipes.

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

**Read the footer first.** If a filter dropped rows, the listing says so and
tells you which filter did it:

```
Total: 0 VMs | 0 running | 4 hidden (stopped/deallocated) | 2 excluded by --vm-pattern
```

That line distinguishes the two cases that used to look identical — an empty
resource group, and a resource group whose VMs were all filtered out. Match the
clause to the fix:

| Footer clause | Cause | Fix |
|---------------|-------|-----|
| `{n} hidden (stopped/deallocated)` | The VMs exist but are stopped or deallocated | `azlin list --all` |
| `{n} excluded by --tag` | The tag filter matched nothing | Drop `--tag`, or check the tag with `azlin list --all` |
| `{n} excluded by --vm-pattern` | The name pattern matched nothing | Widen or drop `--vm-pattern` |
| No extra clause on the `Total:` line | Nothing was filtered — the resource group really is empty, or you are pointed at the wrong one | Check the resource group and your Azure login |

```bash
# Nothing was hidden, so check where you are pointed
azlin list --rg <your-rg>
az account show

# Look in every resource group (still running-only — add --all for stopped VMs)
azlin list -a
azlin list -a --all
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

## Related Guides

- [Filter Disclosure](filter-disclosure.md) - How `azlin list` reports the VMs its filters hid

## Source Code

- [CLI Command](https://github.com/rysweet/azlin/blob/main/azlin/cli.py#L400)
- [List Logic](https://github.com/rysweet/azlin/blob/main/azlin/vm.py)
- [Quota Checking](https://github.com/rysweet/azlin/blob/main/azlin/quota.py)

---

*Last updated: 2025-11-24*
