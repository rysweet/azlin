"""Multi-context display module for Rich table formatting.

This module provides formatted display of multi-context VM query results.
It uses Rich tables to display VMs grouped by context with summary statistics
and error handling.

Features:
- Grouped display: VMs organized by context
- Rich formatting: Color-coded status and tables
- Summary statistics: Per-context and total counts
- Error display: Clear error messages for failed contexts
- Cost information: Optional cost summaries

Architecture:
- MultiContextDisplay class for table rendering
- Reuses Rich console and table from cli.py patterns
- Integration with MultiContextVMResult from multi_context_list.py

Example Usage:
    >>> display = MultiContextDisplay()
    >>> display.display_results(result)
"""

import logging

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from azlin.multi_context_list import MultiContextVMResult
from azlin.quota_manager import QuotaManager

logger = logging.getLogger(__name__)


class MultiContextDisplayError(Exception):
    """Raised when display rendering fails."""

    pass


class MultiContextDisplay:
    """Display multi-context VM query results using Rich tables.

    This class provides formatted output for multi-context VM listings,
    with tables grouped by context and summary statistics.

    Philosophy:
    - Visual hierarchy: Clear grouping by context
    - Information density: Show relevant data without clutter
    - Error visibility: Make failures obvious but not disruptive
    - Consistent styling: Match existing azlin CLI aesthetics
    """

    def __init__(self, console: Console | None = None):
        """Initialize display formatter.

        Args:
            console: Optional Rich console (creates new one if None)
        """
        self.console = console or Console()

    def display_results(
        self,
        result: MultiContextVMResult,
        show_errors: bool = True,
        show_summary: bool = True,
    ) -> None:
        """Display multi-context VM query results.

        Args:
            result: Multi-context query results
            show_errors: Display error details for failed contexts
            show_summary: Display summary statistics

        Example:
            >>> display = MultiContextDisplay()
            >>> display.display_results(result)
        """
        # Display summary header
        if show_summary:
            self._display_summary_header(result)

        # Display VMs grouped by context
        for ctx_result in result.context_results:
            if ctx_result.success:
                self._display_context_vms(ctx_result)
            elif show_errors:
                self._display_context_error(ctx_result)

        # Display footer summary
        if show_summary:
            self._display_footer_summary(result)

    def _display_summary_header(self, result: MultiContextVMResult) -> None:
        """Display summary header with aggregate statistics.

        Args:
            result: Multi-context query results
        """
        # Create summary text
        summary_lines = [
            f"[bold]Multi-Context VM Query Results[/bold]",
            f"Contexts queried: {len(result.context_results)} "
            f"([green]{result.successful_contexts} succeeded[/green], "
            f"[red]{result.failed_contexts} failed[/red])",
            f"Total VMs: {result.total_vms} "
            f"([green]{result.total_running} running[/green], "
            f"[red]{result.total_stopped} stopped[/red])",
            f"Query duration: {result.total_duration:.2f}s",
        ]

        # Create panel with summary
        summary_text = "\n".join(summary_lines)
        panel = Panel(
            summary_text,
            title="Summary",
            border_style="cyan",
            padding=(1, 2),
        )

        self.console.print(panel)
        self.console.print()  # Spacing

    def _display_context_vms(self, ctx_result) -> None:
        """Display VMs for a single context.

        Args:
            ctx_result: ContextVMResult with VMs to display
        """
        # Create table title with context info
        title = (
            f"Context: [cyan]{ctx_result.context_name}[/cyan] "
            f"({ctx_result.vm_count} VMs, {ctx_result.duration:.2f}s)"
        )

        # Create table
        table = Table(
            title=title,
            show_header=True,
            header_style="bold",
            border_style="dim",
        )

        # Add columns (similar to existing list command)
        table.add_column("VM Name", style="white", width=30)
        table.add_column("Status", width=10)
        table.add_column("IP", style="yellow", width=15)
        table.add_column("Region", width=10)
        table.add_column("Size", width=15)
        table.add_column("vCPUs", justify="right", width=6)

        # Add VM rows
        if not ctx_result.vms:
            # Empty context
            table.add_row("[dim]No VMs found[/dim]", "", "", "", "", "")
        else:
            for vm in ctx_result.vms:
                status = vm.get_status_display()

                # Color code status
                if vm.is_running():
                    status_display = f"[green]{status}[/green]"
                elif vm.is_stopped():
                    status_display = f"[red]{status}[/red]"
                else:
                    status_display = f"[yellow]{status}[/yellow]"

                ip = vm.public_ip or "N/A"
                size = vm.vm_size or "N/A"

                # Get vCPU count
                vcpus = QuotaManager.get_vm_size_vcpus(size) if size != "N/A" else 0
                vcpu_display = str(vcpus) if vcpus > 0 else "-"

                table.add_row(
                    vm.name,
                    status_display,
                    ip,
                    vm.location,
                    size,
                    vcpu_display,
                )

        self.console.print(table)
        self.console.print()  # Spacing between contexts

    def _display_context_error(self, ctx_result) -> None:
        """Display error for a failed context.

        Args:
            ctx_result: ContextVMResult with error
        """
        error_text = (
            f"[bold red]Context: {ctx_result.context_name}[/bold red]\n"
            f"[red]Error:[/red] {ctx_result.error_message}\n"
            f"Duration: {ctx_result.duration:.2f}s"
        )

        panel = Panel(
            error_text,
            title="[red]Failed Context[/red]",
            border_style="red",
            padding=(1, 2),
        )

        self.console.print(panel)
        self.console.print()  # Spacing

    def _display_footer_summary(self, result: MultiContextVMResult) -> None:
        """Display footer summary with totals.

        Args:
            result: Multi-context query results
        """
        # Build summary table
        summary_table = Table(
            title="Summary Statistics",
            show_header=True,
            header_style="bold",
            border_style="cyan",
        )

        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", justify="right")

        # Add summary rows
        summary_table.add_row("Total Contexts", str(len(result.context_results)))
        summary_table.add_row(
            "Successful Queries",
            f"[green]{result.successful_contexts}[/green]",
        )
        summary_table.add_row(
            "Failed Queries",
            f"[red]{result.failed_contexts}[/red]" if result.failed_contexts > 0 else "0",
        )
        summary_table.add_row("Total VMs", str(result.total_vms))
        summary_table.add_row(
            "Running VMs",
            f"[green]{result.total_running}[/green]",
        )
        summary_table.add_row(
            "Stopped VMs",
            f"[red]{result.total_stopped}[/red]" if result.total_stopped > 0 else "0",
        )
        summary_table.add_row("Query Duration", f"{result.total_duration:.2f}s")

        self.console.print(summary_table)

    def display_cost_summary(self, result: MultiContextVMResult) -> None:
        """Display cost summary for multi-context results.

        Args:
            result: Multi-context query results with cost information

        Note:
            This is a placeholder for future cost tracking integration.
            Currently not implemented as it requires CostEstimator integration.
        """
        # TODO: Integrate with CostEstimator from modules/cost_estimator.py
        # This would calculate per-context and aggregate costs
        logger.debug("Cost summary not yet implemented")
        pass

    def display_error_summary(self, result: MultiContextVMResult) -> None:
        """Display summary of all errors encountered.

        Args:
            result: Multi-context query results
        """
        failures = result.get_failures()

        if not failures:
            self.console.print("[green]All contexts queried successfully![/green]")
            return

        # Create error summary table
        error_table = Table(
            title=f"[red]Failed Contexts ({len(failures)})[/red]",
            show_header=True,
            header_style="bold",
            border_style="red",
        )

        error_table.add_column("Context", style="cyan")
        error_table.add_column("Error", style="red")
        error_table.add_column("Duration", justify="right")

        for failure in failures:
            error_table.add_row(
                failure.context_name,
                failure.error_message or "Unknown error",
                f"{failure.duration:.2f}s",
            )

        self.console.print(error_table)

    def format_summary_line(self, result: MultiContextVMResult) -> str:
        """Format single-line summary for compact display.

        Args:
            result: Multi-context query results

        Returns:
            Formatted summary string

        Example:
            >>> summary = display.format_summary_line(result)
            >>> print(summary)
            "3 contexts: 15 VMs (12 running, 3 stopped), 2.5s"
        """
        return (
            f"{len(result.context_results)} contexts: "
            f"{result.total_vms} VMs "
            f"({result.total_running} running, {result.total_stopped} stopped), "
            f"{result.total_duration:.2f}s"
        )


__all__ = ["MultiContextDisplay", "MultiContextDisplayError"]
