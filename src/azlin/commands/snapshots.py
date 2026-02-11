"""VM snapshot management commands.

This module provides commands for creating, listing, restoring, deleting,
and scheduling VM snapshots.
"""

from __future__ import annotations

import sys

import click

from azlin.config_manager import AzlinConfig, ConfigError, ConfigManager
from azlin.modules.snapshot_manager import SnapshotError, SnapshotManager

__all__ = ["snapshot"]


@click.group(name="snapshot")
@click.pass_context
def snapshot(ctx: click.Context) -> None:
    """Manage VM snapshots and scheduled backups.

    Enable scheduled snapshots, sync snapshots manually, or manage snapshot schedules.

    \b
    EXAMPLES:
        # Enable scheduled snapshots (every 24 hours, keep 2)
        $ azlin snapshot enable my-vm --every 24

        # Enable with custom retention (every 12 hours, keep 5)
        $ azlin snapshot enable my-vm --every 12 --keep 5

        # Sync snapshots now (checks all VMs with schedules)
        $ azlin snapshot sync

        # Sync specific VM
        $ azlin snapshot sync --vm my-vm

        # Disable scheduled snapshots
        $ azlin snapshot disable my-vm

        # Show snapshot schedule
        $ azlin snapshot status my-vm
    """
    pass


