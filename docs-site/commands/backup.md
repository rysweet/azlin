# azlin backup

Backup current SSH keys.

Creates a timestamped backup of current SSH keys.


Examples:
    azlin keys backup
    azlin keys backup --destination ~/backups/


## Description

Backup current SSH keys.
Creates a timestamped backup of current SSH keys.

Examples:
azlin keys backup
azlin keys backup --destination ~/backups/

## Usage

```bash
azlin backup [OPTIONS]
```

## Options

- `--destination` PATH (default: `Sentinel.UNSET`) - Backup destination (default: ~/.azlin/key_backups/)
