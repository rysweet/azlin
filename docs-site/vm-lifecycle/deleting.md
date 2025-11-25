# Deleting VMs

Comprehensive guide to VM deletion, cleanup, and resource management.

## Overview

azlin provides multiple commands for VM deletion with different safety levels and use cases:

- **`azlin kill`** - Delete single VM and resources
- **`azlin destroy`** - Delete VM with dry-run and RG deletion options
- **`azlin killall`** - Delete all VMs in resource group
- **`azlin prune`** - Intelligently delete inactive/idle VMs

All commands clean up associated resources (NICs, disks, public IPs) to avoid orphaned resources and unnecessary costs.

## Commands

### azlin kill

Delete a specific VM and all associated resources.

```bash
# Delete a VM (with confirmation)
azlin kill my-vm

# Delete without confirmation
azlin kill my-vm --force

# Delete in specific resource group
azlin kill my-vm --rg other-group
```

**Options:**
- `--force` - Skip confirmation prompt
- `--resource-group`, `--rg` - Specify resource group

**Use Case:** Remove a specific VM you no longer need.

### azlin destroy

Enhanced deletion with dry-run and resource group deletion.

```bash
# Preview what would be deleted
azlin destroy my-vm --dry-run

# Delete VM
azlin destroy my-vm

# Delete VM and entire resource group (DANGEROUS!)
azlin destroy my-vm --delete-rg --force

# Delete without confirmation
azlin destroy my-vm --force
```

**Options:**
- `--dry-run` - Show what would be deleted without deleting
- `--delete-rg` - Delete entire resource group (use with extreme caution)
- `--force` - Skip confirmation
- `--resource-group`, `--rg` - Specify resource group

**Use Case:** When you want to preview deletions or remove entire resource groups.

### azlin killall

Delete all VMs in a resource group, optionally filtered by prefix.

```bash
# Delete all VMs (with confirmation)
azlin killall

# Delete all VMs without confirmation
azlin killall --force

# Delete only VMs with specific prefix
azlin killall --prefix test-vm

# Delete in specific resource group
azlin killall --rg dev-team --force
```

**Options:**
- `--prefix` - Only delete VMs starting with this prefix
- `--force` - Skip confirmation
- `--resource-group`, `--rg` - Specify resource group

**Use Case:** Clean up entire resource groups or VM fleets with common prefix.

### azlin prune

Intelligently delete inactive, old, or idle VMs.

```bash
# Preview what would be pruned (recommended first step)
azlin prune --dry-run

# Prune VMs idle for 1+ days (default)
azlin prune

# Prune VMs older than 7 days, idle for 3+ days
azlin prune --age-days 7 --idle-days 3

# Include running VMs in prune check
azlin prune --include-running

# Include VMs with named sessions
azlin prune --include-named

# Force prune without confirmation
azlin prune --force
```

**Options:**
- `--age-days` - Age threshold in days (default: 1)
- `--idle-days` - Idle threshold in days (default: 1)
- `--dry-run` - Preview without deleting
- `--force` - Skip confirmation
- `--include-running` - Include running VMs (default: stopped only)
- `--include-named` - Include VMs with session names (default: unnamed only)
- `--resource-group`, `--rg` - Specify resource group

**Use Case:** Automated cleanup of forgotten or abandoned VMs to reduce costs.

## Examples

### Delete Single VM

```bash
# Basic deletion
azlin kill azlin-vm-12345

# Force delete without prompts
azlin kill azlin-vm-12345 --force
```

### Preview Before Deletion

```bash
# See what would be deleted
azlin destroy my-vm --dry-run
```

**Output:**
```
Would delete:
  - VM: my-vm
  - NIC: my-vm-nic
  - Disk: my-vm_OsDisk_1
  - Public IP: my-vm-ip
```

### Delete All Test VMs

```bash
# Delete all VMs with 'test-' prefix
azlin killall --prefix test- --force
```

### Clean Up Old Development VMs

```bash
# Preview prune operation
azlin prune --age-days 3 --idle-days 2 --dry-run

# Execute prune
azlin prune --age-days 3 --idle-days 2
```

**Output:**
```
Found 3 VMs matching criteria:
  - old-dev-vm-1 (created 5 days ago, idle 4 days)
  - old-dev-vm-2 (created 7 days ago, idle 6 days)
  - test-experiment (created 10 days ago, idle 9 days)

Delete these VMs? [y/N]:
```

### Emergency Cleanup

```bash
# Delete everything in resource group
azlin killall --force
```

### Delete Resource Group

