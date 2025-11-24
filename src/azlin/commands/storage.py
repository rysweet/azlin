"""Storage management CLI commands for Azure Files NFS.

This module provides commands for managing shared Azure Files NFS storage:
- Create and delete storage accounts
- List storage accounts
- Show storage status and usage
- Mount and unmount NFS shares on VMs
- Mount and unmount SMB shares locally on macOS
"""

import logging
import sys
from pathlib import Path

import click
from rich.console import Console

from azlin.click_group import AzlinGroup
from azlin.config_manager import ConfigError, ConfigManager
from azlin.context_manager import ContextError, ContextManager
from azlin.modules.local_smb_mount import (
    LocalSMBMount,
    LocalSMBMountError,
    UnsupportedPlatformError,
)
from azlin.modules.nfs_mount_manager import NFSMountManager
from azlin.modules.storage_key_manager import StorageKeyError, StorageKeyManager
from azlin.modules.storage_manager import StorageManager
from azlin.vm_manager import VMManager

logger = logging.getLogger(__name__)


class MountGroup(click.Group):
    """Custom group that handles backward compatibility for mount command.

    Allows:
    - azlin storage mount vm <storage> --vm <vm>  (new explicit)
    - azlin storage mount local --mount-point ... (new explicit)
    - azlin storage mount <storage> --vm <vm>    (backward compat - auto-detects vm mount)
    """

    def main(self, *args, **kwargs):
        """Intercept args to handle backward compatibility."""
        # Find the "mount" argument position and check what comes after
        try:
            mount_idx = sys.argv.index("mount")
            if len(sys.argv) > mount_idx + 1:
                next_arg = sys.argv[mount_idx + 1]

                # If next_arg is not a known subcommand name and --vm is present (backward compat)
                if next_arg not in ("vm", "local", "--help", "-h") and "--vm" in sys.argv:
                    # Inject "vm" as the subcommand after "mount"
                    sys.argv.insert(mount_idx + 1, "vm")
        except (ValueError, IndexError):
            pass

        return super().main(*args, **kwargs)


@click.group(name="storage", cls=AzlinGroup)
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
        mount      Mount storage (group with vm/local subcommands)
        unmount    Unmount storage from VM

    \b
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
    console = Console()
    try:
        # Ensure Azure CLI subscription matches current context
        try:
            ContextManager.ensure_subscription_active()
        except ContextError as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)

        # Get config
        try:
            config = ConfigManager.load_config()
            rg = resource_group or config.default_resource_group
            location = region or config.default_region
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
            region=location,
            tier=tier,
            size_gb=size,
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
    console = Console()
    try:
        # Ensure Azure CLI subscription matches current context
        try:
            ContextManager.ensure_subscription_active()
        except ContextError as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)

        # Get config
        try:
            config = ConfigManager.load_config()
            rg = resource_group or config.default_resource_group
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
            click.echo(f"  Region: {account.region}")

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
    console = Console()
    try:
        # Ensure Azure CLI subscription matches current context
        try:
            ContextManager.ensure_subscription_active()
        except ContextError as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)

        # Get config
        try:
            config = ConfigManager.load_config()
            rg = resource_group or config.default_resource_group
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

        click.echo(f"\nStorage Account: {status.info.name}")
        click.echo("=" * 80)
        click.echo(f"  Endpoint: {status.info.nfs_endpoint}")
        click.echo(f"  Region: {status.info.region}")
        click.echo(f"  Tier: {status.info.tier}")
        click.echo("\nCapacity:")
        click.echo(f"  Total: {status.info.size_gb}GB")
        click.echo(f"  Used: {status.used_gb:.2f}GB ({status.utilization_percent:.1f}%)")
        click.echo(f"  Available: {status.info.size_gb - status.used_gb:.2f}GB")
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
    console = Console()
    try:
        # Ensure Azure CLI subscription matches current context
        try:
            ContextManager.ensure_subscription_active()
        except ContextError as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)

        # Get config
        try:
            config = ConfigManager.load_config()
            rg = resource_group or config.default_resource_group
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
        StorageManager.delete_storage(name, rg, force=force)

        # Clean up config
        try:
            config = ConfigManager.load_config()
            config_dict = config.to_dict()

            # Remove from storage accounts if present
            storage_accounts = config_dict.get("storage_accounts", {})
            if name in storage_accounts:
                del storage_accounts[name]

            # Remove any VM storage mappings
            vm_storage = config_dict.get("vm_storage", {})
            vms_to_update = [vm for vm, storage in vm_storage.items() if storage == name]
            for vm_name in vms_to_update:
                del vm_storage[vm_name]

            # Save updated config if changes were made
            if vms_to_update or name in config_dict.get("storage_accounts", {}):
                # Update the config object attributes
                # Note: storage_accounts is not in AzlinConfig dataclass, only vm_storage
                if hasattr(config, "vm_storage"):
                    config.vm_storage = vm_storage
                ConfigManager.save_config(config)
        except Exception as e:
            logger.warning(f"Failed to clean up config: {e}")

        click.echo(f"✓ Storage account '{name}' deleted successfully")

    except Exception as e:
        click.echo(f"Error deleting storage: {e}", err=True)
        sys.exit(1)


