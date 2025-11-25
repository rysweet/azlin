# Connecting to VMs

Connect to Azure VMs via SSH with automatic reconnection, tmux integration, and bastion support.

## Quick Start

```bash
# Interactive VM selection
azlin connect

# Connect to specific VM
azlin connect my-vm

# Connect and run command
azlin connect my-vm -- ls -la
```

## Overview

The `azlin connect` command provides intelligent SSH connectivity with:

- **Interactive VM selection** - Choose from list or create new
- **Auto-reconnection** - Automatically reconnect on network drops
- **Tmux integration** - Resume sessions automatically
- **Bastion support** - Seamless private network access
- **Session name resolution** - Connect by VM name, session name, or IP
- **Remote command execution** - Run commands without full SSH session

## Command Reference

```bash
azlin connect [OPTIONS] [VM_IDENTIFIER] [REMOTE_COMMAND]...
```

### Connection Options

| Option | Description | Default |
|--------|-------------|---------|
| `VM_IDENTIFIER` | VM name, session name, or IP address | Interactive selection |
| `--resource-group, --rg TEXT` | Resource group (for VM name) | From config |
| `--user TEXT` | SSH username | `azureuser` |
| `--key PATH` | SSH private key path | Auto-detected from Key Vault |

### Tmux Options

| Option | Description | Default |
|--------|-------------|---------|
| `--no-tmux` | Skip tmux session creation | Enabled |
| `--tmux-session TEXT` | Custom tmux session name | `azlin` |

### Reconnection Options

| Option | Description | Default |
|--------|-------------|---------|
| `--no-reconnect` | Disable auto-reconnect | Enabled |
| `--max-retries INTEGER` | Max reconnection attempts | 3 |

### Other Options

| Option | Description | Default |
|--------|-------------|---------|
| `-y, --yes` | Skip confirmation prompts | Interactive |
| `REMOTE_COMMAND` | Command to execute (use `--` separator) | None |

## Common Usage Patterns

### Interactive Connection

```bash
# Show VM list and connect
azlin connect
```

**What happens:**

1. Lists all available VMs
2. Shows option to create new VM
3. Prompts for selection
4. Connects via SSH with tmux

**Example interaction:**

```
Available VMs:
1. azlin-vm-12345 (eastus) - Running - my-project
2. dev-environment (westus) - Running - backend-api
3. ml-training (eastus2) - Running
4. Create new VM

Select VM (1-4): 1

Connecting to azlin-vm-12345...
[Connected - tmux session 'azlin']
```

### Direct Connection

```bash
# Connect by VM name
azlin connect my-vm

# Connect by session name
azlin connect my-project

# Connect by IP address
azlin connect 20.51.23.145

# Connect with specific resource group
azlin connect my-vm --rg production-rg
```

**What happens:**

1. Resolves VM identifier (name/session/IP)
2. Retrieves SSH keys from Key Vault (if needed)
3. Establishes SSH connection
4. Creates or attaches to tmux session
5. Auto-reconnects on disconnect (up to 3 times)

### Tmux Session Management

```bash
# Connect with tmux (default)
azlin connect my-vm

# Connect without tmux
azlin connect my-vm --no-tmux

# Connect with custom tmux session name
azlin connect my-vm --tmux-session dev-session
```

**Tmux behavior:**

- **First connection:** Creates new tmux session
- **Subsequent connections:** Attaches to existing session
- **Multiple users:** Each user gets their own tmux session
- **Persistence:** Sessions survive SSH disconnections

!!! tip "Tmux Benefits"
    - Resume exactly where you left off
    - Run long processes safely (survive network drops)
    - Multiple windows and panes
    - Shared sessions for pair programming

### Auto-Reconnection

```bash
# Default: Auto-reconnect enabled (3 attempts)
azlin connect my-vm

# Disable auto-reconnect
azlin connect my-vm --no-reconnect

# Custom retry limit
azlin connect my-vm --max-retries 5
```

**What happens on disconnect:**

1. Detects SSH connection drop
2. Waits 2 seconds
3. Attempts reconnection
4. Resumes tmux session (if enabled)
5. Repeats up to max-retries times

**Example reconnection:**

```
SSH connection lost. Reconnecting (attempt 1/3)...
Reconnected successfully!
[tmux session resumed]
```

### Remote Command Execution

```bash
# Run command and exit (use -- separator)
azlin connect my-vm -- ls -la /home/azureuser

# Run script
azlin connect my-vm -- bash -c "cd myproject && python train.py"

# Check status
azlin connect my-vm -- docker ps

# Run command without tmux
azlin connect my-vm --no-tmux -- htop -n 1
```

**What happens:**

