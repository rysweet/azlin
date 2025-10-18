"""Storage management CLI commands for Azure Files NFS.

This module provides commands for managing shared Azure Files NFS storage:
- Create and delete storage accounts
- List storage accounts
- Show storage status and usage
- Mount and unmount NFS shares on VMs
"""

import logging
import sys
from pathlib import Path

import click

from azlin.config_manager import ConfigError, ConfigManager
from azlin.modules.nfs_mount_manager import NFSMountManager
from azlin.modules.storage_manager import StorageManager
from azlin.vm_manager import VMManager

logger = logging.getLogger(__name__)


@click.group(name="storage")
def storage_group():
    """Manage Azure Files NFS shared storage.

    Create and manage Azure Files NFS storage accounts for sharing
    home directories across multiple VMs.

    \b
    COMMANDS:
        create     Create new NFS storage account
        list       List storage accounts
        status     Show storage status and usage
        delete     Delete storage account
        mount      Mount storage on VM
        unmount    Unmount storage from VM

    \b
    EXAMPLES:
        # Create 100GB Premium storage
        $ azlin storage create myteam-shared --size 100 --tier Premium

        # List all storage accounts
        $ azlin storage list

        # Mount storage on VM
        $ azlin storage mount myteam-shared --vm my-dev-vm

        # Check storage status
        $ azlin storage status myteam-shared

        # Unmount from VM
        $ azlin storage unmount my-dev-vm

        # Delete storage
        $ azlin storage delete myteam-shared
    """
    pass


@storage_group.command(name="create")
@click.argument("name", type=str)
@click.option("--size", type=int, default=100, help="Size in GB (default: 100)")
@click.option(
    "--tier",
    type=click.Choice(["Premium", "Standard"], case_sensitive=False),
    default="Premium",
    help="Storage tier (default: Premium)",
)
@click.option("--resource-group", "--rg", help="Azure resource group")
@click.option("--region", help="Azure region")
def create_storage(name: str, size: int, tier: str, resource_group: str | None, region: str | None):
    """Create Azure Files NFS storage account.

    Creates a new Azure Files storage account with NFS support for
    sharing home directories across VMs. The storage is accessible
    only within the Azure VNet for security.

    \b
    NAME should be globally unique across Azure (3-24 chars, lowercase/numbers).

    \b
    Storage tiers:
      Premium: $0.153/GB/month, high performance
      Standard: $0.0184/GB/month, standard performance

    \b
    Examples:
      $ azlin storage create myteam-shared --size 100 --tier Premium
      $ azlin storage create backups --size 500 --tier Standard
    """
    try:
        # Get config
        try:
            config = ConfigManager.get_config()
            rg = resource_group or config.resource_group
            location = region or config.region
        except ConfigError:
            click.echo(
                "Error: No config found. Run 'azlin new' first or specify --resource-group and --region.",
                err=True,
            )
            sys.exit(1)

        if not rg:
            click.echo(
                "Error: Resource group required. Use --resource-group or set in config.", err=True
            )
            sys.exit(1)

        if not location:
            click.echo("Error: Region required. Use --region or set in config.", err=True)
            sys.exit(1)

        # Validate inputs
        click.echo(f"Creating {tier} NFS storage account '{name}'...")
        click.echo(f"  Size: {size}GB")
        click.echo(f"  Resource Group: {rg}")
        click.echo(f"  Region: {location}")

        # Calculate cost
        cost_per_gb = 0.153 if tier.lower() == "premium" else 0.0184
        monthly_cost = size * cost_per_gb
        click.echo(f"  Estimated cost: ${monthly_cost:.2f}/month")

        # Create storage
        result = StorageManager.create_storage(
            name=name,
            resource_group=rg,
            location=location,
            size_gb=size,
            tier=tier,
        )

        click.echo("\n✓ Storage account created successfully")
        click.echo(f"  Name: {result.name}")
        click.echo(f"  NFS Endpoint: {result.nfs_endpoint}")
        click.echo(f"  Size: {result.size_gb}GB")
        click.echo(f"\nTo mount on a VM: azlin storage mount {name} --vm <vm-name>")

    except Exception as e:
        click.echo(f"Error creating storage: {e}", err=True)
        sys.exit(1)


