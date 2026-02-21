"""PS command for azlin monitoring.

This module contains the 'ps' command (process listing) extracted from monitoring.py.
Part of Issue #423 - monitoring.py decomposition.

Command:
    - ps: Run 'ps aux' command on all VMs (process listing)
"""

from __future__ import annotations

import sys

import click

from azlin.config_manager import ConfigManager
from azlin.modules.ssh_keys import SSHKeyManager
from azlin.remote_exec import PSCommandExecutor
from azlin.tag_manager import TagManager
from azlin.vm_manager import VMManagerError

__all__ = ["ps"]


@click.command()
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--grouped", is_flag=True, help="Group output by VM instead of prefixing")
def ps(resource_group: str | None, config: str | None, grouped: bool):
    """Run 'ps aux' command on all VMs.

    Shows running processes on each VM. Output is prefixed with [vm-name].
    SSH processes are automatically filtered out.

    \b
    Examples:
        azlin ps
        azlin ps --rg my-resource-group
        azlin ps --grouped
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
        # This ensures azlin ps detects same VMs as azlin list, including custom-named VMs
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

        click.echo(f"Running 'ps aux' on {len(ssh_configs)} VMs...\n")

        # Execute in parallel (bastion tunnels cleaned up automatically via atexit)

        results = PSCommandExecutor.execute_ps_on_vms(ssh_configs, timeout=30)

        # Display output
        if grouped:
            output = PSCommandExecutor.format_ps_output_grouped(results, filter_ssh=True)
        else:
            output = PSCommandExecutor.format_ps_output(results, filter_ssh=True)

        click.echo(output)

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
