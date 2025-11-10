# azlin - Azure Ubuntu VM Provisioning CLI

**Version:** 2.0.0
**Last Updated:** 2025-10-27

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
azlin new # Dotfiles automatically synced after provisioning

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

### Azure Bastion (Secure Access)

Connect to VMs securely without public IPs using Azure Bastion:

```bash
# List available Bastion hosts
azlin bastion list

# Connect to VM through Bastion (auto-detected)
azlin connect my-vm --use-bastion

# Configure VM to use specific Bastion
azlin bastion configure my-vm --bastion-name my-bastion --resource-group my-rg
```

**Security Benefits**: Bastion eliminates internet-facing access to VMs, providing enhanced security through centralized access control, audit logging, and compliance with security policies requiring private-only VMs.

**Cost**: ~$289/month per Bastion host (Standard SKU, shared across all VMs in the VNet).

**Note**: azlin requires Standard SKU to enable CLI tunneling via `az network bastion tunnel`. Basic SKU only supports browser-based access.

For complete documentation, see the [Azure Bastion](#azure-bastion-secure-vm-access) section.

## Authentication

azlin supports multiple authentication methods for Azure, automatically detecting and using the best available method.

### Authentication Methods (Priority Order)

1. **Azure CLI** (Default) - Uses your existing `az login` session
2. **Service Principal with Client Secret** - For automation and CI/CD
3. **Service Principal with Certificate** - Enhanced security option
4. **Managed Identity** - Automatic authentication on Azure-hosted resources

### Quick Start: Azure CLI (Default)

Most users can start immediately with Azure CLI authentication:

```bash
# Login to Azure (one-time setup)
az login

# Use azlin (authentication automatic)
azlin list
```

### Service Principal Authentication

For CI/CD pipelines and automation, set up service principal authentication:

```bash
# Interactive setup
azlin auth setup

# Test authentication
azlin auth test

# Use with profile
azlin --auth-profile prod list
```

### Environment Variables

Service principal authentication via environment variables:

```bash
export AZURE_TENANT_ID="your-tenant-id"
export AZURE_CLIENT_ID="your-client-id"
export AZURE_CLIENT_SECRET="your-client-secret"

azlin list
```

### Documentation

- **Architecture**: See [AUTH_ARCHITECTURE_DESIGN.md](docs/AUTH_ARCHITECTURE_DESIGN.md) for authentication architecture
- **Implementation**: See [AUTH_IMPLEMENTATION_GUIDE.md](docs/AUTH_IMPLEMENTATION_GUIDE.md) for setup and implementation details

### Profile Management

Manage multiple authentication profiles for different environments:

```bash
# List profiles
azlin auth list

# Show profile details
azlin auth show prod

# Remove profile
azlin auth remove dev
```

For detailed authentication setup and troubleshooting, see the [Authentication Implementation Guide](docs/AUTH_IMPLEMENTATION_GUIDE.md).

# Comprehensive Command Reference

This section provides detailed examples of all azlin commands with practical use cases.

## Table of Contents

- [Common Options](#common-options) - Standard options across commands
- [VM Lifecycle](#vm-lifecycle) - Create, manage, and delete VMs
- [VM Maintenance](#vm-maintenance) - Update tools and packages
- [Connection](#connection) - Connect to VMs
- [Azure Bastion](#azure-bastion-secure-vm-access) - Secure VM access without public IPs
- [Monitoring](#monitoring) - Monitor VM status and processes
- [File Operations](#file-operations) - Transfer and sync files
- [Shared Storage](#shared-storage) - NFS storage across VMs
- [Cost Management](#cost-management) - Track spending
- [Batch Operations](#batch-operations) - Execute on multiple VMs
- [SSH Key Management](#ssh-key-management) - Rotate and manage SSH keys
- [VM Templates](#vm-templates) - Save and reuse configurations
- [Environment Variable Management](#environment-variable-management) - Manage env vars
- [Snapshot Management](#snapshot-management) - Backup and restore VMs
- [Advanced Usage](#advanced-usage) - Command passthrough and config
- [Common Workflows](#common-workflows) - Example use cases
- [Tips & Best Practices](#tips-best-practices) - Optimization tips
- [Quick Reference](#quick-reference) - Command cheat sheet
- [Natural Language Commands](#natural-language-commands-ai-powered) - Use AI-powered commands

---

## Common Options

Most azlin commands support these standard options:

- **`--resource-group, --rg TEXT`** - Specify the Azure resource group to use. If not provided, uses the default resource group from your config file (`~/.azlin/config.toml`) or prompts for selection.
- **`--config PATH`** - Path to a custom config file (overrides the default `~/.azlin/config.toml`)

These options are available on nearly all commands that interact with Azure resources, including:
- VM management: `new`, `list`, `start`, `stop`, `kill`, `destroy`, `status`
- Maintenance: `update`, `os-update`, `prune`
- Monitoring: `w`, `ps`, `top`, `cost`
- File operations: `sync`, `cp`
- Storage: `storage list`, `storage create`, `storage mount`, etc.
- Snapshots: `snapshot create`, `snapshot list`, `snapshot restore`, etc.
- Environment: `env set`, `env list`, `env import`, etc.
- SSH keys: `keys rotate`, `keys list`
- Sessions: `session`, `killall`

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

# Provision with shared NFS storage for home directory
azlin new --nfs-storage team-shared --name worker-1

# Specify VM size and region
azlin new --vm-size Standard_D4s_v3 --region westus2

# Provision from saved template
azlin new --template dev-vm --name my-instance

# Provision without auto-connecting
azlin new --no-auto-connect

# Provision multiple VMs in parallel (pool)
azlin new --pool 5

# Provision with custom resource group
azlin new --resource-group my-rg

# Combine options
azlin new --name gpu-trainer --vm-size Standard_NC6 --repo https://github.com/openai/whisper

# Create multiple workers with shared storage
azlin storage create team-shared --size 100
azlin new --nfs-storage team-shared --name worker-1
azlin new --nfs-storage team-shared --name worker-2
```

**Use cases**:
- Quick development environment setup
- Testing across multiple VM instances
- GPU-enabled model training
- Team onboarding (everyone gets identical setup)
- Distributed computing with shared storage

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

#### `azlin list` - List VMs

```bash
# List VMs in default resource group
azlin list

# List VMs in specific resource group
azlin list --resource-group my-custom-rg

# Show ALL VMs (including stopped)
azlin list --all

# List ALL VMs across all resource groups (expensive operation)
azlin list --show-all-vms
azlin list -a  # Short form

# Filter by tag
azlin list --tag env=dev

# Filter by tag key only
azlin list --tag team
```

**Output columns:**
- SESSION NAME - Custom label (if set)
- VM NAME - Azure VM name
- STATUS - Running/Stopped/Deallocated
- IP - Public IP address
- REGION - Azure region
- SIZE - VM size (e.g., Standard_D2s_v3)

**Filtering:**
- Default: Shows only running VMs
- `--all`: Shows stopped/deallocated VMs
- `--tag KEY=VALUE`: Filter by specific tag value
- `--tag KEY`: Filter by tag key existence

**Output example**:
```
VMs in resource group 'azlin-rg-1234567890':
SESSION NAME         VM NAME                             STATUS          IP              REGION     SIZE
my-project           azlin-vm-001                        Running         20.12.34.56     eastus     Standard_D2s_v3
-                    azlin-vm-002                        Stopped         N/A             westus2    Standard_B2s
```

#### `azlin session` - Manage session names

Session names are custom labels you can assign to VMs to help identify what you're working on. They appear in the `azlin list` output and make it easier to track multiple projects. You can also use session names to connect to VMs.

**Note:** Session names are different from tmux session names. Session names identify VMs, while tmux session names (specified with `--tmux-session`) control which tmux session you connect to on the remote VM. By default, azlin connects to the "azlin" tmux session.

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

# Show status for specific VM only
azlin status --vm my-vm

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
# Stop VM (stops compute billing)
azlin stop my-vm

# By default, VM is DEALLOCATED (compute fully released)
# Storage charges still apply

# Stop without deallocating (keeps resources allocated)
azlin stop my-vm --no-deallocate

# Specific resource group
azlin stop my-vm --resource-group my-rg
```

**Cost Impact:**
- `azlin stop` (default deallocate) → Compute billing STOPS, storage continues
- `azlin stop --no-deallocate` → Full billing continues

**Important:** Always use default (deallocate) for cost savings unless you need guaranteed resource availability.

**Defaults:**
- `--deallocate`: yes (fully release compute)
- `--timeout`: 300 seconds

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

### Deletion Commands Comparison

| Feature | `kill` | `destroy` | `killall` |
|---------|--------|-----------|-----------|
| Delete single VM | ✓ | ✓ | ✗ |
| Delete multiple VMs | ✗ | ✗ | ✓ |
| Dry-run mode | ✗ | ✓ | ✗ |
| Delete resource group | ✗ | ✓ | ✗ |
| Confirmation | ✓ | ✓ | ✓ |
| Force flag | ✓ | ✓ | ✓ |

**When to use:**
- `kill` - Simple, quick VM deletion
- `destroy` - Advanced with dry-run and RG deletion
- `killall` - Bulk cleanup of multiple VMs

#### `azlin killall` - Delete all VMs in resource group

```bash
# Delete all VMs (with confirmation)
azlin killall

# Delete all in specific resource group
azlin killall --resource-group my-rg

# Force delete all
azlin killall --force
```

**Warning**: This deletes ALL VMs in the resource group!

**Defaults:**
- `--prefix`: "azlin" (only deletes azlin-created VMs)

### Deletion Commands Comparison

| Feature | `kill` | `destroy` | `killall` |
|---------|--------|-----------|-----------|
| Delete single VM | ✓ | ✓ | ✗ |
| Delete multiple VMs | ✗ | ✗ | ✓ |
| Dry-run mode | ✗ | ✓ | ✗ |
| Delete resource group | ✗ | ✓ | ✗ |
| Confirmation | ✓ | ✓ | ✓ |
| Force flag | ✓ | ✓ | ✓ |

**When to use:**
- `kill` - Simple, quick VM deletion
- `destroy` - Advanced with dry-run and RG deletion
- `killall` - Bulk cleanup of multiple VMs

### `azlin prune` - Automated VM cleanup

Intelligently identify and delete idle or unused VMs based on age and activity.

```bash
# Preview what would be deleted (SAFE)
azlin prune --dry-run

# Delete VMs idle for 1+ days (default)
azlin prune

# Custom thresholds: 7+ days old, 3+ days idle
azlin prune --age-days 7 --idle-days 3

# Include running VMs in cleanup
azlin prune --include-running

# Include named sessions (normally protected)
azlin prune --include-named

# Skip confirmation prompt
azlin prune --force
```

**Safety Features:**
- Default excludes running VMs
- Default excludes VMs with session names
- Requires confirmation unless `--force`
- Dry-run mode shows exactly what will be deleted

**Criteria for Deletion:**
- VM older than `--age-days` (default: 1)
- VM idle for `--idle-days` (default: 1)
- VM stopped or deallocated
- VM has no session name (unless `--include-named`)

**Defaults:**
- `--age-days`: 1 day
- `--idle-days`: 1 day
- Excludes running VMs
- Excludes named sessions

**Use cases:**
- Automated cost reduction
- Remove forgotten test VMs
- Scheduled cleanup in CI/CD
- Prevent resource sprawl

---

## VM Maintenance

### `azlin update` - Update development tools on a VM

Update all programming tools and AI CLI tools that were installed during VM provisioning. **Default timeout: 300 seconds per tool.**

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

### Understanding VM Identifiers

Many azlin commands accept a **VM identifier** in three formats:

1. **VM Name:** Full Azure VM name (e.g., `azlin-vm-12345`)
   - Requires: `--resource-group` or default config
   - Example: `azlin connect azlin-vm-12345 --rg my-rg`

2. **Session Name:** Custom label you assigned (e.g., `my-project`)
   - Automatically resolves to VM name
   - Example: `azlin connect my-project`

3. **IP Address:** Direct connection (e.g., `20.1.2.3`)
   - No resource group needed
   - Example: `azlin connect 20.1.2.3`

**Commands that accept VM identifiers:**
- `connect`, `update`, `os-update`, `stop`, `start`, `kill`, `destroy`

**Tip:** Use session names for easy access:
```bash
azlin session azlin-vm-12345 myproject
azlin connect myproject  # Much easier!
```

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
# Note: By default, connects to existing "azlin" tmux session
# Use --tmux-session to specify a different tmux session name
azlin connect my-vm --tmux-session work

# Connect without tmux
azlin connect my-vm --no-tmux

# Connect with custom SSH user
azlin connect my-vm --user myusername

# Connect with custom key
azlin connect my-vm --key ~/.ssh/custom_key

# Disable auto-reconnect
azlin connect my-vm --no-reconnect
```

**New Feature: Auto-Reconnect**

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

## Azure Bastion (Secure VM Access)

Azure Bastion provides secure SSH access to VMs without public IPs, enhancing security by eliminating internet-facing access.

### Why Use Bastion?

**Security Benefits:**
- No public IPs needed on VMs (reduces attack surface)
- Centralized access control through Azure RBAC
- Audit logging of all connections
- Compliance with security policies requiring private-only VMs

**Cost Consideration:**
- Bastion: ~$289/month per host (Standard SKU required for CLI access)
- Saves: ~$3/month per VM (no public IP needed)
- Break-even: ~96 VMs per Bastion host

**Standard SKU Requirement:**

azlin uses Azure Bastion Standard SKU (not Basic) because:
- **CLI tunneling support**: Standard SKU enables `az network bastion tunnel` for programmatic SSH access
- **Basic SKU limitation**: Basic SKU only supports browser-based SSH through Azure Portal
- **azlin workflow**: Requires CLI-based tunneling for automated connection management and tmux integration

### Bastion Commands

#### `azlin bastion list` - List Bastion hosts

```bash
# List all Bastion hosts in subscription
azlin bastion list

# List Bastions in specific resource group
azlin bastion list --resource-group my-rg
```

**Output:**
```
Found 3 Bastion host(s):

  my-bastion
    Resource Group: my-rg
    Location: westus2
    SKU: Standard
    State: Succeeded
```

#### `azlin bastion status` - Show Bastion details

```bash
# Get status of specific Bastion
azlin bastion status my-bastion --resource-group my-rg
```

**Output:**
```
Bastion Host: my-bastion
Resource Group: my-rg
Location: westus2
SKU: Standard
Provisioning State: Succeeded
DNS Name: bst-xxx.bastion.azure.com

IP Configurations: 1
  [1] Subnet: AzureBastionSubnet
      Public IP: my-bastion-ip
```

#### `azlin bastion configure` - Configure VM to use Bastion

```bash
# Configure VM to connect through Bastion
azlin bastion configure my-vm --bastion-name my-bastion --resource-group my-rg
```

Stores VM-to-Bastion mapping in `~/.azlin/bastion_config.toml` for automatic use.

### Connecting Through Bastion

#### `azlin connect` with Bastion

```bash
# Auto-detect Bastion (prompts if found)
azlin connect my-private-vm --resource-group my-rg
# Output: Found Bastion host 'my-bastion'. Use it? (y/N)

# Force Bastion connection
azlin connect my-vm --use-bastion --resource-group my-rg

# Use specific Bastion
azlin connect my-vm --use-bastion --bastion-name my-bastion
```

**How It Works:**
1. Creates localhost tunnel: `127.0.0.1:random-port`
2. Routes SSH through tunnel to VM's private IP
3. Automatic cleanup on disconnect

**Performance:**
- Direct SSH: 3-5s connection time
- Through Bastion: 5-10s connection time (slight overhead)

### Bastion Configuration

Configuration stored in `~/.azlin/bastion_config.toml`:

```toml
# VM-to-Bastion mappings
[mappings.my-vm]
vm_name = "my-vm"
vm_resource_group = "my-rg"
bastion_name = "my-bastion"
bastion_resource_group = "network-rg"
enabled = true

# Auto-detection preferences
auto_detect = true
prefer_bastion = false  # Prefer direct connection when both available
```

### Security Features

- **Localhost-only tunnels**: Binds to 127.0.0.1 (not network-accessible)
- **Random ephemeral ports**: 50000-60000 range
- **Automatic cleanup**: Tunnels closed on disconnect
- **No credential storage**: Uses existing Azure authentication
- **Fail-secure**: Denies connection if Bastion unavailable for private-only VMs

### Documentation

- **Security Requirements**: See [BASTION_SECURITY_REQUIREMENTS.md](docs/BASTION_SECURITY_REQUIREMENTS.md)
- **Security Testing**: See [BASTION_SECURITY_TESTING.md](docs/BASTION_SECURITY_TESTING.md)

---

## Monitoring

### `azlin top` - Distributed real-time monitoring

Monitor CPU, memory, and processes across all VMs in a unified dashboard.

```bash
# Default: 10 second refresh
azlin top

# Custom refresh rate (5 second refresh)
azlin top --interval 5
azlin top -i 5

# Custom SSH timeout per VM (default 5s)
azlin top --timeout 10
azlin top -t 10

# Specific resource group
azlin top --rg my-rg

# Combine options: 15s refresh, 10s timeout
azlin top -i 15 -t 10
```

**Options:**
- `--interval, -i SECONDS` - Refresh rate (default: 10 seconds)
- `--timeout, -t SECONDS` - SSH timeout per VM (default: 5 seconds)

**Output:** Real-time dashboard showing:
- CPU usage per VM
- Memory utilization
- System load averages
- Top processes

**Use cases:**
- Monitor distributed workloads
- Identify resource bottlenecks
- Track performance across fleet
- Real-time capacity planning

Press Ctrl+C to exit.

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

## Shared Storage

Share home directories across multiple VMs using Azure Files NFS.

### `azlin storage` - NFS storage management

### Quick Start

```bash
# Create shared storage
azlin storage create myteam-shared --size 100 --tier Premium

# Provision VMs with shared home directory
azlin new --nfs-storage myteam-shared --name worker-1
azlin new --nfs-storage myteam-shared --name worker-2

# Or mount on existing VMs
azlin storage mount myteam-shared --vm existing-vm

# Now all VMs share the same home directory!
```

### Provisioning VMs with Shared Storage

The easiest way to use shared storage is to specify it when creating a new VM:

```bash
# Create storage once
azlin storage create team-shared --size 100 --tier Premium

# Create multiple VMs that share the same home directory
azlin new --nfs-storage team-shared --name worker-1
azlin new --nfs-storage team-shared --name worker-2
azlin new --nfs-storage team-shared --name worker-3

# All VMs will have /home/azureuser mounted from NFS
# Any file created on one VM is immediately visible on all others
```

When you use `--nfs-storage`, the VM's home directory is automatically mounted from the NFS share during provisioning. This means:
- No need to run separate mount commands
- Files are shared immediately
- Your `~/.azlin/home` contents (if any) are copied to the shared storage on first mount

### `azlin storage create` - Create NFS storage

Create a new Azure Files NFS share for shared storage across VMs.

```bash
# Create storage with default size (100GB) and tier (Premium)
azlin storage create myteam-shared

# Specify custom size and tier
azlin storage create myteam-shared --size 100 --tier Premium

# Create standard tier storage (lower cost)
azlin storage create myteam-shared --size 500 --tier Standard
```

**Note**: 100GB Premium costs approximately $15/month.

### `azlin storage list` - List storage accounts

Display all storage accounts in your resource group.

```bash
# List all storage accounts
azlin storage list
```

### `azlin storage status` - Show storage status

Check usage statistics and see which VMs are connected to a storage account.

```bash
# Check usage and connected VMs
azlin storage status myteam-shared
```

### `azlin storage mount` - Mount storage on VM

Mount shared storage on an existing VM, replacing its home directory with the shared NFS mount.

```bash
# Mount storage on existing VM
azlin storage mount myteam-shared --vm my-dev-vm
```

**Important**: Your existing home directory is backed up before mounting. Files from `~/.azlin/home` (if present) are copied to shared storage on first mount.

### `azlin storage unmount` - Unmount storage

Unmount shared storage from a VM and restore its local home directory from backup.

```bash
# Unmount storage and restore local home
azlin storage unmount --vm my-dev-vm
```

### `azlin storage delete` - Delete storage account

Delete a storage account. Fails by default if VMs are still connected.

```bash
# Delete storage (fails if VMs connected)
azlin storage delete myteam-shared

# Force delete even if VMs connected
azlin storage delete myteam-shared --force
```

### Use Cases

- **Team Collaboration**: Multiple developers in the same environment
- **Seamless Switching**: Move between VMs without losing work
- **Consistent Tools**: Same configs and tools across all VMs
- **Multi-VM Workflows**: Different tasks, shared data
- **Distributed Computing**: Multiple workers accessing shared datasets

### Storage Tiers

| Tier | Cost/GB/month | Use Case |
|------|---------------|----------|
| **Premium** | $0.153 | Active development, high performance |
| **Standard** | $0.0184 | Backups, archival, less frequent access |

**Example**: 100GB Premium = ~$15.30/month, 100GB Standard = ~$1.84/month

### How It Works

1. **Mount**: Existing home directory backed up, NFS share mounted
2. **Share**: All VMs with same storage see same files instantly
3. **Unmount**: NFS unmounted, local home restored from backup

**Security**: Storage is accessible only within your Azure VNet - no public access.

For complete documentation, see [docs/STORAGE_README.md](docs/STORAGE_README.md).

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

# Show monthly cost estimate for all VMs
azlin cost --estimate

# Per-VM monthly estimates
azlin cost --by-vm --estimate

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

**Tip**: Use `azlin stop` when not using VMs to minimize costs!

---

## Batch Operations

Execute operations on multiple VMs simultaneously using tags, patterns, or select all.

### Selection Methods

1. **By Tag:** `--tag env=dev`
2. **By Pattern:** `--vm-pattern 'test-*'`
3. **All VMs:** `--all`

### `azlin batch` - Batch VM operations

### `azlin batch stop` - Stop multiple VMs

```bash
# Stop all dev VMs
azlin batch stop --tag env=dev

# Stop VMs matching pattern
azlin batch stop --vm-pattern 'test-*'

# Stop all VMs
azlin batch stop --all

# Skip confirmation
azlin batch stop --all --confirm
```

### `azlin batch start` - Start multiple VMs

```bash
# Start all staging VMs
azlin batch start --tag env=staging

# Start specific pattern
azlin batch start --vm-pattern 'worker-*'
```

### `azlin batch sync` - Sync files to multiple VMs

```bash
# Sync dotfiles to all dev VMs
azlin batch sync --tag env=dev

# Sync to all VMs
azlin batch sync --all
```

### `azlin batch command` - Execute command on multiple VMs

```bash
# Update all test VMs
azlin batch command 'git pull' --tag env=test

# Restart service on all VMs
azlin batch command 'sudo systemctl restart myapp' --all

# Run with timeout
azlin batch command 'long-task.sh' --all --timeout 600
```

**Options:**
- `--tag KEY=VALUE` - Select by tag
- `--vm-pattern PATTERN` - Select by name pattern
- `--all` - Select all VMs
- `--confirm` - Skip confirmation
- `--timeout SECONDS` - Command timeout (for batch command only)

**Use cases:**
- Nightly shutdown of dev environments
- Deploy updates across fleet
- Restart services on multiple VMs
- Synchronized configuration updates

---

## SSH Key Management

Rotate and manage SSH keys across all VMs for enhanced security.

### `azlin keys` - SSH key management

### `azlin keys rotate` - Rotate SSH keys

Generate new SSH keys and update VMs in resource group.

```bash
# Rotate keys for azlin VMs only (default: VMs with "azlin" prefix)
azlin keys rotate

# Rotate keys for ALL VMs in resource group
azlin keys rotate --all-vms

# Rotate keys for VMs with specific prefix
azlin keys rotate --vm-prefix production

# Specific resource group
azlin keys rotate --rg production

# Skip backup (not recommended)
azlin keys rotate --no-backup

# Combine options
azlin keys rotate --all-vms --rg production --no-backup
```

**Options:**
- `--all-vms` - Rotate keys for ALL VMs (not just those with --vm-prefix)
- `--vm-prefix PREFIX` - Only rotate keys for VMs with this prefix (default: "azlin")
- `--no-backup` - Skip backing up old keys (not recommended)

**What happens:**
1. Generates new SSH key pair
2. Backs up existing keys (unless `--no-backup`)
3. Updates matching VMs with new public key
4. Verifies SSH access with new keys
5. Removes old keys from VMs

**Safety:** Old keys automatically backed up to `~/.azlin/keys-backup-<timestamp>/` (use `--no-backup` to skip)

### `azlin keys list` - List VM SSH keys

```bash
# Show SSH keys for all VMs
azlin keys list

# Show all keys (not just azlin VMs)
azlin keys list --all-vms

# Filter by prefix
azlin keys list --vm-prefix production
```

### `azlin keys export` - Export public key

```bash
# Export to file
azlin keys export --output my-key.pub
```

### `azlin keys backup` - Backup current keys

```bash
# Backup to default location
azlin keys backup

# Backup to custom location
azlin keys backup --destination /secure/backup/
```

**Best Practices:**
- Rotate keys every 90 days
- Backup before rotation
- Test access after rotation
- Store backups securely

---

## VM Templates

Save and reuse VM configurations for consistent provisioning.

### `azlin template` - VM template management

### `azlin template create` - Create template

Create a VM configuration template with optional parameters.

```bash
# Create template with all defaults (uses config file values)
azlin template create dev-vm

# Create template with specific VM size and region
azlin template create dev-vm --vm-size Standard_B2s --region westus2

# Create template with description
azlin template create prod-vm --description "Production configuration"

# Create template with cloud-init script
azlin template create custom-vm --cloud-init ~/my-cloud-init.yaml

# Combine all options
azlin template create ml-vm \
  --vm-size Standard_NC6 \
  --region eastus \
  --description "GPU-enabled ML training VM" \
  --cloud-init ~/ml-setup.yaml
```

**Options:**
- `--vm-size SIZE` - VM size (default: from config or Standard_D2s_v3)
- `--region REGION` - Azure region (default: from config or eastus)
- `--description TEXT` - Template description
- `--cloud-init PATH` - Path to cloud-init YAML file for custom VM setup

**Templates stored at:** `~/.azlin/templates/<name>.yaml`

### `azlin template list` - List templates

```bash
# Show all templates
azlin template list
```

### `azlin template delete` - Delete template

```bash
# Remove template
azlin template delete dev-vm

# Force delete without confirmation
azlin template delete dev-vm --force
```

### Using Templates

```bash
# Provision VM from template
azlin new --template dev-vm --name my-instance

# Template settings override defaults
# CLI flags override template settings
```

### `azlin template export` - Export template

```bash
# Export to file
azlin template export dev-vm my-template.yaml
```

### `azlin template import` - Import template

```bash
# Import from file
azlin template import my-template.yaml
```

**Use cases:**
- Standardize VM configurations
- Share configs across team
- Environment-specific templates (dev/staging/prod)
- Consistent onboarding

---





## Environment Variable Management

Manage environment variables stored in `~/.bashrc` on remote VMs.

### `azlin env` - Environment variable management

### `azlin env set` - Set variable

```bash
# Set environment variable
azlin env set my-vm DATABASE_URL="postgres://localhost/db"

# Set multiple variables
azlin env set my-vm API_KEY="secret123" ENVIRONMENT="production"

# Set variable containing secrets (skip warning)
azlin env set my-vm API_KEY="secret123" --force
```

**Options:**
- `--force` - Skip warnings when setting variables that may contain secrets

Variables are added to `~/.bashrc` with comment:
```bash
# Managed by azlin
export DATABASE_URL="postgres://localhost/db"
```

### `azlin env list` - List variables

```bash
# List all azlin-managed variables
azlin env list my-vm

# Show values (default hides)
azlin env list my-vm --show-values
```

### `azlin env delete` - Delete variable

```bash
# Remove specific variable
azlin env delete my-vm API_KEY
```

### `azlin env export` - Export to file

```bash
# Export to .env format
azlin env export my-vm prod.env

# Contents:
# DATABASE_URL=postgres://localhost/db
# API_KEY=secret123
```

### `azlin env import` - Import from file

```bash
# Import variables from .env file
azlin env import my-vm prod.env
```

### `azlin env clear` - Clear all variables

```bash
# Remove all azlin-managed variables
azlin env clear my-vm

# Skip confirmation
azlin env clear my-vm --force
```

**Security:**
- Variables only in `~/.bashrc` (not system-wide)
- Plaintext storage (use Azure Key Vault for secrets)
- No variables logged by azlin

**Use cases:**
- Configure applications
- Share team configuration
- Environment-specific settings
- Quick deployment configuration

---
## Snapshot Management

Create point-in-time backups of VM disks and restore VMs to previous states.

### `azlin snapshot` - VM snapshot management

### `azlin snapshot enable` - Enable automated snapshots

Enable scheduled snapshot creation for a VM.

```bash
# Enable scheduled snapshots (every 24 hours, keep 2)
azlin snapshot enable my-vm --every 24 --keep 2

# Custom schedule (every 12 hours, keep 5)
azlin snapshot enable my-vm --every 12 --keep 5
```

### `azlin snapshot disable` - Disable automated snapshots

Disable scheduled snapshot creation for a VM.

```bash
# Disable scheduled snapshots
azlin snapshot disable my-vm
```

### `azlin snapshot create` - Create a snapshot

Manually create a snapshot of a VM disk.

```bash
# Create snapshot manually
azlin snapshot create my-vm
```

### `azlin snapshot delete` - Delete a snapshot

Remove an existing snapshot.

```bash
# Delete snapshot (with confirmation)
azlin snapshot delete my-vm-snapshot-20251015-053000

# Delete without confirmation
azlin snapshot delete my-vm-snapshot-20251015-053000 --force
```

**Options:**
- `--force` - Skip confirmation prompt

### `azlin snapshot list` - List snapshots

Show all snapshots for a VM.

```bash
# List snapshots for VM
azlin snapshot list my-vm
```

### `azlin snapshot restore` - Restore from snapshot

Restore a VM from a previous snapshot.

```bash
# Restore VM from snapshot
azlin snapshot restore my-vm my-vm-snapshot-20251015-053000
```

### `azlin snapshot status` - View snapshot schedule

Check the snapshot schedule for a VM.

```bash
# View snapshot schedule
azlin snapshot status my-vm
```

### `azlin snapshot sync` - Trigger snapshot sync

Manually trigger snapshot sync across all scheduled VMs.

```bash
# Trigger snapshot sync now
azlin snapshot sync

# Sync specific VM
azlin snapshot sync --vm my-vm
```

**Snapshot Naming:** Automatic format `<vm-name>-snapshot-<timestamp>`

**Schedule Management:**
- Schedules stored in `~/.azlin/config.toml`
- `snapshot sync` checks all VMs with schedules
- Run `sync` in cron for automation

**Retention:**
- Old snapshots automatically deleted when limit reached
- `--keep N` maintains last N snapshots

**Defaults:**
- `--every`: 24 hours
- `--keep`: 2 snapshots

**Use cases:**
- Disaster recovery
- Pre-update backups
- Experimental changes (restore if needed)
- Compliance/archival requirements

---

## Natural Language Commands (AI-Powered)

**New in v2.1**: Use natural language to control azlin with Claude AI

The `azlin do` command understands what you want and executes the appropriate commands automatically. Just describe what you need in plain English, and azlin figures out the right commands to run.

### Installation & Setup

```bash
# Install via uvx (no installation needed)
uvx --from git+https://github.com/rysweet/azlin azlin do "list all my vms"

# Or install locally
pip install git+https://github.com/rysweet/azlin

# Configure your API key (required)
export ANTHROPIC_API_KEY=sk-ant-xxxxx...

# Make it permanent
echo 'export ANTHROPIC_API_KEY=sk-ant-xxxxx...' >> ~/.bashrc
```

Get your API key from: https://console.anthropic.com/

### Quick Examples from Integration Tests

All of these were tested and work reliably:

```bash
# VM Provisioning (100% confidence)
azlin do "create a new vm called Sam"
azlin do "provision a Standard_D4s_v3 vm called ml-trainer"
uvx --from git+https://github.com/rysweet/azlin azlin do "create a vm"

# Listing VMs (100% confidence)
azlin do "show me all my vms"
azlin do "list all my vms"
azlin do "what vms do I have"

# Checking Status (95% confidence)
azlin do "what is the status of my vms"
azlin do "show me vm details"

# Cost Queries (90% confidence)
azlin do "what are my azure costs"
azlin do "show me costs by vm"
azlin do "what's my current azure spending"

# File Operations
azlin do "sync all my vms"
azlin do "sync my home directory to vm Sam"
azlin do "copy myproject to the vm"

# Starting/Stopping VMs
azlin do "start my development vm"
azlin do "stop all test vms"
azlin do "stop all idle vms to save costs"

# Complex Multi-Step Operations
azlin do "create 5 test vms and sync them all"
azlin do "set up a new development environment"
azlin do "show me my costs and stop any vms I'm not using"
```

### Resource Cleanup with Natural Language

Safe, step-by-step cleanup workflow:

```bash
# Step 1: List what you have
azlin do "show me all my vms"

# Step 2: Preview deletion (dry-run)
azlin do "delete all test vms" --dry-run

# Step 3: Execute deletion (with confirmation)
azlin do "delete all test vms"
# Shows what will be deleted and asks "Execute these commands? [y/N]"

# Step 4: Verify cleanup
azlin do "list all vms"

# Other cleanup examples
azlin do "delete vm called experiment-123"
azlin do "delete vms older than 7 days"
azlin do "stop all stopped vms to deallocate them"
```

### Error Handling & Safety

The system gracefully handles invalid requests:

```bash
# Invalid requests (no action taken)
azlin do "make me coffee"
# Response: Warning: Low confidence. No commands executed.

# Ambiguous requests (asks for clarification)
azlin do "update something"
# Response: Warning: Low confidence. Continue anyway? [y/N]

# Dry-run for safety
azlin do "delete everything" --dry-run
# Shows plan without executing anything
```

### Command Options

```bash
# Preview without executing
azlin do "delete all old vms" --dry-run

# Skip confirmation prompts (for automation)
azlin do "create vm test-001" --yes

# See detailed parsing and execution
azlin do "create a vm" --verbose

# Combine options
azlin do "delete test vms" --dry-run --verbose
```

### Features

- **High Accuracy**: 95-100% confidence on VM operations (tested)
- **Context-Aware**: Understands your current VMs, storage, and Azure state
- **Safe by Default**: Shows plan and asks for confirmation
- **Dry Run Mode**: Preview actions without executing
- **Automation Ready**: `--yes` flag skips prompts for CI/CD
- **Verbose Mode**: See parsing details and confidence scores

### Integration Testing

All examples above come from real integration tests with actual Azure resources:

- ✅ 7/7 integration tests passing
- ✅ Dry-run tests (List VMs 100%, Status 100%, Create 95%)
- ✅ Real Azure operations (List VMs, Cost queries)
- ✅ Error handling (Invalid requests rejected gracefully)
- ✅ Ambiguous requests (Low confidence warnings)

See [docs/AZDOIT.md](docs/AZDOIT.md) for comprehensive documentation with 50+ examples.

### `azlin do` - Natural language command execution

Quick, stateless natural language commands powered by Claude AI.

### `azlin doit` - Alternative to azlin do

Advanced natural language execution with state persistence and objective tracking.

### Natural Language Commands Comparison

| Feature | `do` | `doit` |
|---------|------|--------|
| Natural language parsing | ✓ | ✓ |
| Command execution | ✓ | ✓ |
| State persistence | ✗ | ✓ |
| Objective tracking | ✗ | ✓ |
| Audit logging | ✗ | ✓ |
| Multi-strategy (future) | ✗ | ✓ |
| Cost estimation (future) | ✗ | ✓ |

**When to use:**
- `do` - Quick, simple natural language commands
- `doit` - Complex objectives requiring state tracking

---

## Autonomous Infrastructure Deployment (R2D2 for Azure)

**azlin doit** is an autonomous goal-seeking agent that deploys complex Azure infrastructure from natural language.

### Quick Examples

```bash
# Deploy complete web application stack
azlin doit deploy "App Service with Cosmos DB and Storage"

# Create API platform
azlin doit deploy "2 App Services behind API Management with shared database"

# Serverless pipeline
azlin doit deploy "Function App triggered by Storage queue saving to Cosmos DB"
```

**What the agent does:**
- 🎯 Parses your goal into executable sub-goals
- 🤖 Deploys resources autonomously (ReAct loop: Reason → Act → Observe → Evaluate)
- ✅ Self-evaluates and adapts to failures
- 📦 Generates production-ready Terraform + Bicep
- 📚 Creates teaching materials with architecture diagrams

### Management

```bash
azlin doit list                 # Show all doit-created resources
azlin doit cleanup --force      # Delete all doit resources
```

**📖 Learn More:**
- [Quick Start Guide](QUICKSTART_DOIT.md)
- [Tagging & Management](DOIT_TAGGING_AND_MANAGEMENT.md)
- [Architecture Docs](src/azlin/doit/README.md)

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

### Cost Optimization

1. **Stop VMs when not in use**: `azlin stop vm-name`
2. **Use B-series for dev**: `--vm-size Standard_B2s` (burstable, cheaper)
3. **Delete unused VMs**: `azlin destroy vm-name --delete-rg`
4. **Track spending**: `azlin cost --by-vm`

### Security

1. **Never commit VM keys**: azlin stores keys in `~/.ssh/`
2. **Use ssh-agent**: Keys are managed securely
3. **Rotate keys regularly**: Delete and recreate VMs periodically
4. **Review `.azlin/home/`**: Don't sync secrets

### Productivity

1. **Set aliases**: `alias azdev='azlin connect my-dev-vm'`
2. **Use tmux sessions**: Work persists across disconnects
3. **Sync dotfiles**: Consistent environment everywhere
4. **Use pools**: Parallel testing across multiple VMs

### Troubleshooting

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
| `azlin top` | Real-time monitor | `azlin top` |
| `azlin prune` | Auto cleanup | `azlin prune --dry-run` |
| `azlin batch` | Batch operations | `azlin batch stop --tag env=test` |
| `azlin keys` | SSH key mgmt | `azlin keys rotate` |
| `azlin template` | VM templates | `azlin template create dev-vm` |
| `azlin w` | Who's logged in | `azlin w` |
| `azlin ps` | Show processes | `azlin ps` |
| `azlin cp` | Copy files | `azlin cp file vm:~/` |
| `azlin sync` | Sync dotfiles | `azlin sync` |
| `azlin cost` | Track spending | `azlin cost --by-vm` |
| `azlin bastion list` | List Bastion hosts | `azlin bastion list --rg my-rg` |
| `azlin bastion status` | Bastion details | `azlin bastion status my-bastion` |
| `azlin bastion configure` | Configure VM for Bastion | `azlin bastion configure my-vm` |

---

For more details on any command, run:
```bash
azlin COMMAND --help
```


---

**For detailed API documentation and architecture, see [docs/](docs/)**
