# azlin storage mount

Mount Azure Files NFS storage on VMs or locally.

## Description

The `azlin storage mount` command enables two types of storage mounting:

1. **VM Mount (NFS)**: Mount shared Azure Files storage on a VM's home directory for team collaboration
2. **Local Mount**: Mount Azure Files storage on your local machine (Linux/macOS only)

When mounting on a VM, the existing home directory is backed up and replaced with the NFS share, enabling multiple VMs to share the same home directory and collaborate seamlessly.

## Usage

```bash
# New syntax (explicit)
azlin storage mount vm STORAGE_NAME --vm VM_NAME [OPTIONS]
azlin storage mount local --mount-point PATH [OPTIONS]

# Backward compatible syntax
azlin storage mount STORAGE_NAME --vm VM_NAME [OPTIONS]
```

## Subcommands

### vm - Mount on Virtual Machine

Mount NFS storage as the VM's home directory.

**Usage:**
```bash
azlin storage mount vm STORAGE_NAME --vm VM_NAME
```

**Options:**
- `--vm TEXT` - VM name or identifier (required)
- `--resource-group, --rg TEXT` - Azure resource group
- `-h, --help` - Show help message

### local - Mount on Local Machine

Mount Azure Files storage on your local filesystem.

**Usage:**
```bash
azlin storage mount local --mount-point PATH
```

**Options:**
- `--mount-point PATH` - Local directory for mount point (required)
- `--storage NAME` - Storage account name (required)
- `--resource-group, --rg TEXT` - Azure resource group
- `-h, --help` - Show help message

**Requirements:**
- Linux or macOS only
- NFS client installed (`nfs-common` on Ubuntu, built-in on macOS)
- sudo access for mounting

## Examples

### Mount Storage on VM (Team Collaboration)

```bash
# Mount shared storage on dev VM
azlin storage mount vm team-shared --vm my-dev-vm
```

**Output:**
```
Mounting storage 'team-shared' on VM 'my-dev-vm'...
  Backing up existing home directory...
  Mounting NFS share at /home/azureuser...
  Configuring auto-mount...

Storage mounted successfully!

Your home directory is now shared with:
  - dev-vm-2
  - dev-vm-3

All changes are instantly visible across VMs.
```

### Mount Storage Locally (Local Access)

```bash
# Create mount point
mkdir -p ~/azure-storage

# Mount Azure Files locally
azlin storage mount local --mount-point ~/azure-storage --storage team-shared
```

**Output:**
```
Mounting storage 'team-shared' locally...
  Mount point: /Users/yourname/azure-storage
  NFS endpoint: team-shared.file.core.windows.net
  Checking permissions...
  Mounting filesystem...

Storage mounted successfully!

Access your Azure files at:
  ~/azure-storage/

To unmount:
  sudo umount ~/azure-storage
```

### Backward Compatible Mount (Auto-detect)

```bash
# Old syntax still works (auto-detects VM mount)
azlin storage mount team-shared --vm my-dev-vm
```

### Mount on Multiple VMs

```bash
# Share storage across entire team
for vm in dev-vm-1 dev-vm-2 dev-vm-3; do
    azlin storage mount vm team-shared --vm $vm
done
```

### Mount with Different Resource Group

```bash
# Mount storage from different resource group
azlin storage mount vm prod-shared --vm staging-vm --rg azlin-prod-rg
```

## Common Use Cases

### Team Development Workspace

Create a shared workspace where all team members see the same files:

```bash
# 1. Create team storage
azlin storage create teamwork --size 200 --tier Premium

# 2. Provision VMs for team members
azlin new --name alice-vm
azlin new --name bob-vm
azlin new --name carol-vm

# 3. Mount shared storage on all VMs
azlin storage mount vm teamwork --vm alice-vm
azlin storage mount vm teamwork --vm bob-vm
azlin storage mount vm teamwork --vm carol-vm

# 4. Now all team members share:
#    - Same codebase
#    - Same configuration files
#    - Same SSH keys
#    - Instant file synchronization
```

### Persistent ML Training Environment

Keep training data and checkpoints persistent:

```bash
# 1. Create ML project storage
azlin storage create ml-training --size 1000 --tier Premium

# 2. Create GPU training VM
azlin new --vm-size Standard_NC6s_v3 --name gpu-trainer

# 3. Mount persistent storage
azlin storage mount vm ml-training --vm gpu-trainer

# 4. Train models - checkpoints persist even if VM is deleted
# 5. Can recreate VM or spin up multiple workers sharing same data
```

### Local Development with Azure Files

Work locally but keep files in Azure:

```bash
# Mount Azure storage on your laptop
mkdir ~/azure-dev
azlin storage mount local --mount-point ~/azure-dev --storage dev-shared

# Edit files locally with your favorite IDE
cd ~/azure-dev
code .

# Changes are automatically synced to Azure
# Other VMs with same storage see changes instantly
```

### Disaster Recovery Setup

Backup critical data to shared storage:

```bash
# 1. Create backup storage
azlin storage create dr-backups --size 2000 --tier Standard

# 2. Mount temporarily for backup
azlin storage mount vm dr-backups --vm production-vm

# 3. Copy critical data
# (on VM) cp -r /var/log /opt/data /home/azureuser/backups/

# 4. Unmount after backup
azlin storage unmount --vm production-vm

# 5. Backups are safe even if VM is deleted
```

## What Happens During VM Mount

When you mount storage on a VM:

1. **Backup**: Existing home directory is backed up to `~/.azlin-backup-{timestamp}/`
2. **Mount**: NFS share is mounted at `/home/azureuser`
3. **Auto-mount**: `/etc/fstab` is configured for automatic mounting on reboot
4. **Permissions**: Directory permissions are preserved
5. **Metadata**: Mount information is stored in VM tags for tracking

**Important**: The local home directory is replaced. Access backups if you need original files.

## Troubleshooting

### Mount Failed - NFS Not Available

**Error**: "NFS mount failed: Connection refused"

**Solution**: Check VM networking and storage configuration:
```bash
# Verify VM can reach storage
azlin connect my-dev-vm
ping team-shared.file.core.windows.net

# Check if storage exists
azlin storage list
```

### Permission Denied

**Error**: "Permission denied when accessing mounted files"

**Solution**: Re-mount to fix permissions:
```bash
azlin storage unmount --vm my-dev-vm
azlin storage mount vm team-shared --vm my-dev-vm
```

### Already Mounted

**Error**: "Storage already mounted on this VM"

**Solution**: Unmount first:
```bash
azlin storage unmount --vm my-dev-vm
azlin storage mount vm team-shared --vm my-dev-vm
```

## Related Commands

- [azlin storage create](create.md) - Create new storage account
- [azlin storage unmount](unmount.md) - Unmount storage from VM
- [azlin storage status](status.md) - Check mounted storage status
- [azlin storage list](list.md) - List all storage accounts

## See Also

- [Storage Overview](../../storage/index.md) - Understanding storage architecture
- [Shared Home Directories](../../storage/shared-home.md) - Team collaboration setup
