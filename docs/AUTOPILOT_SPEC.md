# Cost-Aware Auto-Pilot Mode Specification

## Overview

AI-powered cost optimization that learns user patterns and automatically manages VM lifecycle to stay within budget.

## Explicit User Requirements (MUST PRESERVE)

1. AI-powered cost optimization using existing azlin do/doit AI
2. Learn user patterns (work hours, idle thresholds)
3. Auto stop/downsize based on budget
4. Transparent notifications before actions
5. Command: `azlin autopilot enable --budget 500 --strategy balanced`

## Architecture

### Component 1: AutoPilot Command Module (`commands/autopilot.py`)

**Responsibility**: CLI interface and configuration management

**Commands**:
```bash
azlin autopilot enable --budget 500 --strategy balanced
azlin autopilot disable
azlin autopilot status
azlin autopilot config --set key=value
```

**Configuration Storage**: `~/.azlin/autopilot.json`
```json
{
  "enabled": true,
  "budget_monthly": 500,
  "strategy": "balanced",
  "work_hours": {"start": 9, "end": 17, "days": ["mon", "tue", "wed", "thu", "fri"]},
  "idle_threshold_minutes": 120,
  "cpu_threshold_percent": 20,
  "cpu_observation_days": 3,
  "notifications": {"enabled": true, "channels": ["console"]},
  "protected_tags": ["production", "critical"],
  "last_run": "2025-11-16T14:00:00Z"
}
```

**Public API**:
```python
__all__ = ["autopilot_group", "AutoPilotConfig", "AutoPilotConfigError"]
```

**Lines of Code**: ~120

### Component 2: Pattern Learner (`autopilot/learner.py`)

**Responsibility**: Analyze VM usage patterns and learn work hours

**Core Functions**:
- `analyze_vm_history(resource_group: str) -> UsagePattern`
- `detect_work_hours(vm_history: List[VMEvent]) -> WorkHours`
- `calculate_idle_periods(vm_history: List[VMEvent]) -> List[IdlePeriod]`

**Data Models**:
```python
@dataclass
class UsagePattern:
    vm_name: str
    typical_work_hours: WorkHours
    average_idle_minutes: float
    last_active: datetime
    cpu_utilization_avg: float
    recommendations: List[str]

@dataclass
class WorkHours:
    start_hour: int  # 0-23
    end_hour: int    # 0-23
    days: List[str]  # ["mon", "tue", ...]
    confidence: float  # 0.0-1.0
```

**Pattern Learning Algorithm**:
1. Query Azure Activity Log for VM start/stop events (last 30 days)
2. Extract time patterns from events
3. Cluster active hours to detect work schedule
4. Calculate average idle time between uses
5. Query Azure Monitor for CPU metrics
6. Return recommendations based on patterns

**Public API**:
```python
__all__ = ["PatternLearner", "UsagePattern", "WorkHours", "IdlePeriod"]
```

**Lines of Code**: ~180

### Component 3: Budget Enforcer (`autopilot/enforcer.py`)

**Responsibility**: Execute actions based on budget and patterns

**Core Functions**:
- `check_budget(config: AutoPilotConfig) -> BudgetStatus`
- `recommend_actions(patterns: List[UsagePattern], budget_status: BudgetStatus) -> List[Action]`
- `execute_action(action: Action, dry_run: bool = False) -> ActionResult`

**Action Types**:
```python
@dataclass
class Action:
    action_type: str  # "stop", "downsize", "alert"
    vm_name: str
    reason: str
    estimated_savings_monthly: Decimal
    requires_confirmation: bool
    tags: Dict[str, str]

@dataclass
class BudgetStatus:
    current_monthly_cost: Decimal
    budget_monthly: Decimal
    projected_monthly_cost: Decimal
    overage: Decimal
    overage_percent: float
    needs_action: bool
```

**Enforcement Logic**:
1. Get current costs via `CostTracker`
2. Compare to budget threshold (90% warning, 100% action)
3. Generate recommendations from `PatternLearner`
4. Filter out protected VMs (tags)
5. Sort actions by highest savings
6. Notify user with action plan
7. Wait for confirmation (or auto-execute if configured)
8. Execute actions via `VMManager`
9. Log results

