# azlin.costs - Cost Optimization Intelligence Module

**Module Version**: 1.0.0
**Philosophy**: Ruthless Simplicity, Brick & Studs Architecture, Zero-BS Implementation

## Module Contract (Public API)

This module provides cost optimization intelligence for Azure VMs.

### Public Interface (`__all__`)

```python
from azlin.costs import (
    # Core functionality
    CostDashboard,
    BudgetManager,
    RecommendationEngine,
    CostHistory,
    AutomationEngine,

    # Data models
    RealTimeCost,
    BudgetAlert,
    CostForecast,
    OptimizationRecommendation,
    CostTrend,

    # Exceptions
    CostAPIError,
    BudgetError,
    OptimizationError,
)
```

### Core Classes

#### CostDashboard

Real-time cost monitoring from Azure Cost Management API.

```python
dashboard = CostDashboard(resource_group="my-rg")

# Get current costs
costs = dashboard.get_current_costs()  # List[RealTimeCost]

# Get per-VM breakdown
vm_costs = dashboard.get_vm_costs()  # Dict[str, RealTimeCost]

# Refresh cache
dashboard.refresh()
```

**Performance**: < 2 seconds response time (5-minute cache)

#### BudgetManager

Budget tracking, alerts, and forecasting.

```python
budget = BudgetManager(resource_group="my-rg")

# Set budget
budget.set_budget(amount=500.00, thresholds=[80, 90, 100])

# Check status
status = budget.get_status()  # BudgetAlert

# Get forecast
forecast = budget.get_forecast()  # CostForecast

# Check if alerts triggered
alerts = budget.check_alerts()  # List[BudgetAlert]
```

**Forecast Accuracy**: Within 10% of actual costs

#### RecommendationEngine

AI-powered cost optimization recommendations.

```python
engine = RecommendationEngine(resource_group="my-rg")

# Get all recommendations
recommendations = engine.get_recommendations()  # List[OptimizationRecommendation]

# Filter by savings potential
high_savings = engine.get_recommendations(min_savings=50.00)

# Filter by confidence
confident = engine.get_recommendations(min_confidence=0.8)

# Refresh recommendations
engine.refresh()
```

**Recommendation Types**:
- `downsize` - Reduce VM size
- `schedule` - Schedule stop/start
- `cheaper_size` - Switch to cost-effective alternative
- `region_migration` - Move to cheaper region

#### CostHistory

Track and analyze spending patterns over time.

```python
history = CostHistory(resource_group="my-rg")

# Get history for period
trends = history.get_trends(days=30)  # List[CostTrend]

# Compare periods
comparison = history.compare_periods(
    period1_days=30,
    period2_days=60
)

# Export to CSV
history.export_csv("history.csv", days=90)

# Export to JSON
history.export_json("history.json", days=90)
```

**Data Retention**: 90 days

#### AutomationEngine

Automated cost optimization actions with approval workflows.

```python
automation = AutomationEngine(resource_group="my-rg")

# Enable automation
automation.enable(
    auto_shutdown=True,
    schedule_enforcement=True,
    budget_protection=True
)

# Configure rules
automation.configure(
    idle_threshold_hours=24,
    require_approval_for_downsize=True
)

# Get status
status = automation.get_status()

# Manually trigger optimization
results = automation.run()

# Disable automation
automation.disable()
```

### Data Models

#### RealTimeCost

```python
@dataclass
class RealTimeCost:
    vm_name: str
    resource_id: str
    current_cost: Decimal       # This billing cycle
    daily_cost: Decimal
    projected_monthly: Decimal
    last_updated: datetime
```

#### BudgetAlert

```python
@dataclass
class BudgetAlert:
    threshold_percent: int      # 80, 90, or 100
    budget_amount: Decimal
    current_spend: Decimal
    remaining_budget: Decimal
    triggered: bool
    severity: str               # "warning", "critical", "exceeded"
```

#### CostForecast

```python
@dataclass
class CostForecast:
    forecast_amount: Decimal
    confidence_interval: tuple[Decimal, Decimal]
    end_of_month_projection: Decimal
    accuracy_score: float       # 0.0 - 1.0
    based_on_days: int          # Historical data period
```

#### OptimizationRecommendation

