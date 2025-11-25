# Basic Concepts


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
