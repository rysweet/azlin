"""Autopilot: AI-powered cost optimization for Azure VMs.

This module provides automated VM lifecycle management based on:
- Learned usage patterns
- Budget constraints
- Cost optimization strategies

Philosophy:
- Transparent decision-making
- Safe defaults (never touch production)
- User control and confirmation
- Audit trail for all actions

Public API:
    AutoPilotConfig: Configuration management
    PatternLearner: Usage pattern analysis
    BudgetEnforcer: Budget enforcement and action execution
"""

from azlin.autopilot.config import AutoPilotConfig, AutoPilotConfigError, ConfigManager
from azlin.autopilot.enforcer import Action, ActionResult, BudgetEnforcer, BudgetStatus
from azlin.autopilot.learner import IdlePeriod, PatternLearner, UsagePattern, WorkHours

__all__ = [
    "Action",
    "ActionResult",
    "AutoPilotConfig",
    "AutoPilotConfigError",
    "BudgetEnforcer",
    "BudgetStatus",
    "ConfigManager",
    "IdlePeriod",
    "PatternLearner",
    "UsagePattern",
    "WorkHours",
]

__version__ = "1.0.0"
