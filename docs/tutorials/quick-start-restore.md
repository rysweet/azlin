# Quick Start: Session Restore in 5 Minutes

Get started with `azlin restore` in 5 minutes or less.

## Prerequisites

- Azlin installed: `pip install azlin`
- At least one running VM: `azlin list` shows active VMs
- SSH configured: `~/.ssh/id_rsa` or custom key

## Step 1: Verify Setup (30 seconds)

Check that ye have running VMs:

```bash
azlin list
```

Expected output:
```
NAME          STATUS    IP ADDRESS    LOCATION
dev-vm-1      Running   10.0.1.4      westus2
test-vm-2     Running   10.0.1.5      westus2
prod-vm-3     Running   10.0.1.6      westus2
```

If no VMs running, start one first:
```bash
azlin start my-vm
```

## Step 2: Test Platform Detection (15 seconds)

Preview what `azlin restore` will do:

```bash
azlin restore --dry-run
```

Expected output:
```
Detecting platform: macOS
Default terminal: Terminal.app
Found 3 running VMs

Would restore sessions:
  - dev-vm-1 → Terminal.app
  - test-vm-2 → Terminal.app
  - prod-vm-3 → Terminal.app
```

Platform detected correctly? Great! Move to Step 3.

**Platform not detected?** See [Platform Setup Guide](platform-setup-restore.md).

## Step 3: Restore Sessions (10 seconds)

Launch all terminal windows with one command:

```bash
azlin restore
```

Expected output:
```
Detecting platform: macOS
Found 3 running VMs

Launching terminals...
✓ Launched terminal for dev-vm-1
✓ Launched terminal for test-vm-2
✓ Launched terminal for prod-vm-3

Successfully restored 3 sessions
```

**What just happened:**
- Platform auto-detected (macOS/Windows/WSL/Linux)
- Appropriate terminal application launched
- SSH connections established to all VMs
- Tmux sessions attached (or created)

## Step 4: Verify Connections (30 seconds)

Check that terminal windows opened:

### macOS/Linux
- Look fer new Terminal.app or gnome-terminal windows
- Each window shows SSH connection to a VM
- Command prompt shows: `[azureuser@vm-name ~]$`

### Windows/WSL
- Windows Terminal opens with multiple tabs
- Each tab named "azlin - vm-name"
- Each tab connected to different VM

### Test tmux session
In any terminal window:
```bash
tmux list-sessions
```

Output:
```
azlin: 1 windows (created Thu Feb 6 12:00:00 2026)
```

## Step 5: Customize (Optional, 2 minutes)

Create configuration file fer custom behavior:

```bash
mkdir -p ~/.azlin
nano ~/.azlin/config.toml
```

Add basic configuration:
```toml
# Default resource group
default_resource_group = "my-rg"

# Custom session names
[session_names]
"dev-vm-1" = "development"
"test-vm-2" = "testing"
"prod-vm-3" = "production"
```

Save and test:
```bash
azlin restore --dry-run
```

Should show custom session names:
```
Would restore sessions:
  - dev-vm-1 → session: development
  - test-vm-2 → session: testing
  - prod-vm-3 → session: production
```

## Common Commands

```bash
# Restore all sessions
azlin restore

# Restore specific resource group
azlin restore --resource-group dev-rg

# Preview without launching
azlin restore --dry-run

# Force specific terminal
azlin restore --terminal windows_terminal

# Disable multi-tab (Windows Terminal)
azlin restore --no-multi-tab
```

## Quick Troubleshooting

### Problem: No terminals open

**Solution**: Check platform detection
```bash
azlin restore --dry-run
# Look fer "Default terminal: ..." line
```

If terminal not detected, specify manually:
```bash
# macOS
azlin restore --terminal macos_terminal

# Windows/WSL
azlin restore --terminal windows_terminal

# Linux
azlin restore --terminal linux_gnome
```

### Problem: SSH connection fails

**Solution**: Test SSH manually
```bash
# Get VM IP from azlin list
azlin list

# Test SSH connection
ssh -i ~/.ssh/id_rsa azureuser@<vm-ip>
```

If manual SSH fails, check:
- SSH key path: `ls -la ~/.ssh/id_rsa`
- SSH key permissions: `chmod 600 ~/.ssh/id_rsa`
- VM network accessibility

### Problem: Wrong session names

**Solution**: Add session mappings to config
```bash
cat >> ~/.azlin/config.toml << 'EOF'
[session_names]
"my-vm" = "my-session"
EOF
```

## Platform-Specific Tips

### macOS
- Terminal.app windows open automatically
- No multi-tab support (separate windows)
- Sessions preserved across Terminal.app restart

### Windows Terminal
- Multi-tab mode enabled by default
- All VMs open in one window as tabs
- Disable with `--no-multi-tab` fer separate windows

### WSL
- Uses Windows Terminal from WSL
- Longer launch time (cross-boundary overhead)
- Increase timeout if needed: `--timeout 60`

### Linux
- Uses gnome-terminal by default
- Falls back to xterm if gnome-terminal not installed
- Separate windows fer each VM

## Next Steps

Now that yer up and running:

1. **Learn daily workflows**: [How to Restore Sessions](../how-to/restore-sessions.md)
2. **Configure advanced options**: [Configuration Reference](../reference/configuration-reference.md)
3. **Platform-specific setup**: [Platform Setup Guide](platform-setup-restore.md)
4. **Handle issues**: [Troubleshooting Guide](../troubleshooting/restore-issues.md)

## Quick Reference Card

| Task | Command |
|------|---------|
| Restore all sessions | `azlin restore` |
| Preview restore | `azlin restore --dry-run` |
| Restore specific RG | `azlin restore -g my-rg` |
| Force terminal | `azlin restore -t windows_terminal` |
| Disable multi-tab | `azlin restore --no-multi-tab` |
| Increase timeout | `azlin restore --timeout 60` |
| Show help | `azlin restore --help` |

## Success!

Ye now know how to use `azlin restore` to automatically reopen all yer VM sessions. This saves 4-5 minutes every time ye need to reconnect after a reboot, network disruption, or context switch.

**Time saved per day** (assuming 3 reconnects): **12-15 minutes**
**Time saved per week**: **60-75 minutes**
**Time saved per month**: **4-5 hours**

## See Also

- [Feature Overview](../features/session-restore.md)
- [Complete How-To Guide](../how-to/restore-sessions.md)
- [Configuration Reference](../reference/configuration-reference.md)
- [Architecture Specification](../../Specs/azlin-restore-command.md)
