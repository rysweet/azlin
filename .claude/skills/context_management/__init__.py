"""Context Management Skill - Proactive context window management.

This skill provides intelligent token monitoring, context extraction,
and selective rehydration for Claude Code sessions.
"""

from .context_extractor import ContextExtractor
from .context_rehydrator import ContextRehydrator
from .core import (
    check_status,
    context_management_skill,
    create_snapshot,
    list_snapshots,
    rehydrate_context,
)
from .models import ContextSnapshot, UsageStats
from .orchestrator import ContextManagementOrchestrator
from .token_monitor import TokenMonitor

__all__ = [
    "ContextExtractor",
    "ContextManagementOrchestrator",
    "ContextRehydrator",
    "ContextSnapshot",
    # Component bricks (for advanced usage)
    "TokenMonitor",
    # Data models
    "UsageStats",
    # Convenience functions
    "check_status",
    # Main skill entry point
    "context_management_skill",
    "create_snapshot",
    "list_snapshots",
    "rehydrate_context",
]

__version__ = "1.0.0"
