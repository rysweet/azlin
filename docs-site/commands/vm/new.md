# azlin new

**Primary command for provisioning new Azure VMs**

## Description

The `azlin new` command is the core of azlin - it provisions a fully-equipped Azure Ubuntu VM with all development tools pre-installed in 4-7 minutes. This single command handles authentication, VM creation, SSH key management (automatically stored in Azure Key Vault), cloud-init tool installation, optional NFS storage mounting, GitHub repository cloning, and automatic SSH connection with tmux.

**What gets installed on every VM:**
- Docker, Azure CLI, GitHub CLI, Git
- Node.js with user-local npm configuration
- Python 3.13+, Rust, Golang, .NET 10 RC
- ripgrep (rg) for fast code search
- AI tools: GitHub Copilot CLI, OpenAI Codex CLI, Claude Code CLI
- Persistent tmux session management

## Usage

```bash
azlin new [OPTIONS]
```

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--repo TEXT` | URL | GitHub repository URL to clone after provisioning |
| `--size [s\|m\|l\|xl]` | Choice | VM size tier: `s`(mall)=8GB, `m`(edium)=64GB, `l`(arge)=128GB (default), `xl`=256GB RAM |
| `--vm-size TEXT` | Azure Size | Exact Azure VM size (e.g., `Standard_E8as_v5`). Overrides `--size` |
| `--region TEXT` | Azure Region | Azure region for VM placement (default: from config or interactive) |
| `--resource-group, --rg TEXT` | Name | Azure resource group (default: from config or interactive) |
| `--name TEXT` | Name | Custom VM name (default: auto-generated `azlin-vm-TIMESTAMP`) |
| `--pool INTEGER` | Count | Number of VMs to create in parallel for distributed workloads |
| `--no-auto-connect` | Flag | Skip automatic SSH connection after provisioning |
| `--config PATH` | File | Path to custom config file (default: `~/.azlin/config.toml`) |
| `--template TEXT` | Name | Template name for VM configuration presets |
| `--nfs-storage TEXT` | Storage Account | NFS storage account name to mount as persistent home directory |
| `--no-nfs` | Flag | Skip NFS storage mounting; use only local home directory |
| `--no-bastion` | Flag | Force public IP creation; skip Azure Bastion auto-detection |
| `--bastion-name TEXT` | Name | Explicit bastion host name for private VM connections |
| `-y, --yes` | Flag | Non-interactive mode: accept all defaults and skip confirmations |
| `-h, --help` | Flag | Show command help and exit |

## Size Tiers Explained

azlin provides convenient size tiers that map to Azure VM SKUs:

| Tier | RAM | vCPUs | Azure VM Size | Use Case |
|------|-----|-------|---------------|----------|
| `s` (small) | 8GB | 2 | `Standard_D2s_v5` | Light development, testing |
| `m` (medium) | 64GB | 16 | `Standard_E16as_v5` | General development, ML training |
| `l` (large) | 128GB | 32 | `Standard_E32as_v5` | **Default** - Heavy workloads, containers |
| `xl` (extra-large) | 256GB | 64 | `Standard_E64as_v5` | Large datasets, distributed systems |

**Tip:** Use `--size` for quick selection or `--vm-size` for exact Azure SKU control.

## Examples

### Basic Provisioning

```bash
# Provision VM with default settings (Large = 128GB RAM)
azlin new

# Provision Medium VM (64GB RAM)
azlin new --size m

# Provision Small VM (8GB RAM) for testing
azlin new --size s

# Provision Extra-Large VM (256GB RAM) for heavy workloads
azlin new --size xl
```

### Custom VM Names

```bash
# Give your VM a meaningful name
azlin new --name myproject

# Name VM and clone repository
azlin new --name web-app --repo https://github.com/owner/webapp

# Team workflow with named VMs
azlin new --name backend-dev --size m
azlin new --name frontend-dev --size s
```

### Exact Azure VM Size

```bash
# Use specific Azure VM SKU (overrides --size)
azlin new --vm-size Standard_E8as_v5