@storage_group.group(name="mount", cls=MountGroup)
def mount_group():
    """Mount storage on VM or locally.

    Two ways to mount storage:

    \b
    VM MOUNT (NFS shared across VMs):
        $ azlin storage mount vm <storage> --vm <vm-name>
        Mounts NFS storage on VM home directory for sharing.

    \b
    LOCAL MOUNT (local path):
        $ azlin storage mount local --mount-point ~/azure/
        Mounts storage locally (Linux/macOS only).

    \b
    BACKWARD COMPATIBILITY:
        $ azlin storage mount <storage> --vm <vm-name>
        Auto-detects and mounts on VM (same as: mount vm <storage> --vm <vm-name>)

    \b
    EXAMPLES:
        # Mount on VM (new)
        $ azlin storage mount vm myteam-shared --vm my-dev-vm

        # Mount locally (new)
        $ azlin storage mount local --mount-point ~/azure/

        # Mount on VM (backward compatible)
        $ azlin storage mount myteam-shared --vm my-dev-vm
    """
    pass


@mount_group.command(name="vm")
@click.argument("storage_name", type=str)
@click.option("--vm", required=True, help="VM name or identifier")
@click.option("--resource-group", "--rg", help="Azure resource group")
def mount_vm_storage(storage_name: str, vm: str, resource_group: str | None):
    """Mount NFS storage on VM home directory.

    Mounts the specified storage account's NFS share to /home/azureuser
    on the VM, replacing the local home directory. Existing home
    directory contents are backed up first.

    \b
    Examples:
      $ azlin storage mount vm myteam-shared --vm my-dev-vm
    """
    console = Console()
    try:
        # Ensure Azure CLI subscription matches current context
        try:
            ContextManager.ensure_subscription_active()
        except ContextError as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)

        # Get config
        try:
            config = ConfigManager.load_config()
            rg = resource_group or config.default_resource_group
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

        # Use public IP if available, otherwise private IP for Bastion-only VMs (Issue #372)
        vm_ip = vm_obj.public_ip or vm_obj.private_ip
        if not vm_ip:
            click.echo(f"Error: VM '{vm}' has no IP address (neither public nor private)", err=True)
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
        click.echo(f"  VM: {vm_obj.name} ({vm_ip})")

        result = NFSMountManager.mount_storage(
            vm_ip=vm_ip,
            ssh_key=ssh_key_path,
            nfs_endpoint=storage.nfs_endpoint,
        )

        if result.backed_up_files > 0:
            click.echo(f"✓ Existing home directory backed up ({result.backed_up_files} files)")

        click.echo(f"✓ Storage mounted successfully on {vm_obj.name}")
        click.echo("\nThe VM now uses shared storage for its home directory.")
        click.echo(
            "All files in /home/azureuser are now shared across any VM with this storage mounted."
        )

        # Update config to track storage
        try:
            if config.vm_storage is None:
                config.vm_storage = {}
            config.vm_storage[vm_obj.name] = storage_name
            ConfigManager.save_config(config)
        except Exception as e:
            logger.warning(f"Failed to save VM storage mapping: {e}")

    except Exception as e:
        click.echo(f"Error mounting storage: {e}", err=True)
        sys.exit(1)


