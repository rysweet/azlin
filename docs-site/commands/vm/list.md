# azlin list

**Discover and filter VMs across resource groups and contexts**

## Description

The `azlin list` command displays all azlin-managed VMs in table format, showing VM name, status, IP address, region, size, vCPU count, and optionally quota usage and tmux session information. It supports filtering by tags, scanning across all resource groups, and querying multiple Azure contexts for multi-tenant scenarios.

**Key features:**
- Fast listing of VMs in configured resource group (default)
- Filter by tags for organizational queries
- Show quota usage and remaining capacity
- Display active tmux sessions per VM
- Multi-context support for complex Azure setups
- Prevent VM name truncation with `--wide` flag

## Usage

```bash
azlin list [OPTIONS]
```

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--resource-group, --rg TEXT` | Name | Resource group to list VMs from (default: from config) |
| `--config PATH` | File | Path to custom config file (default: `~/.azlin/config.toml`) |
| `--all` | Flag | Show all VMs including stopped/deallocated ones (default: running only) |
| `--tag TEXT` | Key or Key=Value | Filter VMs by tag (format: `key` or `key=value`) |
| `--show-quota / --no-quota` | Flag | Show/hide Azure vCPU quota information (default: show) |
| `--show-tmux / --no-tmux` | Flag | Show/hide active tmux sessions (default: show) |
| `-a, --show-all-vms` | Flag | List ALL VMs across ALL resource groups (expensive operation) |
| `--all-contexts` | Flag | List VMs across all configured contexts (requires context setup) |
| `--contexts TEXT` | Glob Pattern | List VMs from contexts matching pattern (e.g., `prod*`, `dev-*`) |
| `-w, --wide` | Flag | **NEW in v0.3.2** - Prevent VM name truncation in output |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Basic Listing

```bash
# List running VMs in default resource group
azlin list

# List all VMs including stopped ones
azlin list --all

# List VMs in specific resource group
azlin list --rg my-resource-group
```

### Wide Format (No Truncation)

```bash
# Show full VM names without truncation (NEW in v0.3.2)
azlin list --wide
azlin list -w

# Useful for long VM names
azlin list --wide --all
```

### Tag-Based Filtering

```bash
# Filter by tag key (any value)
azlin list --tag environment

# Filter by exact tag key=value
azlin list --tag environment=production
azlin list --tag team=backend
azlin list --tag project=ml-training

# Combine with --all to include stopped VMs
azlin list --tag environment=dev --all
```

### Quota and Session Information

```bash
# List with quota information (default)
azlin list

# Hide quota information for faster output
azlin list --no-quota

# Hide tmux session information
azlin list --no-tmux

# Minimal output (no quota, no tmux)
azlin list --no-quota --no-tmux
```

### Cross-Resource Group Scanning

```bash
# List ALL VMs across ALL resource groups (expensive!)
azlin list --show-all-vms
azlin list -a

# Combine with filters
azlin list -a --tag environment=production
```

### Multi-Context Queries

```bash
# List VMs across all configured contexts
azlin list --all-contexts

# List VMs from production contexts
azlin list --contexts "prod*"

# List VMs from development contexts
azlin list --contexts "*-dev"

# Include stopped VMs across contexts
azlin list --contexts "prod*" --all
```

### Combined Filters

```bash
# Production VMs, including stopped, with full names
azlin list --tag environment=production --all --wide

# Development VMs without quota display
azlin list --tag environment=dev --no-quota

