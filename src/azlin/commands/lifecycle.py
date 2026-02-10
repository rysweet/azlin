"""VM lifecycle commands for azlin CLI.

This module provides commands for managing VM lifecycle operations:
- start: Start a stopped/deallocated VM
- stop: Stop/deallocate a running VM
- kill: Delete a VM and all associated resources
- destroy: Alias for kill with additional options
- killall: Delete all VMs in a resource group
- prune: Delete inactive VMs based on age and idle time
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from azlin.vm_lifecycle import DeletionSummary
    from azlin.vm_manager import VMInfo

import click

from azlin.auth_models import AuthConfig, AuthMethod
from azlin.config_manager import ConfigError, ConfigManager
from azlin.context_manager import ContextError, ContextManager
from azlin.modules.cleanup_orchestrator import CleanupOrchestrator
from azlin.modules.interaction_handler import CLIInteractionHandler
from azlin.prune import PruneManager
from azlin.modules.ssh_key_vault import KeyVaultError, create_key_vault_manager
from azlin.vm_lifecycle import DeletionSummary, VMLifecycleError, VMLifecycleManager
from azlin.vm_lifecycle_control import VMLifecycleControlError, VMLifecycleController
from azlin.vm_manager import VMInfo, VMManager, VMManagerError

logger = logging.getLogger(__name__)


# ============================================================================
# START COMMAND
# ============================================================================


@click.command()
@click.argument("vm_name", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def start(vm_name: str, resource_group: str | None, config: str | None):
    """Start a stopped or deallocated VM.

    \b
    Examples:
        azlin start my-vm
        azlin start my-vm --rg my-resource-group
    """
    try:
        # Resolve session name to VM name if applicable
        resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_name, config)
        if resolved_vm_name:
            vm_name = resolved_vm_name

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        click.echo(f"Starting VM '{vm_name}'...")

        result = VMLifecycleController.start_vm(vm_name=vm_name, resource_group=rg, no_wait=False)

        if result.success:
            click.echo(f"Success! {result.message}")
            if result.cost_impact:
                click.echo(f"Cost impact: {result.cost_impact}")
        else:
            click.echo(f"Error: {result.message}", err=True)
            sys.exit(1)

    except VMLifecycleControlError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# STOP COMMAND
# ============================================================================


@click.command()
@click.argument("vm_name", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option(
    "--no-deallocate", is_flag=True, help="Stop VM without deallocating (keeps billing active)"
)
def stop(vm_name: str, resource_group: str | None, config: str | None, no_deallocate: bool):
    """Stop or deallocate a VM.

    Stopping a VM with deallocate (default) fully releases compute resources
    and stops billing for the VM (storage charges still apply).

    \b
    Examples:
        azlin stop my-vm
        azlin stop my-vm --rg my-resource-group
        azlin stop my-vm --no-deallocate
    """
    # Invert the flag logic: CLI has --no-deallocate, but function expects deallocate
    deallocate = not no_deallocate

    try:
        # Resolve session name to VM name if applicable
        resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_name, config)
        if resolved_vm_name:
            vm_name = resolved_vm_name

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        click.echo(f"{'Deallocating' if deallocate else 'Stopping'} VM '{vm_name}'...")

        result = VMLifecycleController.stop_vm(
            vm_name=vm_name, resource_group=rg, deallocate=deallocate, no_wait=False
        )

        if result.success:
            click.echo(f"Success! {result.message}")
            if result.cost_impact:
                click.echo(f"Cost impact: {result.cost_impact}")
        else:
            click.echo(f"Error: {result.message}", err=True)
            sys.exit(1)

    except VMLifecycleControlError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# KILL COMMAND
# ============================================================================


@click.command()
@click.argument("vm_name", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def kill(vm_name: str, resource_group: str | None, config: str | None, force: bool):
    """Delete a VM and all associated resources.

    Deletes the VM, NICs, disks, and public IPs.

    \b
    Examples:
        azlin kill azlin-vm-12345
        azlin kill my-vm --rg my-resource-group
        azlin kill my-vm --force
    """
    try:
        # Resolve session name to VM name if applicable
        resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_name, config)
        if resolved_vm_name:
            vm_name = resolved_vm_name

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # Validate VM exists
        vm = VMManager.get_vm(vm_name, rg)

        if not vm:
            click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'.", err=True)
            sys.exit(1)

        # Show confirmation prompt unless --force
        if not force:
            click.echo("\nVM Details:")
            click.echo(f"  Name:           {vm.name}")
            click.echo(f"  Resource Group: {vm.resource_group}")
            click.echo(f"  Status:         {vm.get_status_display()}")
            click.echo(f"  IP:             {vm.public_ip or 'N/A'}")
            click.echo(f"  Size:           {vm.vm_size or 'N/A'}")
            click.echo("\nThis will delete the VM and all associated resources (NICs, disks, IPs).")
            click.echo("This action cannot be undone.\n")

            confirm = input("Are you sure you want to delete this VM? [y/N]: ").lower()
            if confirm not in ["y", "yes"]:
                click.echo("Cancelled.")
                return

        # Delete VM
        click.echo(f"\nDeleting VM '{vm_name}'...")

        result = VMLifecycleManager.delete_vm(
            vm_name=vm_name, resource_group=rg, force=True, no_wait=False
        )

        if result.success:
            click.echo(f"\nSuccess! {result.message}")
            if result.resources_deleted:
                click.echo("\nDeleted resources:")
                for resource in result.resources_deleted:
                    click.echo(f"  - {resource}")

            # Clean up SSH key from Key Vault
            _cleanup_key_from_vault(vm_name, config)

            # Clean up session name mapping
            try:
                if ConfigManager.delete_session_name(vm_name, config):
                    click.echo("\nRemoved session name mapping")
            except ConfigError:
                pass  # Config cleanup is non-critical
        else:
            click.echo(f"\nError: {result.message}", err=True)
            sys.exit(1)

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except VMLifecycleError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# DESTROY COMMAND (alias for kill with additional options)
# ============================================================================


@click.command(name="destroy")
@click.argument("vm_name", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be deleted without actually deleting"
)
@click.option(
    "--delete-rg", is_flag=True, help="Delete the entire resource group (use with caution)"
)
def destroy(
    vm_name: str,
    resource_group: str | None,
    config: str | None,
    force: bool,
    dry_run: bool,
    delete_rg: bool,
):
    """Destroy a VM and optionally the entire resource group.

    This is an alias for the 'kill' command with additional options.
    Deletes the VM, NICs, disks, and public IPs.

    \b
    Examples:
        azlin destroy azlin-vm-12345
        azlin destroy my-vm --dry-run
        azlin destroy my-vm --delete-rg --force
        azlin destroy my-vm --rg my-resource-group
    """
    try:
        # Resolve session name to VM name if applicable
        resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_name, config)
        if resolved_vm_name:
            vm_name = resolved_vm_name

        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        if delete_rg:
            _handle_delete_resource_group(rg, vm_name, force, dry_run)
            return

        if dry_run:
            _handle_vm_dry_run(vm_name, rg)
            return

        _execute_vm_deletion(vm_name, rg, force, config)

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except VMLifecycleError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# KILLALL COMMAND
# ============================================================================


@click.command()
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
@click.option("--prefix", default="azlin", help="Only delete VMs with this prefix")
def killall(resource_group: str | None, config: str | None, force: bool, prefix: str):
    """Delete all VMs in resource group.

    Deletes all VMs matching the prefix and their associated resources.

    \b
    Examples:
        azlin killall
        azlin killall --rg my-resource-group
        azlin killall --prefix test-vm
        azlin killall --force
    """
    try:
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        vms = VMManager.list_vms(rg, include_stopped=True)
        vms = VMManager.filter_by_prefix(vms, prefix)

        if not vms:
            click.echo(f"No VMs found with prefix '{prefix}' in resource group '{rg}'.")
            return

        if not force and not _confirm_killall(vms, rg):
            click.echo("Cancelled.")
            return

        click.echo(f"\nDeleting {len(vms)} VM(s) in parallel...")

        # Execute bulk deletion
        summary = VMLifecycleManager.delete_vms_bulk(
            vms=[vm.name for vm in vms], resource_group=rg, parallel=True
        )

        # Display results
        _display_killall_results(summary)

        # Exit with error code if any failed
        if summary.failed > 0:
            sys.exit(1)

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except VMLifecycleError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# PRUNE COMMAND
# ============================================================================


@click.command()
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option(
    "--age-days", default=1, type=click.IntRange(min=1), help="Age threshold in days (default: 1)"
)
@click.option(
    "--idle-days", default=1, type=click.IntRange(min=1), help="Idle threshold in days (default: 1)"
)
@click.option("--dry-run", is_flag=True, help="Preview without deleting")
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
@click.option("--include-running", is_flag=True, help="Include running VMs")
@click.option("--include-named", is_flag=True, help="Include named sessions")
def prune(
    resource_group: str | None,
    config: str | None,
    age_days: int,
    idle_days: int,
    dry_run: bool,
    force: bool,
    include_running: bool,
    include_named: bool,
):
    """Prune inactive VMs based on age and idle time.

    Identifies and optionally deletes VMs that are:
    - Older than --age-days (default: 1)
    - Idle for longer than --idle-days (default: 1)
    - Stopped/deallocated (unless --include-running)
    - Without named sessions (unless --include-named)

    \b
    Examples:
        azlin prune --dry-run                    # Preview what would be deleted
        azlin prune                              # Delete VMs idle for 1+ days (default)
        azlin prune --age-days 7 --idle-days 3   # Custom thresholds
        azlin prune --force                      # Skip confirmation
        azlin prune --include-running            # Include running VMs
    """
    try:
        # Ensure Azure CLI subscription matches current context
        try:
            ContextManager.ensure_subscription_active(config)
        except ContextError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            click.echo("Set default with: azlin config set default_resource_group <name>")
            click.echo("Or specify with --resource-group option.")
            sys.exit(1)

        # Get candidates (single API call)
        candidates, connection_data = PruneManager.get_candidates(
            resource_group=rg,
            age_days=age_days,
            idle_days=idle_days,
            include_running=include_running,
            include_named=include_named,
        )

        # If no candidates, exit early
        if not candidates:
            click.echo("No VMs eligible for pruning.")
            return

        # Display table
        table = PruneManager.format_prune_table(candidates, connection_data)
        click.echo("\n" + table + "\n")

        # In dry-run mode, just show what would be deleted
        if dry_run:
            click.echo(f"DRY RUN: {len(candidates)} VM(s) would be deleted.")
            click.echo("Run without --dry-run to actually delete these VMs.")
            return

        # If not force mode, ask for confirmation
        if not force:
            click.echo(f"This will delete {len(candidates)} VM(s) and their associated resources.")
            click.echo("This action cannot be undone.\n")

            if not click.confirm(
                f"Are you sure you want to delete {len(candidates)} VM(s)?", default=False
            ):
                click.echo("Cancelled.")
                return

        # Execute deletion
        click.echo(f"\nDeleting {len(candidates)} VM(s)...")
        result = PruneManager.execute_prune(candidates, rg)

        # Display deletion summary
        deleted = result["deleted"]
        failed = result["failed"]

        click.echo("\n" + "=" * 80)
        click.echo("Deletion Summary")
        click.echo("=" * 80)
        click.echo(f"Total VMs:     {len(candidates)}")
        click.echo(f"Succeeded:     {deleted}")
        click.echo(f"Failed:        {failed}")
        click.echo("=" * 80)

        # Show errors if any
        if result["errors"]:
            click.echo("\nErrors:")
            for error in result["errors"]:
                click.echo(f"  - {error}")

        # Exit with error code if any failed
        if failed > 0:
            sys.exit(1)

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _cleanup_key_from_vault(vm_name: str, config: str | None) -> None:
    """Delete SSH key from Azure Key Vault when VM is destroyed.

    Args:
        vm_name: VM name (used to lookup secret)
        config: Config file path

    Note:
        This function logs warnings but does not raise exceptions to avoid
        blocking VM deletion if Key Vault cleanup fails.
    """
    try:
        # Load context to get key_vault_name
        context_config = ContextManager.load(config)
        current_context = context_config.get_current_context()

        if not current_context or not current_context.key_vault_name:
            logger.debug("No Key Vault configured, skipping cleanup")
            return

        logger.info(f"Cleaning up SSH key from Key Vault for VM: {vm_name}")

        # Build auth config from context
        # Note: Currently only supports Azure CLI authentication
        # Service Principal support would require storing credentials in context
        auth_config = AuthConfig(method=AuthMethod.AZURE_CLI)

        # Create Key Vault manager
        manager = create_key_vault_manager(
            vault_name=current_context.key_vault_name,
            subscription_id=current_context.subscription_id,
            tenant_id=current_context.tenant_id,
            auth_config=auth_config,
        )

        # Delete key
        deleted = manager.delete_key(vm_name)
        if deleted:
            click.echo(f"SSH key deleted from Key Vault: {current_context.key_vault_name}")
        else:
            logger.debug(f"SSH key not found in Key Vault for VM: {vm_name}")

    except KeyVaultError as e:
        logger.warning(f"Failed to delete SSH key from Key Vault: {e}")
        # Don't block VM deletion if Key Vault cleanup fails
    except Exception as e:
        logger.warning(f"Unexpected error during Key Vault cleanup: {e}")


def _handle_delete_resource_group(rg: str, vm_name: str, force: bool, dry_run: bool) -> None:
    """Handle resource group deletion."""
    if dry_run:
        click.echo(f"\n[DRY RUN] Would delete entire resource group: {rg}")
        click.echo(f"This would delete ALL resources in the group, not just '{vm_name}'")
        return

    if not force:
        click.echo(f"\nWARNING: You are about to delete the ENTIRE resource group: {rg}")
        click.echo(f"This will delete ALL resources in the group, not just the VM '{vm_name}'!")
        click.echo("\nThis action cannot be undone.\n")

        confirm = input("Type the resource group name to confirm deletion: ").strip()
        if confirm != rg:
            click.echo("Cancelled. Resource group name did not match.")
            return

    click.echo(f"\nDeleting resource group '{rg}'...")

    cmd = ["az", "group", "delete", "--name", rg, "--yes"]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=True)
        click.echo(f"\nSuccess! Resource group '{rg}' and all resources deleted.")
    except subprocess.CalledProcessError as e:
        click.echo(f"\nError deleting resource group: {e.stderr}", err=True)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        click.echo("\nError: Resource group deletion timed out.", err=True)
        sys.exit(1)


def _handle_vm_dry_run(vm_name: str, rg: str) -> None:
    """Handle dry-run mode for VM deletion."""
    vm = VMManager.get_vm(vm_name, rg)
    if not vm:
        click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'.", err=True)
        sys.exit(1)

    click.echo(f"\n[DRY RUN] Would delete VM: {vm_name}")
    click.echo(f"  Resource Group: {rg}")
    click.echo(f"  Status:         {vm.get_status_display()}")
    click.echo(f"  IP:             {vm.public_ip or 'N/A'}")
    click.echo(f"  Size:           {vm.vm_size or 'N/A'}")
    click.echo("\nResources that would be deleted:")
    click.echo(f"  - VM: {vm_name}")
    click.echo("  - Associated NICs")
    click.echo("  - Associated disks")
    click.echo("  - Associated public IPs")


def _confirm_vm_deletion(vm: VMInfo) -> bool:
    """Show VM details and get confirmation for deletion."""
    click.echo("\nVM Details:")
    click.echo(f"  Name:           {vm.name}")
    click.echo(f"  Resource Group: {vm.resource_group}")
    click.echo(f"  Status:         {vm.get_status_display()}")
    click.echo(f"  IP:             {vm.public_ip or 'N/A'}")
    click.echo(f"  Size:           {vm.vm_size or 'N/A'}")
    click.echo("\nThis will delete the VM and all associated resources (NICs, disks, IPs).")
    click.echo("This action cannot be undone.\n")

    confirm = input("Are you sure you want to delete this VM? [y/N]: ").lower()
    return confirm in ["y", "yes"]


def _execute_vm_deletion(vm_name: str, rg: str, force: bool, config: str | None = None) -> None:
    """Execute VM deletion and display results."""
    vm = VMManager.get_vm(vm_name, rg)

    if not vm:
        click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'.", err=True)
        sys.exit(1)

    if not force and not _confirm_vm_deletion(vm):
        click.echo("Cancelled.")
        return

    click.echo(f"\nDeleting VM '{vm_name}'...")

    result = VMLifecycleManager.delete_vm(
        vm_name=vm_name, resource_group=rg, force=True, no_wait=False
    )

    if result.success:
        click.echo(f"\nSuccess! {result.message}")
        if result.resources_deleted:
            click.echo("\nDeleted resources:")
            for resource in result.resources_deleted:
                click.echo(f"  - {resource}")

        # Clean up SSH key from Key Vault
        _cleanup_key_from_vault(vm_name, config)

        # Clean up session name mapping if it exists
        try:
            if ConfigManager.delete_session_name(vm_name, config):
                click.echo(f"Removed session name mapping for '{vm_name}'")
        except ConfigError:
            pass  # Config cleanup is non-critical

        # Check for orphaned Bastion after VM deletion
        try:
            cleanup_orch = CleanupOrchestrator(
                resource_group=rg, interaction_handler=CLIInteractionHandler()
            )

            orphaned = cleanup_orch.detect_orphaned_bastions()
            if orphaned:
                click.echo(f"\n🔍 Detected {len(orphaned)} orphaned Bastion host(s)")
                cleanup_results = cleanup_orch.cleanup_orphaned_bastions()

                for cleanup_result in cleanup_results:
                    if cleanup_result.was_successful():
                        click.echo(
                            click.style(
                                f"✓ Removed {cleanup_result.bastion_name} "
                                f"(saving ${cleanup_result.estimated_monthly_savings:.2f}/month)",
                                fg="green",
                            )
                        )
        except Exception as e:
            # Bastion cleanup is optional - don't fail the entire destroy
            logger.debug(f"Bastion cleanup check failed: {e}")

    else:
        click.echo(f"\nError: {result.message}", err=True)
        sys.exit(1)


def _confirm_killall(vms: list[Any], rg: str) -> bool:
    """Display VMs and get confirmation for bulk deletion."""
    click.echo(f"\nFound {len(vms)} VM(s) in resource group '{rg}':")
    click.echo("=" * 80)
    for vm in vms:
        status = vm.get_status_display()
        # Display IP with type indicator (Issue #492)
        ip = (
            f"{vm.public_ip} (Public)"
            if vm.public_ip
            else f"{vm.private_ip} (Private)"
            if vm.private_ip
            else "N/A"
        )
        click.echo(f"  {vm.name:<35} {status:<15} {ip:<15}")
    click.echo("=" * 80)

    click.echo(f"\nThis will delete all {len(vms)} VM(s) and their associated resources.")
    click.echo("This action cannot be undone.\n")

    confirm = input(f"Are you sure you want to delete {len(vms)} VM(s)? [y/N]: ").lower()
    return confirm in ["y", "yes"]


def _display_killall_results(summary: DeletionSummary) -> None:
    """Display killall operation results."""
    click.echo("\n" + "=" * 80)
    click.echo("Deletion Summary")
    click.echo("=" * 80)
    click.echo(f"Total VMs:     {summary.total}")
    click.echo(f"Succeeded:     {summary.succeeded}")
    click.echo(f"Failed:        {summary.failed}")
    click.echo("=" * 80)

    if summary.succeeded > 0:
        click.echo("\nSuccessfully deleted:")
        for result in summary.results:
            if result.success:
                click.echo(f"  - {result.vm_name}")

    if summary.failed > 0:
        click.echo("\nFailed to delete:")
        for result in summary.results:
            if not result.success:
                click.echo(f"  - {result.vm_name}: {result.message}")


__all__ = [
    "destroy",
    "kill",
    "killall",
    "prune",
    "start",
    "stop",
]
