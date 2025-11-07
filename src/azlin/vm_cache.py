"""VM Session Name Cache Module.

This module provides a TTL-based cache for VM session name mappings.
Reduces Azure API calls during VM connection resolution by caching
session_name -> vm_name mappings for 15 minutes.

Cache file: ~/.azlin/vm_cache.toml
TTL: 15 minutes (900 seconds)

Security:
- Cache file permissions: 0600 (owner read/write only)
- Atomic writes using temporary file
- Path validation
- TTL validation to prevent stale data

Example:
    >>> cache = VMCache()
    >>> cache.set("my-session", "my-vm-name")
    >>> vm_name = cache.get("my-session")  # Returns "my-vm-name" if not expired
    >>> cache.delete("my-session")  # Remove specific entry
    >>> cache.clear()  # Clear all entries
"""

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import tomli
except ImportError:
    try:
        import tomllib as tomli  # type: ignore[import]
    except ImportError as e:
        raise ImportError("toml library not available. Install with: pip install tomli") from e

try:
    import tomlkit  # type: ignore[import]
except ImportError as e:
    raise ImportError("tomlkit library not available. Install with: pip install tomlkit") from e

logger = logging.getLogger(__name__)


class VMCacheError(Exception):
    """Raised when VM cache operations fail."""

    pass


@dataclass
class VMCacheEntry:
    """VM cache entry with TTL.

    Attributes:
        session_name: Session name (key)
        vm_name: VM name (value)
        timestamp: Unix timestamp when entry was created
        ttl: Time-to-live in seconds (default: 900 = 15 minutes)
    """

    session_name: str
    vm_name: str
    timestamp: float
    ttl: int = 900  # 15 minutes

    def is_expired(self) -> bool:
        """Check if cache entry has expired.

        Returns:
            True if entry is older than TTL

        Example:
            >>> entry = VMCacheEntry("session", "vm", time.time(), ttl=60)
            >>> entry.is_expired()  # False (just created)
            >>> time.sleep(61)
            >>> entry.is_expired()  # True (expired after 61 seconds)
        """
        current_time = time.time()
        age = current_time - self.timestamp
        return age > self.ttl

    def to_dict(self) -> dict:
        """Convert to dictionary for TOML serialization.

        Returns:
            Dictionary with vm_name, timestamp, ttl keys

        Example:
            >>> entry = VMCacheEntry("session", "vm", 1234567890.0)
            >>> entry.to_dict()
            {'vm_name': 'vm', 'timestamp': 1234567890.0, 'ttl': 900}
        """
        return {
            "vm_name": self.vm_name,
            "timestamp": self.timestamp,
            "ttl": self.ttl,
        }

    @classmethod
    def from_dict(cls, session_name: str, data: dict) -> "VMCacheEntry":
        """Create from dictionary.

        Args:
            session_name: Session name (key)
            data: Dictionary with vm_name, timestamp, ttl keys

        Returns:
            VMCacheEntry object

        Example:
            >>> data = {'vm_name': 'vm', 'timestamp': 1234567890.0, 'ttl': 900}
            >>> entry = VMCacheEntry.from_dict("session", data)
            >>> entry.session_name
            'session'
        """
        return cls(
            session_name=session_name,
            vm_name=data["vm_name"],
            timestamp=data["timestamp"],
            ttl=data.get("ttl", 900),
        )


