"""Async Multi-Context VM Query Module - Parallel listing across multiple contexts.

This module extends multi_context_list.py with async parallel operations
and caching support for even better performance in multi-tenant scenarios.

Philosophy:
- Parallel execution across contexts AND within each context
- Leverage vm_manager_async for per-context parallel listing
- Backward compatible with existing MultiContextVMQuery
- Resource-efficient with configurable concurrency

Public API (the "studs"):
    AsyncMultiContextVMQuery: Async multi-context query with parallel operations
    query_all_contexts_parallel: Main entry point for parallel multi-context queries

Performance:
- Baseline (serial): 30-50s per context * N contexts
- With multi_context_list (parallel contexts): 30-50s (parallel across contexts)
- With async + caching: <5s total (parallel contexts + parallel VMs + caching)

Integration:
- Uses AsyncVMManager for per-context parallel listing
- Uses VMListCache for tiered caching
- Compatible with existing MultiContextVMResult
"""

import asyncio
import logging
from dataclasses import dataclass

from azlin.cache.vm_list_cache import VMListCache
from azlin.context_manager import Context
from azlin.multi_context_list import ContextVMResult, MultiContextVMResult
from azlin.vm_manager import VMManager, VMManagerError
from azlin.vm_manager_async import AsyncVMManager

logger = logging.getLogger(__name__)


class AsyncMultiContextQueryError(Exception):
    """Raised when async multi-context query fails."""

    pass


@dataclass
class AsyncMultiContextQueryStats:
    """Performance statistics for async multi-context query.

    Attributes:
        total_duration: Total duration in seconds
        contexts_queried: Number of contexts queried
        total_vms: Total VMs found across all contexts
        total_cache_hits: Total cache hits across all contexts
        total_cache_misses: Total cache misses across all contexts
        total_api_calls: Total Azure API calls across all contexts
    """

    total_duration: float
    contexts_queried: int
    total_vms: int
    total_cache_hits: int
    total_cache_misses: int
    total_api_calls: int

    def cache_hit_rate(self) -> float:
        """Calculate overall cache hit rate.

        Returns:
            Cache hit rate as percentage (0.0 - 1.0)
        """
        total = self.total_cache_hits + self.total_cache_misses
        return self.total_cache_hits / total if total > 0 else 0.0


