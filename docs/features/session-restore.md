# Feature: Session Restore

Automatically restore all active azlin VM sessions with new terminal windows.

## Overview

The `azlin restore` command provides one-command restoration of ALL running VM sessions. It automatically detects yer platform, finds all active VMs, and launches appropriate terminal windows with SSH connections.

## Key Features

### 1. Smart Platform Detection

Automatically detects operating system and selects appropriate terminal:
- **macOS**: Terminal.app
- **Windows**: Windows Terminal (wt.exe)
- **WSL**: Windows Terminal with WSL integration
- **Linux**: gnome-terminal (fallback to xterm)

### 2. Multi-Tab Support (Windows Terminal)

Opens all sessions efficiently:
- **Single window mode**: All VMs as tabs in one Windows Terminal window
- **Multi-window mode**: Separate window fer each VM (configurable)

### 3. Automatic Session Management

Connects to existing tmux sessions or creates new ones:
- Attaches to existing session if available
- Creates new session with configured name if not
- Supports custom session name mappings per VM

### 4. Dry-Run Mode

Preview restore operations without launching terminals:
```bash
azlin restore --dry-run
```

Shows:
- Platform detection results
- VMs that would be restored
- Terminal commands that would execute
- Session mappings and SSH keys

### 5. Flexible Configuration

Configure behavior via `~/.azlin/config.toml`:
- Override terminal launcher
- Set session name mappings
- Configure timeouts
- Enable/disable multi-tab mode

## Use Cases

### Morning Routine - Restore Work Environment

After system reboot or disconnection:
```bash
azlin restore
```

Instantly reopens all development VMs with proper sessions.

### Multi-Project Development

Restore only specific resource group:
```bash
azlin restore --resource-group frontend-rg
azlin restore --resource-group backend-rg
```

### Network Recovery

After VPN reconnection or network disruption:
```bash
azlin restore
```

Re-establishes all SSH connections with preserved tmux sessions.

### Multi-Monitor Workflow

Disable multi-tab to spread sessions across monitors:
```bash
azlin restore --no-multi-tab
```

## Example Workflows

### Workflow 1: Development Team Morning Standup

```bash
# Team member arrives
azlin list  # Shows 3 VMs running from yesterday

# One command restores all sessions
azlin restore

# Output:
# ✓ frontend-vm → Terminal with React dev server
# ✓ backend-vm → Terminal with API server logs
# ✓ database-vm → Terminal with psql prompt

# All sessions preserved from yesterday
```

### Workflow 2: Multi-Environment Testing

```bash
# Preview environments
azlin restore --dry-run

# Restore dev environment
azlin restore --resource-group dev-rg

# Restore staging (in separate windows)
azlin restore --resource-group staging-rg --no-multi-tab

# Each environment isolated in its own terminals
```

### Workflow 3: After Laptop Sleep/Resume

```bash
# Laptop wakes from sleep
# SSH connections dropped

# Single command reconnects everything
azlin restore

# All sessions back online
# No manual reconnection needed
```

## Architecture Integration

### Platform Detection Layer

```
User Command
    ↓
Platform Detector (PlatformDetector.detect_platform())
    ↓
Terminal Launcher Factory (TerminalLauncher.get_launcher())
    ↓
Platform-Specific Launcher
    ↓
Terminal Windows
```

### Session Configuration Flow

```
User Config (~/.azlin/config.toml)
    ↓
Config Manager (load_config())
    ↓
VM Manager (list_vms())
    ↓
Session Config Builder (RestoreSessionConfig)
    ↓
Terminal Launcher (launch_all_sessions())
    ↓
SSH Connections + Tmux Attachment
```

## Security Considerations

All connections use:
- **SSH key authentication** (no passwords)
- **Per-VM SSH keys** (optional)
- **Standard SSH security options**:
  - `StrictHostKeyChecking=no` (for dynamic IPs)
  - `UserKnownHostsFile=/dev/null` (avoids conflicts)

