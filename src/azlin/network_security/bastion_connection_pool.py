"""Bastion Connection Pool for tunnel reuse and resource management.

Manages a pool of reusable Bastion tunnels to optimize connection performance
and prevent resource exhaustion.

Key features:
- Tunnel reuse (15s → <1s for repeat connections)
- Idle timeout cleanup
- Connection limits (prevent port exhaustion)
- Health monitoring
- Thread-safe operations

Philosophy:
- Performance through reuse
- Resource limits prevent DoS
- Graceful degradation on failures
- Autonomous cleanup

Public API:
    BastionConnectionPool: Main pool manager
    PooledTunnel: Tunnel with pool metadata
    BastionCleanupDaemon: Background cleanup thread

Example:
    >>> pool = BastionConnectionPool(bastion_manager)
    >>> pooled = pool.get_or_create_tunnel("bastion1", "rg1", "vm-id", 22)
    >>> # Reuse same tunnel later (fast!)
    >>> pooled = pool.get_or_create_tunnel("bastion1", "rg1", "vm-id", 22)
"""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Raised when a security violation is detected in tunnel configuration."""

    pass


@dataclass
class PooledTunnel:
    """Tunnel with pool management metadata.

    Wraps a BastionTunnel with additional tracking for pool management including
    creation time, last use time, use count, and idle timeout.
    """

    tunnel: Any  # BastionTunnel from bastion_manager
    created_at: datetime
    last_used: datetime
    use_count: int = 0
    idle_timeout: int = 300  # 5 minutes default

    def is_expired(self) -> bool:
        """Check if tunnel exceeded idle timeout.

        Returns:
            True if tunnel has been idle longer than idle_timeout
        """
        idle_seconds = (datetime.now() - self.last_used).total_seconds()
        return idle_seconds > self.idle_timeout

    def is_healthy(self, manager: Any) -> bool:
        """Verify tunnel is still active and healthy.

        Args:
            manager: BastionManager instance to check health

        Returns:
            True if tunnel is healthy, False otherwise
        """
        return manager.check_tunnel_health(self.tunnel)


class BastionConnectionPool:
    """Manage pool of reusable Bastion tunnels.

    Features:
    - Tunnel reuse based on (bastion, vm, remote_port) key
    - Idle timeout cleanup
    - Connection limits
    - Health monitoring
    - Thread-safe operations

    The pool significantly improves performance by reusing tunnels:
    - First connection: ~15 seconds (tunnel creation)
    - Repeat connection: <1 second (reuse from pool)
    """

    DEFAULT_MAX_TUNNELS = 10
    DEFAULT_IDLE_TIMEOUT = 300  # 5 minutes

    def __init__(
        self,
        bastion_manager: Any,
        max_tunnels: int = DEFAULT_MAX_TUNNELS,
        idle_timeout: int = DEFAULT_IDLE_TIMEOUT,
    ):
        """Initialize connection pool.

        Args:
            bastion_manager: BastionManager instance for tunnel operations
            max_tunnels: Maximum number of tunnels to keep in pool
            idle_timeout: Seconds before idle tunnel is evicted
        """
        self.manager = bastion_manager
        self.max_tunnels = max_tunnels
        self.idle_timeout = idle_timeout
        self.pool: dict[tuple[str, str, int], PooledTunnel] = {}
        self._lock = threading.Lock()

    def get_or_create_tunnel(
        self,
        bastion_name: str,
        resource_group: str,
        target_vm_id: str,
        remote_port: int = 22,
    ) -> PooledTunnel:
        """Get existing tunnel from pool or create new one.

        This is the main entry point for getting tunnels. It implements the
        tunnel reuse logic:

        1. Check pool for existing tunnel with matching key
        2. Verify tunnel is healthy
        3. If healthy, update last_used and return (FAST PATH)
        4. If unhealthy or missing, create new tunnel
        5. Enforce max_tunnels limit (evict oldest idle tunnel if needed)

        Args:
            bastion_name: Bastion host name
            resource_group: Resource group name
            target_vm_id: Full Azure VM resource ID
            remote_port: Remote port on VM (default 22 for SSH)

        Returns:
            PooledTunnel that is ready to use

        Raises:
            BastionManagerError: If tunnel creation fails
        """
        with self._lock:
            key = (bastion_name, target_vm_id, remote_port)

            # Check if pool is disabled (force new tunnels)
            import os
            pool_disabled = os.environ.get("AZLIN_DISABLE_BASTION_POOL") == "1"

            # Only check pool if not disabled
            if not pool_disabled and key in self.pool:
                pooled = self.pool[key]

                # Verify health
                if pooled.is_healthy(self.manager):
                    # FAST PATH: Reuse healthy tunnel
                    pooled.last_used = datetime.now()
                    pooled.use_count += 1
                    logger.info(
                        f"Reusing tunnel {key} (use_count={pooled.use_count}, "
                        f"age={(datetime.now() - pooled.created_at).total_seconds():.0f}s)"
                    )
                    return pooled
                # Unhealthy - remove and recreate
                logger.warning(f"Tunnel {key} unhealthy, recreating")
                self.manager.close_tunnel(pooled.tunnel)
                del self.pool[key]

            # Create new tunnel (SLOW PATH or pool disabled)
            if pool_disabled:
                logger.info(f"Pool disabled - creating fresh tunnel for {target_vm_id[:50]}...")
            if len(self.pool) >= self.max_tunnels:
                self._evict_idle_tunnel()

            local_port = self.manager.get_available_port()
            tunnel = self.manager.create_tunnel(
                bastion_name=bastion_name,
                resource_group=resource_group,
                target_vm_id=target_vm_id,
                local_port=local_port,
                remote_port=remote_port,
            )

            # SECURITY: Verify tunnel is bound to localhost only
            self._validate_localhost_binding(tunnel)

            now = datetime.now()
            pooled = PooledTunnel(
                tunnel=tunnel,
                created_at=now,
                last_used=now,
                use_count=0,
                idle_timeout=self.idle_timeout,
            )

            self.pool[key] = pooled
            logger.info(f"Created new tunnel {key} (pool_size={len(self.pool)})")
            return pooled

    def _evict_idle_tunnel(self) -> None:
        """Evict oldest idle tunnel to make room for new connection.

        This implements the eviction policy: evict the tunnel that has been
        idle the longest (LRU-style eviction).
        """
        if not self.pool:
            return

        # Find oldest by last_used
        oldest_key = min(self.pool.keys(), key=lambda k: self.pool[k].last_used)
        oldest = self.pool[oldest_key]

        idle_seconds = (datetime.now() - oldest.last_used).total_seconds()
        logger.info(
            f"Evicting idle tunnel {oldest_key} "
            f"(idle for {idle_seconds:.0f}s, use_count={oldest.use_count})"
        )

        self.manager.close_tunnel(oldest.tunnel)
        del self.pool[oldest_key]

    def _validate_localhost_binding(self, tunnel: Any) -> None:
        """Verify tunnel is bound to localhost only (security requirement).

        SECURITY CRITICAL: Bastion tunnels MUST bind to localhost (127.0.0.1)
        to prevent network exposure. This method verifies the tunnel's local
        address is localhost.

        Args:
            tunnel: BastionTunnel to validate

        Raises:
            SecurityError: If tunnel is not bound to localhost
        """
        # Get tunnel's local address (should be 127.0.0.1 or localhost)
        local_address = getattr(tunnel, "local_address", "127.0.0.1")

        # Verify it's localhost
        if local_address not in ("127.0.0.1", "localhost", "::1"):
            error_msg = (
                f"SECURITY VIOLATION: Tunnel bound to {local_address} instead of localhost. "
                f"This exposes the tunnel to network access. Tunnel rejected."
            )
            logger.error(error_msg)
            # Close the insecure tunnel immediately
            self.manager.close_tunnel(tunnel)
            raise SecurityError(error_msg)

        logger.debug(f"Tunnel localhost binding verified: {local_address}")

    def cleanup_expired(self) -> int:
        """Remove all expired tunnels from pool.

        This should be called periodically by the cleanup daemon.

        Returns:
            Number of tunnels cleaned up
        """
        with self._lock:
            expired_keys = [key for key, pooled in self.pool.items() if pooled.is_expired()]

            for key in expired_keys:
                pooled = self.pool[key]
                idle_seconds = (datetime.now() - pooled.last_used).total_seconds()
                logger.info(
                    f"Cleaning up expired tunnel {key} "
                    f"(idle for {idle_seconds:.0f}s, use_count={pooled.use_count})"
                )
                self.manager.close_tunnel(pooled.tunnel)
                del self.pool[key]

            return len(expired_keys)

    def close_all(self) -> None:
        """Close all tunnels in pool.

        This should be called on application shutdown.
        """
        with self._lock:
            for key, pooled in self.pool.items():
                logger.info(f"Closing tunnel {key} (use_count={pooled.use_count})")
                self.manager.close_tunnel(pooled.tunnel)
            self.pool.clear()

    def get_stats(self) -> dict[str, int]:
        """Get pool statistics.

        Returns:
            Dictionary with pool statistics
        """
        with self._lock:
            return {
                "total_tunnels": len(self.pool),
                "max_tunnels": self.max_tunnels,
                "total_uses": sum(p.use_count for p in self.pool.values()),
            }


class BastionCleanupDaemon:
    """Background daemon for tunnel maintenance.

    Runs periodic cleanup to remove expired tunnels from the pool.
    This prevents resource leaks from idle tunnels that are no longer needed.
    """

    def __init__(self, pool: BastionConnectionPool, interval: int = 60):
        """Initialize cleanup daemon.

        Args:
            pool: BastionConnectionPool to maintain
            interval: Seconds between cleanup runs (default 60)
        """
        self.pool = pool
        self.interval = interval
        self.running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start cleanup daemon in background thread."""
        if self.running:
            logger.warning("Cleanup daemon already running")
            return

        self.running = True
        self._thread = threading.Thread(
            target=self._cleanup_loop, daemon=True, name="BastionCleanup"
        )
        self._thread.start()
        logger.info(f"Bastion cleanup daemon started (interval={self.interval}s)")

    def stop(self) -> None:
        """Stop cleanup daemon."""
        if not self.running:
            return

        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Bastion cleanup daemon stopped")

    def _cleanup_loop(self) -> None:
        """Periodic cleanup of expired tunnels.

        This runs in a background thread and periodically calls cleanup_expired()
        on the pool to remove idle tunnels.
        """
        while self.running:
            try:
                expired_count = self.pool.cleanup_expired()
                if expired_count > 0:
                    logger.info(f"Cleaned up {expired_count} expired tunnel(s)")
            except Exception as e:
                logger.error(f"Cleanup daemon error: {e}", exc_info=True)

            # Sleep in small intervals so we can stop quickly
            for _ in range(self.interval):
                if not self.running:
                    break
                time.sleep(1)


__all__ = ["BastionCleanupDaemon", "BastionConnectionPool", "PooledTunnel", "SecurityError"]
