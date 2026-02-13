# Monitoring Custom-Named VMs

## Overview

This document provides examples of monitoring commands working with custom-named VMs, including the compound `hostname:session` naming format.

All examples assume VMs are properly tagged with `azlin-managed=true` (automatic for VMs created with azlin).

## Example Setup

### Create VMs with Custom Names

```bash
# Create VMs with various naming formats
azlin new --name myproject
azlin new --name api-server:prod
azlin new --name ml-trainer:experiment-1
azlin new --name devbox:alice
```

### List VMs

```bash
azlin list
```

**Output:**
```
VMs in resource group 'my-rg':
SESSION NAME         VM NAME                     STATUS    IP              REGION     SIZE
myproject            myproject                   Running   20.12.34.56     eastus     Standard_D2s_v3
api-server:prod      api-server:prod             Running   20.12.34.57     eastus     Standard_D4s_v3
ml-trainer:experi... ml-trainer:experiment-1     Running   20.12.34.58     westus2    Standard_NC6
devbox:alice         devbox:alice                Running   20.12.34.59     eastus     Standard_B2s
```

## Monitoring Commands with Custom Names

### `azlin w` - Who's Logged In

```bash
azlin w
```

**Output:**
```
=== VM: myproject (20.12.34.56) ===
 15:42:13 up  3:24,  1 user,  load average: 0.15, 0.12, 0.08
USER     TTY      FROM             LOGIN@   IDLE   JCPU   PCPU WHAT
azureuser pts/0   192.168.1.10     14:30    0.00s  0.03s  0.01s vim app.py

=== VM: api-server:prod (20.12.34.57) ===
 15:42:14 up  1 day,  6:15,  2 users,  load average: 1.23, 1.45, 1.38
USER     TTY      FROM             LOGIN@   IDLE   JCPU   PCPU WHAT
azureuser pts/0   192.168.1.11     09:00    0.00s  0.15s  0.08s node server.js
admin    pts/1   192.168.1.12     14:00    0.00s  0.02s  0.01s htop

=== VM: ml-trainer:experiment-1 (20.12.34.58) ===
 15:42:15 up  5:42,  1 user,  load average: 3.45, 3.23, 3.01
USER     TTY      FROM             LOGIN@   IDLE   JCPU   PCPU WHAT
azureuser pts/0   192.168.1.13     10:00    0.00s  2.45s  2.30s python train.py

=== VM: devbox:alice (20.12.34.59) ===
 15:42:16 up  12 min,  1 user,  load average: 0.05, 0.08, 0.04
USER     TTY      FROM             LOGIN@   IDLE   JCPU   PCPU WHAT
azureuser pts/0   192.168.1.14     15:30    0.00s  0.01s  0.00s bash
```

### `azlin ps` - Show Processes

```bash
azlin ps
```

**Output:**
```
=== VM: myproject (20.12.34.56) ===
USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
azureuser 1234  0.5  1.2  123456  6789 pts/0   S+   14:30   0:03 vim app.py
azureuser 5678  0.1  0.8   98765  4321 ?       S    12:00   0:01 tmux: server
root      9012  0.0  0.3   45678  2345 ?       S    09:00   0:00 /usr/sbin/sshd

=== VM: api-server:prod (20.12.34.57) ===
USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
azureuser 2345 28.5 15.2  987654 98765 pts/0   S+   09:00   4:15 node server.js
azureuser 6789  8.2  8.5  456789 45678 ?       S    09:00   1:23 redis-server
postgres  1011 12.3 25.1 1234567 123456 ?      S    08:00   2:45 postgres

=== VM: ml-trainer:experiment-1 (20.12.34.58) ===
USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
azureuser 3456 95.2 78.5 2048000 1024000 pts/0 R+   10:00   5:15 python train.py
azureuser 7890  0.8  0.5   12345   6789 ?      S    10:00   0:02 tmux: server

=== VM: devbox:alice (20.12.34.59) ===
USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
azureuser 4567  0.1  0.3   23456  1234 pts/0   S    15:30   0:00 bash
root      8901  0.0  0.2   34567  2345 ?       S    15:18   0:00 /usr/sbin/sshd
```

### `azlin top` - Real-Time Monitoring

```bash
azlin top --interval 5
```

