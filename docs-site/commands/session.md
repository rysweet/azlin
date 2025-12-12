# azlin session

Set or view session name for a VM.

Session names are labels that help you identify what you're working on.
They appear in the 'azlin list' output alongside the VM name.


Examples:
    # Set session name
    azlin session azlin-vm-12345 my-project

    # View current session name
    azlin session azlin-vm-12345

    # Clear session name
    azlin session azlin-vm-12345 --clear


## Description

Set or view session name for a VM.
Session names are labels that help you identify what you're working on.
They appear in the 'azlin list' output alongside the VM name.

Examples:
# Set session name
azlin session azlin-vm-12345 my-project
# View current session name
azlin session azlin-vm-12345
# Clear session name
azlin session azlin-vm-12345 --clear

## Usage

```bash
azlin session VM_NAME [SESSION_NAME] [OPTIONS]
```

## Arguments

- `VM_NAME` - No description available
- `SESSION_NAME` - No description available (optional)

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--clear` - Clear session name
