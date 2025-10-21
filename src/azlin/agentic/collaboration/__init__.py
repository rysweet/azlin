"""Team collaboration features for multi-user azlin operations.

Provides:
- Team management with user roles
- Distributed locking for concurrent operations
- User authentication across cloud providers
- Workspace isolation and resource management
"""

from .team_manager import Team, TeamManager, TeamRole
from .workspace import Workspace, WorkspaceManager

__all__ = [
    "Team",
    "TeamManager",
    "TeamRole",
    "Workspace",
    "WorkspaceManager",
]
