"""Custom code execution strategy.

Phase 4 Implementation (not yet implemented).

Generates and executes custom Python/shell scripts for objectives.
"""

from azlin.agentic.strategies.base_strategy import ExecutionStrategy
from azlin.agentic.types import (
    ExecutionContext,
    ExecutionResult,
    Strategy,
)


class CustomCodeStrategy(ExecutionStrategy):
    """Execute using custom generated code.

    Phase 4 will implement:
    - Generate Python/shell scripts via Claude
    - Execute in sandboxed environment
    - Parse output for resources
    - Handle errors and rollback

    Example (when implemented):
        >>> strategy = CustomCodeStrategy()
        >>> context = ExecutionContext(...)
        >>> if strategy.can_handle(context):
        ...     result = strategy.execute(context)
    """

    def can_handle(self, context: ExecutionContext) -> bool:
        """Check if custom code can handle this intent.

        TODO Phase 4:
        - Check Python/shell available
        - Check Azure SDK installed
        - Always returns True (fallback strategy)

        Args:
            context: Execution context

        Returns:
            True (can always generate custom code)

        Raises:
            NotImplementedError: Phase 4 not yet implemented
        """
        raise NotImplementedError("Phase 4 - Custom code strategy not yet implemented")

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute using custom generated code.

        TODO Phase 4:
        - Generate code via Claude API
        - Write to temp file
        - Execute via subprocess
        - Parse output

        Args:
            context: Execution context

        Returns:
            ExecutionResult

        Raises:
            NotImplementedError: Phase 4 not yet implemented
        """
        raise NotImplementedError("Phase 4 - Custom code execution not yet implemented")

    def validate(self, context: ExecutionContext) -> tuple[bool, str | None]:
        """Validate custom code prerequisites.

        TODO Phase 4:
        - Check Python >= 3.9
        - Check Azure SDK installed
        - Check Claude API key available

        Args:
            context: Execution context

        Returns:
            Tuple of (is_valid, error_message)

        Raises:
            NotImplementedError: Phase 4 not yet implemented
        """
        raise NotImplementedError("Phase 4 - Custom code validation not yet implemented")

    def estimate_duration(self, context: ExecutionContext) -> int:
        """Estimate custom code execution duration.

        TODO Phase 4:
        - Hard to estimate
        - Use conservative estimates
        - Add overhead for code generation

        Args:
            context: Execution context

        Returns:
            Estimated duration in seconds

        Raises:
            NotImplementedError: Phase 4 not yet implemented
        """
        raise NotImplementedError("Phase 4 - duration estimation not yet implemented")

    def get_strategy_type(self) -> Strategy:
        """Get strategy type.

        Returns:
            Strategy.CUSTOM_CODE
        """
        return Strategy.CUSTOM_CODE

    def get_prerequisites(self) -> list[str]:
        """Get custom code prerequisites.

        Returns:
            List of prerequisites
        """
        return [
            "Python >= 3.9",
            "Azure SDK for Python (azure-mgmt-*)",
            "ANTHROPIC_API_KEY for code generation",
        ]
