# azlin sync

Automatically sync dotfiles and configuration from `~/.azlin/home/` to all azlin VMs.

## Description

The `azlin sync` command synchronizes your local configuration files to VMs, ensuring consistent development environments across all VMs. Place dotfiles in `~/.azlin/home/` and they're automatically distributed to VMs on provisioning, first login, or manual sync.

**Security:** Automatically blocks SSH keys, credentials, `.env` files, and other secrets.

## Usage

```bash
azlin sync [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--vm-name TEXT` | Sync to specific VM only |
| `--dry-run` | Preview files that would be synced |
| `--force` | Skip confirmation prompts |
| `--resource-group, --rg TEXT` | Azure resource group |
| `-h, --help` | Show help message |

## Examples

### Sync to All VMs (Default)

```bash
azlin sync
```

**Output:**
```
Syncing dotfiles to all VMs...

Source: ~/.azlin/home/
VMs found: 3

Syncing to azlin-vm-001 (20.12.34.56)...
  .bashrc -> /home/azureuser/.bashrc
  .vimrc -> /home/azureuser/.vimrc
  .gitconfig -> /home/azureuser/.gitconfig
  ✓ Synced (3 files, 12.4 KB)

✓ Sync complete!
  VMs synced: 3
  Total files: 9
```

### Sync to Specific VM

```bash
azlin sync --vm-name my-dev-vm
```

### Preview Sync (Dry Run)

```bash
azlin sync --dry-run
```

## Setup

```bash
# 1. Create sync directory
mkdir -p ~/.azlin/home

# 2. Copy dotfiles
cp ~/.bashrc ~/.vimrc ~/.gitconfig ~/.tmux.conf ~/.azlin/home/

# 3. Sync to VMs
azlin sync
```

## Auto-Sync Events

Dotfiles automatically sync:
- On VM provisioning (`azlin new`)
- On first SSH connection
- Manual sync (`azlin sync`)

## Security Filters

Automatically blocks:
- SSH keys (`.ssh/`, `id_rsa`, `*.pem`)
- Cloud credentials (`.aws/`, `.azure/`)
- Secrets (`.env`, `credentials.json`)

## Common Workflows

### Team Configuration

```bash
# Share team dotfiles via Git
git clone https://github.com/company/team-dotfiles.git ~/.azlin/home
azlin sync
```

### Custom Scripts

```bash
# Add scripts to sync
mkdir -p ~/.azlin/home/scripts
echo '#!/bin/bash\necho "Hello from script"' > ~/.azlin/home/scripts/hello.sh
chmod +x ~/.azlin/home/scripts/hello.sh

# Sync to VMs
azlin sync

# Available on all VMs
azlin connect any-vm
~/scripts/hello.sh
```

## Troubleshooting

**Files not syncing:**
```bash
# Verify files exist
ls -la ~/.azlin/home/

# Check for blocked files
azlin sync --dry-run

# Force sync
azlin sync --force
```

## Performance

| Files | VMs | Time |
|-------|-----|------|
| 5 dotfiles | 5 VMs | 10s |
| 10 dotfiles | 10 VMs | 30s |
| 20 dotfiles | 20 VMs | 60s |

## Related Commands

- [`azlin cp`](cp.md) - Copy specific files
- [`azlin new`](../vm/new.md) - Provision VM (auto-syncs)
- [`azlin env set`](../env/set.md) - Set environment variables

## See Also

- [Dotfiles Management](../../file-transfer/dotfiles.md)
- [Authentication Profiles](../../authentication/profiles.md)
