# Quick Start Guide


Get up and running with azlin in 5 minutes.

## Prerequisites

- Azure account ([create free account](https://azure.microsoft.com/free/))
- Azure CLI installed and configured (`az login`)
- Python 3.12 or later

## Step 1: Install azlin

```bash
# Run directly from GitHub (no installation needed)
uvx --from git+https://github.com/rysweet/azlin azlin new
```

Or install permanently:

```bash
uv tool install git+https://github.com/rysweet/azlin
```

## Step 2: Login to Azure

```bash
az login
```

## Step 3: Create Your First VM

```bash
azlin new --name myproject
```

azlin will:

1. ✓ Create an Ubuntu 24.04 VM
2. ✓ Install 12 development tools
3. ✓ Configure SSH access
4. ✓ Start tmux session
5. ✓ Connect you automatically

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

# Check VM status
azlin status

# View distributed metrics
azlin top
```

## What's Next?

- **[Create Shared Storage](../storage/creating.md)** - Set up NFS storage
- **[Transfer Files](../file-transfer/copy.md)** - Copy files to/from VMs
- **[Manage Multiple VMs](../vm-lifecycle/index.md)** - Scale your fleet
- **[Set Up Authentication](../authentication/service-principal.md)** - Use service principals

## Troubleshooting

**Issue: Quota exceeded**

See [Quota Management](../advanced/quotas.md) for solutions.

**Issue: Connection timeout**

Check [Connection Issues](../troubleshooting/connection.md).

**Issue: Authentication failed**

See [Authentication Errors](../troubleshooting/auth-errors.md).

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

# Storage
azlin storage create           # Create NFS storage
azlin storage mount            # Mount storage

# Monitoring
azlin status                   # VM status
azlin w                        # Who is logged in
azlin top                      # Distributed metrics
azlin cost                     # Cost tracking
```

---

**Next:** [Learn core concepts](concepts.md) or [dive into VM lifecycle](../vm-lifecycle/index.md)
