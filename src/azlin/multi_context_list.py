"""Multi-context VM query module.

This module provides parallel VM listing across multiple Azure contexts.
It executes VM queries concurrently using ThreadPoolExecutor and aggregates
results with proper error handling.

Features:
- Parallel query execution across multiple contexts
- Per-context error handling (one failure doesn't break others)
- Authentication switching between contexts
- Result aggregation with context metadata
- Cost tracking per context

Architecture:
- MultiContextVMQuery class for query orchestration
- ThreadPoolExecutor for parallel execution (pattern from batch_executor.py)
- CredentialFactory for per-context authentication
- VMManager for VM listing (reused)

Example Usage:
    >>> query = MultiContextVMQuery(contexts=contexts)
    >>> result = query.query_all_contexts(resource_group="azlin-rg")
    >>> for ctx_result in result.context_results:
    ...     print(f"{ctx_result.context_name}: {len(ctx_result.vms)} VMs")
"""

import logging
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from azlin.context_manager import Context
from azlin.vm_manager import VMInfo, VMManager, VMManagerError

logger = logging.getLogger(__name__)


class MultiContextQueryError(Exception):
    """Raised when multi-context query fails."""

    pass


@dataclass
class ContextVMResult:
    """Result of VM query for a single context.

    Attributes:
        context_name: Name of the context
        context: The Context object
        success: Whether query succeeded
        vms: List of VMs found (empty if failed)
        error_message: Error message if failed (None if succeeded)
        duration: Query duration in seconds
        total_cost: Estimated total cost for all VMs (optional)
    """

    context_name: str
    context: Context
    success: bool
    vms: list[VMInfo] = field(default_factory=list)
    error_message: str | None = None
    duration: float = 0.0
    total_cost: float | None = None

    @property
    def vm_count(self) -> int:
        """Get number of VMs found."""
        return len(self.vms)

    @property
    def running_count(self) -> int:
        """Get number of running VMs."""
        return sum(1 for vm in self.vms if vm.is_running())

    @property
    def stopped_count(self) -> int:
        """Get number of stopped VMs."""
        return sum(1 for vm in self.vms if vm.is_stopped())


@dataclass
class MultiContextVMResult:
    """Aggregated results from multi-context VM query.

    Attributes:
        context_results: List of per-context results
        total_duration: Total query duration in seconds
    """

    context_results: list[ContextVMResult] = field(default_factory=list)
    total_duration: float = 0.0

    @property
    def total_vms(self) -> int:
        """Get total number of VMs across all contexts."""
        return sum(r.vm_count for r in self.context_results)

    @property
    def total_running(self) -> int:
        """Get total number of running VMs."""
        return sum(r.running_count for r in self.context_results)

    @property
    def total_stopped(self) -> int:
        """Get total number of stopped VMs."""
        return sum(r.stopped_count for r in self.context_results)

    @property
    def successful_contexts(self) -> int:
        """Get number of successfully queried contexts."""
        return sum(1 for r in self.context_results if r.success)

    @property
    def failed_contexts(self) -> int:
        """Get number of failed contexts."""
        return sum(1 for r in self.context_results if not r.success)

    @property
    def all_succeeded(self) -> bool:
        """Check if all context queries succeeded."""
        return all(r.success for r in self.context_results) if self.context_results else True

    def get_failures(self) -> list[ContextVMResult]:
        """Get only failed context results."""
        return [r for r in self.context_results if not r.success]

    def get_successes(self) -> list[ContextVMResult]:
        """Get only successful context results."""
        return [r for r in self.context_results if r.success]


