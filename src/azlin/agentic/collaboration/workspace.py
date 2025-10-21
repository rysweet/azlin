"""Workspace management for resource isolation and team collaboration."""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path


@dataclass
class Workspace:
    """Isolated workspace for team resources."""

    id: str
    name: str
    team_id: str
    budget_monthly: Decimal = Decimal("0")
    budget_used: Decimal = Decimal("0")
    resource_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    description: str | None = None

    def is_over_budget(self) -> bool:
        """Check if workspace has exceeded budget."""
        return self.budget_used > self.budget_monthly

    def remaining_budget(self) -> Decimal:
        """Get remaining budget amount."""
        return max(Decimal("0"), self.budget_monthly - self.budget_used)

    def budget_utilization_percent(self) -> float:
        """Get budget utilization as percentage."""
        if self.budget_monthly == 0:
            return 0.0
        return float((self.budget_used / self.budget_monthly) * 100)


class WorkspaceManager:
    """Manage workspaces for team collaboration."""

    def __init__(self, storage_dir: str | None = None):
        """Initialize workspace manager.

        Args:
            storage_dir: Directory for workspace storage (default: ~/.azlin/workspaces)
        """
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path.home() / ".azlin" / "workspaces"

        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def create_workspace(
        self,
        name: str,
        team_id: str,
        budget_monthly: Decimal | None = None,
        description: str | None = None,
    ) -> Workspace:
        """Create a new workspace.

        Args:
            name: Workspace name
            team_id: Owning team ID
            budget_monthly: Optional monthly budget limit
            description: Optional description

        Returns:
            Created Workspace
        """
        # Generate workspace ID
        workspace_id = f"{team_id}-{name.lower().replace(' ', '-')}"

        # Create workspace
        workspace = Workspace(
            id=workspace_id,
            name=name,
            team_id=team_id,
            budget_monthly=budget_monthly or Decimal("0"),
            description=description,
        )

        # Save
        self._save_workspace(workspace)

        return workspace

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        """Get workspace by ID.

        Args:
            workspace_id: Workspace ID

        Returns:
            Workspace or None
        """
        ws_file = self.storage_dir / f"{workspace_id}.json"
        if not ws_file.exists():
            return None

        with open(ws_file) as f:
            data = json.load(f)

        return Workspace(
            id=data["id"],
            name=data["name"],
            team_id=data["team_id"],
            budget_monthly=Decimal(data.get("budget_monthly", "0")),
            budget_used=Decimal(data.get("budget_used", "0")),
            resource_count=data.get("resource_count", 0),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            description=data.get("description"),
        )

    def update_budget_usage(self, workspace_id: str, amount: Decimal) -> bool:
        """Update budget usage for workspace.

        Args:
            workspace_id: Workspace ID
            amount: Amount to add to budget_used

        Returns:
            True if successful
        """
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            return False

        workspace.budget_used += amount
        self._save_workspace(workspace)

        return True

    def set_budget(self, workspace_id: str, monthly_budget: Decimal) -> bool:
        """Set monthly budget for workspace.

        Args:
            workspace_id: Workspace ID
            monthly_budget: New monthly budget limit

        Returns:
            True if successful
        """
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            return False

        workspace.budget_monthly = monthly_budget
        self._save_workspace(workspace)

        return True

    def increment_resource_count(self, workspace_id: str, count: int = 1) -> bool:
        """Increment resource count for workspace.

        Args:
            workspace_id: Workspace ID
            count: Number to increment by

        Returns:
            True if successful
        """
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            return False

        workspace.resource_count += count
        self._save_workspace(workspace)

        return True

    def list_workspaces(self, team_id: str | None = None) -> list[Workspace]:
        """List all workspaces, optionally filtered by team.

        Args:
            team_id: Optional team ID to filter by

        Returns:
            List of workspaces
        """
        workspaces = []

        for ws_file in self.storage_dir.glob("*.json"):
            workspace = self.get_workspace(ws_file.stem)
            if workspace:
                if team_id is None or workspace.team_id == team_id:
                    workspaces.append(workspace)

        return workspaces

    def _save_workspace(self, workspace: Workspace) -> None:
        """Save workspace to disk.

        Args:
            workspace: Workspace to save
        """
        ws_file = self.storage_dir / f"{workspace.id}.json"

        data = {
            "id": workspace.id,
            "name": workspace.name,
            "team_id": workspace.team_id,
            "budget_monthly": str(workspace.budget_monthly),
            "budget_used": str(workspace.budget_used),
            "resource_count": workspace.resource_count,
            "created_at": workspace.created_at,
            "description": workspace.description,
        }

        with open(ws_file, "w") as f:
            json.dump(data, f, indent=2)

        # Set restrictive permissions
        os.chmod(ws_file, 0o600)
