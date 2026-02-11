# VM Discovery for Monitoring Commands

## Overview

All azlin monitoring commands (`azlin w`, `azlin ps`, `azlin top`) use **tag-based VM discovery** to reliably detect and monitor VMs, regardless of their naming convention.

This ensures consistent behavior across all monitoring commands and enables custom VM names (including the `hostname:session` format) to work seamlessly.

## How VM Discovery Works

### Tag-Based Discovery (Primary)

All monitoring commands discover VMs by querying Azure for resources with the `azlin-managed=true` tag. This is the same discovery mechanism used by `azlin list`.

```python
# All monitoring commands use this discovery method
def discover_vms():
    """Discover VMs with azlin-managed=true tag"""
    vms = az.vm.list(tag="azlin-managed=true")
    return vms
```

**Benefits:**
- **Reliable**: Works regardless of VM name format
- **Consistent**: Same logic as `azlin list`
- **Flexible**: Supports custom names like "myhost:dev"
- **Accurate**: Only discovers VMs created by azlin

### Name-Prefix Fallback (Secondary)

If tag-based discovery returns no results (e.g., VMs created before tagging was introduced), commands fall back to name-prefix filtering:

```python
# Fallback for VMs without tags
if not vms:
    vms = az.vm.list(name_prefix="azlin-")
```

**Use Case:** Backward compatibility with VMs created before tag-based discovery was implemented.

## Supported VM Name Formats

All monitoring commands support these VM name formats:

### Standard Format
```bash
azlin-vm-1234567890
```
**Example:** `azlin list` shows `azlin-vm-1234567890`

### Custom Name Format
```bash
myproject
```
**Example:** Created with `azlin new --name myproject`

### Compound Format (hostname:session)
```bash
hostname:session_name
```
**Example:** `myhost:dev`, `api-server:prod`, `ml-trainer:experiment-1`

**All three formats work identically with all monitoring commands.**

## Commands Updated

### `azlin w` - Show Who's Logged In

Run the `w` command on all VMs to see active users and their processes.

```bash
# Discovers ALL azlin VMs (including custom-named)
azlin w

# Works with any resource group
azlin w --resource-group my-rg
```

**Output** (showing custom-named VMs):
```
=== VM: myhost:dev (10.0.1.5) ===
 12:34:56 up  2:15,  1 user,  load average: 0.52, 0.58, 0.59
USER     TTY      FROM             LOGIN@   IDLE   JCPU   PCPU WHAT
azureuser pts/0   192.168.1.1      10:30    0.00s  0.04s  0.00s w

=== VM: api-server:prod (10.0.1.6) ===
 12:34:57 up  5:42,  2 users,  load average: 1.23, 1.15, 1.08
USER     TTY      FROM             LOGIN@   IDLE   JCPU   PCPU WHAT
azureuser pts/0   192.168.1.2      08:15    0.00s  0.12s  0.04s node server.js
admin    pts/1   192.168.1.3      11:20    0.00s  0.02s  0.01s top
```

**Use cases:**
- Check if anyone is using a VM
- Monitor system load across all VMs
- See active sessions on custom-named VMs

### `azlin ps` - Show Running Processes

Run `ps aux` on all VMs to see all processes.

```bash
# Discovers ALL azlin VMs (including custom-named)
azlin ps

# Works with any resource group
azlin ps --resource-group my-rg
```

**Output** (showing custom-named VMs):
```
=== VM: ml-trainer:experiment-1 (10.0.1.7) ===
USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
azureuser 1234 95.2 12.5 2048000 512000 pts/0  R+   10:30   2:15 python train.py
azureuser 5678  0.5  0.1  12345  6789 pts/1  S    08:00   0:05 tmux
root      9012  0.0  0.0  56789  1234 ?      S    06:00   0:00 /usr/sbin/sshd
```

**Use cases:**
- Find runaway processes across fleet
- Monitor resource usage on custom-named VMs
- Debug performance issues

### `azlin top` - Distributed Real-Time Monitoring

Monitor CPU, memory, and processes across all VMs in a unified dashboard.

```bash
# Default: 10 second refresh, discovers ALL VMs
azlin top

# Custom refresh rate (5 second refresh)
azlin top --interval 5
azlin top -i 5

# Custom SSH timeout per VM (default 5s)
azlin top --timeout 10
azlin top -t 10

# Specific resource group
azlin top --rg my-rg

# Combine options: 15s refresh, 10s timeout
azlin top -i 15 -t 10
```

**Options:**
- `--interval, -i SECONDS` - Refresh rate (default: 10 seconds)
- `--timeout, -t SECONDS` - SSH timeout per VM (default: 5 seconds)

