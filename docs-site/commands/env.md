# azlin env

Manage environment variables on VMs.

Commands to set, list, delete, and export environment variables
stored in ~/.bashrc on remote VMs.


Examples:
    azlin env set my-vm DATABASE_URL="postgres://localhost/db"
    azlin env list my-vm
    azlin env delete my-vm API_KEY
    azlin env export my-vm prod.env


## Description

Manage environment variables on VMs.
Commands to set, list, delete, and export environment variables
stored in ~/.bashrc on remote VMs.

Examples:
azlin env set my-vm DATABASE_URL="postgres://localhost/db"
azlin env list my-vm
azlin env delete my-vm API_KEY
azlin env export my-vm prod.env

## Usage

```bash
azlin env
```

## Subcommands

### clear

Clear all environment variables from VM.


Examples:
    azlin env clear my-vm
    azlin env clear my-vm --force


**Usage:**
```bash
azlin env clear VM_IDENTIFIER [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--force` - Skip confirmation prompt

### delete

Delete environment variable from VM.


Examples:
    azlin env delete my-vm API_KEY
    azlin env delete 20.1.2.3 DATABASE_URL


**Usage:**
```bash
azlin env delete VM_IDENTIFIER KEY [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path

### export

Export environment variables to .env file format.


Examples:
    azlin env export my-vm prod.env
    azlin env export my-vm  # Print to stdout


**Usage:**
```bash
azlin env export VM_IDENTIFIER OUTPUT_FILE [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path

### import

Import environment variables from .env file.


Examples:
    azlin env import my-vm .env
    azlin env import my-vm prod.env


**Usage:**
```bash
azlin env import VM_IDENTIFIER ENV_FILE [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path

### list

List environment variables on VM.


Examples:
    azlin env list my-vm
    azlin env list my-vm --show-values
    azlin env list 20.1.2.3


**Usage:**
```bash
azlin env list VM_IDENTIFIER [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--show-values` - Show full values (default: masked)

### set

Set environment variable on VM.

ENV_VAR should be in format KEY=VALUE.


Examples:
    azlin env set my-vm DATABASE_URL="postgres://localhost/db"
    azlin env set my-vm API_KEY=secret123 --force
    azlin env set 20.1.2.3 NODE_ENV=production


**Usage:**
```bash
azlin env set VM_IDENTIFIER ENV_VAR [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--force` - Skip secret detection warnings
