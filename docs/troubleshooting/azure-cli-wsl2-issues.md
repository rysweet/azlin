# Azure CLI WSL2 Issues - Troubleshooting Guide

Common problems and solutions for Azure CLI in WSL2 environments.

## Quick Diagnostics

Run this command to diagnose your setup:

```bash
azlin --debug list 2>&1 | grep -i "azure cli\|wsl2\|subprocess"
```

Look for:
- `[DEBUG] Environment: WSL2 detected` - Confirms WSL2 detection
- `[DEBUG] Azure CLI: /usr/bin/az (Linux)` - Confirms Linux CLI
- `[DEBUG] Subprocess: Using explicit path` - Confirms fix is active

## Common Issues

### Issue 1: Commands Hang Indefinitely

**Symptoms**:
```bash
$ azlin list
# Hangs forever, no output, Ctrl+C required
```

**Cause**: Windows Azure CLI in WSL2 causes subprocess pipe deadlock.

**Diagnosis**:
```bash
# Check which Azure CLI you're using
which az
# If output is /mnt/c/Program Files/.../az.cmd - WRONG

# Check for Windows CLI
which az.cmd
# If found - Windows CLI is in PATH
```

**Solution**:

1. **Automatic fix**:
   ```bash
   # Run azlin - it will detect and offer to install
   azlin list
   # Follow prompts to install Linux CLI
   ```

2. **Manual fix**:
   ```bash
   # Install Linux Azure CLI
   curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

   # Verify installation
   which az
   # Output should be: /usr/bin/az (NOT az.cmd)

   # Test it works
   az version
   ```

3. **Force explicit path**:
   ```bash
   # Set environment variable
   export AZLIN_CLI_PATH=/usr/bin/az

   # Add to ~/.bashrc or ~/.zshrc for persistence
   echo 'export AZLIN_CLI_PATH=/usr/bin/az' >> ~/.bashrc
   ```

**Verification**:
```bash
# Should complete quickly now
azlin list
```

### Issue 2: Installation Fails with Network Error

**Symptoms**:
```bash
$ azlin list
[ERROR] Failed to download Azure CLI installation script
```

**Cause**: Network connectivity issues or firewall blocking.

**Diagnosis**:
```bash
# Test connectivity to Microsoft servers
curl -I https://aka.ms/InstallAzureCLIDeb
# Should return HTTP 302 or 200

# Test DNS resolution
nslookup packages.microsoft.com
```

**Solution**:

1. **Check proxy settings**:
   ```bash
   # If behind corporate proxy
   export HTTP_PROXY=http://proxy.company.com:8080
   export HTTPS_PROXY=http://proxy.company.com:8080

   # Retry installation
   azlin list
   ```

2. **Manual download and install**:
   ```bash
   # Download script manually
   wget https://aka.ms/InstallAzureCLIDeb -O install_azure_cli.sh

   # Review script (security best practice)
   less install_azure_cli.sh

   # Run installation
   sudo bash install_azure_cli.sh
   ```

3. **Use package manager directly**:
   ```bash
   # Ubuntu/Debian
   curl -sL https://packages.microsoft.com/keys/microsoft.asc | \
       gpg --dearmor | \
       sudo tee /etc/apt/trusted.gpg.d/microsoft.gpg > /dev/null

   echo "deb [arch=amd64] https://packages.microsoft.com/repos/azure-cli/ $(lsb_release -cs) main" | \
       sudo tee /etc/apt/sources.list.d/azure-cli.list

   sudo apt-get update
   sudo apt-get install azure-cli
   ```

**Verification**:
```bash
az version
```

### Issue 3: Permission Denied During Installation

**Symptoms**:
```bash
[ERROR] Installation failed: Permission denied
```

**Cause**: Insufficient permissions for system-wide installation.

**Diagnosis**:
```bash
# Check sudo access
sudo -v
# Should prompt for password, then succeed

# Check if user is in sudoers
groups
# Should include "sudo" or "wheel"
```

**Solution**:

1. **Run with sudo**:
   ```bash
   # If auto-install doesn't use sudo
   curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
   ```

2. **Add user to sudoers** (if needed):
   ```bash
   # Switch to root or admin user
   su -

   # Add user to sudo group
   usermod -aG sudo your_username

   # Log out and back in for group change to take effect
   exit
   ```

3. **User-local installation** (alternative):
   ```bash
   # Install in user directory (no sudo needed)
   pip install --user azure-cli

   # Add to PATH
   export PATH="$HOME/.local/bin:$PATH"
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
   ```

**Verification**:
```bash
az version
which az
```

### Issue 4: Wrong Azure CLI Version Detected

**Symptoms**:
```bash
$ azlin list
[WARNING] Windows Azure CLI detected: /mnt/c/Program Files/...
# But you've already installed Linux CLI
```

