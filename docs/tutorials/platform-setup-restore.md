# Platform Setup Guide fer azlin restore

Learn how to set up `azlin restore` on yer platform from scratch.

## Overview

This tutorial walks ye through settin' up the `azlin restore` command on yer specific platform. Ye'll learn platform detection, terminal configuration, and test yer setup.

**Time Required**: 10-15 minutes
**Prerequisites**:
- Azlin CLI installed (`pip install azlin`)
- At least one running VM (`azlin list` shows VMs)
- SSH key configured (`~/.ssh/id_rsa` or custom)

## Setup by Platform

Choose yer platform:
- [macOS Setup](#macos-setup)
- [Windows Setup](#windows-setup)
- [WSL Setup](#wsl-setup)
- [Linux Setup](#linux-setup)

---

## macOS Setup

### Step 1: Verify Terminal.app

macOS comes with Terminal.app pre-installed. No installation needed.

```bash
# Verify terminal is available
which open
# Output: /usr/bin/open
```

### Step 2: Test Platform Detection

```bash
azlin restore --dry-run
```

Expected output:
```
Detecting platform: macOS
Default terminal: Terminal.app
```

### Step 3: Create Configuration (Optional)

```bash
# Create config file if it doesn't exist
mkdir -p ~/.azlin
cat > ~/.azlin/config.toml << 'EOF'
# macOS configuration
default_resource_group = "my-rg"
terminal_launcher = "macos_terminal"
restore_timeout = 30

[session_names]
"dev-vm" = "development"
EOF
```

### Step 4: Test Restore

```bash
# Start one VM first
azlin start my-dev-vm

# Test restore
azlin restore --dry-run

# Actually restore
azlin restore
```

### Step 5: Verify Terminal Windows

Terminal.app should open new windows fer each VM. Each window shows:
```
Last login: Thu Feb  6 12:00:00 2026
[azureuser@dev-vm ~]$
```

### macOS Troubleshooting

**Problem**: Terminal windows don't open
```bash
# Check if AppleScript execution is enabled
defaults read com.apple.Terminal

# Try forcing macOS terminal
azlin restore --terminal macos_terminal
```

**Problem**: Wrong SSH key
```bash
# Specify custom key in config
cat >> ~/.azlin/config.toml << 'EOF'
ssh_key_path = "~/.ssh/custom_key"
EOF
```

---

## Windows Setup

### Step 1: Install Windows Terminal

1. Open Microsoft Store
2. Search "Windows Terminal"
3. Click "Install"

Or via command line:
```powershell
winget install Microsoft.WindowsTerminal
```

### Step 2: Verify Installation

```powershell
# Check Windows Terminal is installed
where wt
# Output: C:\Users\YourName\AppData\Local\Microsoft\WindowsApps\wt.exe
```

### Step 3: Test Platform Detection

```powershell
azlin restore --dry-run
```

Expected output:
```
Detecting platform: Windows
Default terminal: Windows Terminal
Multi-tab: enabled
```

### Step 4: Create Configuration

```powershell
# Create config directory
mkdir $HOME\.azlin

# Create config file
@"
default_resource_group = "my-rg"
terminal_launcher = "windows_terminal"
terminal_multi_tab = true
restore_timeout = 30
"@ | Out-File -FilePath $HOME\.azlin\config.toml -Encoding UTF8
```

### Step 5: Test Restore

```powershell
# Test with dry-run
azlin restore --dry-run

# Actually restore (opens Windows Terminal tabs)
azlin restore
```

### Step 6: Verify Multi-Tab Behavior

Windows Terminal opens one window with multiple tabs:
- Tab 1: "azlin - dev-vm-1"
- Tab 2: "azlin - test-vm-2"
- Tab 3: "azlin - prod-vm-3"

### Windows Troubleshooting

**Problem**: wt.exe not found
```powershell
# Manual path configuration
$config = @"
terminal_launcher = "windows_terminal"
windows_terminal_path = "C:\Program Files\WindowsApps\Microsoft.WindowsTerminal_1.0.0.0_x64\wt.exe"
"@
$config | Out-File -Append $HOME\.azlin\config.toml
```

**Problem**: Separate windows instead of tabs
```powershell
# Disable multi-tab in config
azlin restore --no-multi-tab
```

---

## WSL Setup

### Step 1: Verify WSL Environment

```bash
# Check WSL version
cat /proc/version
# Output should contain "microsoft"
```

### Step 2: Locate Windows Terminal from WSL

```bash
# Find Windows Terminal executable
ls -la /mnt/c/Users/*/AppData/Local/Microsoft/WindowsApps/wt.exe
```

### Step 3: Test Platform Detection

```bash
azlin restore --dry-run
```

Expected output:
```
Detecting platform: WSL
Default terminal: Windows Terminal
Windows Terminal path: /mnt/c/Users/YourName/AppData/Local/Microsoft/WindowsApps/wt.exe
Multi-tab: enabled
```

### Step 4: Create WSL Configuration

```bash
# Get Windows username
WINDOWS_USER=$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r\n')

# Create config
mkdir -p ~/.azlin
cat > ~/.azlin/config.toml << EOF
# WSL configuration
default_resource_group = "azlin-wsl"
terminal_launcher = "windows_terminal"
terminal_multi_tab = true
restore_timeout = 60  # Longer timeout fer WSL

[session_names]
"dev-vm" = "development"
"test-vm" = "testing"
EOF
```

### Step 5: Test Restore

```bash
# Dry-run first
azlin restore --dry-run

# Full restore
azlin restore
```

### Step 6: Verify Windows Terminal Opens

Windows Terminal opens in Windows (not WSL) with tabs containing SSH sessions.

### WSL Troubleshooting

**Problem**: Windows Terminal not found
```bash
# Manual path discovery
find /mnt/c/Users -name "wt.exe" 2>/dev/null

# Add to config
echo 'windows_terminal_path = "/mnt/c/Users/YourName/AppData/Local/Microsoft/WindowsApps/wt.exe"' >> ~/.azlin/config.toml
```

**Problem**: SSH connection fails from Windows Terminal
```bash
# Verify SSH works from WSL first
ssh -i ~/.ssh/id_rsa azureuser@10.0.1.4

# Check SSH key path is accessible from Windows
wt.exe wsl -e ssh -i ~/.ssh/id_rsa azureuser@10.0.1.4
```

**Problem**: Slow launch times
```bash
# Increase timeout in config
sed -i 's/restore_timeout = 30/restore_timeout = 90/' ~/.azlin/config.toml
```

---

## Linux Setup

### Step 1: Install gnome-terminal (Ubuntu/Debian)

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install gnome-terminal

# Fedora/RHEL
sudo dnf install gnome-terminal

# Arch
sudo pacman -S gnome-terminal
```

### Step 2: Verify Installation

```bash
# Check gnome-terminal
which gnome-terminal
# Output: /usr/bin/gnome-terminal

# Fallback check fer xterm
which xterm
# Output: /usr/bin/xterm
```

### Step 3: Test Platform Detection

```bash
azlin restore --dry-run
```

Expected output:
```
Detecting platform: Linux
Default terminal: gnome-terminal
```

### Step 4: Create Configuration

```bash
mkdir -p ~/.azlin
cat > ~/.azlin/config.toml << 'EOF'
# Linux configuration
default_resource_group = "linux-vms"
terminal_launcher = "linux_gnome"
restore_timeout = 30

[session_names]
"dev-vm" = "development"
"build-vm" = "build-server"
EOF
```

### Step 5: Test Restore

```bash
# Dry-run
azlin restore --dry-run

# Full restore
azlin restore
```

### Step 6: Verify Terminal Windows

gnome-terminal opens separate windows fer each VM.

### Linux Troubleshooting

**Problem**: gnome-terminal not opening
```bash
# Check DISPLAY variable
echo $DISPLAY
# Should show :0 or similar

# Set if missing
export DISPLAY=:0

# Test manual launch
gnome-terminal -- bash -c "echo 'Test window'; read"
```

**Problem**: Permission denied fer terminal launch
```bash
# Check if user in correct groups
groups
# Should include: sudo, adm, cdrom

# Add to groups if missing
sudo usermod -aG sudo $USER
```

**Problem**: xterm fallback instead of gnome-terminal
```bash
# Force gnome-terminal in config
echo 'terminal_launcher = "linux_gnome"' >> ~/.azlin/config.toml

# Or install gnome-terminal
sudo apt install gnome-terminal
```

---

## Testing Yer Setup

### Test 1: Dry-Run Mode

```bash
azlin restore --dry-run
```

Should show:
- Detected platform
- Terminal launcher
- List of VMs that would be restored
- No actual terminal windows open

### Test 2: Single VM Restore

```bash
# Start one VM
azlin start test-vm

# Restore it
azlin restore --resource-group test-rg
```

Expected: One terminal window opens with SSH connection.

### Test 3: Multi-VM Restore

```bash
# Start multiple VMs
azlin start dev-vm test-vm prod-vm

# Restore all
azlin restore
```

Expected:
- macOS/Linux: 3 separate terminal windows
- Windows/WSL: 3 tabs in one Windows Terminal window (if multi-tab enabled)

### Test 4: Custom Session Names

```bash
# Add session mapping to config
cat >> ~/.azlin/config.toml << 'EOF'
[session_names]
"test-vm" = "testing-session"
EOF

# Restore
azlin restore

# In terminal, check session name
tmux list-sessions
# Should show: testing-session
```

---

## Next Steps

After setup is complete:

1. **Configure terminal preferences**: [Configuration Reference](../reference/configuration-reference.md)
2. **Learn restore workflows**: [How to Restore Sessions](../how-to/restore-sessions.md)
3. **Handle issues**: [Troubleshooting Guide](../troubleshooting/restore-issues.md)

## Quick Reference

| Platform | Default Terminal | Multi-Tab | Config Location |
|----------|-----------------|-----------|-----------------|
| macOS | Terminal.app | No | `~/.azlin/config.toml` |
| Windows | Windows Terminal | Yes | `%USERPROFILE%\.azlin\config.toml` |
| WSL | Windows Terminal | Yes | `~/.azlin/config.toml` |
| Linux | gnome-terminal | No | `~/.azlin/config.toml` |

## See Also

- [Configuration Reference](../reference/configuration-reference.md)
- [How to Restore Sessions](../how-to/restore-sessions.md)
- [Troubleshooting Guide](../troubleshooting/restore-issues.md)
