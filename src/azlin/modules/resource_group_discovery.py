"""Resource Group Discovery Module.

Automatically discovers which resource group contains a VM by querying Azure.
Implements caching to minimize Azure API calls and improve performance.

Key features:
- Fast cache lookups (<100ms)
- Azure query fallback (2-3 seconds)
- Configurable TTL (default: 15 minutes)
- Automatic cache invalidation on failures
- Session name and VM name lookups
"""

import json
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Constants
DEFAULT_CACHE_TTL = 900  # 15 minutes
DEFAULT_QUERY_TIMEOUT = 30
MAX_CACHE_AGE = 3600  # 1 hour cleanup threshold


@dataclass
class ResourceGroupInfo:
    """Information about discovered resource group."""

    vm_name: str
    resource_group: str
    session_name: Optional[str] = None
    source: str = "unknown"  # cache, tags, config, default
    confidence: str = "low"  # high, medium, low
    cached: bool = False


class ResourceGroupDiscoveryError(Exception):
    """Exception raised for resource group discovery failures."""

    pass


class ResourceGroupDiscovery:
    """Discovers VM resource groups automatically."""

    def __init__(self, config: Optional[dict] = None):
        """Initialize resource group discovery.

        Args:
            config: Configuration dictionary with resource_group settings
        """
        self.config = config or {}
        self.cache_path = Path.home() / ".azlin" / "cache" / "rg_cache.json"
        self.cache_ttl = self.config.get("resource_group", {}).get("cache_ttl", DEFAULT_CACHE_TTL)
        self._ensure_cache_directory()

    def _ensure_cache_directory(self):
        """Create cache directory if it doesn't exist."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Failed to create cache directory: {e}")

    def find_vm_resource_group(
        self,
        vm_identifier: str,
        use_cache: bool = True,
        force_refresh: bool = False,
        subscription_id: Optional[str] = None,
    ) -> Optional[ResourceGroupInfo]:
        """Find resource group for a VM by name or session identifier.

        Args:
            vm_identifier: VM name or session name to find
            use_cache: Whether to use cached results (default: True)
            force_refresh: Force fresh Azure query, bypass cache
            subscription_id: Optional Azure subscription ID to filter

        Returns:
            ResourceGroupInfo if found, None otherwise
        """
        if not vm_identifier or not vm_identifier.strip():
            logger.warning("Empty VM identifier provided")
            return None

        vm_identifier = vm_identifier.strip()

        # Check cache first (unless force_refresh)
        if use_cache and not force_refresh:
            cached_result = self._get_from_cache(vm_identifier)
            if cached_result:
                return cached_result

        # Cache miss - query Azure
        try:
            result = self.query_all_resource_groups(vm_identifier, subscription_id)
            if result:
                self._save_to_cache(vm_identifier, result)
                return result
            return self._try_fallbacks(vm_identifier)

        except (subprocess.TimeoutExpired, Exception) as e:
            error_type = "timed out" if isinstance(e, subprocess.TimeoutExpired) else "failed"
            logger.warning(f"Azure query {error_type} for {vm_identifier}: {e}")
            return self._try_fallbacks(vm_identifier)

    def query_all_resource_groups(
        self, vm_identifier: str, subscription_id: Optional[str] = None
    ) -> Optional[ResourceGroupInfo]:
        """Query Azure for VMs matching the identifier.

        Searches by VM name or azlin-session tag.

        Args:
            vm_identifier: VM name or session name
            subscription_id: Optional subscription filter

        Returns:
            ResourceGroupInfo if exactly one match found

        Raises:
            ResourceGroupDiscoveryError: If multiple matches found
        """
        timeout = self.config.get("resource_group", {}).get("query_timeout", DEFAULT_QUERY_TIMEOUT)

        # Build Azure CLI query
        query = (
            "[?tags.\"managed-by\"=='azlin' && "
            "(name=='{0}' || tags.\"azlin-session\"=='{0}')]"
            ".{{name:name, resourceGroup:resourceGroup, "
            'sessionName:tags."azlin-session"}}'
        ).format(vm_identifier)

        cmd = ["az", "vm", "list", "--query", query, "--output", "json"]

        if subscription_id:
            cmd.extend(["--subscription", subscription_id])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                if "az login" in error_msg.lower():
                    raise ResourceGroupDiscoveryError("Not logged in to Azure CLI")
                elif "permission" in error_msg.lower():
                    raise ResourceGroupDiscoveryError("Insufficient permissions to list VMs")
                else:
                    logger.warning(f"Azure query failed: {error_msg}")
                    return None

            vms = json.loads(result.stdout)

            if not vms:
                logger.debug(f"No VMs found matching {vm_identifier}")
                return None

            if len(vms) > 1:
                # Multiple matches - raise error with list
                vm_list = "\n".join(
                    [
                        f"  {i + 1}. {vm['name']} ({vm['resourceGroup']}) "
                        f"- Session: {vm.get('sessionName', 'N/A')}"
                        for i, vm in enumerate(vms)
                    ]
                )
                raise ResourceGroupDiscoveryError(
                    f"Multiple VMs found with identifier '{vm_identifier}':\n{vm_list}\n"
                    "Use --resource-group to specify which one."
                )

            # Single match - success
            vm = vms[0]
            return ResourceGroupInfo(
                vm_name=vm["name"],
                resource_group=vm["resourceGroup"],
                session_name=vm.get("sessionName"),
                source="tags",
                confidence="high",
                cached=False,
            )

        except subprocess.TimeoutExpired:
            raise
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Azure response: {e}")
            return None

    def _get_from_cache(self, vm_identifier: str) -> Optional[ResourceGroupInfo]:
        """Get resource group info from cache if valid.

        Args:
            vm_identifier: VM or session name

        Returns:
            ResourceGroupInfo if cache hit and not expired, None otherwise
        """
        try:
            cache = self._load_cache()

            if vm_identifier not in cache.get("entries", {}):
                return None

            entry = cache["entries"][vm_identifier]

            # Check if expired
            if self._is_cache_expired(entry):
                logger.debug(f"Cache entry expired for {vm_identifier}")
                return None

            # Valid cache entry
            return ResourceGroupInfo(
                vm_name=entry["vm_name"],
                resource_group=entry["resource_group"],
                session_name=entry.get("session_name"),
                source="cache",
                confidence="high",
                cached=True,
            )

        except Exception as e:
            logger.debug(f"Cache read error: {e}")
            return None

    def _save_to_cache(self, vm_identifier: str, info: ResourceGroupInfo):
        """Save resource group info to cache.

        Args:
            vm_identifier: VM or session name
            info: ResourceGroupInfo to cache
        """
        try:
            cache = self._load_cache()

            if "entries" not in cache:
                cache["entries"] = {}

            cache["entries"][vm_identifier] = {
                "vm_name": info.vm_name,
                "resource_group": info.resource_group,
                "session_name": info.session_name,
                "timestamp": time.time(),
                "ttl": self.cache_ttl,
            }

            self._write_cache(cache)
            logger.debug(f"Cached resource group for {vm_identifier}")

        except Exception as e:
            logger.warning(f"Failed to write cache: {e}")

    def _load_cache(self) -> dict:
        """Load cache from disk.

        Returns:
            Cache dictionary, or empty cache if file doesn't exist/invalid
        """
        if not self.cache_path.exists():
            return {"version": 1, "entries": {}}

        try:
            with open(self.cache_path, "r") as f:
                cache = json.load(f)

            # Validate version
            if cache.get("version") != 1:
                logger.warning("Cache version mismatch, rebuilding")
                return {"version": 1, "entries": {}}

            # Cleanup old entries (> 1 hour)
            self._cleanup_old_entries(cache)

            return cache

        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Cache corrupted, rebuilding: {e}")
            return {"version": 1, "entries": {}}

    def _write_cache(self, cache: dict):
        """Write cache to disk.

        Args:
            cache: Cache dictionary to write
        """
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.cache_path, "w") as f:
                json.dump(cache, f, indent=2)

            # Set permissions to 0600 (owner read/write only)
            self.cache_path.chmod(0o600)

        except Exception as e:
            logger.warning(f"Failed to write cache: {e}")

    def _is_cache_expired(self, entry: dict) -> bool:
        """Check if cache entry is expired."""
        if "timestamp" not in entry:
            return True
        age = time.time() - entry["timestamp"]
        ttl = entry.get("ttl", self.cache_ttl)
        return age > ttl

    def _cleanup_old_entries(self, cache: dict):
        """Remove cache entries older than 1 hour (modified in place)."""
        if "entries" not in cache:
            return

        current_time = time.time()
        entries_to_remove = [
            key
            for key, entry in cache["entries"].items()
            if "timestamp" not in entry or (current_time - entry["timestamp"]) > MAX_CACHE_AGE
        ]

        for key in entries_to_remove:
            del cache["entries"][key]

        if entries_to_remove:
            logger.debug(f"Cleaned up {len(entries_to_remove)} old cache entries")

    def _try_fallbacks(self, vm_identifier: str) -> Optional[ResourceGroupInfo]:
        """Try fallback methods when Azure query fails or returns no results."""
        # Use default resource group if configured and fallback enabled
        fallback_enabled = self.config.get("resource_group", {}).get("fallback_to_default", True)
        default_rg = self.config.get("default_resource_group")

        if fallback_enabled and default_rg:
            return ResourceGroupInfo(
                vm_name=vm_identifier,
                resource_group=default_rg,
                source="default",
                confidence="low",
                cached=False,
            )

        return None

    def invalidate_cache(self, vm_identifier: Optional[str] = None):
        """Invalidate cache entries.

        Args:
            vm_identifier: Specific entry to invalidate, or None for all
        """
        if vm_identifier is None:
            # Clear entire cache
            try:
                if self.cache_path.exists():
                    self.cache_path.unlink()
                logger.debug("Cleared entire cache")
            except Exception as e:
                logger.warning(f"Failed to clear cache: {e}")
        else:
            # Remove specific entry
            try:
                cache = self._load_cache()
                if vm_identifier in cache.get("entries", {}):
                    del cache["entries"][vm_identifier]
                    self._write_cache(cache)
                    logger.debug(f"Invalidated cache for {vm_identifier}")
            except Exception as e:
                logger.warning(f"Failed to invalidate cache entry: {e}")
