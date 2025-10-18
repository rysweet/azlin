"""Cost tracking command for azlin CLI.

This module provides the cost command for tracking VM costs.
"""

import sys
from datetime import datetime

import click

from azlin.config_manager import ConfigManager
from azlin.cost_tracker import CostTracker, CostTrackerError
from azlin.vm_manager import VMManagerError


def register_cost_command(main: click.Group) -> None:
    """Register cost command with main CLI group.

    Args:
        main: The main CLI group to register commands with
    """

    @main.command()
    @click.option("--resource-group", "--rg", help="Resource group", type=str)
    @click.option("--config", help="Config file path", type=click.Path())
    @click.option("--by-vm", is_flag=True, help="Show per-VM breakdown")
    @click.option("--from", "from_date", help="Start date (YYYY-MM-DD)", type=str)
    @click.option("--to", "to_date", help="End date (YYYY-MM-DD)", type=str)
    @click.option("--estimate", is_flag=True, help="Show monthly cost estimate")
    def cost(
        resource_group: str | None,
        config: str | None,
        by_vm: bool,
        from_date: str | None,
        to_date: str | None,
        estimate: bool,
    ):
        """Show cost estimates for VMs.

        Displays cost estimates based on VM size and uptime.
        Costs are approximate based on Azure pay-as-you-go pricing.

        \b
        Examples:
            azlin cost
            azlin cost --by-vm
            azlin cost --from 2025-01-01 --to 2025-01-31
            azlin cost --estimate
            azlin cost --rg my-resource-group --by-vm
        """
        try:
            # Get resource group
            rg = ConfigManager.get_resource_group(resource_group, config)

            if not rg:
                click.echo("Error: No resource group specified.", err=True)
                sys.exit(1)

            # Parse dates if provided
            start_date = None
            end_date = None

            if from_date:
                try:
                    start_date = datetime.strptime(from_date, "%Y-%m-%d")
                except ValueError:
                    click.echo("Error: Invalid from date format. Use YYYY-MM-DD", err=True)
                    sys.exit(1)

            if to_date:
                try:
                    end_date = datetime.strptime(to_date, "%Y-%m-%d")
                except ValueError:
                    click.echo("Error: Invalid to date format. Use YYYY-MM-DD", err=True)
                    sys.exit(1)

            # Get cost estimates
            click.echo(f"Calculating costs for resource group: {rg}\n")

            summary = CostTracker.estimate_costs(
                resource_group=rg, from_date=start_date, to_date=end_date, include_stopped=True
            )

            # Display formatted table
            output = CostTracker.format_cost_table(summary, by_vm=by_vm)
            click.echo(output)

            # Show estimate if requested
            if estimate and summary.running_vms > 0:
                monthly = summary.get_monthly_estimate()
                click.echo(f"Monthly estimate for running VMs: ${monthly:.2f}")
                click.echo("")

        except CostTrackerError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        except VMManagerError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"Unexpected error: {e}", err=True)
            sys.exit(1)