@mount_group.command(name="local")
@click.option("--mount-point", required=True, type=click.Path(), help="Local mount point")
@click.option(
    "--storage",
    required=False,
    help="Storage account name (uses default if not provided)",
)
def mount_local_storage(mount_point: str, storage: str | None):
    """Mount storage locally on this machine.

    Mounts Azure Files SMB storage locally to the specified mount point.
    Only supported on macOS.

    \b
    Examples:
      $ azlin storage mount local --mount-point ~/azure/
      $ azlin storage mount local --mount-point /mnt/shared --storage myteam-shared
    """
    console = Console()

    try:
        # Platform check - LocalSMBMount will raise if not macOS
        # but we'll catch it explicitly for better error messages

        # Get config
        try:
            config = ConfigManager.load_config()
            rg = config.default_resource_group
        except ConfigError as e:
            click.echo(f"Error: {e}", err=True)
            click.echo("Run 'azlin new' to initialize config", err=True)
            sys.exit(1)

        if not rg:
            click.echo("Error: Resource group required. Set default_resource_group in config.", err=True)
            sys.exit(1)

        # Determine storage account to use
        storage_name = storage or config.default_nfs_storage
        if not storage_name:
            click.echo(
                "Error: No storage account specified and no default configured",
                err=True,
            )
            click.echo(
                "Either provide --storage option or set default_nfs_storage in config",
                err=True,
            )
            sys.exit(1)

        # Get subscription ID
        try:
            subscription_id = VMManager.get_subscription_id()
        except Exception as e:
            click.echo(f"Error getting subscription ID: {e}", err=True)
            sys.exit(1)

        # List storage accounts to get the storage info
        console.print(f"[blue]Looking up storage account: {storage_name}[/blue]")
        try:
            accounts = StorageManager.list_storage(rg)
            storage_obj = next((a for a in accounts if a.name == storage_name), None)

            if not storage_obj:
                click.echo(
                    f"Error: Storage account '{storage_name}' not found in "
                    f"resource group '{rg}'",
                    err=True,
                )
                sys.exit(1)

        except Exception as e:
            click.echo(f"Error listing storage accounts: {e}", err=True)
            sys.exit(1)

        # Parse NFS endpoint to extract share name
        # Format: "storageaccount.file.core.windows.net:/sharename"
        try:
            if not storage_obj.nfs_endpoint or ":" not in storage_obj.nfs_endpoint:
                click.echo(
                    f"Error: Invalid NFS endpoint format: {storage_obj.nfs_endpoint}",
                    err=True,
                )
                sys.exit(1)

            nfs_parts = storage_obj.nfs_endpoint.split(":")
            share_path = nfs_parts[1]  # "/sharename" or "/sharename/subdir"
            # For SMB, extract first directory component only (Azure Files share name)
            path_components = share_path.strip("/").split("/")
            share_name = path_components[0]  # First component = share name

            if not share_name:
                click.echo(
                    f"Error: Could not extract share name from NFS endpoint: "
                    f"{storage_obj.nfs_endpoint}",
                    err=True,
                )
                sys.exit(1)

        except IndexError:
            click.echo(
                f"Error: Invalid NFS endpoint format: {storage_obj.nfs_endpoint}",
                err=True,
            )
            sys.exit(1)

        # Get storage keys
        console.print("[blue]Retrieving storage account keys...[/blue]")
        if not subscription_id:
            click.echo("Error: Could not determine subscription ID", err=True)
            sys.exit(1)
        try:
            keys = StorageKeyManager.get_storage_keys(
                storage_account_name=storage_name,
                resource_group=rg,
                subscription_id=subscription_id,
            )
        except StorageKeyError as e:
            click.echo(f"Error getting storage keys: {e}", err=True)
            sys.exit(1)

        # Mount the share
        console.print(f"[blue]Mounting {storage_name}/{share_name} to {mount_point}...[/blue]")
        try:
            mount_point_path = Path(mount_point).expanduser()
            result = LocalSMBMount.mount(
                storage_account=storage_name,
                share_name=share_name,
                storage_key=keys.key1,
                mount_point=mount_point_path,
            )

            if result.success:
                console.print(
                    f"[green]✓ Mounted {storage_name}/{share_name} to {mount_point}[/green]"
                )
            else:
                click.echo("Error: Mount operation failed", err=True)
                if result.errors:
                    for error in result.errors:
                        click.echo(f"  {error}", err=True)
                sys.exit(1)

        except UnsupportedPlatformError as e:
            click.echo(f"Error: {e}", err=True)
            click.echo("Local mount is only supported on macOS", err=True)
            sys.exit(1)
        except LocalSMBMountError as e:
            click.echo(f"Error mounting share: {e}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
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
    console = Console()
    try:
        # Ensure Azure CLI subscription matches current context
        try:
            ContextManager.ensure_subscription_active()
        except ContextError as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)

        # Get config
        try:
            config = ConfigManager.load_config()
            rg = resource_group or config.default_resource_group
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

        # Use public IP if available, otherwise private IP for Bastion-only VMs (Issue #372)
        vm_ip = vm_obj.public_ip or vm_obj.private_ip
        if not vm_ip:
            click.echo(f"Error: VM '{vm}' has no IP address (neither public nor private)", err=True)
            sys.exit(1)

        # Get SSH key
        ssh_key_path = Path.home() / ".ssh" / "azlin"
        if not ssh_key_path.exists():
            click.echo(f"Error: SSH key not found at {ssh_key_path}", err=True)
            sys.exit(1)

        # Unmount storage
        click.echo("Unmounting storage from VM...")
        click.echo(f"  VM: {vm_obj.name} ({vm_ip})")

        result = NFSMountManager.unmount_storage(
            vm_ip=vm_ip,
            ssh_key=ssh_key_path,
        )

        if result.backed_up_files > 0:
            click.echo(f"✓ Local home directory restored ({result.backed_up_files} files)")

        click.echo(f"✓ Storage unmounted successfully from {vm_obj.name}")
        click.echo("\nThe VM now uses its local disk for the home directory.")

        # Update config
        try:
            if config.vm_storage and vm_obj.name in config.vm_storage:
                del config.vm_storage[vm_obj.name]
                ConfigManager.save_config(config)
        except Exception as e:
            logger.warning(f"Failed to clear VM storage mapping: {e}")

    except Exception as e:
        click.echo(f"Error unmounting storage: {e}", err=True)
        sys.exit(1)


