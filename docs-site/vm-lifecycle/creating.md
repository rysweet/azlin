# Creating VMs

Create new Azure VMs with azlin's `new` command - optimized for development workflows with automatic configuration and cloud-init provisioning.

## Quick Start

```bash
# Create a VM with sensible defaults (128GB RAM)
azlin new

# Create with custom name
azlin new --name my-dev-vm

# Create and clone a repository
azlin new --repo https://github.com/yourusername/yourproject
```

## Overview

The `azlin new` command provisions Azure VMs with:

- **Pre-installed development tools** (Docker, Python, Node.js, Git, etc.)
- **Automatic SSH key management** via Azure Key Vault
- **Optional NFS storage mounting** for shared home directories
- **Flexible sizing** from 8GB to 256GB RAM
- **Template support** for repeatable configurations
- **Bastion integration** for secure private networking

## Command Reference

```bash
azlin new [OPTIONS]
```

### Essential Options

| Option | Description | Default |
|--------|-------------|---------|
| `--name TEXT` | Custom VM name | Auto-generated (azlin-vm-xxxxx) |
| `--size [s\|m\|l\|xl]` | Size tier: s(8GB), m(64GB), l(128GB), xl(256GB) | `l` (128GB) |
| `--vm-size TEXT` | Exact Azure VM size (overrides --size) | Based on size tier |
| `--region TEXT` | Azure region | From config or eastus |
| `--resource-group TEXT` | Azure resource group | From config |
| `--repo TEXT` | GitHub repository URL to clone | None |

### Advanced Options

| Option | Description | Default |
|--------|-------------|---------|
| `--pool INTEGER` | Number of VMs to create in parallel | 1 |
| `--no-auto-connect` | Skip automatic SSH connection after provision | Enabled |
| `--template TEXT` | Template name for VM configuration | None |
| `--nfs-storage TEXT` | NFS storage account to mount as home | None |
| `--no-nfs` | Skip NFS storage mounting | NFS enabled if configured |
| `--no-bastion` | Always create public IP (skip bastion) | Bastion auto-detected |
| `--bastion-name TEXT` | Explicit bastion host name | Auto-detected |
| `-y, --yes` | Accept all defaults (non-interactive) | Interactive |

## Size Tiers Explained

azlin provides four convenience size tiers that map to optimal Azure VM SKUs:

| Tier | RAM | vCPUs | Azure VM Size | Use Case |
|------|-----|-------|---------------|----------|
| **s** (small) | 8GB | 2 | Standard_D2s_v3 | Lightweight dev, testing |
| **m** (medium) | 64GB | 16 | Standard_E16s_v5 | Standard development |
| **l** (large) | 128GB | 32 | Standard_E32s_v5 | **Default** - ML, large projects |
| **xl** (extra-large) | 256GB | 64 | Standard_E64s_v5 | Training, heavy workloads |

!!! tip "Custom Sizes"
    Use `--vm-size` with any Azure VM SKU for exact control:
    ```bash
    azlin new --vm-size Standard_E8as_v5  # ARM-based, cost-effective
    ```

## Common Usage Patterns

### Basic VM Creation

```bash
# Default VM (128GB RAM, auto-name, auto-connect)
azlin new

# Small VM for testing (8GB RAM)
azlin new --size s --name test-vm

# Medium VM with custom name (64GB RAM)
azlin new --size m --name dev-environment
```

**What happens:**

1. Generates unique VM name (if not provided)
2. Creates or retrieves SSH keys from Azure Key Vault
3. Provisions VM with cloud-init configuration
4. Installs development tools (Docker, Python, uv, Git, etc.)
5. Auto-connects via SSH (unless `--no-auto-connect`)

### Development with Repository

```bash
# Clone repository during provisioning
azlin new --repo https://github.com/youruser/yourproject

# Large VM for ML project
azlin new --size xl --name ml-training \
  --repo https://github.com/yourteam/ml-pipeline
```

**What happens:**

1. Provisions VM as normal
2. Clones repository to `/home/azureuser/yourproject`
3. Connects you directly to the VM
4. Repository ready to use immediately

### Team Environments with NFS

```bash
# Create VM with shared home directory
azlin new --nfs-storage myteam-shared --name worker-1

# Multiple workers sharing same home directory
azlin new --nfs-storage myteam-shared --name worker-2
azlin new --nfs-storage myteam-shared --name worker-3
```

**What happens:**

1. Mounts existing NFS storage account as `/home/azureuser`
2. All files, configs, and code shared across VMs
3. Perfect for distributed workloads or team collaboration

!!! warning "NFS Storage Must Exist"
    Create NFS storage first with `azlin storage create myteam-shared`

### Parallel VM Provisioning