# GPU-enabled VM (check Azure availability)
azlin new --vm-size Standard_NC6s_v3
```

### GitHub Repository Integration

```bash
# Provision VM and clone repository
azlin new --repo https://github.com/microsoft/vscode

# Named VM with repository
azlin new --name vscode-dev --repo https://github.com/microsoft/vscode --size xl
```

### Parallel VM Pools

```bash
# Create 5 VMs in parallel for distributed workloads
azlin new --pool 5 --size l

# Named pool for team onboarding
azlin new --pool 3 --name team-vm --size m
```

### NFS Shared Storage

```bash
# Provision VM with shared NFS home directory
azlin new --nfs-storage myteam-shared --name worker-1

# Multiple workers sharing same NFS storage
azlin new --nfs-storage myteam-shared --name worker-2
azlin new --nfs-storage myteam-shared --name worker-3

# Skip NFS and use only local storage
azlin new --no-nfs --name local-only
```

### Azure Bastion Integration

```bash
# Use specific bastion host for private VM
azlin new --bastion-name my-bastion

# Force public IP (skip bastion detection)
azlin new --no-bastion

# Let azlin auto-detect bastion (default behavior)
azlin new
```

### Non-Interactive / CI/CD Automation

```bash
# Full automation - zero prompts
azlin new --name ci-vm --yes

# CI/CD with specific configuration
azlin new --name build-agent --size xl --yes --no-auto-connect

# Automated with repository clone
azlin new --name test-runner --repo https://github.com/owner/tests --yes
```

### Template-Based Provisioning

```bash
# Use saved template for consistent VM configuration
azlin new --template dev-vm

# Template with custom name
azlin new --template ml-workstation --name my-ml-vm
```

### Execute Command After Provisioning

```bash
# Provision and run command on VM
azlin new --size xl -- python train.py

# Run setup script after provisioning
azlin new --name worker -- bash /setup.sh
```

## Provisioning Workflow

When you run `azlin new`, the following happens automatically:

1. **Authentication** - Verifies Azure CLI authentication
2. **Prerequisites** - Checks SSH keys and required tools
3. **VM Creation** - Provisions Ubuntu 24.04 VM with your chosen size
4. **Cloud-Init** - Installs all development tools (4-5 minutes)
5. **SSH Key Storage** - Automatically stores private key in Azure Key Vault for cross-system access
6. **NFS Storage** (optional) - Mounts shared persistent home directory
7. **Home Sync** - Syncs initial dotfiles and configuration
8. **GitHub Setup** (optional) - Clones repository if `--repo` specified
9. **SSH Connection** (optional) - Auto-connects with tmux unless `--no-auto-connect`

**Total time:** 4-7 minutes from command to working shell.

## SSH Key Management

**NEW:** SSH keys are automatically stored in Azure Key Vault for seamless cross-system access.

- Private keys stored securely in Key Vault as secrets
- Automatic retrieval when connecting from different machines
- No manual key distribution needed
- Works across macOS, Linux, and Windows (via WSL)

## NFS Shared Storage

Optionally mount Azure Files as your home directory for persistent, shared storage:

**Benefits:**
- Home directory persists across VM destroy/recreate cycles
- Multiple VMs can share the same home directory
- Works as a team collaboration workspace

**Setup:**
```bash
# Create storage account first (one-time setup)
azlin storage create myteam-shared --region eastus

# Provision VMs with shared storage
azlin new --nfs-storage myteam-shared --name dev-1
azlin new --nfs-storage myteam-shared --name dev-2
```

**Without NFS:**
```bash
# Use only local home directory (not persistent)
azlin new --no-nfs
```

## Cloud-Init Details

Every VM runs a comprehensive cloud-init script that:

1. Updates system packages (apt update/upgrade)
2. Installs Docker and docker-compose
3. Configures non-root Docker access
4. Installs Azure CLI, GitHub CLI, Git
5. Sets up Node.js with user-local npm (no sudo needed)
6. Installs Python 3.13+ from deadsnakes PPA
7. Installs Rust via rustup
8. Installs Golang
9. Installs .NET 10 RC
10. Installs ripgrep (rg) for fast search
11. Installs AI CLI tools (Copilot, Codex, Claude)
12. Configures tmux for persistent sessions

**Monitoring Progress:**
```bash
# After provisioning, check cloud-init status
azlin connect myvm -- cloud-init status --wait
```

## Troubleshooting

### VM Creation Hangs

**Symptoms:** Provisioning stuck at "Creating VM" step.

**Solutions:**
```bash
# Check Azure portal for quota limits
az vm list-usage --location eastus --output table

