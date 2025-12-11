# azlin prune

Prune inactive VMs based on age and idle time.

Identifies and optionally deletes VMs that are:
- Older than --age-days (default: 1)
- Idle for longer than --idle-days (default: 1)
- Stopped/deallocated (unless --include-running)
- Without named sessions (unless --include-named)


Examples:
    azlin prune --dry-run                    # Preview what would be deleted
    azlin prune                              # Delete VMs idle for 1+ days (default)
    azlin prune --age-days 7 --idle-days 3   # Custom thresholds
    azlin prune --force                      # Skip confirmation
    azlin prune --include-running            # Include running VMs


## Description

Prune inactive VMs based on age and idle time.
Identifies and optionally deletes VMs that are:
- Older than --age-days (default: 1)
- Idle for longer than --idle-days (default: 1)
- Stopped/deallocated (unless --include-running)
- Without named sessions (unless --include-named)

Examples:
azlin prune --dry-run                    # Preview what would be deleted
azlin prune                              # Delete VMs idle for 1+ days (default)
azlin prune --age-days 7 --idle-days 3   # Custom thresholds
azlin prune --force                      # Skip confirmation
azlin prune --include-running            # Include running VMs

## Usage

```bash
azlin prune [OPTIONS]
```

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--age-days` TEXT (default: `1`) - Age threshold in days (default: 1)
- `--idle-days` TEXT (default: `1`) - Idle threshold in days (default: 1)
- `--dry-run` - Preview without deleting
- `--force` - Skip confirmation prompt
- `--include-running` - Include running VMs
- `--include-named` - Include named sessions
