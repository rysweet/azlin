"""Team management for collaborative azlin operations."""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class TeamRole(str, Enum):
    """Team member roles with hierarchical permissions."""

    OWNER = "owner"  # Full control
    ADMIN = "admin"  # Manage members, execute operations
    MEMBER = "member"  # Execute operations only
    VIEWER = "viewer"  # Read-only access


@dataclass
class TeamMember:
    """Team member with role and metadata."""

    user_id: str
    role: TeamRole
    added_at: str
    added_by: str


@dataclass
class Team:
    """Team for collaborative operations."""

    id: str
    name: str
    owner_id: str
    members: list[TeamMember] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    description: str | None = None

    def has_member(self, user_id: str) -> bool:
        """Check if user is a team member."""
        return user_id == self.owner_id or any(m.user_id == user_id for m in self.members)

    def get_member_role(self, user_id: str) -> TeamRole | None:
        """Get role of a team member."""
        if user_id == self.owner_id:
            return TeamRole.OWNER
        for member in self.members:
            if member.user_id == user_id:
                return member.role
        return None

    def can_execute(self, user_id: str) -> bool:
        """Check if user can execute operations."""
        role = self.get_member_role(user_id)
        return role in [TeamRole.OWNER, TeamRole.ADMIN, TeamRole.MEMBER]

    def can_manage(self, user_id: str) -> bool:
        """Check if user can manage team members."""
        role = self.get_member_role(user_id)
        return role in [TeamRole.OWNER, TeamRole.ADMIN]


class TeamManager:
    """Manage teams for collaborative operations."""

    def __init__(self, storage_dir: str | None = None):
        """Initialize team manager.

        Args:
            storage_dir: Directory for team storage (default: ~/.azlin/teams)
        """
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path.home() / ".azlin" / "teams"

        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def create_team(self, name: str, owner_id: str, description: str | None = None) -> Team:
        """Create a new team.

        Args:
            name: Team name
            owner_id: Owner user ID
            description: Optional team description

        Returns:
            Created Team
        """
        # Generate team ID from name
        team_id = name.lower().replace(" ", "-")

        # Create team
        team = Team(
            id=team_id,
            name=name,
            owner_id=owner_id,
            description=description,
        )

        # Save to disk
        self._save_team(team)

        return team

    def get_team(self, team_id: str) -> Team | None:
        """Get team by ID.

        Args:
            team_id: Team ID

        Returns:
            Team or None if not found
        """
        team_file = self.storage_dir / f"{team_id}.json"
        if not team_file.exists():
            return None

        with open(team_file) as f:
            data = json.load(f)

        return Team(
            id=data["id"],
            name=data["name"],
            owner_id=data["owner_id"],
            members=[
                TeamMember(
                    user_id=m["user_id"],
                    role=TeamRole(m["role"]),
                    added_at=m["added_at"],
                    added_by=m["added_by"],
                )
                for m in data.get("members", [])
            ],
            created_at=data["created_at"],
            description=data.get("description"),
        )

    def add_member(self, team_id: str, user_id: str, role: TeamRole, added_by: str) -> bool:
        """Add member to team.

        Args:
            team_id: Team ID
            user_id: User ID to add
            role: Role to assign
            added_by: User ID adding the member

        Returns:
            True if successful
        """
        team = self.get_team(team_id)
        if not team:
            return False

        # Check if adder has permission
        if not team.can_manage(added_by):
            return False

        # Check if already a member
        if team.has_member(user_id):
            return False

        # Add member
        member = TeamMember(
            user_id=user_id,
            role=role,
            added_at=datetime.utcnow().isoformat(),
            added_by=added_by,
        )
        team.members.append(member)

        # Save
        self._save_team(team)

        return True

    def remove_member(self, team_id: str, user_id: str, removed_by: str) -> bool:
        """Remove member from team.

        Args:
            team_id: Team ID
            user_id: User ID to remove
            removed_by: User ID removing the member

        Returns:
            True if successful
        """
        team = self.get_team(team_id)
        if not team:
            return False

        # Check if remover has permission
        if not team.can_manage(removed_by):
            return False

        # Cannot remove owner
        if user_id == team.owner_id:
            return False

        # Remove member
        team.members = [m for m in team.members if m.user_id != user_id]

        # Save
        self._save_team(team)

        return True

    def list_teams(self, user_id: str | None = None) -> list[Team]:
        """List all teams, optionally filtered by user membership.

        Args:
            user_id: Optional user ID to filter by

        Returns:
            List of teams
        """
        teams = []

        for team_file in self.storage_dir.glob("*.json"):
            team = self.get_team(team_file.stem)
            if team and (user_id is None or team.has_member(user_id)):
                teams.append(team)

        return teams

    def _save_team(self, team: Team) -> None:
        """Save team to disk.

        Args:
            team: Team to save
        """
        team_file = self.storage_dir / f"{team.id}.json"

        data = {
            "id": team.id,
            "name": team.name,
            "owner_id": team.owner_id,
            "members": [
                {
                    "user_id": m.user_id,
                    "role": m.role.value,
                    "added_at": m.added_at,
                    "added_by": m.added_by,
                }
                for m in team.members
            ],
            "created_at": team.created_at,
            "description": team.description,
        }

        with open(team_file, "w") as f:
            json.dump(data, f, indent=2)

        # Set restrictive permissions
        os.chmod(team_file, 0o600)
