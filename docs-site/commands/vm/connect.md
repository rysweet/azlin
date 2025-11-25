# azlin connect

**SSH connection with automatic tmux session management and auto-reconnect**

## Description

The `azlin connect` command establishes SSH connections to Azure VMs with intelligent features: interactive VM selection, automatic tmux session creation and reattachment, Azure Bastion tunneling for private VMs, session name resolution, and automatic reconnection on disconnect. It's the primary way to access your azlin VMs for development work.

**Key features:**
- Interactive VM selection if no identifier provided
- Automatic tmux session management (persistent sessions survive SSH disconnect)
- Auto-reconnect on network drops (enabled by default)
- Azure Bastion integration for private VMs
- Session name resolution (connect by project name instead of VM name)
- Remote command execution support
- Automatic SSH key retrieval from Azure Key Vault

## Usage

```bash
azlin connect [OPTIONS] [VM_IDENTIFIER] [REMOTE_COMMAND]...
```

## Arguments

| Argument | Description |
|----------|-------------|
| `VM_IDENTIFIER` | Optional. VM name, session name, or IP address. If omitted, shows interactive menu |
| `REMOTE_COMMAND` | Optional. Command to execute on VM (use `--` separator for commands with flags) |

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--resource-group, --rg TEXT` | Name | Resource group (required when using VM name) |
| `--config PATH` | File | Path to custom config file (default: `~/.azlin/config.toml`) |
| `--no-tmux` | Flag | Skip tmux session, use plain SSH |
| `--tmux-session TEXT` | Name | Custom tmux session name (default: `azlin`) |
| `--user TEXT` | Username | SSH username (default: `azureuser`) |
| `--key PATH` | File | SSH private key path (default: auto-retrieve from Key Vault) |
| `--no-reconnect` | Flag | Disable automatic reconnection on disconnect |
| `--max-retries INTEGER` | Count | Maximum reconnection attempts (default: 3) |
| `-y, --yes` | Flag | Skip confirmation prompts (e.g., bastion usage) |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Interactive Connection

```bash
# Show menu of available VMs
azlin connect

# Example output:
# Select a VM:
# 1. myproject (20.123.45.67) - eastus - Running
# 2. backend-dev (20.123.45.68) - westus2 - Running
# 3. [Create new VM]
# Choice [1]:
```

### Connect by VM Name

```bash
# Connect to VM by name
azlin connect myproject

# Connect with explicit resource group
azlin connect myvm --rg my-resource-group

# Connect and disable auto-reconnect
azlin connect myproject --no-reconnect
```

### Connect by Session Name

```bash
# Set session name first
azlin session azlin-vm-12345 ml-training

# Connect using session name
azlin connect ml-training

# azlin resolves session name to VM name automatically
```

### Connect by IP Address

```bash
# Connect directly to IP (bypasses VM lookup)
azlin connect 20.123.45.67

# Useful for temporary access or non-azlin VMs
azlin connect 10.0.1.5 --user ubuntu --key ~/.ssh/custom_key
```

### Custom Tmux Sessions

```bash
# Connect without tmux (plain SSH)
azlin connect myvm --no-tmux

# Connect with custom tmux session name
azlin connect myvm --tmux-session dev-work

# Multiple tmux sessions on same VM
azlin connect myvm --tmux-session session1  # Terminal 1
azlin connect myvm --tmux-session session2  # Terminal 2
```

### Execute Remote Commands

```bash
# Run single command
azlin connect myvm -- ls -la

# Run command with sudo
azlin connect myvm -- sudo systemctl status docker

# Multi-line command
azlin connect myvm -- "cd /app && git pull && docker-compose up -d"

# Capture output
result=$(azlin connect myvm -- cat /proc/cpuinfo)
```

### Custom SSH Configuration

```bash
# Custom SSH user
azlin connect myvm --user myuser

# Custom SSH key
azlin connect myvm --key ~/.ssh/custom_id_rsa

# Both custom user and key
azlin connect myvm --user admin --key ~/.ssh/admin_key
```

### Auto-Reconnect Configuration

```bash
# Connect with default auto-reconnect (3 retries)
azlin connect myvm

# Increase retry attempts
azlin connect myvm --max-retries 10

# Disable auto-reconnect for one-off commands
azlin connect myvm --no-reconnect -- uptime
```

### Azure Bastion Integration

```bash
# Auto-detect bastion requirement (default)
azlin connect myvm

# Skip bastion confirmation prompt
azlin connect myvm --yes