1. Connects to VM
2. Executes command
3. Displays output
4. Disconnects automatically
5. No tmux session created (for command execution)

### Custom SSH Configuration

```bash
# Custom SSH user
azlin connect my-vm --user admin

# Custom SSH key
azlin connect my-vm --key ~/.ssh/custom_id_rsa

# Combine options
azlin connect my-vm --user admin --key ~/.ssh/custom_key --no-tmux
```

## Advanced Scenarios

### Bastion-Connected VMs

```bash
# Auto-detect bastion (default)
azlin connect private-vm

# Skip bastion confirmation
azlin connect private-vm --yes
```

**What happens:**

1. Detects VM has no public IP
2. Finds bastion host in virtual network
3. Prompts for bastion usage (unless `-y`)
4. Establishes connection through bastion
5. Works transparently (no difference to user)

**See:** [Azure Bastion Guide](../bastion/index.md)

### Connection by Session Name

```bash
# Set session name
azlin session azlin-vm-12345 my-project

# Connect by session name (anywhere)
azlin connect my-project
```

**What happens:**

1. Resolves session name to VM name
2. Finds VM in configured resource groups
3. Connects normally

**See:** [Session Management](sessions.md)

### Multiple Concurrent Connections

```bash
# Terminal 1
azlin connect my-vm --tmux-session window-1

# Terminal 2
azlin connect my-vm --tmux-session window-2

# Terminal 3 - attach to same session as Terminal 1
azlin connect my-vm --tmux-session window-1
```

### Non-Interactive (CI/CD)

```bash
# Skip all prompts
azlin connect my-vm --yes --no-tmux -- python run_tests.py

# Run command in script
azlin connect my-vm -y -- "cd /app && make deploy"
```

## Troubleshooting

### Connection Refused

```bash
# Check VM is running
azlin status --vm my-vm

# Restart VM if stopped
azlin start my-vm && azlin connect my-vm

# Check firewall rules
az vm show -g <rg> -n <vm> --query "networkProfile"
```

### SSH Key Issues

```bash
# Verify SSH keys in Key Vault
az keyvault secret list --vault-name <vault>

# Regenerate SSH keys
azlin new --name test-connection

# Use explicit key
azlin connect my-vm --key ~/.ssh/id_rsa
```

### Bastion Connection Issues

```bash
# Verify bastion exists
az network bastion list --resource-group <rg>

# Force public IP connection
azlin connect my-vm --no-bastion

# Check bastion status
az network bastion show --name <bastion> --resource-group <rg>
```

### Tmux Session Not Resuming

```bash
# List tmux sessions on VM
azlin connect my-vm -- tmux list-sessions

# Kill stuck session
azlin connect my-vm -- tmux kill-session -t azlin

# Connect without tmux
azlin connect my-vm --no-tmux
```

### Auto-Reconnect Not Working

```bash
# Check network connectivity
ping <vm-ip>

# Disable auto-reconnect
azlin connect my-vm --no-reconnect

# Increase retry limit
azlin connect my-vm --max-retries 10
```

## SSH Configuration

azlin automatically handles SSH configuration, but you can customize it:

### Manual SSH Access

```bash
# Get VM IP
azlin list

# SSH directly (if you have keys)
ssh azureuser@<vm-ip>

# Or use Azure CLI
az ssh vm -g <rg> -n <vm>
```

### SSH Config Integration

Add to `~/.ssh/config`:

```
Host azlin-*
    User azureuser
    IdentityFile ~/.ssh/azlin_key
    StrictHostKeyChecking no
```

Then:

```bash
ssh azlin-vm-12345
```

## Tmux Quick Reference

Once connected with tmux:

| Command | Action |
|---------|--------|
| `Ctrl-B D` | Detach from session |
| `Ctrl-B C` | Create new window |
| `Ctrl-B N` | Next window |
| `Ctrl-B P` | Previous window |
| `Ctrl-B %` | Split pane vertically |
| `Ctrl-B "` | Split pane horizontally |

**See:** [Tmux Cheat Sheet](https://tmuxcheatsheet.com/)

## Related Commands

- [`azlin new`](creating.md) - Create new VM
- [`azlin list`](listing.md) - View available VMs
- [`azlin status`](start-stop.md) - Check VM status
- [`azlin session`](sessions.md) - Manage session names
- [`azlin logs`](../monitoring/logs.md) - View VM logs

## Source Code

- [CLI Command](https://github.com/rysweet/azlin/blob/main/azlin/cli.py#L500)
- [SSH Connection Logic](https://github.com/rysweet/azlin/blob/main/azlin/ssh.py)
- [Bastion Integration](https://github.com/rysweet/azlin/blob/main/azlin/bastion.py)

---

*Last updated: 2025-11-24*
