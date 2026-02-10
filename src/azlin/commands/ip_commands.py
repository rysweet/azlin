"""IP diagnostics and network troubleshooting commands for azlin.

This module contains IP-related CLI commands extracted from cli.py.
Part of Issue #423 - cli.py decomposition.

Commands:
    - ip: Command group for IP diagnostics
    - ip check: Check IP address classification and connectivity for VM(s)
"""

import sys

import click

from azlin.config_manager import ConfigManager
from azlin.ip_diagnostics import (
    check_connectivity,
    classify_ip_address,
    format_diagnostic_report,
)
from azlin.vm_manager import VMManager, VMManagerError

__all__ = ["ip"]


@click.group()
def ip():
    """IP diagnostics and network troubleshooting commands.

    Commands to diagnose IP address classification and connectivity issues.

    \b
    Examples:
        azlin ip check my-vm
        azlin ip check --all
    """
    pass


@ip.command(name="check")
@click.argument("vm_identifier", required=False)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--all", "check_all", is_flag=True, help="Check all VMs in resource group")
@click.option("--port", help="Port to test connectivity (default: 22)", type=int, default=22)
def ip_check(
    vm_identifier: str | None,
    resource_group: str | None,
    config: str | None,
    check_all: bool,
    port: int,
):
    """Check IP address classification and connectivity for VM(s).

    Diagnoses IP classification (Public, Private, or Public-Azure) and tests
    connectivity. Particularly useful for identifying Azure's public IP range
    172.171.0.0/16 which appears private but is actually public.

    \b
    Examples:
        azlin ip check my-vm                  # Check specific VM
        azlin ip check --all                  # Check all VMs
        azlin ip check my-vm --port 80        # Check different port
        azlin ip check 172.171.118.91         # Check by IP address directly
    """
    try:
        # Validate arguments
        if not vm_identifier and not check_all:
            click.echo("Error: Either specify a VM name/IP or use --all flag", err=True)
            sys.exit(1)

        if vm_identifier and check_all:
            click.echo("Error: Cannot specify both VM name and --all flag", err=True)
            sys.exit(1)

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        # Check if vm_identifier is an IP address
        if vm_identifier and "." in vm_identifier:
            # Direct IP check
            click.echo(f"Running diagnostic for IP: {vm_identifier}\n")

            diagnostic_data = {
                "ip": vm_identifier,
                "classification": classify_ip_address(vm_identifier),
                "connectivity": check_connectivity(vm_identifier, port=port),
                "nsg_check": None,  # Can't check NSG without VM context
            }

            report = format_diagnostic_report(diagnostic_data)
            click.echo(report)
            return

        # Get VMs
        if check_all:
            if not rg:
                click.echo("Error: --all requires resource group to be specified", err=True)
                sys.exit(1)

            vms = VMManager.list_vms(rg, include_stopped=True)
            vms = VMManager.filter_by_prefix(vms, "azlin")

            if not vms:
                click.echo("No VMs found.")
                return
        else:
            # Single VM check
            if not rg:
                click.echo("Error: Resource group required. Set via --rg or config.", err=True)
                sys.exit(1)

            vm_name = vm_identifier
            vms = VMManager.list_vms(rg, include_stopped=True)
            vms = [v for v in vms if v.name == vm_name]

            if not vms:
                click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'.", err=True)
                sys.exit(1)

        # Run diagnostics on each VM
        for vm in vms:
            if not vm.public_ip:
                click.echo(f"\nVM: {vm.name}")
                click.echo("  Status: No public IP assigned (VM may be stopped)")
                continue

            click.echo(f"\nVM: {vm.name}")

            # Get NSG information if available
            # Note: NSG info would need to be extracted from VM details
            # For now, we'll skip NSG checking as it requires additional Azure API calls

            diagnostic_data = {
                "ip": vm.public_ip,
                "classification": classify_ip_address(vm.public_ip),
                "connectivity": check_connectivity(vm.public_ip, port=port),
                "nsg_check": None,  # Would require additional Azure NSG query
            }

            report = format_diagnostic_report(diagnostic_data)
            click.echo(report)

            if check_all:
                click.echo("\n" + "=" * 70 + "\n")

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
