# azlin destroy Command Reference

Arr matey! This here document be explainin' the `azlin destroy` command fer cleanly deletin' VMs and all their associated resources.

## Overview

The `destroy` command completely removes a VM and ALL associated Azure resources, including:

- Virtual Machine itself
- Network Interfaces (NICs)
- Network Security Groups (NSGs) **[NEW]**
- OS and data disks
- Public IP addresses (if attached)

This ensures no orphaned resources remain after deletion, allowing ye to reuse VM names without conflicts.

## Basic Usage

```bash
# Delete a VM with all resources
azlin destroy my-vm-name

# Show what would be deleted (dry-run)
azlin destroy my-vm-name --dry-run

# Skip confirmation prompt
azlin destroy my-vm-name --force
```

## Command Options

### Required Arguments

- `vm_name` - Name of the VM to destroy (or session name)

### Optional Flags

| Flag | Description |
|------|-------------|
| `--resource-group`, `--rg` | Specify resource group (uses config default if not provided) |
| `--config` | Path to custom config file |
| `--force` | Skip confirmation prompt |
| `--dry-run` | Show what would be deleted without actually deleting |
| `--delete-rg` | Delete the entire resource group (DANGEROUS) |

## What Gets Deleted

### Resource Deletion Order

Resources are deleted in the followin' order to handle dependencies:

1. **Virtual Machine** - The VM instance itself
2. **Network Interfaces (NICs)** - All network interfaces attached to the VM
3. **Network Security Groups (NSGs)** - NSGs discovered from each NIC **[NEW]**
4. **OS and Data Disks** - All disks attached to the VM
5. **Public IP Addresses** - Public IPs associated with NICs (if any)

### NSG Deletion Behavior **[NEW]**

- NSGs be discovered by querying each NIC attached to the VM
- NSG deletion be best-effort (graceful if NSG doesn't exist or already deleted)
- Multiple NICs may share the same NSG (only deleted once)
- No errors if NSG not found (handles race conditions)

## Examples

### Example 1: Standard Deletion

```bash
azlin destroy azlin-vm-20250112-120000
```

**Output:**
```
VM Details:
  Name:           azlin-vm-20250112-120000
  Resource Group: my-dev-rg
  Status:         Running
  IP:             20.123.45.67
  Size:           Standard_D2s_v3

This will delete the VM and all associated resources (NICs, NSGs, disks, IPs).
This action cannot be undone.

Are you sure you want to delete this VM? [y/N]: y

Deleting VM: azlin-vm-20250112-120000
  ✓ Deleted VM
  ✓ Deleted NIC: azlin-vm-nic
  ✓ Deleted NSG: azlin-vm-nsg
  ✓ Deleted disk: azlin-vm-osdisk
  ✓ Deleted Public IP: azlin-vm-ip

Successfully deleted azlin-vm-20250112-120000 and all associated resources.
```

### Example 2: Dry-Run Mode

```bash
azlin destroy my-dev-vm --dry-run
```

**Output:**
```
DRY RUN: The following resources would be deleted:

VM: my-dev-vm
├── Network Interfaces:
│   ├── my-dev-vm-nic-1
│   └── my-dev-vm-nic-2
├── Network Security Groups:
│   └── my-dev-vm-nsg
├── Disks:
│   ├── my-dev-vm-osdisk
│   └── my-dev-vm-datadisk-0
└── Public IPs:
    └── my-dev-vm-ip

Total: 1 VM, 2 NICs, 1 NSG, 2 disks, 1 Public IP

No resources were deleted (--dry-run mode).
```

### Example 3: Skip Confirmation

```bash
azlin destroy test-vm-001 --force
```

**Use Case:** Automated scripts or CI/CD pipelines where manual confirmation not be needed.

### Example 4: Multiple Resource Groups

```bash
# Delete VM in specific resource group
azlin destroy vm-name --rg production-rg

# Delete VM in development group
azlin destroy vm-name --rg dev-rg
```

## Success Messages

After successful deletion, ye'll see:

```
Successfully deleted <vm-name> and all associated resources.
Resources deleted:
  - VM: <vm-name>
  - NIC(s): <nic-count> deleted
  - NSG(s): <nsg-count> deleted
  - Disk(s): <disk-count> deleted
  - Public IP(s): <ip-count> deleted
```

## Error Handling

### VM Not Found

```bash
azlin destroy nonexistent-vm
```

**Output:**
```
Error: VM 'nonexistent-vm' not found in resource group 'my-rg'.
```

### Permission Denied

```
Error: Insufficient permissions to delete VM.
Ensure you have 'Contributor' or 'Owner' role on the resource group.
```

### Partial Deletion

If some resources fail to delete, ye'll see:

```
Warning: Some resources could not be deleted:
  ✓ Deleted VM: my-vm
  ✓ Deleted NIC: my-vm-nic
  ✗ Failed to delete NSG: my-vm-nsg (ResourceInUse)
  ✓ Deleted disk: my-vm-osdisk

VM deleted but some resources remain. Manual cleanup may be required.
```

## Important Notes

### Name Reuse

After destroy completes successfully, the VM name be immediately available for reuse:

```bash
# Delete old VM
azlin destroy my-project-vm --force

# Create new VM with same name
azlin new --name my-project-vm
```

Previously, orphaned NSGs would prevent name reuse. This be fixed with NSG cleanup.

### NSG Sharing

If multiple VMs share a Network Security Group:
- NSG only deleted when the LAST VM using it be destroyed
- Azure prevents deletion of NSGs still attached to other resources
- This be safe and automatic - no user action needed

### Resource Group Deletion

```bash
azlin destroy my-vm --delete-rg --force
```

**WARNING:** This deletes the ENTIRE resource group, not just the VM. All resources in the group be permanently lost.

## Comparison with killall

| Command | Purpose | Confirmation |
|---------|---------|--------------|
| `azlin destroy <vm-name>` | Delete single VM | Per-VM prompt |
| `azlin killall` | Delete all VMs in RG | Single bulk prompt |
| `azlin destroy --delete-rg` | Delete entire RG | Extra warning |

## Related Commands

- [`azlin list`](../QUICK_REFERENCE.md#list-vms) - List VMs before deletion
- [`azlin killall`](../QUICK_REFERENCE.md#vm-deletion-new) - Bulk deletion
- `azlin status <vm>` - Check VM details before destroying

## Troubleshooting

### "Resource still in use" Error

**Problem:** NSG or NIC cannot be deleted because it be attached elsewhere.

**Solution:** Azure prevents deletion automatically. The VM deletion succeeds, orphaned resources be cleaned up when no longer in use.

### Deletion Timeout

**Problem:** Deletion takes longer than 5 minutes.

**Solution:**
```bash
# Use --no-wait flag (advanced)
export AZLIN_NO_WAIT=1
azlin destroy my-vm --force
```

### Can't Find VM by Name

**Problem:** VM name doesn't match what ye expect.

**Solution:**
```bash
# List all VMs first
azlin list

# Use exact name from list output
azlin destroy azlin-20250112-143022
```

## See Also

- [Quick Reference Guide](../QUICK_REFERENCE.md) - All azlin commands
- [VM Lifecycle](../vm-lifecycle-architecture.md) - Lifecycle management
- [Resource Management](../ARCHITECTURE.md) - Architecture overview
