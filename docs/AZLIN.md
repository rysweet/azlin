# azlin - Traditional Command Reference

> **For natural language commands**, see [AZDOIT.md](AZDOIT.md)

This document provides a comprehensive reference for all traditional azlin commands. These are the direct CLI commands that don't require AI or an API key.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [VM Lifecycle](#vm-lifecycle)
- [VM Maintenance](#vm-maintenance)
- [Connection](#connection)
- [Monitoring](#monitoring)
- [File Operations](#file-operations)
- [Shared Storage](#shared-storage)
- [Cost Management](#cost-management)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

### Installation

```bash
# Via uvx (no installation needed)
uvx --from git+https://github.com/rysweet/azlin azlin list

# Or install with uv
uv tool install git+https://github.com/rysweet/azlin

# Or with pip
pip install git+https://github.com/rysweet/azlin
```

### Prerequisites

- `az` (Azure CLI) - `brew install azure-cli`
- `gh` (GitHub CLI) - `brew install gh`
- `git`, `ssh`, `tmux`
- `uv` for installation
- Azure authentication: `az login`

### First Commands

```bash
# List your VMs
azlin list

# Create a new VM
azlin new

# Connect to a VM
azlin connect my-vm

# Get help
azlin --help
azlin new --help
```

---

## Installation

### Option 1: uvx (Zero-Install)

Run without installing:

```bash
# Any azlin command works
uvx --from git+https://github.com/rysweet/azlin azlin list
uvx --from git+https://github.com/rysweet/azlin azlin new
uvx --from git+https://github.com/rysweet/azlin azlin status

# Create an alias for convenience
alias azlin-git='uvx --from git+https://github.com/rysweet/azlin azlin'
azlin-git list
```

### Option 2: uv tool install (Recommended)

```bash
# Install azlin
uv tool install git+https://github.com/rysweet/azlin

# Now use azlin directly
azlin list
azlin new
```

### Option 3: pip install

```bash
# Create virtual environment
uv venv
source .venv/bin/activate

# Install with pip
pip install git+https://github.com/rysweet/azlin

# Use azlin
azlin list
```

---

## VM Lifecycle

### `azlin new` - Provision a new VM

Create a fresh Azure Ubuntu VM with all development tools pre-installed.

**Aliases**: `azlin vm`, `azlin create`

```bash
# Basic provisioning (interactive if VMs exist)
azlin new

# Provision with custom name
azlin new --name my-dev-vm

# Provision with GitHub repo clone
azlin new --repo https://github.com/microsoft/vscode

# Provision with shared NFS storage
azlin new --nfs-storage team-shared --name worker-1

# Specify VM size tier (s=8GB, m=64GB, l=128GB, xl=256GB)
azlin new --size s      # Small: 8GB RAM (original default)
azlin new --size m      # Medium: 64GB RAM
azlin new --size l      # Large: 128GB RAM (NEW DEFAULT)
azlin new --size xl     # Extra-large: 256GB RAM

# Or specify exact Azure VM size
azlin new --vm-size Standard_E8as_v5 --region westus2

# Provision without auto-connecting
azlin new --no-auto-connect

# Provision multiple VMs (pool)
azlin new --pool 5

# Custom resource group
azlin new --resource-group my-rg

# GPU-enabled VM
azlin new --name gpu-trainer --vm-size Standard_NC6
```

**Options**:
- `--name NAME` - VM name/session name
- `--repo URL` - Clone GitHub repository
- `--nfs-storage NAME` - Mount shared NFS storage
- `--size TIER` - VM size tier: s (8GB), m (64GB), l (128GB), xl (256GB) - default: l
- `--vm-size SIZE` - Exact Azure VM size (overrides --size) - default: Standard_E16as_v5
- `--region REGION` - Azure region (default: westus2)
- `--resource-group RG` - Resource group name
- `--pool N` - Create N VMs in parallel
- `--no-auto-connect` - Don't connect after creation
- `--no-update` - Skip tool updates

**What gets installed**:
- Docker, Azure CLI, GitHub CLI, Git
- Node.js, Python 3.13+, Rust, Golang, .NET 10
- GitHub Copilot CLI, OpenAI Codex CLI, Claude Code CLI
- tmux, vim, and essential utilities

**Default VM**: Size 'l' = Standard_E16as_v5 (128GB RAM, 16 vCPU, 12.5 Gbps network)
- Memory-optimized for development workloads
- Prevents swap thrashing and I/O bottlenecks
- Cost: ~$417/month pay-as-you-go, ~$209/month with 1-year Reserved Instance

**VM Size Tiers**:
- `--size s`: Small - 8GB RAM, 2 vCPU (~$70/month) - Original default
- `--size m`: Medium - 64GB RAM, 8 vCPU (~$363/month) - Good for most dev
- `--size l`: Large - 128GB RAM, 16 vCPU (~$417/month) - **NEW DEFAULT**
- `--size xl`: Extra-Large - 256GB RAM, 32 vCPU (~$1,144/month) - Heavy workloads

**Time**: 4-7 minutes

### `azlin clone` - Clone a VM with home directory

Clone existing VMs with their complete home directory contents.

```bash
# Clone single VM
azlin clone amplihack

# Clone with custom session name
azlin clone amplihack --session-prefix dev-env

# Clone multiple replicas
azlin clone amplihack --num-replicas 3 --session-prefix worker
# Creates: worker-1, worker-2, worker-3

# Clone with custom VM size
azlin clone my-vm --vm-size Standard_D4s_v3 --region westus2
```

**Options**:
- `--session-prefix PREFIX` - Prefix for cloned VM session names
- `--num-replicas N` - Number of clones to create
- `--vm-size SIZE` - VM size for clones
- `--region REGION` - Azure region for clones

**What gets cloned**:
- Entire home directory (`/home/azureuser/`)
- All files, configurations, and data
- Excludes: SSH keys, cloud credentials, .env files (security)

**Time**: 4-15 minutes depending on home directory size

### `azlin list` - List all VMs

```bash
# List VMs in default resource group
azlin list

# List VMs in specific resource group
azlin list --resource-group my-custom-rg
```

**Output**:
```
VMs in resource group 'azlin-rg-1234567890':
SESSION NAME         VM NAME                             STATUS          IP              REGION     SIZE
my-project           azlin-vm-001                        Running         20.12.34.56     eastus     Standard_D2s_v3
-                    azlin-vm-002                        Stopped         N/A             westus2    Standard_B2s
```

### `azlin session` - Manage session names

Session names are custom labels for VMs. They appear in `azlin list` and can be used to connect.

```bash
# Create VM with session name
azlin new --name my-project

# Set session name for existing VM
azlin session azlin-vm-12345 my-project

# View current session name
azlin session azlin-vm-12345

# Clear session name
azlin session azlin-vm-12345 --clear

# Connect using session name
azlin connect my-project
```

**Note**: Session names are stored locally in `~/.azlin/config.toml`

**Important**: Session names identify VMs (for connection), while tmux session names control which remote tmux session to connect to. By default, azlin connects to the "azlin" tmux session on the remote VM. Use `--tmux-session` to specify a different tmux session name.

### `azlin status` - Detailed VM status

```bash
# Show detailed status of all VMs
azlin status

# Status for specific resource group
azlin status --resource-group my-rg
```

**Shows**:
- Power state (Running/Stopped/Deallocated)
- Public IP address
- Location and VM size
- Uptime
- Cost estimates

### `azlin start` - Start a stopped VM

```bash
# Start a VM by name
azlin start my-vm

# Start VM in specific resource group
azlin start my-vm --resource-group my-rg
```

**Use case**: Resume work on a VM stopped to save costs overnight

### `azlin stop` - Stop/deallocate a VM

```bash
# Stop a VM to save costs
azlin stop my-vm

# Stop with resource group
azlin stop my-vm --resource-group my-rg
```

**Cost saving**: Stopped VMs only incur storage costs, not compute costs

### `azlin kill` - Delete a VM and its resources

```bash
# Delete a specific VM
azlin kill azlin-vm-12345

# Delete with confirmation
azlin kill my-vm --resource-group my-rg
```

**Deletes**:
- Virtual machine
- Network interface
- Public IP address
- OS disk
- (Resource group remains)

### `azlin destroy` - Advanced deletion with dry-run

```bash
# Preview what would be deleted (dry-run)
azlin destroy my-vm --dry-run

# Delete VM and show resources
azlin destroy my-vm

# Delete VM and entire resource group
azlin destroy my-vm --delete-rg

# Force deletion without prompts
azlin destroy my-vm --delete-rg --force
```

**Options**:
- `--dry-run` - Preview deletion without executing
- `--delete-rg` - Delete entire resource group
- `--force` - Skip confirmation prompts

### `azlin killall` - Delete all VMs in resource group

```bash
# Delete all VMs (with confirmation)
azlin killall

# Delete all in specific resource group
azlin killall --resource-group my-rg

# Force delete all
azlin killall --force
```

**Warning**: This deletes ALL VMs in the resource group!

---

## VM Maintenance

### `azlin update` - Update development tools

Update all programming tools and AI CLI tools installed during provisioning.

```bash
# Update tools on a VM by session name
azlin update my-project

# Update tools on a VM by name
azlin update azlin-vm-12345 --resource-group my-rg

# Update with longer timeout (default 300s)
azlin update my-vm --timeout 600
```

**What gets updated**:
- Node.js packages (npm, AI CLI tools)
- Python packages (pip, uv, astral-uv)
- Rust toolchain (rustup)
- Go toolchain
- Docker, GitHub CLI, Azure CLI

**Time**: 2-5 minutes

### `azlin os-update` - Update Ubuntu packages

Run system package updates (apt update && apt upgrade).

```bash
# Update OS packages by session name
azlin os-update my-project

# Update by VM name
azlin os-update azlin-vm-12345 --resource-group my-rg

# Update with longer timeout (default 300s)
azlin os-update my-vm --timeout 600
```

**What happens**:
1. `sudo apt update` - Refresh package lists
2. `sudo apt upgrade -y` - Install updates (non-interactive)

**Time**: 30 seconds to 10 minutes

**Best practice**: Run monthly or before major deployments

---

## Connection

### `azlin connect` - SSH into a VM

Connect with automatic tmux session management and auto-reconnect.

```bash
# Connect to a VM by name
azlin connect my-vm

# Connect by session name
azlin connect my-project

# Connect by IP address
azlin connect 20.12.34.56

# Connect to specific tmux session
# Note: By default, connects to existing "azlin" tmux session
# Use --tmux-session to specify a different session
azlin connect my-vm --tmux-session work

# Connect without tmux
azlin connect my-vm --no-tmux

# Specify SSH user
azlin connect my-vm --ssh-user azureuser

# Connect with custom key
azlin connect my-vm --ssh-key ~/.ssh/custom_key

# Disable auto-reconnect
azlin connect my-vm --no-reconnect
```

**Auto-Reconnect Feature**:

If your SSH session disconnects, azlin automatically prompts to reconnect:

```
Your session to my-vm was disconnected, do you want to reconnect? [Y|n]: y
Attempting to reconnect to my-vm...
[Reconnected successfully]
```

**Options**:
- `--tmux-session NAME` - Connect to specific tmux session
- `--no-tmux` - Skip tmux, connect directly
- `--ssh-user USER` - SSH username (default: azureuser)
- `--ssh-key PATH` - SSH key file
- `--no-reconnect` - Disable auto-reconnect

---

## Monitoring

### `azlin w` - Show who's logged in

Run `w` command on all VMs to see active users and processes.

```bash
# Run 'w' on all VMs
azlin w

# Run on specific resource group
azlin w --resource-group my-rg
```

**Output**:
```
=== VM: my-vm (20.12.34.56) ===
 12:34:56 up  2:15,  1 user,  load average: 0.52, 0.58, 0.59
USER     TTY      FROM             LOGIN@   IDLE   JCPU   PCPU WHAT
azureuser pts/0   192.168.1.1      10:30    0.00s  0.04s  0.00s w
```

### `azlin ps` - Show running processes

Run `ps aux` on all VMs to see all processes.

```bash
# Show all processes on all VMs
azlin ps

# Show on specific resource group
azlin ps --resource-group my-rg
```

**Use cases**:
- Find runaway processes
- Monitor resource usage
- Debug performance issues

---

## File Operations

### `azlin cp` - Copy files to/from VMs

Bidirectional file transfer with security validation.

```bash
# Copy local file to VM
azlin cp report.pdf my-vm:~/documents/

# Copy from VM to local
azlin cp my-vm:~/results.tar.gz ./

# Copy directory recursively
azlin cp -r ./my-project/ my-vm:~/workspace/

# Preview transfer (dry-run)
azlin cp --dry-run large-dataset.zip my-vm:~/

# Copy between VMs
azlin cp vm1:~/data.csv vm2:~/backup/
```

**Security**: Automatically blocks transfer of:
- SSH keys (`.ssh/`, `id_rsa`, etc.)
- Cloud credentials (`.aws/`, `.azure/`, etc.)
- Environment files (`.env`, `.env.*`)
- Secrets (`*.pem`, `*.key`, `credentials.json`)

**Options**:
- `-r` - Recursive copy for directories
- `--dry-run` - Preview without copying

### `azlin sync` - Sync dotfiles from ~/.azlin/home/

Automatically sync configuration files to all VMs.

```bash
# Sync dotfiles to all VMs
azlin sync

# Sync to specific VM
azlin sync --vm-name my-vm

# Preview what would be synced
azlin sync --dry-run

# Sync to specific resource group
azlin sync --resource-group my-rg
```

**Setup**:
```bash
# Place your dotfiles in ~/.azlin/home/
mkdir -p ~/.azlin/home
cp ~/.bashrc ~/.vimrc ~/.gitconfig ~/.azlin/home/
```

**Auto-sync**: Dotfiles are automatically synced:
- After VM provisioning
- On first login
- When you run `azlin sync`

**Use cases**:
- Consistent shell configuration
- Share vim/emacs settings
- Distribute git configuration

---

## Shared Storage

Share home directories across multiple VMs using Azure Files NFS.

### Quick Start

```bash
# Create shared storage
azlin storage create myteam-shared --size 100 --tier Premium

# Provision VMs with shared home directory
azlin new --nfs-storage myteam-shared --name worker-1
azlin new --nfs-storage myteam-shared --name worker-2

# Or mount on existing VMs
azlin storage mount myteam-shared --vm existing-vm
```

### Commands

#### `azlin storage create` - Create NFS storage

```bash
# Create storage account with NFS share
azlin storage create myteam-shared --size 100 --tier Premium

# Create with Standard tier (cheaper)
azlin storage create backup-storage --size 500 --tier Standard
```

**Options**:
- `--size SIZE` - Size in GB (default: 100)
- `--tier TIER` - Premium or Standard (default: Premium)
- `--region REGION` - Azure region (default: same as VMs)
- `--resource-group RG` - Resource group

**Cost**:
- Premium: $0.153/GB/month (100GB = ~$15.30/mo)
- Standard: $0.0184/GB/month (100GB = ~$1.84/mo)

#### `azlin storage list` - List storage accounts

```bash
# List all storage accounts
azlin storage list

# List in specific resource group
azlin storage list --resource-group my-rg
```

#### `azlin storage status` - Check storage details

```bash
# Show usage and connected VMs
azlin storage status myteam-shared

# Status for specific resource group
azlin storage status myteam-shared --resource-group my-rg
```

#### `azlin storage mount` - Mount storage on existing VM

```bash
# Mount storage on VM (replaces home directory)
azlin storage mount myteam-shared --vm my-dev-vm

# Mount with resource group
azlin storage mount myteam-shared --vm my-vm --resource-group my-rg
```

**What happens**:
1. Existing home directory backed up
2. NFS share mounted to `/home/azureuser`
3. Your `~/.azlin/home` contents copied to shared storage (if any)

#### `azlin storage unmount` - Unmount storage

```bash
# Unmount storage (restores local home)
azlin storage unmount --vm my-dev-vm

# Unmount with resource group
azlin storage unmount --vm my-vm --resource-group my-rg
```

**What happens**:
1. NFS share unmounted
2. Local home directory restored from backup

#### `azlin storage delete` - Delete storage

```bash
# Delete storage account
azlin storage delete myteam-shared

# Delete with confirmation
azlin storage delete myteam-shared --resource-group my-rg
```

**Warning**: This deletes the storage account and all data!

### Use Cases

- **Team Collaboration**: Multiple developers in same environment
- **Seamless Switching**: Move between VMs without losing work
- **Consistent Tools**: Same configs and tools across all VMs
- **Multi-VM Workflows**: Different tasks, shared data
- **Distributed Computing**: Multiple workers accessing shared datasets

---

## Cost Management

### `azlin cost` - Track VM spending

Monitor Azure VM costs with detailed breakdowns.

```bash
# Show total costs for all VMs
azlin cost

# Break down costs by VM
azlin cost --by-vm

# Show costs for specific date range
azlin cost --from 2025-01-01 --to 2025-01-31

# Combine options
azlin cost --by-vm --from 2025-01-01 --to 2025-01-31

# Specific resource group
azlin cost --resource-group my-rg
```

**Output**:
```
Cost Summary (2025-01-01 to 2025-01-31):
  Total: $247.50

  By VM:
    azlin-vm-001 (Standard_D2s_v3): $142.00
    azlin-vm-002 (Standard_B2s):     $105.50
```

**Options**:
- `--by-vm` - Show per-VM breakdown
- `--from DATE` - Start date (YYYY-MM-DD)
- `--to DATE` - End date (YYYY-MM-DD)
- `--resource-group RG` - Specific resource group

**Cost-Saving Tip**: Use `azlin stop` when not using VMs!

---

## Configuration

### Configuration File

Set defaults in `~/.azlin/config.toml`:

```toml
default_resource_group = "my-dev-rg"
default_region = "westus2"
default_vm_size = "Standard_D4s_v3"
```

Then commands use these defaults:

```bash
# Uses defaults from config
azlin new

# Override defaults
azlin new --region eastus --vm-size Standard_B2s
```

### Common Configuration Options

**Resource Group**:
```bash
# Set default
echo 'default_resource_group = "my-rg"' >> ~/.azlin/config.toml

# Or use --resource-group flag
azlin new --resource-group my-rg
```

**Region**:
```bash
# Set default
echo 'default_region = "westus2"' >> ~/.azlin/config.toml

# Or use --region flag
azlin new --region eastus
```

**VM Size**:
```bash
# Set default
echo 'default_vm_size = "Standard_D4s_v3"' >> ~/.azlin/config.toml

# Or use --vm-size flag
azlin new --vm-size Standard_NC6
```

---

## Advanced Usage

### Command Passthrough

Execute commands on VMs without creating persistent sessions.

```bash
# Execute command on running VM (opens in new terminal)
azlin -- python train.py

# Execute on new VM
azlin new -- ./run_tests.sh

# With VM selection (if multiple VMs exist)
azlin -- nvidia-smi
```

**Use cases**:
- Run one-off commands
- CI/CD pipelines
- Remote script execution
- Automated testing

### Working with Multiple Resource Groups

```bash
# List VMs across different resource groups
azlin list --resource-group team-1
azlin list --resource-group team-2

# Provision in specific group
azlin new --resource-group experiments --name test-vm

# Connect to VM in specific group
azlin connect test-vm --resource-group experiments
```

---

## Common Workflows

### Daily Development

```bash
# Morning: Start your VM
azlin start my-dev-vm
azlin connect my-dev-vm

# Work...

# Evening: Stop to save costs
azlin stop my-dev-vm
```

**Cost savings**: ~50% reduction vs. running 24/7

### Team Onboarding

```bash
# Create identical VMs for team members
azlin new --name alice-vm --repo https://github.com/company/project
azlin new --name bob-vm --repo https://github.com/company/project

# Or use pool
azlin new --pool 3 --repo https://github.com/company/project
```

### GPU Model Training

```bash
# Create GPU VM
azlin new --name gpu-trainer \
  --vm-size Standard_NC6 \
  --repo https://github.com/openai/whisper

# Monitor training
azlin connect gpu-trainer
azlin ps  # Check GPU usage

# When done, stop to save costs
azlin stop gpu-trainer
```

### Experimentation

```bash
# Create test VM
azlin new --name experiment-1

# Try things...

# Preview deletion
azlin destroy experiment-1 --dry-run

# Delete everything
azlin destroy experiment-1 --delete-rg
```

### Resource Cleanup

Safe cleanup workflow:

```bash
# Step 1: List what you have
azlin list

# Step 2: Preview deletion
azlin destroy test-vm --dry-run

# Step 3: Delete specific VM
azlin destroy test-vm

# Step 4: Verify cleanup
azlin list
```

**Bulk cleanup**:
```bash
# Delete all VMs in resource group (with confirmation)
azlin killall

# Force delete all without prompts
azlin killall --force

# Delete resource group entirely
azlin destroy my-vm --delete-rg
```

---

## Troubleshooting

### Common Issues

#### Can't connect to VM

```bash
# Check if VM is running
azlin status

# Start if stopped
azlin start my-vm

# Verify SSH key
ls -la ~/.ssh/azlin-*

# Test direct SSH
ssh -i ~/.ssh/azlin-key azureuser@<ip-address>
```

#### Connection drops frequently

- Auto-reconnect feature will prompt you
- Check network stability
- Use tmux for persistence (default)

#### VM is slow

```bash
# Check for resource-heavy processes
azlin ps

# Consider larger VM size
azlin destroy my-vm
azlin new --name my-vm --vm-size Standard_D4s_v3
```

#### Tool updates fail

```bash
# Try with longer timeout
azlin update my-vm --timeout 600

# Check VM connectivity
azlin connect my-vm

# Manual update
azlin connect my-vm
npm update -g
pip install --upgrade pip uv
```

#### Storage mount fails

```bash
# Check storage exists
azlin storage list

# Check storage status
azlin storage status my-storage

# Verify VM connectivity
azlin connect my-vm

# Check mount logs
azlin connect my-vm
sudo journalctl -u nfs-mount
```

### Debugging

**Verbose mode**:
```bash
# Most commands support --verbose
azlin new --name test-vm --verbose
azlin connect my-vm --verbose
```

**Check Azure resources**:
```bash
# Using Azure CLI
az vm list --output table
az vm show --name azlin-vm-123 --resource-group my-rg

# Check costs
az consumption usage list --output table
```

**Logs**:
```bash
# Check azlin config
cat ~/.azlin/config.toml

# Check session names
cat ~/.azlin/config.toml | grep session

# Azure CLI logs
cat ~/.azure/az.log
```

---

## Quick Reference

| Command | Purpose | Example |
|---------|---------|---------|
| `azlin new` | Create VM | `azlin new --repo URL` |
| `azlin clone` | Clone VM + home | `azlin clone vm --num-replicas 3` |
| `azlin list` | List VMs | `azlin list` |
| `azlin status` | Detailed status | `azlin status` |
| `azlin connect` | SSH to VM | `azlin connect my-vm` |
| `azlin start` | Start stopped VM | `azlin start my-vm` |
| `azlin stop` | Stop VM (save $) | `azlin stop my-vm` |
| `azlin kill` | Delete VM | `azlin kill my-vm` |
| `azlin destroy` | Advanced delete | `azlin destroy --dry-run` |
| `azlin killall` | Delete all VMs | `azlin killall` |
| `azlin update` | Update dev tools | `azlin update my-vm` |
| `azlin os-update` | Update Ubuntu | `azlin os-update my-vm` |
| `azlin session` | Manage names | `azlin session vm-123 my-name` |
| `azlin w` | Who's logged in | `azlin w` |
| `azlin ps` | Show processes | `azlin ps` |
| `azlin cp` | Copy files | `azlin cp file vm:~/` |
| `azlin sync` | Sync dotfiles | `azlin sync` |
| `azlin storage create` | Create NFS storage | `azlin storage create name --size 100` |
| `azlin storage list` | List storage | `azlin storage list` |
| `azlin storage status` | Storage details | `azlin storage status name` |
| `azlin storage mount` | Mount storage | `azlin storage mount name --vm vm` |
| `azlin storage unmount` | Unmount storage | `azlin storage unmount --vm vm` |
| `azlin storage delete` | Delete storage | `azlin storage delete name` |
| `azlin cost` | Track spending | `azlin cost --by-vm` |

---

## Tips & Best Practices

### Cost Optimization

1. **Stop VMs when not in use**: `azlin stop vm-name`
2. **Use B-series for dev**: `--vm-size Standard_B2s` (burstable, cheaper)
3. **Delete unused VMs**: `azlin destroy vm-name --delete-rg`
4. **Track spending**: `azlin cost --by-vm`
5. **Use Standard storage for backups**: Cheaper than Premium

### Security

1. **Never commit VM keys**: azlin stores keys in `~/.ssh/`
2. **Use ssh-agent**: Keys are managed securely
3. **Rotate keys regularly**: Delete and recreate VMs periodically
4. **Review `.azlin/home/`**: Don't sync secrets
5. **Use NFS within VNet**: Storage not publicly accessible

### Productivity

1. **Set aliases**: `alias azdev='azlin connect my-dev-vm'`
2. **Use tmux sessions**: Work persists across disconnects
3. **Sync dotfiles**: Consistent environment everywhere
4. **Use pools**: Parallel testing across multiple VMs
5. **Use session names**: Easier to identify VMs

### Performance

1. **Choose appropriate VM sizes**: Start small, scale up if needed
2. **Use Standard storage for archives**: Premium for active development
3. **Stop VMs during idle times**: Start them when needed
4. **Use shared storage**: Avoid copying large datasets
5. **Clone VMs**: Faster than provisioning from scratch

---

## Support

### Documentation

- [README.md](../README.md) - Project overview
- [AZDOIT.md](AZDOIT.md) - Natural language commands
- [STORAGE_README.md](STORAGE_README.md) - Shared storage details

### Getting Help

```bash
# Command help
azlin --help
azlin new --help
azlin storage --help

# GitHub Issues
# https://github.com/rysweet/azlin/issues
```

### Contributing

- Follow the brick philosophy
- Write tests for new features
- Update documentation
- Run pre-commit hooks

---

## License

See [LICENSE](../LICENSE) for details.

---

Last Updated: 2025-10-21
Version: 2.1.0
