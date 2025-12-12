# azlin sync

Sync ~/.azlin/home/ to VM home directory.

Syncs local configuration files to remote VM for consistent
development environment.


Examples:
    azlin sync                    # Interactive VM selection
    azlin sync --vm-name myvm     # Sync to specific VM
    azlin sync --dry-run          # Show what would be synced


## Description

Sync ~/.azlin/home/ to VM home directory.
Syncs local configuration files to remote VM for consistent
development environment.

Examples:
azlin sync                    # Interactive VM selection
azlin sync --vm-name myvm     # Sync to specific VM
azlin sync --dry-run          # Show what would be synced

## Usage

```bash
azlin sync [OPTIONS]
```

## Options

- `--vm-name` TEXT (default: `Sentinel.UNSET`) - VM name to sync to
- `--dry-run` - Show what would be synced
- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
