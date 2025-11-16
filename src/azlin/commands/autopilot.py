"""Autopilot CLI commands.

This module provides the command-line interface for autopilot:
- Enable/disable autopilot
- Check status
- Configure settings
- Run manual check

Philosophy:
- Simple, clear commands
- Rich formatting for output
- Safe defaults
- User confirmation for destructive actions

Commands:
    azlin autopilot enable --budget 500 --strategy balanced
    azlin autopilot disable
    azlin autopilot status
    azlin autopilot config --set key=value
    azlin autopilot run --dry-run
"""

import sys
from datetime import datetime

import click
from rich.console import Console
from rich.table import Table

from azlin.autopilot import (
    AutoPilotConfig,
    AutoPilotConfigError,
    BudgetEnforcer,
    ConfigManager,
    PatternLearner,
)
from azlin.config_manager import ConfigManager as AzlinConfigManager

console = Console()


@click.group(name="autopilot")
def autopilot_group():
    """AI-powered cost optimization and VM lifecycle management.

    Autopilot learns your VM usage patterns and automatically manages
    VM lifecycle to stay within budget.

    Features:
    - Learns work hours and idle patterns
    - Auto-stops idle VMs
    - Downsizes underutilized VMs
    - Enforces budget constraints
    - Transparent notifications

    Example:
        azlin autopilot enable --budget 500 --strategy balanced
    """
    pass


@autopilot_group.command(name="enable")
@click.option(
    "--budget",
    "-b",
    type=int,
    required=True,
    help="Monthly budget in USD",
)
@click.option(
    "--strategy",
    "-s",
    type=click.Choice(["conservative", "balanced", "aggressive"], case_sensitive=False),
    default="balanced",
    help="Cost optimization strategy",
)
@click.option(
    "--idle-threshold",
    type=int,
    default=120,
    help="Minutes before VM considered idle (default: 120)",
)
@click.option(
    "--cpu-threshold",
    type=int,
    default=20,
    help="CPU utilization threshold for downsizing (default: 20%%)",
)
def enable_command(budget: int, strategy: str, idle_threshold: int, cpu_threshold: int):
    """Enable autopilot with specified budget and strategy.

    This will:
    1. Create autopilot configuration
    2. Analyze existing VM usage patterns
    3. Start monitoring costs against budget
    4. Send notifications before taking actions

    Example:
        azlin autopilot enable --budget 500 --strategy balanced
    """
    try:
        console.print("\n[bold cyan]Enabling Autopilot[/bold cyan]\n")

        # Create configuration
        config = AutoPilotConfig(
            enabled=True,
            budget_monthly=budget,
            strategy=strategy.lower(),
            idle_threshold_minutes=idle_threshold,
            cpu_threshold_percent=cpu_threshold,
        )

        # Save configuration
        ConfigManager.save_config(config)

        console.print("[green]✓[/green] Configuration saved")

        # Get resource group from azlin config
        try:
            azlin_config = AzlinConfigManager.load_config()
            resource_group = azlin_config.resource_group
        except Exception:
            console.print(
                "\n[yellow]Warning:[/yellow] Could not load azlin config. "
                "Run 'azlin config set resource-group <name>' first."
            )
            sys.exit(1)

        # Analyze current VMs
        console.print(f"\n[bold]Analyzing VMs in resource group:[/bold] {resource_group}")

        learner = PatternLearner()
        patterns = learner.analyze_resource_group(resource_group)

        if patterns:
            console.print(f"[green]✓[/green] Analyzed {len(patterns)} VMs")

            # Show summary table
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("VM Name")
            table.add_column("Avg Idle (min)")
            table.add_column("CPU Avg (%)")
            table.add_column("Recommendations")

            for pattern in patterns[:5]:  # Show first 5
                table.add_row(
                    pattern.vm_name,
                    f"{pattern.average_idle_minutes:.0f}",
                    f"{pattern.cpu_utilization_avg:.1f}",
                    str(len(pattern.recommendations)),
                )

            console.print("\n")
            console.print(table)

            if len(patterns) > 5:
                console.print(f"\n[dim]... and {len(patterns) - 5} more VMs[/dim]")

        else:
            console.print("[yellow]No VMs found to analyze[/yellow]")

        # Summary
        console.print("\n[bold green]Autopilot enabled successfully![/bold green]")
        console.print(f"\nBudget: [cyan]${budget}/month[/cyan]")
        console.print(f"Strategy: [cyan]{strategy}[/cyan]")
        console.print("\nAutopilot will:")
        console.print(f"  • Monitor costs against ${budget}/month budget")
        console.print(f"  • Stop VMs idle >{idle_threshold} minutes")
        console.print(f"  • Downsize VMs with <{cpu_threshold}% CPU")
        console.print("  • Notify you before taking actions")
        console.print("  • Never touch production-tagged VMs")
        console.print(f"\nConfiguration saved to: {ConfigManager.get_default_config_path()}")
        console.print("\nRun 'azlin autopilot status' to check current status.")
        console.print("Run 'azlin autopilot run --dry-run' to see what actions would be taken.\n")

    except AutoPilotConfigError as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}\n")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]Unexpected error:[/bold red] {e}\n")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@autopilot_group.command(name="disable")
