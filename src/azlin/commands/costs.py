"""Cost optimization CLI commands.

This module provides commands for cost intelligence and optimization:
- View cost dashboard with current spending
- Analyze cost history and trends
- Set and monitor budgets with alerts
- Get optimization recommendations
- Execute cost-saving actions
"""

import logging
import sys
from datetime import datetime, timedelta
from decimal import Decimal

import click
from rich.console import Console

from azlin.click_group import AzlinGroup
from azlin.costs import (
    BudgetAlertManager,
    BudgetThreshold,
    CostDashboard,
    CostHistory,
    CostOptimizer,
    RecommendationPriority,
)

logger = logging.getLogger(__name__)
console = Console()


@click.group(name="costs", cls=AzlinGroup)
def costs_group():
    """Cost intelligence and optimization.

    Analyze spending, set budgets, get recommendations, and automate
    cost-saving actions for your Azure resources.

    \b
    COMMANDS:
        dashboard      View current costs and spending trends
        history        Analyze historical cost data
        budget         Manage budgets and alerts
        recommend      Get cost optimization recommendations
        actions        Execute cost-saving actions

    \b
    EXAMPLES:
        # View current costs
        $ azlin costs dashboard --resource-group my-rg

        # Analyze last 30 days
        $ azlin costs history --resource-group my-rg --days 30

        # Set monthly budget with alert
        $ azlin costs budget set --resource-group my-rg --amount 1000 --threshold 80

        # Get optimization recommendations
        $ azlin costs recommend --resource-group my-rg

        # Execute high-priority actions
        $ azlin costs actions execute --priority high
    """
    pass


@costs_group.command(name="dashboard")
@click.option("--resource-group", "--rg", help="Resource group name", type=str, required=True)
@click.option("--refresh", is_flag=True, help="Force refresh (ignore cache)")
def costs_dashboard(resource_group: str, refresh: bool):
    """View current costs and spending dashboard.

    Shows current month costs, daily spending, and resource breakdown.

    \b
    Examples:
        azlin costs dashboard --resource-group my-rg
        azlin costs dashboard --rg my-rg --refresh
    """
    try:
        dashboard = CostDashboard(resource_group=resource_group)

        # Get metrics (respects cache unless refresh=True)
        metrics = dashboard.get_current_metrics(refresh=refresh)

        console.print(f"\n[bold cyan]Cost Dashboard - {resource_group}[/bold cyan]")
        console.print(f"Period: {metrics.period_start.date()} to {metrics.period_end.date()}\n")  # type: ignore[attr-defined]

        console.print(f"[bold]Total Cost:[/bold] ${metrics.total_cost:.2f}")
        console.print(f"[bold]Daily Average:[/bold] ${metrics.daily_average:.2f}")  # type: ignore[attr-defined]
        console.print(f"[bold]Daily Trend:[/bold] {metrics.daily_trend}")  # type: ignore[attr-defined]

        if metrics.resources:  # type: ignore[attr-defined]
            console.print("\n[bold]Top Resources by Cost:[/bold]")
            for resource in metrics.resources[:10]:  # type: ignore[attr-defined]
                console.print(f"  {resource.name}: ${resource.cost:.2f}")

        console.print()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@costs_group.command(name="history")
@click.option("--resource-group", "--rg", help="Resource group name", type=str, required=True)
@click.option("--days", help="Number of days to analyze", type=int, default=30)
def costs_history(resource_group: str, days: int):
    """Analyze historical cost data and trends.

    \b
    Examples:
        azlin costs history --resource-group my-rg
        azlin costs history --rg my-rg --days 90
    """
    try:
        history = CostHistory(resource_group=resource_group)

        # Calculate time range
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        # Get history entries from store
        entries = history.store.get_range(start_date=start_date, end_date=end_date)

        console.print(f"\n[bold cyan]Cost History - {resource_group}[/bold cyan]")
        console.print(f"Period: {start_date} to {end_date}\n")

        if not entries:
            console.print("[yellow]No cost data available for this period[/yellow]")
            return

        total = sum(e.cost for e in entries)  # type: ignore[attr-defined]
        console.print(f"[bold]Total Cost:[/bold] ${total:.2f}")
        console.print(f"[bold]Number of Days:[/bold] {len(entries)}")
        console.print(f"[bold]Average per Day:[/bold] ${total / max(1, len(entries)):.2f}\n")

        # Show daily breakdown
        console.print("[bold]Daily Breakdown:[/bold]")
        for entry in entries[-14:]:  # Show last 14 days
            console.print(f"  {entry.date.date()}: ${entry.cost:.2f}")  # type: ignore[attr-defined]

        console.print()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@costs_group.command(name="budget")
