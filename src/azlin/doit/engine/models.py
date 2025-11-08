"""Execution engine models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ActionType(Enum):
    """Types of actions the engine can take."""

    AZ_CLI = "az_cli"  # Azure CLI command
    MCP_CALL = "mcp_call"  # MCP tool call
    REST_API = "rest_api"  # Direct REST API call
    TERRAFORM = "terraform"  # Terraform operation
    BICEP = "bicep"  # Bicep operation
    VERIFICATION = "verification"  # Verify resource state


class ExecutionPhase(Enum):
    """Execution phases."""

    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    GENERATING = "generating"  # Generating artifacts
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Action:
    """Represents a single action to execute."""

    id: str
    goal_id: str
    action_type: ActionType
    command: str  # Command to execute
    parameters: dict[str, Any] = field(default_factory=dict)
    description: str = ""  # Human-readable description
    estimated_duration: int = 60  # Seconds


@dataclass
class ActionResult:
    """Result of executing an action."""

    action_id: str
    goal_id: str
    success: bool
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    tool_used: str  # az_cli, mcp, etc.
    command: str
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    resource_id: str | None = None
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    iac_fragments: dict[str, str] = field(default_factory=dict)  # terraform, bicep

    @property
    def is_transient_error(self) -> bool:
        """Check if error is transient (should retry)."""
        if not self.error:
            return False

        transient_patterns = [
            "timeout",
            "throttl",
            "temporarily unavailable",
            "connection reset",
            "service unavailable",
            "conflict",  # Provisioning conflict
        ]

        error_lower = self.error.lower()
        return any(pattern in error_lower for pattern in transient_patterns)

    @property
    def is_recoverable_error(self) -> bool:
        """Check if error is recoverable (can adjust and retry)."""
        if not self.error:
            return False

        recoverable_patterns = [
            "already exists",
            "name not available",
            "invalid",
            "not found",
            "bad request",
        ]

        error_lower = self.error.lower()
        return any(pattern in error_lower for pattern in recoverable_patterns)


@dataclass
class ExecutionState:
    """Current state of execution."""

    phase: ExecutionPhase = ExecutionPhase.PLANNING
    iteration: int = 0
    max_iterations: int = 50
    started_at: datetime | None = None
    completed_at: datetime | None = None
    current_goal_id: str | None = None
    actions_taken: list[ActionResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_action_result(self, result: ActionResult) -> None:
        """Add action result to history."""
        self.actions_taken.append(result)
        if not result.success and result.error:
            self.errors.append(result.error)

    def get_action_results_for_goal(self, goal_id: str) -> list[ActionResult]:
        """Get all action results for a specific goal."""
        return [r for r in self.actions_taken if r.goal_id == goal_id]

    def get_elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        if not self.started_at:
            return 0.0
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()

    def should_continue(self) -> bool:
        """Check if execution should continue."""
        if self.phase in [ExecutionPhase.COMPLETED, ExecutionPhase.FAILED]:
            return False
        if self.iteration >= self.max_iterations:
            return False
        return True


@dataclass
class ReActStep:
    """Single step in ReAct (Reason + Act) loop."""

    iteration: int
    goal_id: str

    # Reasoning
    thought: str  # What to do and why
    plan: str  # Specific plan for this step

    # Action
    action: Action

    # Observation
    result: ActionResult | None = None

    # Evaluation
    evaluation: dict[str, Any] = field(default_factory=dict)
    success: bool = False
    should_continue: bool = True
    adaptation: str | None = None  # If failed, what to try next
