"""W command for azlin monitoring.

This module contains the 'w' command (who's logged in) extracted from monitoring.py.
Part of Issue #423 - monitoring.py decomposition.

Command:
    - w: Run 'w' command on all VMs (who's logged in)
"""

from __future__ import annotations

import sys

import click

from azlin.config_manager import ConfigManager
from azlin.modules.ssh_keys import SSHKeyManager
from azlin.remote_exec import WCommandExecutor
from azlin.tag_manager import TagManager
from azlin.vm_manager import VMManagerError

__all__ = ["w"]


@click.command()
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def w(resource_group: str | None, config: str | None):
    """Run 'w' command on all VMs.

    Shows who is logged in and what they are doing on each VM.

    \b
    Examples:
        azlin w
        azlin w --rg my-resource-group
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
        # This ensures azlin w detects same VMs as azlin list, including custom-named VMs
        vms, _was_cached = TagManager.list_managed_vms(resource_group=rg, use_cache=False)
        vms = [vm for vm in vms if vm.is_running()]  # Filter to running VMs

        # Populate session names from tags (same logic as list command)
        for vm in vms:
            # Use tags already in memory instead of making N API calls
            if vm.tags and TagManager.TAG_SESSION in vm.tags:
                vm.session_name = vm.tags[TagManager.TAG_SESSION]
            else:
                # Fall back to config file
                vm.session_name = ConfigManager.get_session_name(vm.name, config)

        if not vms:
            click.echo("No running VMs found.")
            return

        # Get SSH configs with bastion support (Issue #281 fix)
        from azlin.cli_helpers import get_ssh_configs_for_vms

        ssh_configs, routes = get_ssh_configs_for_vms(
            vms=vms,
            ssh_key_path=ssh_key_pair.private_path,
            skip_interactive=True,  # Batch operation
            show_summary=True,
        )

        if not ssh_configs:
            click.echo("No reachable VMs found.")
            return

        click.echo(f"Running 'w' on {len(ssh_configs)} VMs...\n")

        # Execute in parallel (bastion tunnels cleaned up automatically via atexit)
        results = WCommandExecutor.execute_w_on_routes(routes, timeout=30)

        # Display output
        output = WCommandExecutor.format_w_output(results)
        click.echo(output)

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
