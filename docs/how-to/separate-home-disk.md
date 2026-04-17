# Separate Home & Tmp Disk Guide

## Overview

azlin automatically provisions VMs with a separate 100GB managed disk mounted as `/home` (unless using NFS storage). You can also add a dedicated `/tmp` disk for scratch space. Both disks are Azure Premium SSD managed disks, tagged with azlin metadata for easy auditing, and set up via hardened cloud-init with retry logic and graceful degradation.

## Quick Start

```bash
# Create VM with default 100GB home disk
azlin new --name dev-vm

# Create VM with custom-sized home disk
azlin new --name data-vm --home-disk-size 200

# Create VM with both home disk and /tmp disk
azlin new --name build-vm --home-disk-size 200 --tmp-disk-size 64

# Create VM with /tmp disk only (no separate home disk)
azlin new --name scratch-vm --no-home-disk --tmp-disk-size 128

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
4. **Cost-Effective**: Premium SSD provides fast, reliable storage at reasonable cost
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

### 1. Disk Creation and Tagging

azlin creates Azure Managed Disks with metadata tags for auditing:
- **Home disk**: `{vm-name}_home` at LUN 0
- **Tmp disk**: `{vm-name}_tmp` at LUN 1 (or LUN 0 if no home disk)
- **SKU**: Premium_LRS (Premium SSD)
- **Size bounds**: 16–4096 GB (validated before creation)
- **Tags**: `azlin-session={session-name}`, `azlin-role=home` or `azlin-role=tmp`

```bash
# Behind the scenes:
az disk create \
  --name dev-vm_home \
  --resource-group rg-azlin \
  --location westus2 \
  --size-gb 100 \
  --sku Premium_LRS \
  --tags azlin-session=dev-vm azlin-role=home
```

**Orphan cleanup:** If VM creation fails after disks are created (or if the second disk fails after the first succeeds), azlin automatically deletes the orphaned disks (`az disk delete --ids <id> --yes --no-wait`) and logs any cleanup failures so they don't accumulate cost silently.

### 2. Disk Attachment

Disks are attached to the VM at creation time via `--attach-data-disks`. The order determines LUN assignment:
- First disk listed → LUN 0 (home disk)
- Second disk listed → LUN 1 (tmp disk)

The disks appear at stable Azure device paths:
- Home: `/dev/disk/azure/scsi1/lun0`
- Tmp: `/dev/disk/azure/scsi1/lun1`

### 3. Hardened Cloud-Init Setup

Cloud-init runs a hardened shell script with the following safeguards:

**Retry loop for LUN device detection:**
The Azure SCSI device symlinks may not appear immediately. Cloud-init polls for up to 60 seconds (12 retries × 5s) using `udevadm settle` and `readlink -f` before giving up.

**Subshell isolation:**
Each disk block runs inside a subshell `( ... ) || echo "WARN: disk setup failed"`. This means a failure in one disk block (e.g., `mkfs.ext4` error) does not abort the entire cloud-init script. The rest of provisioning (tool installation, etc.) continues normally.

**Rollback trap:**
If the bind mount fails after `/home/{user}` has been renamed, a shell `trap` automatically restores the original home directory. This prevents the VM from booting with an empty `/home/{user}`.

**Home disk script flow:**
```bash
(
  # 1. Wait for /dev/disk/azure/scsi1/lun0 (up to 60s)
  udevadm settle
  for i in $(seq 1 12); do
    [ -e /dev/disk/azure/scsi1/lun0 ] && break
    sleep 5
  done
  HOME_DEV=$(readlink -f /dev/disk/azure/scsi1/lun0)

  # 2. Format with ext4
  mkfs.ext4 -F -L azlin-home "$HOME_DEV"

  # 3. Mount disk and rsync existing home data
  mkdir -p /mnt/home-data
  mount "$HOME_DEV" /mnt/home-data
  rsync -aAX /home/{user}/ /mnt/home-data/{user}/

  # 4. Bind-mount with rollback trap
  mv /home/{user} /home/{user}.old
  trap 'if [ -d /home/{user}.old ] && ! mountpoint -q /home/{user}; then
    rm -rf /home/{user}; mv /home/{user}.old /home/{user}
    echo "[AZLIN] Rolled back /home/{user} after disk setup failure"
  fi' EXIT
  mkdir -p /home/{user}
  mount --bind /mnt/home-data/{user} /home/{user}

  # 5. Verify bind mount and clean up
  if mountpoint -q /home/{user}; then
    rm -rf /home/{user}.old
  fi

  # 6. Add idempotent UUID-based fstab entries
  HOME_UUID=$(blkid -s UUID -o value "$HOME_DEV")
  grep -q "UUID=$HOME_UUID" /etc/fstab || \
    echo "UUID=$HOME_UUID /mnt/home-data ext4 defaults,nofail 0 2" >> /etc/fstab
  grep -q "/mnt/home-data/{user} /home/{user}" /etc/fstab || \
    echo "/mnt/home-data/{user} /home/{user} none bind 0 0" >> /etc/fstab
) || echo "WARN: home disk setup failed, continuing without separate home disk"
```

**Tmp disk script flow** follows the same pattern, mounting at `/tmp` with `mode=1777`.

### 4. Persistent Configuration

The mount is added to `/etc/fstab` idempotently (only if not already present) for persistence across reboots. UUID-based entries are used for the disk mount, with a bind mount entry for `/home/{user}`:

```
UUID=<home-disk-uuid> /mnt/home-data ext4 defaults,nofail 0 2
/mnt/home-data/{user} /home/{user} none bind 0 0
UUID=<tmp-disk-uuid> /tmp ext4 defaults,nofail,mode=1777 0 2
```

## Configuration Options

### `--home-disk-size`

Specify custom home disk size in GB (default: 100):

```bash
# Small disk for lightweight development
azlin new --name dev-vm --home-disk-size 50

