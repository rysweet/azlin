# azlin command

Execute command on multiple VMs.

Execute a shell command on multiple VMs simultaneously.


Examples:
    azlin batch command 'git pull' --tag 'env=dev'
    azlin batch command 'df -h' --vm-pattern 'web-*'
    azlin batch command 'uptime' --all --show-output


## Description

Execute command on multiple VMs.
Execute a shell command on multiple VMs simultaneously.

Examples:
azlin batch command 'git pull' --tag 'env=dev'
azlin batch command 'df -h' --vm-pattern 'web-*'
azlin batch command 'uptime' --all --show-output

## Usage

```bash
azlin command COMMAND [OPTIONS]
```

## Arguments

- `COMMAND` - No description available

## Options

- `--tag` TEXT (default: `Sentinel.UNSET`) - Filter VMs by tag (format: key=value)
- `--vm-pattern` TEXT (default: `Sentinel.UNSET`) - Filter VMs by name pattern (glob)
- `--all` - Select all VMs in resource group
- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--max-workers` INT (default: `10`) - Maximum parallel workers (default: 10)
- `--timeout` INT (default: `300`) - Command timeout in seconds (default: 300)
- `--show-output` - Show command output from each VM