# Connect to VM explicitly requiring bastion
# (azlin detects private IP and offers bastion tunnel)
```

## VM Identifier Resolution

azlin resolves VM identifiers in this order:

1. **IP Address** - Direct connection if valid IP format
2. **Session Name** - Looks up VM tagged with session name
3. **VM Name** - Queries Azure for VM by name in resource group
4. **Interactive** - Shows menu if no identifier provided

**Example:**
```bash
# 1. Check if "myproject" is an IP - No
# 2. Check if "myproject" is a session name - Yes! Resolve to "azlin-vm-12345"
# 3. Connect to "azlin-vm-12345"
azlin connect myproject
```

## Tmux Session Management

By default, `azlin connect` uses tmux for persistent sessions:

**Benefits:**
- Sessions survive SSH disconnections
- Multiple terminal panes within one connection
- Background processes continue running
- Rejoin work exactly where you left off

**Behavior:**
- First connection: Creates new tmux session named `azlin`
- Subsequent connections: Reattaches to existing `azlin` session
- Multiple sessions: Use `--tmux-session` for separate work contexts

**Example workflow:**
```bash
# Day 1: Start work
azlin connect myvm
# (Inside tmux, start long-running process)
# Close terminal (process keeps running)

# Day 2: Resume work
azlin connect myvm
# (Automatically reattaches to same tmux session)
# (Process still running exactly where you left it)
```

**Tmux basics:**
- `Ctrl-B D` - Detach from tmux (keeps session running)
- `tmux ls` - List tmux sessions
- `tmux attach -t azlin` - Manual reattach
- `tmux kill-session -t azlin` - Kill session

## Auto-Reconnect Feature

**Enabled by default.** If SSH connection drops, azlin automatically attempts to reconnect:

**Reconnection triggers:**
- Network interruption
- VM temporarily unreachable
- SSH timeout
- Bastion tunnel failure

**Behavior:**
```
Connection lost. Attempting to reconnect... (1/3)
Connection lost. Attempting to reconnect... (2/3)
Connection restored!
```

**Disable for:**
- One-off command execution
- Scripts where failure should propagate
- Debugging connection issues

```bash
# Disable auto-reconnect
azlin connect myvm --no-reconnect
```

## Azure Bastion Integration

azlin automatically detects when VMs require Azure Bastion:

**Detection:**
1. Checks if VM has public IP
2. If no public IP, searches for bastion in resource group
3. Offers bastion tunnel connection

**Interactive prompt:**
```
VM has no public IP. Use Azure Bastion tunnel? [Y/n]:
```

**Non-interactive mode:**
```bash
# Skip prompt, auto-accept bastion
azlin connect myvm --yes
```

**How bastion tunneling works:**
- azlin creates temporary SSH tunnel through bastion
- Transparent to user - works like normal SSH
- Requires Azure Bastion deployed in same VNet

## SSH Key Management

azlin automatically retrieves SSH keys from Azure Key Vault:

**Default behavior:**
1. Connects to VM
2. Checks if private key exists locally
3. If not found, retrieves from Key Vault
4. Caches locally for future connections

**Manual key specification:**
```bash
# Use specific key file
azlin connect myvm --key ~/.ssh/my_custom_key
```

**Key Vault storage:**
- Keys stored during `azlin new` provisioning
- Accessible from any machine with Azure access
- Secure, centralized key management

## Troubleshooting

### Connection Refused

**Symptoms:** `Connection refused` or `Cannot connect to VM` error.

**Solutions:**
```bash
# Check VM is running
azlin status --vm myvm

# Start stopped VM
azlin start myvm

# Verify network security group allows SSH (port 22)
az network nsg rule list --resource-group <rg> --nsg-name <nsg>

# Check if bastion is required
azlin connect myvm --yes  # Auto-accept bastion if needed
```

### Tmux Session Already Exists

**Symptoms:** Connects to old tmux session with unintended work.

**Solutions:**
```bash
# Kill old session and create new one
azlin connect myvm -- tmux kill-session -t azlin
azlin connect myvm

# Or use different tmux session name
azlin connect myvm --tmux-session newsession
```

### Auto-Reconnect Keeps Failing

**Symptoms:** Infinite reconnection loop or max retries exceeded.

**Solutions:**
```bash
# Disable auto-reconnect to see actual error
azlin connect myvm --no-reconnect

# Check VM is actually running
azlin list

# Verify network connectivity
ping <vm-ip>

# Check SSH manually
ssh -vvv azureuser@<vm-ip>
```

### Session Name Not Found

**Symptoms:** `Session 'myproject' not found` error.

**Solutions:**
```bash
# List VMs to see actual names
azlin list

# Set session name if missing
azlin session azlin-vm-12345 myproject

# Or connect by VM name directly
azlin connect azlin-vm-12345
```

### Bastion Tunnel Fails

**Symptoms:** Bastion connection hangs or times out.

**Solutions:**
```bash
# Verify bastion exists and is running
azlin bastion list

# Check bastion status
azlin bastion status

# Try without bastion (if VM has public IP)
azlin connect myvm  # Choose 'n' when prompted for bastion