# Large disk for data-heavy workflows
azlin new --name ml-vm --home-disk-size 500
```

**Size bounds** (validated before disk creation):
- Minimum: 16 GB
- Maximum: 4096 GB

Sizes outside this range produce a clear error before any Azure resources are created.

### `--tmp-disk-size`

Add a dedicated `/tmp` disk (not created by default):

```bash
# 64GB /tmp disk for build artifacts
azlin new --name build-vm --tmp-disk-size 64

# Combine with home disk
azlin new --name ml-vm --home-disk-size 500 --tmp-disk-size 128
```

**Size bounds**: Same as home disk (16–4096 GB).

**When to use**:
- Large compilation builds (Rust, C++, Chromium)
- Docker image builds with large layer caches
- Data processing with temporary intermediate files
- Any workload that fills OS-level `/tmp`

### `--no-home-disk`

Disable separate home disk, use OS disk `/home`:

```bash
# Ephemeral VM - no separate home disk needed
azlin new --name test-vm --no-home-disk

# No home disk, but still get a /tmp disk
azlin new --name scratch-vm --no-home-disk --tmp-disk-size 64
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

> **Note:** `--nfs-storage` is not yet fully implemented in the Rust CLI. Currently, azlin logs a warning ("NFS storage is not yet implemented in the Rust CLI") but does not disable home disk creation. This guard will be implemented alongside the NFS feature.

## Graceful Degradation

azlin is designed so disk failures never prevent a VM from being usable.

### Disk Creation Failure (Azure-side)

If `az disk create` fails (quota exceeded, region capacity, permissions), azlin logs a warning and continues VM creation without the disk:

```
Warning: Home disk creation failed (quota exceeded)
Continuing with OS disk /home
```

### VM Creation Failure (orphan cleanup)

If disks are created successfully but the subsequent `az vm create` fails, azlin automatically deletes the orphaned disks to prevent cost accumulation:

```
Error: VM creation failed (QuotaExceeded)
Cleaning up orphaned disks: dev-vm_home, dev-vm_tmp
```

### Cloud-Init Disk Setup Failure

Each disk block runs in a subshell. If LUN detection, formatting, or mounting fails, the error is contained:

