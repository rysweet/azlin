# azlin batch

Batch operations on multiple VMs.

Execute operations on multiple VMs simultaneously using
tag-based selection, pattern matching, or all VMs.


Examples:
    azlin batch stop --tag 'env=dev'
    azlin batch start --vm-pattern 'test-*'
    azlin batch command 'git pull' --all
    azlin batch sync --tag 'env=dev'


## Description

Batch operations on multiple VMs.
Execute operations on multiple VMs simultaneously using
tag-based selection, pattern matching, or all VMs.

Examples:
azlin batch stop --tag 'env=dev'
azlin batch start --vm-pattern 'test-*'
azlin batch command 'git pull' --all
azlin batch sync --tag 'env=dev'

## Usage

```bash
azlin batch
```

## Subcommands

### command

Execute command on multiple VMs.

Execute a shell command on multiple VMs simultaneously.


Examples:
    azlin batch command 'git pull' --tag 'env=dev'
    azlin batch command 'df -h' --vm-pattern 'web-*'
    azlin batch command 'uptime' --all --show-output


**Usage:**
```bash
azlin batch command COMMAND [OPTIONS]
```

**Options:**
- `--tag` - Filter VMs by tag (format: key=value)
- `--vm-pattern` - Filter VMs by name pattern (glob)
- `--all` - Select all VMs in resource group
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--max-workers` - Maximum parallel workers (default: 10)
- `--timeout` - Command timeout in seconds (default: 300)
- `--show-output` - Show command output from each VM

### start

Batch start VMs.

Start multiple stopped/deallocated VMs simultaneously.


Examples:
    azlin batch start --tag 'env=dev'
    azlin batch start --vm-pattern 'test-*'
    azlin batch start --all --confirm


**Usage:**
```bash
azlin batch start [OPTIONS]
```

**Options:**
- `--tag` - Filter VMs by tag (format: key=value)
- `--vm-pattern` - Filter VMs by name pattern (glob)
- `--all` - Select all VMs in resource group
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--max-workers` - Maximum parallel workers (default: 10)
- `--confirm` - Skip confirmation prompt

### stop

Batch stop/deallocate VMs.

Stop multiple VMs simultaneously. By default, VMs are deallocated
to stop billing for compute resources.


Examples:
    azlin batch stop --tag 'env=dev'
    azlin batch stop --vm-pattern 'test-*'
    azlin batch stop --all --confirm


**Usage:**
```bash
azlin batch stop [OPTIONS]
```

**Options:**
- `--tag` - Filter VMs by tag (format: key=value)
- `--vm-pattern` - Filter VMs by name pattern (glob)
- `--all` - Select all VMs in resource group
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--deallocate` - Deallocate to save costs (default: yes)
- `--max-workers` - Maximum parallel workers (default: 10)
- `--confirm` - Skip confirmation prompt

### sync

Batch sync home directory to VMs.

Sync ~/.azlin/home/ to multiple VMs simultaneously.


Examples:
    azlin batch sync --tag 'env=dev'
    azlin batch sync --vm-pattern 'web-*'
    azlin batch sync --all --dry-run


**Usage:**
```bash
azlin batch sync [OPTIONS]
```

**Options:**
- `--tag` - Filter VMs by tag (format: key=value)
- `--vm-pattern` - Filter VMs by name pattern (glob)
- `--all` - Select all VMs in resource group
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--max-workers` - Maximum parallel workers (default: 10)
- `--dry-run` - Show what would be synced without syncing
