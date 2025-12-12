# azlin disable

Disable scheduled snapshots for a VM.

Removes the snapshot schedule from the VM. Existing snapshots are not deleted.


Example:
    azlin snapshot disable my-vm


## Description

Disable scheduled snapshots for a VM.
Removes the snapshot schedule from the VM. Existing snapshots are not deleted.


## Usage

```bash
azlin disable VM_NAME [OPTIONS]
```

## Arguments

- `VM_NAME` - No description available

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
