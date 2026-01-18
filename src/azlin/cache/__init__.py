"""Cache Module - Caching infrastructure for azlin.

Philosophy:
- Tiered caching (in-memory + file-based)
- TTL-based expiration (immutable 24h, mutable 5min)
- Background refresh for proactive cache warming
- Thread-safe operations

Public API (the "studs"):
    From config_cache:
        CachedConfigManager: In-memory config caching
        ConfigCache: Config cache data model

    From vm_list_cache:
        VMListCache: Tiered TTL cache for VM listing
        VMCacheEntry: VM cache entry data model
        CacheLayer: Cache layer types (immutable/mutable)
        make_cache_key: Create cache key from VM name and resource group

    From background_refresh:
        trigger_background_refresh: Trigger background cache refresh (non-blocking)
        is_refresh_running: Check if refresh is currently running
        BackgroundCacheRefresh: Background cache refresh manager
"""

from azlin.cache.background_refresh import (
    BackgroundCacheRefresh,
    is_refresh_running,
    trigger_background_refresh,
)
from azlin.cache.config_cache import CachedConfigManager, ConfigCache
from azlin.cache.vm_list_cache import (
    CacheLayer,
    VMCacheEntry,
    VMListCache,
    make_cache_key,
)

__all__ = [
    "BackgroundCacheRefresh",
    "CacheLayer",
    "CachedConfigManager",
    "ConfigCache",
    "VMCacheEntry",
    "VMListCache",
    "is_refresh_running",
    "make_cache_key",
    "trigger_background_refresh",
]
