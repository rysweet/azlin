"""Natural Language Fleet Query command.

This module provides the 'azlin ask' command for querying the VM fleet using natural language.
"""

import logging
import sys
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from azlin.agentic.fleet_query_parser import (
    FleetQueryError,
    FleetQueryParser,
    ResultSynthesizer,
)
from azlin.batch_executor import BatchExecutor, BatchSelector
from azlin.click_group import AzlinGroup
from azlin.config_manager import ConfigError, ConfigManager
from azlin.cost_tracker import CostTracker
from azlin.vm_manager import VMManager, VMManagerError

logger = logging.getLogger(__name__)
console = Console()


@click.group(name="ask", cls=AzlinGroup)
def ask_group():
    """Natural language fleet queries.

    Ask questions about your VM fleet in plain English and get intelligent,
    aggregated answers with insights and recommendations.

    \b
    EXAMPLES:
        # Cost analysis
        $ azlin ask "which VMs are costing me the most this month?"

        # Resource usage
        $ azlin ask "show VMs using more than 80% disk space"

        # Version checks
        $ azlin ask "are any VMs running old Python versions?"

        # Idle detection
        $ azlin ask "show VMs not accessed in 2 weeks"

        # Package checks
        $ azlin ask "which VMs have Docker installed?"

        # Comparisons
        $ azlin ask "what's different between staging and prod VMs?"
    """
    pass


@ask_group.command(name="query")
@click.argument("query", type=str)
@click.option("--resource-group", "--rg", help="Azure resource group")
@click.option("--dry-run", is_flag=True, help="Show query plan without executing")
@click.option("--timeout", type=int, default=30, help="Command timeout in seconds (default: 30)")
@click.option(
    "--max-results", type=int, default=10, help="Maximum results to display (default: 10)"
)
def query_fleet(
    query: str,
    resource_group: str | None,
    dry_run: bool,
    timeout: int,
    max_results: int,
):
    """Execute natural language fleet query.

    Ask questions about your VM fleet in plain English. The system will:
    1. Parse your question into executable commands
    2. Run commands across your fleet
    3. Aggregate results and provide insights
    4. Suggest actionable improvements

    \b
    QUERY is your question in natural language.

    \b
    Examples:
        # Cost questions
        $ azlin ask query "which 5 VMs cost the most?"
        $ azlin ask query "show VMs costing more than $100/month"

        # Resource usage
        $ azlin ask query "VMs with high CPU usage"
        $ azlin ask query "which VMs are using >80% disk?"
        $ azlin ask query "show memory usage across all VMs"

        # Software versions
        $ azlin ask query "what Python versions are installed?"
        $ azlin ask query "VMs with Node.js < 18"
        $ azlin ask query "show outdated packages"

        # Idle detection
        $ azlin ask query "which VMs haven't been used in a week?"
        $ azlin ask query "show idle VMs"
        $ azlin ask query "VMs with no active users"

        # Package/software checks
        $ azlin ask query "which VMs have Docker installed?"
        $ azlin ask query "show VMs without Git"

        # Comparisons
        $ azlin ask query "compare staging vs production VMs"
        $ azlin ask query "what's different between web-1 and web-2?"
    """
    try:
        # Get config
        try:
            config = ConfigManager.load_config()
            if resource_group is None:
                resource_group = config.resource_group
        except ConfigError:
            if resource_group is None:
                console.print("[red]Error: No resource group configured[/red]")
                console.print("Run 'azlin config set-rg <name>' or use --resource-group")
                sys.exit(1)

        if resource_group is None:
            console.print("[red]Error: No resource group configured[/red]")
            sys.exit(1)

        console.print(f"[cyan]Analyzing query:[/cyan] {query}")

        # Parse query
        parser = FleetQueryParser()

        # Get context for query parsing
        vms = VMManager.list_vms(resource_group)
        context = {
            "vm_count": len(vms),
            "vms": [{"name": vm.name, "tags": vm.tags} for vm in vms[:5]],  # Sample
        }

        query_plan = parser.parse_query(query, context=context)

        # Display query plan
        if query_plan.get("confidence", 0.0) < 0.7:
            console.print(
                f"[yellow]Warning: Low confidence ({query_plan['confidence']:.0%}) "
                "in understanding query[/yellow]"
            )

        console.print(f"\n[cyan]Query Type:[/cyan] {query_plan['query_type']}")
        console.print(f"[cyan]Explanation:[/cyan] {query_plan.get('explanation', 'N/A')}")

        if dry_run:
            console.print("\n[yellow]DRY RUN - Query Plan:[/yellow]")
            console.print(f"Commands to execute: {len(query_plan['commands'])}")
            for i, cmd in enumerate(query_plan["commands"], 1):
                console.print(f"\n  {i}. {cmd.get('description', 'Command')}")
                console.print(f"     Target: {cmd.get('target', 'all')}")
                console.print(f"     Command: {cmd.get('remote_command', 'N/A')}")
            sys.exit(0)

        # Execute query
        console.print("\n[cyan]Executing query...[/cyan]")

        results = _execute_query_plan(query_plan, vms, resource_group, timeout, max_results, query)

        # Synthesize results
        console.print("\n[cyan]Analyzing results...[/cyan]")

        synthesizer = ResultSynthesizer()
        synthesis = synthesizer.synthesize(query, query_plan, results)

        # Display results
        _display_synthesis(synthesis, max_results)

        sys.exit(0)

    except (VMManagerError, FleetQueryError) as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error in fleet query")
        console.print(f"[red]Unexpected error: {e}[/red]")
        sys.exit(1)


