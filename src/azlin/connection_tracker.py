"""Connection tracker for VM usage tracking.

Tracks last connection time for each VM in ~/.azlin/connections.toml.
Used by prune command to identify idle VMs.
"""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import tomli  # type: ignore[import]
except ImportError:
    try:
        import tomllib as tomli  # type: ignore[import]
    except ImportError as e:
        raise ImportError("toml library not available. Install with: pip install tomli") from e

try:
    import tomli_w
except ImportError as e:
    raise ImportError("tomli-w library not available. Install with: pip install tomli-w") from e

logger = logging.getLogger(__name__)


class ConnectionTrackerError(Exception):
    """Raised when connection tracking operations fail."""

    pass


class ConnectionTracker:
    """Track VM connection times in ~/.azlin/connections.toml."""

    DEFAULT_CONNECTIONS_DIR = Path.home() / ".azlin"
    DEFAULT_CONNECTIONS_FILE = DEFAULT_CONNECTIONS_DIR / "connections.toml"

    @classmethod
    def ensure_connections_dir(cls) -> Path:
        """Ensure connections directory exists with secure permissions (0700)."""
        try:
            cls.DEFAULT_CONNECTIONS_DIR.mkdir(parents=True, exist_ok=True)
            os.chmod(cls.DEFAULT_CONNECTIONS_DIR, 0o700)
            return cls.DEFAULT_CONNECTIONS_DIR
        except Exception as e:
            raise ConnectionTrackerError(f"Failed to create connections directory: {e}") from e

    @classmethod
    def load_connections(cls) -> dict[str, dict[str, Any]]:
        """Load connection data from file, returns empty dict if not found."""
        connections_path = cls.DEFAULT_CONNECTIONS_FILE

        if not connections_path.exists():
            return {}

        try:
            # Verify and fix file permissions if needed
            stat = connections_path.stat()
            mode = stat.st_mode & 0o777
            if mode & 0o077:
                logger.warning(f"Fixing insecure permissions on {connections_path}")
                os.chmod(connections_path, 0o600)

            with open(connections_path, "rb") as f:
                return tomli.load(f)  # type: ignore[attr-defined]

        except Exception as e:
            logger.warning(f"Failed to load connections file: {e}")
            return {}

    @classmethod
    def save_connections(cls, connections: dict[str, dict[str, Any]]) -> None:
        """Save connection data to file atomically with secure permissions."""
        temp_path: Path | None = None
        try:
            cls.ensure_connections_dir()
            connections_path = cls.DEFAULT_CONNECTIONS_FILE
            temp_path = connections_path.with_suffix(".tmp")

            with open(temp_path, "wb") as f:
                tomli_w.dump(connections, f)

            os.chmod(temp_path, 0o600)
            temp_path.replace(connections_path)

        except Exception as e:
            if temp_path and temp_path.exists():
                temp_path.unlink()
            raise ConnectionTrackerError(f"Failed to save connections: {e}") from e

    @classmethod
    def record_connection(cls, vm_name: str, timestamp: datetime | None = None) -> None:
        """Record connection timestamp for a VM (defaults to now)."""
        if timestamp is None:
            timestamp = datetime.now(UTC)

        try:
            connections = cls.load_connections()
            connections[vm_name] = {"last_connected": timestamp.isoformat() + "Z"}
            cls.save_connections(connections)
        except Exception as e:
            raise ConnectionTrackerError(f"Failed to record connection: {e}") from e

    @classmethod
    def get_last_connection(cls, vm_name: str) -> datetime | None:
        """Get last connection timestamp for a VM, or None if never connected."""
        try:
            connections = cls.load_connections()
            last_connected_str = connections.get(vm_name, {}).get("last_connected")
            if not last_connected_str:
                return None
            return datetime.fromisoformat(last_connected_str.replace("Z", "+00:00"))
        except Exception as e:
            logger.warning(f"Failed to get last connection for {vm_name}: {e}")
            return None

    @classmethod
    def get_all_connections(cls) -> dict[str, datetime]:
        """Get all connection timestamps as dict[vm_name, datetime]."""
        try:
            connections = cls.load_connections()
            result = {}
            for vm_name, data in connections.items():
                last_connected_str = data.get("last_connected")
                if last_connected_str:
                    try:
                        result[vm_name] = datetime.fromisoformat(
                            last_connected_str.replace("Z", "+00:00")
                        )
                    except Exception as e:
                        logger.warning(f"Failed to parse timestamp for {vm_name}: {e}")
            return result  # type: ignore[return-value]
        except Exception as e:
            logger.warning(f"Failed to get all connections: {e}")
            return {}

    @classmethod
    def remove_connection(cls, vm_name: str) -> bool:
        """Remove connection record for a VM, returns True if removed."""
        try:
            connections = cls.load_connections()
            if vm_name not in connections:
                return False
            del connections[vm_name]
            cls.save_connections(connections)
            return True
        except Exception as e:
            logger.warning(f"Failed to remove connection for {vm_name}: {e}")
            return False


__all__ = ["ConnectionTracker", "ConnectionTrackerError"]
