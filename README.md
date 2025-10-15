# azlin - Azure Ubuntu VM Provisioning CLI

**One command to create a fully-equipped development VM on Azure**

```bash

# Run directly from GitHub (no installation needed)
uvx --from git+https://github.com/rysweet/azlin azlin

# Create VM with dev tools
azlin

# Create VM and clone GitHub repo
azlin --repo https://github.com/owner/repo
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
6. **Python 3** - Python runtime + pip
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

### Option 1: Zero-Install with uvx (Recommended for Trying)

Run azlin instantly without installation using [uvx](https://docs.astral.sh/uv/concepts/tools/):

```bash
# Run directly from GitHub (no installation needed)
uvx --from git+https://github.com/rysweet/azlin azlin list

# Provision a VM
uvx --from git+https://github.com/rysweet/azlin azlin

# Clone a repo on the VM
uvx --from git+https://github.com/rysweet/azlin azlin --repo https://github.com/microsoft/vscode

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
azlin

# Create VM and clone a repo
azlin --repo https://github.com/microsoft/vscode

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
azlin  # Dotfiles automatically synced after provisioning

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
