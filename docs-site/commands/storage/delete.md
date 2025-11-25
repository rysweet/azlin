# azlin storage delete

Delete an Azure Files NFS storage account.

## Description

The `azlin storage delete` command permanently removes a storage account and all its data. By default, it prevents deletion if VMs are still connected to protect against accidental data loss. Use `--force` to override this safety check.

**WARNING**: This operation is **irreversible**. All data in the storage account will be permanently deleted.

## Usage

```bash
azlin storage delete NAME [OPTIONS]
```

## Arguments

- `NAME` - Storage account name (required)

## Options

| Option | Description |
|--------|-------------|
| `--resource-group, --rg TEXT` | Azure resource group |
| `--force` | Force delete even if VMs are connected |
| `-h, --help` | Show help message |

## Examples

### Safe Delete (Default)

```bash
# Delete storage (fails if VMs connected)
azlin storage delete old-project
```

**Output (no VMs connected):**
```
Deleting storage account 'old-project'...

⚠ WARNING: This will permanently delete all data in 'old-project'

Storage Details:
  Size: 200 GB
  Tier: Premium
  Monthly Cost: $30.60
  Connected VMs: 0
  Created: 2025-10-15

Are you sure you want to delete this storage? [y/N]: y

Deleting storage account...
Storage account 'old-project' deleted successfully.
```

**Output (VMs connected):**
```
Cannot delete storage account 'team-shared'

The following VMs are still connected:
  - alice-vm
  - bob-vm  - carol-vm

To delete, first unmount from all VMs:
  azlin storage unmount --vm alice-vm
  azlin storage unmount --vm bob-vm
  azlin storage unmount --vm carol-vm

Or use --force to override (NOT RECOMMENDED)
```

### Force Delete

```bash
# Delete even with connected VMs (dangerous!)
azlin storage delete old-project --force
```

**Output:**
```
⚠⚠⚠ FORCE DELETE ⚠⚠⚠

Deleting storage 'old-project' with --force flag.
This will disconnect all VMs and delete all data.

Connected VMs (2):
  - dev-vm-1 (will be disconnected)
  - dev-vm-2 (will be disconnected)

WARNING: VMs will LOSE ACCESS to all data in this storage!

Type 'DELETE old-project' to confirm: DELETE old-project

Unmounting from all VMs...
Deleting storage account...
Storage account deleted.

⚠ VMs may need to reconnect to SSH
```

### Delete with Different Resource Group

```bash
azlin storage delete staging-storage --rg azlin-staging-rg
```

### Delete Multiple Storage Accounts

```bash
# Delete several old storage accounts
for storage in old-proj-1 old-proj-2 test-storage; do
    azlin storage delete $storage
done
```

## Common Use Cases

### Cleanup After Project

```bash
# 1. Check what's in storage
azlin storage status project-demo

# 2. Unmount from all VMs
azlin storage unmount --vm demo-vm-1
azlin storage unmount --vm demo-vm-2

# 3. Delete storage
azlin storage delete project-demo
```

### Remove Unused Storage

```bash
# 1. List all storage
azlin storage list

# 2. Find storage with 0 VMs
# 3. Check if data is needed
azlin storage status old-backup

# 4. Delete if not needed
azlin storage delete old-backup
```

### Emergency Cleanup

```bash
# Force delete when VMs are unrecoverable
azlin storage delete crashed-project --force
```

### Cost Reduction

```bash
# Delete expensive unused storage
azlin storage list

# Delete storage with high cost and 0 VMs
azlin storage delete expensive-unused
```

## Pre-Delete Checklist

Before deleting storage:

1. **Check connected VMs**
```bash
azlin storage status <name> | grep "Connected VMs"
```

2. **Verify data is backed up** (if important)
```bash
# Mount locally to backup
azlin storage mount local --mount-point ~/backup --storage <name>
# Copy important files
cp -r ~/backup/important-data /local/backup/
# Unmount
sudo umount ~/backup
```

3. **Unmount from all VMs**
```bash
# Get list of connected VMs
azlin storage status <name>

# Unmount each
azlin storage unmount --vm <vm-name>
```

