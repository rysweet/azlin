# Destroy Command Integration Guide

This document explains the enhancements made to `azlin kill`/`killall` and provides instructions for adding the `azlin destroy` command.

## Changes Made

### 1. Enhanced `vm_lifecycle.py`

Added the following features to `/Users/ryan/src/azlin-feat-1/src/azlin/vm_lifecycle.py`:

- **New Data Models**:
  - `VMResource`: Represents a single Azure resource with optional cost information
  - `VMResources`: Collection of resources for a VM

- **Enhanced `delete_vm()` method**:
  - Added `delete_rg` parameter to delete entire resource group
  - Added `dry_run` parameter to show what would be deleted without actually deleting
  - Returns `DeletionResult` with `dry_run` flag

- **Enhanced `delete_all_vms()` method**:
  - Added `dry_run` parameter
  - Returns `DeletionSummary` with `dry_run` flag

- **New Methods**:
  - `list_vm_resources(vm_name, resource_group)`: Lists all resources associated with a VM
  - `delete_resource_group(resource_group, dry_run)`: Deletes an entire resource group

### 2. Existing CLI Commands

The following commands already exist in `src/azlin/cli.py`:

- `azlin kill <vm-name>` - Delete a VM (lines 993-1076)
- `azlin killall` - Delete all VMs (lines 1079-1182)

Both commands already support:
- `--force` flag for skipping confirmation
- `--resource-group` / `--rg` flag
- `--config` flag

## Integration TODO

To complete the destroy feature implementation, add the following command to `src/azlin/cli.py`:

```python
@main.command()
@click.argument('vm_name', required=False, type=str)
@click.option('--all', 'destroy_all', is_flag=True, help='Destroy all VMs')
@click.option('--resource-group', '--rg', help='Resource group', type=str)
@click.option('--config', help='Config file path', type=click.Path())
@click.option('--delete-rg', is_flag=True, help='Delete entire resource group')
@click.option('--force', is_flag=True, help='Skip confirmation')
@click.option('--dry-run', is_flag=True, help='Show what would be deleted')
@click.option('--prefix', default='azlin', help='VM prefix (with --all)')
def destroy(
    vm_name: Optional[str],
    destroy_all: bool,
    resource_group: Optional[str],
    config: Optional[str],
    delete_rg: bool,
    force: bool,
    dry_run: bool,
    prefix: str
):
    """Destroy VM(s) with enhanced safety features.

    Primary command for VM deletion with dry-run mode and resource group cleanup.
    Aliases: kill, killall (for backward compatibility).

    \b
    Examples:
        azlin destroy my-vm
        azlin destroy my-vm --delete-rg
        azlin destroy my-vm --dry-run
        azlin destroy --all --dry-run
        azlin destroy my-vm --force
    """
    try:
        rg = ConfigManager.get_resource_group(resource_group, config)
        
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)
        
        # Handle --all flag
        if destroy_all:
            vms = VMManager.list_vms(rg, include_stopped=True)
            vms = VMManager.filter_by_prefix(vms, prefix)
            
            if not vms:
                click.echo(f"No VMs found with prefix '{prefix}'.")
                return
            
            # Dry run
            if dry_run:
                click.echo(f"\n[DRY RUN] Would delete {len(vms)} VM(s):")
                for vm in vms:
                    click.echo(f"  - {vm.name} ({vm.get_status_display()})")
                return
            
            # Confirmation
            if not force:
                click.echo(f"\nWill delete {len(vms)} VM(s). Type 'yes' to confirm: ", nl=False)
                if input().lower() != 'yes':
                    click.echo("Cancelled.")
                    return
            
            # Delete
            summary = VMLifecycleManager.delete_all_vms(
                resource_group=rg,
                force=True,
                vm_prefix=prefix,
                dry_run=False
            )
            
            click.echo(f"\nDeleted {summary.succeeded}/{summary.total} VMs")
            return
        
        # Single VM destruction
        if not vm_name:
            click.echo("Error: VM name required or use --all", err=True)
            sys.exit(1)
        
        # List resources
        try:
            vm_resources = VMLifecycleManager.list_vm_resources(vm_name, rg)
        except VMLifecycleError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        
        # Dry run
        if dry_run:
            prefix = "[DRY RUN] Would delete"
            if delete_rg:
                click.echo(f"\n{prefix} resource group '{rg}':")
            else:
                click.echo(f"\n{prefix} VM '{vm_name}':")
            
            for resource in vm_resources.resources:
                click.echo(f"  - {resource}")
            click.echo(f"\nTotal: {vm_resources.resource_count} resources")
            return
        
        # Confirmation
        if not force:
            click.echo(f"\nResources to delete:")
            for resource in vm_resources.resources:
                click.echo(f"  - {resource}")
            click.echo(f"\nType 'yes' to confirm: ", nl=False)
            if input().lower() != 'yes':
                click.echo("Cancelled.")
                return
        
        # Delete
        result = VMLifecycleManager.delete_vm(
            vm_name=vm_name,
            resource_group=rg,
            delete_rg=delete_rg,
            force=True,
            dry_run=False
        )
        
        if result.success:
            click.echo(f"\nSuccess! {result.message}")
        else:
            click.echo(f"\nError: {result.message}", err=True)
            sys.exit(1)
    
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
```

## Testing

The enhanced functionality can be tested with:

```bash
# Dry run - see what would be deleted
azlin destroy my-vm --dry-run

# Dry run with resource group deletion
azlin destroy my-vm --delete-rg --dry-run

# Dry run for all VMs
azlin destroy --all --dry-run

# Actual deletion (with confirmation)
azlin destroy my-vm

# Delete with resource group
azlin destroy my-vm --delete-rg

# Force mode (skip confirmation)
azlin destroy my-vm --force

# Delete all VMs
azlin destroy --all
```

## Backward Compatibility

The existing `kill` and `killall` commands continue to work exactly as before. The `destroy` command is an enhanced version with additional safety features.

## Future Enhancements

1. Cost estimation in dry-run output
2. Resource tagging for better tracking
3. Snapshot creation before destruction
4. Parallel resource group deletion
