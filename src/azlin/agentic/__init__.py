"""Agentic mode for natural language command execution.

Phase 1: Core infrastructure with state persistence and audit logging.
Phase 2: Strategy selection and execution (Azure CLI, Terraform).
"""

from .audit_logger import AuditLogger
from .command_executor import CommandExecutionError, CommandExecutor, ResultValidator
from .error_analyzer import ErrorAnalyzer
from .execution_orchestrator import ExecutionOrchestrator, ExecutionOrchestratorError
from .fleet_query_parser import FleetQueryError, FleetQueryParser, ResultSynthesizer
from .intent_parser import CommandPlanner, IntentParseError, IntentParser
from .objective_manager import ObjectiveError, ObjectiveManager
from .request_clarifier import ClarificationResult, RequestClarificationError, RequestClarifier
from .session_context import CommandHistoryEntry, SessionContext
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
    "ClarificationResult",
    "CommandExecutionError",
    "CommandExecutor",
    "CommandHistoryEntry",
    "CommandPlanner",
    "CostEstimate",
    "ErrorAnalyzer",
    "ExecutionContext",
    "ExecutionOrchestrator",
    "ExecutionOrchestratorError",
    "ExecutionResult",
    "ExecutionStrategy",
    "FailureType",
    "FleetQueryError",
    "FleetQueryParser",
    "Intent",
    "IntentParseError",
    "IntentParser",
    "ObjectiveError",
    "ObjectiveManager",
    "ObjectiveState",
    "ObjectiveStatus",
    "RequestClarificationError",
    "RequestClarifier",
    "ResultSynthesizer",
    "ResultValidator",
    "SessionContext",
    "Strategy",
    "StrategyPlan",
    "StrategySelector",
    "TerraformStrategy",
]