```
WARN: home disk setup failed, using OS disk
```

The rest of cloud-init (tool installation, repo clone, etc.) continues normally. The `nofail` fstab option ensures the system boots even if the disk is absent on reboot.

### Diagnosing Failures

```bash
# Check cloud-init logs for disk setup
sudo cat /var/log/cloud-init-output.log | grep -A10 "disk setup"

# Check if disk is attached
lsblk
ls -la /dev/disk/azure/scsi1/

# Manual mount if needed
sudo mount /dev/disk/azure/scsi1/lun0 /home/azureuser
```

## Cost Analysis

### Premium SSD (Default)

azlin uses Premium SSD (Premium_LRS) for all managed disks:

| Disk Size | Monthly Cost | IOPS | Throughput | Use Case    |
| --------- | ------------ | ---- | ---------- | ----------- |
| 16GB (P3)   | $2.40      | 120  | 25 MB/s    | Minimum     |
| 64GB (P6)   | $9.94      | 240  | 50 MB/s    | /tmp disk   |
| 100GB (P10) | $19.71     | 500  | 100 MB/s   | Default home |
| 256GB (P15) | $38.40     | 1100 | 125 MB/s   | Large home  |
| 512GB (P20) | $73.22     | 2300 | 150 MB/s   | Data-heavy  |

### Cost-Benefit Comparison

| Storage Type       | Setup | Monthly Cost | Performance | Best For         |
| ------------------ | ----- | ------------ | ----------- | ---------------- |
| **OS Disk /home**  | Free  | $0           | Fast        | Ephemeral VMs    |
| **Home Disk (SSD)** | Auto  | $19.71       | Fast        | Development (recommended) |
| **Tmp Disk (SSD)** | Opt-in | $9.94       | Fast        | Build artifacts  |
| **NFS Storage**    | Manual | $15.36+      | Network     | Shared workspaces |

## Storage Comparison

### Home Disk vs NFS Storage vs OS Disk

| Feature                | Home Disk (Managed Disk) | NFS Storage | OS Disk /home |
| ---------------------- | ------------------------ | ----------- | ------------- |
| **Setup**              | Automatic                | Manual      | Default       |
| **Persistence**        | Yes                      | Yes         | Yes           |
| **Sharing**            | No (VM-specific)         | Yes         | No            |
| **Performance**        | Fast (SSD)               | Network     | Fast (SSD)    |
| **Cost (100GB)**       | $19.71/month             | $15.36/month | Included      |
| **Isolation**          | Excellent                | None        | None          |
| **Quota Management**   | No                       | Yes         | No            |
| **Resize**             | Yes (detach/resize)      | Yes         | Complex       |

**Recommendation**:
- **Home Disk**: Most development VMs (default)
- **NFS Storage**: Shared team workspaces with quotas
- **OS Disk**: Short-lived test VMs

## Performance Characteristics

### Premium SSD (Premium_LRS) — Default

- **IOPS**: 500–7500 (depends on disk size)
- **Throughput**: 100–250 MB/s
- **Latency**: ~1ms
- **Use Case**: All development workloads

**Well-suited for**:
- Git repositories and large monorepos
- Build systems (Rust, C++, Go)
- Docker builds and layer caching
- Database workloads
- ML dataset staging

## Troubleshooting

### Disk Not Mounting

**Symptom**: `/home` is still on OS disk after VM creation

**Check cloud-init logs**:
```bash
sudo cat /var/log/cloud-init.log | grep -A10 "disk_setup"
```

**Common causes**:
1. Disk attachment delayed (Azure timing — the retry loop polls for 60s)
2. LUN symlink not yet available at `/dev/disk/azure/scsi1/lun0`
3. Filesystem formatting failed

