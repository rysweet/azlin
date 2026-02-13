# WSL2 Setup Walkthrough - Azure CLI Detection

Step-by-step tutorial showing the Azure CLI detection and auto-fix feature in action.

## Tutorial Overview

**What you'll learn**:
- How azlin detects Windows Azure CLI in WSL2
- How to use the interactive installation
- How to verify the fix is working
- How to handle edge cases

**Time required**: 10 minutes

**Prerequisites**:
- WSL2 installed on Windows
- azlin installed (`pip install azlin`)

## Scenario 1: First-Time Setup (Windows CLI Only)

### Starting State

You have Windows Azure CLI installed, but no Linux Azure CLI:

```powershell
# In Windows PowerShell
az version
# Works in Windows

# In WSL2
which az
# Output: /mnt/c/Program Files (x86)/Microsoft SDKs/Azure/CLI2/wbin/az.cmd
```

### Step 1: Run azlin

```bash
$ azlin list
```

### Step 2: Detection Prompt Appears

You'll see:

```
┌───────────────────────────────────────────────────────────┐
│ Azure CLI Setup Required for WSL2                         │
├───────────────────────────────────────────────────────────┤
│                                                            │
│ azlin detected you're running in WSL2 with the Windows    │
│ Azure CLI. This causes subprocess deadlock issues.        │
│                                                            │
│ Current configuration:                                     │
│   Environment:  WSL2 (Ubuntu 22.04)                       │
│   Windows CLI:  /mnt/c/Program Files/.../az.cmd          │
│   Linux CLI:    Not installed                             │
│                                                            │
│ The Linux Azure CLI is required for reliable operation.   │
│                                                            │
│ Options:                                                   │
│   [Y] Install Linux Azure CLI now (recommended)           │
│   [N] I'll install it manually                            │
│   [?] Tell me more about this issue                       │
│   [Q] Quit                                                 │
│                                                            │
└───────────────────────────────────────────────────────────┘

Your choice [Y/n/?/q]:
```

### Step 3: Request More Information (Optional)

Press `?`:

```
┌───────────────────────────────────────────────────────────┐
│ Why Linux Azure CLI is Required                           │
├───────────────────────────────────────────────────────────┤
│                                                            │
│ Problem:                                                   │
│   Windows Azure CLI (az.cmd) in WSL2 causes:             │
│   • Subprocess pipe deadlock (commands hang)              │
│   • Path resolution issues                                │
│   • Performance degradation                               │
│                                                            │
│ Solution:                                                  │
│   Install native Linux Azure CLI:                         │
│   • No subprocess issues                                   │
│   • Full WSL2 integration                                 │
│   • Better performance                                     │
│                                                            │
│ What will happen:                                          │
│   1. Download installation script from Microsoft          │
│   2. Install Azure CLI to /usr/bin/az                     │
│   3. Verify installation works                            │
│   4. Configure azlin to use Linux CLI                     │
│                                                            │
│ Installation time: ~30-60 seconds                          │
│ Requires: sudo access                                      │
│                                                            │
│ Press any key to continue...                               │
└───────────────────────────────────────────────────────────┘
```

Press any key to return to options.

### Step 4: Choose Automatic Installation

Press `Y`:

```
Installing Linux Azure CLI...

[1/4] Downloading installation script...
      Source: https://aka.ms/InstallAzureCLIDeb
      ✓ Downloaded (15.2 KB)

[2/4] Running installation script...
      This requires sudo access. You may be prompted for your password.

[sudo] password for user:
```

Enter your password:

```
      ✓ Package sources added
      ✓ GPG key imported
      ✓ Package list updated
      ✓ azure-cli installed

[3/4] Verifying installation...
      Running: az version
      ✓ Azure CLI 2.45.0 installed successfully

[4/4] Configuring azlin...
      ✓ Linux CLI detected at /usr/bin/az
      ✓ Configuration updated

┌───────────────────────────────────────────────────────────┐
│ ✓ Installation Complete!                                   │
├───────────────────────────────────────────────────────────┤
│                                                            │
│ Linux Azure CLI is now installed and configured.          │
│                                                            │
│ Next steps:                                                │
│   1. Authenticate: az login                               │
│   2. List VMs: azlin list                                 │
│   3. Connect: azlin connect myvm                          │
│                                                            │
│ Installation completed in 42 seconds.                      │
│                                                            │
└───────────────────────────────────────────────────────────┘

Continuing to list VMs...
```

### Step 5: Verify It Works