class MultiContextVMQuery:
    """Query VMs across multiple Azure contexts in parallel.

    This class orchestrates VM listing across multiple contexts using
    ThreadPoolExecutor for parallel execution. Each context is queried
    independently with proper error handling.

    Philosophy:
    - Parallel execution: Query all contexts concurrently
    - Fault tolerance: One failure doesn't break others
    - Resource limits: Configurable max_workers
    - Clean authentication: Switch contexts per query
    """

    def __init__(self, contexts: list[Context], max_workers: int = 5):
        """Initialize multi-context query executor.

        Args:
            contexts: List of contexts to query
            max_workers: Maximum number of parallel workers (default: 5)
        """
        if not contexts:
            raise MultiContextQueryError("At least one context required")

        self.contexts = contexts
        self.max_workers = min(max_workers, len(contexts))  # Don't spawn unnecessary workers

    def query_all_contexts(
        self,
        resource_group: str | None = None,
        include_stopped: bool = True,
        filter_prefix: str = "azlin",
    ) -> MultiContextVMResult:
        """Query VMs across all contexts in parallel.

        Args:
            resource_group: Resource group to query (None for context default)
            include_stopped: Include stopped VMs in results
            filter_prefix: Filter VMs by name prefix (default: "azlin")

        Returns:
            MultiContextVMResult with aggregated results

        Raises:
            MultiContextQueryError: If query execution fails

        Example:
            >>> query = MultiContextVMQuery(contexts=contexts)
            >>> result = query.query_all_contexts(resource_group="azlin-rg")
            >>> print(f"Found {result.total_vms} VMs across {len(result.context_results)} contexts")
        """
        start_time = time.time()

        logger.info(f"Querying {len(self.contexts)} contexts with {self.max_workers} workers")

        # Execute queries in parallel
        context_results: list[ContextVMResult] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all context queries
            future_to_context = {
                executor.submit(
                    self._query_single_context,
                    context,
                    resource_group,
                    include_stopped,
                    filter_prefix,
                ): context
                for context in self.contexts
            }

            # Collect results as they complete
            for future in as_completed(future_to_context):
                context = future_to_context[future]
                try:
                    result = future.result()
                    context_results.append(result)
                except Exception as e:
                    # This should rarely happen as _query_single_context handles errors
                    logger.error(f"Unexpected error querying context {context.name}: {e}")
                    context_results.append(
                        ContextVMResult(
                            context_name=context.name,
                            context=context,
                            success=False,
                            error_message=f"Unexpected error: {e}",
                        )
                    )

        total_duration = time.time() - start_time

        # Sort results by context name for consistent display
        context_results.sort(key=lambda r: r.context_name)

        logger.info(
            f"Completed {len(context_results)} context queries in {total_duration:.2f}s "
            f"(succeeded: {sum(1 for r in context_results if r.success)}, "
            f"failed: {sum(1 for r in context_results if not r.success)})"
        )

        return MultiContextVMResult(context_results=context_results, total_duration=total_duration)

    def _query_single_context(
        self,
        context: Context,
        resource_group: str | None,
        include_stopped: bool,
        filter_prefix: str,
    ) -> ContextVMResult:
        """Query VMs for a single context.

        This method handles authentication switching, VM listing, and error handling
        for a single context.

        Args:
            context: Context to query
            resource_group: Resource group to query
            include_stopped: Include stopped VMs
            filter_prefix: Filter VMs by name prefix

        Returns:
            ContextVMResult with query results
        """
        start_time = time.time()

        try:
            logger.debug(f"Querying context: {context.name}")

            # Switch to this context's subscription
            self._switch_subscription(context)

            # Determine resource group
            # For multi-context queries, we need a resource group
            # In the future, this could support context-level RG configuration
            if not resource_group:
                # Try to infer from context tags or use a default
                # For now, require explicit resource group
                raise MultiContextQueryError(
                    f"Resource group required for multi-context queries (context: {context.name})"
                )

            # Query VMs
            vms = VMManager.list_vms(resource_group, include_stopped=include_stopped)

            # Filter by prefix
            if filter_prefix:
                vms = VMManager.filter_by_prefix(vms, filter_prefix)

            # Sort by creation time
            vms = VMManager.sort_by_created_time(vms)

            duration = time.time() - start_time

            logger.debug(f"Context {context.name}: found {len(vms)} VMs in {duration:.2f}s")

            return ContextVMResult(
                context_name=context.name,
                context=context,
                success=True,
                vms=vms,
                duration=duration,
            )

        except VMManagerError as e:
            duration = time.time() - start_time
            logger.warning(f"Context {context.name} query failed: {e}")
            return ContextVMResult(
                context_name=context.name,
                context=context,
                success=False,
                error_message=str(e),
                duration=duration,
            )
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Unexpected error querying context {context.name}: {e}")
            return ContextVMResult(
                context_name=context.name,
                context=context,
                success=False,
                error_message=f"Unexpected error: {e}",
                duration=duration,
            )

    def _switch_subscription(self, context: Context) -> None:
        """Switch Azure CLI to the context's subscription.

        Uses ContextManager's thread-safe subscription switching to prevent
        race conditions when multiple threads query different contexts.

        Args:
            context: Context with subscription_id

        Raises:
            MultiContextQueryError: If subscription switch fails
        """
        from azlin.context_manager import _subscription_lock

        try:
            # Use the shared lock to prevent race conditions across threads
            with _subscription_lock:
                # Use Azure CLI to switch subscription
                cmd = ["az", "account", "set", "--subscription", context.subscription_id]

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)  # Increased for WSL compatibility (Issue #580)

                logger.debug(f"Switched to subscription: {context.subscription_id}")

        except subprocess.CalledProcessError as e:
            raise MultiContextQueryError(
                f"Failed to switch to subscription {context.subscription_id}: {e.stderr}"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise MultiContextQueryError(
                f"Subscription switch timed out for {context.subscription_id}"
            ) from e


__all__ = [
    "ContextVMResult",
    "MultiContextQueryError",
    "MultiContextVMQuery",
    "MultiContextVMResult",
]