**Manual recovery**:
```bash
# Check if disk is attached
lsblk
ls -la /dev/disk/azure/scsi1/

# Format disk (if needed)
sudo mkfs.ext4 /dev/disk/azure/scsi1/lun0

# Mount disk
sudo mount /dev/disk/azure/scsi1/lun0 /home/azureuser

# Add to fstab (idempotent)
grep -q 'lun0.*/home/azureuser' /etc/fstab || \
  echo '/dev/disk/azure/scsi1/lun0 /home/azureuser ext4 defaults,nofail 0 2' | sudo tee -a /etc/fstab
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

**If Standard_LRS** (shouldn't happen with azlin's defaults), the disk was created outside azlin. Consider replacing with a Premium SSD disk.

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

Disks follow the pattern: `{vm-name}_home` and `{vm-name}_tmp`

```bash
VM: dev-vm-001
Home Disk: dev-vm-001_home
Tmp Disk:  dev-vm-001_tmp
```

### Azure Tags

Every managed disk is tagged for auditing and orphan detection:

| Tag | Value | Purpose |
|-----|-------|---------|
| `azlin-session` | Session/VM name | Correlate disk with VM |
| `azlin-role` | `home` or `tmp` | Identify disk purpose |

Find orphaned disks with:
```bash
az disk list --query "[?tags.\"azlin-session\" && !managedBy]" -o table
```

### Azure Configuration

**Disk SKU**: `Premium_LRS`
- Premium SSD with locally redundant storage
- Low latency (~1ms) and high IOPS

**LUN Assignment**:
- Home disk → LUN 0 (via `--attach-data-disks` order)
- Tmp disk → LUN 1 (or LUN 0 if no home disk)

**Device Paths** (stable Azure symlinks):
- LUN 0: `/dev/disk/azure/scsi1/lun0`
- LUN 1: `/dev/disk/azure/scsi1/lun1`

**Mount Options**:
- Home: `defaults,nofail` on `/home/{user}`
- Tmp: `defaults,nofail,mode=1777` on `/tmp`

### Cloud-Init Implementation

The disk setup uses a hardened shell script (not cloud-init YAML disk modules) for better control over retry logic and error isolation:

**Key hardening features:**

1. **`udevadm settle` + retry loop**: Waits up to 60s for Azure SCSI device symlinks to appear (12 retries × 5s sleep)
2. **Subshell isolation**: Each disk block runs in `( ... ) || echo "WARN: ..."` so failures don't abort other cloud-init tasks
3. **Mandatory rsync**: Home disk copies existing `/home/{user}` content before bind-mounting (preserves dotfiles, SSH keys)
4. **Idempotent fstab**: Uses `grep -q` guard before appending to `/etc/fstab` (safe for re-runs)
5. **Immediate cleanup**: Removes `/home/{user}.old` after verifying bind-mount succeeded
6. **Ownership fix**: `chown -R {user}:{user}` after mount ensures correct permissions

**Execution order** (per disk block):
1. `udevadm settle` + device readlink poll (up to 60s)
2. `mkfs.ext4 -F` (format)
3. Temp-mount, `rsync -aAX` existing content, unmount
4. Bind-mount to target path
5. Append to `/etc/fstab` (idempotent)
6. Verify with `mountpoint -q`, clean up `.old` directory

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

### Q: What disk type does azlin use?

azlin uses Premium SSD (Premium_LRS) for all managed disks. This provides low-latency (~1ms) I/O suitable for development workloads including builds and database access.

### Q: Does the home disk cost extra?

Yes. The default 100GB Premium SSD costs approximately **$19.71/month** in addition to VM compute costs.

See [Cost Analysis](#cost-analysis) section for detailed pricing.

### Q: Can I attach multiple data disks?

azlin supports up to two data disks: one for `/home` (LUN 0) and one for `/tmp` (LUN 1). Use `--home-disk-size` and `--tmp-disk-size` together:

```bash
azlin new --name dev-vm --home-disk-size 200 --tmp-disk-size 64
```

### Q: What if I use both --nfs-storage and --home-disk-size?

NFS storage takes precedence. If you specify `--nfs-storage`, the `--home-disk-size` flag is ignored, and no home disk is created.

azlin will log: "Using NFS storage, skipping home disk creation"

> **Note:** This NFS precedence guard is planned but not yet active in the Rust CLI. See [NFS Storage Precedence](#nfs-storage-precedence) for current status.

### Q: Can I use --tmp-disk-size with --nfs-storage?

Yes. The tmp disk is independent of NFS. You can have NFS for `/home` and a local disk for `/tmp`:

```bash
azlin new --nfs-storage shared --tmp-disk-size 64
```

### Q: Can I share a home disk between VMs?

No. Azure Managed Disks can only be attached to a single VM at a time. For shared storage, use NFS storage (`--nfs-storage`).

### Q: What happens if I delete the VM?

The home and tmp disks are **NOT automatically deleted**. You must manually delete them:

```bash
# Delete VM
azlin delete {vm-name}

