# azlin set

Set environment variable on VM.

ENV_VAR should be in format KEY=VALUE.


Examples:
    azlin env set my-vm DATABASE_URL="postgres://localhost/db"
    azlin env set my-vm API_KEY=secret123 --force
    azlin env set 20.1.2.3 NODE_ENV=production


## Description

Set environment variable on VM.
ENV_VAR should be in format KEY=VALUE.

Examples:
azlin env set my-vm DATABASE_URL="postgres://localhost/db"
azlin env set my-vm API_KEY=secret123 --force
azlin env set 20.1.2.3 NODE_ENV=production

## Usage

```bash
azlin set VM_IDENTIFIER ENV_VAR [OPTIONS]
```

## Arguments

- `VM_IDENTIFIER` - No description available
- `ENV_VAR` - No description available

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--force` - Skip secret detection warnings
