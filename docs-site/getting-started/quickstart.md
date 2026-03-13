# Quick Start Guide


Get up and running with azlin in 5 minutes.

## Prerequisites

- Azure account ([create free account](https://azure.microsoft.com/free/))
- Azure CLI installed and configured (`az login`)

## Step 1: Install azlin

```bash
# Download pre-built binary (recommended)
curl -sSL https://github.com/rysweet/azlin/releases/latest/download/azlin-linux-x86_64.tar.gz | tar xz -C ~/.local/bin
```

Or run without installing:

```bash
uvx --from git+https://github.com/rysweet/azlin azlin new
```

See [Installation](installation.md) for all options including macOS, Cargo, and pip.

## Step 2: Login to Azure

```bash
az login
```

## Step 3: Create Your First VM

```bash
azlin new --name myproject
```

azlin will:

1. Create an Ubuntu 24.04 VM
2. Install 12 development tools
3. Configure SSH access
4. Start tmux session
5. Connect you automatically

**Total time: 4-7 minutes**

## Step 4: Verify VM

Once connected, verify the tools:

```bash
# Check Docker
docker --version

# Check Python
python3 --version

# Check Node.js
node --version

# List all installed tools
which docker az gh git node python3 rustc go dotnet
```

## Step 5: Explore Commands

```bash
# List all your VMs
azlin list

# Check VM health with Four Golden Signals
azlin health

# View distributed metrics
azlin top

# Keep azlin up to date
azlin self-update
```

## What's Next?

- **[Create Shared Storage](../storage/creating.md)** - Set up NFS storage
- **[GUI Forwarding](../advanced/gui-forwarding.md)** - Run remote GUI apps locally
- **[Set Up Authentication](../authentication/service-principal.md)** - Use service principals

## Troubleshooting

**Issue: Quota exceeded**

Check Azure quota limits with `az vm list-usage --location <region>`.

**Issue: Connection timeout**

Verify SSH connectivity and that the VM's public IP is accessible.

**Issue: Authentication failed**

Run `az login` to refresh your Azure credentials. See [Service Principal Auth](../authentication/service-principal.md) for automated setups.

## Quick Reference

### Essential Commands

```bash
# VM Lifecycle
azlin new --name myvm          # Create VM
azlin list                     # List VMs
azlin connect myvm             # Connect to VM
azlin stop myvm                # Stop VM
azlin start myvm               # Start VM
azlin destroy myvm             # Delete VM

# GUI Forwarding
azlin connect --x11 myvm      # X11 forwarding for lightweight GUI apps
azlin gui myvm                 # Full VNC desktop session

# Storage
azlin storage create           # Create NFS storage
azlin storage mount            # Mount storage

# Monitoring
azlin health                   # VM health dashboard
azlin status                   # VM status
azlin w                        # Who is logged in
azlin top                      # Distributed metrics
azlin cost                     # Cost tracking

# Maintenance
azlin self-update              # Update azlin to latest version
```

---

**Next:** [Learn core concepts](concepts.md) or [dive into VM lifecycle](../vm-lifecycle/index.md)
