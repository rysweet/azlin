# Your First VM


This guide walks you through creating your first Azure VM with azlin in detail.

## Overview

By the end of this tutorial, you'll have:

- A running Ubuntu 24.04 VM in Azure
- 12 development tools pre-installed
- SSH access configured
- A persistent tmux session
- Understanding of azlin basics

**Estimated time: 10-15 minutes**

## Before You Begin

Ensure you have completed:

1. [Installation](installation.md) - azlin and Azure CLI installed
2. Azure login - Run `az login`
3. Active Azure subscription

## Step-by-Step Walkthrough

### 1. Check Prerequisites

Verify Azure CLI is configured:

```bash
az account show
```

You should see your subscription details. If not, run `az login`.

### 2. Run azlin new

Create your first VM:

```bash
azlin new --name my-first-vm
```

### 3. Follow the Prompts

azlin will ask you a few questions:

**Q: Select Azure subscription**
- Choose your subscription from the list

**Q: Select resource group**
- Choose existing or create new
- Recommendation: Create "azlin-dev" for development VMs

**Q: Select region**
- Choose region close to you
- Common choices: eastus, westus2, westeurope

**Q: Select VM size**
- **s** (8GB RAM) - Light development
- **m** (64GB RAM) - Medium workloads
- **l** (128GB RAM) - Heavy workloads (default)
- **xl** (256GB RAM) - Very heavy workloads

**Q: Clone GitHub repository?**
- Enter repository URL or press Enter to skip

### 4. Wait for Provisioning

azlin will now:

1. **Create VM** (2-3 minutes)
2. **Install tools** (2-3 minutes)
3. **Configure SSH** (30 seconds)
4. **Start tmux** (10 seconds)

You'll see progress updates in real-time.

### 5. Automatic Connection

Once provisioning completes, azlin automatically connects you via SSH.

You'll see:

```
✓ VM created successfully
✓ Tools installed
✓ SSH configured
→ Connecting to my-first-vm...

Welcome to Ubuntu 24.04 LTS

azureuser@my-first-vm:~$
```

### 6. Verify Installation

Check that all tools are installed:

```bash
# Development tools
docker --version
az --version
gh --version
git --version

# Programming languages
node --version
python3 --version
rustc --version
go version
dotnet --version

# AI coding assistants
npx @github/copilot --version
```

All commands should return version information.

### 7. Start Developing

You're now in a tmux session on your VM. Try some commands:

```bash
# Clone a repository
git clone https://github.com/username/repo
cd repo

# Install dependencies
npm install
# or
pip install -r requirements.txt

# Run your application
npm start
# or
python app.py
```

### 8. Disconnect and Reconnect

To disconnect without stopping the VM:

```bash
# Detach from tmux (VM keeps running)
# Press: Ctrl+B, then D
```

To reconnect later:

```bash
azlin connect my-first-vm
```

Your tmux session and all running processes will still be there!

## Understanding What Happened

### Resource Group

azlin created or used a resource group containing:

- Virtual Machine
- Network Interface
- Public IP Address
- Network Security Group
- OS Disk
- SSH Keys (stored in Azure Key Vault)

### Installed Tools

The VM came with these tools pre-installed:

**Container & Orchestration:**
- Docker with daemon running

**Cloud & Version Control:**
- Azure CLI (authenticated)
- GitHub CLI
- Git

**Programming Languages:**
- Node.js with npm
- Python 3.13 with pip
- Rust with cargo
- Go
- .NET 10 RC

**AI Coding Assistants:**
- GitHub Copilot CLI
- OpenAI Codex CLI
- Claude Code CLI

### SSH Configuration

azlin configured SSH with:

- ED25519 key pair
- Key stored in Azure Key Vault
- Key synced across all azlin VMs
- Automatic SSH config entry

### tmux Session

A tmux session named "main" was started automatically:

- Survives disconnections
- Multiple windows/panes
- Shared across SSH connections

## Next Steps

Now that you have your first VM:

### Learn VM Management

- [List all VMs](../vm-lifecycle/listing.md)
- [Stop and start VMs](../vm-lifecycle/start-stop.md)
- [Clone VMs](../vm-lifecycle/cloning.md)
- [Delete VMs](../vm-lifecycle/deleting.md)

### Set Up Storage

- [Create NFS storage](../storage/creating.md)
- [Mount storage on VMs](../storage/mounting.md)
- [Share data across VMs](../storage/shared-home.md)

### Transfer Files

- [Copy files with azlin cp](../file-transfer/copy.md)
- [Sync home directory](../file-transfer/sync.md)
- [Manage dotfiles](../file-transfer/dotfiles.md)

### Monitor VMs

- [Check VM status](../monitoring/status.md)
- [View distributed metrics](../monitoring/top.md)
- [Track costs](../monitoring/cost.md)

## Troubleshooting

### VM creation failed

**Check quotas:**
```bash
azlin quota
```

See [Quota Management](../advanced/quotas.md) if you hit limits.

### Can't connect via SSH

**Check VM is running:**
```bash
azlin status my-first-vm
```

**Check SSH config:**
```bash
cat ~/.ssh/config | grep my-first-vm
```

See [Connection Issues](../troubleshooting/connection.md) for more help.

### Tools not installed

**Reconnect and check again:**
```bash
azlin connect my-first-vm
which docker az gh git node python3
```

If still missing, see [Common Issues](../troubleshooting/common-issues.md).

## Cleaning Up

When you're done experimenting:

```bash
# Stop VM (keeps data, stops charges)
azlin stop my-first-vm

# Delete VM (removes everything)
azlin destroy my-first-vm
```

---

**Congratulations!** You've created your first azlin VM. Continue to [Basic Concepts](concepts.md) to learn more.
