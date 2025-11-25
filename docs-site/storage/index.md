# Storage & NFS

Azure Files NFS shared storage for seamless collaboration and data sharing across VMs.

## Quick Start

```bash
# Create shared storage
azlin storage create myteam-shared --size 100

# Mount on VM as home directory
azlin storage mount vm myteam-shared --vm my-vm

# Multiple VMs can now share the same home directory
azlin storage mount vm myteam-shared --vm worker-1
azlin storage mount vm myteam-shared --vm worker-2

# Unmount when done
azlin storage unmount --vm my-vm
```

## Overview

azlin provides integrated Azure Files NFS storage management for:

- **Shared home directories** - Multiple VMs access same files
- **Team collaboration** - Everyone works on shared codebase
- **Data persistence** - Storage independent of VM lifecycle
- **Cost efficiency** - Pay only for storage, not compute
- **High performance** - Premium NFS with low latency

## Key Features

### Shared Home Directories

Mount Azure Files as `/home/azureuser` on multiple VMs:

```bash
# Create storage
azlin storage create team-storage

# Create VMs with shared home
azlin new --nfs-storage team-storage --name worker-1
azlin new --nfs-storage team-storage --name worker-2
azlin new --nfs-storage team-storage --name worker-3

# All VMs share /home/azureuser
```

**Result:** Changes on one VM instantly visible on all others.

### Local Mounting

Mount storage on your laptop/desktop:

```bash
# Mount locally (Linux/macOS)
azlin storage mount local --mount-point ~/azure-shared/

# Access files from local machine
cd ~/azure-shared/
ls -la
```

### Data Persistence

Storage outlives VMs:

```bash
# Delete VM
azlin delete my-vm

# Storage and data remain
azlin storage status myteam-shared

# Create new VM with same storage
azlin new --nfs-storage myteam-shared --name new-vm
# All files still there!
```

## Storage Tiers

| Tier | Price | IOPS | Use Case |
|------|-------|------|----------|
| **Premium** | $0.153/GB/month | High | Active development, databases |
| **Standard** | $0.0184/GB/month | Standard | Backups, archives, cold storage |

!!! tip "Tier Selection"
    - Use **Premium** for VMs' home directories (better performance)
    - Use **Standard** for backups and archival data

## Command Overview

| Command | Purpose | Example |
|---------|---------|---------|
| [`create`](creating.md) | Create new NFS storage | `azlin storage create myteam` |
| [`list`](../commands/storage/list.md) | List storage accounts | `azlin storage list` |
| [`status`](status.md) | Check usage and details | `azlin storage status myteam` |
| [`mount`](mounting.md) | Mount on VM or locally | `azlin storage mount vm myteam --vm my-vm` |
| [`unmount`](../commands/storage/unmount.md) | Unmount from VM | `azlin storage unmount --vm my-vm` |
| [`delete`](../commands/storage/delete.md) | Delete storage account | `azlin storage delete myteam` |

## Common Workflows

### Team Development Environment

```bash
# 1. Create shared storage
azlin storage create team-dev --size 200 --tier Premium

# 2. Create VMs with shared home
for member in alice bob carol; do
  azlin new --nfs-storage team-dev --name "dev-$member"
done

# 3. Everyone works on same codebase
# Changes by alice instantly visible to bob and carol
```

### Distributed Computing

```bash
# 1. Create storage for data
azlin storage create job-data --size 500

# 2. Upload data to one VM
azlin new --nfs-storage job-data --name coordinator
azlin connect coordinator
# ... upload data ...

# 3. Create worker VMs
azlin clone coordinator --num-replicas 10 --session-prefix worker
# All workers have access to same data via NFS

# 4. Process in parallel
for i in {1..10}; do
  azlin connect worker-$i -- python process.py --shard $i &
done
```

### Backup and Disaster Recovery

```bash
# Create backup storage
azlin storage create backups --size 1000 --tier Standard

# Mount on VM for backups
azlin storage mount vm backups --vm production-db

# Automated backups
azlin connect production-db -- "
  rsync -av /var/lib/postgresql/ ~/backups/postgres/
"

# Restore to new VM if needed
azlin new --nfs-storage backups --name db-restore
# All backup data immediately available
```