@snapshot.command(name="enable")
@click.argument("vm_name", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option(
    "--every",
    "interval_hours",
    type=int,
    required=True,
    help="Snapshot interval in hours (e.g., 24 for daily)",
)
@click.option(
    "--keep", "keep_count", type=int, default=2, help="Number of snapshots to keep (default: 2)"
)
def snapshot_enable(
    vm_name: str,
    resource_group: str | None,
    config: str | None,
    interval_hours: int,
    keep_count: int,
):
    """Enable scheduled snapshots for a VM.

    Configures the VM to take snapshots every N hours, keeping only the most recent snapshots.
    Schedule is stored in VM tags and triggered by `azlin snapshot sync`.

    \b
    Examples:
        azlin snapshot enable my-vm --every 24          # Daily, keep 2
        azlin snapshot enable my-vm --every 12 --keep 5 # Every 12h, keep 5
    """
    try:
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        SnapshotManager.enable_snapshots(vm_name, rg, interval_hours, keep_count)

        click.echo(f"✓ Enabled scheduled snapshots for {vm_name}")
        click.echo(f"  Interval: every {interval_hours} hours")
        click.echo(f"  Retention: keep {keep_count} snapshots")
        click.echo("\nRun 'azlin snapshot sync' to trigger snapshot creation.")

    except SnapshotError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@snapshot.command(name="disable")
@click.argument("vm_name", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def snapshot_disable(vm_name: str, resource_group: str | None, config: str | None):
    """Disable scheduled snapshots for a VM.

    Removes the snapshot schedule from the VM. Existing snapshots are not deleted.

    \b
    Example:
        azlin snapshot disable my-vm
    """
    try:
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        SnapshotManager.disable_snapshots(vm_name, rg)

        click.echo(f"✓ Disabled scheduled snapshots for {vm_name}")
        click.echo("Existing snapshots were not deleted.")

    except SnapshotError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@snapshot.command(name="sync")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--vm", "vm_name", help="Sync specific VM only", type=str)
def snapshot_sync(resource_group: str | None, config: str | None, vm_name: str | None):
    """Sync snapshots for VMs with schedules.

    Checks all VMs (or specific VM) and creates snapshots if needed based on their schedules.
    Old snapshots beyond retention count are automatically deleted (FIFO).

    This is the main command to run periodically (e.g., via cron) to trigger snapshot creation.

    \b
    Examples:
        azlin snapshot sync                # Sync all VMs
        azlin snapshot sync --vm my-vm     # Sync specific VM
    """
    try:
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        click.echo("Syncing scheduled snapshots...")

        results = SnapshotManager.sync_snapshots(rg, vm_name)

        click.echo("\n✓ Sync complete:")
        click.echo(f"  VMs checked: {results['checked']}")
        click.echo(f"  Snapshots created: {results['created']}")
        click.echo(f"  Old snapshots cleaned: {results['cleaned']}")
        click.echo(f"  VMs skipped: {results['skipped']}")

    except SnapshotError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@snapshot.command(name="status")
@click.argument("vm_name", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def snapshot_status(vm_name: str, resource_group: str | None, config: str | None):
    """Show snapshot schedule status for a VM.

    \b
    Example:
        azlin snapshot status my-vm
    """
    try:
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        schedule = SnapshotManager.get_snapshot_schedule(vm_name, rg)

        if not schedule:
            click.echo(f"No snapshot schedule configured for {vm_name}")
            return

        click.echo(f"Snapshot schedule for {vm_name}:")
        click.echo(f"  Status: {'Enabled' if schedule.enabled else 'Disabled'}")
        click.echo(f"  Interval: every {schedule.interval_hours} hours")
        click.echo(f"  Retention: keep {schedule.keep_count} snapshots")

        if schedule.last_snapshot_time:
            click.echo(f"  Last snapshot: {schedule.last_snapshot_time.isoformat()}")
        else:
            click.echo("  Last snapshot: Never")

    except SnapshotError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@snapshot.command(name="create")
@click.argument("vm_name")
@click.option("--resource-group", "--rg", help="Resource group name", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def snapshot_create(vm_name: str, resource_group: str | None, config: str | None):
    """Create a snapshot of a VM's OS disk.

    Creates a point-in-time snapshot of the VM's OS disk for backup purposes.
    Snapshots are automatically named with timestamps.

    \b
    EXAMPLES:
        # Create snapshot using default resource group
        $ azlin snapshot create my-vm

        # Create snapshot with specific resource group
        $ azlin snapshot create my-vm --rg my-resource-group
    """
    try:
        # Load config for defaults
        try:
            azlin_config = ConfigManager.load_config(config)
        except ConfigError:
            azlin_config = AzlinConfig()

        # Get resource group
        rg = resource_group or azlin_config.default_resource_group
        if not rg:
            click.echo(
                "Error: No resource group specified. Use --rg or set default_resource_group in config.",
                err=True,
            )
            sys.exit(1)

        # Create snapshot
        click.echo(f"\nCreating snapshot for VM: {vm_name}")
        manager = SnapshotManager()
        snapshot = manager.create_snapshot(vm_name, rg)

        # Show cost estimate
        size_gb = snapshot.size_gb or 0
        monthly_cost = manager.get_snapshot_cost_estimate(size_gb, 30)
        click.echo("\n✓ Snapshot created successfully!")
        click.echo(f"  Name:     {snapshot.name}")
        click.echo(f"  Size:     {size_gb} GB")
        click.echo(f"  Created:  {snapshot.creation_time}")
        click.echo(f"\nEstimated storage cost: ${monthly_cost:.2f}/month")

    except SnapshotError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@snapshot.command(name="list")
@click.argument("vm_name")
@click.option("--resource-group", "--rg", help="Resource group name", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def snapshot_list(vm_name: str, resource_group: str | None, config: str | None):
    """List all snapshots for a VM.

    Shows all snapshots created for the specified VM, sorted by creation time.

    \b
    EXAMPLES:
        # List snapshots for a VM
        $ azlin snapshot list my-vm

        # List snapshots with specific resource group
        $ azlin snapshot list my-vm --rg my-resource-group
    """
    try:
        # Load config for defaults
        try:
            azlin_config = ConfigManager.load_config(config)
        except ConfigError:
            azlin_config = AzlinConfig()

        # Get resource group
        rg = resource_group or azlin_config.default_resource_group
        if not rg:
            click.echo(
                "Error: No resource group specified. Use --rg or set default_resource_group in config.",
                err=True,
            )
            sys.exit(1)

        # List snapshots
        manager = SnapshotManager()
        snapshots = manager.list_snapshots(vm_name, rg)

        if not snapshots:
            click.echo(f"\nNo snapshots found for VM: {vm_name}")
            return

        # Display snapshots table
        click.echo(f"\nSnapshots for VM: {vm_name}")
        click.echo("=" * 90)
        click.echo(f"{'NAME':<50} {'SIZE':<10} {'CREATED':<30}")
        click.echo("=" * 90)

        total_size = 0
        for snap in snapshots:
            created = str(snap.creation_time)[:19].replace("T", " ")
            size_gb = snap.size_gb or 0
            click.echo(f"{snap.name:<50} {size_gb:<10} {created:<30}")
            total_size += size_gb

        click.echo("=" * 90)
        click.echo(f"\nTotal: {len(snapshots)} snapshots ({total_size} GB)")

        # Show cost estimate
        monthly_cost = manager.get_snapshot_cost_estimate(total_size, 30)
        click.echo(f"Estimated total storage cost: ${monthly_cost:.2f}/month\n")

    except SnapshotError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@snapshot.command(name="restore")
@click.argument("vm_name")
@click.argument("snapshot_name")
@click.option("--resource-group", "--rg", help="Resource group name", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def snapshot_restore(
    vm_name: str, snapshot_name: str, resource_group: str | None, config: str | None, force: bool
):
    """Restore a VM from a snapshot.

    WARNING: This will stop the VM, delete the current OS disk, and replace it
    with a disk created from the snapshot. All data on the current disk will be lost.

    \b
    EXAMPLES:
        # Restore VM from a snapshot (with confirmation)
        $ azlin snapshot restore my-vm my-vm-snapshot-20251015-053000

        # Restore without confirmation
        $ azlin snapshot restore my-vm my-vm-snapshot-20251015-053000 --force
    """
    try:
        # Load config for defaults
        try:
            azlin_config = ConfigManager.load_config(config)
        except ConfigError:
            azlin_config = AzlinConfig()

        # Get resource group
        rg = resource_group or azlin_config.default_resource_group
        if not rg:
            click.echo(
                "Error: No resource group specified. Use --rg or set default_resource_group in config.",
                err=True,
            )
            sys.exit(1)

        # Confirm restoration
        if not force:
            click.echo(
                f"\nWARNING: This will restore VM '{vm_name}' from snapshot '{snapshot_name}'"
            )
            click.echo("This operation will:")
            click.echo("  1. Stop/deallocate the VM")
            click.echo("  2. Delete the current OS disk")
            click.echo("  3. Create a new disk from the snapshot")
            click.echo("  4. Attach the new disk to the VM")
            click.echo("  5. Start the VM")
            click.echo("\nAll current data on the VM disk will be lost!")
            click.echo("\nContinue? [y/N]: ", nl=False)
            response = input().lower()
            if response not in ["y", "yes"]:
                click.echo("Cancelled.")
                return

        # Restore snapshot
        click.echo(f"\nRestoring VM '{vm_name}' from snapshot '{snapshot_name}'...")
        click.echo("This may take several minutes...\n")

        manager = SnapshotManager()
        manager.restore_snapshot(vm_name, snapshot_name, rg)

        click.echo(f"\n✓ VM '{vm_name}' successfully restored from snapshot!")
        click.echo(f"  The VM is now running with the disk from: {snapshot_name}\n")

    except SnapshotError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@snapshot.command(name="delete")
@click.argument("snapshot_name")
@click.option("--resource-group", "--rg", help="Resource group name", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def snapshot_delete(
    snapshot_name: str, resource_group: str | None, config: str | None, force: bool
):
    """Delete a snapshot.

    Permanently deletes a snapshot to free up storage and reduce costs.

    \b
    EXAMPLES:
        # Delete a snapshot (with confirmation)
        $ azlin snapshot delete my-vm-snapshot-20251015-053000

        # Delete without confirmation
        $ azlin snapshot delete my-vm-snapshot-20251015-053000 --force
    """
    try:
        # Load config for defaults
        try:
            azlin_config = ConfigManager.load_config(config)
        except ConfigError:
            azlin_config = AzlinConfig()

        # Get resource group
        rg = resource_group or azlin_config.default_resource_group
        if not rg:
            click.echo(
                "Error: No resource group specified. Use --rg or set default_resource_group in config.",
                err=True,
            )
            sys.exit(1)

        # Confirm deletion
        if not force:
            click.echo(f"\nAre you sure you want to delete snapshot '{snapshot_name}'?")
            click.echo("This action cannot be undone!")
            click.echo("\nContinue? [y/N]: ", nl=False)
            response = input().lower()
            if response not in ["y", "yes"]:
                click.echo("Cancelled.")
                return

        # Delete snapshot
        manager = SnapshotManager()
        manager.delete_snapshot(snapshot_name, rg)

        click.echo(f"\n✓ Snapshot '{snapshot_name}' deleted successfully!\n")

    except SnapshotError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
