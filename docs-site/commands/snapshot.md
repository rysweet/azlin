# azlin snapshot

Manage VM snapshots and scheduled backups.

Enable scheduled snapshots, sync snapshots manually, or manage snapshot schedules.


EXAMPLES:
    # Enable scheduled snapshots (every 24 hours, keep 2)
    $ azlin snapshot enable my-vm --every 24

    # Enable with custom retention (every 12 hours, keep 5)
    $ azlin snapshot enable my-vm --every 12 --keep 5

    # Sync snapshots now (checks all VMs with schedules)
    $ azlin snapshot sync

    # Sync specific VM
    $ azlin snapshot sync --vm my-vm

    # Disable scheduled snapshots
    $ azlin snapshot disable my-vm

    # Show snapshot schedule
    $ azlin snapshot status my-vm


## Description

Manage VM snapshots and scheduled backups.
Enable scheduled snapshots, sync snapshots manually, or manage snapshot schedules.

EXAMPLES:
# Enable scheduled snapshots (every 24 hours, keep 2)
$ azlin snapshot enable my-vm --every 24
# Enable with custom retention (every 12 hours, keep 5)
$ azlin snapshot enable my-vm --every 12 --keep 5
# Sync snapshots now (checks all VMs with schedules)
$ azlin snapshot sync
# Sync specific VM
$ azlin snapshot sync --vm my-vm
# Disable scheduled snapshots
$ azlin snapshot disable my-vm
# Show snapshot schedule
$ azlin snapshot status my-vm

## Usage

```bash
azlin snapshot
```

## Subcommands

### create

Create a snapshot of a VM's OS disk.

Creates a point-in-time snapshot of the VM's OS disk for backup purposes.
Snapshots are automatically named with timestamps.


EXAMPLES:
    # Create snapshot using default resource group
    $ azlin snapshot create my-vm

    # Create snapshot with specific resource group
    $ azlin snapshot create my-vm --rg my-resource-group


**Usage:**
```bash
azlin snapshot create VM_NAME [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group name
- `--config` - Config file path

### delete

Delete a snapshot.

Permanently deletes a snapshot to free up storage and reduce costs.


EXAMPLES:
    # Delete a snapshot (with confirmation)
    $ azlin snapshot delete my-vm-snapshot-20251015-053000

    # Delete without confirmation
    $ azlin snapshot delete my-vm-snapshot-20251015-053000 --force


**Usage:**
```bash
azlin snapshot delete SNAPSHOT_NAME [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group name
- `--config` - Config file path
- `--force` - Skip confirmation prompt

### disable

Disable scheduled snapshots for a VM.

Removes the snapshot schedule from the VM. Existing snapshots are not deleted.


Example:
    azlin snapshot disable my-vm


**Usage:**
```bash
azlin snapshot disable VM_NAME [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path

### enable

Enable scheduled snapshots for a VM.

Configures the VM to take snapshots every N hours, keeping only the most recent snapshots.
Schedule is stored in VM tags and triggered by `azlin snapshot sync`.


Examples:
    azlin snapshot enable my-vm --every 24          # Daily, keep 2
    azlin snapshot enable my-vm --every 12 --keep 5 # Every 12h, keep 5


**Usage:**
```bash
azlin snapshot enable VM_NAME [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--every` - Snapshot interval in hours (e.g., 24 for daily)
- `--keep` - Number of snapshots to keep (default: 2)

### list

List all snapshots for a VM.

Shows all snapshots created for the specified VM, sorted by creation time.


EXAMPLES:
    # List snapshots for a VM
    $ azlin snapshot list my-vm

    # List snapshots with specific resource group
    $ azlin snapshot list my-vm --rg my-resource-group


**Usage:**
```bash
azlin snapshot list VM_NAME [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group name
- `--config` - Config file path

### restore

Restore a VM from a snapshot.

WARNING: This will stop the VM, delete the current OS disk, and replace it
with a disk created from the snapshot. All data on the current disk will be lost.


EXAMPLES:
    # Restore VM from a snapshot (with confirmation)
    $ azlin snapshot restore my-vm my-vm-snapshot-20251015-053000

    # Restore without confirmation
    $ azlin snapshot restore my-vm my-vm-snapshot-20251015-053000 --force


**Usage:**
```bash
azlin snapshot restore VM_NAME SNAPSHOT_NAME [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group name
- `--config` - Config file path
- `--force` - Skip confirmation prompt

### status

Show snapshot schedule status for a VM.


Example:
    azlin snapshot status my-vm


**Usage:**
```bash
azlin snapshot status VM_NAME [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path

### sync

Sync snapshots for VMs with schedules.

Checks all VMs (or specific VM) and creates snapshots if needed based on their schedules.
Old snapshots beyond retention count are automatically deleted (FIFO).

This is the main command to run periodically (e.g., via cron) to trigger snapshot creation.


Examples:
    azlin snapshot sync                # Sync all VMs
    azlin snapshot sync --vm my-vm     # Sync specific VM


**Usage:**
```bash
azlin snapshot sync [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--vm` - Sync specific VM only
