# Troubleshooting azlin restore Issues

Common problems and solutions fer the `azlin restore` command.

## Quick Diagnosis

Start with these commands:

```bash
# Check platform detection
azlin restore --dry-run

# Verify VMs are running
azlin list

# Check configuration
azlin config show

# Test SSH connectivity
ssh -i ~/.ssh/id_rsa azureuser@<vm-ip>
```

---

## No VMs Found

### Symptom
```
Error: No running VMs found in resource group
Run 'azlin list' to see available VMs
```

### Causes and Solutions

**Cause 1**: No VMs are running
```bash
# Check VM status
azlin list --all

# Start VMs
azlin start my-vm
```

**Cause 2**: Wrong resource group
```bash
# Check default resource group in config
cat ~/.azlin/config.toml | grep default_resource_group

# Override resource group
azlin restore --resource-group correct-rg
```

**Cause 3**: Azure authentication expired
```bash
# Re-authenticate
az login

# Verify access
az vm list --output table
```

---

## Terminal Not Opening

### Symptom
```
Error launching terminals: Terminal launch failed
Check terminal configuration in ~/.azlin/config.toml
```

### Platform-Specific Solutions

#### macOS

**Cause**: AppleScript execution disabled
```bash
# Enable accessibility permissions
# System Preferences → Security & Privacy → Privacy → Automation
# Check "Terminal" and "azlin"

# Test manual open
open -a Terminal
```

**Cause**: Terminal.app not in default location
```bash
# Find Terminal.app
mdfind "kMDItemFSName == 'Terminal.app'"

# Force using macOS terminal
azlin restore --terminal macos_terminal
```

#### Windows

**Cause**: Windows Terminal not installed
```powershell
# Install Windows Terminal
winget install Microsoft.WindowsTerminal

# Verify installation
where wt
```

**Cause**: wt.exe not in PATH
```powershell
# Add to PATH temporarily
$env:Path += ";C:\Users\$env:USERNAME\AppData\Local\Microsoft\WindowsApps"

# Or add permanent path in config
@"
windows_terminal_path = "C:\Users\$env:USERNAME\AppData\Local\Microsoft\WindowsApps\wt.exe"
"@ | Out-File -Append $HOME\.azlin\config.toml
```

#### WSL

**Cause**: Windows Terminal path not found
```bash
# Find Windows Terminal manually
find /mnt/c/Users -name "wt.exe" 2>/dev/null

# Add path to config
cat >> ~/.azlin/config.toml << 'EOF'
windows_terminal_path = "/mnt/c/Users/YourName/AppData/Local/Microsoft/WindowsApps/wt.exe"
EOF
```

**Cause**: Permission denied accessing Windows filesystem
```bash
# Check mount permissions
mount | grep /mnt/c

# Remount with correct permissions (temporary)
sudo mount -o remount,rw /mnt/c
```

#### Linux

**Cause**: gnome-terminal not installed
```bash
# Ubuntu/Debian
sudo apt install gnome-terminal

# Fedora
sudo dnf install gnome-terminal

# Verify
which gnome-terminal
```

**Cause**: DISPLAY variable not set
```bash
# Check DISPLAY
echo $DISPLAY

# Set if missing
export DISPLAY=:0

# Make permanent
echo 'export DISPLAY=:0' >> ~/.bashrc
```

---

## SSH Connection Failures

### Symptom
```
Terminal opens but SSH connection fails
ssh: connect to host 10.0.1.4 port 22: Connection refused
```

### Causes and Solutions

**Cause 1**: Wrong SSH key
```bash
# Verify SSH key exists
ls -la ~/.ssh/id_rsa

# Test SSH connection manually
ssh -i ~/.ssh/id_rsa azureuser@<vm-ip>

# Update config with correct key path
cat >> ~/.azlin/config.toml << 'EOF'
ssh_key_path = "~/.ssh/correct_key"
EOF
```

**Cause 2**: SSH key permissions too open
```bash
# Fix permissions
chmod 600 ~/.ssh/id_rsa
chmod 700 ~/.ssh

# Test again
azlin restore
```

**Cause 3**: Wrong username
```bash
# Check VM configuration
azlin config show

# Override in config
cat >> ~/.azlin/config.toml << 'EOF'
default_ssh_user = "azureuser"  # or your custom username
EOF
```

**Cause 4**: VM not accessible (firewall/NSG)
```bash
# Check VM network settings
az vm show --name my-vm --resource-group my-rg --query "networkProfile"

# Test connectivity
ping <vm-ip>
nc -zv <vm-ip> 22

# Check NSG rules
az network nsg rule list --nsg-name my-nsg --resource-group my-rg --output table
```

---

## Tmux Session Issues

### Symptom
```
Terminal opens but shows:
error connecting to /tmp/tmux-1000/default (No such file or directory)
```

### Solutions

**Cause 1**: Tmux not installed on VM
```bash
# SSH to VM manually
ssh -i ~/.ssh/id_rsa azureuser@<vm-ip>

# Install tmux
sudo apt install tmux    # Ubuntu/Debian
sudo yum install tmux    # RHEL/CentOS
```

**Cause 2**: Wrong session name
```bash
# Check existing sessions on VM
ssh -i ~/.ssh/id_rsa azureuser@<vm-ip> tmux list-sessions

# Update config with correct session name
cat >> ~/.azlin/config.toml << 'EOF'
[session_names]
"my-vm" = "correct-session-name"
EOF
```

