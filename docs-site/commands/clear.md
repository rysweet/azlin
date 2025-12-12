# azlin clear

Clear all environment variables from VM.


Examples:
    azlin env clear my-vm
    azlin env clear my-vm --force


## Description

Clear all environment variables from VM.

Examples:
azlin env clear my-vm
azlin env clear my-vm --force

## Usage

```bash
azlin clear VM_IDENTIFIER [OPTIONS]
```

## Arguments

- `VM_IDENTIFIER` - No description available

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--force` - Skip confirmation prompt
