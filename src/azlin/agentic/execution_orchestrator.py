"""Execution orchestrator with fallback and retry logic.

Manages the full execution lifecycle including:
- Strategy fallback chain execution
- Retry logic with exponential backoff
- Partial rollback on failure
- Execution state management
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from azlin.agentic.strategies.aws_strategy import AWSStrategy
from azlin.agentic.strategies.azure_cli import AzureCLIStrategy
from azlin.agentic.strategies.gcp_strategy import GCPStrategy
from azlin.agentic.strategies.mcp_client_strategy import MCPClientStrategy
from azlin.agentic.strategies.terraform_strategy import TerraformStrategy
from azlin.agentic.types import (
    ExecutionContext,
    ExecutionResult,
    FailureType,
    Strategy,
    StrategyPlan,
)

logger = logging.getLogger(__name__)


class ExecutionOrchestratorError(Exception):
    """Error raised by execution orchestrator for internal failures."""

    pass


class RetryDecision(str, Enum):
    """Decision on whether to retry after a failure."""

    RETRY_SAME = "retry_same"  # Retry with same strategy
    RETRY_FALLBACK = "retry_fallback"  # Try fallback strategy
    ABORT = "abort"  # Give up


@dataclass
class ExecutionAttempt:
    """Record of a single execution attempt.

    Attributes:
        strategy: Strategy used
        result: Execution result
        attempt_number: Which attempt this was (1-indexed)
        timestamp: When this attempt started
        duration_seconds: How long it took
    """

    strategy: Strategy
    result: ExecutionResult
    attempt_number: int
    timestamp: float
    duration_seconds: float


class ExecutionOrchestrator:
    """Orchestrates execution with fallback and retry logic.

    Manages the full execution lifecycle:
    1. Try primary strategy
    2. On failure, classify and decide retry/fallback
    3. Execute fallback chain if needed
    4. Rollback partial changes on failure
    5. Track all attempts for debugging

    Example:
        >>> orchestrator = ExecutionOrchestrator(max_retries=3)
        >>> result = orchestrator.execute(context, strategy_plan)
        >>> if not result.success:
        ...     print(f"Failed after {len(orchestrator.attempts)} attempts")
    """

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay_base: float = 2.0,
        enable_rollback: bool = True,
    ):
        """Initialize execution orchestrator.

        Args:
            max_retries: Maximum retry attempts per strategy
            retry_delay_base: Base delay for exponential backoff (seconds)
            enable_rollback: Whether to rollback on failure
        """
        self.max_retries = max_retries
        self.retry_delay_base = retry_delay_base
        self.enable_rollback = enable_rollback
        self.attempts: list[ExecutionAttempt] = []

        # Strategy instance cache
        self._strategy_cache: dict[Strategy, Any] = {}

    def execute(
        self,
        context: ExecutionContext,
        strategy_plan: StrategyPlan,
    ) -> ExecutionResult:
        """Execute with fallback and retry logic.

        Args:
            context: Execution context
            strategy_plan: Strategy plan with fallback chain

        Returns:
            Final execution result (success or final failure)

        Example:
            >>> result = orchestrator.execute(context, plan)
            >>> if result.success:
            ...     print("Success!")
            >>> else:
            ...     print(f"All strategies failed: {result.error}")
        """
        # Build strategy chain: primary + fallbacks
        strategy_chain = [strategy_plan.primary_strategy, *strategy_plan.fallback_strategies]

        logger.info(
            "Starting execution with %d strategies in chain",
            len(strategy_chain),
        )

        # Try each strategy in the chain
        for strategy_type in strategy_chain:
            logger.info("Attempting execution with strategy: %s", strategy_type.value)

            # Try this strategy with retries
            result = self._execute_with_retry(context, strategy_type)

            if result.success:
                logger.info(
                    "Execution succeeded with %s after %d total attempts",
                    strategy_type.value,
                    len(self.attempts),
                )
                return result

            # Failed - check if we should try next strategy
            decision = self._should_retry_or_fallback(result, strategy_chain, strategy_type)

            if (
                decision == RetryDecision.RETRY_FALLBACK
                and strategy_chain.index(strategy_type) < len(strategy_chain) - 1
            ):
                logger.info(
                    "Strategy %s failed, trying fallback",
                    strategy_type.value,
                )
                continue

            if decision == RetryDecision.ABORT:
                logger.error(
                    "Aborting execution after %s failure: %s",
                    strategy_type.value,
                    result.error,
                )
                break

        # All strategies failed
        final_result = self.attempts[-1].result if self.attempts else result

        # Attempt rollback if enabled
        if self.enable_rollback and final_result.resources_created:
            logger.info("Attempting rollback of %d resources", len(final_result.resources_created))
            self._rollback(context, final_result)

        # Add metadata about all attempts
        final_result.metadata = final_result.metadata or {}
        final_result.metadata["total_attempts"] = len(self.attempts)
        final_result.metadata["strategies_tried"] = [
            attempt.strategy.value for attempt in self.attempts
        ]

        return final_result

    def _execute_with_retry(
        self,
        context: ExecutionContext,
        strategy_type: Strategy,
    ) -> ExecutionResult:
        """Execute with exponential backoff retry.

        Args:
            context: Execution context
            strategy_type: Strategy to use

        Returns:
            Execution result (success or final failure)
        """
        strategy = self._get_strategy(strategy_type)

        for attempt_num in range(1, self.max_retries + 1):
            logger.debug(
                "Attempt %d/%d with %s", attempt_num, self.max_retries, strategy_type.value
            )

            # Update context with attempt number
            context_copy = context
            start_time = time.time()

            # Execute
            result = strategy.execute(context_copy)
            duration = time.time() - start_time

            # Record attempt
            attempt = ExecutionAttempt(
                strategy=strategy_type,
                result=result,
                attempt_number=attempt_num,
                timestamp=start_time,
                duration_seconds=duration,
            )
            self.attempts.append(attempt)

            if result.success:
                return result

            # Failed - check if retriable
            is_retriable = self._is_retriable_failure(result.failure_type)

            if not is_retriable or attempt_num >= self.max_retries:
                logger.warning(
                    "Strategy %s failed (attempt %d/%d): %s",
                    strategy_type.value,
                    attempt_num,
                    self.max_retries,
                    result.error,
                )
                return result

            # Calculate backoff delay
            delay = self.retry_delay_base**attempt_num
            logger.info(
                "Retriable failure, waiting %.1f seconds before retry %d",
                delay,
                attempt_num + 1,
            )
            time.sleep(delay)

        # Should not reach here, but return last result
        return result

    def _get_strategy(self, strategy_type: Strategy) -> Any:
        """Get strategy instance (cached).

        Args:
            strategy_type: Strategy type

        Returns:
            Strategy instance

        Raises:
            ExecutionOrchestratorError: If strategy type is not implemented
        """
        if strategy_type not in self._strategy_cache:
            if strategy_type == Strategy.AZURE_CLI:
                self._strategy_cache[strategy_type] = AzureCLIStrategy()
            elif strategy_type == Strategy.TERRAFORM:
                self._strategy_cache[strategy_type] = TerraformStrategy()
            elif strategy_type == Strategy.AWS_CLI:
                self._strategy_cache[strategy_type] = AWSStrategy()
            elif strategy_type == Strategy.GCP_CLI:
                self._strategy_cache[strategy_type] = GCPStrategy()
            elif strategy_type == Strategy.MCP_CLIENT:
                self._strategy_cache[strategy_type] = MCPClientStrategy()
            elif strategy_type == Strategy.CUSTOM_CODE:
                # CUSTOM_CODE strategy is not yet implemented
                # This is a valid enum value but requires user-provided code execution
                msg = (
                    f"Strategy {strategy_type.value} is not yet implemented. "
                    "Custom code execution requires additional security considerations."
                )
                logger.error(msg)
                raise ExecutionOrchestratorError(msg)
            else:
                # This should never happen if all Strategy enum values are handled above
                # If you see this error, a new Strategy was added to the enum but not implemented here
                msg = (
                    f"Invalid strategy type: {strategy_type.value}. "
                    "This is a bug - please report it at https://github.com/rynop/azlin/issues"
                )
                logger.error(msg)
                raise ExecutionOrchestratorError(msg)

        return self._strategy_cache[strategy_type]

    def _is_retriable_failure(self, failure_type: FailureType | None) -> bool:
        """Check if failure type is retriable.

        Args:
            failure_type: Type of failure

        Returns:
            True if should retry
        """
        if failure_type is None:
            return False

        # Retriable failures (transient issues)
        retriable = {
            FailureType.TIMEOUT,
            FailureType.NETWORK_ERROR,
        }

        # Non-retriable failures (permanent issues)
        non_retriable = {
            FailureType.VALIDATION_ERROR,
            FailureType.PERMISSION_DENIED,
            FailureType.QUOTA_EXCEEDED,
            FailureType.RESOURCE_NOT_FOUND,
        }

        if failure_type in retriable:
            return True
        return failure_type not in non_retriable  # Unknown failure - retry cautiously

    def _should_retry_or_fallback(
        self,
        result: ExecutionResult,
        strategy_chain: list[Strategy],
        current_strategy: Strategy,
    ) -> RetryDecision:
        """Decide whether to retry, fallback, or abort.

        Args:
            result: Execution result
            strategy_chain: Full strategy chain
            current_strategy: Current strategy

        Returns:
            RetryDecision
        """
        # Check if there are more strategies to try
        current_index = strategy_chain.index(current_strategy)
        has_fallback = current_index < len(strategy_chain) - 1

        # Non-retriable errors should try fallback if available
        if result.failure_type in {
            FailureType.VALIDATION_ERROR,
            FailureType.PERMISSION_DENIED,
        }:
            return RetryDecision.RETRY_FALLBACK if has_fallback else RetryDecision.ABORT

        # Quota exceeded - abort (no point retrying or falling back)
        if result.failure_type == FailureType.QUOTA_EXCEEDED:
            return RetryDecision.ABORT

        # Retriable errors were already retried in _execute_with_retry
        # If we're here, retries failed, so try fallback
        return RetryDecision.RETRY_FALLBACK if has_fallback else RetryDecision.ABORT

    def _rollback(self, context: ExecutionContext, result: ExecutionResult) -> None:
        """Attempt to rollback partial changes.

        Args:
            context: Execution context
            result: Execution result with partial resources
        """
        if not result.resources_created:
            return

        logger.info("Rolling back %d partially created resources", len(result.resources_created))

        # Get cleanup strategy (prefer Azure CLI for rollback)
        cleanup_strategy = self._get_strategy(Strategy.AZURE_CLI)

        try:
            cleanup_strategy.cleanup_on_failure(context, result.resources_created)
            logger.info("Rollback completed successfully")
        except Exception:
            logger.exception("Rollback failed - manual cleanup may be required")

    def get_execution_summary(self) -> dict[str, Any]:
        """Get summary of all execution attempts.

        Returns:
            Summary dictionary
        """
        if not self.attempts:
            return {"total_attempts": 0, "strategies_tried": []}

        return {
            "total_attempts": len(self.attempts),
            "strategies_tried": [a.strategy.value for a in self.attempts],
            "total_duration": sum(a.duration_seconds for a in self.attempts),
            "success": self.attempts[-1].result.success,
            "final_strategy": self.attempts[-1].strategy.value,
            "retries_per_strategy": self._count_retries_per_strategy(),
        }

    def _count_retries_per_strategy(self) -> dict[str, int]:
        """Count retry attempts per strategy.

        Returns:
            Dictionary mapping strategy to retry count
        """
        counts: dict[str, int] = {}
        for attempt in self.attempts:
            strategy_name = attempt.strategy.value
            counts[strategy_name] = counts.get(strategy_name, 0) + 1
        return counts
