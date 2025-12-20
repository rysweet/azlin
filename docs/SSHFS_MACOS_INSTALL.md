# Installing SSHFS on macOS

**IMPORTANT:** The standard `sshfs` package from Homebrew is Linux-only. macOS requires a special version.

## Installation Steps

### Step 1: Install macFUSE (Required)

\`\`\`bash
brew install --cask macfuse
\`\`\`

**After installation:**
1. Go to **System Settings → Privacy & Security**
2. Scroll down to find "macFUSE"
3. Click **Allow** to enable the system extension
4. **Restart your terminal**

### Step 2: Install sshfs-mac

\`\`\`bash
# Add the FUSE tap
brew tap gromgit/fuse

# Install sshfs for macOS
brew install sshfs-mac
\`\`\`

### Step 3: Verify Installation

\`\`\`bash
which sshfs
sshfs --version
\`\`\`

## Common Issues

**"sshfs: Linux is required"**
- You installed the wrong package (`sshfs` instead of `sshfs-mac`)
- Uninstall and use `sshfs-mac` from the gromgit/fuse tap

**macFUSE kernel extension blocked**
- macOS security blocks it by default
- Must manually allow in System Settings → Privacy & Security
- Restart terminal after allowing

**"Operation not permitted"**
- macFUSE not properly enabled
- Restart Mac after enabling in System Settings

## Alternative Methods

If sshfs doesn't work, azlin provides alternatives:
- \`azlin cp\` - Copy files between local and VM
- Direct SSH: \`ssh azureuser@vm\` then work remotely
- VS Code Remote-SSH: \`azlin code <vm>\`

## Usage

Once installed, azlin will automatically offer to mount NFS storage when connecting to VMs:

\`\`\`bash
azlin connect amplihack

📁 This VM uses NFS shared storage: rysweethomedir17
Mount /home/azureuser locally to ~/azlinhome? [Y/n]: y
\`\`\`
