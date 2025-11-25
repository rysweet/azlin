# VM Management Commands

Core VM lifecycle and management operations.

## Overview

VM commands handle the complete lifecycle of Azure VMs - from provisioning to deletion, including configuration, monitoring, and maintenance.

## Available Commands

### Lifecycle Management

- [**azlin new**](new.md) - Provision new Azure VM with development tools
- [**azlin clone**](clone.md) - Clone VM with home directory contents
- [**azlin start**](start.md) - Start a stopped or deallocated VM
- [**azlin stop**](stop.md) - Stop/deallocate VM to save costs
- [**azlin kill**](../util/kill.md) - Delete VM and all associated resources
- [**azlin destroy**](destroy.md) - Delete VM with dry-run and resource group options

### Connection & Access

- [**azlin connect**](connect.md) - SSH to VM with tmux session management
- [**azlin code**](../util/code.md) - Launch VS Code with Remote-SSH

### Information & Status

- [**azlin list**](list.md) - List VMs in resource group
- [**azlin status**](status.md) - Show detailed status of VMs
- [**azlin session**](session.md) - Set or view session name for a VM

### Configuration

- [**azlin tag**](tag.md) - Manage Azure VM tags
- [**azlin update**](../util/update.md) - Update all development tools on VM
- [**azlin os-update**](../util/os-update.md) - Update OS packages

## Quick Start

### Create and Connect

```bash
# Create VM
azlin new --name my-dev-vm

# Connect with SSH
azlin connect my-dev-vm

# Or open in VS Code
azlin code my-dev-vm
```

### List and Manage

```bash
# List all VMs
azlin list

# Show detailed status
azlin status

# Stop VM to save costs
azlin stop my-dev-vm
```

### Clone VMs

```bash
# Clone for team member
azlin clone dev-base --session-prefix alice

# Clone multiple
azlin clone template --num-replicas 3 --session-prefix worker
```

## Related Topics

- [Batch Operations](../batch/index.md) - Multi-VM operations
- [Snapshot Management](../snapshot/index.md) - VM backups
- [Storage Management](../storage/index.md) - Shared storage

## See Also

- [Quick Start](../../getting-started/quickstart.md)
- [VM Lifecycle](../../vm-lifecycle/index.md)
