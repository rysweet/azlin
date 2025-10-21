"""Agentic mode for natural language command execution.

Phase 1: Core infrastructure with state persistence and audit logging.
"""

from .audit_logger import AuditLogger
from .command_executor import CommandExecutionError, CommandExecutor, ResultValidator
from .intent_parser import CommandPlanner, IntentParseError, IntentParser
from .objective_manager import ObjectiveError, ObjectiveManager
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
    # Core infrastructure
    "AuditLogger",
    "CommandExecutionError",
    "CommandExecutor",
    "CommandPlanner",
    "CostEstimate",
    "ExecutionContext",
    "ExecutionResult",
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
]
