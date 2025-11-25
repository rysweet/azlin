# azlin snapshot delete

Permanently delete a snapshot to free up storage and reduce costs.

## Usage

```bash
azlin snapshot delete SNAPSHOT_NAME [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--force` | Skip confirmation prompt |
| `--resource-group, --rg TEXT` | Azure resource group |
| `-h, --help` | Show help message |

## Examples

### Delete Snapshot

```bash
azlin snapshot delete my-vm-snapshot-20251001-020000
```

**Output:**
```
Delete snapshot 'my-vm-snapshot-20251001-020000'?

Size: 30 GB
Created: 2025-10-01 02:00:00 (54 days ago)
Cost savings: ~$1.50/month

⚠ This cannot be undone

Type 'DELETE' to confirm: DELETE

Deleting snapshot...
Snapshot deleted successfully.
```

### Force Delete

```bash
azlin snapshot delete my-vm-snapshot-20251001-020000 --force
```

### Cleanup Old Snapshots

```bash
# Delete snapshots older than 30 days
azlin snapshot list my-vm | grep "2025-10" | awk '{print $1}' | \
    xargs -I {} azlin snapshot delete {} --force
```

## Common Use Cases

### Cost Reduction

```bash
# List snapshots to find expensive old ones
azlin snapshot list my-vm

# Delete old snapshots
azlin snapshot delete my-vm-snapshot-20250901-020000
```

### Retention Policy

```bash
# Keep only last 7 snapshots
azlin snapshot list my-vm | tail -n +8 | awk '{print $1}' | \
    xargs -I {} azlin snapshot delete {} --force
```

## Important Notes

**WARNING**: Deleted snapshots cannot be recovered
- No undo operation
- No Azure recycle bin
- Ensure you don't need the snapshot before deleting

## Related Commands

- [azlin snapshot list](list.md) - List snapshots before deleting
- [azlin snapshot create](create.md) - Create new snapshots
- [azlin snapshot restore](restore.md) - Restore from snapshot