@storage_group.command(name="list")
@click.option("--resource-group", "--rg", help="Azure resource group")
def list_storage(resource_group: str | None):
    """List Azure Files NFS storage accounts.

    Shows all NFS-enabled storage accounts in the resource group
    with their size, tier, and mount status.

    \b
    Examples:
      $ azlin storage list
      $ azlin storage list --resource-group azlin-rg
    """
    try:
        # Get config
        try:
            config = ConfigManager.get_config()
            rg = resource_group or config.resource_group
        except ConfigError:
            click.echo(
                "Error: No config found. Run 'azlin new' first or specify --resource-group.",
                err=True,
            )
            sys.exit(1)

        if not rg:
            click.echo("Error: Resource group required.", err=True)
            sys.exit(1)

        # List storage accounts
        accounts = StorageManager.list_storage(rg)

        if not accounts:
            click.echo(f"No NFS storage accounts found in resource group '{rg}'")
            return

        click.echo(f"\nStorage Accounts in {rg}:")
        click.echo("=" * 80)

        for account in accounts:
            click.echo(f"\n{account.name}")
            click.echo(f"  Endpoint: {account.nfs_endpoint}")
            click.echo(f"  Size: {account.size_gb}GB")
            click.echo(f"  Tier: {account.tier}")
            click.echo(f"  Location: {account.location}")

        click.echo(f"\nTotal: {len(accounts)} storage account(s)")

    except Exception as e:
        click.echo(f"Error listing storage: {e}", err=True)
        sys.exit(1)


@storage_group.command(name="status")
@click.argument("name", type=str)
@click.option("--resource-group", "--rg", help="Azure resource group")
def show_status(name: str, resource_group: str | None):
    """Show storage account status and usage.

    Displays detailed information about a storage account including
    usage statistics, connected VMs, and cost estimates.

    \b
    Examples:
      $ azlin storage status myteam-shared
    """
    try:
        # Get config
        try:
            config = ConfigManager.get_config()
            rg = resource_group or config.resource_group
        except ConfigError:
            click.echo(
                "Error: No config found. Run 'azlin new' first or specify --resource-group.",
                err=True,
            )
            sys.exit(1)

        if not rg:
            click.echo("Error: Resource group required.", err=True)
            sys.exit(1)

        # Get status
        status = StorageManager.get_storage_status(name, rg)

        click.echo(f"\nStorage Account: {status.name}")
        click.echo("=" * 80)
        click.echo(f"  Endpoint: {status.nfs_endpoint}")
        click.echo(f"  Location: {status.location}")
        click.echo(f"  Tier: {status.tier}")
        click.echo("\nCapacity:")
        click.echo(f"  Total: {status.size_gb}GB")
        click.echo(f"  Used: {status.used_gb}GB ({status.used_gb / status.size_gb * 100:.1f}%)")
        click.echo(f"  Available: {status.size_gb - status.used_gb}GB")
        click.echo("\nCost:")
        click.echo(f"  Monthly: ${status.cost_per_month:.2f}")
        click.echo("\nConnected VMs:")

        if status.connected_vms:
            for vm_name in status.connected_vms:
                click.echo(f"  - {vm_name}")
        else:
            click.echo("  (none)")

    except Exception as e:
        click.echo(f"Error getting storage status: {e}", err=True)
        sys.exit(1)


@storage_group.command(name="delete")
@click.argument("name", type=str)
@click.option("--resource-group", "--rg", help="Azure resource group")
@click.option("--force", is_flag=True, help="Force delete even if VMs are connected")
def delete_storage(name: str, resource_group: str | None, force: bool):
    """Delete Azure Files NFS storage account.

    Deletes a storage account. By default, prevents deletion if VMs
    are still connected. Use --force to override.

    WARNING: This deletes all data in the storage account.

    \b
    Examples:
      $ azlin storage delete myteam-shared
      $ azlin storage delete old-storage --force
    """
    try:
        # Get config
        try:
            config = ConfigManager.get_config()
            rg = resource_group or config.resource_group
        except ConfigError:
            click.echo(
                "Error: No config found. Run 'azlin new' first or specify --resource-group.",
                err=True,
            )
            sys.exit(1)

        if not rg:
            click.echo("Error: Resource group required.", err=True)
            sys.exit(1)

        # Confirm deletion
        if not force:
            click.echo(f"WARNING: This will delete storage account '{name}' and ALL DATA.")
            if not click.confirm("Are you sure?"):
                click.echo("Cancelled.")
                return

        # Delete storage
        click.echo(f"Deleting storage account '{name}'...")
        result = StorageManager.delete_storage(name, rg, force=force)

        if result.get("warning"):
            click.echo(f"Warning: {result['warning']}")

        click.echo(f"✓ Storage account '{name}' deleted successfully")

    except Exception as e:
        click.echo(f"Error deleting storage: {e}", err=True)
        sys.exit(1)