```bash
# DANGEROUS: Delete VM and entire RG
azlin destroy my-vm --delete-rg --force
```

**Warning:** This deletes EVERYTHING in the resource group, not just the VM.

## Safety Features

### Confirmation Prompts

All deletion commands prompt for confirmation unless `--force` is used:

```
Delete VM 'my-vm' and all associated resources? [y/N]:
```

### Dry Run

`destroy` and `prune` support `--dry-run` to preview operations:

```bash
azlin destroy my-vm --dry-run
azlin prune --dry-run
```

### Resource Cleanup

All commands automatically clean up:
- Network interfaces (NICs)
- OS disks
- Data disks
- Public IP addresses

This prevents orphaned resources and continued billing.

## Prune Criteria

The `prune` command evaluates VMs based on:

### Age
- How long since VM was created
- Default: 1+ days old
- Configurable with `--age-days`

### Idle Time
- Time since last activity (SSH connection, commands)
- Default: 1+ days idle
- Configurable with `--idle-days`

### State
- Default: Only stopped/deallocated VMs
- Use `--include-running` to include running VMs

### Named Sessions
- Default: Only VMs without session names
- Use `--include-named` to include named VMs

## Common Use Cases

### 1. Delete Finished Work VM

```bash
azlin kill project-vm-123
```

### 2. End of Day Cleanup

```bash
# Delete all temporary test VMs
azlin killall --prefix temp- --force
```

### 3. Weekly Cost Optimization

```bash
# Find and delete VMs idle for a week
azlin prune --age-days 7 --idle-days 7 --dry-run
# Review, then:
azlin prune --age-days 7 --idle-days 7
```

### 4. Project Cleanup

```bash
# Delete all VMs for completed project
azlin killall --prefix myproject- --force
```

### 5. Emergency Stop All

```bash
# Stop and delete everything
azlin killall --force
```

## Cost Implications

### Immediate Savings

Deleting VMs immediately stops:
- Compute costs (VM pricing)
- Public IP costs (if attached)
- Premium disk costs (for premium storage)

### Retained Costs

Some resources may remain unless manually deleted:
- Storage accounts (NFS shares)
- Snapshots
- Azure Bastion hosts
- Key Vaults

### Prune for Automatic Savings

Set up a cron job or scheduled task:

```bash
# Daily cleanup of VMs idle for 2+ days
0 2 * * * azlin prune --age-days 2 --idle-days 2 --force
```

## Troubleshooting

### "Resource Not Found" Errors

**Cause:** VM or resources already deleted.

**Solution:** Normal - azlin continues to clean up remaining resources.

### Partial Deletion

**Symptom:** VM deleted but resources remain.

**Cause:** Permission issues or resource locks.

**Solution:**
```bash
# Use Azure CLI to check for locks
az resource list --resource-group my-rg

# Remove locks if needed
az lock delete --name lock-name --resource-group my-rg
```

### "Cannot Delete" Errors

**Cause:** Resource locked or in use.

**Solution:**
1. Stop any running processes/connections
2. Check for Azure locks
3. Verify permissions (need Contributor role)

### Prune Not Finding VMs

**Cause:** All VMs are either running, named, or not meeting age/idle criteria.

**Solution:**
```bash
# Check with more inclusive options
azlin prune --include-running --include-named --dry-run

# Lower thresholds
azlin prune --age-days 0 --idle-days 0 --dry-run
```

## Best Practices

### 1. Always Dry Run First

For prune and destroy operations:

```bash
azlin prune --dry-run
azlin destroy my-vm --dry-run
```

### 2. Use Prune Regularly

Automated cost management:

```bash
# Weekly cleanup of abandoned VMs
azlin prune --age-days 7 --idle-days 7
```

### 3. Tag Before Deleting

Tag VMs to prevent accidental deletion:

```bash
azlin tag important-vm --add keep=true
```

Then filter prune to exclude:
```bash
# Prune only untagged or dev VMs
azlin list | grep -v keep=true | ...
```

### 4. Use Prefixes for Test VMs

Name test VMs with prefix for easy cleanup:

```bash
azlin new --name test-experiment-1
# Later:
azlin killall --prefix test- --force
```

### 5. Confirm Resource Group Before killall

Always verify RG before mass deletion:

```bash
# Check current RG
azlin list

# Then delete
azlin killall --force
```

## See Also

- [Creating VMs](creating.md)
- [Listing VMs](listing.md)
- [Cost Tracking](../monitoring/cost.md)
- [Tags Guide](../advanced/tags.md)
- [Pruning Advanced](../advanced/pruning.md)

---

*Documentation last updated: 2025-11-24*