**Cause**: Windows CLI appears earlier in PATH than Linux CLI.

**Diagnosis**:
```bash
# Check PATH order
echo $PATH | tr ':' '\n' | grep -E 'mnt|usr/bin'

# Check which CLI is found first
which az
which -a az  # Show ALL matches
```

**Solution**:

1. **Reorder PATH**:
   ```bash
   # Put Linux paths before Windows paths
   export PATH="/usr/local/bin:/usr/bin:$PATH"

   # Make permanent
   echo 'export PATH="/usr/local/bin:/usr/bin:$PATH"' >> ~/.bashrc
   source ~/.bashrc
   ```

2. **Remove Windows CLI from PATH**:
   ```bash
   # Edit ~/.bashrc or ~/.profile
   # Remove or comment out lines that add Windows directories to PATH

   # Example - comment out this line:
   # export PATH="/mnt/c/Program Files/.../CLI2/wbin:$PATH"
   ```

3. **Use explicit path override**:
   ```bash
   # Force azlin to use Linux CLI
   export AZLIN_CLI_PATH=/usr/bin/az
   ```

**Verification**:
```bash
which az
# Should output: /usr/bin/az (NOT az.cmd)

azlin --debug list 2>&1 | grep "Azure CLI"
# Should show: [DEBUG] Azure CLI: /usr/bin/az (Linux)
```

### Issue 5: azlin Doesn't Detect WSL2

**Symptoms**:
```bash
# No installation prompt appears
# But you're definitely in WSL2
```

**Cause**: WSL2 detection failed or was skipped.

**Diagnosis**:
```bash
# Check if running in WSL2
uname -r
# Should contain "microsoft" or "WSL2"

cat /proc/version
# Should mention "Microsoft"

# Check if detection was skipped
echo $AZLIN_SKIP_WSL_DETECTION
# Should be empty or "0"
```

**Solution**:

1. **Verify WSL2 version**:
   ```bash
   # In Windows PowerShell (not WSL2)
   wsl --list --verbose
   # VERSION should show "2" for your distro
   ```

2. **Update WSL2 kernel**:
   ```bash
   # In Windows PowerShell
   wsl --update
   ```

3. **Force detection**:
   ```bash
   # Unset skip flag if set
   unset AZLIN_SKIP_WSL_DETECTION

   # Run azlin again
   azlin list
   ```

4. **Manual Linux CLI installation**:
   ```bash
   # If detection doesn't work, install manually
   curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
   export AZLIN_CLI_PATH=/usr/bin/az
   ```

**Verification**:
```bash
azlin --debug list 2>&1 | head -20
# Should show: [DEBUG] Environment: WSL2 detected
```

### Issue 6: Subprocess Timeout Errors

**Symptoms**:
```bash
$ azlin list
[ERROR] Azure CLI command timed out after 30 seconds
```

**Cause**: Slow network, large resource list, or CLI performance issues.

**Diagnosis**:
```bash
# Test CLI performance directly
time az vm list --output table

# Check Azure CLI responsiveness
time az account show
```

**Solution**:

1. **Increase timeout**:
   ```bash
   # Via environment variable
   export AZLIN_CLI_TIMEOUT=60  # 60 seconds

   # Via configuration file
   cat >> ~/.azlin/config.yaml << EOF
   azure_cli:
     command_timeout: 60
   EOF
   ```

2. **Filter results**:
   ```bash
   # List specific resource group (faster)
   azlin list --resource-group mygroup

   # Use caching
   azlin list --cache
   ```

3. **Check Azure CLI installation**:
   ```bash
   # Reinstall if corrupted
   sudo apt-get remove azure-cli
   curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
   ```

**Verification**:
```bash
# Should complete within timeout
time azlin list
```

### Issue 7: "CLI path not found" After Installation

**Symptoms**:
```bash
[ERROR] Azure CLI not found at configured path: /usr/bin/az
```

**Cause**: Installation succeeded but CLI not in expected location.

**Diagnosis**:
```bash
# Find where CLI was installed
which az
find /usr -name "az" 2>/dev/null
find $HOME -name "az" 2>/dev/null
```

**Solution**:

1. **Update configuration to actual path**:
   ```bash
   # If CLI is at different location
   export AZLIN_CLI_PATH=$(which az)

   # Make permanent
   echo "export AZLIN_CLI_PATH=$(which az)" >> ~/.bashrc
   ```

2. **Reinstall to standard location**:
   ```bash
   # Remove existing installation
   pip uninstall azure-cli  # If installed via pip

   # Install via official script (installs to /usr/bin)
   curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
   ```

