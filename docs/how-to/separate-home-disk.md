# Separate Home Disk Guide

## Overview

azlin automatically provisions VMs with a separate 100GB managed disk mounted as `/home` (unless using NFS storage). This provides persistent, isolated storage for user data separate from the OS disk.

## Quick Start

```bash
# Create VM with default 100GB home disk
azlin new --name dev-vm

# Create VM with custom-sized home disk
azlin new --name data-vm --home-disk-size 200

# Disable home disk (use OS disk /home)
azlin new --name simple-vm --no-home-disk

# NFS storage (automatically disables home disk)
azlin new --name nfs-vm --nfs-storage my-storage
```

## Why Use Separate Home Disks?

### Benefits

1. **Persistent Storage**: Home directory data persists independently from OS disk
2. **Isolation**: Separate OS upgrades/reimaging from user data
3. **Flexibility**: Resize home disk without affecting OS
4. **Cost-Effective**: Standard HDD provides ample storage at low cost
5. **Automatic Setup**: No manual disk configuration required

### When to Use

- Development VMs needing persistent workspace
- VMs with large codebases or datasets
- Long-lived VMs where data preservation matters
- Testing environments with reproducible state

### When NOT to Use

- Ephemeral/disposable VMs (use `--no-home-disk`)
- VMs using NFS shared storage (NFS takes precedence)
- Cost-sensitive scenarios where OS disk is sufficient
- VMs that don't generate significant user data

## How It Works

When you run `azlin new`, the following happens automatically (unless using NFS):

### 1. Disk Creation

azlin creates an Azure Managed Disk:
- **Name**: `{vm-name}-home`
- **Size**: 100GB (default) or custom via `--home-disk-size`
- **Type**: Standard HDD (Standard_LRS)
- **Location**: Same region as VM

```bash
# Behind the scenes:
az disk create \
  --name dev-vm-home \
  --resource-group rg-azlin \
  --location westus2 \
  --size-gb 100 \
  --sku Standard_LRS
```

### 2. Disk Attachment

The disk is attached to the VM during provisioning:

```bash
# Behind the scenes:
az vm disk attach \
  --vm-name dev-vm \
  --resource-group rg-azlin \
  --name dev-vm-home
```

The disk appears as `/dev/disk/azure/scsi1/lun0` (LUN 0 is first data disk).

### 3. Automatic Formatting and Mounting

Cloud-init formats and mounts the disk on first boot:

```yaml
# cloud-init configuration
disk_setup:
  /dev/disk/azure/scsi1/lun0:
    table_type: gpt
    layout: true
    overwrite: false

fs_setup:
  - label: home_disk
    filesystem: ext4
    device: /dev/disk/azure/scsi1/lun0
    partition: auto

mounts:
  - [ /dev/disk/azure/scsi1/lun0-part1, /home, ext4, "defaults,nofail", "0", "2" ]
```

### 4. Persistent Configuration

The mount is added to `/etc/fstab` for persistence across reboots:

```
/dev/disk/azure/scsi1/lun0-part1 /home ext4 defaults,nofail 0 2
```

## Configuration Options

### `--home-disk-size`

Specify custom size in GB (default: 100):

```bash
# Small disk for lightweight development
azlin new --name dev-vm --home-disk-size 50

# Large disk for data-heavy workflows
azlin new --name ml-vm --home-disk-size 500
```

**Azure Limits**:
- Minimum: 1GB
- Maximum: 32TB (32768GB)

### `--no-home-disk`

Disable separate home disk, use OS disk `/home`:

```bash
# Ephemeral VM - no separate home disk needed
azlin new --name test-vm --no-home-disk
```

**When to use**:
- Short-lived test VMs
- Minimal storage needs
- Cost optimization
- OS disk is large enough

### NFS Storage Precedence

When `--nfs-storage` is specified, home disk is **automatically disabled**:

```bash
# This creates VM with NFS mount, NO home disk
azlin new --name dev-vm --nfs-storage shared-storage
```

NFS replaces the entire `/home/azureuser` directory with a network share.

## Graceful Degradation

If home disk creation or mounting fails, the VM continues with OS disk `/home`:

### Disk Creation Failure

```
Warning: Home disk creation failed (quota exceeded)
Continuing with OS disk /home
```

