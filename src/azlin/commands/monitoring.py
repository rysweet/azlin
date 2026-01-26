"""Monitoring commands for azlin.

This module contains monitoring-related CLI commands extracted from cli.py.
Part of Issue #423 - cli.py decomposition.

Commands:
    - status: Show VM status information
"""

import sys

import click

from azlin.config_manager import ConfigManager
from azlin.context_manager import ContextError, ContextManager
from azlin.vm_manager import VMManager, VMManagerError


@click.command()
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--vm", help="Show status for specific VM only", type=str)
def status(resource_group: str | None, config: str | None, vm: str | None):
    """Show status of VMs in resource group.

    Displays detailed status information including power state and IP addresses.

    \b
    Examples:
        azlin status
        azlin status --rg my-resource-group
        azlin status --vm my-vm
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
            sys.exit(1)

        # List VMs - use TagManager to filter by managed-by=azlin tag
        from azlin.tag_manager import TagManager

        vms, was_cached = TagManager.list_managed_vms(resource_group=rg)

        # Filter out stopped VMs by default (consistent with list command behavior)
        # Note: list command doesn't filter by default but shows all,
        # keeping include_stopped=True behavior for status

        if vm:
            # Filter to specific VM
            vms = [v for v in vms if v.name == vm]
            if not vms:
                click.echo(f"Error: VM '{vm}' not found in resource group '{rg}'.", err=True)
                sys.exit(1)

        vms = VMManager.sort_by_created_time(vms)

        if not vms:
            click.echo("No VMs found.")
            return

        # Display status table
        click.echo(f"\nVM Status in resource group: {rg}")
        click.echo("=" * 100)
        click.echo(f"{'NAME':<35} {'POWER STATE':<18} {'IP':<16} {'REGION':<15} {'SIZE':<15}")
        click.echo("=" * 100)

        for v in vms:
            power_state = v.power_state if v.power_state else "Unknown"
            # Display IP with type indicator (Issue #492)
            ip = (
                f"{v.public_ip} (Public)"
                if v.public_ip
                else f"{v.private_ip} (Private)"
                if v.private_ip
                else "N/A"
            )
            size = v.vm_size or "N/A"
            location = v.location or "N/A"
            click.echo(f"{v.name:<35} {power_state:<18} {ip:<16} {location:<15} {size:<15}")

        click.echo("=" * 100)
        click.echo(f"\nTotal: {len(vms)} VMs")

        # Summary stats
        running = sum(1 for v in vms if v.is_running())
        stopped = len(vms) - running
        click.echo(f"Running: {running}, Stopped/Deallocated: {stopped}\n")

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)