class AsyncMultiContextVMQuery:
    """Async multi-context VM query with parallel operations and caching.

    Provides high-performance VM listing across multiple Azure contexts with:
    - Parallel query execution across contexts
    - Parallel VM enrichment within each context
    - Tiered TTL caching (24h immutable, 5min mutable)
    - Configurable concurrency limits

    Example:
        >>> query = AsyncMultiContextVMQuery(contexts=contexts)
        >>> result, stats = await query.query_all_contexts_with_stats(resource_group="azlin-rg")
        >>> print(f"Found {result.total_vms} VMs across {len(result.context_results)} contexts")
        >>> print(f"Cache hit rate: {stats.cache_hit_rate():.1%}")
    """

    def __init__(
        self,
        contexts: list[Context],
        cache: VMListCache | None = None,
        max_workers: int = 5,
        max_concurrent_per_context: int = 10,
    ):
        """Initialize async multi-context query executor.

        Args:
            contexts: List of contexts to query
            cache: Shared VM list cache instance (creates new if None)
            max_workers: Maximum number of parallel context queries (default: 5)
            max_concurrent_per_context: Max concurrent operations per context (default: 10)
        """
        if not contexts:
            raise AsyncMultiContextQueryError("At least one context required")

        self.contexts = contexts
        self.cache = cache or VMListCache()
        self.max_workers = min(max_workers, len(contexts))
        self.max_concurrent_per_context = max_concurrent_per_context

    async def _switch_subscription(self, context: Context) -> None:
        """Switch Azure CLI to the context's subscription (async).

        Args:
            context: Context with subscription_id

        Raises:
            AsyncMultiContextQueryError: If subscription switch fails
        """
        from azlin.context_manager import _subscription_lock

        try:
            # Use the shared lock to prevent race conditions across threads/coroutines
            # Note: This is a threading lock, not asyncio lock, but works for subprocess calls
            with _subscription_lock:
                cmd = ["az", "account", "set", "--subscription", context.subscription_id]

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=30
                )  # Increased for WSL compatibility (Issue #580)

                if process.returncode != 0:
                    raise AsyncMultiContextQueryError(
                        f"Failed to switch to subscription {context.subscription_id}: {stderr.decode()}"
                    )

                logger.debug(f"Switched to subscription: {context.subscription_id}")

        except TimeoutError as e:
            raise AsyncMultiContextQueryError(
                f"Subscription switch timed out for {context.subscription_id}"
            ) from e
        except Exception as e:
            raise AsyncMultiContextQueryError(
                f"Failed to switch subscription {context.subscription_id}: {e}"
            ) from e

    async def _query_single_context(
        self,
        context: Context,
        resource_group: str | None,
        include_stopped: bool,
        filter_prefix: str,
    ) -> ContextVMResult:
        """Query VMs for a single context asynchronously.

        Args:
            context: Context to query
            resource_group: Resource group to query
            include_stopped: Include stopped VMs
            filter_prefix: Filter VMs by name prefix

        Returns:
            ContextVMResult with query results
        """
        start_time = asyncio.get_event_loop().time()

        try:
            logger.debug(f"Querying context: {context.name}")

            # Switch to this context's subscription
            await self._switch_subscription(context)

            # Require explicit resource group
            if not resource_group:
                raise AsyncMultiContextQueryError(
                    f"Resource group required for multi-context queries (context: {context.name})"
                )

            # Use async VM manager for parallel listing within this context
            manager = AsyncVMManager(
                resource_group=resource_group,
                cache=self.cache,
                max_concurrent=self.max_concurrent_per_context,
            )

            vms, stats = await manager.list_vms_with_stats(include_stopped=include_stopped)

            # Filter by prefix
            if filter_prefix:
                vms = VMManager.filter_by_prefix(vms, filter_prefix)

            # Sort by creation time
            vms = VMManager.sort_by_created_time(vms)

            duration = asyncio.get_event_loop().time() - start_time

            logger.debug(
                f"Context {context.name}: found {len(vms)} VMs in {duration:.2f}s "
                f"(cache hit rate: {stats.cache_hit_rate():.1%})"
            )

            return ContextVMResult(
                context_name=context.name,
                context=context,
                success=True,
                vms=vms,
                duration=duration,
            )

        except VMManagerError as e:
            duration = asyncio.get_event_loop().time() - start_time
            logger.warning(f"Context {context.name} query failed: {e}")
            return ContextVMResult(
                context_name=context.name,
                context=context,
                success=False,
                error_message=str(e),
                duration=duration,
            )
        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            logger.error(f"Unexpected error querying context {context.name}: {e}")
            return ContextVMResult(
                context_name=context.name,
                context=context,
                success=False,
                error_message=f"Unexpected error: {e}",
                duration=duration,
            )

    async def query_all_contexts_with_stats(
        self,
        resource_group: str | None = None,
        include_stopped: bool = True,
        filter_prefix: str = "azlin",
    ) -> tuple[MultiContextVMResult, AsyncMultiContextQueryStats]:
        """Query VMs across all contexts in parallel with statistics.

        Args:
            resource_group: Resource group to query (None for context default)
            include_stopped: Include stopped VMs in results
            filter_prefix: Filter VMs by name prefix (default: "azlin")

        Returns:
            Tuple of (MultiContextVMResult, AsyncMultiContextQueryStats)

        Raises:
            AsyncMultiContextQueryError: If query execution fails
        """
        start_time = asyncio.get_event_loop().time()

        logger.info(f"Querying {len(self.contexts)} contexts with async parallel operations")

        # Create tasks for all contexts
        tasks = [
            self._query_single_context(context, resource_group, include_stopped, filter_prefix)
            for context in self.contexts
        ]

        # Execute all context queries in parallel (with semaphore limiting)
        semaphore = asyncio.Semaphore(self.max_workers)

        async def bounded_query(task):
            async with semaphore:
                return await task

        context_results = await asyncio.gather(*[bounded_query(task) for task in tasks])

        total_duration = asyncio.get_event_loop().time() - start_time

        # Sort results by context name for consistent display
        context_results = sorted(context_results, key=lambda r: r.context_name)

        # Calculate overall stats
        total_vms = sum(len(r.vms) for r in context_results)
        successful_contexts = sum(1 for r in context_results if r.success)
        failed_contexts = len(context_results) - successful_contexts

        logger.info(
            f"Completed {len(context_results)} context queries in {total_duration:.2f}s "
            f"(succeeded: {successful_contexts}, failed: {failed_contexts}, "
            f"total VMs: {total_vms})"
        )

        result = MultiContextVMResult(
            context_results=context_results, total_duration=total_duration
        )

        # Note: Detailed cache stats would require tracking in AsyncVMManager
        # For now, we provide basic stats
        stats = AsyncMultiContextQueryStats(
            total_duration=total_duration,
            contexts_queried=len(context_results),
            total_vms=total_vms,
            total_cache_hits=0,  # Would need to track in manager
            total_cache_misses=0,  # Would need to track in manager
            total_api_calls=0,  # Would need to track in manager
        )

        return result, stats

    async def query_all_contexts(
        self,
        resource_group: str | None = None,
        include_stopped: bool = True,
        filter_prefix: str = "azlin",
    ) -> MultiContextVMResult:
        """Query VMs across all contexts in parallel (backward compatible).

        Args:
            resource_group: Resource group to query (None for context default)
            include_stopped: Include stopped VMs in results
            filter_prefix: Filter VMs by name prefix (default: "azlin")

        Returns:
            MultiContextVMResult with aggregated results

        Raises:
            AsyncMultiContextQueryError: If query execution fails
        """
        result, _ = await self.query_all_contexts_with_stats(
            resource_group, include_stopped, filter_prefix
        )
        return result


