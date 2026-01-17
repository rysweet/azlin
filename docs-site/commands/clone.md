# azlin clone

Clone a VM with its home directory contents.

Creates new VM(s) and copies the entire home directory from the source VM.
Useful for creating development environments, parallel testing, or team onboarding.


Examples:
    # Clone single VM
    azlin clone amplihack

    # Clone with custom session name
    azlin clone amplihack --session-prefix dev-env

    # Clone multiple replicas
    azlin clone amplihack --num-replicas 3 --session-prefix worker
    # Creates: worker-1, worker-2, worker-3

    # Clone with specific VM size
    azlin clone my-vm --vm-size Standard_D4s_v3

The source VM can be specified by VM name or session name.
Home directory security filters are applied (no SSH keys, credentials, etc.).


## Description

Clone a VM with its home directory contents.
Creates new VM(s) and copies the entire home directory from the source VM.
Useful for creating development environments, parallel testing, or team onboarding.

Examples:
# Clone single VM
azlin clone amplihack
# Clone with custom session name
azlin clone amplihack --session-prefix dev-env
# Clone multiple replicas
azlin clone amplihack --num-replicas 3 --session-prefix worker
# Creates: worker-1, worker-2, worker-3
# Clone with specific VM size
azlin clone my-vm --vm-size Standard_D4s_v3
The source VM can be specified by VM name or session name.
Home directory security filters are applied (no SSH keys, credentials, etc.).

## Usage

```bash
azlin clone SOURCE_VM [OPTIONS]
```

## Arguments

- `SOURCE_VM` - No description available

## Options

- `--num-replicas` INT (default: `1`) - Number of clones to create (default: 1)
- `--session-prefix` TEXT (default: `Sentinel.UNSET`) - Session name prefix for clones
- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--vm-size` TEXT (default: `Sentinel.UNSET`) - VM size for clones (default: same as source)
- `--region` TEXT (default: `Sentinel.UNSET`) - Azure region (default: same as source)
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
