"""Cost optimization intelligence module.

Philosophy:
- Ruthless simplicity: Direct Azure API integration
- Zero-BS implementation: Working code only
- Brick & studs architecture: Self-contained modules

Public API exported from submodules.
"""

from azlin.costs.actions import (
    ActionExecutor,
    ActionResult,
    ActionStatus,
    AutomatedAction,
    ResourceDeleteAction,
    VMResizeAction,
    VMScheduleAction,
)
from azlin.costs.budget import (
    BudgetAlert,
    BudgetAlertManager,
    BudgetForecast,
    BudgetThreshold,
)
from azlin.costs.dashboard import (
    CostDashboard,
    CostDashboardCache,
    CostDashboardError,
    DashboardMetrics,
    ResourceCostBreakdown,
)
from azlin.costs.history import (
    CostHistory,
    CostHistoryEntry,
    CostTrend,
    TimeRange,
    TrendAnalyzer,
)
from azlin.costs.optimizer import (
    CostOptimizer,
    IdleResourceDetector,
    OptimizationRecommendation,
    OversizedVMDetector,
    RecommendationPriority,
    SchedulingOpportunity,
)

__all__ = [
    "ActionExecutor",
    "ActionResult",
    "ActionStatus",
    "AutomatedAction",
    "BudgetAlert",
    "BudgetAlertManager",
    "BudgetForecast",
    "BudgetThreshold",
    "CostDashboard",
    "CostDashboardCache",
    "CostDashboardError",
    "CostHistory",
    "CostHistoryEntry",
    "CostOptimizer",
    "CostTrend",
    "DashboardMetrics",
    "IdleResourceDetector",
    "OptimizationRecommendation",
    "OversizedVMDetector",
    "RecommendationPriority",
    "ResourceCostBreakdown",
    "ResourceDeleteAction",
    "SchedulingOpportunity",
    "TimeRange",
    "TrendAnalyzer",
    "VMResizeAction",
    "VMScheduleAction",
]
