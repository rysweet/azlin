# azlin storage unmount

Unmount NFS storage from a VM and restore the local home directory.

## Description

The `azlin storage unmount` command removes the NFS storage mount from a VM and restores the original local home directory from backup. This is useful when you want to:

- Work with local storage instead of shared storage
- Disconnect a VM from team workspace
- Troubleshoot storage issues
- Prepare a VM for snapshot or cloning

The original home directory is restored from the backup created during the mount operation.

## Usage

```bash
azlin storage unmount --vm VM_NAME [OPTIONS]
```

## Options

| Option | Description | Required |
|--------|-------------|----------|
| `--vm TEXT` | VM name or identifier | Yes |
| `--resource-group, --rg TEXT` | Azure resource group | No |
| `-h, --help` | Show help message | No |

## Examples

### Basic Unmount

```bash
# Unmount storage from VM
azlin storage unmount --vm my-dev-vm
```

**Output:**
```
Unmounting storage from VM 'my-dev-vm'...
  Stopping processes using mounted storage...
  Unmounting NFS share...
  Restoring local home directory from backup...
  Removing auto-mount configuration...

Storage unmounted successfully!

Local home directory restored from:
  ~/.azlin-backup-2025-11-24-143022/

VM is now using local storage.
```

### Unmount from Multiple VMs

```bash
# Disconnect all VMs from shared storage
for vm in dev-vm-1 dev-vm-2 dev-vm-3; do
    azlin storage unmount --vm $vm
done
```

### Unmount with Different Resource Group

```bash
# Unmount from VM in different resource group
azlin storage unmount --vm staging-vm --rg azlin-staging-rg
```

## Common Use Cases

### Switch from Shared to Local Storage

```bash
# 1. Unmount shared storage
azlin storage unmount --vm my-vm

# 2. Work with local files
azlin connect my-vm
# Files are now local - changes won't affect other VMs

# 3. Re-mount later if needed
azlin storage mount vm team-shared --vm my-vm
```

### Troubleshoot Storage Issues

```bash
# Unmount and remount to fix issues
azlin storage unmount --vm problematic-vm
azlin storage mount vm team-shared --vm problematic-vm
```

### Prepare for Snapshot

```bash
# Unmount before creating snapshot
azlin storage unmount --vm my-vm
azlin snapshot create my-vm
```

### Decommission Shared Workspace

```bash
# 1. Unmount from all VMs
azlin storage unmount --vm alice-vm
azlin storage unmount --vm bob-vm
azlin storage unmount --vm carol-vm

# 2. Delete storage
azlin storage delete team-workspace
```

## What Happens During Unmount

1. **Process Check**: Verifies no active processes are using mounted files
2. **Unmount**: Removes NFS mount from `/home/azureuser`
3. **Restore**: Copies backup directory back to home
4. **Cleanup**: Removes `/etc/fstab` auto-mount entry
5. **Metadata**: Updates VM tags to reflect unmounted state

## Backup Location

Original home directories are backed up during mount to:
```
~/.azlin-backup-{timestamp}/
```

Example: `~/.azlin-backup-2025-11-24-143022/`

The most recent backup is restored during unmount.

## Troubleshooting

### Device Busy Error

**Error**: "umount: target is busy"

**Solution**: Stop processes using mounted files:
```bash
azlin connect my-dev-vm

# Find processes using mount
lsof +D /home/azureuser

# Stop processes
kill <pid>

# Retry unmount
exit
azlin storage unmount --vm my-dev-vm
```

### No Backup Found

**Error**: "No backup directory found for restore"

**Solution**: Backup might have been deleted:
```bash
# Check for backups on VM
azlin connect my-dev-vm
ls -la ~/.azlin-backup-*/

# If no backup, unmount will create empty home directory
# You may need to reconfigure your environment
```

### Permission Denied

**Error**: "Permission denied during unmount"

**Solution**: Ensure VM has proper access:
```bash
# Reconnect and try again
azlin connect my-dev-vm --admin
sudo umount /home/azureuser

# Then complete unmount via azlin
exit
azlin storage unmount --vm my-dev-vm
```

## Important Notes

### Data Safety

- **Before unmount**: Ensure important data is backed up
- **After unmount**: Original backed-up files are restored
- **Shared changes lost**: Any changes made while mounted are NOT restored
- **Other VMs**: Other VMs still using the storage are not affected

### Data Flow

```
Mount: Local Home → Backup → NFS Mount
Unmount: Backup → Local Home (NFS changes lost)
```

Changes made while NFS was mounted stay in NFS storage and won't appear in restored local home.

### Save Important Data

If you have important data in the mounted storage:

```bash
# 1. Before unmounting, copy data from mounted home
azlin connect my-vm
cp -r ~/important-data /tmp/save-this/
exit

# 2. Unmount (restores old local home)
azlin storage unmount --vm my-vm

# 3. Copy data back to local home
azlin connect my-vm
cp -r /tmp/save-this/* ~/
```

## Related Commands

- [azlin storage mount](mount.md) - Mount storage on VMs
- [azlin storage status](status.md) - Check mounted storage
- [azlin storage list](list.md) - List storage accounts
- [azlin storage create](create.md) - Create storage account

## See Also

- [Storage Overview](../../storage/index.md) - Storage architecture
- [Mounting Guide](../../storage/mounting.md) - Best practices
