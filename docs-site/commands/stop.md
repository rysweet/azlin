# azlin stop

Stop or deallocate a VM.

Stopping a VM with --deallocate (default) fully releases compute resources
and stops billing for the VM (storage charges still apply).


Examples:
    azlin stop my-vm
    azlin stop my-vm --rg my-resource-group
    azlin stop my-vm --no-deallocate


## Description

Stop or deallocate a VM.
Stopping a VM with --deallocate (default) fully releases compute resources
and stops billing for the VM (storage charges still apply).

Examples:
azlin stop my-vm
azlin stop my-vm --rg my-resource-group
azlin stop my-vm --no-deallocate

## Usage

```bash
azlin stop VM_NAME [OPTIONS]
```

## Arguments

- `VM_NAME` - No description available

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--deallocate` - Deallocate to save costs (default: yes)
