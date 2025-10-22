"""Agentic mode for natural language command execution.

Phase 1: Core infrastructure with state persistence and audit logging.
Phase 2: Strategy selection and execution (Azure CLI, Terraform).
"""

from .audit_logger import AuditLogger
from .command_executor import CommandExecutionError, CommandExecutor, ResultValidator
from .intent_parser import CommandPlanner, IntentParseError, IntentParser
from .objective_manager import ObjectiveError, ObjectiveManager
from .strategies import AzureCLIStrategy, ExecutionStrategy, TerraformStrategy
from .strategy_selector import StrategySelector
from .types import (
    CostEstimate,
    ExecutionContext,
    ExecutionResult,
    FailureType,
    Intent,
    ObjectiveState,
    ObjectiveStatus,
    Strategy,
    StrategyPlan,
)

__all__ = [
    # Core infrastructure (Phase 1)
    "AuditLogger",
    "AzureCLIStrategy",
    "CommandExecutionError",
    "CommandExecutor",
    "CommandPlanner",
    "CostEstimate",
    "ExecutionContext",
    "ExecutionResult",
    "ExecutionStrategy",
    "FailureType",
    "Intent",
    "IntentParseError",
    "IntentParser",
    "ObjectiveError",
    "ObjectiveManager",
    "ObjectiveState",
    "ObjectiveStatus",
    "ResultValidator",
    "Strategy",
    "StrategyPlan",
    "StrategySelector",
    "TerraformStrategy",
]