**Cause 3**: Stale tmux socket
```bash
# SSH to VM
ssh -i ~/.ssh/id_rsa azureuser@<vm-ip>

# Kill tmux server
tmux kill-server

# Retry restore
azlin restore
```

---

## Multi-Tab Mode Issues (Windows Terminal)

### Symptom
```
Windows Terminal opens but only shows one tab
Expected: 3 tabs for 3 VMs
Actual: 1 tab
```

### Solutions

**Cause 1**: Multi-tab disabled in config
```bash
# Check config
cat ~/.azlin/config.toml | grep terminal_multi_tab

# Enable multi-tab
cat >> ~/.azlin/config.toml << 'EOF'
terminal_multi_tab = true
EOF
```

**Cause 2**: Windows Terminal version too old
```powershell
# Check version
wt --version

# Update Windows Terminal
winget upgrade Microsoft.WindowsTerminal
```

**Cause 3**: WSL path issues
```bash
# Check Windows Terminal path
ls -la /mnt/c/Users/*/AppData/Local/Microsoft/WindowsApps/wt.exe

# Update path in config if wrong
cat >> ~/.azlin/config.toml << 'EOF'
windows_terminal_path = "/mnt/c/Users/YourName/AppData/Local/Microsoft/WindowsApps/wt.exe"
EOF
```

---

## Timeout Errors

### Symptom
```
Error: Terminal launch timed out after 30 seconds
```

### Solutions

**Cause 1**: Slow network connection
```bash
# Increase timeout in config
cat >> ~/.azlin/config.toml << 'EOF'
restore_timeout = 90  # 90 seconds
EOF
```

**Cause 2**: VM slow to respond
```bash
# Check VM is fully booted
azlin status my-vm

# Wait fer VM to fully start
azlin wait my-vm

# Retry restore
azlin restore
```

**Cause 3**: WSL overhead
```bash
# WSL has additional overhead, increase timeout
cat >> ~/.azlin/config.toml << 'EOF'
restore_timeout = 120  # 2 minutes fer WSL
EOF
```

---

## Partial Restore Failures

### Symptom
```
Warning: 2 sessions failed to launch
Successfully restored 1 out of 3 sessions
```

### Solutions

**Cause**: Some VMs unreachable
```bash
# Check which VMs failed
azlin restore --dry-run

# Test each VM individually
azlin connect vm-1  # Works
azlin connect vm-2  # Fails
azlin connect vm-3  # Works

# Focus on failed VM
ssh -v -i ~/.ssh/id_rsa azureuser@<vm-2-ip>
# Look fer errors in verbose output
```

---

## Configuration Not Loading

### Symptom
```
Using default configuration (auto-detected)
Expected: Custom config from ~/.azlin/config.toml
```

### Solutions

**Cause 1**: Config file doesn't exist
```bash
# Check if config exists
ls -la ~/.azlin/config.toml

# Create if missing
mkdir -p ~/.azlin
touch ~/.azlin/config.toml
```

**Cause 2**: Config file syntax error
```bash
# Validate TOML syntax
python3 -c "import tomli; tomli.loads(open('~/.azlin/config.toml').read())"

# Check fer common errors:
# - Missing quotes around strings
# - Wrong section names
# - Duplicate keys
```

**Cause 3**: Config file permissions
```bash
# Fix permissions
chmod 644 ~/.azlin/config.toml

# Verify readable
cat ~/.azlin/config.toml
```

---

## Platform Detection Wrong

### Symptom
```
Detecting platform: Linux
Expected: WSL
```

### Solutions

**Cause**: WSL detection failed
```bash
# Check WSL markers
cat /proc/version | grep -i microsoft

# Force platform in config
cat >> ~/.azlin/config.toml << 'EOF'
platform_override = "wsl"
terminal_launcher = "windows_terminal"
EOF
```

---

## Diagnostic Commands Summary

| Problem | Command | Expected Output |
|---------|---------|-----------------|
| No VMs | `azlin list` | Shows running VMs |
| Platform detection | `azlin restore --dry-run` | Shows correct platform |
| Config loading | `azlin config show` | Shows config values |
| SSH connectivity | `ssh -i ~/.ssh/id_rsa user@ip` | SSH prompt |
| Terminal available | `which gnome-terminal` / `where wt` | Path to terminal |
| Tmux on VM | `ssh user@ip tmux list-sessions` | List of sessions |

---

## Getting Help

If yer issue isn't covered here:

1. **Run diagnostic mode**:
   ```bash
   azlin restore --dry-run --verbose
   ```

2. **Check logs**:
   ```bash
   # macOS/Linux
   cat ~/.azlin/logs/restore.log

   # Windows
   type %USERPROFILE%\.azlin\logs\restore.log
   ```

3. **File an issue**:
   - Include output from `azlin restore --dry-run`
   - Include platform (macOS/Windows/WSL/Linux)
   - Include error messages
   - Include config file (redact sensitive info)

## See Also

- [How to Restore Sessions](../how-to/restore-sessions.md)
- [Configuration Reference](../reference/configuration-reference.md)
- [Platform Setup Guide](../tutorials/platform-setup-restore.md)
