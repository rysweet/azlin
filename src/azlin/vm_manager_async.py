"""Async VM Manager - Parallel VM listing with caching.

Philosophy:
- Parallel execution: Use asyncio to query multiple VMs concurrently
- Tiered caching: Leverage VMListCache for 70% performance improvement
- Backward compatible: Drop-in replacement for VMManager.list_vms()
- Resource efficient: Configurable concurrency limits

Public API (the "studs"):
    AsyncVMManager: Async VM manager with parallel operations
    list_vms_parallel: Parallel VM listing with caching (main entry point)

Performance Targets:
- Cold start: 10-15s for 10 VMs (vs 30-50s baseline)
- Warm start: <1s with full cache (vs 3-5s without cache)
- 70% improvement overall

Architecture:
1. Batch API calls: List VMs + Public IPs in parallel
2. Parallel enrichment: Fetch instance views concurrently
3. Tiered caching: Cache immutable (24h) and mutable (5min) data separately
4. Smart fallback: Use cache when available, fetch missing data in parallel

Integration:
- Uses VMListCache for tiered TTL caching
- Compatible with existing VMManager and VMInfo
- Integrates with multi_context_list for multi-tenant queries
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from azlin.cache.vm_list_cache import VMListCache
from azlin.vm_manager import VMInfo, VMManager, VMManagerError

logger = logging.getLogger(__name__)


@dataclass
class ParallelListStats:
    """Statistics for parallel VM listing operation.

    Attributes:
        total_duration: Total duration in seconds
        cache_hits: Number of cache hits
        cache_misses: Number of cache misses
        api_calls: Number of Azure API calls made
        vms_found: Number of VMs found
    """

    total_duration: float
    cache_hits: int
    cache_misses: int
    api_calls: int
    vms_found: int

    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate.

        Returns:
            Cache hit rate as percentage (0.0 - 1.0)
        """
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0


