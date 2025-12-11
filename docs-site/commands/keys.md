# azlin keys

SSH key management and rotation.

Manage SSH keys across Azure VMs with rotation, backup, and export functionality.


## Description

SSH key management and rotation.
Manage SSH keys across Azure VMs with rotation, backup, and export functionality.

## Usage

```bash
azlin keys
```

## Subcommands

### backup

Backup current SSH keys.

Creates a timestamped backup of current SSH keys.


Examples:
    azlin keys backup
    azlin keys backup --destination ~/backups/


**Usage:**
```bash
azlin keys backup [OPTIONS]
```

**Options:**
- `--destination` - Backup destination (default: ~/.azlin/key_backups/)

### export

Export current SSH public key to file.

Exports the azlin SSH public key to a specified file.


Examples:
    azlin keys export --output ~/my-keys/azlin.pub
    azlin keys export --output ./keys.txt


**Usage:**
```bash
azlin keys export [OPTIONS]
```

**Options:**
- `--output` - Output file path

### list

List VMs and their SSH public keys.

Shows which SSH public key is configured on each VM.


Examples:
    azlin keys list
    azlin keys list --rg my-resource-group
    azlin keys list --all-vms


**Usage:**
```bash
azlin keys list [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--all-vms` - List all VMs (not just azlin prefix)
- `--vm-prefix` - Only list VMs with this prefix

### rotate

Rotate SSH keys for all VMs in resource group.

Generates a new SSH key pair and updates all VMs to use the new key.
Automatically backs up old keys before rotation for safety.


Examples:
    azlin keys rotate
    azlin keys rotate --rg my-resource-group
    azlin keys rotate --all-vms
    azlin keys rotate --no-backup


**Usage:**
```bash
azlin keys rotate [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--all-vms` - Rotate keys for all VMs (not just azlin prefix)
- `--no-backup` - Skip backup before rotation
- `--vm-prefix` - Only update VMs with this prefix
