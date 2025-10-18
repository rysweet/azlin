# azlin - Azure Ubuntu VM Provisioning CLI

**One command to create a fully-equipped development VM on Azure**

```bash

# Run directly from GitHub (no installation needed)
uvx --from git+https://github.com/rysweet/azlin azlin new

# Create VM with dev tools
azlin new

# Create VM and clone GitHub repo
azlin new --repo https://github.com/owner/repo
```

## What is azlin?

azlin automates the tedious process of setting up Azure Ubuntu VMs for development. In one command, it:

1. Authenticates with Azure
2. Provisions an Ubuntu 24.04 VM
3. Installs 12 essential development tools
4. Sets up SSH with key-based authentication
5. Starts a persistent tmux session
6. Optionally clones a GitHub repository

**Total time**: 4-7 minutes from command to working development environment.

## Development Tools Installed

Every azlin VM comes pre-configured with:

1. **Docker** - Container runtime
2. **Azure CLI (az)** - Azure management
3. **GitHub CLI (gh)** - GitHub integration
4. **Git** - Version control
5. **Node.js** - JavaScript runtime with user-local npm configuration
6. **Python 3.12+** - Python runtime + pip (latest stable version from deadsnakes PPA)
7. **Rust** - Systems programming language
8. **Golang** - Go programming language
9. **.NET 10 RC** - .NET development framework
10. **GitHub Copilot CLI** - AI-powered coding assistant
11. **OpenAI Codex CLI** - AI code generation
12. **Claude Code CLI** - AI coding assistant

### AI CLI Tools

Three AI-powered coding assistants are pre-installed and ready to use:

- **GitHub Copilot CLI** (`@github/copilot`) - AI pair programmer from GitHub
- **OpenAI Codex CLI** (`@openai/codex`) - Advanced AI code generation
- **Claude Code CLI** (`@anthropic-ai/claude-code`) - Anthropic's AI coding assistant

These tools are installed using npm's user-local configuration, so they're immediately available in your PATH without requiring sudo permissions.

### npm User-Local Configuration

Node.js is configured for user-local global package installations, which means:
- Install global npm packages **without sudo**: `npm install -g package-name`
- Packages are installed to `~/.npm-packages`
- Automatic PATH and MANPATH configuration
- Clean separation from system Node.js packages

## Prerequisites

Before using azlin, ensure these tools are installed:

- `az` (Azure CLI)
- `gh` (GitHub CLI)
- `git`
- `ssh`
- `tmux`
- `uv`
- `python`

**macOS**: `brew install azure-cli gh git tmux`
**Linux**: See platform-specific installation in Prerequisites module

## Quick Start

### Getting Help

```bash
# Show all available commands
azlin

# Or use the help flag
azlin --help

# Get help for specific commands
azlin new --help
azlin list --help
```

### Option 1: Zero-Install with uvx (Recommended for Trying)

