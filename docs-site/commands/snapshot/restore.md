# azlin snapshot restore

Restore a VM from a snapshot, replacing the current OS disk.

## Description

Restores a VM to a previous state by replacing its OS disk with one created from a snapshot. **WARNING**: This operation is destructive - all current data on the VM will be lost.

## Usage

```bash
azlin snapshot restore VM_NAME SNAPSHOT_NAME [OPTIONS]
```

## Arguments

- `VM_NAME` - Name of the VM to restore
- `SNAPSHOT_NAME` - Name of the snapshot to restore from

## Options

| Option | Description |
|--------|-------------|
| `--force` | Skip confirmation prompt |
| `--resource-group, --rg TEXT` | Azure resource group |
| `-h, --help` | Show help message |

## Examples

### Basic Restore

```bash
azlin snapshot restore my-vm my-vm-snapshot-20251124-143022
```

**Output:**
```
⚠ WARNING: This will replace the current OS disk!

VM: my-vm
Current Disk: my-vm-osdisk (30 GB)
Snapshot: my-vm-snapshot-20251124-143022 (30 GB, created 2025-11-24 14:30)

ALL CURRENT DATA WILL BE LOST

Type 'RESTORE' to confirm: RESTORE

Stopping VM...
Creating disk from snapshot...
Detaching current disk...
Attaching restored disk...
Starting VM...

Restore complete! VM is starting up.
SSH will be available in ~30 seconds.
```

### Force Restore (No Prompt)

```bash
azlin snapshot restore my-vm my-vm-snapshot-20251124-143022 --force
```

### Restore After Failed Update

```bash
# Update failed, need to rollback
azlin snapshot list my-vm
# Find snapshot from before update
azlin snapshot restore my-vm my-vm-snapshot-20251124-120000
```

## Common Use Cases

### Rollback Failed Deployment

```bash
# Deployment broke production
azlin snapshot restore prod-api prod-api-snapshot-20251124-020000

# Verify restoration
azlin connect prod-api
# Check app is working
```

### Recover from Misconfiguration

```bash
# Accidentally deleted important files
azlin snapshot restore my-vm my-vm-snapshot-20251123-235959

# SSH back in
azlin connect my-vm
# Files are restored
```

### Experiment Cleanup

```bash
# Tried experimental changes, want clean slate
azlin snapshot restore experiment-vm experiment-vm-snapshot-20251124-100000
```

## What Happens During Restore

1. **VM Stopped**: VM is deallocated
2. **Disk Created**: New disk created from snapshot
3. **Swap Disks**: Current disk detached, new disk attached
4. **VM Started**: VM boots from restored disk
5. **Old Disk**: Previous disk is kept as backup (deleted after 7 days)

**Duration**: 5-15 minutes depending on disk size

## Important Notes

###  Data Loss

- **Current disk data is LOST**
- Create a snapshot before restore if you need current data
- Old disk is temporarily kept but will be deleted

### Downtime

- VM must be stopped during restore
- Expect 5-15 minutes of downtime
- Plan restores during maintenance windows

### Saved Backup Disk

The replaced disk is saved temporarily as `{vm-name}-osdisk-backup-{timestamp}` for 7 days, allowing recovery if restore was mistake.

## Troubleshooting

### Restore Failed - Disk Size Mismatch

**Error**: "Snapshot disk size doesn't match VM"

**Solution**: This shouldn't happen with azlin snapshots, but if it does:
```bash
# Check snapshot details
azlin snapshot list my-vm

# Contact support if size mismatch occurs
```

### VM Won't Start After Restore

**Issue**: VM restored but won't boot

**Solution**:
```bash
# Check VM status
azlin list --vm my-vm

# View boot diagnostics
az vm boot-diagnostics get-boot-log --name my-vm --resource-group azlin-rg

# If corrupt, restore from different snapshot
azlin snapshot restore my-vm my-vm-snapshot-{earlier-date}
```

## Best Practices

### Always Have Recent Snapshot

```bash
# Before risky operations
azlin snapshot create my-vm

# Perform operation
# ...

# Restore if needed
azlin snapshot restore my-vm {snapshot-name}
```

### Test Restores

Periodically test that snapshots can be restored:

```bash
# Clone VM for testing
azlin clone my-vm --name restore-test

# Restore clone from snapshot
azlin snapshot restore restore-test {snapshot-name}

# Verify works
azlin connect restore-test

# Clean up
azlin destroy restore-test
```

### Document Snapshots

Know what each snapshot contains:

```bash
# Keep external notes
echo "my-vm-snapshot-20251124-143022: Pre-Python 3.13 upgrade" >> snapshots.txt
```

## Related Commands

- [azlin snapshot create](create.md) - Create snapshots
- [azlin snapshot list](list.md) - List available snapshots
- [azlin snapshot delete](delete.md) - Delete snapshots

## See Also

- [Disaster Recovery](../../snapshots/restore.md) - Recovery procedures
- [Backup Strategies](../../snapshots/scheduled.md) - Automated backups