4. **Confirm not in use**
```bash
# Double-check no VMs connected
azlin storage status <name>
```

5. **Delete**
```bash
azlin storage delete <name>
```

## What Gets Deleted

When you delete a storage account:

✅ **Deleted**:
- Storage account resource
- All files and directories
- All data and metadata
- NFS share configuration
- Access keys and credentials
- Cost allocation stops immediately

❌ **Not Deleted**:
- VMs (continue running)
- VM home directory backups (on VMs at `~/.azlin-backup-*`)
- Other storage accounts
- Snapshots of VMs

## Safety Features

### Default Protection

By default, deletion fails if:
- VMs are connected to storage
- Storage contains active mounts
- Storage is referenced in VM tags

### Confirmation Required

You must type 'y' or 'yes' to confirm deletion (or 'DELETE <name>' for force delete).

### Audit Trail

Deletions are logged for security auditing.

## Data Recovery

**Important**: Once deleted, storage **cannot be recovered**.

- No Azure-level recovery
- No "undelete" operation
- No backup unless you created one

**Recommendation**: For important data, backup before deletion:

```bash
# Backup approach 1: Copy to local
azlin storage mount local --mount-point ~/backup --storage important-data
tar -czf important-data-backup.tar.gz ~/backup/*
sudo umount ~/backup

# Backup approach 2: Copy to another storage
azlin storage create backup-storage --size 200 --tier Standard
# Mount both on a VM and copy between them

# Then delete original
azlin storage delete important-data
```

## Troubleshooting

### Cannot Delete - VMs Connected

**Error**: "Cannot delete storage with connected VMs"

**Solution**: Unmount from all VMs first:
```bash
# Check which VMs are connected
azlin storage status problem-storage

# Unmount each
azlin storage unmount --vm vm1
azlin storage unmount --vm vm2

# Try delete again
azlin storage delete problem-storage
```

### Cannot Delete - Permission Denied

**Error**: "Insufficient permissions to delete storage"

**Solution**: Ensure you have Contributor role:
```bash
# Check permissions
az role assignment list --all

# Need Contributor or Owner role
```

### Storage Not Found

**Error**: "Storage account 'xyz' not found"

**Solution**: Check name and resource group:
```bash
# List all storage
azlin storage list

# Try with correct resource group
azlin storage delete xyz --rg azlin-other-rg
```

### Force Delete Hangs

**Issue**: `--force` delete hangs on unmounting VMs

**Solution**: VMs may be stopped or unreachable:
```bash
# Check VM status
azlin list

# Start stopped VMs
azlin start vm1 vm2

# Or manually remove mount references and retry
```

## Important Warnings

### No Recovery

🚨 **CRITICAL**: Deleted storage cannot be recovered
- No Azure recycle bin
- No Microsoft support recovery
- Backups are your only option

### VM Impact with --force

⚠ When using `--force` with connected VMs:
- VMs lose access to mounted files immediately
- Running processes may crash
- SSH sessions to VMs may disconnect
- Applications using mounted storage will fail

### Cost Implications

💰 **Costs stop immediately** upon deletion
- No prorated refunds
- Charged up to deletion time
- Can recreate with same name immediately

### Name Reuse

The storage account name becomes available immediately after deletion and can be reused by anyone globally.

## When NOT to Delete

Don't delete storage if:
- Any doubt about data importance
- VMs are still running workloads
- No backup exists of important data
- Storage is referenced by other automation
- Team members might still need access

**Instead**: Unmount from VMs and keep storage for a grace period:
```bash
# Unmount but don't delete
azlin storage unmount --vm all-vms

# Set a reminder to delete in 30 days
# If no one complains, delete then
```

## Related Commands

- [azlin storage list](list.md) - List all storage accounts
- [azlin storage status](status.md) - View storage details before deletion
- [azlin storage unmount](unmount.md) - Unmount before deleting
- [azlin storage create](create.md) - Create new storage account

## See Also

- [Storage Overview](../../storage/index.md) - Understanding storage
- [Data Safety](../../storage/mounting.md) - Backup strategies
- [Cost Management](../../monitoring/cost.md) - Cost optimization
