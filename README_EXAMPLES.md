# Comprehensive Command Reference

This section provides detailed examples of all azlin commands with practical use cases.

## Command Categories

- [VM Lifecycle](#vm-lifecycle) - Create, manage, and delete VMs
- [Connection](#connection) - Connect to VMs
- [Monitoring](#monitoring) - Monitor VM status and processes
- [File Operations](#file-operations) - Transfer and sync files
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
  1. azlin-vm-001 - Running - 20.12.34.56 - eastus - Standard_D2s_v3
  2. azlin-vm-002 - Stopped - N/A - westus2 - Standard_B2s
```

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

## Connection

### `azlin connect` - SSH into a VM

Connect to a VM with automatic tmux session management and **auto-reconnect on disconnect** ✨.

```bash
# Connect to a VM by name
azlin connect my-vm

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
| `azlin list` | List VMs | `azlin list` |
| `azlin connect` | SSH to VM | `azlin connect my-vm` |
| `azlin start` | Start stopped VM | `azlin start my-vm` |
| `azlin stop` | Stop VM (save $) | `azlin stop my-vm` |
| `azlin kill` | Delete VM | `azlin kill my-vm` |
| `azlin destroy` | Advanced delete | `azlin destroy --dry-run` |
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
