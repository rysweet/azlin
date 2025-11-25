# azlin kill

**Delete a VM and all associated resources**

## Description

The `azlin kill` command deletes a VM and all its associated Azure resources: the VM itself, OS disk, network interface, and public IP. This is the quickest way to completely remove a VM from Azure.

**Warning:** This operation is irreversible. The VM and all data will be permanently deleted.

## Usage

```bash
azlin kill [OPTIONS] VM_NAME
```

## Arguments

| Argument | Description |
|----------|-------------|
| `VM_NAME` | Name of the VM to delete (required) |

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--resource-group, --rg TEXT` | Name | Azure resource group |
| `--config PATH` | Path | Config file path |
| `--force` | Flag | Skip confirmation prompt |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Delete with Confirmation

```bash
azlin kill azlin-vm-12345
```

**Output:**
```
Delete VM: azlin-vm-12345

Resources to delete:
  - VM: azlin-vm-12345
  - OS Disk: azlin-vm-12345_OsDisk_1234
  - NIC: azlin-vm-12345-nic
  - Public IP: azlin-vm-12345-ip

Continue? [y/N]: y

Deleting resources...
✓ Deleted VM
✓ Deleted disk
✓ Deleted NIC
✓ Deleted Public IP

VM 'azlin-vm-12345' deleted successfully.
```

### Force Delete (No Confirmation)

```bash
azlin kill my-vm --force
```

### Delete with Resource Group

```bash
azlin kill my-vm --rg my-resource-group
```

### Delete Multiple VMs

```bash
# Delete several VMs in sequence
azlin kill vm1 --force
azlin kill vm2 --force
azlin kill vm3 --force

# Or use a loop
for vm in vm1 vm2 vm3; do
  azlin kill $vm --force
done
```

## What Gets Deleted

The command deletes:

1. **VM** - The virtual machine instance
2. **OS Disk** - Boot disk attached to VM
3. **Data Disks** - Any additional data disks
4. **Network Interface (NIC)** - Network card
5. **Public IP** - Public IP address (if assigned)
6. **NSG Rules** - Network security group rules specific to this VM

**NOT deleted:**
- Resource group (use `azlin destroy --delete-rg` for that)
- Shared resources (VNet, storage accounts, etc.)
- SSH keys
- Snapshots

## Behavior

1. **Validation** - Verifies VM exists
2. **Resource Discovery** - Identifies all associated resources
3. **Confirmation** - Prompts user (unless `--force`)
4. **Deletion** - Deletes resources in order:
   - VM first
   - Then disk, NIC, and IP in parallel
5. **Verification** - Confirms all resources deleted

## Troubleshooting

### VM Not Found

**Symptoms:** "VM 'NAME' not found"

**Solutions:**
```bash
# List VMs to find correct name
azlin list

# Check spelling and resource group
azlin list --rg my-resource-group
```

### Deletion Hangs

**Symptoms:** Command hangs during deletion

**Solutions:**
```bash
# Check Azure Portal for status
# VM may be in transitional state

# Wait a few minutes, then retry
azlin kill my-vm --force

# If still stuck, use Azure Portal to investigate
```

### Permission Denied

**Symptoms:** "Insufficient permissions" error

**Solutions:**
```bash
# Verify you have Contributor or Owner role
# Check with Azure admin

# Try with explicit resource group
azlin kill my-vm --rg my-resource-group --force
```

### Partial Deletion

**Symptoms:** VM deleted but some resources remain

**Solutions:**
```bash
# Check Azure Portal for orphaned resources
# Delete manually via Portal or CLI

# Common orphans:
az disk list --query "[?contains(name, 'my-vm')]"
az network nic list --query "[?contains(name, 'my-vm')]"
az network public-ip list --query "[?contains(name, 'my-vm')]"
```

## Safety Best Practices

### Always Verify Before Deleting

```bash
# Check what VM you're about to delete
azlin status my-vm

# Verify it's the right one
azlin connect my-vm  # Quick check
```

### Create Snapshots First

```bash
# Snapshot before deleting
azlin snapshot create my-vm

# Then delete
azlin kill my-vm --force

# Can restore later if needed
azlin snapshot list
azlin snapshot restore my-vm snapshot-name
```

### Use Dry Run for Critical VMs

```bash
# Use azlin destroy for dry-run capability
azlin destroy my-vm --dry-run

# Review what would be deleted
# Then proceed with kill
azlin kill my-vm --force
```

### Verify Subscription/Context

```bash
# Always check your context first
azlin context current

# Make sure you're in the right subscription
# Then delete
azlin kill my-vm --force
```

## Comparison with Other Delete Commands

| Command | Purpose | Options |
|---------|---------|---------|
| `azlin kill` | Quick VM deletion | Basic, fast |
| `azlin destroy` | VM deletion with options | Dry-run, delete-rg |
| `azlin killall` | Delete all VMs in RG | Mass deletion |
| `azlin prune` | Delete inactive VMs | Age/idle filters |

## Common Workflows

### Clean Up Test VMs

```bash
# Delete test VMs after work
azlin kill test-vm-1 --force
azlin kill test-vm-2 --force
azlin kill test-vm-3 --force
```

### Remove Failed Provisioning

```bash
# If provisioning failed, clean up
azlin kill azlin-vm-failed-12345 --force
```

### Pre-Recreation Cleanup

```bash
# Delete old VM before recreating with same name
azlin kill old-vm --force
azlin new --name old-vm
```

## Automation Examples

### Script to Delete Multiple VMs

```bash
#!/bin/bash
# Delete all VMs matching a pattern

VMS=$(azlin list --format json | jq -r '.[] | select(.name | contains("temp-")) | .name')

for vm in $VMS; do
  echo "Deleting $vm..."
  azlin kill "$vm" --force
done

echo "Cleanup complete"
```

### Scheduled Cleanup

```bash
# Add to crontab for nightly cleanup
# Delete VMs tagged for deletion
# 0 2 * * * /path/to/cleanup-vms.sh

#!/bin/bash
VMS_TO_DELETE=$(azlin list --tag delete-after=$(date +%Y-%m-%d) --format json | jq -r '.[].name')

for vm in $VMS_TO_DELETE; do
  azlin kill "$vm" --force
done
```

## Related Commands

- [`azlin destroy`](destroy.md) - Delete with dry-run and RG options
- [`azlin killall`](killall.md) - Delete all VMs in resource group
- [`azlin prune`](../util/prune.md) - Delete inactive VMs automatically
- [`azlin snapshot create`](../snapshot/create.md) - Backup before deletion

## Source Code

- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - Command definition
- [vm_operations.py](https://github.com/rysweet/azlin/blob/main/src/azlin/vm_operations.py) - Deletion logic

## See Also

- [All VM commands](index.md)
- [Quota Management](../../advanced/quotas.md)
- [Cost Tracking](../../monitoring/cost.md)