**Safety Checks**:
- Never touch VMs with protected tags
- Always notify before first action in session
- Respect work hours (don't stop during work time)
- Rate limit: max 5 actions per hour
- Log all actions for audit

**Public API**:
```python
__all__ = ["BudgetEnforcer", "Action", "BudgetStatus", "ActionResult"]
```

**Lines of Code**: ~150

## Integration with Existing Components

### Reuses:
- `CostTracker` - Calculate current and projected costs
- `VMManager` - Execute VM stop/start/resize
- `NotificationHandler` - Send notifications
- `BatchExecutor` - Multi-VM operations
- `ConfigManager` - Configuration patterns
- `TagManager` - Check protected tags

### New Files:
```
src/azlin/
├── commands/
│   └── autopilot.py              # 120 LOC
├── autopilot/
│   ├── __init__.py               # 20 LOC
│   ├── learner.py                # 180 LOC
│   ├── enforcer.py               # 150 LOC
│   └── models.py                 # 80 LOC (data classes)
└── tests/
    └── test_autopilot/
        ├── test_config.py        # 80 LOC
        ├── test_learner.py       # 120 LOC
        └── test_enforcer.py      # 150 LOC
```

**Total New Code**: ~900 LOC (450 implementation + 350 tests + 100 models)

## Data Flow

```
1. User enables autopilot with budget
   ↓
2. Config stored to ~/.azlin/autopilot.json
   ↓
3. PatternLearner analyzes historical VM usage
   - Azure Activity Logs (start/stop events)
   - Azure Monitor (CPU metrics)
   - Identifies work hours, idle patterns
   ↓
4. BudgetEnforcer monitors costs (hourly cron or on-demand)
   - Calls CostTracker.estimate_costs()
   - Compares to budget threshold
   ↓
5. When threshold exceeded:
   - Generate action recommendations
   - Filter out protected VMs
   - Send notification to user
   - Wait for confirmation (first time)
   ↓
6. Execute actions:
   - Stop idle VMs
   - Downsize underutilized VMs
   - Log all actions
   ↓
7. Report results:
   - Cost savings achieved
   - Actions taken
   - Next check time
```

## Security Considerations

### Input Validation:
- Budget must be positive number
- Strategy must be one of: conservative, balanced, aggressive
- Thresholds must be reasonable (e.g., idle > 30 minutes)

### Safe Defaults:
- Protected tags: ["production", "critical"]
- Minimum work hours detection confidence: 0.7
- Always notify before first action
- Never delete VMs, only stop/deallocate

### Audit Trail:
- Log all actions to `~/.azlin/autopilot_log.jsonl`
- Include: timestamp, action, vm_name, reason, result
- Retain logs for 90 days

### Rate Limiting:
- Max 5 actions per hour per resource group
- Prevents runaway automation

## Testing Strategy

### Unit Tests (60%):
- Config validation
- Pattern detection algorithms
- Budget calculations
- Action recommendation logic

### Integration Tests (30%):
- Config storage/retrieval
- CostTracker integration
- VMManager integration
- NotificationHandler integration

### E2E Tests (10%):
- Full autopilot enable/disable flow
- Mock Azure APIs
- Verify actions not executed without confirmation
- Verify protected VMs untouched

## Success Metrics

1. Command works: `azlin autopilot enable --budget 500 --strategy balanced`
2. Pattern learning accuracy: >70% confidence
3. Cost reduction: 40-60% (measured over 30 days)
4. False positive rate: <5% (user overrides logged)
5. Zero production VM impacts (protected tags respected)

## Implementation Timeline

### Phase 1: Core Infrastructure (Week 1)
- [ ] Create autopilot module structure
- [ ] Implement AutoPilotConfig with validation
- [ ] Write tests for config management
- [ ] Implement file-based storage

### Phase 2: Pattern Learning (Week 2)
- [ ] Implement PatternLearner.analyze_vm_history()
- [ ] Implement WorkHours detection
- [ ] Implement idle period calculation
- [ ] Write tests for pattern detection
- [ ] Mock Azure Activity Log queries

### Phase 3: Budget Enforcement (Week 3)
- [ ] Implement BudgetEnforcer.check_budget()
- [ ] Implement action recommendation
- [ ] Implement safe action execution
- [ ] Write tests for enforcement logic
- [ ] Integration with CostTracker

### Phase 4: CLI Commands (Week 3-4)
- [ ] Implement autopilot enable command
- [ ] Implement autopilot disable command
- [ ] Implement autopilot status command
- [ ] Implement autopilot config command
- [ ] Add rich console formatting

### Phase 5: Testing & Documentation (Week 4)
- [ ] E2E testing with mock Azure
- [ ] Local testing with real VMs
- [ ] Update README with autopilot docs
- [ ] Create examples and tutorials
- [ ] Performance testing

## Risk Mitigation

### Risk: Stopping production VMs
**Mitigation**:
- Protected tags (production, critical)
- Explicit opt-in via configuration
- Always notify before first action
- Dry-run mode for testing

### Risk: Pattern learning false positives
**Mitigation**:
- Minimum confidence threshold (0.7)
- Conservative defaults
- User can override detected patterns
- Manual work hours configuration

### Risk: Azure API rate limits
**Mitigation**:
- Use existing VMManager retry logic
- Batch operations when possible
- Exponential backoff

### Risk: Concurrent modifications
**Mitigation**:
- Check VM state before action
- Handle "already stopped" gracefully
- Log conflicts for review

## Future Enhancements (Out of Scope)

- Slack/Teams notification integration (v2)
- Machine learning for pattern prediction (v2)
- Multi-subscription support (v2)
- Cost forecasting dashboard (v3)
- Auto-scaling based on demand (v3)
