# azlin destroy

Destroy a VM and optionally the entire resource group.

This is an alias for the 'kill' command with additional options.
Deletes the VM, NICs, disks, and public IPs.


Examples:
    azlin destroy azlin-vm-12345
    azlin destroy my-vm --dry-run
    azlin destroy my-vm --delete-rg --force
    azlin destroy my-vm --rg my-resource-group


## Description

Destroy a VM and optionally the entire resource group.
This is an alias for the 'kill' command with additional options.
Deletes the VM, NICs, disks, and public IPs.

Examples:
azlin destroy azlin-vm-12345
azlin destroy my-vm --dry-run
azlin destroy my-vm --delete-rg --force
azlin destroy my-vm --rg my-resource-group

## Usage

```bash
azlin destroy VM_NAME [OPTIONS]
```

## Arguments

- `VM_NAME` - No description available

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--force` - Skip confirmation prompt
- `--dry-run` - Show what would be deleted without actually deleting
- `--delete-rg` - Delete the entire resource group (use with caution)