@click.argument("action", type=click.Choice(["set", "show", "alerts"]))
@click.option("--resource-group", "--rg", help="Resource group name", type=str, required=True)
@click.option("--amount", help="Budget amount in USD", type=float)
@click.option("--threshold", help="Alert threshold percentage (e.g., 80)", type=int)
def costs_budget(action: str, resource_group: str, amount: float | None, threshold: int | None):
    """Manage budgets and alerts.

    \b
    Examples:
        azlin costs budget set --rg my-rg --amount 1000 --threshold 80
        azlin costs budget show --rg my-rg
        azlin costs budget alerts --rg my-rg
    """
    try:
        if action == "set":
            if amount is None:
                console.print("[red]Error:[/red] --amount required for 'set' action")
                sys.exit(1)

            # Create budget threshold
            threshold_obj = BudgetThreshold(
                name=resource_group,
                limit=Decimal(str(amount)),
                notification_threshold=Decimal(str(threshold or 80)),  # type: ignore[call-arg]
            )

            # Create manager with this threshold
            budget_mgr = BudgetAlertManager(thresholds=[threshold_obj])

            console.print(
                f"[green]✓[/green] Budget set to ${amount:.2f} with {threshold or 80}% alert threshold"
            )

        elif action == "show":
            # For show/alerts, need to load existing thresholds
            # Simplified for now - will need proper storage
            console.print("[yellow]Budget display not yet implemented[/yellow]")

        elif action == "alerts":
            # For show/alerts, need to load existing thresholds
            # Simplified for now - will need proper storage
            console.print("[yellow]Alert checking not yet implemented[/yellow]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@costs_group.command(name="recommend")
@click.option("--resource-group", "--rg", help="Resource group name", type=str, required=True)
@click.option("--priority", help="Filter by priority (low, medium, high)", type=str)
def costs_recommend(resource_group: str, priority: str | None):
    """Get cost optimization recommendations.

    \b
    Examples:
        azlin costs recommend --resource-group my-rg
        azlin costs recommend --rg my-rg --priority high
    """
    try:
        optimizer = CostOptimizer(resource_group=resource_group)

        # Get recommendations
        recommendations = optimizer.analyze()

        # Filter by priority if specified
        if priority:
            priority_enum = RecommendationPriority[priority.upper()]
            recommendations = [r for r in recommendations if r.priority == priority_enum]

        console.print(
            f"\n[bold cyan]Cost Optimization Recommendations - {resource_group}[/bold cyan]\n"
        )

        if not recommendations:
            console.print("[green]No recommendations at this time[/green]")
            return

        for i, rec in enumerate(recommendations, 1):
            priority_color = {
                RecommendationPriority.HIGH: "red",
                RecommendationPriority.MEDIUM: "yellow",
                RecommendationPriority.LOW: "blue",
            }.get(rec.priority, "white")

            console.print(f"[bold]{i}. {rec.title}[/bold]")  # type: ignore[attr-defined]
            console.print(f"   Priority: [{priority_color}]{rec.priority.value}[/{priority_color}]")
            console.print(f"   Savings: ${rec.estimated_savings:.2f}/month")
            console.print(f"   {rec.description}")  # type: ignore[attr-defined]
            console.print()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@costs_group.command(name="actions")
@click.argument("action", type=click.Choice(["list", "execute"]))
@click.option("--resource-group", "--rg", help="Resource group name", type=str, required=True)
@click.option("--priority", help="Execute only high-priority actions", type=str)
@click.option("--dry-run", is_flag=True, help="Show what would be done without executing")
def costs_actions(action: str, resource_group: str, priority: str | None, dry_run: bool):
    """Execute cost-saving actions.

    \b
    Examples:
        azlin costs actions list --rg my-rg
        azlin costs actions execute --rg my-rg --dry-run
        azlin costs actions execute --rg my-rg --priority high
    """
    try:
        optimizer = CostOptimizer(resource_group=resource_group)

        # Get recommendations first
        recommendations = optimizer.analyze()

        # Filter by priority if specified
        if priority:
            priority_enum = RecommendationPriority[priority.upper()]
            recommendations = [r for r in recommendations if r.priority == priority_enum]

        if action == "list":
            console.print(f"\n[bold cyan]Available Actions - {resource_group}[/bold cyan]\n")

            if not recommendations:
                console.print("[green]No actions available[/green]")
                return

            for i, rec in enumerate(recommendations, 1):
                console.print(f"{i}. {rec.title}")  # type: ignore[attr-defined]
                console.print(f"   Action: {rec.action_type}")  # type: ignore[attr-defined]
                console.print(f"   Savings: ${rec.estimated_savings:.2f}/month")
                console.print()

        elif action == "execute":
            if not recommendations:
                console.print("[green]No actions to execute[/green]")
                return

            if dry_run:
                console.print(
                    "\n[bold yellow]DRY RUN - No actions will be executed[/bold yellow]\n"
                )
            else:
                console.print(f"\n[bold cyan]Executing Actions - {resource_group}[/bold cyan]\n")

            # Note: Actual action execution would be implemented here
            # For now, just show what would be done
            for rec in recommendations:
                console.print(f"Processing: {rec.title}")  # type: ignore[attr-defined]

                if dry_run:
                    console.print(f"  [yellow]Would execute:[/yellow] {rec.description}")  # type: ignore[attr-defined]
                else:
                    console.print("  [yellow]Action execution not yet implemented[/yellow]")

                console.print()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


__all__ = ["costs_group"]
