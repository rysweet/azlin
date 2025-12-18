"""Audit logging for azdoit framework.

Append-only audit log at ~/.azlin/audit.log with automatic rotation.
"""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, TypedDict

from azlin.file_lock_manager import acquire_file_lock

logger = logging.getLogger(__name__)


class AuditLogEntry(TypedDict):
    """Typed structure for audit log entries."""

    timestamp: str
    objective_id: str | None
    event: str
    details: dict[str, str]


class AuditLogger:
    """Audit logger for objective tracking.

    Writes structured audit logs to ~/.azlin/audit.log with:
    - Append-only writes
    - Automatic rotation at 10MB
    - Secure 0600 permissions
    - Structured format: timestamp | objective_id | event | details

    Example:
        >>> logger = AuditLogger()
        >>> logger.log("OBJECTIVE_CREATED", objective_id="obj_123", details={"intent": "provision_vm"})
        >>> logger.log("STRATEGY_SELECTED", objective_id="obj_123", details={"strategy": "terraform"})
    """

    DEFAULT_LOG_FILE = Path.home() / ".azlin" / "audit.log"
    MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
    ROTATION_COUNT = 5  # Keep 5 old logs

    # Standard event types
    EVENT_TYPES: ClassVar[list[str]] = [
        "OBJECTIVE_CREATED",
        "STRATEGY_SELECTED",
        "EXECUTION_STARTED",
        "EXECUTION_COMPLETED",
        "EXECUTION_FAILED",
        "RETRY_ATTEMPTED",
        "MAX_RETRIES_REACHED",
        "OBJECTIVE_DELETED",
    ]

    def __init__(self, log_file: Path | None = None):
        """Initialize audit logger.

        Args:
            log_file: Path to audit log (default: ~/.azlin/audit.log)
        """
        self.log_file = log_file or self.DEFAULT_LOG_FILE
        self._ensure_log_file()

    def log(
        self,
        event: str,
        objective_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Write audit log entry.

        Format: timestamp | objective_id | event | details

        Args:
            event: Event type (e.g., "OBJECTIVE_CREATED")
            objective_id: Associated objective ID (optional)
            details: Additional details as dict (optional)

        Example:
            >>> logger = AuditLogger()
            >>> logger.log(
            ...     "STRATEGY_SELECTED",
            ...     objective_id="obj_20251020_001",
            ...     details={"strategy": "azure_cli", "fallbacks": ["terraform"]}
            ... )
        """
        # Rotate if needed
        self._rotate_if_needed()

        timestamp = datetime.now(UTC).isoformat()
        obj_id = objective_id or "N/A"

        # Format details
        if details:
            # Convert dict to compact string representation
            details_str = " ".join(f"{k}={v}" for k, v in details.items())
            # Build log line with details
            log_line = f"{timestamp} | {obj_id} | {event} | {details_str}\n"
        else:
            # Build log line without details separator
            log_line = f"{timestamp} | {obj_id} | {event}\n"

        # Append to log file with file locking for concurrent access
        try:
            with acquire_file_lock(self.log_file, timeout=5.0, operation="audit logging"):
                with open(self.log_file, "a") as f:
                    f.write(log_line)
                    f.flush()  # Ensure data is written before lock release
            logger.debug(f"Audit log: {event} for {obj_id}")
        except OSError as e:
            logger.error(f"Failed to write audit log: {e}")

    def read_logs(
        self,
        objective_id: str | None = None,
        event_type: str | None = None,
        limit: int | None = None,
    ) -> list[AuditLogEntry]:
        """Read audit logs with filtering.

        Args:
            objective_id: Filter by objective ID
            event_type: Filter by event type
            limit: Maximum number of entries to return (newest first)

        Returns:
            List of parsed log entries

        Example:
            >>> logger = AuditLogger()
            >>> entries = logger.read_logs(objective_id="obj_123", limit=10)
            >>> for entry in entries:
            ...     print(f"{entry['timestamp']}: {entry['event']}")
        """
        if not self.log_file.exists():
            return []

        entries = []

        try:
            with open(self.log_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    entry = self._parse_log_line(line)
                    if not entry:
                        continue

                    # Apply filters
                    if objective_id and entry.get("objective_id") != objective_id:
                        continue
                    if event_type and entry.get("event") != event_type:
                        continue

                    entries.append(entry)

        except OSError as e:
            logger.error(f"Failed to read audit log: {e}")
            return []

        # Return newest first
        entries.reverse()

        # Apply limit
        if limit is not None:
            entries = entries[:limit]

        return entries

    def get_objective_timeline(self, objective_id: str) -> list[AuditLogEntry]:
        """Get complete timeline for an objective.

        Args:
            objective_id: Objective ID

        Returns:
            List of log entries for this objective (chronological order)

        Example:
            >>> logger = AuditLogger()
            >>> timeline = logger.get_objective_timeline("obj_123")
            >>> for event in timeline:
            ...     print(f"{event['event']} at {event['timestamp']}")
        """
        entries = self.read_logs(objective_id=objective_id)
        entries.reverse()  # Chronological order (oldest first)
        return entries

    def _ensure_log_file(self) -> None:
        """Ensure log file and directory exist with secure permissions."""
        # Create directory if needed
        self.log_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Create log file if needed
        if not self.log_file.exists():
            self.log_file.touch(mode=0o600)
            logger.info(f"Created audit log: {self.log_file}")
        else:
            # Ensure secure permissions on existing file
            os.chmod(self.log_file, 0o600)

    def _rotate_if_needed(self) -> None:
        """Rotate log file if it exceeds max size.

        Rotation scheme:
        - audit.log -> audit.log.1
        - audit.log.1 -> audit.log.2
        - ...
        - audit.log.4 -> audit.log.5 (oldest, will be deleted next rotation)
        """
        if not self.log_file.exists():
            return

        # Check size
        try:
            size = self.log_file.stat().st_size
            if size < self.MAX_LOG_SIZE:
                return
        except OSError:
            return

        logger.info(f"Rotating audit log (size: {size} bytes)")

        # Acquire lock for rotation to prevent concurrent access during rotation
        try:
            with acquire_file_lock(self.log_file, timeout=5.0, operation="audit log rotation"):
                # Rotate existing numbered logs
                for i in range(self.ROTATION_COUNT - 1, 0, -1):
                    old_log = Path(f"{self.log_file}.{i}")
                    new_log = Path(f"{self.log_file}.{i + 1}")

                    if old_log.exists():
                        if new_log.exists():
                            new_log.unlink()  # Delete oldest if at limit
                        old_log.rename(new_log)

                # Rotate current log to .1
                backup_log = Path(f"{self.log_file}.1")
                if backup_log.exists():
                    backup_log.unlink()
                self.log_file.rename(backup_log)

                # Create new empty log file
                self.log_file.touch(mode=0o600)
        except OSError as e:
            logger.error(f"Failed to rotate audit log: {e}")

    def _parse_log_line(self, line: str) -> AuditLogEntry | None:
        """Parse log line into structured entry.

        Args:
            line: Raw log line

        Returns:
            Parsed entry dict or None if invalid

        Example:
            >>> logger = AuditLogger()
            >>> line = "2025-10-20T10:30:00 | obj_123 | OBJECTIVE_CREATED | intent=provision_vm"
            >>> entry = logger._parse_log_line(line)
            >>> print(entry["event"])
            OBJECTIVE_CREATED
        """
        try:
            parts = line.split(" | ")
            if len(parts) < 3:
                return None

            timestamp = parts[0].strip()
            objective_id = parts[1].strip()
            event = parts[2].strip()
            details_str = parts[3].strip() if len(parts) > 3 else ""

            # Parse details
            details: dict[str, str] = {}
            if details_str:
                for pair in details_str.split():
                    if "=" in pair:
                        key, value = pair.split("=", 1)
                        details[key] = value

            return AuditLogEntry(
                timestamp=timestamp,
                objective_id=objective_id if objective_id != "N/A" else None,
                event=event,
                details=details,
            )

        except Exception as e:
            logger.warning(f"Failed to parse log line: {e}")
            return None

    def get_statistics(self) -> dict[str, Any]:
        """Get audit log statistics.

        Returns:
            Dictionary with stats (total_entries, events_by_type, etc.)

        Example:
            >>> logger = AuditLogger()
            >>> stats = logger.get_statistics()
            >>> print(f"Total entries: {stats['total_entries']}")
            >>> print(f"Created: {stats['events_by_type']['OBJECTIVE_CREATED']}")
        """
        entries = self.read_logs()

        events_by_type: dict[str, int] = {}
        objectives: set[str] = set()

        for entry in entries:
            event = entry["event"]
            events_by_type[event] = events_by_type.get(event, 0) + 1

            if entry["objective_id"]:
                objectives.add(entry["objective_id"])

        return {
            "total_entries": len(entries),
            "events_by_type": events_by_type,
            "unique_objectives": len(objectives),
            "log_file_size": self.log_file.stat().st_size if self.log_file.exists() else 0,
        }
