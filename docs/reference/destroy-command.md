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
| `--delete-rg` | **Rejected.** `destroy` refuses this flag outright — see [Resource Group Deletion](#resource-group-deletion) below. |

## What Gets Deleted

### Resource Deletion Order

Resources are deleted in the followin' order to handle dependencies:

1. **Virtual Machine** - The VM instance itself
2. **OS and Data Disks** - All disks owned by the VM
3. **Network Interfaces (NICs)** - All network interfaces attached to the VM
4. **Public IP Addresses** - Public IPs associated with the VM's NIC(s)
5. **Network Security Groups (NSGs)** - NSGs associated with the VM's NIC(s)

The NIC must be fully deleted before its Public IP or NSG can be — Azure
refuses to delete either while a NIC still references it. That's why NICs are
torn down third and the Public IP/NSG come last, not the other way around.

### NSG and Public IP Deletion Behavior

- The Public IP and NSG are discovered by querying the resource group,
  scoped to the `azlin-session` tag so a sibling session's resources are
  never touched
- Deletion is idempotent and best-effort per resource: a resource Azure has
  already removed (404) counts as success, and one failed resource does not
  abort the rest
- Azure's association data can lag briefly after a NIC delete (a stale or
  "ghost" reference — see [Microsoft's troubleshooting
  guidance](https://learn.microsoft.com/en-us/answers/questions/691897/cannot-delete-nsg-associted-with-with-non-existent)).
  `destroy` re-checks anything it had to skip as still-in-use once the NIC
  delete has settled, and deletes it then if it's now genuinely free
- A Public IP or NSG with no `azlin-session` tag at all is never deleted
  automatically — ownership can't be proven. `destroy` reports it instead and
  points at `azlin cleanup`

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
  ✓ Deleted disk: azlin-vm-osdisk
  ✓ Deleted NIC: azlin-vm-nic
  ✓ Deleted Public IP: azlin-vm-ip
  ✓ Deleted NSG: azlin-vm-nsg

Deleted azlin-vm-20250112-120000 and 4 associated resource(s) (~$3.65/month reclaimed)
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

**This is rejected.** `--delete-rg` is parsed but always refused with an
error — it is *not* a supported way to delete a resource group. Resource
groups routinely hold hand-made VMs, VNets and Public IPs alongside azlin
sessions, so honoring the flag could destroy unrelated data with no way back.
`destroy` only ever removes the named VM and its own disks, NIC, Public IP
and NSG.

If you really do want to delete the whole resource group, run the Azure CLI
directly and accept that responsibility explicitly:

```bash
az group delete --name my-resource-group
```

To reclaim other leftovers in a resource group without deleting the group
itself, use `azlin cleanup --resource-group my-resource-group`.

## Comparison with killall

| Command | Purpose | Confirmation |
|---------|---------|--------------|
| `azlin destroy <vm-name>` | Delete single VM | Per-VM prompt |
| `azlin killall` | Delete all VMs matching a prefix in a resource group | Single bulk prompt |
| `azlin destroy --delete-rg` | **Rejected** — not supported | n/a |

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
