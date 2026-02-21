"""
Azlin Data Models

Shared dataclasses and data structures to avoid circular dependencies.

Philosophy:
- Zero dependencies on other azlin modules
- Self-contained data definitions
- Shared types used across multiple modules
"""

from .session_models import TmuxSession

__all__ = ["TmuxSession"]