@storage_group.group(name="mount-file")
def mount_file_group():
    """Mount file storage locally."""
    pass


@mount_file_group.command(name="local")
@click.option(
    "--mount-point",
    type=click.Path(path_type=Path),
    default="~/azure",
    help="Local directory to mount to (default: ~/azure)",
)
@click.option("--storage-account", help="Storage account name (overrides config)")
@click.option("--share-name", default="home", help="Share name (default: home)")
@click.option("--resource-group", "--rg", help="Azure resource group")
def mount_local(
    mount_point: Path,
    storage_account: str | None,
    share_name: str,
    resource_group: str | None,
):
    """Mount Azure Files SMB share locally on macOS.

    Mounts an Azure Files share to your local macOS machine using SMB.
    The storage account key is retrieved from Azure and used for authentication.

    By default, uses default_nfs_storage from config. You can override with
    --storage-account.

    \b
    Requirements:
      - macOS only
      - Azure authentication configured (az login)
      - Mount point directory exists or can be created

    \b
    Examples:
      # Mount default storage to ~/azure
      $ azlin storage mount local

      # Mount specific storage to custom location
      $ azlin storage mount local --storage-account myaccount --mount-point ~/mydata

      # Mount different share
      $ azlin storage mount local --share-name backups
    """
    console = Console()
    try:
        # Ensure Azure CLI subscription matches current context
        try:
            ContextManager.ensure_subscription_active()
        except ContextError as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)

        # Get config
        try:
            config = ConfigManager.load_config()
            rg = resource_group or config.default_resource_group
        except ConfigError:
            click.echo(
                "Error: No config found. Run 'azlin new' first or specify --resource-group.",
                err=True,
            )
            sys.exit(1)

        if not rg:
            click.echo("Error: Resource group required.", err=True)
            sys.exit(1)

        # Determine storage account name
        if not storage_account:
            # Use default from config
            storage_account = config.default_nfs_storage
            if not storage_account:
                click.echo(
                    "Error: No storage account specified and no default_nfs_storage in config.\n"
                    "Use --storage-account or set default_nfs_storage in ~/.azlin/config.toml",
                    err=True,
                )
                sys.exit(1)
            click.echo(f"Using default storage account: {storage_account}")

        # Get current context for subscription ID
        try:
            context_config = ContextManager.load(None)
            current_context = context_config.get_current_context()
            subscription_id = current_context.subscription_id
        except ContextError as e:
            click.echo(f"Error: Could not get current context: {e}", err=True)
            sys.exit(1)

        click.echo("Mounting Azure Files share locally...")
        click.echo(f"  Storage Account: {storage_account}")
        click.echo(f"  Share: {share_name}")
        click.echo(f"  Mount Point: {mount_point}")
        click.echo(f"  Resource Group: {rg}")

        # Get storage account keys from Azure
        click.echo("\nRetrieving storage account keys from Azure...")
        try:
            keys = StorageKeyManager.get_storage_keys(
                storage_account_name=storage_account,
                resource_group=rg,
                subscription_id=subscription_id,
            )
        except Exception as e:
            click.echo(f"Error retrieving storage keys: {e}", err=True)
            click.echo(
                "\nMake sure:\n"
                "  1. You're authenticated with Azure (az login)\n"
                "  2. The storage account exists\n"
                "  3. You have permission to access storage keys",
                err=True,
            )
            sys.exit(1)

        # Mount using SMB
        click.echo("Mounting SMB share...")
        try:
            result = LocalSMBMount.mount(
                storage_account=storage_account,
                share_name=share_name,
                storage_key=keys.key1,  # Use primary key
                mount_point=mount_point,
            )

            if result.success:
                click.echo(f"\n✓ Successfully mounted to: {result.mount_point}")
                click.echo(f"  SMB Share: {result.smb_share}")
                click.echo(f"\nYou can now access your Azure Files at: {result.mount_point}")
            else:
                click.echo("\nMount failed:", err=True)
                if result.errors:
                    for error in result.errors:
                        click.echo(f"  - {error}", err=True)
                sys.exit(1)

        except Exception as e:
            click.echo(f"Error mounting share: {e}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@storage_group.group(name="unmount-file")
def unmount_file_group():
    """Unmount file storage from local machine."""
    pass


@unmount_file_group.command(name="local")
@click.option(
    "--mount-point",
    type=click.Path(path_type=Path),
    default="~/azure",
    help="Local mount point to unmount (default: ~/azure)",
)
@click.option("--force", is_flag=True, help="Force unmount even if busy")
def unmount_local(mount_point: Path, force: bool):
    """Unmount Azure Files SMB share from local macOS machine.

    Unmounts a previously mounted Azure Files share from your local machine.

    \b
    Examples:
      # Unmount default location
      $ azlin storage unmount local

      # Unmount specific location
      $ azlin storage unmount local --mount-point ~/mydata

      # Force unmount if busy
      $ azlin storage unmount local --force
    """
    console = Console()
    try:
        click.echo(f"Unmounting Azure Files share from: {mount_point}")

        # Check if mounted
        try:
            mount_info = LocalSMBMount.get_mount_info(mount_point)

            if not mount_info.is_mounted:
                click.echo(f"Mount point is not currently mounted: {mount_point}")
                return

        except Exception as e:
            click.echo(f"Warning: Could not check mount status: {e}")

        # Unmount
        try:
            result = LocalSMBMount.unmount(mount_point=mount_point, force=force)

            if result.success:
                if result.was_mounted:
                    click.echo(f"✓ Successfully unmounted from: {result.mount_point}")
                else:
                    click.echo(f"Mount point was not mounted: {result.mount_point}")
            else:
                click.echo("\nUnmount failed:", err=True)
                if result.errors:
                    for error in result.errors:
                        click.echo(f"  - {error}", err=True)
                click.echo("\nTip: Try --force to force unmount if the share is busy", err=True)
                sys.exit(1)

        except Exception as e:
            click.echo(f"Error unmounting share: {e}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


__all__ = ["storage_group"]
