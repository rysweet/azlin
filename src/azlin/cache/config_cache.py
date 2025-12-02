"""Config Cache Module - In-memory configuration caching.

Philosophy:
- In-memory caching for fast access
- File modification detection for automatic invalidation
- Thread-safe operations
- Zero external dependencies

Public API (the "studs"):
    CachedConfigManager: In-memory config cache with mtime tracking
    ConfigCache: Data model for config cache entries
"""

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tomli  # noqa: F401 (used in try/except at runtime)


@dataclass
class ConfigCache:
    """Config cache data model.

    Attributes:
        data: Cached configuration data
        mtime: File modification time
        path: Path to config file
    """

    data: dict[str, Any] | None = None
    mtime: float = 0.0
    path: Path | None = None

    def is_valid(self) -> bool:
        """Check if cache is still valid.

        Returns:
            True if cache is valid (file unchanged), False otherwise
        """
        if self.path is None or self.data is None:
            return False

        try:
            current_mtime = self.path.stat().st_mtime
            return current_mtime == self.mtime
        except (FileNotFoundError, OSError):
            return False


class CachedConfigManager:
    """Config manager with in-memory cache.

    Provides in-memory caching of configuration files with automatic
    invalidation when files are modified.

    Example:
        >>> manager = CachedConfigManager()
        >>> config = manager.load(config_path)  # Cache miss
        >>> config = manager.load(config_path)  # Cache hit (<1ms)
    """

    # Singleton cache shared across all instances
    _shared_cache: ConfigCache | None = None
    _shared_lock = threading.Lock()

    def __init__(self):
        """Initialize cached config manager."""
        self._cache_lock = threading.Lock()
        self.default_config_path = Path.home() / ".azlin" / "config.toml"
        self._hit_count = 0
        self._miss_count = 0

    @property
    def _cache(self) -> ConfigCache | None:
        """Get shared cache instance."""
        return CachedConfigManager._shared_cache

    @_cache.setter
    def _cache(self, value: ConfigCache | None) -> None:
        """Set shared cache instance."""
        CachedConfigManager._shared_cache = value

    def load(self, config_path: Path | None = None, force_reload: bool = False) -> dict[str, Any]:
        """Load config with in-memory cache.

        Args:
            config_path: Path to configuration file (uses default if not specified)
            force_reload: Force reload from disk, bypassing cache

        Returns:
            Configuration dictionary

        Example:
            >>> manager = CachedConfigManager()
            >>> config = manager.load(Path("~/.azlin/config.toml"))
        """
        if config_path is None:
            config_path = self.default_config_path

        config_path = Path(config_path).expanduser()

        with self._cache_lock:
            # Check if file exists
            try:
                current_mtime = config_path.stat().st_mtime
            except (FileNotFoundError, OSError):
                # File doesn't exist or inaccessible
                return {}

            # Check cache validity
            if (
                not force_reload
                and self._cache is not None
                and self._cache.path == config_path
                and self._cache.is_valid()
            ):
                # Cache hit: <1ms
                self._hit_count += 1
                return self._cache.data or {}

            # Cache miss: reload from disk
            self._miss_count += 1
            config = self._load_from_disk(config_path)
            self._cache = ConfigCache(data=config, mtime=current_mtime, path=config_path)
            return config

    def _load_from_disk(self, config_path: Path) -> dict[str, Any]:
        """Load configuration from disk.

        Args:
            config_path: Path to configuration file

        Returns:
            Configuration dictionary
        """
        try:
            # Try TOML first (most common for azlin)
            try:
                import tomli

                with open(config_path, "rb") as f:
                    return tomli.load(f)
            except ImportError:
                # Fallback to tomllib (Python 3.11+)
                try:
                    import tomllib

                    with open(config_path, "rb") as f:
                        return tomllib.load(f)
                except ImportError:
                    pass

            # Fallback to JSON
            import json

            with open(config_path) as f:
                return json.load(f)
        except Exception:
            # Return empty dict on any load error
            return {}

    def invalidate(self, config_path: Path | None = None) -> None:
        """Invalidate cache for specific path or all.

        Args:
            config_path: Path to invalidate (None = invalidate all)

        Example:
            >>> manager = CachedConfigManager()
            >>> manager.invalidate()  # Clear all
            >>> manager.invalidate(Path("~/.azlin/config.toml"))  # Clear specific
        """
        with self._cache_lock:
            # Just clear the cache - we have singleton cache
            self._cache = None

    def clear_cache(self) -> None:
        """Clear the cache.

        Example:
            >>> manager = CachedConfigManager()
            >>> manager.clear_cache()
        """
        with self._cache_lock:
            self._cache = None

    def save(self, config: dict[str, Any], config_path: Path | None = None) -> None:
        """Save config to disk and invalidate cache.

        Args:
            config: Configuration dictionary to save
            config_path: Path to save to (uses default if not specified)

        Example:
            >>> manager = CachedConfigManager()
            >>> config = {"settings": {"default_region": "westus2"}}
            >>> manager.save(config)
        """
        if config_path is None:
            config_path = self.default_config_path

        config_path = Path(config_path).expanduser()

        # Write to disk
        try:
            import tomli_w

            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "wb") as f:
                tomli_w.dump(config, f)
        except ImportError:
            # Fallback to JSON
            import json

            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)

        # Invalidate cache
        with self._cache_lock:
            self._cache = None

    def get_resource_group(self, config_path: Path | None = None) -> str | None:
        """Get default resource group from config.

        Args:
            config_path: Path to config file (uses default if not specified)

        Returns:
            Default resource group name or None

        Example:
            >>> manager = CachedConfigManager()
            >>> rg = manager.get_resource_group()
        """
        config = self.load(config_path)
        return config.get("settings", {}).get("default_resource_group")

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics

        Example:
            >>> manager = CachedConfigManager()
            >>> stats = manager.get_cache_stats()
            >>> print(stats["cached"])
        """
        with self._cache_lock:
            total = self._hit_count + self._miss_count
            hit_ratio = self._hit_count / total if total > 0 else 0.0

            return {
                "cached": self._cache is not None,
                "hit_count": self._hit_count,
                "miss_count": self._miss_count,
                "hit_ratio": hit_ratio,
            }


__all__ = ["CachedConfigManager", "ConfigCache"]
