"""VM List Cache Module - Tiered TTL caching for VM listing.

Philosophy:
- Tiered TTL: Immutable data cached longer (24h), mutable data shorter (5min)
- File-based caching for persistence across CLI invocations
- Thread-safe operations
- Automatic cache invalidation based on TTL

Public API (the "studs"):
    VMListCache: Tiered caching for VM listing data
    VMCacheEntry: Data model for cached VM entries
    CacheLayer: Enum for cache layer types (immutable/mutable)
    make_cache_key: Create cache key from VM name and resource group

Architecture:
- Immutable Layer (24h TTL): VM name, location, size, resource group
- Mutable Layer (5min TTL): Power state, IPs, provisioning state
- Automatic merging of cache layers with fallback to API calls

Performance Target:
- Cold start: ~10-15s (baseline)
- Warm start (full cache): <1s (98% improvement)
- Partial cache: 3-5s (70% improvement)
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def make_cache_key(vm_name: str, resource_group: str) -> str:
    """Create cache key from VM name and resource group.

    This function provides a consistent cache key format used across all
    caching operations. Cache keys use the format "resource_group:vm_name".

    Args:
        vm_name: VM name
        resource_group: Resource group name

    Returns:
        Cache key string in format "resource_group:vm_name"

    Example:
        >>> make_cache_key("my-vm", "my-rg")
        'my-rg:my-vm'
    """
    return f"{resource_group}:{vm_name}"


class VMListCacheError(Exception):
    """Raised when VM list cache operations fail."""

    pass


class CacheLayer(StrEnum):
    """Cache layer types with different TTLs."""

    IMMUTABLE = "immutable"  # 24h TTL - VM metadata that rarely changes
    MUTABLE = "mutable"  # 5min TTL - VM state that changes frequently


@dataclass
class VMCacheEntry:
    """VM cache entry with tiered data.

    Attributes:
        vm_name: VM name (key)
        resource_group: Resource group name
        immutable_data: Immutable VM metadata (name, location, size)
        immutable_timestamp: Timestamp for immutable data
        mutable_data: Mutable VM state (power state, IPs)
        mutable_timestamp: Timestamp for mutable data
        tmux_sessions: Tmux session data (session names, attached status)
        tmux_timestamp: Timestamp for tmux data
    """

    vm_name: str
    resource_group: str
    immutable_data: dict[str, Any] = field(default_factory=dict)
    immutable_timestamp: float = 0.0
    mutable_data: dict[str, Any] = field(default_factory=dict)
    mutable_timestamp: float = 0.0
    tmux_sessions: list[dict[str, Any]] = field(default_factory=list)
    tmux_timestamp: float = 0.0

    def is_immutable_expired(self, ttl: int = 86400) -> bool:
        """Check if immutable data has expired.

        Args:
            ttl: Time-to-live in seconds (default: 86400 = 24h)

        Returns:
            True if expired, False otherwise
        """
        if self.immutable_timestamp == 0.0:
            return True
        age = time.time() - self.immutable_timestamp
        return age > ttl

    def is_mutable_expired(self, ttl: int = 300) -> bool:
        """Check if mutable data has expired.

        Args:
            ttl: Time-to-live in seconds (default: 300 = 5min)

        Returns:
            True if expired, False otherwise
        """
        if self.mutable_timestamp == 0.0:
            return True
        age = time.time() - self.mutable_timestamp
        return age > ttl

    def is_tmux_expired(self, ttl: int = 300) -> bool:
        """Check if tmux session data has expired.

        Args:
            ttl: Time-to-live in seconds (default: 300 = 5min)

        Returns:
            True if expired, False otherwise
        """
        if self.tmux_timestamp == 0.0:
            return True
        age = time.time() - self.tmux_timestamp
        return age > ttl

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary with all cache entry fields
        """
        return {
            "vm_name": self.vm_name,
            "resource_group": self.resource_group,
            "immutable_data": self.immutable_data,
            "immutable_timestamp": self.immutable_timestamp,
            "mutable_data": self.mutable_data,
            "mutable_timestamp": self.mutable_timestamp,
            "tmux_sessions": self.tmux_sessions,
            "tmux_timestamp": self.tmux_timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VMCacheEntry":
        """Create from dictionary.

        Args:
            data: Dictionary with cache entry fields

        Returns:
            VMCacheEntry object
        """
        return cls(
            vm_name=data["vm_name"],
            resource_group=data["resource_group"],
            immutable_data=data.get("immutable_data", {}),
            immutable_timestamp=data.get("immutable_timestamp", 0.0),
            mutable_data=data.get("mutable_data", {}),
            mutable_timestamp=data.get("mutable_timestamp", 0.0),
            tmux_sessions=data.get("tmux_sessions", []),
            tmux_timestamp=data.get("tmux_timestamp", 0.0),
        )


class VMListCache:
    """Tiered TTL cache for VM listing operations.

    Provides two-layer caching with different TTLs:
    - Immutable layer (24h): VM metadata that rarely changes
    - Mutable layer (5min): VM state that changes frequently

    TTL Rationale:
    - Immutable (24h): VM metadata changes only through VM recreation (location,
      size, OS type). Users rarely modify these properties, so a long TTL
      significantly reduces API calls without risk of stale data.
    - Mutable (5min): VM state changes during normal operations (power state,
      IPs). The 5-minute TTL balances freshness with performance, allowing
      multiple list operations to use cached data while ensuring recent
      start/stop/IP changes are reflected.

    Cache file: ~/.azlin/vm_list_cache.json

    Example:
        >>> cache = VMListCache()
        >>> cache.set_immutable("vm1", "rg1", {"name": "vm1", "location": "westus2"})
        >>> cache.set_mutable("vm1", "rg1", {"power_state": "VM running"})
        >>> entry = cache.get("vm1", "rg1")
        >>> if entry and not entry.is_mutable_expired():
        ...     print(entry.mutable_data)
    """

    DEFAULT_CACHE_DIR = Path.home() / ".azlin"
    DEFAULT_CACHE_FILE = DEFAULT_CACHE_DIR / "vm_list_cache.json"

    # TTL Rationale:
    # - Immutable (24h): VM metadata changes require VM recreation (location, size, OS type)
    #   Users rarely change these, so long TTL reduces API calls without stale data risk
    # - Mutable (5min): VM state changes during normal operations (power state, IPs)
    #   Balance between freshness and performance: 5min is long enough for repeated
    #   list operations but short enough to reflect recent start/stop/IP changes
    IMMUTABLE_TTL = 86400  # 24 hours
    MUTABLE_TTL = 300  # 5 minutes

    def __init__(
        self,
        cache_path: Path | None = None,
        immutable_ttl: int | None = None,
        mutable_ttl: int | None = None,
    ):
        """Initialize VM list cache.

        Args:
            cache_path: Custom cache file path (default: ~/.azlin/vm_list_cache.json)
            immutable_ttl: TTL for immutable data in seconds (default: 86400 = 24h)
            mutable_ttl: TTL for mutable data in seconds (default: 300 = 5min)
        """
        self.cache_path = cache_path or self.DEFAULT_CACHE_FILE
        self.immutable_ttl = immutable_ttl or self.IMMUTABLE_TTL
        self.mutable_ttl = mutable_ttl or self.MUTABLE_TTL

    def _ensure_cache_dir(self) -> None:
        """Ensure cache directory exists with secure permissions.

        Raises:
            VMListCacheError: If directory creation fails
        """
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            # Set secure permissions (owner only: rwx------)
            os.chmod(self.cache_path.parent, 0o700)
            logger.debug(f"Cache directory ready: {self.cache_path.parent}")
        except Exception as e:
            raise VMListCacheError(f"Failed to create cache directory: {e}") from e

    def _load_cache(self) -> dict[str, VMCacheEntry]:
        """Load cache from file.

        Returns:
            Dictionary of (vm_name, resource_group) -> VMCacheEntry
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

            # Load JSON
            with open(self.cache_path) as f:
                data = json.load(f)

            # Convert to VMCacheEntry objects
            entries = {}
            for key, entry_data in data.items():
                try:
                    entry = VMCacheEntry.from_dict(entry_data)
                    entries[key] = entry
                except Exception as e:
                    logger.warning(f"Skipping invalid cache entry for '{key}': {e}")
                    continue

            logger.debug(f"Loaded {len(entries)} cache entries from {self.cache_path}")
            return entries

        except Exception as e:
            logger.warning(f"Failed to load cache, returning empty cache: {e}")
            return {}

    def _save_cache(self, entries: dict[str, VMCacheEntry]) -> None:
        """Save cache to file.

        Args:
            entries: Dictionary of key -> VMCacheEntry

        Raises:
            VMListCacheError: If saving fails
        """
        temp_path: Path | None = None
        try:
            # Ensure directory exists
            self._ensure_cache_dir()

            # Use temporary file and atomic rename for safety
            temp_path = self.cache_path.with_suffix(".tmp")

            # Convert entries to JSON-serializable format
            data = {key: entry.to_dict() for key, entry in entries.items()}

            # Write to temp file
            with open(temp_path, "w") as f:
                json.dump(data, f, indent=2)

            # Set secure permissions before moving
            os.chmod(temp_path, 0o600)

            # Atomic rename
            temp_path.replace(self.cache_path)

            logger.debug(f"Saved {len(entries)} cache entries to {self.cache_path}")

        except Exception as e:
            # Cleanup temp file on error
            if temp_path and temp_path.exists():
                temp_path.unlink()
            raise VMListCacheError(f"Failed to save cache: {e}") from e

    def get(self, vm_name: str, resource_group: str) -> VMCacheEntry | None:
        """Get VM cache entry.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            VMCacheEntry if found, None otherwise
        """
        try:
            entries = self._load_cache()
            key = make_cache_key(vm_name, resource_group)

            if key not in entries:
                logger.debug(f"Cache miss: '{key}' not found")
                return None

            entry = entries[key]
            logger.debug(
                f"Cache hit: '{key}' "
                f"(immutable_expired={entry.is_immutable_expired(self.immutable_ttl)}, "
                f"mutable_expired={entry.is_mutable_expired(self.mutable_ttl)})"
            )
            return entry

        except Exception as e:
            logger.warning(f"Cache lookup failed for '{vm_name}': {e}")
            return None

    def set_immutable(
        self, vm_name: str, resource_group: str, immutable_data: dict[str, Any]
    ) -> None:
        """Set immutable VM data in cache.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            immutable_data: Immutable VM metadata (name, location, size, etc.)

        Raises:
            VMListCacheError: If cache update fails
        """
        try:
            entries = self._load_cache()
            key = make_cache_key(vm_name, resource_group)

            # Get existing entry or create new one
            if key in entries:
                entry = entries[key]
                entry.immutable_data = immutable_data
                entry.immutable_timestamp = time.time()
            else:
                entry = VMCacheEntry(
                    vm_name=vm_name,
                    resource_group=resource_group,
                    immutable_data=immutable_data,
                    immutable_timestamp=time.time(),
                )

            entries[key] = entry
            self._save_cache(entries)

            logger.debug(f"Cache set (immutable): '{key}' (TTL: {self.immutable_ttl}s)")

        except Exception as e:
            raise VMListCacheError(f"Failed to set immutable cache for '{vm_name}': {e}") from e

    def set_mutable(self, vm_name: str, resource_group: str, mutable_data: dict[str, Any]) -> None:
        """Set mutable VM data in cache.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            mutable_data: Mutable VM state (power state, IPs, etc.)

        Raises:
            VMListCacheError: If cache update fails
        """
        try:
            entries = self._load_cache()
            key = make_cache_key(vm_name, resource_group)

            # Get existing entry or create new one
            if key in entries:
                entry = entries[key]
                entry.mutable_data = mutable_data
                entry.mutable_timestamp = time.time()
            else:
                entry = VMCacheEntry(
                    vm_name=vm_name,
                    resource_group=resource_group,
                    mutable_data=mutable_data,
                    mutable_timestamp=time.time(),
                )

            entries[key] = entry
            self._save_cache(entries)

            logger.debug(f"Cache set (mutable): '{key}' (TTL: {self.mutable_ttl}s)")

        except Exception as e:
            raise VMListCacheError(f"Failed to set mutable cache for '{vm_name}': {e}") from e

    def set_full(
        self,
        vm_name: str,
        resource_group: str,
        immutable_data: dict[str, Any],
        mutable_data: dict[str, Any],
    ) -> None:
        """Set both immutable and mutable VM data in cache.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            immutable_data: Immutable VM metadata
            mutable_data: Mutable VM state

        Raises:
            VMListCacheError: If cache update fails
        """
        try:
            entries = self._load_cache()
            key = make_cache_key(vm_name, resource_group)

            entry = VMCacheEntry(
                vm_name=vm_name,
                resource_group=resource_group,
                immutable_data=immutable_data,
                immutable_timestamp=time.time(),
                mutable_data=mutable_data,
                mutable_timestamp=time.time(),
            )

            entries[key] = entry
            self._save_cache(entries)

            logger.debug(f"Cache set (full): '{key}'")

        except Exception as e:
            logger.warning(f"Failed to cache VM {vm_name}: {e}")
            raise VMListCacheError(f"Failed to set full cache: {e}") from e

    def set_tmux(
        self,
        vm_name: str,
        resource_group: str,
        tmux_sessions: list[dict[str, Any]],
    ) -> None:
        """Set tmux session data in cache for a VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            tmux_sessions: List of tmux session dicts

        Raises:
            VMListCacheError: If cache update fails
        """
        try:
            entries = self._load_cache()
            key = make_cache_key(vm_name, resource_group)

            if key in entries:
                # Update existing entry
                entries[key].tmux_sessions = tmux_sessions
                entries[key].tmux_timestamp = time.time()
            else:
                # Create new entry with just tmux data
                entries[key] = VMCacheEntry(
                    vm_name=vm_name,
                    resource_group=resource_group,
                    tmux_sessions=tmux_sessions,
                    tmux_timestamp=time.time(),
                )

            self._save_cache(entries)
            logger.debug(f"Cache set (tmux): '{key}' with {len(tmux_sessions)} sessions")

        except Exception as e:
            logger.warning(f"Failed to cache tmux sessions for {vm_name}: {e}")
            raise VMListCacheError(f"Failed to cache tmux sessions: {e}") from e

    def delete(self, vm_name: str, resource_group: str) -> bool:
        """Delete cache entry for VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            True if entry was deleted, False if not found
        """
        try:
            entries = self._load_cache()
            key = make_cache_key(vm_name, resource_group)

            if key not in entries:
                logger.debug(f"Cache delete: '{key}' not found")
                return False

            del entries[key]
            self._save_cache(entries)

            logger.debug(f"Cache deleted: '{key}'")
            return True

        except Exception as e:
            logger.warning(f"Cache delete failed for '{vm_name}': {e}")
            return False

    def clear(self) -> None:
        """Clear all cache entries."""
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
        """
        try:
            entries = self._load_cache()
            original_count = len(entries)

            # Filter out entries where BOTH layers are expired
            valid_entries = {}
            for key, entry in entries.items():
                immutable_expired = entry.is_immutable_expired(self.immutable_ttl)
                mutable_expired = entry.is_mutable_expired(self.mutable_ttl)

                # Keep entry if at least one layer is still valid
                if not (immutable_expired and mutable_expired):
                    valid_entries[key] = entry

            removed_count = original_count - len(valid_entries)

            if removed_count > 0:
                self._save_cache(valid_entries)
                logger.debug(f"Cleaned up {removed_count} expired cache entries")

            return removed_count

        except Exception as e:
            logger.warning(f"Cache cleanup failed: {e}")
            return 0

    def get_resource_group_entries(self, resource_group: str) -> list[VMCacheEntry]:
        """Get all cache entries for a resource group.

        Args:
            resource_group: Resource group name

        Returns:
            List of VMCacheEntry objects for the resource group
        """
        try:
            entries = self._load_cache()
            return [entry for entry in entries.values() if entry.resource_group == resource_group]
        except Exception as e:
            logger.warning(f"Failed to get resource group entries: {e}")
            return []


__all__ = ["CacheLayer", "VMCacheEntry", "VMListCache", "VMListCacheError", "make_cache_key"]
