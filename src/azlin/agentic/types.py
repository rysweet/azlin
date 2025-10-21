"""Core types for azdoit multi-strategy execution framework.

This module defines all dataclasses and enums used throughout the azdoit system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class Strategy(str, Enum):
    """Available execution strategies."""

    AZURE_CLI = "azure_cli"
    TERRAFORM = "terraform"
    MCP_CLIENT = "mcp_client"
    CUSTOM_CODE = "custom_code"


class ObjectiveStatus(str, Enum):
    """Objective execution status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class FailureType(str, Enum):
    """Failure classification for recovery strategies."""

    RESOURCE_NOT_FOUND = "resource_not_found"
    QUOTA_EXCEEDED = "quota_exceeded"
    PERMISSION_DENIED = "permission_denied"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    VALIDATION_ERROR = "validation_error"
    DEPENDENCY_FAILED = "dependency_failed"
    UNKNOWN = "unknown"


@dataclass
class Intent:
    """Parsed intent from natural language.

    This is the output from IntentParser and input to StrategySelector.
    """

    intent: str
    parameters: dict[str, Any]
    confidence: float
    azlin_commands: list[dict[str, Any]]
    explanation: str | None = None

    def __post_init__(self):
        """Validate intent structure."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0.0-1.0, got {self.confidence}")
        if not isinstance(self.parameters, dict):
            raise ValueError("Parameters must be a dict")
        if not isinstance(self.azlin_commands, list):
            raise ValueError("azlin_commands must be a list")


@dataclass
class CostEstimate:
    """Azure cost estimate for execution."""

    total_monthly: Decimal
    total_hourly: Decimal
    breakdown: dict[str, Decimal] = field(default_factory=dict)
    confidence: str = "medium"  # low, medium, high

    def __post_init__(self):
        """Ensure Decimal types for costs."""
        if not isinstance(self.total_monthly, Decimal):
            self.total_monthly = Decimal(str(self.total_monthly))
        if not isinstance(self.total_hourly, Decimal):
            self.total_hourly = Decimal(str(self.total_hourly))
        # Convert breakdown values to Decimal
        self.breakdown = {k: Decimal(str(v)) if not isinstance(v, Decimal) else v
                          for k, v in self.breakdown.items()}


@dataclass
class StrategyPlan:
    """Execution strategy with fallback chain."""

    primary_strategy: Strategy
    fallback_strategies: list[Strategy] = field(default_factory=list)
    prerequisites_met: bool = True
    reasoning: str | None = None
    estimated_duration_seconds: int | None = None

    def all_strategies(self) -> list[Strategy]:
        """Get all strategies in order (primary + fallbacks)."""
        return [self.primary_strategy] + self.fallback_strategies


@dataclass
class ExecutionContext:
    """Context passed to strategy execution."""

    objective_id: str
    intent: Intent
    strategy: Strategy
    dry_run: bool = False
    resource_group: str | None = None
    retry_count: int = 0
    previous_failures: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "objective_id": self.objective_id,
            "intent": {
                "intent": self.intent.intent,
                "parameters": self.intent.parameters,
                "confidence": self.intent.confidence,
                "azlin_commands": self.intent.azlin_commands,
                "explanation": self.intent.explanation,
            },
            "strategy": self.strategy.value,
            "dry_run": self.dry_run,
            "resource_group": self.resource_group,
            "retry_count": self.retry_count,
            "previous_failures": self.previous_failures,
        }


@dataclass
class ExecutionResult:
    """Result from strategy execution."""

    success: bool
    strategy: Strategy
    output: str | None = None
    error: str | None = None
    failure_type: FailureType | None = None
    resources_created: list[str] = field(default_factory=list)
    duration_seconds: float | None = None
    cost_incurred: Decimal | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Ensure Decimal for cost."""
        if self.cost_incurred is not None and not isinstance(self.cost_incurred, Decimal):
            self.cost_incurred = Decimal(str(self.cost_incurred))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "strategy": self.strategy.value,
            "output": self.output,
            "error": self.error,
            "failure_type": self.failure_type.value if self.failure_type else None,
            "resources_created": self.resources_created,
            "duration_seconds": self.duration_seconds,
            "cost_incurred": str(self.cost_incurred) if self.cost_incurred else None,
            "metadata": self.metadata,
        }


