# Snapshot Commands

Manage VM snapshots and scheduled backups.

## Overview

Snapshot commands enable manual and scheduled backups of VM disks. Create point-in-time backups, restore VMs, and automate snapshot schedules.

## Available Commands

- [**azlin snapshot create**](create.md) - Create a snapshot of VM's OS disk
- [**azlin snapshot list**](list.md) - List all snapshots for a VM
- [**azlin snapshot restore**](restore.md) - Restore a VM from a snapshot
- [**azlin snapshot delete**](delete.md) - Delete a snapshot
- **azlin snapshot enable** - Enable scheduled snapshots (run `azlin snapshot enable --help`)
- **azlin snapshot disable** - Disable scheduled snapshots (run `azlin snapshot disable --help`)
- **azlin snapshot status** - Show snapshot schedule status (run `azlin snapshot status --help`)
- **azlin snapshot sync** - Sync snapshots for VMs with schedules (run `azlin snapshot sync --help`)

## Quick Start

### Manual Snapshots

```bash
# Create snapshot
azlin snapshot create my-vm

# List snapshots
azlin snapshot list my-vm

# Restore from snapshot
azlin snapshot restore my-vm my-vm-snapshot-20250124-120000
```

### Scheduled Snapshots

```bash
# Enable snapshots every 24 hours, keep 2
azlin snapshot enable my-vm --every 24 --keep 2

# Check status
azlin snapshot status my-vm

# Trigger sync manually
azlin snapshot sync --vm my-vm
```

## Use Cases

### Development Snapshots

```bash
# Before major changes
azlin snapshot create dev-vm

# Make changes
azlin connect dev-vm
# ... work ...

# If something breaks, restore
azlin snapshot restore dev-vm dev-vm-snapshot-20250124-120000
```

### Scheduled Backups

```bash
# Production VMs: daily backups, keep 7
azlin snapshot enable prod-vm --every 24 --keep 7

# Development VMs: weekly backups, keep 2
azlin snapshot enable dev-vm --every 168 --keep 2
```

## Related Commands

- [azlin clone](../vm/clone.md) - Clone VM (creates new VM with same data)
- [azlin status](../vm/status.md) - Check VM status

## See Also

- [Snapshots & Backups](../../snapshots/index.md)
- [Scheduled Backups](../../snapshots/scheduled.md)