# Check Azure portal for bastion connectivity
```

### SSH Key Not Found

**Symptoms:** `Permission denied (publickey)` error.

**Solutions:**
```bash
# Check if key exists locally
ls ~/.ssh/id_rsa_azlin_*

# Manually retrieve from Key Vault
azlin keys get myvm

# Specify key explicitly
azlin connect myvm --key ~/.ssh/id_rsa_azlin_myvm

# Verify key permissions
chmod 600 ~/.ssh/id_rsa_azlin_myvm
```

### Cannot Execute Remote Command

**Symptoms:** Command not found or unexpected output.

**Solutions:**
```bash
# Use -- separator for commands with flags
azlin connect myvm -- ls -la  # Correct
azlin connect myvm ls -la     # May fail

# Quote complex commands
azlin connect myvm -- "cd /app && npm start"

# Check command executes on VM directly
azlin connect myvm -- which docker
```

### Tmux Nested Sessions Warning

**Symptoms:** "sessions should be nested with care" warning.

**Cause:** Running tmux inside an existing tmux session.

**Solutions:**
```bash
# Detach from current tmux before connecting
# (Press Ctrl-B D)

# Or connect without tmux
azlin connect myvm --no-tmux

# Use different tmux session names
azlin connect myvm --tmux-session inner
```

## Advanced Usage

### Multiple Concurrent Connections

```bash
# Terminal 1: Main work
azlin connect myvm --tmux-session main

# Terminal 2: Monitoring
azlin connect myvm --tmux-session monitor -- htop

# Terminal 3: Logs
azlin connect myvm --tmux-session logs -- tail -f /var/log/syslog
```

### Scripting and Automation

```bash
# Non-interactive connection in scripts
export AZLIN_VM="myvm"
azlin connect $AZLIN_VM --yes --no-reconnect -- ./deploy.sh

# Check VM reachability
if azlin connect myvm --no-reconnect -- echo "ok" > /dev/null 2>&1; then
    echo "VM is reachable"
fi

# Parallel command execution
for vm in vm1 vm2 vm3; do
    azlin connect $vm -- apt update &
done
wait
```

### Custom SSH Config Integration

azlin respects `~/.ssh/config` settings:

```bash
# Add to ~/.ssh/config
Host myvm
    User admin
    Port 2222
    IdentityFile ~/.ssh/custom_key

# Connect using SSH config alias
azlin connect myvm  # Uses SSH config settings
```

### Port Forwarding

```bash
# Forward local port 8080 to VM port 80
ssh -L 8080:localhost:80 azureuser@<vm-ip>

# Or use azlin with SSH options
azlin connect myvm -- -L 8080:localhost:80
```

### Debugging Connection Issues

```bash
# Verbose SSH output
ssh -vvv azureuser@<vm-ip>

# Test without tmux
azlin connect myvm --no-tmux

# Test without auto-reconnect
azlin connect myvm --no-reconnect

# Check bastion connectivity
azlin bastion status
```

## Workflow Integration

### Development Workflow

```bash
# Morning: Start work
azlin connect myproject
# (Inside VM: git pull, start services, etc.)

# Afternoon: Check status from another machine
azlin connect myproject
# (Automatically reattaches to same tmux session)

# Evening: Leave long-running job
# (Press Ctrl-B D to detach, close terminal)
# (Job keeps running on VM)
```

### Team Collaboration

```bash
# Team member 1: Start shared work
azlin connect shared-vm --tmux-session team-work

# Team member 2: Join session (shared tmux)
azlin connect shared-vm --tmux-session team-work
# (Both see same terminal - pair programming!)
```

### CI/CD Integration

```bash
# Deploy script with automatic reconnect
azlin connect build-vm --max-retries 10 -- ./deploy.sh

# Health check before deployment
azlin connect prod-vm --no-reconnect -- curl -f http://localhost/health
if [ $? -eq 0 ]; then
    echo "VM healthy, proceeding with deployment"
fi
```

## Related Commands

- [`azlin new`](new.md) - Provision new VM
- [`azlin list`](list.md) - List VMs to connect to
- [`azlin session`](session.md) - Set session names for easy connection
- [`azlin start`](start.md) - Start stopped VM before connecting
- [`azlin status`](status.md) - Check VM status
- [`azlin bastion status`](../bastion/status.md) - Check bastion availability
- [`azlin keys get`](../keys/get.md) - Retrieve SSH keys from Key Vault

## Source Code

- [vm_connector.py](https://github.com/rysweet/azlin/blob/main/src/azlin/vm_connector.py) - Connection logic
- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - CLI command definition
- [bastion_detector.py](https://github.com/rysweet/azlin/blob/main/src/azlin/modules/bastion_detector.py) - Bastion integration

## See Also

- [All VM commands](index.md)
- [Session Management](../../vm-lifecycle/sessions.md)
- [SSH Key Management](../../advanced/ssh-keys.md)