```bash
$ azlin list

┌─────────────┬──────────┬────────────┬─────────────┐
│ VM Name     │ Status   │ Location   │ Size        │
├─────────────┼──────────┼────────────┼─────────────┤
│ dev-vm      │ Running  │ eastus     │ Standard_D2 │
│ test-vm     │ Stopped  │ westus2    │ Standard_D4 │
└─────────────┴──────────┴────────────┴─────────────┘

# Works perfectly! No hangs.
```

### Verification

Check your setup:

```bash
$ which az
/usr/bin/az

$ az version
{
  "azure-cli": "2.45.0",
  "azure-cli-core": "2.45.0",
  ...
}

$ azlin --version
azlin 2.3.0
```

**Success!** You now have Linux Azure CLI working with azlin.

---

## Scenario 2: Manual Installation Choice

### Step 1: Choose Manual Installation

```bash
$ azlin list
```

When prompted, press `N`:

```
You chose manual installation.

To install Linux Azure CLI manually:

  # Ubuntu/Debian
  curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

  # Verify installation
  az version

After installation, run azlin again.

Exiting...
```

### Step 2: Install Manually

```bash
$ curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Wait for installation...
Reading package lists... Done
Building dependency tree... Done
...
Setting up azure-cli (2.45.0-1~jammy) ...

# Verify
$ az version
{
  "azure-cli": "2.45.0",
  ...
}
```

### Step 3: Run azlin Again

```bash
$ azlin list

# This time, no prompt - goes straight to listing VMs
┌─────────────┬──────────┬────────────┬─────────────┐
│ VM Name     │ Status   │ Location   │ Size        │
...
```

**Success!** Manual installation detected automatically.

---

## Scenario 3: Both CLIs Installed (PATH Priority Issue)

### Starting State

You have both Windows and Linux Azure CLI:

```bash
$ which az
/mnt/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd

$ which -a az
/mnt/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd
/usr/bin/az
```

Windows CLI is found first (wrong).

### Step 1: Run azlin with Debug

```bash
$ azlin --debug list

[DEBUG] Environment: WSL2 detected
[DEBUG] Windows CLI found: /mnt/c/Program Files/.../az.cmd
[DEBUG] Linux CLI found: /usr/bin/az
[DEBUG] Using explicit path: /usr/bin/az
[DEBUG] Subprocess: Draining pipes to prevent deadlock

┌─────────────┬──────────┬────────────┬─────────────┐
│ VM Name     │ Status   │ Location   │ Size        │
...
```

**Good news**: azlin automatically uses Linux CLI even though Windows CLI appears first in PATH.

### Step 2: Fix PATH Order (Optional)

To avoid confusion:

```bash
$ nano ~/.bashrc

# Add at the end:
export PATH="/usr/local/bin:/usr/bin:$PATH"

# Save and reload
$ source ~/.bashrc

$ which az
/usr/bin/az  # Now correct!
```

### Verification

```bash
$ azlin list
# Works without any warnings
```

---

## Scenario 4: Installation Failure (Network Error)

### Step 1: Network Issue During Installation

```bash
$ azlin list

# Choose Y for automatic installation
[1/4] Downloading installation script...
      Source: https://aka.ms/InstallAzureCLIDeb
      ✗ Download failed: Connection timeout

┌───────────────────────────────────────────────────────────┐
│ Installation Failed                                        │
├───────────────────────────────────────────────────────────┤
│                                                            │
│ Could not download Azure CLI installation script.         │
│                                                            │
│ Possible causes:                                           │
│   • Network connectivity issues                           │
│   • Firewall blocking Microsoft servers                   │
│   • Corporate proxy settings                              │
│                                                            │
│ Solutions:                                                 │
│                                                            │
│ 1. Check network connection:                               │
│    curl -I https://aka.ms/InstallAzureCLIDeb             │
│                                                            │
│ 2. Configure proxy (if behind corporate firewall):        │
│    export HTTP_PROXY=http://proxy.company.com:8080       │
│    export HTTPS_PROXY=http://proxy.company.com:8080      │
│                                                            │
│ 3. Manual installation:                                    │
│    See: docs/how-to/azure-cli-wsl2-setup.md               │
│                                                            │
│ Press R to retry, M for manual install, or Q to quit      │
│                                                            │
└───────────────────────────────────────────────────────────┘

Your choice [R/m/q]:
```

### Step 2: Configure Proxy and Retry

```bash
# Press Q to exit, configure proxy
$ export HTTP_PROXY=http://proxy.company.com:8080
$ export HTTPS_PROXY=http://proxy.company.com:8080

# Try again
$ azlin list

# Press Y, installation should succeed now
[1/4] Downloading installation script...
      Source: https://aka.ms/InstallAzureCLIDeb
      ✓ Downloaded (15.2 KB)
...
```

