# azlin kill

Delete a VM and all associated resources.

Deletes the VM, NICs, disks, and public IPs.


Examples:
    azlin kill azlin-vm-12345
    azlin kill my-vm --rg my-resource-group
    azlin kill my-vm --force


## Description

Delete a VM and all associated resources.
Deletes the VM, NICs, disks, and public IPs.

Examples:
azlin kill azlin-vm-12345
azlin kill my-vm --rg my-resource-group
azlin kill my-vm --force

## Usage

```bash
azlin kill VM_NAME [OPTIONS]
```

## Arguments

- `VM_NAME` - No description available

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--force` - Skip confirmation prompt
