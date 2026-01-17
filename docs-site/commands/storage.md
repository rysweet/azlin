# azlin storage

Manage Azure Files NFS shared storage.

Create and manage Azure Files NFS storage accounts for sharing
home directories across multiple VMs.


COMMANDS:
    create     Create new NFS storage account
    list       List storage accounts
    status     Show storage status and usage
    delete     Delete storage account
    mount      Mount storage (group with vm/local subcommands)
    unmount    Unmount storage from VM


EXAMPLES:
    # Create 100GB Premium storage
    $ azlin storage create myteam-shared --size 100 --tier Premium

    # List all storage accounts
    $ azlin storage list

    # Mount storage on VM (new syntax)
    $ azlin storage mount vm myteam-shared --vm my-dev-vm

    # Mount storage locally
    $ azlin storage mount local --mount-point ~/azure/

    # Mount storage on VM (backward compatible)
    $ azlin storage mount myteam-shared --vm my-dev-vm

    # Check storage status
    $ azlin storage status myteam-shared

    # Unmount from VM
    $ azlin storage unmount --vm my-dev-vm

    # Delete storage
    $ azlin storage delete myteam-shared


## Description

Manage Azure Files NFS shared storage.
Create and manage Azure Files NFS storage accounts for sharing
home directories across multiple VMs.

COMMANDS:
create     Create new NFS storage account
list       List storage accounts
status     Show storage status and usage
delete     Delete storage account
mount      Mount storage (group with vm/local subcommands)
unmount    Unmount storage from VM

EXAMPLES:
# Create 100GB Premium storage
$ azlin storage create myteam-shared --size 100 --tier Premium
# List all storage accounts
$ azlin storage list
# Mount storage on VM (new syntax)
$ azlin storage mount vm myteam-shared --vm my-dev-vm
# Mount storage locally
$ azlin storage mount local --mount-point ~/azure/
# Mount storage on VM (backward compatible)
$ azlin storage mount myteam-shared --vm my-dev-vm
# Check storage status
$ azlin storage status myteam-shared
# Unmount from VM
$ azlin storage unmount --vm my-dev-vm
# Delete storage
$ azlin storage delete myteam-shared

## Usage

```bash
azlin storage
```

## Subcommands

### create

Create Azure Files NFS storage account.

Creates a new Azure Files storage account with NFS support for
sharing home directories across VMs. The storage is accessible
only within the Azure VNet for security.

All storage accounts are created with blob public access disabled
by default for Azure policy compliance.


NAME should be globally unique across Azure (3-24 chars, lowercase/numbers).


Storage tiers:
  Premium: $0.153/GB/month, high performance
  Standard: $0.0184/GB/month, standard performance


Examples:
  $ azlin storage create myteam-shared --size 100 --tier Premium
  $ azlin storage create backups --size 500 --tier Standard


**Usage:**
```bash
azlin storage create NAME [OPTIONS]
```

**Options:**
- `--size` - Size in GB (default: 100)
- `--tier` - Storage tier (default: Premium)
- `--resource-group`, `--rg` - Azure resource group
- `--region` - Azure region

### delete

Delete Azure Files NFS storage account.

Deletes a storage account. By default, prevents deletion if VMs
are still connected. Use --force to override.

WARNING: This deletes all data in the storage account.


Examples:
  $ azlin storage delete myteam-shared
  $ azlin storage delete old-storage --force


**Usage:**
```bash
azlin storage delete NAME [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Azure resource group
- `--force` - Force delete even if VMs are connected

### list

List Azure Files NFS storage accounts.

Shows all NFS-enabled storage accounts in the resource group
with their size, tier, and mount status.


Examples:
  $ azlin storage list
  $ azlin storage list --resource-group azlin-rg


**Usage:**
```bash
azlin storage list [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Azure resource group

### mount

Mount storage on VM or locally.

Two ways to mount storage:


VM MOUNT (NFS shared across VMs):
    $ azlin storage mount vm <storage> --vm <vm-name>
    Mounts NFS storage on VM home directory for sharing.


LOCAL MOUNT (local path):
    $ azlin storage mount local --mount-point ~/azure/
    Mounts storage locally (Linux/macOS only).


BACKWARD COMPATIBILITY:
    $ azlin storage mount <storage> --vm <vm-name>
    Auto-detects and mounts on VM (same as: mount vm <storage> --vm <vm-name>)


EXAMPLES:
    # Mount on VM (new)
    $ azlin storage mount vm myteam-shared --vm my-dev-vm

    # Mount locally (new)
    $ azlin storage mount local --mount-point ~/azure/

    # Mount on VM (backward compatible)
    $ azlin storage mount myteam-shared --vm my-dev-vm


### mount-file

Mount file storage locally.

### status

Show storage account status and usage.

Displays detailed information about a storage account including
usage statistics, connected VMs, and cost estimates.


Examples:
  $ azlin storage status myteam-shared


**Usage:**
```bash
azlin storage status NAME [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Azure resource group

### unmount

Unmount NFS storage from VM.

Unmounts the NFS share from the VM and restores the local
home directory from backup if available.


Examples:
  $ azlin storage unmount --vm my-dev-vm


**Usage:**
```bash
azlin storage unmount [OPTIONS]
```

**Options:**
- `--vm` - VM name or identifier
- `--resource-group`, `--rg` - Azure resource group

### unmount-file

Unmount file storage from local machine.