### Development/Staging/Production

```bash
# Shared storage per environment
azlin storage create dev-shared --size 100
azlin storage create staging-shared --size 200
azlin storage create prod-shared --size 500

# VMs use appropriate storage
azlin new --nfs-storage dev-shared --name dev-vm --tag env=dev
azlin new --nfs-storage staging-shared --name staging-vm --tag env=staging
azlin new --nfs-storage prod-shared --name prod-vm --tag env=production
```

## How It Works

### Architecture

```
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│   VM-1       │       │   VM-2       │       │   VM-3       │
│              │       │              │       │              │
│ /home/user ──┼───────┼──────────────┼───────┼─┐            │
└──────────────┘       └──────────────┘       └─┼────────────┘
                                                 │
                      ┌──────────────────────────┘
                      │
              ┌───────▼────────┐
              │  Azure Files   │
              │  NFS Storage   │
              │                │
              │  Premium/Std   │
              └────────────────┘
```

### Mount Process

1. **Create storage:** Azure Files Premium NFS account
2. **Create file share:** 100GB (or specified size)
3. **Configure network:** Private endpoint in VNet
4. **Mount on VM:** NFS mount to `/home/azureuser`
5. **Backup local:** Original home backed up to `/home/azureuser.local`

### Security

- **Private network only:** No public internet access
- **VNet integration:** Storage accessible only within Azure VNet
- **No credentials needed:** Identity-based authentication
- **Encryption at rest:** All data encrypted

## Pricing Examples

### Small Team (3 devs, 100GB)

```
Premium: 100GB × $0.153 = $15.30/month
Standard: 100GB × $0.0184 = $1.84/month
```

### Medium Team (10 devs, 500GB)

```
Premium: 500GB × $0.153 = $76.50/month
Standard: 500GB × $0.0184 = $9.20/month
```

### Large Project (10TB backups)

```
Premium: 10,000GB × $0.153 = $1,530/month
Standard: 10,000GB × $0.0184 = $184/month
```

!!! tip "Cost Optimization"
    - Use Premium for active work (better performance)
    - Use Standard for backups/archives
    - Delete unused storage: `azlin storage delete`

## Limitations

- **Linux/NFS only:** No Windows support currently
- **VNet required:** Must be within Azure VNet
- **Region-specific:** Storage and VMs must be in same region
- **Single mount:** One VM can't have multiple NFS mounts as home

## Troubleshooting

### Can't Create Storage

```bash
# Check name availability (must be globally unique)
az storage account check-name --name myteam-shared

# Try different name
azlin storage create myteam-shared-2

# Check quota
azlin quota
```

### Mount Fails

```bash
# Verify storage exists
azlin storage list

# Check VM and storage in same region
azlin list
azlin storage status <storage-name>

# Check VNet configuration
az storage account show -n <storage> -g <rg>
```

### Can't Access Files

```bash
# Check mount status
azlin connect my-vm -- mount | grep nfs

# Verify permissions
azlin connect my-vm -- ls -la /home/azureuser

# Remount if needed
azlin storage unmount --vm my-vm
azlin storage mount vm <storage> --vm my-vm
```

## Next Steps

- [Create Storage](creating.md) - Set up new NFS storage
- [Mount Storage](mounting.md) - Attach storage to VMs
- [Storage Status](status.md) - Monitor usage and health
- [Shared Home Directories](shared-home.md) - Team collaboration setup

## Related Features

- [VM Cloning](../vm-lifecycle/cloning.md) - Clone with shared storage
- [Snapshots](../snapshots/index.md) - Backup entire storage
- [File Transfer](../file-transfer/index.md) - Alternative data sharing

## Source Code

- [Storage Commands](https://github.com/rysweet/azlin/blob/main/azlin/cli.py#L1000)
- [NFS Mount Logic](https://github.com/rysweet/azlin/blob/main/azlin/storage.py)
- [Azure Files Integration](https://github.com/rysweet/azlin/blob/main/azlin/azure_files.py)

---

*Last updated: 2025-11-24*