# Manually delete disks
az disk delete --name {vm-name}_home --resource-group rg-azlin
az disk delete --name {vm-name}_tmp --resource-group rg-azlin
```

You can find orphaned disks (created by azlin but not attached to any VM) with:
```bash
az disk list --query "[?tags.\"azlin-session\" && !managedBy]" -o table
```

This prevents accidental data loss. Future versions may add `--delete-disks` flag.

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
# /dev/disk/azure/scsi1/lun0   99G   60M   94G   1% /home

# Check disk configuration
lsblk
```

### Q: What's the difference between home disk and NFS storage?

| Feature         | Home Disk       | NFS Storage     |
| --------------- | --------------- | --------------- |
| **Type**        | Block storage   | File share      |
| **Performance** | Local disk I/O  | Network I/O     |
| **Sharing**     | Single VM only  | Multiple VMs    |
| **Cost**        | $19.71 (100GB)  | $15.36+ (100GB) |
| **Setup**       | Automatic       | Manual          |
| **Quotas**      | No              | Yes             |

## Examples

### Example 1: Basic Development VM

```bash
# Default: 100GB home disk, no tmp disk
azlin new --name dev-vm
```

Result:
- VM with 30GB OS disk
- 100GB Premium SSD home disk mounted as `/home/azureuser`
- Total storage: 130GB
- Cost: +$19.71/month for home disk

### Example 2: Data Science VM

```bash
# Large home disk for datasets, tmp disk for intermediate files
azlin new --name ml-vm --home-disk-size 500 --tmp-disk-size 128
```

Result:
- 500GB home disk for datasets, notebooks, models
- 128GB `/tmp` disk for training checkpoints and scratch data
- Cost: +$73.22/month (home) + $19.71/month (tmp)

### Example 3: Build Server

```bash
# Standard home, large /tmp for build artifacts
azlin new --name build-vm --tmp-disk-size 256
```

Result:
- 100GB home disk (default)
- 256GB `/tmp` disk for compilation intermediates
- Prevents OS `/tmp` from filling up during large builds

### Example 4: Ephemeral Test VM

```bash
# No separate home disk needed
azlin new --name test-vm --no-home-disk
```

Result:
- Uses OS disk `/home` only
- Lower cost (no extra disk)
- Suitable for short-lived testing

### Example 5: Scratch-Only VM

```bash
# No home disk, just a tmp disk
azlin new --name scratch-vm --no-home-disk --tmp-disk-size 64
```

Result:
- OS disk `/home` (no separate home disk)
- 64GB `/tmp` disk for scratch space
- Cost: +$9.94/month for tmp disk

### Example 6: Team Shared Workspace with Tmp Disk

```bash
# NFS for /home, local disk for /tmp
azlin new --name team-vm --nfs-storage shared-workspace --tmp-disk-size 64
```

Result:
- No home disk created (NFS takes precedence)
- `/home/azureuser` is NFS mount (shared across VMs)
- 64GB local `/tmp` disk for per-VM scratch space

## Related Documentation

- [NFS Storage Guide](NFS_SETUP_GUIDE.md) - Alternative to home disk for shared storage
- [AZLIN Command Reference](AZLIN.md) - Complete CLI documentation
- [Cost Optimization](cost-optimization-intelligence.md) - Managing Azure costs

---

**Last updated**: 2026-04-17