The VM provisions successfully, just without the separate disk.

### Mount Failure

The `nofail` mount option ensures the system boots even if the disk isn't available:

```bash
# Check cloud-init logs
sudo cat /var/log/cloud-init.log | grep -A5 "disk_setup"

# Manual mount if needed
sudo mount /dev/disk/azure/scsi1/lun0-part1 /home
```

## Cost Analysis

### Standard HDD (Default)

| Disk Size | Monthly Cost | Use Case                     |
| --------- | ------------ | ---------------------------- |
| 50GB      | $2.40        | Lightweight development      |
| 100GB     | $4.80        | Standard development (default) |
| 200GB     | $9.60        | Data-heavy projects          |
| 500GB     | $24.00       | Large datasets               |

**Cost per GB**: $0.048/month (Standard_LRS)

### Premium SSD (Optional)

For better performance, consider Premium SSD:

| Disk Size | Monthly Cost | IOPS | Throughput | Use Case    |
| --------- | ------------ | ---- | ---------- | ----------- |
| 128GB (E10) | $19.71     | 500  | 60 MB/s    | Fast I/O    |
| 256GB (E15) | $38.40     | 1100 | 125 MB/s   | Database    |
| 512GB (E20) | $73.22     | 2300 | 150 MB/s   | High perf   |

**Note**: azlin currently defaults to Standard HDD. Premium SSD support coming soon.

### Cost-Benefit Comparison

| Storage Type       | Setup | Monthly Cost | Performance | Best For         |
| ------------------ | ----- | ------------ | ----------- | ---------------- |
| **OS Disk /home**  | Free  | $0           | Fast        | Ephemeral VMs    |
| **Home Disk (HDD)** | Auto  | $4.80        | Moderate    | Development (recommended) |
| **NFS Storage**    | Manual | $15.36+      | Network     | Shared workspaces |
| **Premium SSD**    | Manual | $19.71+      | Very fast   | I/O intensive    |

## Storage Comparison

### Home Disk vs NFS Storage vs OS Disk

| Feature                | Home Disk (Managed Disk) | NFS Storage | OS Disk /home |
| ---------------------- | ------------------------ | ----------- | ------------- |
| **Setup**              | Automatic                | Manual      | Default       |
| **Persistence**        | Yes                      | Yes         | Yes           |
| **Sharing**            | No (VM-specific)         | Yes         | No            |
| **Performance**        | Moderate (HDD)           | Network     | Fast (SSD)    |
| **Cost (100GB)**       | $4.80/month              | $15.36/month | Included      |
| **Isolation**          | Excellent                | None        | None          |
| **Quota Management**   | No                       | Yes         | No            |
| **Resize**             | Yes (detach/resize)      | Yes         | Complex       |

**Recommendation**:
- **Home Disk**: Most development VMs (default)
- **NFS Storage**: Shared team workspaces with quotas
- **OS Disk**: Short-lived test VMs

## Performance Characteristics

### Standard HDD (Standard_LRS)

- **IOPS**: 500
- **Throughput**: 60 MB/s
- **Latency**: ~10ms
- **Use Case**: Code, documents, general development

**Sufficient for**:
- Git repositories
- Python/Node.js development
- Config files and dotfiles
- Build outputs

**Not ideal for**:
- Database workloads (use Premium SSD)
- Continuous I/O operations
- Large compilation (use Premium SSD)

## Troubleshooting

### Disk Not Mounting

**Symptom**: `/home` is still on OS disk after VM creation

**Check cloud-init logs**:
```bash
sudo cat /var/log/cloud-init.log | grep -A10 "disk_setup"
```

**Common causes**:
1. Disk attachment delayed (Azure timing)
2. Device path changed (not /dev/sdc)
3. Filesystem formatting failed

**Manual recovery**:
```bash
# Check if disk is attached
lsblk

# Format disk (if needed)
sudo mkfs.ext4 /dev/sdc

# Mount disk
sudo mount /dev/sdc /home

# Add to fstab
echo "/dev/sdc /home ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab
```

### Disk Creation Failed

**Symptom**: Warning message during `azlin new`: "Home disk creation failed"