```bash
# Create 5 identical VMs simultaneously
azlin new --pool 5 --size l --name batch-job

# Creates: batch-job-1, batch-job-2, batch-job-3, batch-job-4, batch-job-5
```

**What happens:**

1. Provisions all VMs in parallel (much faster)
2. Each gets unique name with numeric suffix
3. All VMs ready simultaneously
4. No automatic connection (use `azlin list` to see them)

### Template-Based Provisioning

```bash
# Create VM from saved template
azlin new --template dev-vm

# Template overrides defaults for size, region, tools, etc.
```

**What happens:**

1. Loads configuration from template
2. Applies template defaults (size, region, software, etc.)
3. Any explicit flags override template settings

**See:** [Templates Guide](../advanced/templates.md) for template creation

### Private VMs with Bastion

```bash
# Auto-detect bastion (default behavior)
azlin new --name private-vm

# Explicitly specify bastion
azlin new --name private-vm --bastion-name my-bastion

# Force public IP (skip bastion)
azlin new --name public-vm --no-bastion
```

**What happens:**

1. If bastion detected: Creates private VM (no public IP)
2. If no bastion: Creates VM with public IP
3. Connection automatically routed through bastion when present

**See:** [Azure Bastion Guide](../bastion/index.md)

### Non-Interactive (CI/CD)

```bash
# Accept all defaults without prompts
azlin new --yes --name ci-runner --size m

# Provision and run command without interaction
azlin new --yes --size xl -- python train.py --epochs 100
```

**What happens:**

1. No interactive prompts
2. Uses defaults for all unspecified options
3. Perfect for automation and scripts

## Advanced Examples

### GPU-Enabled VM

```bash
# Specify exact VM size with GPU
azlin new --vm-size Standard_NC6s_v3 --name gpu-training
```

### Multi-Region Deployment

```bash
# Deploy to specific regions
azlin new --region eastus --name east-vm
azlin new --region westus --name west-vm
azlin new --region northeurope --name eu-vm
```

### Execute Command Post-Provisioning

```bash
# Run command after VM is ready (use -- separator)
azlin new --size xl --repo https://github.com/user/ml-project -- \
  python train.py --config production.yaml

# Install additional software
azlin new --size m -- \
  "sudo apt-get update && sudo apt-get install -y postgresql-client"
```

## Provisioning Time

Typical provisioning times:

- **VM Creation:** 3-5 minutes
- **Cloud-init (software):** 5-10 minutes
- **Total:** ~10-15 minutes for fully configured VM

!!! tip "Watch Progress"
    Cloud-init logs available via: `azlin logs <vm-name>`

## What Gets Installed

Every azlin VM comes with:

**Development Tools:**
- Python 3.13 (with uv package manager)
- Docker & Docker Compose
- Node.js & npm
- Git & GitHub CLI (gh)
- tmux, vim, htop

**Cloud Tools:**
- Azure CLI (authenticated)
- kubectl (Kubernetes)
- Terraform

**System Configuration:**
- Docker added to user's group (no sudo needed)
- SSH keys stored in Key Vault
- Automatic security updates enabled

**See:** [Cloud-init Configuration](https://github.com/rysweet/azlin/blob/main/azlin/cloud_init_config.yaml)

## Troubleshooting

### VM Provisioning Fails

```bash
# Check Azure quota
azlin quota

# View detailed error logs
azlin logs <vm-name>

# Try different region
azlin new --region westus
```

### Can't Connect After Creation

```bash
# Check VM status
azlin status --vm <vm-name>

# Verify SSH keys
az keyvault secret list --vault-name <vault-name>

# Manual connection
azlin connect <vm-name>
```

### Cloud-init Incomplete

```bash
# SSH to VM and check cloud-init status
azlin connect <vm-name> -- cloud-init status

# View cloud-init logs
azlin logs <vm-name>
```

### Out of Quota

```bash
# Check current quota
azlin quota

# Request quota increase via Azure Portal
# Or try different region/size

azlin new --region westus --size m
```

**See:** [Quota Management](../advanced/quotas.md)

## Related Commands

- [`azlin list`](listing.md) - View all VMs
- [`azlin connect`](connecting.md) - SSH to VM
- [`azlin status`](../commands/vm/status.md) - Check VM status
- [`azlin clone`](cloning.md) - Clone existing VM
- [`azlin storage mount`](../commands/storage/mount.md) - Attach shared storage

## Source Code

- [CLI Command](https://github.com/rysweet/azlin/blob/main/azlin/cli.py#L200)
- [VM Provisioning Logic](https://github.com/rysweet/azlin/blob/main/azlin/vm.py)
- [Cloud-init Config](https://github.com/rysweet/azlin/blob/main/azlin/cloud_init_config.yaml)

---

*Last updated: 2025-11-24*