@dataclass
class ObjectiveState:
    """Persistent state for an objective.

    This is stored at ~/.azlin/objectives/<uuid>.json
    """

    id: str
    natural_language: str
    intent: Intent
    status: ObjectiveStatus
    created_at: datetime
    updated_at: datetime
    selected_strategy: Strategy | None = None
    strategy_plan: StrategyPlan | None = None
    cost_estimate: CostEstimate | None = None
    execution_results: list[ExecutionResult] = field(default_factory=list)
    execution_history: list[dict[str, Any]] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    resources_created: list[str] = field(default_factory=list)
    error_message: str | None = None
    failure_type: FailureType | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary with all fields serialized for JSON storage
        """
        return {
            "id": self.id,
            "natural_language": self.natural_language,
            "intent": {
                "intent": self.intent.intent,
                "parameters": self.intent.parameters,
                "confidence": self.intent.confidence,
                "azlin_commands": self.intent.azlin_commands,
                "explanation": self.intent.explanation,
            },
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "selected_strategy": self.selected_strategy.value if self.selected_strategy else None,
            "strategy_plan": {
                "primary_strategy": self.strategy_plan.primary_strategy.value,
                "fallback_strategies": [s.value for s in self.strategy_plan.fallback_strategies],
                "prerequisites_met": self.strategy_plan.prerequisites_met,
                "reasoning": self.strategy_plan.reasoning,
                "estimated_duration_seconds": self.strategy_plan.estimated_duration_seconds,
            } if self.strategy_plan else None,
            "cost_estimate": {
                "total_monthly": str(self.cost_estimate.total_monthly),
                "total_hourly": str(self.cost_estimate.total_hourly),
                "breakdown": {k: str(v) for k, v in self.cost_estimate.breakdown.items()},
                "confidence": self.cost_estimate.confidence,
            } if self.cost_estimate else None,
            "execution_results": [r.to_dict() for r in self.execution_results],
            "execution_history": self.execution_history,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "resources_created": self.resources_created,
            "error_message": self.error_message,
            "failure_type": self.failure_type.value if self.failure_type else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ObjectiveState":
        """Create ObjectiveState from dictionary.

        Args:
            data: Dictionary with serialized state

        Returns:
            ObjectiveState instance
        """
        # Parse intent
        intent_data = data["intent"]
        intent = Intent(
            intent=intent_data["intent"],
            parameters=intent_data["parameters"],
            confidence=intent_data["confidence"],
            azlin_commands=intent_data["azlin_commands"],
            explanation=intent_data.get("explanation"),
        )

        # Parse strategy plan if present
        strategy_plan = None
        if data.get("strategy_plan"):
            sp_data = data["strategy_plan"]
            strategy_plan = StrategyPlan(
                primary_strategy=Strategy(sp_data["primary_strategy"]),
                fallback_strategies=[Strategy(s) for s in sp_data.get("fallback_strategies", [])],
                prerequisites_met=sp_data.get("prerequisites_met", True),
                reasoning=sp_data.get("reasoning"),
                estimated_duration_seconds=sp_data.get("estimated_duration_seconds"),
            )

        # Parse cost estimate if present
        cost_estimate = None
        if data.get("cost_estimate"):
            ce_data = data["cost_estimate"]
            cost_estimate = CostEstimate(
                total_monthly=Decimal(ce_data["total_monthly"]),
                total_hourly=Decimal(ce_data["total_hourly"]),
                breakdown={k: Decimal(v) for k, v in ce_data.get("breakdown", {}).items()},
                confidence=ce_data.get("confidence", "medium"),
            )

        # Parse execution results
        execution_results = []
        for er_data in data.get("execution_results", []):
            execution_results.append(ExecutionResult(
                success=er_data["success"],
                strategy=Strategy(er_data["strategy"]),
                output=er_data.get("output"),
                error=er_data.get("error"),
                failure_type=FailureType(er_data["failure_type"]) if er_data.get("failure_type") else None,
                resources_created=er_data.get("resources_created", []),
                duration_seconds=er_data.get("duration_seconds"),
                cost_incurred=Decimal(er_data["cost_incurred"]) if er_data.get("cost_incurred") else None,
                metadata=er_data.get("metadata", {}),
            ))

        return cls(
            id=data["id"],
            natural_language=data["natural_language"],
            intent=intent,
            status=ObjectiveStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            selected_strategy=Strategy(data["selected_strategy"]) if data.get("selected_strategy") else None,
            strategy_plan=strategy_plan,
            cost_estimate=cost_estimate,
            execution_results=execution_results,
            execution_history=data.get("execution_history", []),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            resources_created=data.get("resources_created", []),
            error_message=data.get("error_message"),
            failure_type=FailureType(data["failure_type"]) if data.get("failure_type") else None,
        )

    def validate_schema(self) -> bool:
        """Validate state object structure.

        Returns:
            True if valid

        Raises:
            ValueError: If validation fails
        """
        if not self.id:
            raise ValueError("id cannot be empty")
        if not self.natural_language:
            raise ValueError("natural_language cannot be empty")
        if not isinstance(self.intent, Intent):
            raise ValueError("intent must be Intent instance")
        if not isinstance(self.status, ObjectiveStatus):
            raise ValueError("status must be ObjectiveStatus")
        if self.retry_count < 0:
            raise ValueError("retry_count cannot be negative")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        return True