**Possible reasons**:
- **Quota exceeded**: Reached Azure disk quota in region
- **Region capacity**: Selected region out of capacity
- **Permission issue**: Service principal lacks disk creation permission

**Recovery**:
```bash
# Check quota
az vm list-usage --location westus2 | grep "Total Disk Size"

# Try different region
azlin new --name dev-vm --region eastus2

# Or disable home disk for this VM
azlin new --name dev-vm --no-home-disk
```

### Slow Performance

**Symptom**: Home directory operations are slow

**Diagnosis**:
```bash
# Check disk type
az disk show --name {vm-name}-home --resource-group rg-azlin \
  --query sku.name -o tsv
```

**If Standard_LRS**, consider upgrading to Premium SSD (requires manual resize for now).

## Best Practices

### 1. **Size Appropriately**

- **50GB**: Lightweight development, config files only
- **100GB**: Standard development (default, recommended)
- **200GB+**: Data-heavy projects, large repos

### 2. **Monitor Disk Usage**

```bash
# SSH to VM
ssh azureuser@{vm-ip}

# Check disk usage
df -h /home

# Check inode usage
df -i /home
```

### 3. **Backup Strategy**

Home disks are persistent but not automatically backed up:

```bash
# Create snapshot
az snapshot create \
  --name {vm-name}-home-snapshot \
  --resource-group rg-azlin \
  --source {vm-name}-home
```

### 4. **Cost Optimization**

