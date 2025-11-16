"""Objective state manager for azdoit framework.

Manages persistent state for objectives at ~/.azlin/objectives/<uuid>.json
with secure file permissions and atomic updates.
"""

import contextlib
import json
import logging
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, cast

from azlin.agentic.types import (
    Intent,
    ObjectiveState,
    ObjectiveStatus,
    WorkflowHistoryEvent,
)

logger = logging.getLogger(__name__)


class ObjectiveError(Exception):
    """Error managing objective state."""

    pass


class ObjectiveManager:
    """Manage objective state persistence.

    Objectives are stored as JSON files at ~/.azlin/objectives/<uuid>.json
    with secure 0600 permissions.

    Example:
        >>> manager = ObjectiveManager()
        >>> state = manager.create(
        ...     natural_language="Create a VM",
        ...     intent=Intent(intent="provision_vm", parameters={}, confidence=0.9, azlin_commands=[])
        ... )
        >>> print(state.id)
        obj_20251020_001
        >>> loaded = manager.load(state.id)
        >>> manager.update(state.id, status=ObjectiveStatus.COMPLETED)
    """

    DEFAULT_OBJECTIVES_DIR = Path.home() / ".azlin" / "objectives"

    # Valid state transitions
    STATE_TRANSITIONS: ClassVar[dict[ObjectiveStatus, list[ObjectiveStatus]]] = {
        ObjectiveStatus.PENDING: [ObjectiveStatus.IN_PROGRESS, ObjectiveStatus.FAILED],
        ObjectiveStatus.IN_PROGRESS: [ObjectiveStatus.COMPLETED, ObjectiveStatus.FAILED],
        ObjectiveStatus.COMPLETED: [],  # Terminal state
        ObjectiveStatus.FAILED: [
            ObjectiveStatus.PENDING,
            ObjectiveStatus.IN_PROGRESS,
        ],  # Allow retry
    }

    def __init__(self, objectives_dir: Path | None = None):
        """Initialize objective manager.

        Args:
            objectives_dir: Directory for objective files (default: ~/.azlin/objectives)
        """
        self.objectives_dir = objectives_dir or self.DEFAULT_OBJECTIVES_DIR
        self.objectives_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _validate_objective_id(self, objective_id: str) -> None:
        """Validate objective ID format for security.

        Args:
            objective_id: Objective ID to validate

        Raises:
            ValueError: If ID is invalid
        """
        if not objective_id or not objective_id.strip():
            raise ValueError("objective_id cannot be empty")
        if len(objective_id) > 255:
            raise ValueError(f"objective_id too long ({len(objective_id)} > 255 chars)")
        if ".." in objective_id or "/" in objective_id or "\\" in objective_id:
            raise ValueError("objective_id cannot contain path traversal characters")
        # Additional security: ensure only safe characters (UUID format)
        if not all(c.isalnum() or c in "-_" for c in objective_id):
            raise ValueError(
                "objective_id contains invalid characters (only alphanumeric, dash, underscore allowed)"
            )

    def create(
        self,
        natural_language: str,
        intent: Intent,
        status: ObjectiveStatus = ObjectiveStatus.PENDING,
        max_retries: int = 3,
    ) -> ObjectiveState:
        """Create a new objective with generated ID.

        Args:
            natural_language: User's original request
            intent: Parsed intent structure
            status: Initial status (default: PENDING)
            max_retries: Maximum retry attempts (default: 3)

        Returns:
            ObjectiveState with generated ID

        Raises:
            ValueError: If natural_language is empty or intent is invalid

        Example:
            >>> manager = ObjectiveManager()
            >>> state = manager.create(
            ...     "Create an AKS cluster",
            ...     Intent(intent="provision_aks", parameters={}, confidence=0.9, azlin_commands=[])
            ... )
            >>> assert state.status == ObjectiveStatus.PENDING
        """
        if not natural_language or not natural_language.strip():
            raise ValueError("Natural language cannot be empty")

        if not isinstance(intent, Intent):
            raise ValueError("intent must be an Intent instance")

        # Validate intent has required field
        if not hasattr(intent, "intent") or not intent.intent:
            raise ValueError("Missing required field: intent")

        # Generate unique ID
        objective_id = self._generate_id()

        now = datetime.now(UTC)
        state = ObjectiveState(
            id=objective_id,
            natural_language=natural_language.strip(),
            intent=intent,
            status=status,
            created_at=now,
            updated_at=now,
            max_retries=max_retries,
        )

        # Validate and save
        state.validate_schema()
        self._save(state)

        logger.info(f"Created objective {objective_id}: {natural_language[:50]}")
        return state

    def load(self, objective_id: str) -> ObjectiveState:
        """Load objective by ID.

        Args:
            objective_id: Objective ID

        Returns:
            ObjectiveState

        Raises:
            FileNotFoundError: If objective doesn't exist
            ValueError: If objective_id is invalid

        Example:
            >>> manager = ObjectiveManager()
            >>> state = manager.load("obj_20251020_001")
        """
        # Validate ID format for security
        self._validate_objective_id(objective_id)

        objective_file = self.objectives_dir / f"{objective_id}.json"

        if not objective_file.exists():
            raise FileNotFoundError(f"Objective not found: {objective_id}")

        try:
            with open(objective_file) as f:
                data = json.load(f)
            return ObjectiveState.from_dict(data)
        except json.JSONDecodeError as e:
            raise ObjectiveError(f"Corrupted objective file: {objective_id}") from e

    def update(
        self,
        objective_id: str,
        status: ObjectiveStatus | None = None,
        **kwargs: Any,
    ) -> ObjectiveState:
        """Update objective fields atomically.

        Args:
            objective_id: Objective ID
            status: New status (validates transitions)
            **kwargs: Other fields to update (selected_strategy, cost_estimate, etc.)

        Returns:
            Updated ObjectiveState

        Raises:
            ValueError: If state transition is invalid

        Example:
            >>> manager = ObjectiveManager()
            >>> state = manager.update(
            ...     "obj_20251020_001",
            ...     status=ObjectiveStatus.IN_PROGRESS,
            ...     selected_strategy=Strategy.TERRAFORM,
            ... )
        """
        state = self.load(objective_id)

        # Validate and apply status change
        self._apply_status_change(state, status)

        # Update additional fields
        self._apply_field_updates(state, kwargs)

        # Update timestamp
        state.updated_at = datetime.now(UTC)

        # Validate and persist
        self._validate_and_persist(state)

        logger.info(f"Updated objective {objective_id}: status={state.status.value}")
        return state

    def _apply_status_change(
        self, state: ObjectiveState, new_status: ObjectiveStatus | None
    ) -> None:
        """Apply status change with validation.

        Args:
            state: Objective state to modify
            new_status: New status to apply

        Raises:
            ValueError: If state transition is invalid
        """
        if new_status is not None and new_status != state.status:
            if not self._is_valid_transition(state.status, new_status):
                raise ValueError(
                    f"Invalid state transition: {state.status.value} -> {new_status.value}"
                )
            state.status = new_status

    def _apply_field_updates(self, state: ObjectiveState, updates: dict[str, Any]) -> None:
        """Apply field updates to state.

        Args:
            state: Objective state to modify
            updates: Dictionary of field updates
        """
        for key, value in updates.items():
            if hasattr(state, key):
                setattr(state, key, value)
            else:
                logger.warning(f"Unknown field ignored: {key}")

    def _validate_and_persist(self, state: ObjectiveState) -> None:
        """Validate state and persist to disk.

        Args:
            state: Objective state to validate and save
        """
        state.validate_schema()
        self._save(state)

    def delete(self, objective_id: str) -> None:
        """Delete objective file.

        Args:
            objective_id: Objective ID

        Raises:
            FileNotFoundError: If objective doesn't exist

        Example:
            >>> manager = ObjectiveManager()
            >>> manager.delete("obj_20251020_001")
        """
        objective_file = self.objectives_dir / f"{objective_id}.json"

        if not objective_file.exists():
            raise FileNotFoundError(f"Objective not found: {objective_id}")

        objective_file.unlink()
        logger.info(f"Deleted objective {objective_id}")

    def list_objectives(
        self,
        status: ObjectiveStatus | None = None,
        limit: int | None = None,
    ) -> list[ObjectiveState]:
        """List all objectives with optional filtering.

        Args:
            status: Filter by status (default: all)
            limit: Maximum number to return (default: all)

        Returns:
            List of ObjectiveState ordered by created_at (newest first)

        Example:
            >>> manager = ObjectiveManager()
            >>> in_progress = manager.list_objectives(status=ObjectiveStatus.IN_PROGRESS)
            >>> recent = manager.list_objectives(limit=10)
        """
        objectives = []

        for objective_file in self.objectives_dir.glob("*.json"):
            try:
                with open(objective_file) as f:
                    data = json.load(f)
                state = ObjectiveState.from_dict(data)

                # Apply status filter
                if status is not None and state.status != status:
                    continue

                objectives.append(state)

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"Skipping corrupted file {objective_file}: {e}")
                continue

        # Sort by created_at descending (newest first)
        objectives.sort(key=lambda x: x.created_at, reverse=True)

        # Apply limit
        if limit is not None:
            objectives = objectives[:limit]

        return objectives

    def append_history(
        self,
        objective_id: str,
        event: dict[str, Any],  # Kept as dict for flexibility - can be WorkflowHistoryEvent
    ) -> ObjectiveState:
        """Append event to execution history.

        Args:
            objective_id: Objective ID
            event: Event dictionary (should include timestamp, action, details)

        Returns:
            Updated ObjectiveState

        Example:
            >>> manager = ObjectiveManager()
            >>> state = manager.append_history(
            ...     "obj_20251020_001",
            ...     {
            ...         "timestamp": datetime.now(timezone.utc).isoformat(),
            ...         "action": "strategy_selected",
            ...         "details": {"strategy": "azure_cli"},
            ...     }
            ... )
        """
        state = self.load(objective_id)
        state.execution_history.append(cast(WorkflowHistoryEvent, event))
        state.updated_at = datetime.now(UTC)
        self._save(state)
        return state

    def increment_retry(self, objective_id: str) -> ObjectiveState:
        """Increment retry count.

        Args:
            objective_id: Objective ID

        Returns:
            Updated ObjectiveState

        Example:
            >>> manager = ObjectiveManager()
            >>> state = manager.increment_retry("obj_20251020_001")
            >>> print(state.retry_count)
            1
        """
        state = self.load(objective_id)
        state.retry_count += 1
        state.updated_at = datetime.now(UTC)
        self._save(state)
        logger.info(f"Incremented retry count for {objective_id}: {state.retry_count}")
        return state

    def reset_retry_count(self, objective_id: str) -> ObjectiveState:
        """Reset retry count to 0.

        Args:
            objective_id: Objective ID

        Returns:
            Updated ObjectiveState

        Example:
            >>> manager = ObjectiveManager()
            >>> state = manager.reset_retry_count("obj_20251020_001")
            >>> assert state.retry_count == 0
        """
        state = self.load(objective_id)
        state.retry_count = 0
        state.updated_at = datetime.now(UTC)
        self._save(state)
        return state

    def has_max_retries_reached(self, objective_id: str) -> bool:
        """Check if max retries reached.

        Args:
            objective_id: Objective ID

        Returns:
            True if retry_count >= max_retries

        Example:
            >>> manager = ObjectiveManager()
            >>> if manager.has_max_retries_reached("obj_20251020_001"):
            ...     print("Max retries reached, giving up")
        """
        state = self.load(objective_id)
        return state.retry_count >= state.max_retries

    def recover_incomplete_objectives(self) -> list[ObjectiveState]:
        """Recover objectives that were in progress during restart.

        Returns:
            List of ObjectiveState with IN_PROGRESS or PENDING status

        Example:
            >>> manager = ObjectiveManager()
            >>> incomplete = manager.recover_incomplete_objectives()
            >>> for obj in incomplete:
            ...     print(f"Recovering: {obj.id}")
        """
        return self.list_objectives(status=ObjectiveStatus.IN_PROGRESS) + self.list_objectives(
            status=ObjectiveStatus.PENDING
        )

    def get_valid_transitions(self) -> dict[str, list[str]]:
        """Get valid state transitions.

        Returns:
            Dictionary mapping status to valid next statuses

        Example:
            >>> manager = ObjectiveManager()
            >>> transitions = manager.get_valid_transitions()
            >>> print(transitions["pending"])
            ['in_progress', 'failed']
        """
        return {k.value: [v.value for v in values] for k, values in self.STATE_TRANSITIONS.items()}

    def _generate_id(self) -> str:
        """Generate unique objective ID.

        Format: <uuid4>

        Returns:
            Generated ID string

        Example:
            >>> manager = ObjectiveManager()
            >>> obj_id = manager._generate_id()
            >>> print(obj_id)
            'a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d'
        """
        return str(uuid.uuid4())

    def _save(self, state: ObjectiveState) -> None:
        """Save objective state atomically.

        Uses tmp file + rename pattern for atomic writes.
        Sets file permissions to 0600.

        Args:
            state: ObjectiveState to save
        """
        objective_file = self.objectives_dir / f"{state.id}.json"

        # Use temp file + rename for atomic write
        fd, tmp_path = tempfile.mkstemp(
            dir=self.objectives_dir, prefix=f".{state.id}.", suffix=".tmp"
        )

        try:
            # Write to temp file
            with os.fdopen(fd, "w") as f:
                json.dump(state.to_dict(), f, indent=2)

            # Set secure permissions (0600)
            os.chmod(tmp_path, 0o600)

            # Atomic replace (guaranteed atomic on POSIX)
            os.replace(tmp_path, objective_file)

        except Exception:
            # Clean up temp file on error
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

    def _is_valid_transition(
        self,
        from_status: ObjectiveStatus,
        to_status: ObjectiveStatus,
    ) -> bool:
        """Check if state transition is valid.

        Args:
            from_status: Current status
            to_status: Target status

        Returns:
            True if transition is allowed
        """
        return to_status in self.STATE_TRANSITIONS.get(from_status, [])
