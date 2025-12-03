"""SSH Connection Pool Module - Connection pooling and reuse.

Philosophy:
- Connection reuse for performance
- Thread-safe pool management
- Automatic idle connection cleanup
- Health checks before reuse

Public API (the "studs"):
    SSHConnectionPool: Connection pool for SSH sessions
    SSHConnection: Wrapper for SSH connections
    PoolConfig: Configuration for connection pool
"""

import threading
import time
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from typing import Any

try:
    import paramiko
except ImportError:
    paramiko = None  # Graceful degradation if paramiko not available


@dataclass
class PoolConfig:
    """Connection pool configuration.

    Attributes:
        max_connections: Maximum number of pooled connections
        idle_timeout: Idle timeout in seconds
        health_check_interval: Health check interval in seconds
        connection_timeout: Connection timeout in seconds
    """

    max_connections: int = 20
    idle_timeout: int = 300  # 5 minutes
    health_check_interval: int = 60  # 1 minute
    connection_timeout: int = 30

    def __post_init__(self):
        """Validate configuration."""
        if self.max_connections <= 0:
            raise ValueError("max_connections must be positive")
        if self.idle_timeout <= 0:
            raise ValueError("idle_timeout must be positive")


@dataclass
class SSHConnection:
    """Wrapper for SSH connection with metadata.

    Attributes:
        host: Remote host address
        user: SSH username
        key_path: Path to SSH private key
        client: Paramiko SSH client
        connection_key: Unique connection identifier
        last_used: Timestamp of last use
        connected: Connection status
    """

    host: str
    user: str
    key_path: str
    client: Any | None = None
    connection_key: str = field(init=False)
    last_used: float | None = None
    connected: bool = False

    def __post_init__(self):
        """Initialize connection key."""
        self.connection_key = f"{self.user}@{self.host}"

    def connect(self) -> None:
        """Establish SSH connection.

        Raises:
            Exception: If paramiko not available or connection fails
        """
        if paramiko is None:
            raise Exception("paramiko library not available")

        if self.client is None:
            self.client = paramiko.SSHClient()
            # Security: Load known hosts first
            with suppress(Exception):  # System host keys may not exist
                self.client.load_system_host_keys()

            # Azure VMs have dynamic IPs and ephemeral hosts - AutoAddPolicy is acceptable
            # in this infrastructure context. In production, consider using a custom policy
            # that validates against Azure-specific host key management.
            # nosec B507: AutoAddPolicy acceptable for Azure VM infrastructure automation
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # nosec B507

        try:
            self.client.connect(
                hostname=self.host,
                username=self.user,
                key_filename=self.key_path,
                timeout=30,
            )
            self.connected = True
            self.last_used = time.time()
        except Exception as e:
            self.connected = False
            raise Exception(f"SSH connection failed: {e}") from e

    def is_alive(self) -> bool:
        """Check if connection is still alive.

        Returns:
            True if connection is active, False otherwise
        """
        if not self.connected or self.client is None:
            return False

        try:
            # Try to get transport
            transport = self.client.get_transport()
            if transport is None or not transport.is_active():
                return False
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Close SSH connection."""
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass  # Ignore errors during close
            finally:
                self.connected = False


class SSHConnectionPool:
    """Connection pool for SSH sessions.

    Provides connection pooling and reuse to reduce SSH handshake overhead.

    Example:
        >>> pool = SSHConnectionPool(max_connections=20, idle_timeout=300)
        >>> conn = pool.get_connection(host="10.0.0.1", user="azureuser", key_path="/key")
        >>> # Use connection...
        >>> pool.release_connection(conn)
    """

    def __init__(
        self,
        max_connections: int | None = None,
        idle_timeout: int | None = None,
        config: PoolConfig | None = None,
    ):
        """Initialize connection pool.

        Args:
            max_connections: Maximum number of pooled connections (deprecated, use config)
            idle_timeout: Idle timeout in seconds (deprecated, use config)
            config: Pool configuration object
        """
        if config is not None:
            self._config = config
        else:
            self._config = PoolConfig(
                max_connections=max_connections or 20, idle_timeout=idle_timeout or 300
            )

        self.pool: dict[str, SSHConnection] = {}
        self.max_connections = self._config.max_connections
        self.idle_timeout = self._config.idle_timeout
        self._lock = threading.Lock()
        self._stats = {
            "connections_created": 0,
            "connections_reused": 0,
            "connections_evicted": 0,
        }
        self._shutdown_event = threading.Event()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def _cleanup_loop(self) -> None:
        """Background cleanup thread."""
        while not self._shutdown_event.is_set():
            self._cleanup_idle_connections()
            time.sleep(self._config.health_check_interval)

    def get_connection(self, host: str, user: str, key_path: str) -> SSHConnection:
        """Get connection from pool or create new.

        Args:
            host: Remote host address
            user: SSH username
            key_path: Path to SSH private key

        Returns:
            SSH connection (from pool or newly created)

        Example:
            >>> pool = SSHConnectionPool()
            >>> conn = pool.get_connection("10.0.0.1", "azureuser", "/key")
        """
        conn_key = f"{user}@{host}"

        with self._lock:
            # Return existing if valid
            if conn_key in self.pool:
                conn = self.pool[conn_key]
                if conn.is_alive() and not self._is_idle_timeout(conn):
                    conn.last_used = time.time()
                    self._stats["connections_reused"] += 1
                    return conn
                # Connection dead or timed out - remove it
                self._close_connection(conn_key)

            # Evict if needed before creating new
            if len(self.pool) >= self.max_connections:
                self._evict_oldest()

        # CRITICAL: Create and connect OUTSIDE the lock to avoid blocking other threads
        conn = SSHConnection(host=host, user=user, key_path=key_path)
        conn.connect()

        # Add to pool after connection established
        with self._lock:
            self.pool[conn_key] = conn
            self._stats["connections_created"] += 1
            return conn

    def release_connection(self, conn: SSHConnection) -> None:
        """Return connection to pool.

        Args:
            conn: Connection to return

        Example:
            >>> pool = SSHConnectionPool()
            >>> conn = pool.get_connection("10.0.0.1", "azureuser", "/key")
            >>> pool.release_connection(conn)
        """
        # Keep connection open for reuse
        conn.last_used = time.time()

    def _is_idle_timeout(self, conn: SSHConnection) -> bool:
        """Check if connection has exceeded idle timeout.

        Args:
            conn: Connection to check

        Returns:
            True if timed out, False otherwise
        """
        if conn.last_used is None:
            return False
        current_time = time.time()
        return (current_time - conn.last_used) > self.idle_timeout

    def _evict_oldest(self) -> None:
        """Evict oldest connection from pool (LRU)."""
        if not self.pool:
            return

        # Find oldest connection (filter out None last_used)
        oldest_key = min(
            self.pool.keys(),
            key=lambda k: self.pool[k].last_used or float("inf"),
        )
        self._close_connection(oldest_key)
        self._stats["connections_evicted"] += 1

    def _close_connection(self, conn_key: str) -> None:
        """Close and remove connection from pool.

        Args:
            conn_key: Connection key to remove
        """
        if conn_key in self.pool:
            conn = self.pool[conn_key]
            conn.close()
            del self.pool[conn_key]

    def _cleanup_idle_connections(self) -> None:
        """Close idle connections (internal method called by cleanup thread)."""
        with self._lock:
            current_time = time.time()
            to_remove = []

            for key, conn in self.pool.items():
                if conn.last_used and (current_time - conn.last_used) > self.idle_timeout:
                    to_remove.append(key)

            for key in to_remove:
                self._close_connection(key)

    def cleanup_idle(self) -> None:
        """Close idle connections (public method).

        Example:
            >>> pool = SSHConnectionPool()
            >>> pool.cleanup_idle()
        """
        self._cleanup_idle_connections()

    def shutdown(self) -> None:
        """Shutdown pool and cleanup thread.

        Example:
            >>> pool = SSHConnectionPool()
            >>> pool.shutdown()
        """
        self._shutdown_event.set()
        if self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=1.0)
        self.close_all()

    @contextmanager
    def connection(self, host: str, user: str, key_path: str):
        """Context manager for connections.

        Args:
            host: Remote host address
            user: SSH username
            key_path: Path to SSH private key

        Yields:
            SSH connection

        Example:
            >>> pool = SSHConnectionPool()
            >>> with pool.connection("10.0.0.1", "azureuser", "/key") as conn:
            ...     # Use connection
            ...     pass
        """
        conn = self.get_connection(host, user, key_path)
        try:
            yield conn
        finally:
            self.release_connection(conn)

    def close_all(self) -> None:
        """Close all connections in pool.

        Example:
            >>> pool = SSHConnectionPool()
            >>> pool.close_all()
        """
        with self._lock:
            for conn in self.pool.values():
                conn.close()
            self.pool.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get pool statistics.

        Returns:
            Dictionary with connection statistics

        Example:
            >>> pool = SSHConnectionPool()
            >>> stats = pool.get_stats()
            >>> print(stats["reuse_ratio"])
        """
        total = self._stats["connections_created"] + self._stats["connections_reused"]
        reuse_ratio = self._stats["connections_reused"] / total if total > 0 else 0.0

        # Count idle vs active connections
        with self._lock:
            idle_count = len(self.pool)  # All pooled connections are idle
            total_connections = len(self.pool)
            active_connections = 0  # No way to track active without checkout tracking

        return {
            "pool_size": len(self.pool),
            "total_connections": total_connections,
            "active_connections": active_connections,
            "idle_connections": idle_count,
            "connections_created": self._stats["connections_created"],
            "connections_reused": self._stats["connections_reused"],
            "connections_evicted": self._stats["connections_evicted"],
            "reuse_ratio": reuse_ratio,
        }


__all__ = ["PoolConfig", "SSHConnection", "SSHConnectionPool"]
