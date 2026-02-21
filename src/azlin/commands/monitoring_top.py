"""TOP command for azlin monitoring.

This module contains the 'top' command (distributed real-time monitoring) extracted from monitoring.py.
Part of Issue #423 - monitoring.py decomposition.

Command:
    - top: Distributed real-time monitoring dashboard
"""

from __future__ import annotations

import logging
import sys

import click

from azlin.config_manager import ConfigManager
from azlin.distributed_top import DistributedTopError, DistributedTopExecutor
from azlin.modules.ssh_keys import SSHKeyManager
from azlin.tag_manager import TagManager
from azlin.vm_manager import VMManagerError

logger = logging.getLogger(__name__)

__all__ = ["top"]


@click.command()
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option(
    "--interval",
    "-i",
    help="Refresh interval in seconds (default 10)",
    type=int,
    default=10,
)
@click.option(
    "--timeout",
    "-t",
    help="SSH timeout per VM in seconds (default 5)",
    type=int,
    default=5,
)
def top(
    resource_group: str | None,
    config: str | None,
    interval: int,
    timeout: int,
):
    """Run distributed top command on all VMs.

    Shows real-time CPU, memory, load, and top processes across all VMs
    in a unified dashboard that updates every N seconds.

    \b
    Examples:
        azlin top                    # Default: 10s refresh
        azlin top -i 5               # 5 second refresh
        azlin top --rg my-rg         # Specific resource group
        azlin top -i 15 -t 10        # 15s refresh, 10s timeout

    \b
    Press Ctrl+C to exit the dashboard.
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # Get SSH key
        ssh_key_pair = SSHKeyManager.ensure_key_exists()

        # List running VMs - use tag-based discovery (consistent with list command)
        # This ensures azlin top detects same VMs as azlin list, including custom-named VMs
        vms, _was_cached = TagManager.list_managed_vms(resource_group=rg, use_cache=False)
        vms = [vm for vm in vms if vm.is_running()]  # Filter to running VMs

        if not vms:
            click.echo("No running VMs found.")
            return

        # Get SSH configs with bastion support (Issue #281 fix)
        from azlin.cli_helpers import get_ssh_configs_for_vms

        ssh_configs, _routes = get_ssh_configs_for_vms(
            vms=vms,
            ssh_key_path=ssh_key_pair.private_path,
            skip_interactive=True,  # Batch operation
            show_summary=True,
        )

        if not ssh_configs:
            click.echo("No reachable VMs found.")
            return

        click.echo(
            f"Starting distributed top for {len(ssh_configs)} VMs "
            f"(refresh: {interval}s, timeout: {timeout}s)..."
        )
        click.echo("Press Ctrl+C to exit.\n")

        # Create and run executor (bastion tunnels cleaned up automatically via atexit)
        executor = DistributedTopExecutor(
            ssh_configs=ssh_configs,
            interval=interval,
            timeout=timeout,
        )
        executor.run_dashboard()

    except VMManagerError as e:
        # VMManagerError is already user-friendly
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except DistributedTopError as e:
        # DistributedTopError is already user-friendly
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nDashboard stopped by user.")
        sys.exit(0)
    except Exception as e:
        # Log detailed error for debugging, show generic error to user
        logger.debug(f"Unexpected error in distributed top: {e}", exc_info=True)
        click.echo("Error: An unexpected error occurred. Run with --verbose for details.", err=True)
        sys.exit(1)
