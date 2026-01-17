# azlin ps

Run 'ps aux' command on all VMs.

Shows running processes on each VM. Output is prefixed with [vm-name].
SSH processes are automatically filtered out.


Examples:
    azlin ps
    azlin ps --rg my-resource-group
    azlin ps --grouped


## Description

Run 'ps aux' command on all VMs.
Shows running processes on each VM. Output is prefixed with [vm-name].
SSH processes are automatically filtered out.

Examples:
azlin ps
azlin ps --rg my-resource-group
azlin ps --grouped

## Usage

```bash
azlin ps [OPTIONS]
```

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--grouped` - Group output by VM instead of prefixing