See [Security Review](../../Specs/azlin-restore-command.md#security-review) fer complete analysis.

## Performance Characteristics

| Scenario | Sessions | Time | Method |
|----------|----------|------|--------|
| macOS | 3 VMs | ~2-3s | Sequential launch |
| Windows (multi-tab) | 5 VMs | ~1-2s | Single window |
| Windows (separate) | 5 VMs | ~3-5s | Multiple windows |
| WSL | 3 VMs | ~3-5s | Cross-boundary launch |
| Linux | 3 VMs | ~2-3s | Sequential launch |

**Note**: Times include platform detection, VM discovery, and terminal launch. Actual SSH connection time varies by network.

## Configuration Examples

### Minimal Configuration

```toml
# Use defaults fer everything
default_resource_group = "my-rg"
```

### Full Configuration

```toml
# Override terminal detection
terminal_launcher = "windows_terminal"
terminal_multi_tab = true
restore_timeout = 60

# Custom session names
[session_names]
"frontend-vm" = "react-dev"
"backend-vm" = "api-server"
"database-vm" = "postgres"

# Per-VM SSH keys
[vm_ssh_keys]
"production-vm" = "~/.ssh/prod_key"
```

### Platform-Specific Configurations

See [Configuration Reference](../reference/configuration-reference.md) fer complete examples.

## Error Handling

The command provides clear error messages fer common issues:

### No VMs Found
```
Error: No running VMs found
→ Run 'azlin list' to see available VMs
```

### Terminal Launch Failed
```
Error: Terminal launch failed fer 2/3 VMs
→ Check terminal configuration in config.toml
→ See troubleshooting guide
```

### SSH Connection Issues
```
Warning: Could not connect to VM 'dev-vm-1'
→ Check SSH key: ~/.ssh/id_rsa
→ Verify VM is accessible: ssh azureuser@10.0.1.4
```

## Comparison with Manual Workflow

### Before `azlin restore`

```bash
# Manual restore (4-5 minutes)
azlin list  # Check VMs
azlin connect dev-vm-1  # First VM
# Wait fer connection...
# Open new terminal
azlin connect test-vm-2  # Second VM
# Wait fer connection...
# Open new terminal
azlin connect prod-vm-3  # Third VM
# Wait fer connection...
# Total: 3 separate commands, 4-5 minutes
```

### With `azlin restore`

```bash
# Automated restore (5-10 seconds)
azlin restore
# All VMs connected simultaneously
# Total: 1 command, 5-10 seconds
```

**Time Savings**: 85-90% reduction fer 3+ VMs

## Limitations

1. **Terminal Required**: Must have compatible terminal installed
2. **Tmux Dependency**: VMs must have tmux installed fer session management
3. **Platform-Specific**: Behavior varies by platform (multi-tab only on Windows Terminal)
4. **Network Required**: Active network connection to Azure

## Future Enhancements

Potential improvements (not yet implemented):
- Custom terminal profiles per VM
- Automatic VM startup before restore
- Session layout configuration (split panes, window arrangement)
- Terminal window positioning (coordinates, monitor selection)

## Documentation

Complete documentation available:
- **[How-To Guide](../how-to/restore-sessions.md)** - Daily usage patterns
- **[Tutorial](../tutorials/platform-setup-restore.md)** - Platform setup from scratch
- **[Configuration Reference](../reference/configuration-reference.md)** - All config options
- **[Troubleshooting](../troubleshooting/restore-issues.md)** - Common problems and solutions
- **[CLI Help](../reference/cli-help-restore.md)** - Complete CLI reference

## See Also

- [Architecture Specification](../../Specs/azlin-restore-command.md)
- [Terminal Launcher Module](../../src/azlin/terminal_launcher.py)
- [VM Manager Integration](../../src/azlin/vm_manager.py)
- [Config Manager](../../src/azlin/config_manager.py)
