# Azure CLI WSL2 Auto-Detection and Fix

**Status**: Production Ready
**Introduced**: v2.3.0
**Type**: Automatic Detection Feature

## Overview

This feature automatically detects when you're running `azlin` in WSL2 with Windows Azure CLI installed, which causes Bastion tunnel connection failures. When detected, `azlin` offers to install the Linux version of Azure CLI to fix the problem.

## The Problem

When Windows Azure CLI is used from WSL2:

1. **Tunnel Binding**: The `az network bastion tunnel` command binds to Windows localhost (`127.0.0.1`)
2. **Network Isolation**: WSL2 has a separate network stack from Windows
3. **Connection Failure**: WSL2 cannot access Windows localhost
4. **Result**: All Bastion tunnel commands fail with timeout errors

## The Solution

`azlin` now automatically:

1. **Detects** WSL2 environment on startup
2. **Identifies** Windows Azure CLI usage (paths like `/mnt/c/...`)
3. **Prompts** for installation of Linux Azure CLI
4. **Installs** Linux version automatically (with your permission)
5. **Uses** explicit path to Linux CLI for all operations

## How It Works

### Automatic Detection

On every `azlin` startup in WSL2, the detection system checks:

- **Environment**: Is this WSL2? (checks `/proc/version`, `/run/WSL`, environment variables)
- **CLI Location**: Where is `az` command? (checks PATH resolution)
- **Problem State**: Is `az` pointing to Windows installation? (looks for `/mnt/c/` paths)

### Interactive Installation

When a problem is detected, you'll see:

```
═══════════════════════════════════════════════════════════════════════
AZURE CLI INSTALLATION REQUIRED
═══════════════════════════════════════════════════════════════════════

Ahoy! Ye be using Windows Azure CLI in WSL2.
This causes problems:
  - Bastion tunnels create on Windows localhost
  - WSL2 can't reach Windows localhost (separate network)
  - Result: Connection failures

Solution: Install Linux Azure CLI in WSL2
  - Downloads from: https://aka.ms/InstallAzureCLIDeb
  - Requires sudo permission
  - Takes ~2-3 minutes

Install Linux Azure CLI now? [y/N]:
```

**If you choose Yes**:
- Downloads official Microsoft installation script
- Runs installation with `sudo` (you'll be prompted for password)
- Verifies installation succeeded
- Continues with normal `azlin` operation

**If you choose No**:
- Provides manual installation instructions
- Exits gracefully
- You can run `azlin` again after manual installation

### Subprocess Pipe Fix

Additionally, the feature fixes a subprocess deadlock issue:

- **Problem**: Azure CLI writes continuous output that fills pipe buffers (64KB)
- **Solution**: Background threads drain stdout/stderr continuously
- **Result**: No more blocked tunnel processes

## User Benefits

### Before This Feature

```bash
$ azlin list
Context: MySubscription
Listing VMs in resource group: my-rg

⠇ Collecting tmux sessions from 3 VMs...
Failed to create tunnel for VM dev-vm-1 (attempt 1/3):
  Tunnel failed to become ready within 30 seconds
Failed to create tunnel for VM dev-vm-1 (attempt 2/3):
  Tunnel failed to become ready within 30 seconds
Failed to create tunnel for VM dev-vm-1 (attempt 3/3):
  Tunnel failed to become ready within 30 seconds
# ... repeated for all VMs ...
```

### After This Feature

```bash
$ azlin list

⚠️  Ahoy! Ye be using Windows Azure CLI in WSL2.
    The tunnel creates on Windows localhost, but WSL2
    can't reach it (separate network). Ye need Linux
    Azure CLI installed in WSL2.

Install Linux Azure CLI now? [y/N]: y

Starting installation... (requires sudo)
[sudo] password for user:
✓ Installation successful: /usr/bin/az

Ye may need to run 'az login' again in WSL2.

Context: MySubscription
Listing VMs in resource group: my-rg

⠹ Collecting tmux sessions from 3 VMs...
                    Azure VMs
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┓
┃ Session  ┃ Tmux Sessions   ┃ Status ┃ IP       ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━┩
│ dev-vm-1 │ main, test      │ Run    │ 10.0.0.4 │
│ dev-vm-2 │ No sessions     │ Run    │ 10.0.0.5 │
│ dev-vm-3 │ agent-001       │ Run    │ 10.0.0.6 │
└──────────┴─────────────────┴────────┴──────────┘
```

## Architecture

### Components

1. **cli_detector.py**: Environment and CLI detection
2. **cli_installer.py**: Interactive installation flow
3. **subprocess_helper.py**: Deadlock prevention
4. **Integration**: Hooks in `cli.py` and `bastion_manager.py`

### Detection Flow

```
azlin startup
    ↓
Is this WSL2?
    ↓ Yes
Is `az` Windows version? (/mnt/c/...)
    ↓ Yes
Display problem explanation
    ↓
Prompt for installation
    ↓ User chooses Yes
Download install script
    ↓
Execute with sudo
    ↓
Verify installation
    ↓
Continue with azlin
```

## Requirements

- **Environment**: WSL2 (Ubuntu, Debian, or compatible distro)
- **Permissions**: sudo access for installation
- **Network**: Internet connection for downloading Azure CLI
- **Disk Space**: ~100MB for Azure CLI installation

## FAQ

### Will this work on Windows directly?

No, this feature only activates in WSL2. If you're running `azlin` natively on Windows, it will use your Windows Azure CLI normally.

### Will this work on native Linux?

The feature only activates in WSL2 where the problem occurs. On native Linux, if you have Azure CLI installed, it will work normally without any prompts.

### What if I have both Windows and Linux Azure CLI installed?

The system will automatically prefer the Linux version when both are present. It uses an explicit path to `/usr/bin/az` instead of relying on PATH order.

### Do I need to authenticate again after installation?

Yes, you'll likely need to run `az login` in WSL2 after installing Linux Azure CLI. Your Windows authentication doesn't carry over to the Linux version.

### Can I skip the installation and use manual steps?

Yes! If you choose "No" when prompted, the system will show you the manual installation commands and exit. You can then install Azure CLI yourself and run `azlin` again.

### Will this affect my Windows Azure CLI?

No, installing Linux Azure CLI in WSL2 doesn't affect your Windows installation. They coexist independently.

## Related Documentation

- [How-To: Azure CLI WSL2 Setup](../how-to/azure-cli-wsl2-setup.md)
- [Reference: Azure CLI Detection API](../reference/azure-cli-detection.md)
- [Troubleshooting: Azure CLI WSL2 Issues](../troubleshooting/azure-cli-wsl2-issues.md)
- [Tutorial: WSL2 Setup Walkthrough](../tutorials/wsl2-setup-walkthrough.md)

## See Also

- [Azure CLI Official Documentation](https://docs.microsoft.com/en-us/cli/azure/)
- [WSL2 Documentation](https://docs.microsoft.com/en-us/windows/wsl/)
- [Azure Bastion Documentation](https://docs.microsoft.com/en-us/azure/bastion/)
