"""Main execution engine - ReAct loop implementation."""

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

from azlin.doit.engine.models import (
    Action,
    ActionResult,
    ActionType,
    ExecutionPhase,
    ExecutionState,
    ReActStep,
)
from azlin.doit.goals import Goal, GoalHierarchy, GoalStatus


class ExecutionEngine:
    """Autonomous execution engine using ReAct pattern."""

    def __init__(
        self,
        prompts_dir: Path | None = None,
        enable_mcp: bool = True,
        dry_run: bool = False,
    ):
        """Initialize execution engine."""
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent.parent.parent / "prompts" / "doit"
        self.prompts_dir = prompts_dir
        self.enable_mcp = enable_mcp
        self.dry_run = dry_run
        self.state = ExecutionState()

        # Load prompts
        self.system_prompt = self._load_prompt("system_prompt.md")
        self.action_prompt = self._load_prompt("action_execution.md")
        self.strategy_prompt = self._load_prompt("strategy_selection.md")

    def _load_prompt(self, filename: str) -> str:
        """Load prompt file."""
        path = self.prompts_dir / filename
        if path.exists():
            return path.read_text()
        return ""

    def execute(self, hierarchy: GoalHierarchy, max_iterations: int = 50) -> ExecutionState:
        """Execute goal hierarchy using ReAct loop.

        ReAct Loop:
        1. Reason: What goal to work on? What action to take?
        2. Act: Execute the action
        3. Observe: Collect results
        4. Evaluate: Did it work? What's next?
        5. Adapt: If failed, adjust and retry

        Args:
            hierarchy: Goal hierarchy to execute
            max_iterations: Maximum iterations to prevent infinite loops

        Returns:
            Final execution state
        """
        self.state = ExecutionState(max_iterations=max_iterations)
        self.state.started_at = datetime.now()
        self.state.phase = ExecutionPhase.PLANNING

        iteration = 0
        while self.state.should_continue() and not hierarchy.is_complete():
            iteration += 1
            self.state.iteration = iteration

            # ReAct Step
            step = self._react_step(hierarchy, iteration)

            # If no action possible, wait or finish
            if step is None:
                if self._are_all_goals_final(hierarchy):
                    break
                # Some goals might be in progress, wait a bit
                time.sleep(1)
                continue

            # Execute and evaluate
            if step.result and not step.success and step.adaptation:
                # Failed, apply adaptation
                self._apply_adaptation(hierarchy, step)

            # Check if we're stuck
            if iteration > max_iterations:
                self.state.phase = ExecutionPhase.FAILED
                self.state.errors.append("Max iterations reached")
                break

        # Finalize
        self.state.completed_at = datetime.now()
        if hierarchy.is_complete():
            self.state.phase = ExecutionPhase.COMPLETED
        elif self.state.phase != ExecutionPhase.FAILED:
            self.state.phase = ExecutionPhase.FAILED

        return self.state

    def _react_step(self, hierarchy: GoalHierarchy, iteration: int) -> ReActStep | None:
        """Execute one ReAct step."""

        # 1. REASON: Select next goal to work on
        goal = self._select_next_goal(hierarchy)
        if goal is None:
            return None

        self.state.current_goal_id = goal.id
        self.state.phase = ExecutionPhase.EXECUTING

        # 2. PLAN: Decide what action to take
        action = self._plan_action(goal, hierarchy)

        # Create ReAct step
        step = ReActStep(
            iteration=iteration,
            goal_id=goal.id,
            thought=f"Working on {goal.type.value}: {goal.name}",
            plan=action.description,
            action=action,
        )

        # 3. ACT: Execute the action
        goal.mark_in_progress()
        result = self._execute_action(action)
        step.result = result
        self.state.add_action_result(result)

        # 4. OBSERVE & EVALUATE: Check result
        if result.success:
            # Success - mark goal completed
            goal.mark_completed(result.outputs)
            step.success = True
            step.evaluation = {
                "status": "completed",
                "resource_id": result.resource_id,
                "outputs": result.outputs,
            }
        else:
            # 5. ADAPT: Plan recovery
            if result.is_transient_error and goal.can_retry():
                # Transient error - will retry
                goal.status = GoalStatus.PENDING
                step.adaptation = "Retry after delay (transient error)"
                step.should_continue = True
            elif result.is_recoverable_error and goal.can_retry():
                # Recoverable - adjust parameters
                step.adaptation = self._plan_recovery(goal, result)
                goal.status = GoalStatus.PENDING
                step.should_continue = True
            else:
                # Unrecoverable or out of retries
                goal.mark_failed(result.error or "Unknown error")
                step.success = False
                step.should_continue = False
                step.evaluation = {
                    "status": "failed",
                    "error": result.error,
                    "recoverable": False,
                }

        return step

    def _select_next_goal(self, hierarchy: GoalHierarchy) -> Goal | None:
        """Select the next goal to work on."""
        # Get ready goals (dependencies met, not started or failed with retries)
        ready = hierarchy.get_ready_goals()

        if not ready:
            return None

        # Prioritize by level (lower first) and attempt count
        ready.sort(key=lambda g: (g.level, g.attempts))

        return ready[0]

    def _plan_action(self, goal: Goal, hierarchy: GoalHierarchy) -> Action:
        """Plan what action to take for a goal.

        This is simplified. In production, would use LLM to select strategy
        and build command based on strategy_selection.md prompt.
        """
        from azlin.doit.strategies import get_strategy

        # Get appropriate strategy for goal type
        strategy = get_strategy(goal.type)

        # Build command
        command = strategy.build_command(goal, hierarchy)

        return Action(
            id=f"action-{goal.id}-{goal.attempts}",
            goal_id=goal.id,
            action_type=ActionType.AZ_CLI,  # Default to Azure CLI
            command=command,
            parameters=goal.parameters,
            description=f"Deploy {goal.type.value}: {goal.name}",
        )

    def _execute_action(self, action: Action) -> ActionResult:
        """Execute an action and return result."""
        started_at = datetime.now()

        if self.dry_run:
            # Dry run mode - simulate success
            return ActionResult(
                action_id=action.id,
                goal_id=action.goal_id,
                success=True,
                started_at=started_at,
                completed_at=datetime.now(),
                duration_seconds=0.1,
                tool_used="dry_run",
                command=action.command,
                stdout="[DRY RUN] Command would execute",
            )

        # Execute based on action type
        if action.action_type == ActionType.AZ_CLI:
            return self._execute_az_cli(action, started_at)
        if action.action_type == ActionType.MCP_CALL:
            return self._execute_mcp(action, started_at)
        # Not implemented yet
        return ActionResult(
            action_id=action.id,
            goal_id=action.goal_id,
            success=False,
            started_at=started_at,
            completed_at=datetime.now(),
            duration_seconds=0,
            tool_used=action.action_type.value,
            command=action.command,
            error=f"Action type {action.action_type} not implemented",
        )

    def _execute_az_cli(self, action: Action, started_at: datetime) -> ActionResult:
        """Execute Azure CLI command."""
        try:
            # Convert command string to list for shell=False security
            import shlex

            cmd_list = (
                shlex.split(action.command) if isinstance(action.command, str) else action.command
            )
            result = subprocess.run(
                cmd_list,
                shell=False,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            completed_at = datetime.now()
            duration = (completed_at - started_at).total_seconds()

            # Parse outputs if JSON
            outputs = {}
            resource_id = None

            if result.returncode == 0 and result.stdout:
                try:
                    data = json.loads(result.stdout)
                    if isinstance(data, dict):
                        outputs = data
                        resource_id = data.get("id")
                except json.JSONDecodeError:
                    pass

            return ActionResult(
                action_id=action.id,
                goal_id=action.goal_id,
                success=result.returncode == 0,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                tool_used="az_cli",
                command=action.command,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                resource_id=resource_id,
                outputs=outputs,
                error=result.stderr if result.returncode != 0 else None,
            )

        except subprocess.TimeoutExpired:
            return ActionResult(
                action_id=action.id,
                goal_id=action.goal_id,
                success=False,
                started_at=started_at,
                completed_at=datetime.now(),
                duration_seconds=300,
                tool_used="az_cli",
                command=action.command,
                error="Command timed out after 5 minutes",
            )
        except Exception as e:
            return ActionResult(
                action_id=action.id,
                goal_id=action.goal_id,
                success=False,
                started_at=started_at,
                completed_at=datetime.now(),
                duration_seconds=0,
                tool_used="az_cli",
                command=action.command,
                error=str(e),
            )

    def _execute_mcp(self, action: Action, started_at: datetime) -> ActionResult:
        """Execute MCP call.

        TODO: Implement MCP integration.
        """
        return ActionResult(
            action_id=action.id,
            goal_id=action.goal_id,
            success=False,
            started_at=started_at,
            completed_at=datetime.now(),
            duration_seconds=0,
            tool_used="mcp",
            command=action.command,
            error="MCP integration not yet implemented",
        )

    def _plan_recovery(self, goal: Goal, result: ActionResult) -> str:
        """Plan recovery strategy for failed action."""
        if not result.error:
            return "Retry with same parameters"

        error_lower = result.error.lower()

        # Name conflicts
        if "already exists" in error_lower or "name not available" in error_lower:
            # Try with numeric suffix
            import re

            name = goal.name
            match = re.search(r"(\d+)$", name)
            if match:
                num = int(match.group(1)) + 1
                new_name = re.sub(r"\d+$", str(num), name)
            else:
                new_name = f"{name}2"

            goal.name = new_name
            goal.parameters["name"] = new_name
            return f"Retry with adjusted name: {new_name}"

        # Region issues
        if "region" in error_lower or "location" in error_lower:
            # Try different region
            current_region = goal.parameters.get("location", "eastus")
            regions = ["eastus", "westus2", "centralus", "westeurope"]
            if current_region in regions:
                idx = regions.index(current_region)
                new_region = regions[(idx + 1) % len(regions)]
                goal.parameters["location"] = new_region
                return f"Retry in different region: {new_region}"

        return "Retry with same parameters after delay"

    def _apply_adaptation(self, hierarchy: GoalHierarchy, step: ReActStep) -> None:
        """Apply adaptation from failed step."""
        # Parameters already adjusted in _plan_recovery
        # Just need to ensure goal is reset for retry
        goal = hierarchy.get_goal(step.goal_id)
        if goal and goal.status != GoalStatus.FAILED:
            goal.status = GoalStatus.PENDING

    def _are_all_goals_final(self, hierarchy: GoalHierarchy) -> bool:
        """Check if all goals are in a final state."""
        return all(g.status in [GoalStatus.COMPLETED, GoalStatus.FAILED] for g in hierarchy.goals)