@click.option(
    "--keep-config",
    is_flag=True,
    help="Keep configuration file (just disable autopilot)",
)
def disable_command(keep_config: bool):
    """Disable autopilot.

    This will stop all automated actions but optionally keep
    configuration for future use.

    Example:
        azlin autopilot disable
        azlin autopilot disable --keep-config
    """
    try:
        console.print("\n[bold cyan]Disabling Autopilot[/bold cyan]\n")

        if keep_config:
            # Just update enabled flag
            ConfigManager.update_config(None, {"enabled": False})
            console.print("[green]✓[/green] Autopilot disabled (configuration kept)")
        else:
            # Delete configuration
            ConfigManager.delete_config()
            console.print("[green]✓[/green] Autopilot disabled and configuration removed")

        console.print("\n[bold]Autopilot disabled[/bold]")
        console.print("Run 'azlin autopilot enable' to re-enable.\n")

    except AutoPilotConfigError as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}\n")
        sys.exit(1)


@autopilot_group.command(name="status")
def status_command():
    """Show autopilot status and budget information.

    Displays:
    - Current configuration
    - Budget status
    - Recent actions
    - Recommendations

    Example:
        azlin autopilot status
    """
    try:
        console.print("\n[bold cyan]Autopilot Status[/bold cyan]\n")

        # Load configuration
        try:
            config = ConfigManager.load_config()
        except AutoPilotConfigError:
            console.print("[yellow]Autopilot is not enabled[/yellow]")
            console.print("Run 'azlin autopilot enable --budget 500' to get started.\n")
            sys.exit(0)

        # Show configuration
        console.print("[bold]Configuration:[/bold]")
        console.print(
            "  Status: [green]Enabled[/green]"
            if config.enabled
            else "  Status: [red]Disabled[/red]"
        )
        console.print(f"  Budget: [cyan]${config.budget_monthly}/month[/cyan]")
        console.print(f"  Strategy: [cyan]{config.strategy}[/cyan]")
        console.print(f"  Idle threshold: {config.idle_threshold_minutes} minutes")
        console.print(f"  CPU threshold: {config.cpu_threshold_percent}%")

        if config.last_run:
            last_run = datetime.fromisoformat(config.last_run)
            console.print(f"  Last run: {last_run.strftime('%Y-%m-%d %H:%M:%S')}")

        # Get resource group
        try:
            azlin_config = AzlinConfigManager.load_config()
            resource_group = azlin_config.resource_group
        except Exception:
            console.print("\n[yellow]Warning:[/yellow] Could not load azlin config")
            sys.exit(1)

        # Check budget
        console.print(f"\n[bold]Budget Status:[/bold] {resource_group}")

        enforcer = BudgetEnforcer()
        budget_status = enforcer.check_budget(config, resource_group)

        console.print(
            f"  Current cost: [cyan]${budget_status.current_monthly_cost:.2f}/month[/cyan]"
        )
        console.print(f"  Budget limit: [cyan]${budget_status.budget_monthly:.2f}/month[/cyan]")

        if budget_status.overage > 0:
            console.print(
                f"  [bold red]Over budget by ${budget_status.overage:.2f} "
                f"({budget_status.overage_percent:.1f}%)[/bold red]"
            )
        else:
            remaining = budget_status.budget_monthly - budget_status.current_monthly_cost
            console.print(f"  [green]Within budget (${remaining:.2f} remaining)[/green]")

        if budget_status.needs_action:
            console.print("\n  [bold yellow]⚠ Action needed to stay within budget[/bold yellow]")
            console.print("  Run 'azlin autopilot run --dry-run' to see recommended actions")

        console.print(f"\nConfiguration file: {ConfigManager.get_default_config_path()}\n")

    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}\n")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@autopilot_group.command(name="config")
