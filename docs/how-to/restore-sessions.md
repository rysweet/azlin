# How to Restore Azlin Sessions

Quick guide fer restorin' ALL yer active azlin sessions with new terminal windows.

## Overview

The `azlin restore` command reopens ALL yer running VM sessions in new terminal windows with SSH connections. It automatically detects yer platform (macOS, Windows, WSL, Linux) and launches the appropriate terminal application.

## Quick Start

Restore all active sessions with one command:

```bash
azlin restore
```

This command:
- Lists all running VMs from `azlin list`
- Detects yer platform automatically
- Launches terminal windows with SSH connections
- Attaches to existing tmux sessions (or creates new ones)

## Basic Usage

### Restore All Sessions

```bash
azlin restore
```

Output:
```
Detecting platform: macOS
Found 3 running VMs:
  - dev-vm-1 (10.0.1.4)
  - test-vm-2 (10.0.1.5)
  - prod-vm-3 (10.0.1.6)

Launching terminals...
✓ Launched terminal for dev-vm-1
✓ Launched terminal for test-vm-2
✓ Launched terminal for prod-vm-3

Successfully restored 3 sessions
```

### Restore Sessions from Specific Resource Group

```bash
azlin restore --resource-group my-dev-rg
```

### Dry-Run Mode (Preview Without Launching)

```bash
azlin restore --dry-run
```

Output:
```
[DRY RUN] Would restore the following sessions:
  - dev-vm-1 → Terminal.app with SSH to azureuser@10.0.1.4
  - test-vm-2 → Terminal.app with SSH to azureuser@10.0.1.5
  - prod-vm-3 → Terminal.app with SSH to azureuser@10.0.1.6

Platform: macOS
Terminal: Terminal.app
Multi-tab: disabled (not supported)
```

## Platform-Specific Behavior

### macOS
- **Default Terminal**: Terminal.app
- **Command**: Opens separate Terminal.app windows
- **Session**: Attaches to tmux session named "azlin" (or custom)

```bash
# macOS automatically uses Terminal.app
azlin restore
```

### Windows Terminal (Windows & WSL)
- **Default Terminal**: Windows Terminal (wt.exe)
- **Command**: Opens Windows Terminal tabs
- **Session**: Connects via SSH from WSL
- **Multi-Tab**: Opens ALL sessions in one window (configurable)

```bash
# WSL automatically finds Windows Terminal
azlin restore

# Disable multi-tab mode
azlin restore --no-multi-tab
```

### Linux
- **Default Terminal**: gnome-terminal (fallback to xterm)
- **Command**: Opens separate terminal windows
- **Session**: Attaches to tmux session

```bash
# Linux auto-detects available terminal
azlin restore
```

## Advanced Options

### Override Terminal Launcher

```bash
# Force specific terminal
azlin restore --terminal windows_terminal

# Available options:
#   macos_terminal    - macOS Terminal.app
#   windows_terminal  - Windows Terminal (wt.exe)
#   linux_gnome      - gnome-terminal
#   linux_xterm      - xterm
```

### Custom Config File

```bash
azlin restore --config ~/.azlin/custom-config.toml
```

### Disable Multi-Tab Mode

```bash
# Open separate windows instead of tabs (Windows Terminal only)
azlin restore --no-multi-tab
```

## Exit Codes

- **0**: All sessions restored successfully
- **1**: Partial failure (some sessions failed to launch)
- **2**: Total failure (no sessions restored)

## Common Workflows

### Morning Routine - Restore All Work Sessions

```bash
# After reboot, restore all development VMs
azlin restore
```

### After Network Disruption

```bash
# Reconnect to all VMs after VPN reconnection
azlin restore
```

### Multi-Project Development

```bash
# Restore only development resource group
azlin restore --resource-group dev-rg

# Check what would be restored first
azlin restore --resource-group prod-rg --dry-run
```

## What Happens During Restore

1. **Platform Detection**: Automatically detects macOS, WSL, Windows, or Linux
2. **VM Discovery**: Queries Azure fer running VMs via `azlin list`
3. **Config Loading**: Loads SSH keys and session names from `~/.azlin/config.toml`
4. **Terminal Launch**: Opens terminal windows/tabs with SSH connections
5. **Session Attachment**: Connects to existing tmux sessions (or creates new ones)

## Security

All SSH connections use:
- **Key-based authentication** (no passwords)
- **StrictHostKeyChecking=no** (for dynamic IPs)
- **UserKnownHostsFile=/dev/null** (prevents known_hosts conflicts)
- **SSH keys** from `~/.azlin/config.toml` or default `~/.ssh/id_rsa`

## Next Steps

- [Configure terminal preferences](../reference/configuration-reference.md#terminal-settings)
- [Platform-specific setup guide](../tutorials/platform-setup-restore.md)
- [Troubleshooting restore issues](../troubleshooting/restore-issues.md)

## See Also

- `azlin list` - Show running VMs
- `azlin connect` - Connect to single VM
- `azlin config` - View configuration
