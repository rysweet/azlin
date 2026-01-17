# azlin status

Show status of VMs in resource group.

Displays detailed status information including power state and IP addresses.


Examples:
    azlin status
    azlin status --rg my-resource-group
    azlin status --vm my-vm


## Description

Show status of VMs in resource group.
Displays detailed status information including power state and IP addresses.

Examples:
azlin status
azlin status --rg my-resource-group
azlin status --vm my-vm

## Usage

```bash
azlin status [OPTIONS]
```

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--vm` TEXT (default: `Sentinel.UNSET`) - Show status for specific VM only
