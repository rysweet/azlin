# azlin os-update

Update OS packages on a VM.

Runs 'apt update && apt upgrade -y' on Ubuntu VMs to update all packages.

VM_IDENTIFIER can be:
- Session name (resolved to VM)
- VM name (requires --resource-group or default config)
- IP address (direct connection)


Examples:
    azlin os-update my-session
    azlin os-update azlin-myvm --rg my-resource-group
    azlin os-update 20.1.2.3
    azlin os-update my-vm --timeout 600  # 10 minute timeout


## Description

Update OS packages on a VM.
Runs 'apt update && apt upgrade -y' on Ubuntu VMs to update all packages.
VM_IDENTIFIER can be:
- Session name (resolved to VM)
- VM name (requires --resource-group or default config)
- IP address (direct connection)

Examples:
azlin os-update my-session
azlin os-update azlin-myvm --rg my-resource-group
azlin os-update 20.1.2.3
azlin os-update my-vm --timeout 600  # 10 minute timeout

## Usage

```bash
azlin os-update VM_IDENTIFIER [OPTIONS]
```

## Arguments

- `VM_IDENTIFIER` - No description available

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--timeout` INT (default: `300`) - Timeout in seconds (default 300)