```python
@dataclass
class OptimizationRecommendation:
    vm_name: str
    recommendation_type: str    # "downsize", "schedule", "cheaper_size"
    current_cost: Decimal
    projected_savings: Decimal
    confidence: float           # 0.0 - 1.0
    action_command: str         # CLI command to execute
    reason: str                 # Human-readable explanation
```

### Error Handling

```python
class CostAPIError(Exception):
    """Raised when Azure Cost Management API fails."""
    pass

class BudgetError(Exception):
    """Raised when budget operations fail."""
    pass

class OptimizationError(Exception):
    """Raised when optimization actions fail."""
    pass
```

## Module Philosophy

### Ruthless Simplicity

- **Start simple**: JSON file storage (migrate to SQLite only if needed)
- **Minimize abstractions**: Direct Azure SDK calls, no unnecessary wrappers
- **Clear data flow**: Request → API → Cache → Response

### Brick & Studs Architecture

- **Self-contained**: All cost logic in this module
- **Clear interface**: `__all__` defines public API
- **Testable**: Each class independently testable
- **Regeneratable**: Can rebuild from specification

### Zero-BS Implementation

- **No stubs**: Every function works or doesn't exist
- **No fake data**: Real Azure API integration
- **No placeholders**: Complete implementation
- **No TODOs in code**: Issues tracked externally

## Dependencies

**Azure SDK**:
- `azure-mgmt-costmanagement` - Cost Management API
- `azure-identity` - Authentication (shared with azlin)

**Standard Library Only** (where possible):
- `json` - Data persistence
- `dataclasses` - Data models
- `decimal` - Precise cost calculations
- `datetime` - Time handling

**Minimal External**:
- `click` - CLI integration (existing dependency)

## Data Storage

```
~/.azlin/costs/
├── history.json          # Cost history (30/60/90 days)
├── budgets.json          # Budget configurations
├── cache.json            # API response cache (5 min TTL)
└── recommendations.json  # Cached recommendations
```

**Format**: JSON (human-readable, easy debugging)
**Migration Path**: SQLite if files > 10MB or query performance issues

## Testing Strategy

Follow TDD pyramid:
- **60% Unit Tests**: Individual classes and methods
- **30% Integration Tests**: Azure API mocking
- **10% E2E Tests**: Full workflows with real credentials

```
tests/
├── test_cost_dashboard.py
├── test_budget_manager.py
├── test_recommendation_engine.py
├── test_cost_history.py
├── test_automation_engine.py
└── integration/
    ├── test_azure_api_integration.py
    └── test_full_workflow.py
```

## Performance Requirements

- **Dashboard load**: < 2 seconds (with cache)
- **API cache TTL**: 5 minutes
- **Forecast accuracy**: Within 10% of actual
- **Data retention**: 90 days
- **Cache invalidation**: Manual refresh option

## Security Considerations

- **No cost data logging**: Costs are sensitive
- **Use existing auth**: Same credentials as azlin
- **Local storage only**: No external transmission
- **File permissions**: 0600 on cost data files

## CLI Integration

Module integrates with azlin CLI:

```bash
azlin costs show           # CostDashboard.get_current_costs()
azlin costs budget set     # BudgetManager.set_budget()
azlin costs forecast       # BudgetManager.get_forecast()
azlin costs recommendations # RecommendationEngine.get_recommendations()
azlin costs history        # CostHistory.get_trends()
azlin costs optimize       # AutomationEngine.run()
```

## Extension Points

Future enhancements (not in initial implementation):

1. **SQLite migration**: If JSON files exceed 10MB
2. **Azure Advisor integration**: Pull recommendations from Azure Advisor API
3. **Multi-region support**: Track costs across regions
4. **Reserved instance analysis**: Identify RI opportunities
5. **Spot VM recommendations**: Suggest spot instances

## Module Maintainability

- **Single responsibility**: Cost optimization only
- **Clear boundaries**: No VM management (use vm_manager)
- **Documented decisions**: Why choices were made
- **Version compatibility**: Semantic versioning

## Related Modules

- `azlin.cost_tracker` - Original estimation-based tracking (kept for backward compatibility)
- `azlin.vm_manager` - VM operations (called by AutomationEngine)
- `azlin.config_manager` - Configuration (budget settings)

---

**Module Author**: azlin Development Team
**Created**: 2025-12-01
**Last Updated**: 2025-12-01
**License**: Same as azlin
