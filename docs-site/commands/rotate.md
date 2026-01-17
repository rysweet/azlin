# azlin rotate

Rotate SSH keys for all VMs in resource group.

Generates a new SSH key pair and updates all VMs to use the new key.
Automatically backs up old keys before rotation for safety.


Examples:
    azlin keys rotate
    azlin keys rotate --rg my-resource-group
    azlin keys rotate --all-vms
    azlin keys rotate --no-backup


## Description

Rotate SSH keys for all VMs in resource group.
Generates a new SSH key pair and updates all VMs to use the new key.
Automatically backs up old keys before rotation for safety.

Examples:
azlin keys rotate
azlin keys rotate --rg my-resource-group
azlin keys rotate --all-vms
azlin keys rotate --no-backup

## Usage

```bash
azlin rotate [OPTIONS]
```

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--all-vms` - Rotate keys for all VMs (not just azlin prefix)
- `--no-backup` - Skip backup before rotation
- `--vm-prefix` TEXT (default: `azlin`) - Only update VMs with this prefix