class AsyncVMManager:
    """Async VM manager with parallel operations and caching.

    Provides high-performance VM listing with:
    - Parallel API calls using asyncio
    - Tiered TTL caching (24h immutable, 5min mutable)
    - Smart cache fallback strategy
    - Configurable concurrency limits

    Example:
        >>> manager = AsyncVMManager(resource_group="azlin-rg")
        >>> vms, stats = await manager.list_vms_with_stats()
        >>> print(f"Found {len(vms)} VMs (cache hit rate: {stats.cache_hit_rate():.1%})")
    """

    def __init__(
        self,
        resource_group: str,
        cache: VMListCache | None = None,
        max_concurrent: int = 10,
    ):
        """Initialize async VM manager.

        Args:
            resource_group: Resource group name
            cache: VM list cache instance (creates new if None)
            max_concurrent: Maximum concurrent operations (default: 10)
        """
        self.resource_group = resource_group
        self.cache = cache or VMListCache()
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)

        # Stats
        self.cache_hits = 0
        self.cache_misses = 0
        self.api_calls = 0

    async def _run_az_command(self, cmd: list[str], timeout: int = 30) -> str:
        """Run Azure CLI command asynchronously.

        Args:
            cmd: Command list
            timeout: Timeout in seconds

        Returns:
            Command output

        Raises:
            VMManagerError: If command fails
        """
        async with self.semaphore:
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

                if process.returncode != 0:
                    raise VMManagerError(f"Command failed: {stderr.decode()}")

                self.api_calls += 1
                return stdout.decode()

            except TimeoutError as e:
                raise VMManagerError(f"Command timed out after {timeout}s") from e
            except Exception as e:
                raise VMManagerError(f"Command execution failed: {e}") from e

    async def _get_vms_list(self) -> list[dict[str, Any]]:
        """Get list of VMs from Azure (batch call).

        Returns:
            List of VM data dictionaries
        """
        cmd = [
            "az",
            "vm",
            "list",
            "--resource-group",
            self.resource_group,
            "--show-details",
            "--output",
            "json",
        ]

        output = await self._run_az_command(cmd, timeout=60)

        if not output or output.strip() == "":
            return []

        return json.loads(output)

    async def _get_public_ips(self) -> dict[str, str]:
        """Get all public IPs in resource group (batch call).

        Returns:
            Dictionary mapping public IP resource name to IP address
        """
        cmd = [
            "az",
            "network",
            "public-ip",
            "list",
            "--resource-group",
            self.resource_group,
            "--query",
            "[].{name:name, ip:ipAddress}",
            "--output",
            "json",
        ]

        try:
            output = await self._run_az_command(cmd, timeout=30)
            ips_data: list[dict[str, Any]] = json.loads(output)
            return {item["name"]: item["ip"] for item in ips_data if item.get("ip")}
        except Exception as e:
            logger.debug(f"Failed to fetch public IPs: {e}")
            return {}

    async def _get_instance_view(self, vm_name: str) -> dict[str, Any] | None:
        """Get VM instance view (individual call).

        Args:
            vm_name: VM name

        Returns:
            Instance view data or None if failed
        """
        cmd = [
            "az",
            "vm",
            "get-instance-view",
            "--name",
            vm_name,
            "--resource-group",
            self.resource_group,
            "--output",
            "json",
        ]

        try:
            output = await self._run_az_command(
                cmd, timeout=30
            )  # Increased for WSL compatibility (Issue #580)
            return json.loads(output)
        except Exception as e:
            logger.debug(f"Failed to get instance view for {vm_name}: {e}")
            return None

    async def _enrich_vm_with_cache(
        self, vm_data: dict[str, Any], public_ips: dict[str, str]
    ) -> VMInfo:
        """Enrich VM data using cache and parallel API calls.

        Args:
            vm_data: Basic VM data from list call
            public_ips: Public IP mapping

        Returns:
            Enriched VMInfo object
        """
        vm_name = vm_data["name"]

        # Check cache for this VM
        cache_entry = self.cache.get(vm_name, self.resource_group)

        # Prepare immutable data (always available from list call)
        immutable_data = {
            "name": vm_data["name"],
            "location": vm_data["location"],
            "vm_size": vm_data.get("hardwareProfile", {}).get("vmSize"),
            "os_type": vm_data.get("storageProfile", {}).get("osDisk", {}).get("osType"),
            "tags": vm_data.get("tags", {}),
            "created_time": vm_data.get("timeCreated"),
        }

        # Check if we need to fetch mutable data
        need_mutable_fetch = True
        mutable_data = {}

        if cache_entry:
            # Check if mutable cache is still valid
            if not cache_entry.is_mutable_expired(self.cache.mutable_ttl):
                # Use cached mutable data
                mutable_data = cache_entry.mutable_data
                need_mutable_fetch = False
                self.cache_hits += 1
                logger.debug(f"Cache hit (mutable) for {vm_name}")
            else:
                self.cache_misses += 1
                logger.debug(f"Cache miss (mutable expired) for {vm_name}")
        else:
            self.cache_misses += 1
            logger.debug(f"Cache miss (not found) for {vm_name}")

        # Fetch mutable data if needed
        if need_mutable_fetch:
            # Get instance view for power state
            instance_view = await self._get_instance_view(vm_name)

            power_state = "Unknown"
            if instance_view:
                statuses = instance_view.get("statuses", [])
                for status in statuses:
                    if status.get("code", "").startswith("PowerState/"):
                        power_state = status["displayStatus"]
                        break

            # Get public IP
            public_ip = vm_data.get("publicIps")
            if not public_ip:
                public_ip = public_ips.get(f"{vm_name}PublicIP")

            mutable_data = {
                "power_state": power_state,
                "public_ip": public_ip,
                "private_ip": vm_data.get("privateIps"),
                "provisioning_state": vm_data.get("provisioningState"),
            }

            # Update cache with both layers
            try:
                self.cache.set_full(vm_name, self.resource_group, immutable_data, mutable_data)
            except Exception as e:
                logger.warning(f"Failed to update cache for {vm_name}: {e}")

        # Merge immutable and mutable data
        return VMInfo(
            name=immutable_data["name"],
            resource_group=self.resource_group,
            location=immutable_data["location"],
            power_state=mutable_data.get("power_state", "Unknown"),
            public_ip=mutable_data.get("public_ip"),
            private_ip=mutable_data.get("private_ip"),
            vm_size=immutable_data.get("vm_size"),
            os_type=immutable_data.get("os_type"),
            provisioning_state=mutable_data.get("provisioning_state"),
            created_time=immutable_data.get("created_time"),
            tags=immutable_data.get("tags", {}),
        )

    async def list_vms_with_stats(
        self, include_stopped: bool = True, filter_prefix: str = "azlin"
    ) -> tuple[list[VMInfo], ParallelListStats]:
        """List VMs with performance statistics.

        Args:
            include_stopped: Include stopped/deallocated VMs
            filter_prefix: Filter VMs by name prefix

        Returns:
            Tuple of (list of VMInfo objects, performance stats)

        Raises:
            VMManagerError: If listing fails
        """
        start_time = asyncio.get_event_loop().time()

        try:
            # Cache-first optimization: Check if all VMs are fully cached and fresh
            cached_entries = self.cache.get_resource_group_entries(self.resource_group)

            if cached_entries:
                # Check if all cached entries are fresh (both layers valid)
                all_fresh = True
                for entry in cached_entries:
                    immutable_expired = entry.is_immutable_expired(self.cache.immutable_ttl)
                    mutable_expired = entry.is_mutable_expired(self.cache.mutable_ttl)
                    if immutable_expired or mutable_expired:
                        all_fresh = False
                        break

                if all_fresh:
                    # Build VMs from cache - FAST PATH!
                    result_vms = []
                    for entry in cached_entries:
                        # Add resource_group to immutable_data (stored separately in entry)
                        immutable_with_rg = {
                            **entry.immutable_data,
                            "resource_group": entry.resource_group,
                        }
                        vm = VMInfo.from_cache_data(immutable_with_rg, entry.mutable_data)
                        result_vms.append(vm)

                    # Apply filters (same as Azure path)
                    if not include_stopped:
                        result_vms = [vm for vm in result_vms if vm.is_running()]

                    if filter_prefix:
                        result_vms = VMManager.filter_by_prefix(result_vms, filter_prefix)

                    # Sort by creation time
                    result_vms = VMManager.sort_by_created_time(result_vms)

                    total_duration = asyncio.get_event_loop().time() - start_time

                    stats = ParallelListStats(
                        total_duration=total_duration,
                        cache_hits=len(result_vms),
                        cache_misses=0,
                        api_calls=0,  # No Azure API calls!
                        vms_found=len(result_vms),
                    )

                    logger.info(
                        f"Cache hit: Returned {len(result_vms)} VMs from cache in {total_duration:.2f}s "
                        f"(cache hit rate: 100%, API calls: 0)"
                    )

                    return result_vms, stats

            # Cache miss or partial - proceed with Azure API flow
            # Batch API calls in parallel (step 1)
            vms_data, public_ips = await asyncio.gather(
                self._get_vms_list(), self._get_public_ips(), return_exceptions=False
            )

            if not vms_data:
                return [], ParallelListStats(
                    total_duration=asyncio.get_event_loop().time() - start_time,
                    cache_hits=0,
                    cache_misses=0,
                    api_calls=self.api_calls,
                    vms_found=0,
                )

            # Enrich VMs in parallel (step 2)
            enrich_tasks = [self._enrich_vm_with_cache(vm_data, public_ips) for vm_data in vms_data]

            vms = await asyncio.gather(*enrich_tasks, return_exceptions=False)

            # Filter by power state
            if not include_stopped:
                vms = [vm for vm in vms if vm.is_running()]

            # Filter by prefix
            if filter_prefix:
                vms = VMManager.filter_by_prefix(vms, filter_prefix)

            # Sort by creation time
            vms = VMManager.sort_by_created_time(vms)

            total_duration = asyncio.get_event_loop().time() - start_time

            stats = ParallelListStats(
                total_duration=total_duration,
                cache_hits=self.cache_hits,
                cache_misses=self.cache_misses,
                api_calls=self.api_calls,
                vms_found=len(vms),
            )

            logger.info(
                f"Parallel VM listing completed: {len(vms)} VMs found in {total_duration:.2f}s "
                f"(cache hit rate: {stats.cache_hit_rate():.1%}, API calls: {self.api_calls})"
            )

            return vms, stats

        except VMManagerError:
            raise
        except Exception as e:
            raise VMManagerError(f"Parallel VM listing failed: {e}") from e

    async def list_vms(
        self, include_stopped: bool = True, filter_prefix: str = "azlin"
    ) -> list[VMInfo]:
        """List VMs (backward compatible interface).

        Args:
            include_stopped: Include stopped/deallocated VMs
            filter_prefix: Filter VMs by name prefix

        Returns:
            List of VMInfo objects

        Raises:
            VMManagerError: If listing fails
        """
        vms, _ = await self.list_vms_with_stats(include_stopped, filter_prefix)
        return vms