def _execute_query_plan(
    query_plan: dict[str, Any],
    vms: list[Any],
    resource_group: str,
    timeout: int,
    max_results: int,
    original_query: str,
) -> list[dict[str, Any]]:
    """Execute the query plan and return results."""
    results = []

    # Check if we need cost data
    if query_plan.get("requires_cost_data", False):
        console.print("  [dim]Fetching cost data...[/dim]")
        try:
            cost_tracker = CostTracker()
            cost_summary = cost_tracker.estimate_costs(resource_group)

            for vm_cost in cost_summary.estimates:
                results.append(
                    {
                        "vm_name": vm_cost.vm_name,
                        "value": f"${vm_cost.estimated_cost:.2f}",
                        "metric": "cost",
                    }
                )
        except Exception as e:
            logger.warning(f"Failed to fetch cost data: {e}")
            console.print(f"  [yellow]Warning: Could not fetch cost data: {e}[/yellow]")

    # Execute commands on fleet
    executor = BatchExecutor(max_workers=10)

    for cmd_spec in query_plan["commands"]:
        remote_cmd = cmd_spec.get("remote_command")
        if not remote_cmd:
            continue

        target = cmd_spec.get("target", "all")

        # Filter VMs based on target
        if target == "all":
            target_vms = BatchSelector.select_running_only(vms)
        elif target.startswith("tag:"):
            tag_filter = target[4:]  # Remove "tag:" prefix
            target_vms = BatchSelector.select_by_tag(vms, tag_filter)
        elif target.startswith("pattern:"):
            pattern = target[8:]  # Remove "pattern:" prefix
            target_vms = BatchSelector.select_by_pattern(vms, pattern)
        else:
            target_vms = BatchSelector.select_running_only(vms)

        if not target_vms:
            console.print(f"  [yellow]No VMs match target: {target}[/yellow]")
            continue

        console.print(f"  [dim]Running on {len(target_vms)} VMs: {remote_cmd}[/dim]")

        # Execute command
        batch_results = executor.execute_command(
            vms=target_vms,
            command=remote_cmd,
            resource_group=resource_group,
            timeout=timeout,
        )

        # Aggregate results
        for batch_result in batch_results:
            if batch_result.success and batch_result.output:
                results.append(
                    {
                        "vm_name": batch_result.vm_name,
                        "value": batch_result.output.strip(),
                        "metric": query_plan.get("metric", "unknown"),
                        "command": remote_cmd,
                    }
                )

    return results


def _display_synthesis(synthesis: dict[str, Any], max_results: int) -> None:
    """Display synthesized results in a nice format."""
    # Summary
    console.print(
        Panel(
            synthesis.get("summary", "Query completed"),
            title="[bold cyan]Answer[/bold cyan]",
            border_style="cyan",
        )
    )

    # Results table
    results = synthesis.get("results", [])
    if results:
        table = Table(title="Results", show_header=True, header_style="bold magenta")
        table.add_column("VM Name", style="cyan")
        table.add_column("Value", style="yellow")
        table.add_column("Status", style="green")

        for i, result in enumerate(results[:max_results]):
            status = result.get("status", "ok")
            status_color = {
                "ok": "[green]✓[/green]",
                "warning": "[yellow]⚠[/yellow]",
                "critical": "[red]✗[/red]",
            }.get(status, "[white]•[/white]")

            table.add_row(
                result.get("vm_name", "N/A"),
                str(result.get("value", "N/A")),
                status_color,
            )

        if len(results) > max_results:
            table.add_row("...", f"({len(results) - max_results} more)", "")

        console.print(table)

    # Insights
    insights = synthesis.get("insights", [])
    if insights:
        console.print("\n[bold cyan]Insights:[/bold cyan]")
        for insight in insights:
            console.print(f"  • {insight}")

    # Recommendations
    recommendations = synthesis.get("recommendations", [])
    if recommendations:
        console.print("\n[bold green]Recommendations:[/bold green]")
        for rec in recommendations:
            console.print(f"  → {rec}")

    # Statistics
    total = synthesis.get("total_analyzed", 0)
    critical = synthesis.get("critical_count", 0)
    warning = synthesis.get("warning_count", 0)

    if total > 0:
        console.print(f"\n[dim]Analyzed {total} VMs")
        if critical > 0:
            console.print(f"  Critical: {critical}[/dim]")
        if warning > 0:
            console.print(f"  Warnings: {warning}[/dim]")


# Main command (shortcut)
@click.command(name="ask")
@click.argument("query", type=str, required=False)
@click.option("--resource-group", "--rg", help="Azure resource group")
@click.option("--dry-run", is_flag=True, help="Show query plan without executing")
@click.option("--timeout", type=int, default=30, help="Command timeout in seconds (default: 30)")
@click.option(
    "--max-results", type=int, default=10, help="Maximum results to display (default: 10)"
)
def ask_command(
    query: str | None,
    resource_group: str | None,
    dry_run: bool,
    timeout: int,
    max_results: int,
):
    """Ask questions about your VM fleet in natural language.

    This is a shortcut for 'azlin ask query <question>'.

    \b
    Examples:
        $ azlin ask "which VMs cost the most?"
        $ azlin ask "show VMs using >80% disk"
        $ azlin ask "VMs with old Python versions"
    """
    if query is None:
        console.print("[red]Error: QUERY is required[/red]")
        console.print("\nUsage: azlin ask <query>")
        console.print("\nExample: azlin ask 'which VMs cost the most?'")
        sys.exit(1)

    # Call the main query command
    ctx = click.get_current_context()
    ctx.invoke(
        query_fleet,
        query=query,
        resource_group=resource_group,
        dry_run=dry_run,
        timeout=timeout,
        max_results=max_results,
    )


__all__ = ["ask_command", "ask_group"]
