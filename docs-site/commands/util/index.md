# Utility Commands

Utility and helper commands for VM management and monitoring.

## Overview

Utility commands provide helpful tools for monitoring, updating, file operations, and system administration across your VM fleet.

## Available Commands

### Monitoring

- [**azlin w**](w.md) - Run 'w' command on all VMs (who's logged in)
- [**azlin ps**](ps.md) - Run 'ps aux' on all VMs (process listing)
- [**azlin top**](top.md) - Real-time distributed system monitoring
- [**azlin cost**](cost.md) - Show cost estimates for VMs

### File Operations

- [**azlin sync**](sync.md) - Sync ~/.azlin/home/ to VM home directory
- [**azlin cp**](cp.md) - Copy files between local machine and VMs

### VM Maintenance

- [**azlin update**](update.md) - Update all development tools on a VM
- [**azlin os-update**](os-update.md) - Update OS packages on a VM
- [**azlin prune**](prune.md) - Prune inactive VMs based on age and idle time

### Development Tools

- [**azlin code**](code.md) - Launch VS Code with Remote-SSH for a VM
- [**azlin help**](help.md) - Show help for commands

## Quick Start

### Monitoring

```bash
# Who's logged in
azlin w

# Running processes
azlin ps

# Real-time monitoring
azlin top

# Cost estimates
azlin cost --by-vm
```

### File Operations

```bash
# Sync files to VM
azlin sync my-vm

# Copy specific files
azlin cp local-file.txt my-vm:~/remote-file.txt
azlin cp my-vm:~/data.json ./local-data.json
```

### Maintenance

```bash
# Update development tools
azlin update my-vm

# Update OS packages
azlin os-update my-vm

# Clean up old VMs
azlin prune --older-than 30 --dry-run
```

## Related Commands

- [Batch Commands](../batch/index.md) - Multi-VM operations
- [Fleet Management](../fleet/index.md) - Distributed operations

## See Also

- [Monitoring](../../monitoring/index.md)
- [Copy Command](../../file-transfer/copy.md)
