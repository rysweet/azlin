# azlin enable

Enable scheduled snapshots for a VM.

Configures the VM to take snapshots every N hours, keeping only the most recent snapshots.
Schedule is stored in VM tags and triggered by `azlin snapshot sync`.


Examples:
    azlin snapshot enable my-vm --every 24          # Daily, keep 2
    azlin snapshot enable my-vm --every 12 --keep 5 # Every 12h, keep 5


## Description

Enable scheduled snapshots for a VM.
Configures the VM to take snapshots every N hours, keeping only the most recent snapshots.
Schedule is stored in VM tags and triggered by `azlin snapshot sync`.

Examples:
azlin snapshot enable my-vm --every 24          # Daily, keep 2
azlin snapshot enable my-vm --every 12 --keep 5 # Every 12h, keep 5

## Usage

```bash
azlin enable VM_NAME [OPTIONS]
```

## Arguments

- `VM_NAME` - No description available

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--every` INT (default: `Sentinel.UNSET`) **[required]** - Snapshot interval in hours (e.g., 24 for daily)
- `--keep` INT (default: `2`) - Number of snapshots to keep (default: 2)
