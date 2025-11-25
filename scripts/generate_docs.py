#!/usr/bin/env python3
"""Generate MkDocs documentation pages from README and existing docs.

This script performs Pass 1 (Coverage) of the content migration:
- Extracts sections from README.md
- Migrates existing docs/ files
- Creates structured page stubs
- Tracks migration progress
"""

from pathlib import Path


class DocGenerator:
    """Generate documentation pages from source files."""

    def __init__(self, source_readme: Path, source_docs: Path, output_dir: Path):
        self.readme = source_readme.read_text()
        self.source_docs = source_docs
        self.output_dir = output_dir
        self.generated_files = []

    def extract_readme_section(self, start_line: int, end_line: int) -> str:
        """Extract lines from README."""
        lines = self.readme.split("\n")
        return "\n".join(lines[start_line - 1 : end_line])

    def find_section(self, heading: str) -> tuple[int, str]:
        """Find a section in README by heading."""
        lines = self.readme.split("\n")
        for i, line in enumerate(lines):
            if heading.lower() in line.lower() and line.startswith("#"):
                # Find next section
                end = i + 1
                while end < len(lines) and not (
                    lines[end].startswith("##") and lines[end] != lines[i]
                ):
                    end += 1
                return i + 1, "\n".join(lines[i:end])
        return 0, ""

    def create_page(self, path: Path, title: str, content: str, front_matter: dict | None = None):
        """Create a documentation page."""
        path.parent.mkdir(parents=True, exist_ok=True)

        md = f"# {title}\n\n{content}\n"

        path.write_text(md)
        self.generated_files.append(str(path.relative_to(self.output_dir)))
        print(f"Created: {path}")

    def generate_quickstart(self):
        """Generate quickstart page from README."""
        _, content = self.find_section("Quick Start")
        _, whats_new = self.find_section("What's New")

        quickstart_content = """
Get up and running with azlin in 5 minutes.

## Prerequisites

- Azure account ([create free account](https://azure.microsoft.com/free/))
- Azure CLI installed and configured (`az login`)
- Python 3.12 or later

## Step 1: Install azlin

```bash
# Run directly from GitHub (no installation needed)
uvx --from git+https://github.com/rysweet/azlin azlin new
```

Or install permanently:

```bash
uv tool install git+https://github.com/rysweet/azlin
```

## Step 2: Login to Azure

```bash
az login
```

## Step 3: Create Your First VM

```bash
azlin new --name myproject
```

azlin will:

1. ✓ Create an Ubuntu 24.04 VM
2. ✓ Install 12 development tools
3. ✓ Configure SSH access
4. ✓ Start tmux session
5. ✓ Connect you automatically

**Total time: 4-7 minutes**

## Step 4: Verify VM

Once connected, verify the tools:

```bash
# Check Docker
docker --version

# Check Python
python3 --version

# Check Node.js
node --version

# List all installed tools
which docker az gh git node python3 rustc go dotnet
```

## Step 5: Explore Commands

```bash
# List all your VMs
azlin list

# Check VM status
azlin status

# View distributed metrics
azlin top
```

## What's Next?

- **[Create Shared Storage](../storage/creating.md)** - Set up NFS storage
- **[Transfer Files](../file-transfer/copy.md)** - Copy files to/from VMs
- **[Manage Multiple VMs](../vm-lifecycle/index.md)** - Scale your fleet
- **[Set Up Authentication](../authentication/service-principal.md)** - Use service principals

## Troubleshooting

**Issue: Quota exceeded**

See [Quota Management](../advanced/quotas.md) for solutions.

**Issue: Connection timeout**

Check [Connection Issues](../troubleshooting/connection.md).

**Issue: Authentication failed**

See [Authentication Errors](../troubleshooting/auth-errors.md).

## Quick Reference

### Essential Commands

```bash
# VM Lifecycle
azlin new --name myvm          # Create VM
azlin list                     # List VMs
azlin connect myvm             # Connect to VM
azlin stop myvm                # Stop VM
azlin start myvm               # Start VM
azlin destroy myvm             # Delete VM

# Storage
azlin storage create           # Create NFS storage
azlin storage mount            # Mount storage

# Monitoring
azlin status                   # VM status
azlin w                        # Who is logged in
azlin top                      # Distributed metrics
azlin cost                     # Cost tracking
```

---

**Next:** [Learn core concepts](concepts.md) or [dive into VM lifecycle](../vm-lifecycle/index.md)
"""

        self.create_page(
            self.output_dir / "getting-started/quickstart.md",
            "Quick Start Guide",
            quickstart_content,
        )

    def generate_first_vm(self):
        """Generate detailed first VM walkthrough."""
        content = """
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
"""

        self.create_page(self.output_dir / "getting-started/first-vm.md", "Your First VM", content)

    def generate_concepts(self):
        """Generate basic concepts page."""
        content = """
Understand the core concepts behind azlin to use it effectively.

## Core Concepts

### Virtual Machines (VMs)

azlin creates **Ubuntu 24.04 LTS** virtual machines in Azure with development tools pre-installed.

**Key characteristics:**

- **Ephemeral or persistent** - VMs can be short-lived (CI/CD) or long-running (development)
- **Fully configured** - 12 tools installed on first boot
- **SSH-enabled** - Key-based authentication with Azure Key Vault
- **tmux session** - Persistent session survives disconnections

### Resource Groups

Azure organizes resources into **resource groups**. azlin can:

- Use existing resource groups
- Create new ones automatically
- Manage multiple resource groups

**Best practice:** Create separate resource groups for different projects or environments:

```bash
azlin new --name dev-vm --rg my-project-dev
azlin new --name prod-vm --rg my-project-prod
```

### VM Size Tiers

azlin uses simple size tiers instead of cryptic Azure SKUs:

| Tier | RAM | CPU | Azure SKU | Use Case |
|------|-----|-----|-----------|----------|
| **s** | 8 GB | 2 vCPU | Standard_D2s_v5 | Light development, testing |
| **m** | 64 GB | 8 vCPU | Standard_D8s_v5 | Medium workloads |
| **l** | 128 GB | 16 vCPU | Standard_D16s_v5 | Heavy workloads (default) |
| **xl** | 256 GB | 32 vCPU | Standard_D32s_v5 | Very heavy workloads |

**Custom sizes:** Override with `--vm-size`:

```bash
azlin new --vm-size Standard_D4s_v5
```

See [VM size optimization](../advanced/templates.md#vm-sizes) for more details.

### SSH Keys

azlin uses **ED25519 SSH keys** for authentication:

- **Generated automatically** on first run
- **Stored in Azure Key Vault** for cross-system access
- **Rotated regularly** for security
- **Shared across VMs** in same resource group

**Key locations:**

- Local: `~/.ssh/id_ed25519_azlin`
- Azure Key Vault: `azlin-ssh-key-<hash>`

See [SSH Key Management](../advanced/ssh-keys.md) for details.

### Azure Key Vault

azlin uses Azure Key Vault to:

- Store SSH keys securely
- Enable key sharing across systems
- Support multi-user access
- Provide audit logs

**Automatic setup:** azlin creates Key Vault automatically when needed.

### Authentication

azlin supports two authentication methods:

**1. Azure CLI (Default)**
```bash
az login
azlin new
```

**2. Service Principal**
```bash
azlin auth setup --method service-principal
```

See [Authentication Guide](../authentication/index.md) for details.

### Contexts

**Contexts** manage multiple Azure subscriptions or configurations:

```bash
# Create context for different subscription
azlin context create --name prod-sub --subscription <sub-id>

# Switch context
azlin context use prod-sub

# List contexts
azlin context list
```

See [Multi-Context Management](../authentication/multi-tenant.md) for details.

### Storage (Azure Files NFS)

azlin creates **Azure Files NFS shares** for shared storage:

- **NFSv4.1 protocol** - High performance, POSIX-compliant
- **Premium tier** - Low latency, high throughput
- **Automatic mounting** - Mount on VM creation or later
- **Shared across VMs** - Single source of truth for data

**Use cases:**

- Shared datasets
- Home directory sync
- Code repositories
- Build artifacts

See [Storage Guide](../storage/index.md) for details.

### Snapshots

**Snapshots** are point-in-time backups of VM disks:

- **Incremental** - Only changed blocks stored
- **Fast restore** - Create new VM from snapshot
- **Scheduled** - Automated daily/weekly backups

```bash
# Create snapshot
azlin snapshot create my-vm

# Restore from snapshot
azlin snapshot restore my-vm-snapshot --name restored-vm
```

See [Snapshots & Backups](../snapshots/index.md) for details.

### Bastion

**Azure Bastion** provides secure SSH without public IPs:

- **Browser-based SSH** - No local SSH client needed
- **No public IP** - VMs stay private
- **MFA support** - Enhanced security
- **Audit logs** - Track all connections

azlin detects Bastion automatically and uses it when available.

See [Bastion Guide](../bastion/index.md) for details.

### Batch Operations

Run commands across **multiple VMs** in parallel:

```bash
# Execute on all VMs
azlin batch exec --all "docker ps"

# Execute on tagged VMs
azlin batch exec --tag env=dev "git pull"

# Sync files to all VMs
azlin batch sync --all ~/config.json /etc/myapp/
```

See [Batch Operations](../batch/index.md) for details.

### Environment Variables

Manage environment variables across VMs:

```bash
# Set variable
azlin env set DATABASE_URL "postgres://..."

# Import from .env file
azlin env import .env.production

# Export current variables
azlin env export > backup.env
```

Variables are stored in:

- Local: `~/.azlin/env/<vm-name>.env`
- VM: `/etc/azlin/environment`

See [Environment Management](../environment/index.md) for details.

### Cost Management

azlin includes cost tracking and optimization:

- **Quota management** - Avoid exceeding limits
- **Auto-stop** - Stop idle VMs automatically
- **Cost tracking** - View spending by VM/resource group
- **Size recommendations** - Right-size VMs

```bash
# View costs
azlin cost --resource-group my-rg

# Check quotas
azlin quota

# Enable auto-stop
azlin autopilot enable --idle-timeout 2h
```

See [Cost Optimization](../advanced/quotas.md) for details.

## Configuration

azlin stores configuration in `~/.azlin/`:

```
~/.azlin/
├── config.toml           # Main configuration
├── contexts/             # Multi-context configs
├── ssh/                  # SSH keys
├── env/                  # Environment variables
└── logs/                 # Debug logs
```

**Edit configuration:**

```bash
# View current config
cat ~/.azlin/config.toml

# Edit with your editor
vim ~/.azlin/config.toml
```

See [Configuration Reference](../api/core.md#configuration) for all options.

## Workflow Patterns

### Development Workflow

```bash
# 1. Create VM
azlin new --name dev --repo https://github.com/me/project

# 2. Work on VM
azlin connect dev

# 3. Disconnect (VM keeps running)
# Ctrl+B, then D

# 4. Reconnect anytime
azlin connect dev

# 5. Stop when done
azlin stop dev
```

### Team Workflow

```bash
# 1. Create shared storage
azlin storage create --name team-data

# 2. Each team member creates VM
azlin new --name alice-dev --storage team-data
azlin new --name bob-dev --storage team-data

# 3. Everyone shares data via /mnt/azlin/
```

### CI/CD Workflow

```bash
# 1. Create ephemeral VM
azlin new --name ci-$BUILD_ID --yes --no-auto-connect

# 2. Run tests
azlin exec ci-$BUILD_ID "pytest tests/"

# 3. Cleanup
azlin destroy ci-$BUILD_ID --yes
```

## Next Steps

Now that you understand the concepts:

- **[Create Storage](../storage/creating.md)** - Set up shared NFS
- **[Manage VMs](../vm-lifecycle/index.md)** - Learn VM lifecycle
- **[Batch Operations](../batch/index.md)** - Scale to multiple VMs
- **[Cost Optimization](../advanced/quotas.md)** - Manage spending

---

**Ready to dive deeper?** Explore [Authentication](../authentication/index.md) or [Command Reference](../commands/index.md).
"""

        self.create_page(self.output_dir / "getting-started/concepts.md", "Basic Concepts", content)

    def generate_all(self):
        """Generate all documentation pages."""
        print("Generating Getting Started pages...")
        self.generate_quickstart()
        self.generate_first_vm()
        self.generate_concepts()

        print(f"\n✅ Generated {len(self.generated_files)} pages")
        return self.generated_files


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate documentation pages")
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument("--source-docs", type=Path, default=Path("docs"))
    parser.add_argument("--output", type=Path, default=Path("docs-site"))

    args = parser.parse_args()

    generator = DocGenerator(args.readme, args.source_docs, args.output)
    generator.generate_all()


if __name__ == "__main__":
    main()