### Alternative: Manual Installation

If automatic installation keeps failing:

```bash
# Download script manually
$ wget https://aka.ms/InstallAzureCLIDeb -O install_cli.sh

# Review it (good security practice)
$ less install_cli.sh

# Run it
$ sudo bash install_cli.sh
```

---

## Scenario 5: Disabling Auto-Detection

### Use Case

You want to skip detection prompts (advanced users):

```bash
# Disable auto-install prompts
$ export AZLIN_NO_AUTO_INSTALL=1

# Or skip WSL2 detection entirely
$ export AZLIN_SKIP_WSL_DETECTION=1

# Add to ~/.bashrc for persistence
$ echo 'export AZLIN_NO_AUTO_INSTALL=1' >> ~/.bashrc
```

### Testing Configuration Override

```bash
# Force specific CLI path
$ export AZLIN_CLI_PATH=/usr/bin/az

# Verify it's used
$ azlin --debug list | grep "CLI path"
[DEBUG] CLI path: /usr/bin/az (explicit override)
```

---

## Real-World Example: Complete Workflow

Let's walk through a complete workflow from scratch.

### Initial State

```bash
# Fresh WSL2 Ubuntu installation
$ uname -r
5.10.16.3-microsoft-standard-WSL2

# Windows Azure CLI installed (via Windows installer)
$ which az
/mnt/c/Program Files (x86)/Microsoft SDKs/Azure/CLI2/wbin/az.cmd

# No azlin yet
$ azlin
Command 'azlin' not found
```

### Step 1: Install azlin

```bash
$ pip install azlin

Collecting azlin
  Downloading azlin-2.3.0-py3-none-any.whl
...
Successfully installed azlin-2.3.0

$ azlin --version
azlin 2.3.0
```

### Step 2: First Run

```bash
$ azlin list
```

Detection prompt appears (as shown in Scenario 1).

### Step 3: Choose Automatic Installation

Press `Y`, enter sudo password, wait 45 seconds.

```
✓ Installation Complete!
Continuing to list VMs...
```

### Step 4: Authenticate

```bash
$ az login

A web browser has been opened at https://login.microsoftonline.com/...
Please continue the login in the web browser.

# Complete authentication in browser

[
  {
    "cloudName": "AzureCloud",
    "id": "xxxx-xxxx-xxxx-xxxx",
    "isDefault": true,
    ...
  }
]
```

### Step 5: Use azlin Normally

```bash
# List VMs
$ azlin list

# Create VM
$ azlin create dev-vm --size Standard_D2s_v3

# Connect
$ azlin connect dev-vm

# Everything works!
```

### Step 6: Verify Health

```bash
# Check setup
$ which az
/usr/bin/az

$ az version
{
  "azure-cli": "2.45.0",
  ...
}

# Test performance
$ time azlin list
real    0m1.234s  # Fast!
```

---

## Key Takeaways

1. **Automatic detection** - azlin detects WSL2 and CLI issues automatically
2. **Interactive prompts** - Clear options with explanations
3. **One-click installation** - Install Linux CLI in under a minute
4. **Manual control** - Override with environment variables or config
5. **Robust error handling** - Clear messages for network/permission issues

## Next Steps

- [Configure preferences](../reference/configuration-reference.md)
- [Troubleshoot issues](../troubleshooting/azure-cli-wsl2-issues.md)
- [Learn advanced features](../how-to/azure-cli-wsl2-setup.md)

## Testing Checklist

Use this checklist to verify the feature works on your system:

```bash
# 1. Environment detection
uname -r | grep -i microsoft
# ✓ Should match if in WSL2

# 2. CLI detection
which az
which -a az
# ✓ Should find all Azure CLI installations

# 3. Auto-installation
azlin list  # Follow prompts
# ✓ Should offer installation if needed

# 4. Verification
az version
azlin --debug list
# ✓ Should use /usr/bin/az

# 5. Performance
time azlin list
# ✓ Should complete in 1-3 seconds (not hang)

# 6. Configuration override
export AZLIN_CLI_PATH=/usr/bin/az
azlin list
# ✓ Should use explicit path
```

---

## Related Documentation

- [How-To: Azure CLI WSL2 Setup](../how-to/azure-cli-wsl2-setup.md) - Configuration options
- [Reference: Azure CLI Detection](../reference/azure-cli-detection.md) - Technical details
- [Troubleshooting: WSL2 Issues](../troubleshooting/azure-cli-wsl2-issues.md) - Problem solving

---

**Tutorial complete!** You now understand how Azure CLI detection works in azlin.
