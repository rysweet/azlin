"""Team collaboration and workspace management for multi-user azlin deployments.

Provides team-based collaboration with:
- Team creation and membership management
- Role-based access control (RBAC)
- Workspace isolation with per-team budgets
- Audit logging of team activities
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class Role(str, Enum):
    """User roles for RBAC."""

    OWNER = "owner"  # Full admin access
    ADMIN = "admin"  # Manage team and resources
    DEVELOPER = "developer"  # Create and manage resources
    VIEWER = "viewer"  # Read-only access


class Permission(str, Enum):
    """Granular permissions."""

    # Resource permissions
    CREATE_RESOURCE = "create_resource"
    DELETE_RESOURCE = "delete_resource"
    MODIFY_RESOURCE = "modify_resource"
    VIEW_RESOURCE = "view_resource"

    # Team permissions
    MANAGE_TEAM = "manage_team"
    INVITE_MEMBER = "invite_member"
    REMOVE_MEMBER = "remove_member"

    # Workspace permissions
    CREATE_WORKSPACE = "create_workspace"
    DELETE_WORKSPACE = "delete_workspace"
    MANAGE_BUDGET = "manage_budget"


# Role to permissions mapping
ROLE_PERMISSIONS: dict[Role, list[Permission]] = {
    Role.OWNER: list(Permission),  # All permissions
    Role.ADMIN: [
        Permission.CREATE_RESOURCE,
        Permission.DELETE_RESOURCE,
        Permission.MODIFY_RESOURCE,
        Permission.VIEW_RESOURCE,
        Permission.INVITE_MEMBER,
        Permission.CREATE_WORKSPACE,
        Permission.MANAGE_BUDGET,
    ],
    Role.DEVELOPER: [
        Permission.CREATE_RESOURCE,
        Permission.MODIFY_RESOURCE,
        Permission.VIEW_RESOURCE,
    ],
    Role.VIEWER: [
        Permission.VIEW_RESOURCE,
    ],
}


@dataclass
class TeamMember:
    """Team member with role."""

    user_id: str
    role: Role
    joined_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Workspace:
    """Isolated workspace with budget limits."""

    name: str
    team_id: str
    budget_usd: float  # Monthly budget in USD
    resources: list[str] = field(default_factory=list)  # Resource IDs
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Team:
    """Team with members and workspaces."""

    team_id: str
    name: str
    owner_id: str
    members: list[TeamMember] = field(default_factory=list)
    workspaces: dict[str, Workspace] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


class TeamManager:
    """Manages teams, members, and workspaces."""

    def __init__(self, data_dir: Path | None = None):
        """Initialize team manager.

        Args:
            data_dir: Directory for team data storage (default: ~/.azlin/teams)
        """
        self.data_dir = data_dir or Path.home() / ".azlin" / "teams"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def create_team(self, team_id: str, name: str, owner_id: str) -> Team:
        """Create a new team.

        Args:
            team_id: Unique team identifier
            name: Team name
            owner_id: User ID of team owner

        Returns:
            Created team

        Raises:
            ValueError: If team already exists
        """
        team_file = self.data_dir / f"{team_id}.json"
        if team_file.exists():
            raise ValueError(f"Team {team_id} already exists")

        team = Team(
            team_id=team_id,
            name=name,
            owner_id=owner_id,
            members=[TeamMember(user_id=owner_id, role=Role.OWNER)],
        )

        self._save_team(team)
        return team

    def get_team(self, team_id: str) -> Team:
        """Get team by ID.

        Args:
            team_id: Team identifier

        Returns:
            Team object

        Raises:
            FileNotFoundError: If team doesn't exist
        """
        team_file = self.data_dir / f"{team_id}.json"
        if not team_file.exists():
            raise FileNotFoundError(f"Team {team_id} not found")

        with open(team_file) as f:
            data = json.load(f)
            return self._team_from_dict(data)

    def add_member(self, team_id: str, user_id: str, role: Role, actor_id: str) -> None:
        """Add member to team.

        Args:
            team_id: Team identifier
            user_id: User to add
            role: Role to assign
            actor_id: User performing the action

        Raises:
            PermissionError: If actor lacks permission
            ValueError: If member already exists
        """
        team = self.get_team(team_id)

        # Check permission
        if not self.has_permission(team_id, actor_id, Permission.INVITE_MEMBER):
            raise PermissionError(f"User {actor_id} cannot invite members")

        # Check if already member
        if any(m.user_id == user_id for m in team.members):
            raise ValueError(f"User {user_id} is already a member")

        team.members.append(TeamMember(user_id=user_id, role=role))
        self._save_team(team)

    def remove_member(self, team_id: str, user_id: str, actor_id: str) -> None:
        """Remove member from team.

        Args:
            team_id: Team identifier
            user_id: User to remove
            actor_id: User performing the action

        Raises:
            PermissionError: If actor lacks permission or trying to remove owner
            ValueError: If user not a member
        """
        team = self.get_team(team_id)

        # Check permission
        if not self.has_permission(team_id, actor_id, Permission.REMOVE_MEMBER):
            raise PermissionError(f"User {actor_id} cannot remove members")

        # Cannot remove owner
        if user_id == team.owner_id:
            raise PermissionError("Cannot remove team owner")

        # Find and remove member
        original_len = len(team.members)
        team.members = [m for m in team.members if m.user_id != user_id]

        if len(team.members) == original_len:
            raise ValueError(f"User {user_id} is not a member")

        self._save_team(team)

    def create_workspace(
        self,
        team_id: str,
        workspace_name: str,
        budget_usd: float,
        actor_id: str,
    ) -> Workspace:
        """Create workspace in team.

        Args:
            team_id: Team identifier
            workspace_name: Workspace name
            budget_usd: Monthly budget in USD
            actor_id: User performing the action

        Returns:
            Created workspace

        Raises:
            PermissionError: If actor lacks permission
            ValueError: If workspace already exists
        """
        team = self.get_team(team_id)

        # Check permission
        if not self.has_permission(team_id, actor_id, Permission.CREATE_WORKSPACE):
            raise PermissionError(f"User {actor_id} cannot create workspaces")

        # Check if workspace exists
        if workspace_name in team.workspaces:
            raise ValueError(f"Workspace {workspace_name} already exists")

        workspace = Workspace(
            name=workspace_name,
            team_id=team_id,
            budget_usd=budget_usd,
        )

        team.workspaces[workspace_name] = workspace
        self._save_team(team)
        return workspace

    def get_workspace(self, team_id: str, workspace_name: str) -> Workspace:
        """Get workspace by name.

        Args:
            team_id: Team identifier
            workspace_name: Workspace name

        Returns:
            Workspace object

        Raises:
            KeyError: If workspace doesn't exist
        """
        team = self.get_team(team_id)
        if workspace_name not in team.workspaces:
            raise KeyError(f"Workspace {workspace_name} not found in team {team_id}")
        return team.workspaces[workspace_name]

    def has_permission(self, team_id: str, user_id: str, permission: Permission) -> bool:
        """Check if user has permission in team.

        Args:
            team_id: Team identifier
            user_id: User to check
            permission: Permission to check

        Returns:
            True if user has permission
        """
        try:
            team = self.get_team(team_id)
        except FileNotFoundError:
            return False

        # Find user's role
        member = next((m for m in team.members if m.user_id == user_id), None)
        if not member:
            return False

        # Check if role has permission
        role_perms = ROLE_PERMISSIONS.get(member.role, [])
        return permission in role_perms

    def get_user_role(self, team_id: str, user_id: str) -> Role | None:
        """Get user's role in team.

        Args:
            team_id: Team identifier
            user_id: User ID

        Returns:
            User's role or None if not a member
        """
        try:
            team = self.get_team(team_id)
        except FileNotFoundError:
            return None

        member = next((m for m in team.members if m.user_id == user_id), None)
        return member.role if member else None

    def list_teams(self, user_id: str) -> list[Team]:
        """List all teams user is a member of.

        Args:
            user_id: User ID

        Returns:
            List of teams
        """
        teams = []
        for team_file in self.data_dir.glob("*.json"):
            try:
                team = self.get_team(team_file.stem)
                if any(m.user_id == user_id for m in team.members):
                    teams.append(team)
            except Exception:
                continue
        return teams

    def _save_team(self, team: Team) -> None:
        """Save team to disk."""
        team_file = self.data_dir / f"{team.team_id}.json"
        with open(team_file, "w") as f:
            json.dump(self._team_to_dict(team), f, indent=2, default=str)

    def _team_to_dict(self, team: Team) -> dict[str, Any]:
        """Convert team to JSON-serializable dict."""
        return {
            "team_id": team.team_id,
            "name": team.name,
            "owner_id": team.owner_id,
            "members": [
                {
                    "user_id": m.user_id,
                    "role": m.role.value,
                    "joined_at": m.joined_at.isoformat(),
                }
                for m in team.members
            ],
            "workspaces": {
                name: {
                    "name": ws.name,
                    "team_id": ws.team_id,
                    "budget_usd": ws.budget_usd,
                    "resources": ws.resources,
                    "created_at": ws.created_at.isoformat(),
                }
                for name, ws in team.workspaces.items()
            },
            "created_at": team.created_at.isoformat(),
        }

    def _team_from_dict(self, data: dict[str, Any]) -> Team:
        """Convert dict to team object."""
        return Team(
            team_id=data["team_id"],
            name=data["name"],
            owner_id=data["owner_id"],
            members=[
                TeamMember(
                    user_id=m["user_id"],
                    role=Role(m["role"]),
                    joined_at=datetime.fromisoformat(m["joined_at"]),
                )
                for m in data["members"]
            ],
            workspaces={
                name: Workspace(
                    name=ws["name"],
                    team_id=ws["team_id"],
                    budget_usd=ws["budget_usd"],
                    resources=ws["resources"],
                    created_at=datetime.fromisoformat(ws["created_at"]),
                )
                for name, ws in data["workspaces"].items()
            },
            created_at=datetime.fromisoformat(data["created_at"]),
        )
