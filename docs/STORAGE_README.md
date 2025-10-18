# Azure Files NFS Storage - README Section

## Storage

Share home directories across multiple VMs using Azure Files NFS.

### Create Storage

Create an Azure Files NFS storage account for shared home directories:

```bash
# Create 100GB Premium storage
azlin storage create myteam-shared --size 100 --tier Premium

# Create 500GB Standard storage (cheaper)
azlin storage create backups --size 500 --tier Standard
```

**Storage Tiers**:
- **Premium**: $0.153/GB/month, high IOPS, low latency
- **Standard**: $0.0184/GB/month, standard IOPS

**Example costs** for 100GB:
- Premium: ~$15.30/month
- Standard: ~$1.84/month

### List Storage Accounts

View all NFS storage accounts in your resource group:

```bash
azlin storage list

# Example output:
# Storage Accounts in azlin-rg:
# ================================================================================
# 
# myteam-shared
#   Endpoint: myteam-shared.blob.core.windows.net:/myteam-shared/share
#   Size: 100GB
#   Tier: Premium
#   Location: westus2
# 
# Total: 1 storage account(s)
```

### Check Storage Status

Show detailed information including usage and connected VMs:

```bash
azlin storage status myteam-shared

# Example output:
# Storage Account: myteam-shared
# ================================================================================
#   Endpoint: myteam-shared.blob.core.windows.net:/myteam-shared/share
#   Location: westus2
#   Tier: Premium
# 
# Capacity:
#   Total: 100GB
#   Used: 12GB (12.0%)
#   Available: 88GB
# 
# Cost:
#   Monthly: $15.30
# 
# Connected VMs:
#   - azlin-20251017-162042-05
#   - azlin-20251017-153211-22
```

### Mount Storage on VM

Mount the NFS storage to a VM's home directory. This replaces the local home directory with the shared storage, allowing multiple VMs to share the same files:

```bash
azlin storage mount myteam-shared --vm my-dev-vm

# Example output:
# Getting storage account 'myteam-shared'...
# Getting VM 'my-dev-vm'...
# Mounting storage on VM...
#   Storage: myteam-shared
#   Endpoint: myteam-shared.blob.core.windows.net:/myteam-shared/share
#   VM: azlin-20251017-162042-05 (20.12.34.56)
# ✓ Existing home directory backed up to: /home/azureuser.backup
# ✓ Storage mounted successfully on azlin-20251017-162042-05
# 
# The VM now uses shared storage for its home directory.
# All files in /home/azureuser are now shared across any VM with this storage mounted.
```

**Use Cases**:
- **Team Collaboration**: Multiple team members work in the same environment
- **Seamless Switching**: Switch between VMs without losing work
- **Consistent Tools**: Same tools and configs across all VMs
- **Multi-VM Workflows**: Run different tasks on different VMs with shared data

### Unmount Storage

Unmount the shared storage and restore the local home directory:

```bash
azlin storage unmount --vm my-dev-vm

# Example output:
# Getting VM 'my-dev-vm'...
# Unmounting storage from VM...
#   VM: azlin-20251017-162042-05 (20.12.34.56)
# ✓ Local home directory restored from: /home/azureuser.backup
# ✓ Storage unmounted successfully from azlin-20251017-162042-05
# 
# The VM now uses its local disk for the home directory.
```

### Delete Storage

Delete a storage account. By default, this prevents deletion if VMs are still connected:

```bash
# Safe delete (checks for connected VMs)
azlin storage delete myteam-shared

# Force delete even if VMs are connected
azlin storage delete old-storage --force
```

**WARNING**: Deleting a storage account permanently deletes all data.

### Complete Workflow Example

```bash
# 1. Create shared storage for your team
azlin storage create team-dev --size 200 --tier Premium

# 2. Create multiple VMs
azlin new --name vm1
azlin new --name vm2

# 3. Mount storage on both VMs
azlin storage mount team-dev --vm vm1
azlin storage mount team-dev --vm vm2

# Now both VMs share the same home directory!
# Changes made on vm1 are immediately visible on vm2

# 4. Check what's using the storage
azlin storage status team-dev

# 5. When done, unmount from VMs
azlin storage unmount --vm vm1
azlin storage unmount --vm vm2

# 6. Delete the storage
azlin storage delete team-dev
```

### Security

- **VNet Only**: NFS endpoints are only accessible within the Azure VNet
- **No Public Access**: Storage cannot be accessed from the internet
- **SSH Auth**: All mount operations use SSH key authentication
- **Backup Safety**: Existing home directories are always backed up before mounting

### Technical Details

The storage feature consists of two modules:
- **storage_manager.py**: Manages Azure Files NFS storage accounts
- **nfs_mount_manager.py**: Handles NFS mounting via SSH

All operations are:
- **Atomic**: Operations either fully succeed or fully roll back
- **Idempotent**: Safe to run multiple times
- **Validated**: Input validation before any Azure operations
- **Logged**: Full logging for debugging

For architecture details, see [DESIGN_NFS_STORAGE.md](docs/DESIGN_NFS_STORAGE.md).
