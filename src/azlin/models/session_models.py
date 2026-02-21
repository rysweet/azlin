"""
Session Data Models

Shared dataclasses for session management to avoid circular dependencies.

Philosophy:
- Single responsibility: Session data structures only
- Zero dependencies: No imports from other azlin modules
- Regeneratable: Can be rebuilt from specification
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class TmuxSession:
    """Information about a tmux session.

    This dataclass is shared between session_manager and remote_exec
    to avoid circular import dependencies.

    Attributes:
        vm_name: Name of the VM where session runs
        session_name: Name of the tmux session
        windows: Number of windows in session
        created_time: ISO timestamp of session creation
        attached: Whether session is currently attached
    """

    vm_name: str
    session_name: str
    windows: int
    created_time: str
    attached: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for caching."""
        return {
            "vm_name": self.vm_name,
            "session_name": self.session_name,
            "windows": self.windows,
            "created_time": self.created_time,
            "attached": self.attached,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TmuxSession":
        """Create from cached dictionary."""
        return cls(
            vm_name=data["vm_name"],
            session_name=data["session_name"],
            windows=data["windows"],
            created_time=data["created_time"],
            attached=data.get("attached", False),
        )


__all__ = ["TmuxSession"]