# All VMs in specific RG with full details
azlin list --rg my-rg --all --wide
```

## Output Format

The `azlin list` command displays a table with the following columns:

| Column | Description |
|--------|-------------|
| **VM Name** | VM identifier (truncated unless `--wide` used) |
| **Session** | Named session (set via `azlin session`) or empty |
| **Status** | Running, Stopped, Deallocated, etc. |
| **IP Address** | Public IP (or private IP if bastion-only) |
| **Region** | Azure region (e.g., eastus, westus2) |
| **Size** | Azure VM SKU (e.g., Standard_E32as_v5) |
| **vCPUs** | Number of virtual CPUs |
| **Tmux** | Active tmux session count (if `--show-tmux`) |

**Additional footer information:**
- Total vCPU usage across running VMs
- Azure quota limits and remaining capacity (if `--show-quota`)

### Example Output

```
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━┓
┃ VM Name           ┃ Session  ┃ Status   ┃ IP Address     ┃ Region  ┃ Size                 ┃ vCPUs  ┃ Tmux  ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━┩
│ myproject         │ ml-train │ Running  │ 20.123.45.67   │ eastus  │ Standard_E32as_v5    │ 32     │ 2     │
│ backend-dev       │          │ Running  │ 20.123.45.68   │ westus2 │ Standard_E16as_v5    │ 16     │ 1     │
│ frontend-dev      │ webapp   │ Running  │ 20.123.45.69   │ eastus  │ Standard_D2s_v5      │ 2      │ 0     │
│ test-vm           │          │ Stopped  │ -              │ eastus  │ Standard_D2s_v5      │ 2      │ -     │
└───────────────────┴──────────┴──────────┴────────────────┴─────────┴──────────────────────┴────────┴───────┘

Total: 50 vCPUs used | Quota: 100 vCPUs available (50 remaining)
```

## Understanding Quota Display

The quota footer shows:

- **Total vCPUs used**: Sum of vCPUs from all running VMs
- **Quota limit**: Azure subscription regional vCPU limit
- **Remaining**: Available vCPUs for new VM provisioning

**Example:**
```
Total: 80 vCPUs used | Quota: 100 vCPUs available (20 remaining)
```

This means:
- Current running VMs use 80 vCPUs total
- You can provision up to 20 more vCPUs worth of VMs
- Attempting to provision a 32-vCPU VM would fail (exceeds 20 remaining)

## Understanding Tmux Display

The tmux column shows the number of active tmux sessions on each VM:

- **Number (e.g., 2)**: Count of running tmux sessions
- **0**: No active tmux sessions (or tmux not installed)
- **-**: VM is stopped/not accessible

**Use case:** Identify which VMs have active work sessions running.

## Performance Considerations

### Fast Operations
- `azlin list` (default resource group) - **Fast** (~1-2 seconds)
- `azlin list --rg my-rg` - **Fast** (~1-2 seconds)
- `azlin list --tag key=value` - **Fast** (client-side filter)

### Slow Operations
- `azlin list --show-all-vms` - **Slow** (~10-30 seconds)
  - Queries all resource groups across subscription
  - Use sparingly or cache results

- `azlin list --all-contexts` - **Slow** (~5-60 seconds)
  - Depends on number of configured contexts
  - Authenticates to each context separately

**Tip:** For frequently-used multi-RG queries, use tags instead:
```bash
# Instead of slow --show-all-vms
azlin list --show-all-vms --tag project=myapp

# Prefer fast tag-based org + context
azlin list --tag project=myapp --contexts "prod*"
```

## Tag-Based Filtering

Tags enable powerful organizational queries:

```bash
# Find all VMs for a project
azlin list --tag project=webapp

# Find all production VMs
azlin list --tag environment=production

# Find VMs by team
azlin list --tag team=backend

# Find VMs by cost center
azlin list --tag costcenter=engineering
```

**Best practice:** Establish a tagging strategy for your organization:
- `environment`: dev, staging, production
- `project`: Project identifier
- `team`: Team or department
- `owner`: Primary contact
- `costcenter`: Billing allocation

See [`azlin tag`](tag.md) for managing tags.

## Multi-Context Scenarios

Multi-context support enables querying across:
- Multiple Azure subscriptions
- Multiple tenants
- Different authentication profiles

**Setup:**
```bash
# Create contexts for each subscription
azlin context create prod-eastus --subscription <sub-id> --rg prod-rg
azlin context create prod-westus --subscription <sub-id> --rg prod-rg-west
azlin context create dev-eastus --subscription <sub-id> --rg dev-rg

