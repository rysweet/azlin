"""Session context for context-aware natural language parsing.

This module provides session state management to enable pronoun resolution
and context-aware command execution in azlin's natural language interface.

Philosophy:
- Ruthless simplicity: In-memory state, no database
- Clear contract: Simple API for adding commands and resolving pronouns
- Self-contained: All session logic in one module

Public API (the "studs"):
    SessionContext: Main class for managing session state
    CommandHistoryEntry: Dataclass for command history records
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

__all__ = ["CommandHistoryEntry", "SessionContext"]


@dataclass
class CommandHistoryEntry:
    """Single command in session history.

    Attributes:
        request: Original natural language request
        entities: Extracted entities by type (e.g., {"vm": ["test"]})
        timestamp: When command was executed
    """

    request: str
    entities: dict[str, list[str]]
    timestamp: datetime


class SessionContext:
    """Session context for context-aware natural language parsing.

    Tracks recent commands and entities to enable pronoun resolution.
    Keeps last N commands in memory for context.

    Example:
        >>> session = SessionContext()
        >>> session.add_command("create vm test", {"vm": ["test"]})
        >>> session.resolve_pronoun("it", "vm")
        'test'
        >>> context = session.get_context()
        >>> print(context["last_entities"])
        {'vm': 'test'}
    """

    def __init__(self, max_history: int = 10):
        """Initialize session context.

        Args:
            max_history: Maximum number of commands to keep in history.
                        Default 10. Use 0 to disable history tracking.
        """
        self.session_id = str(uuid.uuid4())
        self.max_history = max_history
        self.history: list[CommandHistoryEntry] = []
        self.last_entities: dict[str, str] = {}
        self.created_at = datetime.now()
        self.last_used = datetime.now()

    def add_command(self, request: str, entities: dict[str, list[str]] | None) -> None:
        """Record a command and its entities in session history.

        Updates last_entities with the most recent entity of each type.
        Enforces max_history by removing oldest entries.

        Args:
            request: Original natural language request
            entities: Extracted entities by type. Can be None (treated as empty).

        Example:
            >>> session = SessionContext()
            >>> session.add_command(
            ...     "create vm test in my-rg",
            ...     {"vm": ["test"], "resource_group": ["my-rg"]}
            ... )
            >>> session.last_entities
            {'vm': 'test', 'resource_group': 'my-rg'}
        """
        # Handle None entities
        if entities is None:
            entities = {}

        # Create history entry
        entry = CommandHistoryEntry(request=request, entities=entities, timestamp=datetime.now())

        # Add to history (respecting max_history)
        if self.max_history > 0:
            self.history.append(entry)
            # Remove oldest if over limit
            if len(self.history) > self.max_history:
                self.history.pop(0)

        # Update last_entities (regardless of max_history setting)
        for entity_type, entity_list in entities.items():
            if entity_list:  # Only if list is non-empty
                # Use last entity in list as the "most recent"
                self.last_entities[entity_type] = entity_list[-1]

        # Update last_used timestamp
        self.last_used = datetime.now()

    def resolve_pronoun(self, pronoun: str, entity_type: str) -> str | None:
        """Resolve pronoun to entity name.

        Supports pronouns: "it", "that"
        Case-insensitive matching.

        Args:
            pronoun: Pronoun to resolve ("it", "that", etc.)
            entity_type: Type of entity to resolve to ("vm", "resource_group", etc.)

        Returns:
            Entity name if found, None otherwise

        Example:
            >>> session = SessionContext()
            >>> session.add_command("create vm test", {"vm": ["test"]})
            >>> session.resolve_pronoun("it", "vm")
            'test'
            >>> session.resolve_pronoun("IT", "vm")  # Case insensitive
            'test'
            >>> session.resolve_pronoun("it", "nonexistent")
            None
        """
        # Normalize pronoun to lowercase
        pronoun_lower = pronoun.lower()

        # Check if this is a resolvable pronoun
        if pronoun_lower not in ["it", "that"]:
            return None

        # Return last entity of specified type, or None if not found
        return self.last_entities.get(entity_type)

    def get_context(self) -> dict[str, Any]:
        """Get context dictionary for IntentParser.

        Returns a dict containing:
        - session_id: Unique session identifier
        - last_entities: Most recent entity of each type
        - recent_commands: Last 5 commands (strings)
        - created_at: Session creation timestamp
        - last_used: Last activity timestamp

        Returns:
            Context dict suitable for passing to IntentParser

        Example:
            >>> session = SessionContext()
            >>> session.add_command("create vm test", {"vm": ["test"]})
            >>> context = session.get_context()
            >>> context["last_entities"]
            {'vm': 'test'}
            >>> len(context["recent_commands"])
            1
        """
        # Get last 5 commands for context (don't overwhelm the parser)
        recent_limit = min(5, len(self.history))
        recent_commands = [entry.request for entry in self.history[-recent_limit:]]

        return {
            "session_id": self.session_id,
            "last_entities": self.last_entities.copy(),
            "recent_commands": recent_commands,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat(),
        }

    def is_expired(self, timeout_hours: float = 1.0) -> bool:
        """Check if session has expired due to inactivity.

        Args:
            timeout_hours: Timeout duration in hours. Default 1.0 (1 hour).

        Returns:
            True if session has been idle longer than timeout, False otherwise

        Example:
            >>> session = SessionContext()
            >>> session.is_expired()
            False
            >>> # Simulate 2 hours passing
            >>> session.last_used = datetime.now() - timedelta(hours=2)
            >>> session.is_expired(timeout_hours=1.0)
            True
        """
        timeout_delta = timedelta(hours=timeout_hours)
        idle_time = datetime.now() - self.last_used
        return idle_time > timeout_delta