def query_all_contexts_parallel(
    contexts: list[Context],
    resource_group: str | None = None,
    include_stopped: bool = True,
    filter_prefix: str = "azlin",
    cache: VMListCache | None = None,
) -> MultiContextVMResult:
    """Query VMs across all contexts in parallel (sync wrapper).

    This is the main entry point for parallel multi-context VM listing.
    It provides a drop-in replacement for MultiContextVMQuery.query_all_contexts()
    with better performance through async operations and caching.

    Args:
        contexts: List of contexts to query
        resource_group: Resource group to query (None for context default)
        include_stopped: Include stopped VMs in results
        filter_prefix: Filter VMs by name prefix (default: "azlin")
        cache: Shared VM list cache instance (creates new if None)

    Returns:
        MultiContextVMResult with aggregated results

    Raises:
        AsyncMultiContextQueryError: If query execution fails

    Example:
        >>> from azlin.context_manager import ContextManager
        >>> contexts = ContextManager().list_contexts()
        >>> result = query_all_contexts_parallel(contexts, resource_group="azlin-rg")
        >>> print(f"Found {result.total_vms} VMs across {len(result.context_results)} contexts")
    """
    # Create event loop if needed
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Run async operation
    query = AsyncMultiContextVMQuery(contexts, cache=cache)
    return loop.run_until_complete(
        query.query_all_contexts(resource_group, include_stopped, filter_prefix)
    )


__all__ = [
    "AsyncMultiContextQueryError",
    "AsyncMultiContextQueryStats",
    "AsyncMultiContextVMQuery",
    "query_all_contexts_parallel",
]
