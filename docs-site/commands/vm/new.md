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
| `--size [xs\|s\|m\|l\|xl\|xxl]` | Choice | VM size tier (see [Size Tiers](#size-tiers-explained) below) |
| `--vm-size TEXT` | Azure Size | Exact Azure VM size (e.g., `Standard_E8as_v5`). Overrides `--size` |
| `--vm-family [d\|e]` | Choice | VM family: `d` (general purpose, default) or `e` (memory-optimized). See [VM Families](#vm-families) |
| `--region TEXT` | Azure Region | Azure region for VM placement (default: from config or interactive) |
| `--region-fit` | Flag | Automatically find a region with available quota and SKU capacity. See [Region Fit](#region-fit) |
| `--resource-group, --rg TEXT` | Name | Azure resource group (default: from config or interactive) |
| `--name TEXT` | Name | Base VM name for a single create (or a base name for pools). Single named creates also use the resolved VM name as the `azlin-session` tag shown by `azlin list`. |
| `--pool INTEGER` | Count | Number of VMs to create in parallel for distributed workloads |
| `--no-auto-connect` | Flag | Skip automatic SSH connection after provisioning |
| `--config PATH` | File | Path to custom config file (default: `~/.azlin/config.toml`) |
| `--template TEXT` | Name | Template name for VM configuration presets |
| `--nfs-storage TEXT` | Storage Account | NFS storage account name to mount as persistent home directory |
| `--no-nfs` | Flag | Skip NFS storage mounting; use only local home directory |
| `--no-bastion` | Flag | Force public IP creation; skip Azure Bastion auto-detection |
| `--bastion-name TEXT` | Name | Explicit bastion host name for private VM connections |
| `--home-disk-size INTEGER` | Size | Size of separate /home disk in GB (16–4096). See [Disk Configuration](#disk-configuration) | `100` |
| `--no-home-disk` | Flag | Disable separate /home disk; use OS disk | Enabled |
| `--tmp-disk-size INTEGER` | Size | Size of separate /tmp disk in GB (16–4096). See [Disk Configuration](#disk-configuration) | None (no tmp disk) |
| `-y, --yes` | Flag | Non-interactive mode: accept all defaults and skip confirmations |
| `-h, --help` | Flag | Show command help and exit |

## Size Tiers Explained

azlin provides convenient size tiers that map to Azure VM SKUs. The default family is **D-series v5** (general purpose). Use `--vm-family e` for **E-series v5** (memory-optimized).

### D-series (default: `--vm-family d`)

| Tier | vCPUs | RAM | Azure VM Size | Use Case |
|------|-------|-----|---------------|----------|
| `xs` (extra-small) | 2 | 8GB | `Standard_D2s_v5` | Cheapest dev box, CI runners |
| `s` (small) | 4 | 16GB | `Standard_D4s_v5` | Light development |
| `m` (medium) | 8 | 32GB | `Standard_D8s_v5` | Standard development |
| `l` (large) | 16 | 64GB | `Standard_D16s_v5` | Heavy development |
| `xl` (extra-large) | 32 | 128GB | `Standard_D32s_v5` | Power user workloads |
| `xxl` (2x-large) | 64 | 256GB | `Standard_D64s_v5` | Maximum compute |

### E-series (`--vm-family e`)

Memory-optimized VMs with higher RAM-to-core ratios, ideal for large datasets, in-memory caches, and ML workloads:

| Tier | vCPUs | RAM | Azure VM Size | Use Case |
|------|-------|-----|---------------|----------|
| `xs` (extra-small) | 2 | 16GB | `Standard_E2as_v5` | Light memory-intensive work |
| `s` (small) | 4 | 32GB | `Standard_E4as_v5` | Dev with larger datasets |
| `m` (medium) | 8 | 64GB | `Standard_E8as_v5` | General ML development |
| `l` (large) | 16 | 128GB | `Standard_E16as_v5` | Heavy ML, containers |
| `xl` (extra-large) | 32 | 256GB | `Standard_E32as_v5` | Large in-memory workloads |
| `xxl` (2x-large) | 64 | 512GB | `Standard_E64as_v5` | Maximum memory |

**Tip:** Use `--size` for quick selection, `--vm-family` to pick the series, or `--vm-size` for exact Azure SKU control. When `--vm-size` is provided, `--size` and `--vm-family` are ignored.

> **Migration note:** Previous versions used D-series v3 SKUs with different tier mappings (`s`=2 cores, `m`=16 cores, `l`=32 cores, `xl`=64 cores). The v5 series offers better availability and performance at the same or lower cost. If you have v3-specific quota, use `--vm-size` to specify v3 SKUs directly.

## VM Families

The `--vm-family` flag selects which Azure VM series to use:

| Family | Series | Optimized For | Example |
|--------|--------|---------------|---------|
| `d` (default) | Dv5 | General purpose — balanced CPU/RAM | `Standard_D8s_v5` |
| `e` | Eav5 | Memory — 2x RAM per core vs D-series | `Standard_E8as_v5` |

```bash
# General purpose (default)
azlin new --size m
# → Standard_D8s_v5 (8 cores, 32GB)

# Memory-optimized
azlin new --size m --vm-family e
# → Standard_E8as_v5 (8 cores, 64GB)
```

## Region Fit

The `--region-fit` flag automatically scans Azure regions to find one with available quota and SKU capacity:

```bash
# Auto-select a region with capacity for a large VM
azlin new --size l --region-fit
```

Output:
```
🔍 Scanning 8 regions for Standard_D16s_v5 (16 cores)...
  ✓ westus2: 48/100 cores used, SKU available
  ✗ centralus: 98/100 cores used (insufficient)
  ... (skipping remaining — match found)

✅ Selected region: westus2 (52 cores available)
Creating VM in westus2...
```

When combined with `--region`, the specified region is checked first; others are scanned only if it lacks capacity:

```bash
# Prefer westus2, fall back to any available region
azlin new --size l --region westus2 --region-fit
```

If no region has capacity, azlin prints a diagnostic table showing quota and SKU status for all candidate regions, plus suggestions for next steps.

Region fit also activates as **error recovery**: when a VM creation fails with `QuotaExceeded` or `SkuNotAvailable`, the error message suggests re-running with `--region-fit`.

**Full documentation:** [Region Fit Feature](../../../docs/features/region-fit.md)

## Examples

### Basic Provisioning

```bash
# Provision VM with default settings (large = 16 cores, 64GB RAM)
azlin new

# Cheapest dev box (2 cores, 8GB)
azlin new --size xs

# Standard development (8 cores, 32GB)
azlin new --size m

# Maximum compute (64 cores, 256GB)
azlin new --size xxl
```

### VM Family Selection

```bash
# General purpose D-series (default)
azlin new --size m
# → Standard_D8s_v5 (8 cores, 32GB)

# Memory-optimized E-series (2x RAM per core)
azlin new --size m --vm-family e
# → Standard_E8as_v5 (8 cores, 64GB)

# E-series large for ML workloads
azlin new --size xl --vm-family e
# → Standard_E32as_v5 (32 cores, 256GB)
```

### Region Fit — Automatic Region Selection

```bash
# Find any region with capacity
azlin new --size l --region-fit

# Prefer westus2, fall back if quota exhausted
azlin new --size xl --region westus2 --region-fit

# Combine with E-series and automation
azlin new --size l --vm-family e --region-fit --yes
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

For a single named VM, azlin also seeds the new machine from your local
`~/.azlin/home/` directory when that directory exists and is not empty. With
`--pool`, azlin treats `--name` as a base name for the generated VM names
instead of applying one shared session label.

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
7. **Home Sync** - For named single-VM creates, seeds initial dotfiles and configuration from `~/.azlin/home/` when that directory exists and is not empty
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
# Automatic: let azlin find a region with capacity
azlin new --size l --region-fit

# Check current quota usage
azlin list --show-quota

# Use smaller VM size
azlin new --size xs  # or --size s

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

### Disk Configuration

```bash
# Default: 100GB home disk, no tmp disk
azlin new --name dev-vm

# Custom home disk size
azlin new --name data-vm --home-disk-size 200

# Add /tmp disk for build artifacts
azlin new --name build-vm --tmp-disk-size 64

# Both disks
azlin new --name ml-vm --home-disk-size 500 --tmp-disk-size 128

# No home disk (use OS disk), with /tmp disk
azlin new --name scratch-vm --no-home-disk --tmp-disk-size 64

# Disable home disk entirely
azlin new --name simple-vm --no-home-disk
```

**Disk details:**
- **SKU**: Premium_LRS (Premium SSD)
- **Size bounds**: 16–4096 GB (validated before creation)
- **LUN assignment**: Home → LUN 0, Tmp → LUN 1
- **Tags**: `azlin-session`, `azlin-role` for auditing
- **Orphan cleanup**: Disks auto-deleted if VM creation fails
- **NFS precedence**: `--nfs-storage` disables home disk (planned; NFS not yet in Rust CLI)
- **Graceful degradation**: Disk setup failure does not abort cloud-init

**Full documentation:** [Separate Home & Tmp Disk Guide](../../../docs/how-to/separate-home-disk.md)

## Related Commands

- [`azlin list`](list.md) - List all VMs
- [`azlin connect`](connect.md) - Connect to existing VM
- [`azlin status`](status.md) - Check VM status
- [`azlin destroy`](destroy.md) - Delete VM and resources
- [`azlin template create`](../template/create.md) - Create VM template
- [`azlin storage create`](../storage/create.md) - Create NFS storage

## Source Code

- [vm.rs](https://github.com/rysweet/azlin/blob/main/rust/crates/azlin-azure/src/vm.rs) - Core provisioning logic (`create_vm`)
- [cmd_vm_ops.rs](https://github.com/rysweet/azlin/blob/main/rust/crates/azlin/src/cmd_vm_ops.rs) - `new` command handler
- [lib.rs](https://github.com/rysweet/azlin/blob/main/rust/crates/azlin-cli/src/lib.rs) - CLI command definitions

## See Also

- [All VM commands](index.md)
- [Getting Started Guide](../../getting-started/quickstart.md)
- [Authentication Profiles](../../authentication/profiles.md)