3. **Add CLI to PATH**:
   ```bash
   # If installed in non-standard location
   export PATH="/path/to/azure-cli/bin:$PATH"
   ```

**Verification**:
```bash
which az
azlin list
```

## Advanced Diagnostics

### Enable Debug Logging

```bash
# Full debug output
export AZLIN_DEBUG_CLI=1
azlin list 2>&1 | tee azlin_debug.log

# Debug specific components
export AZLIN_DEBUG_DETECTION=1
export AZLIN_DEBUG_SUBPROCESS=1
```

### Collect Diagnostic Information

```bash
# System information
uname -a > diagnostics.txt
cat /proc/version >> diagnostics.txt

# Azure CLI information
which -a az >> diagnostics.txt
az version >> diagnostics.txt 2>&1

# PATH information
echo "=== PATH ===" >> diagnostics.txt
echo $PATH | tr ':' '\n' >> diagnostics.txt

# azlin debug output
azlin --debug list >> diagnostics.txt 2>&1

# Share diagnostics.txt when reporting issues
```

### Manual Testing

```bash
# Test environment detection
python3 -c "
import platform
print(f'System: {platform.system()}')
print(f'Release: {platform.release()}')
with open('/proc/version', 'r') as f:
    print(f'Kernel: {f.read().strip()}')
"

# Test CLI detection
python3 -c "
import shutil
print(f'which az: {shutil.which(\"az\")}')
print(f'which az.cmd: {shutil.which(\"az.cmd\")}')
"

# Test subprocess
python3 -c "
import subprocess
result = subprocess.run(['az', 'version'], capture_output=True, text=True, timeout=10)
print(f'Return code: {result.returncode}')
print(f'Output: {result.stdout[:200]}')
"
```

## Environment-Specific Issues

### Ubuntu 20.04 LTS

```bash
# May need to update package sources
sudo apt-get update
sudo apt-get install ca-certificates curl apt-transport-https lsb-release gnupg
```

### Ubuntu 22.04 LTS

```bash
# Should work out of the box
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

### Debian

```bash
# Use Debian-specific installation
sudo apt-get install apt-transport-https ca-certificates curl gnupg lsb-release
curl -sL https://packages.microsoft.com/keys/microsoft.asc | \
    gpg --dearmor | \
    sudo tee /etc/apt/trusted.gpg.d/microsoft.gpg > /dev/null
sudo apt-get update
sudo apt-get install azure-cli
```

## Getting Help

If issues persist:

1. **Check documentation**:
   - [How-To Guide](../how-to/azure-cli-wsl2-setup.md)
   - [Technical Reference](../reference/azure-cli-detection.md)

2. **Collect diagnostics** (see above)

3. **Report issue**:
   - GitHub: https://github.com/rysweet/azlin/issues
   - Include diagnostics.txt
   - Specify OS and WSL2 version

4. **Community support**:
   - Discussions: https://github.com/rysweet/azlin/discussions

## Prevention

### Best Practices

```bash
# 1. Keep Azure CLI updated
az upgrade

# 2. Use explicit paths
export AZLIN_CLI_PATH=/usr/bin/az

# 3. Verify installation
az version

# 4. Test before heavy usage
azlin list --resource-group test

# 5. Monitor performance
time azlin list
```

### Health Check

Add to your `~/.bashrc`:

```bash
# Azure CLI health check
function azlin_health_check() {
    echo "=== azlin Health Check ==="

    # Check WSL2
    if uname -r | grep -qi microsoft; then
        echo "✓ WSL2 detected"
    else
        echo "✗ Not WSL2"
    fi

    # Check Linux CLI
    if which az >/dev/null 2>&1; then
        cli_path=$(which az)
        if [[ "$cli_path" != *".cmd"* ]]; then
            echo "✓ Linux CLI: $cli_path"
        else
            echo "✗ Windows CLI: $cli_path"
        fi
    else
        echo "✗ Azure CLI not found"
    fi

    # Check Azure CLI version
    if az version >/dev/null 2>&1; then
        version=$(az version --output tsv --query '"azure-cli"' 2>/dev/null)
        echo "✓ Azure CLI version: $version"
    else
        echo "✗ Azure CLI not working"
    fi

    # Check azlin
    if command -v azlin >/dev/null 2>&1; then
        echo "✓ azlin installed"
    else
        echo "✗ azlin not found"
    fi
}

# Run on shell startup (optional)
# azlin_health_check
```

## Related Documentation

- [How-To: Azure CLI WSL2 Setup](../how-to/azure-cli-wsl2-setup.md)
- [Reference: Azure CLI Detection](../reference/azure-cli-detection.md)
- [Tutorial: WSL2 Setup Walkthrough](../tutorials/wsl2-setup-walkthrough.md)

---

**Need more help?** Open an issue with diagnostic output attached.
