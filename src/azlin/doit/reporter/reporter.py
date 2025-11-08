"""Progress reporter - provides user-friendly updates."""

from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from azlin.doit.engine.models import ExecutionState
from azlin.doit.goals import GoalHierarchy, GoalStatus


class ProgressReporter:
    """Reports progress during execution."""

    def __init__(self, prompts_dir: Path | None = None, verbose: bool = True):
        """Initialize reporter."""
        if prompts_dir is None:
            prompts_dir = (
                Path(__file__).parent.parent.parent / "prompts" / "doit"
            )
        self.prompts_dir = prompts_dir
        self.verbose = verbose
        self.console = Console()
        self.last_report_iteration = 0

    def report_start(self, user_request: str, hierarchy: GoalHierarchy) -> None:
        """Report start of execution."""
        self.console.print()
        self.console.print("[bold cyan]Azure Infrastructure Deployment[/bold cyan]")
        self.console.print("=" * 70)
        self.console.print()
        self.console.print(f"[bold]Request:[/bold] {user_request}")
        self.console.print()
        self.console.print(f"[bold]Parsed Goal:[/bold] {hierarchy.primary_goal}")
        self.console.print()

        # Show resource plan
        table = Table(title="Deployment Plan")
        table.add_column("Level", style="cyan")
        table.add_column("Resource Type", style="green")
        table.add_column("Name", style="yellow")

        for level in range(hierarchy.get_max_level() + 1):
            goals = hierarchy.get_goals_by_level(level)
            for goal in goals:
                table.add_row(
                    str(goal.level),
                    goal.type.value,
                    goal.name,
                )

        self.console.print(table)
        self.console.print()
        self.console.print(
            f"[bold]Total Resources:[/bold] {len(hierarchy.goals)}"
        )
        self.console.print(
            f"[bold]Estimated Time:[/bold] 5-10 minutes"
        )
        self.console.print()
        self.console.print("=" * 70)
        self.console.print()

    def report_progress(
        self, state: ExecutionState, hierarchy: GoalHierarchy
    ) -> None:
        """Report current progress."""
        # Only report every 2 iterations unless verbose
        if not self.verbose and state.iteration - self.last_report_iteration < 2:
            return

        self.last_report_iteration = state.iteration

        completed, total = hierarchy.get_progress()

        self.console.print()
        self.console.print("[bold]Progress Update[/bold]")
        self.console.print(f"Iteration: {state.iteration}/{state.max_iterations}")
        self.console.print(f"Completed: {completed}/{total}")
        self.console.print()

        # Show status of each goal
        for goal in hierarchy.goals:
            status_icon = self._get_status_icon(goal.status)
            status_color = self._get_status_color(goal.status)

            self.console.print(
                f"{status_icon} [{status_color}]{goal.name}[/{status_color}]"
            )

        elapsed = state.get_elapsed_time()
        self.console.print()
        self.console.print(f"[dim]Elapsed: {elapsed:.1f}s[/dim]")
        self.console.print()

    def report_goal_start(self, goal_name: str, goal_type: str) -> None:
        """Report start of goal execution."""
        if self.verbose:
            self.console.print(
                f"[cyan]→[/cyan] Starting: {goal_type} ({goal_name})"
            )

    def report_goal_complete(self, goal_name: str, duration: float) -> None:
        """Report goal completion."""
        if self.verbose:
            self.console.print(
                f"[green]✓[/green] Completed: {goal_name} ({duration:.1f}s)"
            )

    def report_goal_failed(self, goal_name: str, error: str) -> None:
        """Report goal failure."""
        self.console.print(f"[red]✗[/red] Failed: {goal_name}")
        if error:
            self.console.print(f"  [dim]Error: {error}[/dim]")

    def report_completion(
        self, state: ExecutionState, hierarchy: GoalHierarchy
    ) -> None:
        """Report final completion."""
        completed, total = hierarchy.get_progress()
        elapsed = state.get_elapsed_time()

        self.console.print()
        self.console.print("=" * 70)
        self.console.print("[bold green]Deployment Complete[/bold green]")
        self.console.print("=" * 70)
        self.console.print()

        # Summary table
        table = Table(title="Deployment Summary")
        table.add_column("Status", style="cyan")
        table.add_column("Count", style="yellow")

        status_counts = {}
        for goal in hierarchy.goals:
            status = goal.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        for status, count in status_counts.items():
            status_icon = self._get_status_icon(GoalStatus(status))
            table.add_row(f"{status_icon} {status.title()}", str(count))

        self.console.print(table)
        self.console.print()
        self.console.print(f"[bold]Total Time:[/bold] {elapsed:.1f}s ({elapsed/60:.1f}m)")
        self.console.print()

        # List completed resources
        if completed > 0:
            self.console.print("[bold]Deployed Resources:[/bold]")
            for goal in hierarchy.goals:
                if goal.status == GoalStatus.COMPLETED:
                    self.console.print(f"  [green]✓[/green] {goal.name}")
            self.console.print()

        # List failed resources
        failed = [g for g in hierarchy.goals if g.status == GoalStatus.FAILED]
        if failed:
            self.console.print("[bold red]Failed Resources:[/bold red]")
            for goal in failed:
                self.console.print(f"  [red]✗[/red] {goal.name}")
                if goal.error:
                    self.console.print(f"    [dim]{goal.error}[/dim]")
            self.console.print()

    def report_error(self, message: str) -> None:
        """Report an error."""
        self.console.print(f"[bold red]Error:[/bold red] {message}")

    def report_warning(self, message: str) -> None:
        """Report a warning."""
        self.console.print(f"[yellow]Warning:[/yellow] {message}")

    def report_iteration_summary(
        self, iteration: int, action_description: str, result: str
    ) -> None:
        """Report summary of an iteration."""
        if self.verbose:
            self.console.print()
            self.console.print(f"[bold]Iteration {iteration}[/bold]")
            self.console.print(f"  Action: {action_description}")
            self.console.print(f"  Result: {result}")

    def _get_status_icon(self, status: GoalStatus) -> str:
        """Get icon for status."""
        icons = {
            GoalStatus.PENDING: "□",
            GoalStatus.READY: "□",
            GoalStatus.IN_PROGRESS: "⟳",
            GoalStatus.COMPLETED: "✓",
            GoalStatus.FAILED: "✗",
            GoalStatus.BLOCKED: "⊗",
        }
        return icons.get(status, "?")

    def _get_status_color(self, status: GoalStatus) -> str:
        """Get color for status."""
        colors = {
            GoalStatus.PENDING: "dim",
            GoalStatus.READY: "cyan",
            GoalStatus.IN_PROGRESS: "yellow",
            GoalStatus.COMPLETED: "green",
            GoalStatus.FAILED: "red",
            GoalStatus.BLOCKED: "magenta",
        }
        return colors.get(status, "white")
