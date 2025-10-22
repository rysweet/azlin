"""Reflection module for the amplihack framework."""

# Export main reflection functions
# NOTE: Only export functions that actually exist in reflection.py
from .lightweight_analyzer import LightweightAnalyzer
from .reflection import analyze_session_patterns, process_reflection_analysis

# Export interactive reflection system components
from .semaphore import LockData, ReflectionLock
from .state_machine import (
    ReflectionState,
    ReflectionStateData,
    ReflectionStateMachine,
)

__all__ = [
    "LightweightAnalyzer",
    "LockData",
    # Interactive reflection system
    "ReflectionLock",
    "ReflectionState",
    "ReflectionStateData",
    "ReflectionStateMachine",
    # Existing reflection functions
    "analyze_session_patterns",
    "process_reflection_analysis",
]
