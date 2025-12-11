# azlin killall

Delete all VMs in resource group.

Deletes all VMs matching the prefix and their associated resources.


Examples:
    azlin killall
    azlin killall --rg my-resource-group
    azlin killall --prefix test-vm
    azlin killall --force


## Description

Delete all VMs in resource group.
Deletes all VMs matching the prefix and their associated resources.

Examples:
azlin killall
azlin killall --rg my-resource-group
azlin killall --prefix test-vm
azlin killall --force

## Usage

```bash
azlin killall [OPTIONS]
```

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--force` - Skip confirmation prompt
- `--prefix` TEXT (default: `azlin`) - Only delete VMs with this prefix
