"""Background Cache Refresh Module - Detached subprocess for cache warming.

Philosophy:
- Detached subprocess that survives CLI exit
- File-based locking to prevent duplicate refreshes
- Cross-platform (Unix fcntl + Windows msvcrt fallback)
- JSON serialization for context data
- Graceful error handling (never impact user)

Public API (the "studs"):
    BackgroundCacheRefresh: Background cache refresh manager
    trigger_background_refresh: Trigger background cache refresh (non-blocking)
    is_refresh_running: Check if refresh is currently running

Architecture:
- Lock file: ~/.azlin/cache_refresh.lock
- Lock timeout: 300s (5 min max)
- Uses query_all_contexts_parallel() to refresh
- Logs to standard logging (for debugging)

Usage:
    # Trigger background refresh after VM list
    >>> trigger_background_refresh(contexts)

    # Or run standalone
    $ python -m azlin.cache.background_refresh
"""

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BackgroundRefreshError(Exception):
    """Raised when background refresh operations fail."""

    pass


class BackgroundCacheRefresh:
    """Background cache refresh manager with file-based locking.

    Provides detached subprocess execution for cache warming without
    blocking the main CLI process. Uses file-based locking to prevent
    duplicate refresh operations.

    Lock Mechanism:
    - Lock file: ~/.azlin/cache_refresh.lock
    - Lock timeout: 300s (5 minutes)
    - Cross-platform (Unix fcntl + Windows msvcrt)

    Example:
        >>> refresh = BackgroundCacheRefresh()
        >>> if refresh.trigger_refresh(contexts):
        ...     print("Background refresh started")
        ... else:
        ...     print("Refresh already running")
    """

    DEFAULT_LOCK_FILE = Path.home() / ".azlin" / "cache_refresh.lock"
    LOCK_TIMEOUT = 300  # 5 minutes

    def __init__(self, lock_file: Path | None = None, lock_timeout: int | None = None):
        """Initialize background cache refresh.

        Args:
            lock_file: Custom lock file path (default: ~/.azlin/cache_refresh.lock)
            lock_timeout: Lock timeout in seconds (default: 300 = 5min)
        """
        self.lock_file = lock_file or self.DEFAULT_LOCK_FILE
        self.lock_timeout = lock_timeout or self.LOCK_TIMEOUT

    def _ensure_lock_dir(self) -> None:
        """Ensure lock file directory exists.

        Raises:
            BackgroundRefreshError: If directory creation fails
        """
        try:
            self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise BackgroundRefreshError(f"Failed to create lock directory: {e}") from e

    def _acquire_lock(self) -> bool:
        """Acquire lock file using cross-platform file locking.

        Returns:
            True if lock acquired, False if already locked

        Raises:
            BackgroundRefreshError: If lock acquisition fails
        """
        try:
            self._ensure_lock_dir()

            # Check if lock file exists and is stale
            if self.lock_file.exists():
                try:
                    stat = self.lock_file.stat()
                    age = time.time() - stat.st_mtime

                    if age > self.lock_timeout:
                        # Stale lock - remove it
                        logger.debug(f"Removing stale lock file (age: {age:.0f}s)")
                        self.lock_file.unlink()
                    else:
                        # Lock is still fresh
                        logger.debug(f"Lock file exists (age: {age:.0f}s), refresh already running")
                        return False
                except Exception as e:
                    logger.warning(f"Failed to check lock file: {e}")
                    return False

            # Try to create lock file
            try:
                # Open with exclusive creation (fails if exists)
                fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)

                # Write PID to lock file
                lock_data = {"pid": os.getpid(), "timestamp": time.time()}
                os.write(fd, json.dumps(lock_data).encode())
                os.close(fd)

                logger.debug(f"Lock acquired: {self.lock_file}")
                return True

            except FileExistsError:
                # Another process created lock between our check and creation
                logger.debug("Lock acquired by another process")
                return False

        except Exception as e:
            raise BackgroundRefreshError(f"Failed to acquire lock: {e}") from e

    def _release_lock(self) -> None:
        """Release lock file.

        Raises:
            BackgroundRefreshError: If lock release fails
        """
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
                logger.debug(f"Lock released: {self.lock_file}")
        except Exception as e:
            raise BackgroundRefreshError(f"Failed to release lock: {e}") from e

    def is_refresh_running(self) -> bool:
        """Check if refresh is currently running.

        Returns:
            True if refresh is running, False otherwise
        """
        if not self.lock_file.exists():
            return False

        try:
            stat = self.lock_file.stat()
            age = time.time() - stat.st_mtime

            # If lock is older than timeout, consider it stale
            if age > self.lock_timeout:
                logger.debug(f"Lock file is stale (age: {age:.0f}s)")
                return False

            return True
        except Exception as e:
            logger.warning(f"Failed to check lock file: {e}")
            return False

    def trigger_refresh(self, contexts_data: list[dict[str, Any]]) -> bool:
        """Trigger background cache refresh in detached subprocess.

        Args:
            contexts_data: List of context dictionaries (JSON-serializable)

        Returns:
            True if refresh started, False if already running

        Raises:
            BackgroundRefreshError: If subprocess launch fails
        """
        # Check if refresh is already running
        if self.is_refresh_running():
            logger.debug("Background refresh already running, skipping")
            return False

        # Try to acquire lock
        if not self._acquire_lock():
            logger.debug("Failed to acquire lock, refresh may be starting")
            return False

        try:
            # Create temp file with context data
            temp_file = self.lock_file.parent / "refresh_contexts.json"
            with open(temp_file, "w") as f:
                json.dump(contexts_data, f)

            # Launch detached subprocess
            # Use subprocess.Popen with detachment flags
            if sys.platform == "win32":
                # Windows: Use DETACHED_PROCESS
                creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                subprocess.Popen(
                    [sys.executable, "-m", "azlin.cache.background_refresh", str(temp_file)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creation_flags,
                    close_fds=True,
                )
            else:
                # Unix: Use double-fork to detach
                subprocess.Popen(
                    [sys.executable, "-m", "azlin.cache.background_refresh", str(temp_file)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,  # Detach from parent session
                    close_fds=True,
                )

            logger.debug(f"Background refresh started (contexts: {len(contexts_data)})")
            return True

        except Exception as e:
            # Release lock on error
            self._release_lock()
            raise BackgroundRefreshError(f"Failed to start background refresh: {e}") from e

    def _run_refresh(self, contexts_data: list[dict[str, Any]]) -> None:
        """Run cache refresh operation.

        This method is called by the detached subprocess to perform
        the actual cache refresh operation.

        Args:
            contexts_data: List of context dictionaries

        Raises:
            BackgroundRefreshError: If refresh fails
        """
        try:
            # Import here to avoid circular dependencies

            from azlin.context_manager import Context
            from azlin.multi_context_list_async import query_all_contexts_parallel

            # Convert context dictionaries back to Context objects
            contexts = []
            for ctx_data in contexts_data:
                try:
                    # Basic reconstruction - just enough for cache refresh
                    ctx = Context(
                        name=ctx_data.get("name", "unknown"),
                        subscription_id=ctx_data.get("subscription_id", ""),
                        tenant_id=ctx_data.get("tenant_id", ""),
                    )
                    contexts.append(ctx)
                except Exception as e:
                    logger.warning(f"Failed to reconstruct context: {e}")
                    continue

            if not contexts:
                logger.warning("No valid contexts to refresh")
                return

            # Run parallel query to warm cache
            logger.debug(f"Starting cache refresh for {len(contexts)} contexts")
            start_time = time.time()

            result = query_all_contexts_parallel(contexts)

            duration = time.time() - start_time
            logger.info(
                f"Cache refresh complete: {result.total_vms} VMs across "
                f"{len(result.context_results)} contexts in {duration:.2f}s"
            )

        except Exception as e:
            logger.error(f"Background refresh failed: {e}")
            raise BackgroundRefreshError(f"Refresh execution failed: {e}") from e


def trigger_background_refresh(contexts: list[Any]) -> bool:
    """Trigger background cache refresh (non-blocking).

    Args:
        contexts: List of Context objects to refresh

    Returns:
        True if refresh started, False if already running
    """
    try:
        # Convert contexts to JSON-serializable format
        contexts_data = []
        for ctx in contexts:
            try:
                ctx_data = {
                    "name": getattr(ctx, "name", "unknown"),
                    "subscription_id": getattr(ctx, "subscription_id", ""),
                    "tenant_id": getattr(ctx, "tenant_id", ""),
                }
                contexts_data.append(ctx_data)
            except Exception as e:
                logger.warning(f"Failed to serialize context: {e}")
                continue

        if not contexts_data:
            logger.warning("No valid contexts to refresh")
            return False

        refresh = BackgroundCacheRefresh()
        return refresh.trigger_refresh(contexts_data)

    except Exception as e:
        logger.warning(f"Failed to trigger background refresh: {e}")
        return False


def is_refresh_running() -> bool:
    """Check if background refresh is currently running.

    Returns:
        True if refresh is running, False otherwise
    """
    try:
        refresh = BackgroundCacheRefresh()
        return refresh.is_refresh_running()
    except Exception as e:
        logger.warning(f"Failed to check refresh status: {e}")
        return False


def _main() -> None:
    """Main entry point for standalone background refresh execution.

    Usage:
        $ python -m azlin.cache.background_refresh
        $ python -m azlin.cache.background_refresh /path/to/contexts.json
    """
    # Configure logging for background process
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        # Get contexts file from args
        if len(sys.argv) > 1:
            contexts_file = Path(sys.argv[1])
            if not contexts_file.exists():
                logger.error(f"Contexts file not found: {contexts_file}")
                sys.exit(1)

            # Load contexts
            with open(contexts_file) as f:
                contexts_data = json.load(f)

            # Run refresh
            refresh = BackgroundCacheRefresh()
            try:
                refresh._run_refresh(contexts_data)
            finally:
                # Always release lock
                refresh._release_lock()

                # Cleanup temp file
                try:
                    contexts_file.unlink()
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp file: {e}")

        else:
            logger.error("Usage: python -m azlin.cache.background_refresh <contexts.json>")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Background refresh failed: {e}")
        sys.exit(1)


# Support standalone execution
if __name__ == "__main__":
    _main()


__all__ = [
    "BackgroundCacheRefresh",
    "BackgroundRefreshError",
    "is_refresh_running",
    "trigger_background_refresh",
]