@click.option(
    "--set",
    "config_set",
    multiple=True,
    help="Set configuration value (key=value)",
)
@click.option(
    "--show",
    is_flag=True,
    help="Show full configuration",
)
def config_command(config_set: tuple[str, ...], show: bool):
    """Configure autopilot settings.

    Example:
        azlin autopilot config --set budget_monthly=1000
        azlin autopilot config --set strategy=aggressive
        azlin autopilot config --show
    """
    try:
        if show:
            # Show full configuration
            config = ConfigManager.load_config()
            console.print("\n[bold cyan]Autopilot Configuration[/bold cyan]\n")

            import json

            console.print(json.dumps(config.to_dict(), indent=2))
            console.print()

        elif config_set:
            # Update configuration
            updates = {}
            for setting in config_set:
                try:
                    key, value = setting.split("=", 1)
                    # Try to parse as int
                    try:
                        value = int(value)
                    except ValueError:
                        # Keep as string
                        pass
                    updates[key] = value
                except ValueError:
                    console.print(f"[red]Invalid setting format:[/red] {setting}")
                    console.print("Use: key=value")
                    sys.exit(1)

            ConfigManager.update_config(None, updates)
            console.print("\n[green]✓[/green] Configuration updated")

            for key, value in updates.items():
                console.print(f"  {key}: {value}")
            console.print()

        else:
            console.print("\n[yellow]Specify --set or --show[/yellow]\n")
            sys.exit(1)

    except AutoPilotConfigError as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}\n")
        sys.exit(1)


@autopilot_group.command(name="run")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without executing",
)
def run_command(dry_run: bool):
    """Run autopilot manually to check and execute actions.

    By default, shows recommendations without executing.
    Use without --dry-run to execute actions.

    Example:
        azlin autopilot run --dry-run
        azlin autopilot run
    """
    try:
        console.print("\n[bold cyan]Running Autopilot[/bold cyan]\n")

        # Load configuration
        config = ConfigManager.load_config()

        if not config.enabled:
            console.print("[yellow]Autopilot is disabled[/yellow]")
            console.print("Run 'azlin autopilot enable' first.\n")
            sys.exit(1)

        # Get resource group
        azlin_config = AzlinConfigManager.load_config()
        resource_group = azlin_config.resource_group

        # Check budget
        console.print(f"[bold]Checking budget:[/bold] {resource_group}\n")

        enforcer = BudgetEnforcer()
        budget_status = enforcer.check_budget(config, resource_group)

        console.print(f"Current cost: ${budget_status.current_monthly_cost:.2f}/month")
        console.print(f"Budget: ${budget_status.budget_monthly:.2f}/month")

        if not budget_status.needs_action:
            console.print("\n[green]✓ Within budget - no action needed[/green]\n")
            sys.exit(0)

        # Analyze patterns
        console.print("\n[bold]Analyzing VM patterns...[/bold]\n")

        learner = PatternLearner()
        patterns = learner.analyze_resource_group(resource_group)

        console.print(f"Analyzed {len(patterns)} VMs")

        # Get recommendations
        actions = enforcer.recommend_actions(patterns, budget_status, config)

        if not actions:
            console.print("\n[green]✓ No actions recommended[/green]\n")
            sys.exit(0)

        # Show recommendations
        console.print(f"\n[bold yellow]Recommended Actions:[/bold yellow] ({len(actions)})\n")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Action")
        table.add_column("VM Name")
        table.add_column("Reason")
        table.add_column("Savings/mo")

        for action in actions:
            table.add_row(
                action.action_type,
                action.vm_name,
                action.reason,
                f"${action.estimated_savings_monthly:.2f}",
            )

        console.print(table)

        # Execute if not dry-run
        if dry_run:
            console.print("\n[dim][DRY-RUN] No actions executed[/dim]\n")
        else:
            console.print("\n[bold red]Warning:[/bold red] This will execute actions!")
            response = click.prompt("\nContinue? [y/N]", default="n", type=str)

            if response.lower() in ["y", "yes"]:
                console.print("\n[bold]Executing actions...[/bold]\n")

                results = enforcer.execute_actions(
                    actions, resource_group, dry_run=False, require_confirmation=False
                )

                successful = sum(1 for r in results if r.success)
                console.print(
                    f"\n[bold]Results:[/bold] {successful}/{len(results)} actions successful\n"
                )

                for result in results:
                    status = "[green]✓[/green]" if result.success else "[red]✗[/red]"
                    console.print(f"  {status} {result.action.vm_name}: {result.message}")

                console.print()
            else:
                console.print("\n[yellow]Cancelled[/yellow]\n")

    except AutoPilotConfigError as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}\n")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}\n")
        import traceback

        traceback.print_exc()
        sys.exit(1)


__all__ = ["autopilot_group"]
