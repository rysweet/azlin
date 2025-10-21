"""Azure CLI strategy implementation.

Phase 2 Implementation (not yet implemented).

Executes objectives using Azure CLI commands.
"""

from azlin.agentic.strategies.base_strategy import ExecutionStrategy
from azlin.agentic.types import (
    ExecutionContext,
    ExecutionResult,
    Strategy,
)


class AzureCLIStrategy(ExecutionStrategy):
    """Execute using Azure CLI commands.

    Phase 2 will implement:
    - Generate az cli commands from intent
    - Execute commands via subprocess
    - Parse output and track resources
    - Handle authentication

    Example (when implemented):
        >>> strategy = AzureCLIStrategy()
        >>> context = ExecutionContext(...)
        >>> if strategy.can_handle(context):
        ...     result = strategy.execute(context)
    """

    def can_handle(self, context: ExecutionContext) -> bool:
        """Check if Azure CLI can handle this intent.

        TODO Phase 2:
        - Check if az cli is installed
        - Verify authentication
        - Check if intent maps to CLI commands

        Args:
            context: Execution context

        Returns:
            True if CLI can handle

        Raises:
            NotImplementedError: Phase 2 not yet implemented
        """
        raise NotImplementedError("Phase 2 - Azure CLI strategy not yet implemented")

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute using Azure CLI.

        TODO Phase 2:
        - Generate CLI commands
        - Execute via subprocess
        - Parse output
        - Track created resources

        Args:
            context: Execution context

        Returns:
            ExecutionResult

        Raises:
            NotImplementedError: Phase 2 not yet implemented
        """
        raise NotImplementedError("Phase 2 - Azure CLI execution not yet implemented")

    def validate(self, context: ExecutionContext) -> tuple[bool, str | None]:
        """Validate Azure CLI prerequisites.

        TODO Phase 2:
        - Check az cli installed
        - Verify authentication (az account show)
        - Check required permissions

        Args:
            context: Execution context

        Returns:
            Tuple of (is_valid, error_message)

        Raises:
            NotImplementedError: Phase 2 not yet implemented
        """
        raise NotImplementedError("Phase 2 - Azure CLI validation not yet implemented")

    def estimate_duration(self, context: ExecutionContext) -> int:
        """Estimate CLI execution duration.

        TODO Phase 2:
        - Estimate based on resource types
        - VM provisioning: ~300s
        - AKS cluster: ~600s
        - Simple operations: ~30s

        Args:
            context: Execution context

        Returns:
            Estimated duration in seconds

        Raises:
            NotImplementedError: Phase 2 not yet implemented
        """
        raise NotImplementedError("Phase 2 - duration estimation not yet implemented")

    def get_strategy_type(self) -> Strategy:
        """Get strategy type.

        Returns:
            Strategy.AZURE_CLI
        """
        return Strategy.AZURE_CLI

    def get_prerequisites(self) -> list[str]:
        """Get Azure CLI prerequisites.

        Returns:
            List of prerequisites
        """
        return [
            "azure-cli >= 2.50.0",
            "Authenticated Azure account (az login)",
            "Active Azure subscription",
        ]
