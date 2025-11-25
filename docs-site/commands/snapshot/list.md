# azlin snapshot list

List all snapshots for a VM sorted by creation time.

## Usage

```bash
azlin snapshot list VM_NAME [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--resource-group, --rg TEXT` | Azure resource group |
| `-h, --help` | Show help message |

## Examples

### List Snapshots

```bash
azlin snapshot list my-dev-vm
```

**Output:**
```
Snapshots for my-dev-vm:

Name                                    Size    Created              Age
────────────────────────────────────────────────────────────────────────────
my-dev-vm-snapshot-20251124-143022      30 GB   2025-11-24 14:30:22  1 hour
my-dev-vm-snapshot-20251124-020000      30 GB   2025-11-24 02:00:00  12 hours
my-dev-vm-snapshot-20251123-020000      30 GB   2025-11-23 02:00:00  1 day
my-dev-vm-snapshot-20251122-020000      30 GB   2025-11-22 02:00:00  2 days
my-dev-vm-snapshot-20251121-020000      30 GB   2025-11-21 02:00:00  3 days

Total: 5 snapshots
Storage cost: ~$7.50/month ($0.25/day)
```

### Find Specific Snapshot

```bash
# List and grep for date
azlin snapshot list my-vm | grep 2025-11-24
```

### Get Snapshot Names Only

```bash
# For scripting
azlin snapshot list my-vm --format names
```

## Common Use Cases

### Check Available Restore Points

```bash
# See what snapshots exist before restore
azlin snapshot list production-vm

# Pick one to restore
azlin snapshot restore production-vm {snapshot-name}
```

### Audit Backup Status

```bash
# Check all VMs have recent snapshots
for vm in $(azlin list --format names); do
    echo "=== $vm ==="
    azlin snapshot list $vm | head -3
done
```

### Cleanup Old Snapshots

```bash
# List snapshots
azlin snapshot list my-vm

# Delete old ones
azlin snapshot delete my-vm-snapshot-20251001-020000
```

## Related Commands

- [azlin snapshot create](create.md) - Create new snapshot
- [azlin snapshot restore](restore.md) - Restore from snapshot
- [azlin snapshot delete](delete.md) - Delete snapshots
