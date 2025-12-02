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
    # Dashboard
    "CostDashboard",
    "CostDashboardCache",
    "CostDashboardError",
    "DashboardMetrics",
    "ResourceCostBreakdown",
    # History
    "CostHistory",
    "CostHistoryEntry",
    "CostTrend",
    "TimeRange",
    "TrendAnalyzer",
    # Budget
    "BudgetAlert",
    "BudgetAlertManager",
    "BudgetForecast",
    "BudgetThreshold",
    # Actions
    "AutomatedAction",
    "ActionExecutor",
    "ActionResult",
    "ActionStatus",
    "VMResizeAction",
    "VMScheduleAction",
    "ResourceDeleteAction",
    # Optimizer
    "OptimizationRecommendation",
    "OversizedVMDetector",
    "IdleResourceDetector",
    "SchedulingOpportunity",
    "CostOptimizer",
    "RecommendationPriority",
]
