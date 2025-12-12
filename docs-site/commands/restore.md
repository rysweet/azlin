# azlin restore

Restore a VM from a snapshot.

WARNING: This will stop the VM, delete the current OS disk, and replace it
with a disk created from the snapshot. All data on the current disk will be lost.


EXAMPLES:
    # Restore VM from a snapshot (with confirmation)
    $ azlin snapshot restore my-vm my-vm-snapshot-20251015-053000

    # Restore without confirmation
    $ azlin snapshot restore my-vm my-vm-snapshot-20251015-053000 --force


## Description

Restore a VM from a snapshot.
WARNING: This will stop the VM, delete the current OS disk, and replace it
with a disk created from the snapshot. All data on the current disk will be lost.

EXAMPLES:
# Restore VM from a snapshot (with confirmation)
$ azlin snapshot restore my-vm my-vm-snapshot-20251015-053000
# Restore without confirmation
$ azlin snapshot restore my-vm my-vm-snapshot-20251015-053000 --force

## Usage

```bash
azlin restore VM_NAME SNAPSHOT_NAME [OPTIONS]
```

## Arguments

- `VM_NAME` - No description available
- `SNAPSHOT_NAME` - No description available

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group name
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--force` - Skip confirmation prompt
