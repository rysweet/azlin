# azlin batch sync

Batch sync home directory to multiple VMs simultaneously.

## Synopsis

```bash
azlin batch sync [OPTIONS]
```

## Description

Sync `~/.azlin/home/` to multiple VMs in parallel. Filter VMs by tags, name patterns, or sync to all VMs. Supports dry-run mode for safety.

## Options

| Option | Description |
|--------|-------------|
| `--tag TEXT` | Filter VMs by tag (format: key=value) |
| `--vm-pattern TEXT` | Filter VMs by name pattern (glob) |
| `--all` | Select all VMs in resource group |
| `--resource-group, --rg TEXT` | Resource group |
| `--config PATH` | Config file path |
| `--max-workers INTEGER` | Maximum parallel workers (default: 10) |
| `--dry-run` | Show what would be synced without syncing |
| `-h, --help` | Show help message |

## Examples

### Sync to All VMs

```bash
# Sync to every VM
azlin batch sync --all

# Dry-run first
azlin batch sync --all --dry-run
```

### Filter by Tag

```bash
# Sync to development VMs
azlin batch sync --tag 'env=dev'

# Sync to web servers
azlin batch sync --tag 'app=web'
```

### Filter by Pattern

```bash
# Sync to VMs matching pattern
azlin batch sync --vm-pattern 'web-*'

# Sync to production VMs
azlin batch sync --vm-pattern '*-prod'
```

### Specific Resource Group

```bash
# Sync in specific resource group
azlin batch sync --all --rg production-rg
```

### Parallelism Control

```bash
# More parallel workers
azlin batch sync --all --max-workers 20

# Sequential (one at a time)
azlin batch sync --all --max-workers 1
```

## Use Cases

### Team Onboarding

```bash
# Set up development environment files
mkdir -p ~/.azlin/home/.config
cp ~/.vimrc ~/.azlin/home/
cp ~/.bashrc ~/.azlin/home/
cp -r ~/.config/nvim ~/.azlin/home/.config/

# Sync to all VMs
azlin batch sync --all
```

### Configuration Distribution

```bash
# Update config across fleet
cp new-config.yaml ~/.azlin/home/.myapp/config.yaml

# Sync to production
azlin batch sync --tag 'env=prod'
```

### Code Deployment

```bash
# Copy code to sync directory
cp -r ~/myproject ~/.azlin/home/projects/

# Sync to development VMs
azlin batch sync --tag 'env=dev'
```

### Environment Setup

```bash
# Prepare home directory
mkdir -p ~/.azlin/home/{bin,scripts,.config}
cp ~/useful-scripts/* ~/.azlin/home/scripts/

# Sync to all new VMs
azlin batch sync --all
```

## What Gets Synced

### Source Directory

```
~/.azlin/home/
├── .bashrc           # Shell configuration
├── .vimrc            # Editor config
├── .config/          # Application configs
├── scripts/          # Utility scripts
└── projects/         # Code and projects
```

### Destination on VMs

Synced to: `/home/azureuser/`

Files maintain:
- Permissions
- Timestamps
- Directory structure

### Security Filters

**Not synced:**
- `.ssh/` directory
- Private keys
- `.env` files with secrets
- `.git/` directories (optional)

## Output

### Summary Mode (Default)

```bash
$ azlin batch sync --all
```

**Output:**
```
Syncing to 3 VMs...

✓ web-01: Synced 15 files (2.3 MB) in 3.2s
✓ web-02: Synced 15 files (2.3 MB) in 3.5s
✓ web-03: Synced 15 files (2.3 MB) in 3.1s

3/3 succeeded
Total: 45 files, 6.9 MB in 3.5s
```

### Dry-Run Mode

```bash
$ azlin batch sync --all --dry-run
```

**Output:**
```
DRY-RUN MODE - No files will be transferred

Would sync to 3 VMs:
  - web-01
  - web-02
  - web-03

Files to sync:
  .bashrc (2.1 KB)
  .vimrc (1.5 KB)
  scripts/deploy.sh (3.2 KB)
  projects/myapp/... (2.3 MB)

Total: 15 files, 2.3 MB per VM
```

## Performance

| Workers | Speed (3 VMs) | Best For |
|---------|---------------|----------|
| 1 | 15s | Controlled sync |
| 10 (default) | 5s | General use |
| 20 | 3s | Large fleets |

Actual speed depends on:
- File sizes
- Network bandwidth
- VM locations
- Number of VMs

## Comparison with Other Sync Methods

| Method | Use Case | Speed | Granularity |
|--------|----------|-------|-------------|
| `azlin batch sync` | Multiple VMs | Fast (parallel) | All files |
| `azlin sync` | Single VM | Medium | All files |
| `azlin cp` | Specific files | Slow | Per-file |
| `azlin batch command 'git pull'` | Git repos | Fastest | Repository |

## Best Practices

### Always Dry-Run First

```bash
# Check what will be synced
azlin batch sync --all --dry-run

# Then sync
azlin batch sync --all
```

### Organize Sync Directory

```
~/.azlin/home/
├── common/           # Files for all VMs
├── dev/              # Development-specific
└── prod/             # Production-specific
```

### Use Tags for Environment-Specific Sync

```bash
# Development configs
azlin batch sync --tag 'env=dev'

# Production configs
azlin batch sync --tag 'env=prod'
```

### Control Parallelism for Large Syncs

```bash
# Large files: fewer workers
azlin batch sync --all --max-workers 5

# Small files: more workers
azlin batch sync --all --max-workers 20
```

## Troubleshooting

### No VMs Selected

```bash
# Check available VMs
azlin list

# Verify tags
azlin list --tag 'env=dev'

# Check pattern
azlin list | grep 'web-*'
```

### Sync Failures

```bash
# Test single VM first
azlin sync test-vm

# Check VM connectivity
azlin w

# Verify SSH access
azlin connect test-vm
```

### Permission Errors

```bash
# Check source directory permissions
ls -la ~/.azlin/home/

# Ensure files are readable
chmod -R u+r ~/.azlin/home/
```

### Slow Sync

```bash
# Reduce parallelism
azlin batch sync --all --max-workers 5

# Check file sizes
du -sh ~/.azlin/home/

# Remove large files
rm ~/.azlin/home/large-file.bin
```

## Related Commands

- [azlin sync](../util/sync.md) - Sync to single VM
- [azlin cp](../util/cp.md) - Copy specific files
- [azlin batch command](command.md) - Execute commands on VMs
- [azlin clone](../vm/clone.md) - Clone VM with home directory

## See Also

- [Home Directory Sync](../../file-transfer/sync.md)
- [Fleet Management](../fleet/index.md)
- [Fleet Management](../../batch/fleet.md)
