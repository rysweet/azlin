# How-To: Azure CLI WSL2 Setup

**Audience**: End users
**Time**: 5 minutes
**Skill Level**: Beginner

## Quick Start

If you're using `azlin` in WSL2 and encounter Bastion tunnel failures, this guide will help you fix the problem.

## Symptom

When you run `azlin list` or any command that uses Bastion tunnels, you see:

```bash
Failed to create tunnel for VM <vm-name> (attempt 1/3):
  Tunnel failed to become ready within 30 seconds
```

## Solution: Automatic Fix (Recommended)

1. **Run any azlin command** in WSL2:

   ```bash
   azlin list
   ```

2. **If the problem is detected**, you'll see a prompt:

   ```
   ═══════════════════════════════════════════════════════════
   AZURE CLI INSTALLATION REQUIRED
   ═══════════════════════════════════════════════════════════

   Install Linux Azure CLI now? [y/N]:
   ```

3. **Type `y` and press Enter**

4. **Enter your sudo password** when prompted

5. **Wait 2-3 minutes** for installation to complete

6. **Run `az login`** to authenticate with your Azure account in WSL2

7. **Done!** Run your `azlin` command again - it should work now

## Solution: Manual Installation

If you prefer to install manually:

### Step 1: Download Installation Script

```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

### Step 2: Verify Installation

```bash
which az
# Should show: /usr/bin/az (not /mnt/c/...)
```

### Step 3: Authenticate

```bash
az login
```

### Step 4: Test with azlin

```bash
azlin list
```

## Verification

After installation, verify everything works:

```bash
# Check Azure CLI location
which az
# Expected: /usr/bin/az

# Check Azure CLI version
az --version
# Expected: azure-cli  2.x.x

# Test Bastion tunnel (may take 30 seconds)
azlin list
# Expected: VM list with no tunnel errors
```

## Troubleshooting

### Installation Failed: Permission Denied

**Symptom**: Installation fails with "Permission denied"

**Solution**: Make sure you have sudo access:

```bash
sudo echo "Testing sudo..."
# If this works, retry installation
```

### Installation Failed: Network Timeout

**Symptom**: Download times out or fails

**Solution**: Check your internet connection and retry:

```bash
# Test connectivity
curl -I https://aka.ms/InstallAzureCLIDeb

# Retry installation
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

### Both Windows and Linux CLI Installed

**Symptom**: Both `/mnt/c/.../az` and `/usr/bin/az` exist

**Solution**: `azlin` automatically prefers Linux version. You can verify:

```bash
# Check which one azlin uses
azlin --version  # Will use /usr/bin/az
```

### Still Getting Tunnel Errors

**Symptom**: Tunnel failures persist after installation

**Solution**: See [Troubleshooting Guide](../troubleshooting/azure-cli-wsl2-issues.md) for detailed diagnostics.

## Related Documentation

- [Feature Overview](../features/azure-cli-wsl2-detection.md)
- [Technical Reference](../reference/azure-cli-detection.md)
- [Troubleshooting Guide](../troubleshooting/azure-cli-wsl2-issues.md)
