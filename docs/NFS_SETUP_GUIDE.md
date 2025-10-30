# NFS Home Directory Setup Guide

## Current Status: ✅ BOOTSTRAP COMPLETE

### ✅ What's Working
- NFS storage account `rysweethomedir` exists and is configured
- NFS feature is fully implemented in main branch (issue #72 merged)
- Auto-detection feature works (auto-selects when only one storage exists)
- All necessary commands are available (`azlin storage mount/unmount`)
- **Bootstrap is COMPLETE** - NFS share is populated and ready to use
- Config file is set with `default_nfs_storage = "rysweethomedir"`

### ⚠️ IMPORTANT: Config Protection
**DO NOT remove or comment out `default_nfs_storage` from ~/.azlin/config.toml**

This setting ensures new VMs automatically mount your shared NFS home directory.

## The Problem

When you create a VM with NFS enabled, this happens:
1. VM is created with basic Ubuntu defaults
2. NFS share is mounted to `/home/azureuser`
3. If NFS share is empty, the VM's home directory contents are copied to it

**BUT**: A new VM's home directory only has Ubuntu defaults, NOT your custom configuration from `~/.azlin/home` (SSH keys, .bashrc, tools, etc.).

The `~/.azlin/home` directory is only synced when NFS is NOT being used.

## The Solution: Bootstrap Process

To populate the NFS share with your configuration:

### Step 1: Free Up VM Quota (if needed)
```bash
# Check current VMs
az vm list --resource-group rysweet-linux-vm-pool --output table

# Delete unused VMs to free quota
az vm delete --name <vm-name> --resource-group rysweet-linux-vm-pool --yes
```

### Step 2: Create Bootstrap VM WITHOUT NFS
⚠️ **SKIP THIS STEP - Bootstrap already complete!**

If you need to re-bootstrap, temporarily remove `default_nfs_storage` from config.

```bash
# Create VM that will sync ~/.azlin/home
uv run python -m azlin new --name nfs-bootstrap --vm-size Standard_D2s_v3 --no-auto-connect
```

This VM will:
- Sync `~/.azlin/home` → `/home/azureuser` on the VM
- Include all your SSH keys, dotfiles, and configuration

### Step 3: Mount NFS Storage on Bootstrap VM
```bash
# Mount the NFS storage (copies home directory to NFS share)
uv run python -m azlin storage mount rysweethomedir --vm nfs-bootstrap
```

This will:
- Backup existing `/home/azureuser` on the VM
- Mount the NFS share
- Copy the backed-up home directory to the NFS share

### Step 4: Clean Up Bootstrap VM
```bash
# Delete the bootstrap VM
az vm delete --name nfs-bootstrap --resource-group rysweet-linux-vm-pool --yes
```

### Step 5: Enable Default NFS Storage
Edit `~/.azlin/config.toml` and add:
```toml
default_nfs_storage = "rysweethomedir"
```

### Step 6: Test with New VM
```bash
# Create a VM - it will automatically use NFS
uv run python -m azlin new --name test-nfs-vm --no-auto-connect

# The VM will auto-detect the NFS storage and mount it
# All your configuration will be available immediately
```

### Step 7: Verify Shared Home Directory
```bash
# Create a second VM
uv run python -m azlin new --name test-nfs-vm-2 --no-auto-connect

# Both VMs will share the same home directory
# Changes made on one VM are visible on the other
```

## Current Configuration

Your `~/.azlin/config.toml` is configured:
```toml
default_resource_group = "rysweet-linux-vm-pool"
default_region = "westus2"
default_vm_size = "Standard_E16as_v5"
default_nfs_storage = "rysweethomedir"  # ✅ ACTIVE - Do not remove!
```

**⚠️ WARNING**: Do NOT remove or comment out `default_nfs_storage`. This ensures all new VMs automatically use your shared NFS home directory.

## NFS Storage Details

**Account**: `rysweethomedir`
- **Endpoint**: `rysweethomedir.file.core.windows.net:/rysweethomedir/home`
- **Size**: 100GB Premium
- **Region**: westus2
- **Status**: Currently empty (0% used)

## Available Commands

```bash
# List storage accounts
azlin storage list

# Check storage status
azlin storage status rysweethomedir

# Mount storage on existing VM
azlin storage mount rysweethomedir --vm <vm-name>

# Unmount storage from VM
azlin storage unmount --vm <vm-name>

# Create new storage account
azlin storage create <name> --size 100 --tier Premium
```

## How It Works After Setup

Once the NFS share is populated:

1. **Create VM**: `azlin new --name my-vm`
   - Auto-detects `rysweethomedir` (only one storage)
   - Mounts NFS share instead of syncing home directory
   - VM immediately has all your configuration

2. **Multiple VMs**: All VMs share the same home directory
   - SSH keys work across all VMs
   - Configuration changes propagate instantly
   - Perfect for distributed workloads

3. **Manual Control**: Use `--nfs-storage` to override
   - `azlin new --nfs-storage rysweethomedir` (explicit)
   - `azlin new --nfs-storage ""` (disable NFS for this VM)

## Troubleshooting

### Quota Exceeded Error
If you see "QuotaExceeded" when creating VMs:
```bash
# List and delete old VMs
az vm list --resource-group rysweet-linux-vm-pool --output table
az vm delete --name <old-vm> --resource-group rysweet-linux-vm-pool --yes
```

### NFS Mount Fails
Check that:
1. VM is in the same region as storage (westus2)
2. VM is in the same resource group
3. VM is running before mounting

### SSH Keys Not Working
Verify `~/.azlin/home/.ssh/authorized_keys` exists and contains your public key:
```bash
cat ~/.azlin/home/.ssh/authorized_keys
```

## Architecture

```
┌─────────────────┐
│ ~/.azlin/home/  │
│ (local)         │
└────────┬────────┘
         │
         │ 1. Sync to bootstrap VM
         ▼
┌─────────────────┐
│ Bootstrap VM    │
│ /home/azureuser │
└────────┬────────┘
         │
         │ 2. Mount NFS & copy
         ▼
┌─────────────────────────┐
│ NFS Storage             │
│ rysweethomedir          │
│ (Azure Files Premium)   │
└────────┬────────────────┘
         │
         │ 3. Auto-mount on new VMs
         ▼
┌─────────────────┐     ┌─────────────────┐
│ VM 1            │     │ VM 2            │
│ /home/azureuser │ ◀─▶ │ /home/azureuser │
│ (shared)        │     │ (shared)        │
└─────────────────┘     └─────────────────┘
```

## Next Steps

1. Free up VM quota by deleting unused VMs
2. Create bootstrap VM to populate NFS share
3. Uncomment `default_nfs_storage` in config
4. Test with new VMs

All the code is already in place - you just need to populate the NFS share once!