Run azlin instantly without installation using [uvx](https://docs.astral.sh/uv/concepts/tools/):

```bash
# Run directly from GitHub (no installation needed)
uvx --from git+https://github.com/rysweet/azlin azlin list

# Provision a VM
uvx --from git+https://github.com/rysweet/azlin azlin new

# Clone a repo on the VM
uvx --from git+https://github.com/rysweet/azlin azlin new --repo https://github.com/microsoft/vscode

# Any azlin command works
uvx --from git+https://github.com/rysweet/azlin azlin status
```

**Tip**: For shorter commands, set an alias:
```bash
alias azlin-git='uvx --from git+https://github.com/rysweet/azlin azlin'
azlin-git list
```

### Option 2: Install with uv (Recommended)

```bash
# Install azlin using uv (fastest)
uv tool install azlin

# Or install from GitHub
uv tool install git+https://github.com/rysweet/azlin

# Now use azlin commands
azlin list
azlin --help
```

### Option 3: Install with pip

```bash
# Create and activate virtual environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install azlin
uv pip install azlin

# Or use regular pip
pip install azlin

# Create a development VM
azlin new

# Create VM and clone a repo
azlin new --repo https://github.com/microsoft/vscode

# Sync your dotfiles to existing VMs
azlin sync

# Copy files to/from VMs
azlin cp myfile.txt vm1:~/
azlin cp vm1:~/data.txt ./
```

### Home Directory Sync

Automatically sync your configuration files from `~/.azlin/home/` to all VMs:

```bash
# Setup: Place your dotfiles in ~/.azlin/home/
mkdir -p ~/.azlin/home
cp ~/.bashrc ~/.vimrc ~/.gitconfig ~/.azlin/home/

# Auto-syncs on VM creation and login
azlin new  # Dotfiles automatically synced after provisioning

# Manual sync to specific VM
azlin sync --vm-name my-vm

# Preview what would be synced
azlin sync --dry-run
```

**Security**: Automatically blocks SSH keys, cloud credentials, .env files, and other secrets.

### Bidirectional File Transfer

Copy files between your local machine and VMs:

```bash
# Copy local file to VM
azlin cp report.pdf vm1:~/documents/

# Copy from VM to local
azlin cp vm1:~/results.tar.gz ./

# Preview transfer
azlin cp --dry-run large-dataset.zip vm1:~/
```
# Comprehensive Command Reference

This section provides detailed examples of all azlin commands with practical use cases.

## Command Categories

- [VM Lifecycle](#vm-lifecycle) - Create, manage, and delete VMs
- [VM Maintenance](#vm-maintenance) - Update tools and packages
- [Connection](#connection) - Connect to VMs
- [Monitoring](#monitoring) - Monitor VM status and processes
- [File Operations](#file-operations) - Transfer and sync files
- [Storage & NFS](#storage--nfs) - Shared storage and NFS mounts (NEW)
- [Cost Management](#cost-management) - Track spending

---

## VM Lifecycle

### Creating VMs

#### `azlin new` - Provision a new VM

Create a fresh Azure Ubuntu VM with all development tools pre-installed.

**Aliases**: `azlin vm`, `azlin create`

```bash
# Basic provisioning (interactive if VMs exist)
azlin new

# Provision with custom name
azlin new --name my-dev-vm

# Provision with GitHub repo clone
azlin new --repo https://github.com/microsoft/vscode

# Specify VM size and region
azlin new --vm-size Standard_D4s_v3 --region westus2

# Provision without auto-connecting
azlin new --no-auto-connect

# Provision multiple VMs in parallel (pool)
azlin new --pool 5

# Provision with custom resource group
azlin new --resource-group my-rg

# Combine options
azlin new --name gpu-trainer --vm-size Standard_NC6 --repo https://github.com/openai/whisper
```

**Use cases**:
- Quick development environment setup
- Testing across multiple VM instances
- GPU-enabled model training
- Team onboarding (everyone gets identical setup)

#### `azlin clone` - Clone a VM with home directory

Clone existing VMs with their complete home directory contents.

```bash
# Clone single VM
azlin clone amplihack

# Clone with custom session name
azlin clone amplihack --session-prefix dev-env

# Clone multiple replicas for parallel testing
azlin clone amplihack --num-replicas 3 --session-prefix worker
# Creates: worker-1, worker-2, worker-3

# Clone with custom VM size and region
azlin clone my-vm --vm-size Standard_D4s_v3 --region westus2
```

**What gets cloned**:
- Entire home directory (`/home/azureuser/`)
- All files, configurations, and data
- Excludes: SSH keys, cloud credentials, .env files (security filters)

**Use cases**:
- Create development environments from a "golden" VM
- Parallel testing across identical VMs
- Team onboarding with pre-configured setups
- Experiment with different configurations without affecting original

**Performance**:
- VMs provision in parallel (3-5 minutes regardless of replica count)
- Home directories copy in parallel (1-10 minutes depending on size)
- Total time: ~4-15 minutes

#### `azlin list` - List all VMs

```bash
# List VMs in default resource group
azlin list

# List VMs in specific resource group
azlin list --resource-group my-custom-rg
```

**Output example**:
```
VMs in resource group 'azlin-rg-1234567890':
SESSION NAME         VM NAME                             STATUS          IP              REGION     SIZE      
my-project           azlin-vm-001                        Running         20.12.34.56     eastus     Standard_D2s_v3
-                    azlin-vm-002                        Stopped         N/A             westus2    Standard_B2s
```

#### `azlin session` - Manage session names

Session names are custom labels you can assign to VMs to help identify what you're working on. They appear in the `azlin list` output and make it easier to track multiple projects. You can also use session names to connect to VMs.

```bash
# Create a new VM with a session name
azlin new --name my-project

# Set a session name for an existing VM
azlin session azlin-vm-12345 my-project

# View current session name
azlin session azlin-vm-12345

# Clear session name
azlin session azlin-vm-12345 --clear

# Connect using session name
azlin connect my-project
```

Session names are stored locally in `~/.azlin/config.toml` and don't affect the actual VM name in Azure.

#### `azlin status` - Detailed VM status

```bash
# Show detailed status of all VMs
azlin status

# Status for specific resource group
azlin status --resource-group my-rg
```

**Shows**:
- Power state (Running/Stopped/Deallocated)
- Public IP address
- Location
- VM size
- Uptime
- Cost estimates

#### `azlin start` - Start a stopped VM

```bash
# Start a VM by name
azlin start my-vm

# Start VM in specific resource group
azlin start my-vm --resource-group my-rg
```

**Use case**: Resume work on a VM you stopped to save costs overnight.

#### `azlin stop` - Stop/deallocate a VM

```bash
# Stop a VM to save costs
azlin stop my-vm

# Stop with resource group
azlin stop my-vm --resource-group my-rg
```

**💰 Cost saving**: Stopped VMs only incur storage costs, not compute costs.

#### `azlin kill` - Delete a VM and its resources

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

#### `azlin destroy` - Advanced deletion with dry-run

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

**Use cases**:
- Safe deletion with preview
- Complete cleanup including resource group
- Scripted deletion workflows

#### `azlin killall` - Delete all VMs in resource group

```bash
# Delete all VMs (with confirmation)
azlin killall

# Delete all in specific resource group
azlin killall --resource-group my-rg

# Force delete all
azlin killall --force
```

⚠️ **Warning**: This deletes ALL VMs in the resource group!

---

## VM Maintenance

### `azlin update` - Update development tools on a VM

Update all programming tools and AI CLI tools that were installed during VM provisioning.

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
- Docker
- GitHub CLI
- Azure CLI

**Use cases**:
- Keep development environments up-to-date
- Apply security patches to dev tools
- Get latest AI CLI features
- Synchronize tool versions across VMs

**Performance**: Updates typically complete in 2-5 minutes depending on available updates.

### `azlin os-update` - Update Ubuntu packages

Run system package updates on Ubuntu VMs (apt update && apt upgrade).

```bash
# Update OS packages by session name
azlin os-update my-project

# Update by VM name
azlin os-update azlin-vm-12345 --resource-group my-rg

# Update with longer timeout (default 300s)
azlin os-update my-vm --timeout 600
```

**What happens**:
1. Runs `sudo apt update` to refresh package lists
2. Runs `sudo apt upgrade -y` to install available updates
3. Non-interactive mode (auto-accepts prompts)

**Use cases**:
- Apply Ubuntu security patches
- Keep system packages current
- Maintenance before important deployments
- Regular maintenance schedule

**Best practice**: Run monthly or before major deployments to keep VMs secure and stable.

**Performance**: Update time varies (30 seconds to 10 minutes) depending on number of packages.

---

## Connection

### `azlin connect` - SSH into a VM

Connect to a VM with automatic tmux session management and **auto-reconnect on disconnect** ✨.

```bash
# Connect to a VM by name
azlin connect my-vm

# Connect by session name (new!)
azlin connect my-project

# Connect by IP address
azlin connect 20.12.34.56

# Connect to specific tmux session
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

**New Feature: Auto-Reconnect** 🔄

If your SSH session disconnects (network issue, accidental disconnect), azlin will automatically prompt you to reconnect:

```
Your session to my-vm was disconnected, do you want to reconnect? [Y|n]: y
Attempting to reconnect to my-vm...
[Reconnected successfully]
```

**Options**:
- Press `Y` or `Enter` to reconnect
- Press `N` to exit
- Configurable retry attempts (default: 3)

**Use cases**:
- Unstable network connections
- VPN disconnections
- Accidental terminal closures
- Long-running sessions

---

## Monitoring

### `azlin w` - Show who's logged in

Run the `w` command on all VMs to see active users and their processes.

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

**Use cases**:
- Check if anyone is using a VM
- Monitor system load
- See active sessions

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

**Use cases**:
- Deploy code to VM
- Download results from training
- Backup data between VMs
- Share files across team VMs

### `azlin sync` - Sync dotfiles from ~/.azlin/home/

Automatically sync your configuration files to all VMs.

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
- Consistent shell configuration across VMs
- Share vim/emacs settings
- Distribute git configuration
- Team-wide development standards

---

## Storage & NFS

**COMING SOON**: Share home directories across multiple VMs using Azure Files NFS storage.

### Overview

Planned feature to enable multiple VMs to share a common home directory via NFS, perfect for:
- Team collaboration with shared development environments
- Consistent tooling and configuration across all VMs
- Seamless switching between VMs without data loss
- Cost-effective multi-VM workflows

### Planned CLI Commands

Storage commands are currently in development. The following commands are planned:

```bash
# Create shared storage (100GB Premium NFS)
azlin storage create myteam-shared --size 100 --tier Premium

# List storage accounts
azlin storage list

# Mount storage on VM (shares home directory)
azlin storage mount myteam-shared --vm my-dev-vm

# Unmount storage from VM
azlin storage unmount my-dev-vm

# Show storage status and usage
azlin storage status myteam-shared

# Delete storage
azlin storage delete myteam-shared
```

**Use cases**:
- Create a shared storage once, mount it on multiple VMs
- All VMs see the same home directory with shared files and configs
- Switch between VMs seamlessly without copying data
- Team members collaborate in shared development environment

### Storage Tiers & Costs

**Premium Tier** (Premium_LRS):
- Cost: $0.153/GB/month
- Performance: High IOPS, low latency
- Best for: Active development environments

**Standard Tier** (Standard_LRS):
- Cost: $0.0184/GB/month
- Performance: Standard IOPS
- Best for: Backups, archival data

**Example**: 100GB shared storage
- Premium: ~$15.30/month
- Standard: ~$1.84/month

### Implementation Status

The core modules (`storage_manager.py` and `nfs_mount_manager.py`) are complete and tested. CLI integration is in progress.

**Technical details**: [DESIGN_NFS_STORAGE.md](DESIGN_NFS_STORAGE.md)

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

**Output example**:
```
Cost Summary (2025-01-01 to 2025-01-31):
  Total: $247.50
  
  By VM:
    azlin-vm-001 (Standard_D2s_v3): $142.00
    azlin-vm-002 (Standard_B2s):     $105.50
```

**💡 Tip**: Use `azlin stop` when not using VMs to minimize costs!

---

## Advanced Usage

### Command Passthrough (Execute on VM)

Execute commands on VMs without creating persistent sessions.

```bash
# Execute command on running VM (opens in new terminal)
azlin -- python train.py

# Execute on new VM
azlin new -- ./run_tests.sh

# With VM selection (if multiple VMs exist)
azlin -- nvidia-smi
# [Shows selection menu if multiple VMs]
```

**Use cases**:
- Run one-off commands
- CI/CD pipelines
- Remote script execution
- Automated testing

### Configuration File

Set default values in `~/.azlin/config.toml`:

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
azlin new --region eastus
```

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

### Daily Development Workflow

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
azlin new --name carol-vm --repo https://github.com/company/project

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
azlin ps --resource-group my-rg  # Check GPU usage

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

---

## Tips & Best Practices

### 💰 Cost Optimization

1. **Stop VMs when not in use**: `azlin stop vm-name`
2. **Use B-series for dev**: `--vm-size Standard_B2s` (burstable, cheaper)
3. **Delete unused VMs**: `azlin destroy vm-name --delete-rg`
4. **Track spending**: `azlin cost --by-vm`

### 🔒 Security

1. **Never commit VM keys**: azlin stores keys in `~/.ssh/`
2. **Use ssh-agent**: Keys are managed securely
3. **Rotate keys regularly**: Delete and recreate VMs periodically
4. **Review `.azlin/home/`**: Don't sync secrets

### 🚀 Productivity

1. **Set aliases**: `alias azdev='azlin connect my-dev-vm'`
2. **Use tmux sessions**: Work persists across disconnects
3. **Sync dotfiles**: Consistent environment everywhere
4. **Use pools**: Parallel testing across multiple VMs

### 🔧 Troubleshooting

**Can't connect?**
```bash
azlin status  # Check if VM is running
azlin start my-vm  # Start if stopped
```

**Connection drops frequently?**
- Auto-reconnect feature will prompt you (new in v2.1!)
- Check network stability
- Consider using screen/tmux for persistence

**VM is slow?**
```bash
azlin ps  # Check for resource-heavy processes
# Consider larger VM size: azlin destroy + azlin new --vm-size Standard_D4s_v3
```

---

## Quick Reference

| Command | Purpose | Example |
|---------|---------|---------|
| `azlin new` | Create VM | `azlin new --repo URL` |
| `azlin clone` | Clone VM + home dir | `azlin clone amplihack --num-replicas 3` |
| `azlin list` | List VMs | `azlin list` |
| `azlin connect` | SSH to VM | `azlin connect my-vm` |
| `azlin start` | Start stopped VM | `azlin start my-vm` |
| `azlin stop` | Stop VM (save $) | `azlin stop my-vm` |
| `azlin kill` | Delete VM | `azlin kill my-vm` |
| `azlin destroy` | Advanced delete | `azlin destroy --dry-run` |
| `azlin update` | Update dev tools | `azlin update my-vm` |
| `azlin os-update` | Update Ubuntu packages | `azlin os-update my-vm` |
| `azlin status` | Detailed status | `azlin status` |
| `azlin w` | Who's logged in | `azlin w` |
| `azlin ps` | Show processes | `azlin ps` |
| `azlin cp` | Copy files | `azlin cp file vm:~/` |
| `azlin sync` | Sync dotfiles | `azlin sync` |
| `azlin cost` | Track spending | `azlin cost --by-vm` |

---

For more details on any command, run:
```bash
azlin COMMAND --help
```


---

**For detailed API documentation and architecture, see [docs/](docs/)**