@storage_group.command(name="mount")
@click.argument("storage_name", type=str)
@click.option("--vm", required=True, help="VM name or identifier")
@click.option("--resource-group", "--rg", help="Azure resource group")
def mount_storage(storage_name: str, vm: str, resource_group: str | None):
    """Mount NFS storage on VM home directory.

    Mounts the specified storage account's NFS share to /home/azureuser
    on the VM, replacing the local home directory. Existing home
    directory contents are backed up first.

    \b
    Examples:
      $ azlin storage mount myteam-shared --vm my-dev-vm
    """
    try:
        # Get config
        try:
            config = ConfigManager.get_config()
            rg = resource_group or config.resource_group
        except ConfigError:
            click.echo(
                "Error: No config found. Run 'azlin new' first or specify --resource-group.",
                err=True,
            )
            sys.exit(1)

        if not rg:
            click.echo("Error: Resource group required.", err=True)
            sys.exit(1)

        # Get storage details
        click.echo(f"Getting storage account '{storage_name}'...")
        accounts = StorageManager.list_storage(rg)
        storage = next((a for a in accounts if a.name == storage_name), None)

        if not storage:
            click.echo(
                f"Error: Storage account '{storage_name}' not found in resource group '{rg}'",
                err=True,
            )
            sys.exit(1)

        # Get VM details
        click.echo(f"Getting VM '{vm}'...")
        vm_obj = VMManager.get_vm(vm, rg)

        if not vm_obj:
            click.echo(f"Error: VM '{vm}' not found in resource group '{rg}'", err=True)
            sys.exit(1)

        if not vm_obj.is_running():
            click.echo(
                f"Error: VM '{vm}' is not running. Start it first with: azlin start {vm}", err=True
            )
            sys.exit(1)

        if not vm_obj.public_ip:
            click.echo(f"Error: VM '{vm}' has no public IP address", err=True)
            sys.exit(1)

        # Get SSH key
        ssh_key_path = Path.home() / ".ssh" / "azlin"
        if not ssh_key_path.exists():
            click.echo(f"Error: SSH key not found at {ssh_key_path}", err=True)
            sys.exit(1)

        # Mount storage
        click.echo("Mounting storage on VM...")
        click.echo(f"  Storage: {storage_name}")
        click.echo(f"  Endpoint: {storage.nfs_endpoint}")
        click.echo(f"  VM: {vm_obj.name} ({vm_obj.public_ip})")

        result = NFSMountManager.mount_storage(
            vm_ip=vm_obj.public_ip,
            ssh_key=ssh_key_path,
            nfs_endpoint=storage.nfs_endpoint,
        )

        if result.get("backed_up"):
            click.echo(f"✓ Existing home directory backed up to: {result['backup_path']}")

        click.echo(f"✓ Storage mounted successfully on {vm_obj.name}")
        click.echo("\nThe VM now uses shared storage for its home directory.")
        click.echo(
            "All files in /home/azureuser are now shared across any VM with this storage mounted."
        )

        # Update config to track storage
        try:
            config.vm_storage = storage_name
            ConfigManager.save_config(config)
        except Exception:
            pass  # Non-critical

    except Exception as e:
        click.echo(f"Error mounting storage: {e}", err=True)
        sys.exit(1)


@storage_group.command(name="unmount")
@click.option("--vm", required=True, help="VM name or identifier")
@click.option("--resource-group", "--rg", help="Azure resource group")
def unmount_storage(vm: str, resource_group: str | None):
    """Unmount NFS storage from VM.

    Unmounts the NFS share from the VM and restores the local
    home directory from backup if available.

    \b
    Examples:
      $ azlin storage unmount --vm my-dev-vm
    """
    try:
        # Get config
        try:
            config = ConfigManager.get_config()
            rg = resource_group or config.resource_group
        except ConfigError:
            click.echo(
                "Error: No config found. Run 'azlin new' first or specify --resource-group.",
                err=True,
            )
            sys.exit(1)

        if not rg:
            click.echo("Error: Resource group required.", err=True)
            sys.exit(1)

        # Get VM details
        click.echo(f"Getting VM '{vm}'...")
        vm_obj = VMManager.get_vm(vm, rg)

        if not vm_obj:
            click.echo(f"Error: VM '{vm}' not found in resource group '{rg}'", err=True)
            sys.exit(1)

        if not vm_obj.is_running():
            click.echo(
                f"Error: VM '{vm}' is not running. Start it first with: azlin start {vm}", err=True
            )
            sys.exit(1)

        if not vm_obj.public_ip:
            click.echo(f"Error: VM '{vm}' has no public IP address", err=True)
            sys.exit(1)

        # Get SSH key
        ssh_key_path = Path.home() / ".ssh" / "azlin"
        if not ssh_key_path.exists():
            click.echo(f"Error: SSH key not found at {ssh_key_path}", err=True)
            sys.exit(1)

        # Unmount storage
        click.echo("Unmounting storage from VM...")
        click.echo(f"  VM: {vm_obj.name} ({vm_obj.public_ip})")

        result = NFSMountManager.unmount_storage(
            vm_ip=vm_obj.public_ip,
            ssh_key=ssh_key_path,
        )

        if result.get("restored"):
            click.echo(f"✓ Local home directory restored from: {result['backup_path']}")

        click.echo(f"✓ Storage unmounted successfully from {vm_obj.name}")
        click.echo("\nThe VM now uses its local disk for the home directory.")

        # Update config
        try:
            config.vm_storage = None
            ConfigManager.save_config(config)
        except Exception:
            pass  # Non-critical

    except Exception as e:
        click.echo(f"Error unmounting storage: {e}", err=True)
        sys.exit(1)


__all__ = ["storage_group"]