def list_vms_parallel(
    resource_group: str,
    include_stopped: bool = True,
    filter_prefix: str = "azlin",
    cache: VMListCache | None = None,
) -> list[VMInfo]:
    """List VMs using parallel operations and caching (sync wrapper).

    This is the main entry point for parallel VM listing. It provides
    a drop-in replacement for VMManager.list_vms() with 70% better performance.

    Args:
        resource_group: Resource group name
        include_stopped: Include stopped/deallocated VMs
        filter_prefix: Filter VMs by name prefix
        cache: VM list cache instance (creates new if None)

    Returns:
        List of VMInfo objects

    Raises:
        VMManagerError: If listing fails

    Example:
        >>> # Drop-in replacement for VMManager.list_vms()
        >>> vms = list_vms_parallel("azlin-rg")
        >>> print(f"Found {len(vms)} VMs")
    """
    # Create event loop if needed
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Run async operation
    manager = AsyncVMManager(resource_group, cache=cache)
    return loop.run_until_complete(manager.list_vms(include_stopped, filter_prefix))


def list_vms_parallel_with_stats(
    resource_group: str,
    include_stopped: bool = True,
    filter_prefix: str = "azlin",
    cache: VMListCache | None = None,
) -> tuple[list[VMInfo], ParallelListStats]:
    """List VMs with performance statistics (sync wrapper).

    Args:
        resource_group: Resource group name
        include_stopped: Include stopped/deallocated VMs
        filter_prefix: Filter VMs by name prefix
        cache: VM list cache instance (creates new if None)

    Returns:
        Tuple of (list of VMInfo objects, performance stats)

    Raises:
        VMManagerError: If listing fails

    Example:
        >>> vms, stats = list_vms_parallel_with_stats("azlin-rg")
        >>> print(f"Found {len(vms)} VMs in {stats.total_duration:.2f}s")
        >>> print(f"Cache hit rate: {stats.cache_hit_rate():.1%}")
    """
    # Create event loop if needed
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Run async operation
    manager = AsyncVMManager(resource_group, cache=cache)
    return loop.run_until_complete(manager.list_vms_with_stats(include_stopped, filter_prefix))


__all__ = [
    "AsyncVMManager",
    "ParallelListStats",
    "list_vms_parallel",
    "list_vms_parallel_with_stats",
]
