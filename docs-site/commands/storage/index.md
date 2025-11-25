# Storage Commands

Manage Azure Files NFS shared storage for VMs.

## Overview

Storage commands create and manage Azure Files NFS storage accounts for sharing home directories and data across multiple VMs.

## Available Commands

- [**azlin storage create**](create.md) - Create new NFS storage account
- [**azlin storage list**](list.md) - List storage accounts
- [**azlin storage status**](status.md) - Show storage status and usage
- [**azlin storage mount**](mount.md) - Mount storage on VM or locally
- [**azlin storage unmount**](unmount.md) - Unmount storage from VM
- [**azlin storage delete**](delete.md) - Delete storage account

## Quick Start

### Create and Mount

```bash
# Create 100GB Premium storage
azlin storage create myteam-shared --size 100 --tier Premium

# Mount on VM
azlin storage mount vm myteam-shared --vm my-dev-vm

# Mount locally
azlin storage mount local myteam-shared --mount-point ~/azure-storage
```

### Check Status

```bash
# Show storage usage
azlin storage status myteam-shared

# List all storage
azlin storage list
```

### Cleanup

```bash
# Unmount from VM
azlin storage unmount myteam-shared --vm my-dev-vm

# Delete storage
azlin storage delete myteam-shared
```

## Use Cases

### Shared Team Storage

```bash
# Create shared storage
azlin storage create team-data --size 500 --tier Premium

# Mount on all team VMs
azlin batch command 'azlin storage mount vm team-data' --tag 'team=dev'
```

### Persistent Data

```bash
# Mount on VM
azlin storage mount vm data-store --vm my-vm

# Data persists even if VM is deleted
azlin kill my-vm

# Remount on new VM
azlin new --name new-vm
azlin storage mount vm data-store --vm new-vm
```

## Related Commands

- [azlin new](../vm/new.md) - Create VMs with storage
- [azlin batch](../batch/index.md) - Mount storage on multiple VMs

## See Also

- [Storage & NFS](../../storage/index.md)
- [Shared Home Directories](../../storage/shared-home.md)
