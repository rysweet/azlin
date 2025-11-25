# azlin snapshot create

Create a point-in-time snapshot of a VM's OS disk for backup and recovery.

## Description

The `azlin snapshot create` command captures the complete state of a VM's OS disk, creating a backup that can be restored later. Snapshots are incremental and cost-effective, storing only the changes since the previous snapshot.

Use snapshots for:
- **Backup before updates**: Snapshot before major system changes
- **Safe experimentation**: Try risky operations with easy rollback
- **Version control for VMs**: Save different VM configurations
- **Disaster recovery**: Quick recovery from system failures

Snapshots are named automatically with timestamps: `{vm-name}-snapshot-{timestamp}`

## Usage

```bash
azlin snapshot create VM_NAME [OPTIONS]
```

## Arguments

- `VM_NAME` - Name of the VM to snapshot (required)

## Options

| Option | Description |
|--------|-------------|
| `--resource-group, --rg TEXT` | Azure resource group |
| `--config PATH` | Config file path |
| `-h, --help` | Show help message |

## Examples

### Create Basic Snapshot

```bash
# Create snapshot of VM
azlin snapshot create my-dev-vm
```

**Output:**
```
Creating snapshot of 'my-dev-vm'...
  VM Status: Running
  Disk Size: 30 GB
  Creating snapshot...

Snapshot created successfully!
  Name: my-dev-vm-snapshot-20251124-143022
  Size: 30 GB
  Location: eastus
  Cost: ~$0.06/day

Restore with:
  azlin snapshot restore my-dev-vm my-dev-vm-snapshot-20251124-143022
```

### Snapshot with Specific Resource Group

```bash
azlin snapshot create prod-server --rg azlin-prod-rg
```

### Snapshot Before Risky Operation

```bash
# 1. Create safety snapshot
azlin snapshot create my-vm

# 2. Perform risky operation
azlin connect my-vm
sudo rm -rf /var/log/*  # Dangerous operation

# 3. If something breaks, restore:
#    azlin snapshot restore my-vm my-vm-snapshot-20251124-143022
```

### Scheduled Snapshots (via cron)

```bash
# Create daily snapshot script
cat > ~/snapshot-daily.sh << 'EOF'
#!/bin/bash
azlin snapshot create production-vm
# Keep only last 7 snapshots
azlin snapshot list production-vm | tail -n +8 | awk '{print $1}' | xargs -I {} azlin snapshot delete {} --force
EOF

chmod +x ~/snapshot-daily.sh

# Add to crontab (daily at 2 AM)
crontab -e
# 0 2 * * * ~/snapshot-daily.sh
```

### Snapshot Multiple VMs

```bash
# Snapshot all VMs in resource group
for vm in $(azlin list --format names); do
    echo "Snapshotting $vm..."
    azlin snapshot create $vm
done
```

## Common Use Cases

### Pre-Update Backup

```bash
# Before system updates
azlin snapshot create my-vm

# Perform updates
azlin connect my-vm
sudo apt update && sudo apt upgrade -y
exit

# Test everything works
# If issues: azlin snapshot restore my-vm {snapshot-name}
```

### Development Checkpoints

```bash
# Save working state before major changes
azlin snapshot create dev-vm  # Working state

# Make changes to codebase
# ...test...

# If broken, restore working state
azlin snapshot restore dev-vm dev-vm-snapshot-20251124-120000
```

### Experiment Safely

```bash
# 1. Create snapshot
azlin snapshot create experiment-vm

# 2. Try experimental changes
azlin connect experiment-vm
# Install beta software, change configs, etc.

# 3. If experiment fails
azlin snapshot restore experiment-vm {snapshot-name}

# 4. If experiment succeeds
# Keep the VM, delete old snapshot
azlin snapshot delete {snapshot-name}
```

### Compliance and Audit

```bash
# Weekly compliance snapshots
azlin snapshot create compliance-server

# Tag for audit trail
# Snapshots automatically include timestamp
# Keep for required retention period
```

### Pre-Deployment Checkpoint

```bash
# Before deploying new version
azlin snapshot create production-api

# Deploy new version
azlin connect production-api
cd /opt/app && git pull && systemctl restart app

# Monitor for issues
# If problems: quick rollback
#   azlin snapshot restore production-api {snapshot-name}
```

## Snapshot Naming Convention

Snapshots are automatically named:
```
{vm-name}-snapshot-{YYYYMMDD}-{HHMMSS}
```

**Examples**:
- `my-dev-vm-snapshot-20251124-143022`
- `production-api-snapshot-20251124-020000`
- `gpu-trainer-snapshot-20251123-235959`

The timestamp ensures:
- Unique names (no conflicts)
- Chronological sorting
- Easy identification of snapshot age

## VM State During Snapshot

