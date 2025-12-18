"""Cross-platform file locking for concurrent audit log access.

This module provides atomic file locking to prevent race conditions when multiple
azlin processes write to the audit log simultaneously. It eliminates false "AUDIT
LOG TAMPERING" warnings that occurred during concurrent operations.

Philosophy:
- Standard library only (fcntl/msvcrt are standard library)
- Cross-platform support (Unix/Windows)
- Exponential backoff for contention handling
- Context manager for automatic cleanup
- Self-contained and regeneratable

Public API:
    acquire_file_lock: Context manager for acquiring exclusive file lock
    LockTimeoutError: Exception raised when lock cannot be acquired within timeout

Example:
    >>> from azlin.file_lock_manager import acquire_file_lock
    >>> from pathlib import Path
    >>>
    >>> audit_log = Path("~/.azlin/audit.log").expanduser()
    >>> with acquire_file_lock(audit_log, timeout=5.0, operation="audit logging"):
    ...     # Only this process can write to the file
    ...     with open(audit_log, "a") as f:
    ...         f.write("audit entry\\n")
    ...     # Lock automatically released on exit

Concurrency:
- Supports 10+ concurrent processes
- Each process waits its turn (no data corruption)
- Exponential backoff: 0.1s → 0.2s → 0.4s → 0.8s → 1.6s
"""

import platform
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, TextIO

# Platform-specific imports
_system = platform.system()
if TYPE_CHECKING or _system == "Windows":
    import msvcrt  # type: ignore[import-not-found]
if TYPE_CHECKING or _system != "Windows":
    import fcntl  # type: ignore[import-not-found]


__all__ = ["LockTimeoutError", "acquire_file_lock"]


class LockTimeoutError(Exception):
    """Raised when file lock cannot be acquired within timeout period."""


@contextmanager
def acquire_file_lock(
    file_path: Path,
    timeout: float = 5.0,
    operation: str = "file operation",
) -> Generator[None, None, None]:
    """Acquire exclusive file lock with exponential backoff.

    This context manager acquires an exclusive lock on the specified file,
    blocking other processes from accessing it until the lock is released.
    Uses platform-appropriate locking mechanism:
    - Unix/macOS/Linux: fcntl.flock() (advisory whole-file lock)
    - Windows: msvcrt.locking() (mandatory byte-range lock)

    Args:
        file_path: Path to file to lock
        timeout: Maximum seconds to wait for lock acquisition (default: 5.0)
        operation: Description of operation (used in error messages)

    Yields:
        None (lock is held within context)

    Raises:
        FileNotFoundError: If file does not exist
        PermissionError: If lacking permissions to lock file
        LockTimeoutError: If lock cannot be acquired within timeout

    Example:
        >>> from pathlib import Path
        >>> audit_log = Path("~/.azlin/audit.log").expanduser()
        >>> with acquire_file_lock(audit_log, timeout=5.0):
        ...     # Write to file safely
        ...     with open(audit_log, "a") as f:
        ...         f.write("entry\\n")
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File does not exist: {file_path}")

    # Open file for locking (mode 'a' for append - ensures file exists and is writable)
    # Note: We don't actually write through this handle, just use it for locking
    with open(file_path, "a") as file_handle:
        try:
            # Acquire lock with exponential backoff
            _acquire_lock_with_backoff(file_handle, file_path, timeout, operation)

            # Lock acquired - yield control to caller
            yield

        finally:
            # Always release lock
            _release_lock(file_handle)


def _acquire_lock_with_backoff(
    file_handle: TextIO | BinaryIO,
    file_path: Path,
    timeout: float,
    operation: str,
) -> None:
    """Acquire file lock with exponential backoff strategy.

    Attempts to acquire lock with increasing delays between retries:
    0.1s → 0.2s → 0.4s → 0.8s → 1.6s → ...

    Args:
        file_handle: Open file handle
        file_path: Path to file (for error messages)
        timeout: Maximum seconds to wait
        operation: Operation description (for error messages)

    Raises:
        LockTimeoutError: If lock cannot be acquired within timeout
        PermissionError: If lacking permissions to lock file
    """
    start_time = time.time()
    delay = 0.1  # Initial backoff delay
    attempt = 0

    while True:
        elapsed = time.time() - start_time

        # Check if timeout exceeded
        if elapsed >= timeout:
            raise LockTimeoutError(
                f"Failed to acquire file lock for {operation} after {timeout} seconds. "
                f"File: {file_path}. Another process may be holding the lock."
            )

        try:
            # Try to acquire lock (platform-specific)
            if _system == "Windows":
                _acquire_lock_windows(file_handle)
            else:
                _acquire_lock_unix(file_handle)

            # Lock acquired successfully
            return

        except (BlockingIOError, PermissionError) as e:
            # Lock is held by another process - retry with backoff
            if isinstance(e, PermissionError) and attempt == 0:
                # First permission error might be genuine permission issue
                raise

            # Wait before retry (capped at timeout)
            remaining = timeout - elapsed
            sleep_time = min(delay, remaining)

            if sleep_time > 0:
                time.sleep(sleep_time)

            # Exponential backoff: double delay for next attempt
            delay = min(delay * 2, 2.0)  # Cap at 2 seconds
            attempt += 1


def _acquire_lock_unix(file_handle: TextIO | BinaryIO) -> None:
    """Acquire file lock on Unix systems using fcntl.

    Args:
        file_handle: Open file handle

    Raises:
        BlockingIOError: If lock is held by another process
    """
    fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _acquire_lock_windows(file_handle: TextIO | BinaryIO) -> None:
    """Acquire file lock on Windows using msvcrt.

    Args:
        file_handle: Open file handle

    Raises:
        PermissionError: If lock is held by another process
    """
    # Lock first byte of file (mandatory lock)
    msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]


def _release_lock(file_handle: TextIO | BinaryIO) -> None:
    """Release file lock (platform-specific).

    Args:
        file_handle: Open file handle with active lock
    """
    try:
        if _system == "Windows":
            # Unlock first byte
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
        else:
            # Unlock file
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        # Ignore errors during unlock (file may already be closed)
        # Debug logging helps diagnose lock cleanup issues
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(f"Error during lock cleanup: {e}")