# Try smaller VM size
azlin new --size s

# Try different region
azlin new --region westus2
```

### Cloud-Init Takes Too Long

**Symptoms:** "Waiting for cloud-init" exceeds 10 minutes.

**Solutions:**
```bash
# SSH manually and check cloud-init logs
ssh azureuser@<vm-ip>
sudo tail -f /var/log/cloud-init-output.log

# Check for apt lock issues
sudo lsof /var/lib/dpkg/lock-frontend
```

### SSH Connection Fails

**Symptoms:** Cannot connect after provisioning completes.

**Solutions:**
```bash
# Check VM is running
azlin status --vm myvm

# Verify network security group rules
az network nsg list --resource-group <rg>

# Try connecting with verbose SSH
ssh -vvv azureuser@<vm-ip>

# Check if bastion is required
azlin connect myvm  # Will prompt for bastion if needed
```

### NFS Mount Fails

**Symptoms:** NFS storage mount errors during provisioning.

**Solutions:**
```bash
# Verify storage account exists and is in same region
azlin storage list

# Check storage account network rules
az storage account show --name mystorageaccount --query networkRuleSet

# Use local storage instead
azlin new --no-nfs
```

### Quota Exceeded Errors

**Symptoms:** "QuotaExceeded" or "Cores limit reached" error.

**Solutions:**
```bash
# Check current quota usage
azlin list --show-quota

# Use smaller VM size
azlin new --size s  # or --size m

# Request quota increase (Azure portal)
# Or use different region with available quota
azlin new --region westeurope
```

### Template Not Found

**Symptoms:** `--template` flag reports template doesn't exist.

**Solutions:**
```bash
# List available templates
azlin template list

# Create template first
azlin template create dev-vm --size m --repo https://github.com/owner/repo

# Then use template
azlin new --template dev-vm
```

## Advanced Configuration

### Custom Cloud-Init Script

You can customize cloud-init via templates:

```bash
# Create template with custom cloud-init
azlin template create custom-dev --size m

# Edit template file at ~/.azlin/templates/custom-dev.toml
# Add custom cloud-init commands

# Use template
azlin new --template custom-dev
```

### Network Configuration

```bash
# Force public IP for direct internet access
azlin new --no-bastion

# Use bastion for private network security
azlin new --bastion-name corporate-bastion

# Auto-detect best option (default)
azlin new
```

### Cost Optimization

```bash
# Use smallest size for testing
azlin new --size s --name test-vm

# Auto-shutdown after provisioning (manual script)
azlin new --name temp-vm --no-auto-connect
# Then in another terminal:
# azlin stop temp-vm --deallocate
```

## Related Commands

- [`azlin list`](list.md) - List all VMs
- [`azlin connect`](connect.md) - Connect to existing VM
- [`azlin status`](status.md) - Check VM status
- [`azlin destroy`](destroy.md) - Delete VM and resources
- [`azlin template create`](../template/create.md) - Create VM template
- [`azlin storage create`](../storage/create.md) - Create NFS storage

## Source Code

- [vm_provisioning.py](https://github.com/rysweet/azlin/blob/main/src/azlin/vm_provisioning.py) - Core provisioning logic
- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - CLI command definition
- [cloud-init template](https://github.com/rysweet/azlin/blob/main/src/azlin/cloud_init_config.py) - Cloud-init script

## See Also

- [All VM commands](index.md)
- [Getting Started Guide](../../getting-started/quickstart.md)
- [Authentication Profiles](../../authentication/profiles.md)