- Use `--no-home-disk` for ephemeral VMs
- Start with 50GB, resize if needed
- Delete VMs promptly (disks don't auto-delete)

### 5. **NFS vs Home Disk Decision**

Choose NFS when:
- Multiple VMs share same workspace
- Need quota management
- Team collaboration required

Choose home disk when:
- Single-user development VM
- Need fast local I/O
- Cost-effective persistent storage

## Technical Details

### Disk Naming Convention

Home disks follow the pattern: `{vm-name}-home`

```bash
VM: dev-vm-001
Home Disk: dev-vm-001-home
```

### Azure Configuration

**Disk SKU**: `Standard_LRS`
- Standard HDD with locally redundant storage
- Most cost-effective option
- Suitable for development workloads

**Device Path**: `/dev/disk/azure/scsi1/lun0`
- Azure's stable device path for LUN 0 (first data disk)
- Symlink provided by Azure Linux Agent

**Mount Options**: `defaults,nofail`
- `defaults`: Standard mount options (rw, suid, dev, exec, auto, nouser, async)
- `nofail`: Boot continues if mount fails (graceful degradation)

### Cloud-Init Implementation

The home disk setup uses cloud-init's built-in disk management modules:

```yaml
disk_setup:
  /dev/disk/azure/scsi1/lun0:
    table_type: gpt       # GPT partition table
    layout: true          # Use entire disk
    overwrite: false      # Don't overwrite existing data

fs_setup:
  - label: home_disk
    filesystem: ext4      # ext4 filesystem
    device: /dev/disk/azure/scsi1/lun0
    partition: auto       # Auto-create partition

mounts:
  - [ /dev/disk/azure/scsi1/lun0-part1, /home, ext4, "defaults,nofail", "0", "2" ]
```

**Execution order**:
1. `disk_setup`: Create GPT partition table
2. `fs_setup`: Format with ext4
3. `mounts`: Mount to /home
4. Update `/etc/fstab` for persistence

## FAQ

### Q: Can I change the disk size after creation?

Currently, you need to:
1. Stop the VM
2. Detach the disk
3. Resize the disk with `az disk update`
4. Reattach the disk
5. Expand the filesystem inside the VM

This requires manual intervention. Automated resize support may be added in future versions.

### Q: What happens to existing /home contents?

The OS disk already has `/home/azureuser` with default dotfiles. When the home disk mounts:
- **With `nofail`**: If mount succeeds, it overlays `/home` (existing contents hidden)
- **If mount fails**: Original `/home` from OS disk remains visible

**Best practice**: The default Ubuntu image has minimal `/home` contents. Data created AFTER VM provisioning goes to the home disk.

### Q: Can I use Premium SSD instead of Standard HDD?

Currently, azlin defaults to Standard HDD (Standard_LRS) for cost-effectiveness. Premium SSD support (`--home-disk-sku Premium_LRS`) is planned for a future release.

**Workaround** (manual upgrade):
```bash
# After VM creation, upgrade disk to Premium
az vm deallocate --name {vm-name} --resource-group rg-azlin
az disk update --name {vm-name}-home --resource-group rg-azlin --sku Premium_LRS
az vm start --name {vm-name} --resource-group rg-azlin
```

### Q: Does the home disk cost extra?

Yes. The default 100GB Standard HDD costs approximately **$4.80/month** in addition to VM compute costs.

See [Cost Analysis](#cost-analysis) section for detailed pricing.

### Q: Can I attach multiple data disks?

Currently, azlin only supports a single home disk. Support for multiple data disks may be added in future versions based on user feedback.

### Q: What if I use both --nfs-storage and --home-disk-size?

NFS storage takes precedence. If you specify `--nfs-storage`, the `--home-disk-size` flag is ignored, and no home disk is created.

azlin will log: "Using NFS storage, skipping home disk creation"

### Q: Can I share a home disk between VMs?

No. Azure Managed Disks can only be attached to a single VM at a time. For shared storage, use NFS storage (`--nfs-storage`).

### Q: What happens if I delete the VM?

The home disk is **NOT automatically deleted**. You must manually delete it:

```bash
# Delete VM
azlin delete {vm-name}

# Manually delete home disk
az disk delete --name {vm-name}-home --resource-group rg-azlin
```

This prevents accidental data loss. Future versions may add `--delete-home-disk` flag.

### Q: Can I snapshot the home disk for backups?

Yes! Create snapshots for backups:

```bash
# Create snapshot
az snapshot create \
  --name {vm-name}-home-backup-$(date +%Y%m%d) \
  --resource-group rg-azlin \
  --source {vm-name}-home

# Restore from snapshot (create new disk)
az disk create \
  --name {vm-name}-home-restored \
  --resource-group rg-azlin \
  --source {snapshot-name}

# Attach to VM
az vm disk attach \
  --vm-name {vm-name} \
  --resource-group rg-azlin \
  --name {vm-name}-home-restored
```

### Q: How do I check if my VM has a home disk?

```bash
# SSH to VM
ssh azureuser@{vm-ip}

# Check mounted disks
df -h | grep /home

# Expected output if home disk mounted:
# /dev/sdc1       99G   60M   94G   1% /home

# Check disk configuration
lsblk
```

### Q: What's the difference between home disk and NFS storage?

| Feature         | Home Disk       | NFS Storage     |
| --------------- | --------------- | --------------- |
| **Type**        | Block storage   | File share      |
| **Performance** | Local disk I/O  | Network I/O     |
| **Sharing**     | Single VM only  | Multiple VMs    |
| **Cost**        | $4.80 (100GB)   | $15.36+ (100GB) |
| **Setup**       | Automatic       | Manual          |
| **Quotas**      | No              | Yes             |

## Examples

### Example 1: Basic Development VM

```bash
# Default: 100GB home disk
azlin new --name dev-vm
```

Result:
- VM with 30GB OS disk
- 100GB home disk mounted as /home
- Total storage: 130GB
- Cost: +$4.80/month for home disk

### Example 2: Data Science VM

```bash
# Large home disk for datasets
azlin new --name ml-vm --home-disk-size 500
```

Result:
- 500GB home disk for datasets, notebooks, models
- Cost: +$24.00/month for home disk

### Example 3: Ephemeral Test VM

```bash
# No separate home disk needed
azlin new --name test-vm --no-home-disk
```

Result:
- Uses OS disk /home only
- Lower cost (no extra disk)
- Suitable for short-lived testing

### Example 4: Team Shared Workspace

```bash
# Use NFS instead of home disk
azlin new --name team-vm --nfs-storage shared-workspace
```

Result:
- No home disk created (NFS takes precedence)
- `/home/azureuser` is NFS mount
- Shared across multiple VMs

## Related Documentation

- [NFS Storage Guide](NFS_SETUP_GUIDE.md) - Alternative to home disk for shared storage
- [AZLIN Command Reference](AZLIN.md) - Complete CLI documentation
- [Cost Optimization](cost-optimization-intelligence.md) - Managing Azure costs

---

**Last updated**: 2026-01-11