**VM can remain running** during snapshot creation:
- No downtime required
- Snapshot captures disk state at start of operation
- Safe for production VMs
- Takes 1-5 minutes typically

**Best practice**: For critical systems, create snapshots during low-traffic periods for consistency.

## Snapshot Size and Cost

### Size
- **First snapshot**: Full disk size (30-1024 GB)
- **Subsequent snapshots**: Only changes (incremental)
- Compressed and deduplicated by Azure

**Example progression**:
```
Day 1: 30 GB disk → 30 GB snapshot
Day 2: 2 GB changes → 2 GB snapshot
Day 3: 1 GB changes → 1 GB snapshot
Total: 33 GB stored
```

### Cost
- **Standard snapshots**: ~$0.05/GB/month ($0.002/GB/day)
- **Premium snapshots**: ~$0.12/GB/month ($0.004/GB/day)

**Example costs**:
| Disk Size | Monthly Cost | Daily Cost |
|-----------|--------------|------------|
| 30 GB | $1.50 | $0.05 |
| 128 GB | $6.40 | $0.21 |
| 512 GB | $25.60 | $0.85 |
| 1 TB | $51.20 | $1.71 |

**Tip**: Delete old snapshots to reduce costs. Keep only what you need for recovery.

## Troubleshooting

### Snapshot Creation Failed

**Error**: "Failed to create snapshot: Operation timed out"

**Solution**: Check VM and disk status:
```bash
# Check VM status
azlin list --vm my-vm

# Verify VM is accessible
azlin connect my-vm --command "echo 'VM is up'"

# Retry snapshot
azlin snapshot create my-vm
```

### Insufficient Permissions

**Error**: "Insufficient permissions to create snapshot"

**Solution**: Ensure you have Contributor role:
```bash
# Test authentication
azlin auth test

# Re-authenticate if needed
az login
```

### Quota Exceeded

**Error**: "Snapshot quota exceeded"

**Solution**: Delete old snapshots:
```bash
# List all snapshots
azlin snapshot list my-vm

# Delete old ones
azlin snapshot delete my-vm-snapshot-20251001-120000
```

### VM Not Found

**Error**: "VM 'xyz' not found"

**Solution**: Check VM name and resource group:
```bash
# List VMs
azlin list

# Use correct name
azlin snapshot create correct-vm-name
```

## Best Practices

### Snapshot Retention Policy

Implement a retention strategy:

```bash
# Example: Keep 7 daily, 4 weekly, 3 monthly

# Daily snapshots (keep 7)
azlin snapshot create my-vm
# Delete snapshots older than 7 days

# Weekly snapshots (keep 4) - run on Sundays
# Delete snapshots older than 28 days

# Monthly snapshots (keep 3) - run on 1st
# Delete snapshots older than 90 days
```

### Snapshot Before Changes

Always snapshot before:
- Operating system updates
- Application deployments
- Configuration changes
- Database migrations
- Security patches
- Experimental installations

### Test Restores

Periodically test snapshot restores:

```bash
# 1. Clone VM for testing
azlin clone my-vm --name restore-test

# 2. Create snapshot of test VM
azlin snapshot create restore-test

# 3. Restore from snapshot
azlin snapshot restore restore-test {snapshot-name}

# 4. Verify restore works
azlin connect restore-test

# 5. Clean up test VM
azlin destroy restore-test
```

### Document Snapshots

Keep notes on what each snapshot represents:

```bash
# Create snapshot with descriptive naming
# (use VM tags or external documentation)
azlin snapshot create my-vm  # Creates: my-vm-snapshot-20251124-143022
# Note: "Pre-Python 3.13 upgrade"
```

## Performance Considerations

### Snapshot Creation Time

- **Small disks (< 64 GB)**: 1-3 minutes
- **Medium disks (64-256 GB)**: 3-5 minutes
- **Large disks (256-1024 GB)**: 5-15 minutes

### Impact on VM Performance

- Minimal impact during snapshot
- Slight I/O slowdown (< 5%)
- No downtime required
- Safe for production systems

### Parallel Snapshots

You can snapshot multiple VMs simultaneously:

```bash
# Snapshot all VMs in parallel
azlin list --format names | xargs -P 5 -I {} azlin snapshot create {}
```

## Related Commands

- [azlin snapshot list](list.md) - List all snapshots for a VM
- [azlin snapshot restore](restore.md) - Restore VM from snapshot
- [azlin snapshot delete](delete.md) - Delete old snapshots
- [azlin clone](../vm/clone.md) - Clone VM (includes snapshot)

## See Also

- [Snapshots Overview](../../snapshots/index.md) - Understanding snapshots
- [Scheduled Backups](../../snapshots/scheduled.md) - Automated backup strategies
- [Disaster Recovery](../../snapshots/restore.md) - Recovery procedures