**Output:**
```
╭─ Distributed Top - 2026-02-11 15:42:00 ─────────────────────────────╮
│                                                                      │
│ VM: myproject (20.12.34.56)                                          │
│   CPU:  0.5%  Memory:  1.2%  Load: 0.15, 0.12, 0.08                │
│   Status: ✓ Healthy                                                 │
│   Top Processes:                                                     │
│     vim app.py         -  0.5% CPU,  1.2% MEM                       │
│     tmux: server       -  0.1% CPU,  0.8% MEM                       │
│                                                                      │
│ VM: api-server:prod (20.12.34.57)                                    │
│   CPU: 48.5%  Memory: 48.8%  Load: 1.23, 1.45, 1.38                │
│   Status: ⚠️  High Load                                              │
│   Top Processes:                                                     │
│     node server.js     - 28.5% CPU, 15.2% MEM                       │
│     postgres           - 12.3% CPU, 25.1% MEM                       │
│     redis-server       -  8.2% CPU,  8.5% MEM                       │
│                                                                      │
│ VM: ml-trainer:experiment-1 (20.12.34.58)                            │
│   CPU: 95.2%  Memory: 78.5%  Load: 3.45, 3.23, 3.01                │
│   Status: 🔥 Maximum Utilization                                     │
│   Top Processes:                                                     │
│     python train.py    - 95.2% CPU, 78.5% MEM                       │
│     tmux: server       -  0.8% CPU,  0.5% MEM                       │
│                                                                      │
│ VM: devbox:alice (20.12.34.59)                                       │
│   CPU:  0.1%  Memory:  0.5%  Load: 0.05, 0.08, 0.04                │
│   Status: ✓ Idle                                                    │
│   Top Processes:                                                     │
│     bash               -  0.1% CPU,  0.3% MEM                       │
│     sshd               -  0.0% CPU,  0.2% MEM                       │
│                                                                      │
│ Next refresh in 5 seconds... (Press Ctrl+C to exit)                 │
╰──────────────────────────────────────────────────────────────────────╯
```

## Filtering by Resource Group

All monitoring commands support resource group filtering:

```bash
# Monitor only VMs in production resource group
azlin w --resource-group production-rg
azlin ps --resource-group production-rg
azlin top --resource-group production-rg
```

## Behind the Scenes: VM Discovery

All monitoring commands use the same tag-based discovery logic:

```python
# Pseudo-code for VM discovery
def discover_vms(resource_group=None):
    # Primary: Tag-based discovery
    vms = azure.vm.list(
        resource_group=resource_group,
        tag="azlin-managed=true"
    )

    # Fallback: Name-prefix (backward compatibility)
    if not vms:
        vms = azure.vm.list(
            resource_group=resource_group,
            name_prefix="azlin-"
        )

    return vms
```

This ensures consistent behavior across all monitoring commands, regardless of VM naming convention.

## Troubleshooting

### Custom-Named VMs Not Appearing

**Problem:** VMs with custom names don't appear in monitoring output.

**Solution:** Verify VMs have the `azlin-managed=true` tag:

```bash
# Check tag
az vm show --name "myhost:dev" --resource-group my-rg \
  --query "tags.\"azlin-managed\""

# Add tag if missing
az vm update --name "myhost:dev" --resource-group my-rg \
  --set tags."azlin-managed"="true"

# Verify monitoring commands now discover it
azlin w
```

### Only Some VMs Appear

**Problem:** Only VMs with "azlin-" prefix appear, custom-named VMs are missing.

**Root Cause:** Tag-based discovery is disabled or VMs are missing tags.

**Solution:**

1. Check configuration:
   ```bash
   grep "use_tags" ~/.azlin/config.toml
   # Should show: use_tags = true
   ```

2. Add tags to all custom-named VMs:
   ```bash
   # List all VMs
   azlin list --all

   # Add tag to each custom-named VM
   az vm update --name "myhost:dev" --resource-group my-rg \
     --set tags."azlin-managed"="true"
   ```

## See Also

- [VM Discovery for Monitoring Commands](../monitoring-commands-vm-discovery.md) - Complete VM discovery documentation
- [Monitoring Reference](../monitoring.md) - Full monitoring documentation
- [Compound VM Names](../../reference/compound-vm-names.md) - VM naming conventions