# Query production VMs across regions
azlin list --contexts "prod-*"

# Query all VMs across all contexts
azlin list --all-contexts
```

See [`azlin context`](../context/index.md) for context management.

## Troubleshooting

### No VMs Listed

**Symptoms:** Empty table or "No VMs found" message.

**Solutions:**
```bash
# Verify resource group is correct
azlin list --rg <your-rg>

# Check if VMs are stopped
azlin list --all

# Verify authentication
az account show

# Try cross-RG scan
azlin list --show-all-vms
```

### Quota Display Shows 0/0

**Symptoms:** Quota footer shows "0 vCPUs used | Quota: 0 vCPUs available".

**Solutions:**
```bash
# Check Azure CLI authentication
az account show

# Verify subscription has access
az vm list-usage --location eastus --output table

# Try different region
azlin list --rg <rg> --no-quota  # Skip quota check
```

### Tmux Count Incorrect

**Symptoms:** Tmux column shows 0 but sessions exist, or shows "-" for running VM.

**Possible causes:**
- SSH connection issues (firewall, bastion)
- VM not reachable from current network
- tmux not installed on VM

**Solutions:**
```bash
# Verify VM is reachable
azlin connect myvm -- echo "test"

# Check tmux manually
azlin connect myvm -- tmux ls

# Skip tmux display
azlin list --no-tmux
```

### VM Names Truncated

**Symptoms:** Long VM names cut off with "..." in table output.

**Solution:**
```bash
# Use wide flag (NEW in v0.3.2)
azlin list --wide
azlin list -w
```

### Slow Performance

**Symptoms:** `azlin list` takes >10 seconds.

**Solutions:**
```bash
# Disable quota check
azlin list --no-quota

# Disable tmux check
azlin list --no-tmux

# Both disabled for fastest output
azlin list --no-quota --no-tmux

# If using --show-all-vms, try scoping to specific RG
azlin list --rg my-rg  # Much faster
```

### Context Pattern No Match

**Symptoms:** `azlin list --contexts "prod*"` returns no results.

**Solutions:**
```bash
# List configured contexts
azlin context list

# Verify pattern matches context names
azlin list --contexts "production-*"

# Try wildcard at both ends
azlin list --contexts "*prod*"
```

## Advanced Usage

### Scripting and Automation

```bash
# Get VM count
vm_count=$(azlin list --no-quota --no-tmux | grep -c "Running")

# Check if specific VM exists
if azlin list | grep -q "myvm"; then
    echo "VM exists"
fi

# Export VM list (parse table output)
azlin list --wide --no-quota --no-tmux > vms.txt
```

### Monitoring Workflows

```bash
# Check quota before provisioning
azlin list  # Review "remaining" quota

# Verify new VM appears
azlin new --name test && azlin list

# Monitor multi-region deployment
azlin list --contexts "prod-*" --all
```

### Cost Tracking

```bash
# Find stopped VMs to deallocate
azlin list --all | grep "Stopped"

# Review large VMs for cost optimization
azlin list --wide | grep "E64"

# See per-team resource usage
azlin list --tag team=backend
azlin list --tag team=frontend
```

## Related Commands

- [`azlin new`](new.md) - Provision new VMs
- [`azlin connect`](connect.md) - Connect to VM by name
- [`azlin status`](status.md) - Detailed VM status
- [`azlin session`](session.md) - Manage session names
- [`azlin tag`](tag.md) - Manage VM tags
- [`azlin context list`](../context/list.md) - List configured contexts

## Source Code

- [vm_manager.py](https://github.com/rysweet/azlin/blob/main/src/azlin/vm_manager.py) - VM listing logic
- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - CLI command definition
- [context_manager.py](https://github.com/rysweet/azlin/blob/main/src/azlin/context_manager.py) - Multi-context support

## See Also

- [All VM commands](index.md)
- [Context Management](../context/index.md)
- [Tag Management](tag.md)
