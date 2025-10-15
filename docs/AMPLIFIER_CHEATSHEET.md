# azlin Cheat Sheet for Microsoft Amplifier Development

Quick reference for using azlin to work on the [microsoft/amplifier](https://github.com/microsoft/amplifier) repository.

---

## 🚀 Quick Start

### Create a VM with Amplifier repo

```bash
# Create VM and clone amplifier repo
azlin new --repo https://github.com/microsoft/amplifier

# Create with custom name
azlin new --name amplifier-dev --repo https://github.com/microsoft/amplifier

# Create larger VM for performance
azlin new --vm-size Standard_D4s_v3 --repo https://github.com/microsoft/amplifier
```

**What happens:**
- Provisions Ubuntu 24.04 VM on Azure
- Installs 12 dev tools (Docker, Node.js, Python, Go, Rust, etc.)
- Clones amplifier repo to `~/amplifier`
- Auto-connects via SSH with tmux
- **Total time**: ~5-7 minutes

---

## 📋 Common Workflows

### Daily Development

```bash
# Morning: Start your VM
azlin start amplifier-dev
azlin connect amplifier-dev

# Work in the repo (you're already in ~/amplifier)
cd ~/amplifier
git pull
npm install
npm test

# Evening: Stop to save costs
exit  # Exit SSH session
azlin stop amplifier-dev
```

**💰 Cost savings**: ~50% vs running 24/7

---

### Multiple Amplifier Environments

```bash
# Development environment
azlin new --name amp-dev --repo https://github.com/microsoft/amplifier

# Testing environment
azlin new --name amp-test --repo https://github.com/microsoft/amplifier

# Feature branch work
azlin new --name amp-feature-x --repo https://github.com/microsoft/amplifier

# List all your VMs
azlin list
```

---

## 🏷️ Organize with Tags

```bash
# Tag VMs for organization
azlin tag amp-dev --add project=amplifier env=dev
azlin tag amp-test --add project=amplifier env=test

# List all amplifier VMs
azlin list --tag project=amplifier

# Track costs by project
azlin cost --by-tag project
```

---

## 🔧 Environment Configuration

### Set up environment variables

```bash
# Set individual variables
azlin env set amp-dev NODE_ENV=development
azlin env set amp-dev DEBUG=amplifier:*

# Set from .env file
azlin env set amp-dev --file .env

# List current environment
azlin env list amp-dev

# Export for backup
azlin env export amp-dev > amplifier.env
```

---

## 📁 File Management

### Copy files to/from VM

```bash
# Copy local file to VM
azlin cp config.json amp-dev:~/amplifier/

# Copy from VM to local
azlin cp amp-dev:~/amplifier/output.log ./

# Copy directory
azlin cp -r ./datasets amp-dev:~/amplifier/data/

# Preview transfer
azlin cp --dry-run large-file.zip amp-dev:~/
```

---

## 💾 Backup & Snapshots

### Create snapshots before risky operations

```bash
# Before major upgrade
azlin snapshot create amp-dev --name "before-node-upgrade"

# List snapshots
azlin snapshot list amp-dev

# Restore if something breaks
azlin snapshot restore amp-dev --snapshot "before-node-upgrade"

# Clean up old snapshots
azlin snapshot delete amp-dev --snapshot "old-snapshot"
```

---

## 📊 Monitoring

### Check VM status and logs

```bash
# Show detailed status
azlin status

# View system logs
azlin logs amp-dev

# View boot logs
azlin logs amp-dev --boot

# Follow logs in real-time
azlin logs amp-dev --follow

# Check who's logged in
azlin w

# View running processes
azlin ps
```

---

## 🔄 Multiple VMs / Team Work

### Batch operations

```bash
# Stop all dev VMs at end of day
azlin batch stop --tag env=dev

# Start all amplifier VMs
azlin batch start --tag project=amplifier

# Run command on all VMs
azlin batch command "git pull" --tag project=amplifier

# Sync dotfiles to all VMs
azlin batch sync --tag project=amplifier
```

---

## 🎯 Templates for Amplifier

### Save configuration as template

```bash
# Create template for amplifier development
azlin template create --name amplifier-dev \
  --vm-size Standard_D4s_v3 \
  --region westus2 \
  --repo https://github.com/microsoft/amplifier

# Use template later
azlin new --template amplifier-dev --name amp-dev-2

# Share template with team
azlin template export amplifier-dev > amplifier-template.yaml

# Team member imports it
azlin template import amplifier-template.yaml
azlin new --template amplifier-dev
```

---

## 🧹 Cleanup

### Remove resources when done

```bash
# Preview what would be deleted
azlin destroy amp-dev --dry-run

# Delete specific VM
azlin kill amp-dev

# Delete VM and resource group
azlin destroy amp-dev --delete-rg

# Find and remove orphaned resources
azlin cleanup --dry-run
azlin cleanup --delete
```

---

## 💡 Pro Tips

### 1. Auto-reconnect on disconnect

If your SSH session drops, azlin will prompt:
```
Your session to amp-dev was disconnected, do you want to reconnect? [Y|n]:
```

Press `Y` to reconnect automatically!

### 2. Use tmux sessions

Sessions persist across disconnects:
```bash
# Connect to specific tmux session
azlin connect amp-dev --tmux-session work

# Disconnect: Ctrl+B, then D
# Reconnect: azlin connect amp-dev
```

### 3. Sync dotfiles

```bash
# Setup once
mkdir -p ~/.azlin/home
cp ~/.bashrc ~/.vimrc ~/.gitconfig ~/.azlin/home/

# Auto-syncs to all new VMs
azlin new --repo https://github.com/microsoft/amplifier
```

### 4. Cost tracking

```bash
# Check current month costs
azlin cost --by-vm

# Historical costs
azlin cost --from 2025-01-01 --to 2025-01-31

# By tag
azlin cost --by-tag project
```

### 5. SSH keys rotation

```bash
# Rotate keys for security
azlin keys rotate

# Update all VMs
azlin keys rotate --all-vms
```

---

## 🎓 Example: Full Amplifier Development Session

```bash
# 1. Create VM with amplifier
azlin new --name amp-work --repo https://github.com/microsoft/amplifier

# 2. (Auto-connected via SSH, already in ~/amplifier)
# Set up environment
export NODE_ENV=development
npm install
npm test

# 3. Tag for organization
# (In another terminal)
azlin tag amp-work --add project=amplifier env=dev owner=yourname

# 4. Create snapshot before changes
azlin snapshot create amp-work --name "fresh-install"

# 5. Work on feature...
git checkout -b feature/new-thing
# ... code ...
git commit -m "Add feature"

# 6. Copy results locally
azlin cp amp-work:~/amplifier/build ./local-build

# 7. End of day - stop VM
exit
azlin stop amp-work

# 8. Next day - resume
azlin start amp-work
azlin connect amp-work
# Continue work (tmux session preserved)
```

---

## 📦 Amplifier-Specific Setup

### After VM creation, in SSH session:

```bash
# You're already in ~/amplifier
cd ~/amplifier

# Install dependencies
npm install

# Build
npm run build

# Run tests
npm test

# Start development server
npm run dev

# Lint
npm run lint
```

---

## 🆘 Troubleshooting

### VM won't start
```bash
azlin status  # Check current state
azlin start amp-dev  # Try starting
```

### Can't connect
```bash
azlin status  # Get IP and state
ssh azureuser@<ip>  # Manual connection test
```

### Out of disk space
```bash
# Check disk usage via logs
azlin logs amp-dev

# Or connect and check
azlin connect amp-dev
df -h
```

### High costs
```bash
# Check what's running
azlin list

# Stop unused VMs
azlin stop <vm-name>

# Find orphaned resources
azlin cleanup --dry-run
```

---

## 🔗 Quick Reference

| Task | Command |
|------|---------|
| Create VM with repo | `azlin new --repo https://github.com/microsoft/amplifier` |
| List VMs | `azlin list` |
| Connect to VM | `azlin connect <vm-name>` |
| Start VM | `azlin start <vm-name>` |
| Stop VM | `azlin stop <vm-name>` |
| Delete VM | `azlin kill <vm-name>` |
| View logs | `azlin logs <vm-name>` |
| Copy files | `azlin cp <src> <dest>` |
| Create snapshot | `azlin snapshot create <vm-name>` |
| Tag VM | `azlin tag <vm-name> --add key=value` |
| Set env var | `azlin env set <vm-name> KEY=value` |
| Check costs | `azlin cost --by-vm` |

---

## 📚 More Information

- **Full documentation**: Run `azlin --help`
- **Command help**: Run `azlin <command> --help`
- **GitHub**: https://github.com/rysweet/azlin

---

**Happy Amplifier development! 🚀**