class VMCache:
    """Manage VM session name cache.

    Provides TTL-based caching of session_name -> vm_name mappings.
    Cache is stored at ~/.azlin/vm_cache.toml with secure permissions.

    Thread-safety: Not thread-safe. Use external locking if needed.
    """

    DEFAULT_CACHE_DIR = Path.home() / ".azlin"
    DEFAULT_CACHE_FILE = DEFAULT_CACHE_DIR / "vm_cache.toml"
    DEFAULT_TTL = 900  # 15 minutes in seconds

    def __init__(self, cache_path: Path | None = None, ttl: int | None = None):
        """Initialize VM cache.

        Args:
            cache_path: Custom cache file path (default: ~/.azlin/vm_cache.toml)
            ttl: Time-to-live in seconds (default: 900 = 15 minutes)

        Example:
            >>> cache = VMCache()  # Use defaults
            >>> cache = VMCache(ttl=300)  # 5 minute TTL
            >>> cache = VMCache(cache_path=Path("/custom/path/cache.toml"))
        """
        self.cache_path = cache_path or self.DEFAULT_CACHE_FILE
        self.ttl = ttl or self.DEFAULT_TTL

    def _ensure_cache_dir(self) -> None:
        """Ensure cache directory exists with secure permissions.

        Raises:
            VMCacheError: If directory creation fails
        """
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            # Set secure permissions (owner only: rwx------)
            os.chmod(self.cache_path.parent, 0o700)
            logger.debug(f"Cache directory ready: {self.cache_path.parent}")
        except Exception as e:
            raise VMCacheError(f"Failed to create cache directory: {e}") from e

    def _load_cache(self) -> dict[str, VMCacheEntry]:
        """Load cache from file.

        Returns:
            Dictionary of session_name -> VMCacheEntry

        Raises:
            VMCacheError: If loading fails
        """
        if not self.cache_path.exists():
            logger.debug("Cache file does not exist, returning empty cache")
            return {}

        try:
            # Verify file permissions
            stat = self.cache_path.stat()
            mode = stat.st_mode & 0o777

            if mode & 0o077:  # Check if group/other have any permissions
                logger.warning(
                    f"Cache file has insecure permissions: {oct(mode)}. Fixing to 0600..."
                )
                os.chmod(self.cache_path, 0o600)

            # Load TOML
            with open(self.cache_path, "rb") as f:
                data = tomli.load(f)

            # Convert to VMCacheEntry objects
            entries = {}
            for session_name, entry_data in data.items():
                try:
                    entry = VMCacheEntry.from_dict(session_name, entry_data)
                    entries[session_name] = entry
                except Exception as e:
                    logger.warning(f"Skipping invalid cache entry for '{session_name}': {e}")
                    continue

            logger.debug(f"Loaded {len(entries)} cache entries from {self.cache_path}")
            return entries

        except Exception as e:
            logger.warning(f"Failed to load cache, returning empty cache: {e}")
            return {}

    def _save_cache(self, entries: dict[str, VMCacheEntry]) -> None:
        """Save cache to file.

        Args:
            entries: Dictionary of session_name -> VMCacheEntry

        Raises:
            VMCacheError: If saving fails
        """
        temp_path: Path | None = None
        try:
            # Ensure directory exists
            self._ensure_cache_dir()

            # Write TOML with secure permissions
            # Use temporary file and atomic rename for safety
            temp_path = self.cache_path.with_suffix(".tmp")

            # Convert entries to TOML document
            doc = tomlkit.document()
            for session_name, entry in entries.items():
                doc[session_name] = entry.to_dict()

            # Write to temp file
            with open(temp_path, "w") as f:
                tomlkit.dump(doc, f)

            # Set secure permissions before moving
            os.chmod(temp_path, 0o600)

            # Atomic rename
            temp_path.replace(self.cache_path)

            logger.debug(f"Saved {len(entries)} cache entries to {self.cache_path}")

        except Exception as e:
            # Cleanup temp file on error
            if temp_path and temp_path.exists():
                temp_path.unlink()
            raise VMCacheError(f"Failed to save cache: {e}") from e

    def get(self, session_name: str) -> str | None:
        """Get VM name from cache by session name.

        Args:
            session_name: Session name to look up

        Returns:
            VM name if found and not expired, None otherwise

        Example:
            >>> cache = VMCache()
            >>> cache.set("my-session", "my-vm")
            >>> cache.get("my-session")
            'my-vm'
            >>> cache.get("nonexistent")
            None
        """
        try:
            entries = self._load_cache()

            if session_name not in entries:
                logger.debug(f"Cache miss: '{session_name}' not found")
                return None

            entry = entries[session_name]

            # Check if expired
            if entry.is_expired():
                logger.debug(
                    f"Cache expired: '{session_name}' (age: {time.time() - entry.timestamp:.0f}s)"
                )
                # Remove expired entry
                del entries[session_name]
                self._save_cache(entries)
                return None

            logger.debug(f"Cache hit: '{session_name}' -> '{entry.vm_name}'")
            return entry.vm_name

        except Exception as e:
            logger.warning(f"Cache lookup failed for '{session_name}': {e}")
            return None

    def set(self, session_name: str, vm_name: str) -> None:
        """Set VM name in cache for session name.

        Args:
            session_name: Session name (key)
            vm_name: VM name (value)

        Raises:
            VMCacheError: If cache update fails

        Example:
            >>> cache = VMCache()
            >>> cache.set("my-session", "my-vm")
            >>> cache.get("my-session")
            'my-vm'
        """
        try:
            entries = self._load_cache()

            # Create new entry
            entry = VMCacheEntry(
                session_name=session_name,
                vm_name=vm_name,
                timestamp=time.time(),
                ttl=self.ttl,
            )

            # Update cache
            entries[session_name] = entry
            self._save_cache(entries)

            logger.debug(f"Cache set: '{session_name}' -> '{vm_name}' (TTL: {self.ttl}s)")

        except Exception as e:
            raise VMCacheError(f"Failed to set cache entry for '{session_name}': {e}") from e

    def delete(self, session_name: str) -> bool:
        """Delete cache entry for session name.

        Args:
            session_name: Session name to delete

        Returns:
            True if entry was deleted, False if not found

        Example:
            >>> cache = VMCache()
            >>> cache.set("my-session", "my-vm")
            >>> cache.delete("my-session")
            True
            >>> cache.delete("nonexistent")
            False
        """
        try:
            entries = self._load_cache()

            if session_name not in entries:
                logger.debug(f"Cache delete: '{session_name}' not found")
                return False

            del entries[session_name]
            self._save_cache(entries)

            logger.debug(f"Cache deleted: '{session_name}'")
            return True

        except Exception as e:
            logger.warning(f"Cache delete failed for '{session_name}': {e}")
            return False

    def clear(self) -> None:
        """Clear all cache entries.

        Example:
            >>> cache = VMCache()
            >>> cache.set("session1", "vm1")
            >>> cache.set("session2", "vm2")
            >>> cache.clear()
            >>> cache.get("session1")
            None
        """
        try:
            if self.cache_path.exists():
                self.cache_path.unlink()
                logger.debug("Cache cleared")
            else:
                logger.debug("Cache file does not exist, nothing to clear")
        except Exception as e:
            logger.warning(f"Cache clear failed: {e}")

    def cleanup_expired(self) -> int:
        """Remove all expired entries from cache.

        Returns:
            Number of entries removed

        Example:
            >>> cache = VMCache(ttl=1)  # 1 second TTL
            >>> cache.set("session1", "vm1")
            >>> time.sleep(2)
            >>> cache.cleanup_expired()
            1
        """
        try:
            entries = self._load_cache()
            original_count = len(entries)

            # Filter out expired entries
            valid_entries = {
                name: entry for name, entry in entries.items() if not entry.is_expired()
            }

            removed_count = original_count - len(valid_entries)

            if removed_count > 0:
                self._save_cache(valid_entries)
                logger.debug(f"Cleaned up {removed_count} expired cache entries")

            return removed_count

        except Exception as e:
            logger.warning(f"Cache cleanup failed: {e}")
            return 0


__all__ = ["VMCache", "VMCacheEntry", "VMCacheError"]
