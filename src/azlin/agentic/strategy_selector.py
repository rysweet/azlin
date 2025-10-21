"""Strategy selection for azdoit execution.

Phase 2 Implementation (not yet implemented).

Selects optimal execution strategy with fallback chain based on:
- Intent type
- Available tools (az cli, terraform, etc.)
- Resource prerequisites
- Cost considerations
"""

from azlin.agentic.types import Intent, Strategy, StrategyPlan


class StrategySelector:
    """Selects optimal execution strategy with fallbacks.

    Phase 2 will implement:
    - PrerequisiteChecker integration
    - Priority rules: CLI > Terraform > MCP > Custom
    - Fallback chain building
    - Tool availability detection

    Example (when implemented):
        >>> selector = StrategySelector()
        >>> intent = Intent(...)
        >>> plan = selector.select(intent)
        >>> print(plan.primary_strategy)
        Strategy.AZURE_CLI
    """

    @staticmethod
    def select(
        intent: Intent,
        available_tools: list[str] | None = None,
    ) -> StrategyPlan:
        """Select best strategy for intent.

        TODO Phase 2:
        - Check prerequisites (PrerequisiteChecker)
        - Apply priority rules: CLI > Terraform > MCP > Custom
        - Build fallback chain
        - Return StrategyPlan with reasoning

        Args:
            intent: Parsed intent from IntentParser
            available_tools: List of available tools (default: auto-detect)

        Returns:
            StrategyPlan with primary and fallback strategies

        Raises:
            NotImplementedError: Phase 2 not yet implemented
        """
        raise NotImplementedError("Phase 2 - strategy selection not yet implemented")

    @staticmethod
    def get_available_strategies() -> list[Strategy]:
        """Get list of available strategies.

        TODO Phase 2:
        - Detect installed tools (az cli, terraform, etc.)
        - Check authentication status
        - Return list of usable strategies

        Returns:
            List of available Strategy enums

        Raises:
            NotImplementedError: Phase 2 not yet implemented
        """
        raise NotImplementedError("Phase 2 - tool detection not yet implemented")

    @staticmethod
    def validate_prerequisites(strategy: Strategy) -> tuple[bool, str | None]:
        """Validate prerequisites for a strategy.

        TODO Phase 2:
        - Check tool installation
        - Verify authentication
        - Check permissions

        Args:
            strategy: Strategy to validate

        Returns:
            Tuple of (is_valid, error_message)

        Raises:
            NotImplementedError: Phase 2 not yet implemented
        """
        raise NotImplementedError("Phase 2 - prerequisite validation not yet implemented")
