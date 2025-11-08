"""Main DoIt orchestrator - coordinates all components."""

from pathlib import Path

from azlin.doit.artifacts import ArtifactGenerator
from azlin.doit.engine import ExecutionEngine, ExecutionState
from azlin.doit.evaluator import GoalEvaluator
from azlin.doit.goals import GoalParser, ParsedRequest
from azlin.doit.reporter import ProgressReporter


class DoItOrchestrator:
    """Main orchestrator for azlin doit autonomous agent."""

    def __init__(
        self,
        output_dir: Path | None = None,
        prompts_dir: Path | None = None,
        max_iterations: int = 50,
        dry_run: bool = False,
        verbose: bool = True,
    ):
        """Initialize orchestrator.

        Args:
            output_dir: Directory for generated artifacts
            prompts_dir: Directory containing prompts
            max_iterations: Maximum ReAct loop iterations
            dry_run: If True, don't actually execute commands
            verbose: If True, show detailed progress
        """
        if output_dir is None:
            output_dir = Path.home() / ".azlin" / "doit" / "output"
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent.parent / "prompts" / "doit"

        self.output_dir = output_dir
        self.prompts_dir = prompts_dir
        self.max_iterations = max_iterations
        self.dry_run = dry_run
        self.verbose = verbose

        # Initialize components
        self.parser = GoalParser(prompts_dir)
        self.engine = ExecutionEngine(prompts_dir, dry_run=dry_run)
        self.evaluator = GoalEvaluator(prompts_dir)
        self.reporter = ProgressReporter(prompts_dir, verbose=verbose)
        self.artifact_generator = ArtifactGenerator(output_dir)

    def execute(self, user_request: str) -> ExecutionState:
        """Execute user request end-to-end.

        This is the main entry point for the autonomous agent.

        Args:
            user_request: Natural language infrastructure request

        Returns:
            Final execution state with results
        """
        # Phase 1: Parse request into goals
        self.reporter.console.print("\n[bold cyan]Phase 1: Parsing Request[/bold cyan]")
        parsed = self.parser.parse(user_request)

        if not parsed.goal_hierarchy:
            self.reporter.report_error("Failed to parse request into goals")
            raise ValueError("Failed to parse request")

        hierarchy = parsed.goal_hierarchy

        # Report parsed goals
        self.reporter.report_start(user_request, hierarchy)

        # Phase 2: Execute goals using ReAct loop
        self.reporter.console.print("\n[bold cyan]Phase 2: Executing Deployment[/bold cyan]")
        state = self.engine.execute(hierarchy, max_iterations=self.max_iterations)

        # Report progress periodically during execution
        # (The engine will call reporter.report_progress internally)

        # Phase 3: Final evaluation
        self.reporter.console.print("\n[bold cyan]Phase 3: Evaluation[/bold cyan]")
        for goal in hierarchy.goals:
            action_results = state.get_action_results_for_goal(goal.id)
            if action_results:
                evaluation = self.evaluator.evaluate(goal, action_results)
                if evaluation.teaching_notes and self.verbose:
                    self.reporter.console.print(
                        f"[dim]{evaluation.teaching_notes}[/dim]"
                    )

        # Report completion
        self.reporter.report_completion(state, hierarchy)

        # Phase 4: Generate artifacts
        if not self.dry_run:
            self.reporter.console.print(
                "\n[bold cyan]Phase 4: Generating Artifacts[/bold cyan]"
            )
            artifacts = self.artifact_generator.generate_all(hierarchy, state)

            self.reporter.console.print("\n[bold green]Generated Files:[/bold green]")
            for artifact_type, path in artifacts.items():
                self.reporter.console.print(f"  [green]✓[/green] {path}")

            self.reporter.console.print(
                f"\n[bold]Output Directory:[/bold] {self.output_dir}"
            )

        return state

    def execute_with_monitoring(self, user_request: str) -> ExecutionState:
        """Execute with real-time monitoring.

        Similar to execute() but with more frequent progress updates.
        """
        # For now, delegate to regular execute
        # In the future, this could stream progress updates
        return self.execute(user_request)
