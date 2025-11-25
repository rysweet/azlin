# azlin prune

Prune inactive VMs based on age and idle time.

## Synopsis

```bash
azlin prune [OPTIONS]
```

## Description

Identifies and optionally deletes VMs that are:
- Older than --age-days (default: 1)
- Idle for longer than --idle-days (default: 1)
- Stopped/deallocated (unless --include-running)
- Without named sessions (unless --include-named)

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--resource-group, --rg TEXT` | Resource group | current |
| `--config PATH` | Config file path | - |
| `--age-days INTEGER` | Age threshold in days | `1` |
| `--idle-days INTEGER` | Idle threshold in days | `1` |
| `--dry-run` | Preview without deleting | `false` |
| `--force` | Skip confirmation | `false` |
| `--include-running` | Include running VMs | `false` |
| `--include-named` | Include named sessions | `false` |
| `-h, --help` | Show help | - |

## Examples

### Preview what would be deleted
```bash
azlin prune --dry-run
```

### Delete VMs idle 1+ days (default)
```bash
azlin prune
```

### Custom thresholds
```bash
azlin prune --age-days 7 --idle-days 3
```

### Force delete without confirmation
```bash
azlin prune --force
```

### Include running VMs
```bash
azlin prune --include-running --age-days 30
```

## Output Example

```
VM Pruning Analysis

Scanning VMs...
Found 8 VMs

Candidates for deletion:
  vm-test-123    Age: 5 days    Idle: 3 days    Status: Stopped
  vm-temp-456    Age: 10 days   Idle: 8 days    Status: Stopped
  vm-old-789     Age: 15 days   Idle: 15 days   Status: Stopped

Protected VMs:
  vm-prod-1      Named session: "production"
  vm-dev-main    Active (last used 2 hours ago)

Total to delete: 3 VMs
Estimated savings: $45/month

Continue? [y/N]: y

Deleting VMs...
✓ Deleted vm-test-123
✓ Deleted vm-temp-456
✓ Deleted vm-old-789

Prune complete! 3 VMs deleted.
```

## Protection Rules

VMs are **protected** if:
- They have named sessions (unless `--include-named`)
- They are running (unless `--include-running`)
- They were used within idle threshold
- They are tagged with `critical=true` or `production=true`

## Use Cases

### Regular cleanup
```bash
# Daily cron job
0 2 * * * azlin prune --force --age-days 7
```

### Pre-billing cleanup
```bash
# Last day of month
azlin prune --age-days 3 --idle-days 1 --dry-run
azlin prune --age-days 3 --idle-days 1
```

### Development environment
```bash
# Clean up test VMs
azlin prune --age-days 1 --force
```

### Production (conservative)
```bash
# Only very old, unused VMs
azlin prune --age-days 30 --idle-days 14 --dry-run
```

## Troubleshooting

### No VMs deleted

```
Total to delete: 0 VMs
```

**Reasons:**
- All VMs are actively used
- All VMs have named sessions
- Thresholds too strict

**Solution**: Adjust thresholds or list VMs manually:
```bash
azlin list
azlin status
```

### Important VM deleted

If a VM was accidentally deleted:
1. Restore from snapshot if available:
```bash
azlin snapshot list
azlin snapshot restore vm-name snapshot-name
```

2. Or recreate and sync:
```bash
azlin new --name vm-name
azlin sync vm-name
```

## Best Practices

1. **Always dry-run first**
```bash
azlin prune --dry-run
```

2. **Use named sessions for important VMs**
```bash
azlin session vm-prod-1 "production"
```

3. **Tag critical VMs**
```bash
azlin tag vm-prod-1 --add critical=true
```

4. **Regular automated cleanup**
```bash
# Cron job for development RG
0 2 * * * azlin prune --rg dev-rg --age-days 7 --force
```

## Related Commands

- [azlin autopilot](../autopilot/index.md) - Automated optimization
- [azlin kill](../vm/kill.md) - Delete specific VM
- [azlin killall](../vm/killall.md) - Delete all VMs
- [azlin status](../vm/status.md) - View VM activity
