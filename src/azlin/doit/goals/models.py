"""Data models for goal representation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GoalStatus(Enum):
    """Status of a goal in the execution pipeline."""

    PENDING = "pending"
    READY = "ready"  # Dependencies met, ready to execute
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"  # Waiting on dependencies


class ResourceType(Enum):
    """Azure resource types we can deploy."""

    RESOURCE_GROUP = "azurerm_resource_group"
    APP_SERVICE = "azurerm_app_service"
    APP_SERVICE_PLAN = "azurerm_app_service_plan"
    FUNCTION_APP = "azurerm_function_app"
    COSMOS_DB = "azurerm_cosmosdb_account"
    SQL_DATABASE = "azurerm_sql_database"
    SQL_SERVER = "azurerm_sql_server"
    STORAGE_ACCOUNT = "azurerm_storage_account"
    KEY_VAULT = "azurerm_key_vault"
    API_MANAGEMENT = "azurerm_api_management"
    VNET = "azurerm_virtual_network"
    SUBNET = "azurerm_subnet"
    MANAGED_IDENTITY = "azurerm_user_assigned_identity"
    CONNECTION = "connection"  # Logical connection between resources
    CONFIGURATION = "configuration"  # Configuration task


class ConnectionType(Enum):
    """Types of connections between resources."""

    CONNECTION_STRING = "connection_string"  # Via Key Vault
    MANAGED_IDENTITY = "managed_identity"  # Using managed identity
    API_BACKEND = "api_backend"  # APIM backend
    VNET_INTEGRATION = "vnet_integration"  # Network integration
    PRIVATE_ENDPOINT = "private_endpoint"  # Private endpoint


@dataclass
class Goal:
    """Represents a single goal to achieve."""

    id: str
    type: ResourceType
    name: str
    level: int  # Dependency level (0 = no deps, higher = more deps)
    dependencies: list[str] = field(default_factory=list)  # Goal IDs
    status: GoalStatus = GoalStatus.PENDING
    parameters: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)  # Results after execution
    error: str | None = None
    attempts: int = 0
    max_attempts: int = 3

    def is_ready(self, completed_goals: set[str]) -> bool:
        """Check if all dependencies are completed."""
        if self.status in [GoalStatus.COMPLETED, GoalStatus.FAILED]:
            return False
        return all(dep_id in completed_goals for dep_id in self.dependencies)

    def mark_ready(self) -> None:
        """Mark goal as ready for execution."""
        if self.status == GoalStatus.PENDING:
            self.status = GoalStatus.READY

    def mark_in_progress(self) -> None:
        """Mark goal as in progress."""
        self.status = GoalStatus.IN_PROGRESS
        self.attempts += 1

    def mark_completed(self, outputs: dict[str, Any]) -> None:
        """Mark goal as completed with outputs."""
        self.status = GoalStatus.COMPLETED
        self.outputs = outputs

    def mark_failed(self, error: str) -> None:
        """Mark goal as failed."""
        self.status = GoalStatus.FAILED
        self.error = error

    def mark_blocked(self, reason: str) -> None:
        """Mark goal as blocked."""
        self.status = GoalStatus.BLOCKED
        self.error = reason

    def can_retry(self) -> bool:
        """Check if goal can be retried."""
        return self.attempts < self.max_attempts and self.status == GoalStatus.FAILED


@dataclass
class Connection:
    """Represents a connection between two resources."""

    from_goal_id: str
    to_goal_id: str
    connection_type: ConnectionType
    via: str | None = None  # e.g., "key_vault_secret"
    configuration: dict[str, Any] = field(default_factory=dict)


@dataclass
class GoalHierarchy:
    """Complete hierarchy of goals to achieve."""

    primary_goal: str  # High-level description
    goals: list[Goal] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)
    implicit_requirements: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_goal(self, goal_id: str) -> Goal | None:
        """Get goal by ID."""
        for goal in self.goals:
            if goal.id == goal_id:
                return goal
        return None

    def get_goals_by_level(self, level: int) -> list[Goal]:
        """Get all goals at a specific dependency level."""
        return [g for g in self.goals if g.level == level]

    def get_ready_goals(self) -> list[Goal]:
        """Get all goals ready for execution."""
        completed = {g.id for g in self.goals if g.status == GoalStatus.COMPLETED}
        return [goal for goal in self.goals if goal.is_ready(completed)]

    def get_max_level(self) -> int:
        """Get maximum dependency level."""
        if not self.goals:
            return 0
        return max(g.level for g in self.goals)

    def is_complete(self) -> bool:
        """Check if all goals are completed."""
        return all(g.status in [GoalStatus.COMPLETED, GoalStatus.FAILED] for g in self.goals)

    def get_progress(self) -> tuple[int, int]:
        """Get (completed, total) count."""
        completed = sum(1 for g in self.goals if g.status == GoalStatus.COMPLETED)
        return completed, len(self.goals)

    def get_connections_for_goal(self, goal_id: str) -> list[Connection]:
        """Get all connections involving a goal."""
        return [c for c in self.connections if c.from_goal_id == goal_id or c.to_goal_id == goal_id]


@dataclass
class ParsedRequest:
    """Result of parsing a user request."""

    raw_request: str
    primary_goal: str
    resource_requests: list[dict[str, Any]]  # Raw resource descriptions
    implied_connections: list[dict[str, Any]]  # Implied relationships
    constraints: dict[str, Any]  # User constraints
    goal_hierarchy: GoalHierarchy | None = None  # Built hierarchy
