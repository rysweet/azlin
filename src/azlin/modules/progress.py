"""
Progress Display Module

Show real-time progress to user during long operations.

Security Requirements:
- No credential exposure in output
- Safe output formatting
- Thread-safe operations (if used concurrently)
"""

import logging
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ProgressStage(Enum):
    """Progress stage indicators."""

    STARTED = "started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    WARNING = "warning"


@dataclass
class ProgressUpdate:
    """Progress update information."""

    stage: ProgressStage
    message: str
    timestamp: float
    operation: str


class ProgressDisplay:
    """
    Real-time progress display for long operations.

    Features:
    - Stage-based updates
    - Time tracking
    - Console output
    - Optional rich formatting (if available)
    """

    # Stage symbols (ASCII-safe, works in all terminals)
    SYMBOLS = {
        ProgressStage.STARTED: "►",
        ProgressStage.IN_PROGRESS: "...",
        ProgressStage.COMPLETED: "✓",
        ProgressStage.FAILED: "✗",
        ProgressStage.WARNING: "⚠",
    }

    # Fallback ASCII symbols (if Unicode not supported)
    ASCII_SYMBOLS = {
        ProgressStage.STARTED: ">",
        ProgressStage.IN_PROGRESS: "...",
        ProgressStage.COMPLETED: "OK",
        ProgressStage.FAILED: "FAIL",
        ProgressStage.WARNING: "WARN",
    }

    def __init__(self, use_unicode: bool = True, output_file=None):
        """
        Initialize progress display.

        Args:
            use_unicode: Use Unicode symbols (True) or ASCII (False)
            output_file: Output file object (default: sys.stdout)
        """
        self.use_unicode = use_unicode
        self.output_file = output_file or sys.stdout
        self.current_operation: Optional[str] = None
        self.start_time: Optional[float] = None
        self.updates: list[ProgressUpdate] = []

    def start_operation(self, name: str, estimated_seconds: Optional[int] = None) -> None:
        """
        Begin showing progress for an operation.

        Args:
            name: Operation name
            estimated_seconds: Optional estimated duration

        Example:
            >>> progress = ProgressDisplay()
            >>> progress.start_operation("Creating VM", estimated_seconds=300)
        """
        self.current_operation = name
        self.start_time = time.time()

        message = f"Starting: {name}"
        if estimated_seconds:
            minutes = estimated_seconds / 60
            message += f" (estimated: {minutes:.1f} minutes)"

        self.update(message, ProgressStage.STARTED)

    def update(self, message: str, stage: ProgressStage = ProgressStage.IN_PROGRESS) -> None:
        """
        Update progress with stage indicator.

        Args:
            message: Progress message
            stage: Current stage

        Example:
            >>> progress.update("Provisioning resources", ProgressStage.IN_PROGRESS)
        """
        # Record update
        update = ProgressUpdate(
            stage=stage,
            message=message,
            timestamp=time.time(),
            operation=self.current_operation or "unknown",
        )
        self.updates.append(update)

        # Format and print
        formatted = self._format_update(update)
        self._print(formatted)

    def complete(self, success: bool = True, message: Optional[str] = None) -> None:
        """
        Mark operation complete.

        Args:
            success: Whether operation succeeded
            message: Optional completion message

        Example:
            >>> progress.complete(success=True, message="VM created successfully")
        """
        if success:
            stage = ProgressStage.COMPLETED
            default_message = f"{self.current_operation} completed"
        else:
            stage = ProgressStage.FAILED
            default_message = f"{self.current_operation} failed"

        final_message = message or default_message

        # Add elapsed time
        if self.start_time:
            elapsed = time.time() - self.start_time
            final_message += f" ({self._format_duration(elapsed)})"

        self.update(final_message, stage)

        # Reset
        self.current_operation = None
        self.start_time = None

    def _format_update(self, update: ProgressUpdate) -> str:
        """
        Format progress update for display.

        Args:
            update: Progress update to format

        Returns:
            str: Formatted message
        """
        # Get symbol for stage
        symbols = self.SYMBOLS if self.use_unicode else self.ASCII_SYMBOLS
        symbol = symbols.get(update.stage, "")

        # Format message
        return f"{symbol} {update.message}"

    def _format_duration(self, seconds: float) -> str:
        """
        Format duration in human-readable format.

        Args:
            seconds: Duration in seconds

        Returns:
            str: Formatted duration (e.g., "2m 30s")
        """
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"

    def _print(self, message: str) -> None:
        """
        Print message to output file.

        Args:
            message: Message to print

        Security: Uses print() with explicit file parameter
        """
        print(message, file=self.output_file, flush=True)

    def get_updates(self) -> list[ProgressUpdate]:
        """
        Get all progress updates.

        Returns:
            list: All progress updates recorded

        Example:
            >>> updates = progress.get_updates()
            >>> for update in updates:
            ...     print(update.message)
        """
        return self.updates.copy()
