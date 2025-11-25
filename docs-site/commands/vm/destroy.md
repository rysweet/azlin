# azlin destroy

**Destroy VM and optionally entire resource group**

## Description

The `azlin destroy` command is an alias for `azlin kill` with additional options. It deletes a VM and all associated resources (disk, network interface, public IP), with options for dry-run testing and resource group deletion.

**Use with caution** - this operation is irreversible.

## Usage

```bash
azlin destroy [OPTIONS] VM_NAME
```

## Arguments

| Argument | Description |
|----------|-------------|
| `VM_NAME` | Name of the VM to destroy (required) |

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--resource-group, --rg TEXT` | Name | Azure resource group |
| `--config PATH` | Path | Config file path |
| `--force` | Flag | Skip confirmation prompt |
| `--dry-run` | Flag | Show what would be deleted without deleting |
| `--delete-rg` | Flag | Delete entire resource group (use with extreme caution) |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Basic Destruction

```bash
azlin destroy azlin-vm-12345
```

### Dry Run (Preview)

```bash
# See what would be deleted without actually deleting
azlin destroy my-vm --dry-run
```

**Output:**
```
DRY RUN - Nothing will be deleted

Would delete:
  VM: my-vm
  OS Disk: my-vm_OsDisk_1234
  NIC: my-vm-nic
  Public IP: my-vm-ip

Total resources: 4
```

### Force Destroy

```bash
# Skip confirmation prompt
azlin destroy my-vm --force
```

### Destroy with Resource Group

```bash
azlin destroy my-vm --rg my-resource-group
```

### Delete Entire Resource Group

```bash
# WARNING: Deletes ALL resources in the group
azlin destroy my-vm --delete-rg --force
```

## What Gets Deleted

By default:
- VM itself
- OS disk
- Data disks (if any)
- Network interface (NIC)
- Public IP address (if assigned)

With `--delete-rg`:
- Everything above, PLUS
- All other VMs in the resource group
- All storage accounts
- All network resources
- Virtual networks
- ALL resources in the group

## Behavior

### Standard Destroy

1. **Validation** - Checks VM exists
2. **Resource Discovery** - Identifies associated resources
3. **Confirmation** - Prompts for confirmation (unless `--force`)
4. **Deletion** - Deletes VM and associated resources
5. **Cleanup** - Verifies all resources deleted

### Dry Run

Shows exactly what would be deleted without making changes. Safe to run anytime.

### Delete Resource Group

**EXTREME CAUTION**: This deletes the ENTIRE resource group including all VMs, storage, networks, and other resources. Cannot be undone.

## Troubleshooting

### VM Not Found

**Symptoms:** "VM 'NAME' not found"

**Solutions:**
```bash
# List VMs to find correct name
azlin list

# Check resource group
azlin list --rg my-resource-group
```

### Deletion Fails

**Symptoms:** Some resources fail to delete

**Solutions:**
```bash
# Check Azure Portal for dependencies
# Some resources may have locks or dependencies

# Retry with explicit resource group
azlin destroy my-vm --rg my-resource-group --force

# Or use Azure Portal to investigate and delete manually
```

### Accidental Deletion

**Symptoms:** Deleted wrong VM

**Solutions:**
```bash
# If you have snapshots, restore
azlin snapshot list
azlin snapshot restore my-vm snapshot-name

# Otherwise, recreate and sync
azlin new --name my-vm
azlin sync --vm-name my-vm
```

## Safety Best Practices

### Always Dry Run First

```bash
# ALWAYS run dry-run first
azlin destroy my-vm --dry-run

# Review output carefully
# Only proceed if correct
azlin destroy my-vm --force
```

### Never Use --delete-rg Lightly

```bash
# NEVER run this without extreme caution
# azlin destroy my-vm --delete-rg

# This deletes EVERYTHING in the resource group
# Only use if you're absolutely certain
```

### Create Snapshots First

```bash
# Snapshot before destroying
azlin snapshot create my-vm

# Then destroy
azlin destroy my-vm --force

# Can restore if needed
azlin snapshot restore my-vm my-vm-snapshot-...
```

### Verify Context

```bash
# Check what subscription you're in
azlin context current

# Ensure correct context before destroying
azlin context use correct-context
azlin destroy my-vm --dry-run
azlin destroy my-vm --force
```

## Comparison with azlin kill

| Feature | `azlin destroy` | `azlin kill` |
|---------|-----------------|--------------|
| Delete VM | ✓ | ✓ |
| Delete resources | ✓ | ✓ |
| Dry-run mode | ✓ | ✗ |
| Delete RG option | ✓ | ✗ |
| Force flag | ✓ | ✓ |

## Related Commands

- [`azlin kill`](kill.md) - Simple VM deletion
- [`azlin killall`](killall.md) - Delete all VMs in resource group
- [`azlin prune`](../util/prune.md) - Delete inactive VMs
- [`azlin snapshot create`](../snapshot/create.md) - Create snapshot before destroying

## Source Code

- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - Command definition
- [vm_operations.py](https://github.com/rysweet/azlin/blob/main/src/azlin/vm_operations.py) - Deletion logic

## See Also

- [All VM commands](index.md)
- [Restoring Snapshots](../../snapshots/restore.md)
- [Scheduled Backups](../../snapshots/scheduled.md)