**Output** (showing custom-named VMs):
```
╭─ Distributed Top - 2026-02-11 15:30:00 ─────────────────────────────╮
│                                                                      │
│ VM: myhost:dev (10.0.1.5)                                            │
│   CPU: 45.2%  Memory: 62.1%  Load: 0.52, 0.58, 0.59                │
│   Top Processes:                                                     │
│     python train.py    - 35.2% CPU, 12.5% MEM                       │
│     node server.js     -  8.1% CPU,  4.2% MEM                       │
│                                                                      │
│ VM: api-server:prod (10.0.1.6)                                       │
│   CPU: 78.9%  Memory: 89.2%  Load: 1.23, 1.15, 1.08                │
│   Top Processes:                                                     │
│     postgres           - 42.3% CPU, 45.1% MEM                       │
│     redis-server       - 28.5% CPU, 32.6% MEM                       │
│                                                                      │
│ VM: ml-trainer:experiment-1 (10.0.1.7)                               │
│   CPU: 95.2%  Memory: 78.5%  Load: 2.45, 2.38, 2.21                │
│   Top Processes:                                                     │
│     python train.py    - 95.2% CPU, 75.2% MEM                       │
│                                                                      │
│ Press Ctrl+C to exit                                                 │
╰──────────────────────────────────────────────────────────────────────╯
```

**Use cases:**
- Monitor distributed workloads across custom-named VMs
- Identify resource bottlenecks
- Track performance across fleet
- Real-time capacity planning

Press Ctrl+C to exit.

## Implementation Details

### Discovery Order

1. **Tag-based query** (primary): `az vm list --query "[?tags.\"azlin-managed\"=='true']"`
2. **Name-prefix fallback** (backward compatibility): `az vm list --query "[?starts_with(name, 'azlin-')]"`

### Performance

- **Tag queries**: ~500ms for 10 VMs
- **Name-prefix queries**: ~500ms for 10 VMs
- **Combined (tag + fallback)**: ~1000ms worst case
- **Caching**: Results cached for 60 seconds (configurable)

### Backward Compatibility

VMs created before tag-based discovery was implemented are still discovered via name-prefix fallback. To enable full tag-based discovery for these VMs, add the `azlin-managed=true` tag:

```bash
# Add tag to existing VM
az vm update --name azlin-vm-1234567890 --resource-group my-rg \
  --set tags."azlin-managed"="true"
```

## Configuration

VM discovery behavior can be configured in `~/.azlin/config.toml`:

```toml
[vm_discovery]
# Enable tag-based discovery (default: true)
use_tags = true

# Enable name-prefix fallback (default: true)
use_name_prefix_fallback = true

# Cache discovery results (seconds, default: 60)
cache_ttl = 60

# Tag key to query (default: "azlin-managed")
tag_key = "azlin-managed"

# Tag value to query (default: "true")
tag_value = "true"

# Name prefix for fallback (default: "azlin-")
name_prefix = "azlin-"
```

## Troubleshooting

### No VMs Found

**Symptom:** Monitoring commands show "No VMs found" but `azlin list` shows VMs.

**Solutions:**

1. Verify VMs have the `azlin-managed=true` tag:
   ```bash
   az vm show --name myvm --resource-group my-rg --query tags
   ```

2. Add tag to VMs missing it:
   ```bash
   az vm update --name myvm --resource-group my-rg \
     --set tags."azlin-managed"="true"
   ```

3. Check fallback is enabled:
   ```bash
   grep "use_name_prefix_fallback" ~/.azlin/config.toml
   # Should show: use_name_prefix_fallback = true
   ```

### Custom-Named VMs Not Detected

**Symptom:** VMs with custom names (e.g., "myhost:dev") don't appear in monitoring output.

**Root Cause:** VM missing `azlin-managed=true` tag (name-prefix fallback only works for VMs starting with "azlin-").

**Solution:**

```bash
# Add tag to custom-named VM
az vm update --name "myhost:dev" --resource-group my-rg \
  --set tags."azlin-managed"="true"

# Verify tag was added
az vm show --name "myhost:dev" --resource-group my-rg \
  --query "tags.\"azlin-managed\""
# Output: "true"

# Now monitoring commands will discover it
azlin w
azlin ps
azlin top
```

### Slow Discovery

**Symptom:** Monitoring commands take >3 seconds to discover VMs.

**Solutions:**

1. Check cache is enabled:
   ```bash
   grep "cache_ttl" ~/.azlin/config.toml
   # Should show: cache_ttl = 60
   ```

2. Reduce cache TTL if needed:
   ```toml
   [vm_discovery]
   cache_ttl = 30  # Faster refresh, more API calls
   ```

3. Disable fallback if all VMs have tags:
   ```toml
   [vm_discovery]
   use_name_prefix_fallback = false  # Skip fallback query
   ```

## Migration Guide

### From Name-Based to Tag-Based Discovery

If you have VMs created before tag-based discovery was implemented:

**Step 1: List all VMs**
```bash
azlin list --all
```

**Step 2: Add tags to all VMs**
```bash
# For each VM
az vm update --name VM_NAME --resource-group RESOURCE_GROUP \
  --set tags."azlin-managed"="true"
```

**Step 3: Verify tag-based discovery**
```bash
# Should show same VMs as azlin list
azlin w
azlin ps
azlin top
```

**Step 4: (Optional) Disable fallback**
```toml
# In ~/.azlin/config.toml
[vm_discovery]
use_name_prefix_fallback = false
```

## See Also

- [Monitoring Commands Reference](monitoring.md) - Complete monitoring documentation
- [Monitoring Quick Reference](monitoring-quick-reference.md) - Command cheat sheet
- [VM Tagging](../reference/vm-tagging.md) - VM tagging standards
- [Configuration Reference](../reference/configuration-reference.md) - Configuration options
