"""Base strategy abstract class for azdoit execution.

All execution strategies must inherit from ExecutionStrategy and implement
the required methods.
"""

from abc import ABC, abstractmethod
from typing import Any

from azlin.agentic.types import (
    ExecutionContext,
    ExecutionResult,
    Strategy,
)


class ExecutionStrategy(ABC):
    """Abstract base class for execution strategies.

    Each strategy implements a different approach to executing Azure operations:
    - AzureCLIStrategy: Direct azure-cli commands
    - TerraformStrategy: Generate and apply Terraform configs
    - CustomCodeStrategy: Custom Python/shell scripts

    Example:
        >>> class MyStrategy(ExecutionStrategy):
        ...     def can_handle(self, context: ExecutionContext) -> bool:
        ...         return context.intent.intent == "provision_vm"
        ...
        ...     def execute(self, context: ExecutionContext) -> ExecutionResult:
        ...         # Implementation here
        ...         return ExecutionResult(success=True, strategy=Strategy.AZURE_CLI)
    """

    @abstractmethod
    def can_handle(self, context: ExecutionContext) -> bool:
        """Check if this strategy can handle the given context.

        Args:
            context: Execution context with intent and metadata

        Returns:
            True if this strategy can execute the intent

        Example:
            >>> strategy = AzureCLIStrategy()
            >>> context = ExecutionContext(...)
            >>> if strategy.can_handle(context):
            ...     result = strategy.execute(context)
        """
        pass

    @abstractmethod
    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute the objective using this strategy.

        This method should:
        1. Validate prerequisites
        2. Execute the required operations
        3. Track created resources
        4. Handle errors appropriately
        5. Return comprehensive result

        Args:
            context: Execution context with all necessary information

        Returns:
            ExecutionResult with success status and details

        Raises:
            ExecutionError: If execution fails critically

        Example:
            >>> strategy = TerraformStrategy()
            >>> context = ExecutionContext(
            ...     objective_id="obj_20251020_001",
            ...     intent=Intent(...),
            ...     strategy=Strategy.TERRAFORM,
            ... )
            >>> result = strategy.execute(context)
            >>> if result.success:
            ...     print(f"Created: {result.resources_created}")
        """
        pass

    @abstractmethod
    def validate(self, context: ExecutionContext) -> tuple[bool, str | None]:
        """Validate prerequisites for this strategy.

        Checks:
        - Required tools installed (az cli, terraform, etc.)
        - Authentication/credentials configured
        - Required permissions available
        - Resource quotas sufficient

        Args:
            context: Execution context to validate

        Returns:
            Tuple of (is_valid, error_message)
            - (True, None) if valid
            - (False, "error message") if invalid

        Example:
            >>> strategy = AzureCLIStrategy()
            >>> context = ExecutionContext(...)
            >>> valid, error = strategy.validate(context)
            >>> if not valid:
            ...     print(f"Validation failed: {error}")
        """
        pass

    @abstractmethod
    def estimate_duration(self, context: ExecutionContext) -> int:
        """Estimate execution duration in seconds.

        This helps users understand expected wait time and plan accordingly.

        Args:
            context: Execution context

        Returns:
            Estimated duration in seconds

        Example:
            >>> strategy = TerraformStrategy()
            >>> context = ExecutionContext(...)
            >>> duration = strategy.estimate_duration(context)
            >>> print(f"Expected duration: {duration}s (~{duration//60} minutes)")
        """
        pass

    def get_strategy_type(self) -> Strategy:
        """Get the strategy type enum.

        Returns:
            Strategy enum value

        Example:
            >>> strategy = AzureCLIStrategy()
            >>> assert strategy.get_strategy_type() == Strategy.AZURE_CLI
        """
        return Strategy.AZURE_CLI  # Override in subclasses

    def cleanup_on_failure(self, context: ExecutionContext, partial_resources: list[str]) -> None:
        """Clean up partially created resources on failure.

        Optional method for strategies to implement cleanup logic.
        Default implementation does nothing.

        Args:
            context: Execution context
            partial_resources: List of resource IDs that were partially created
        """
        pass

    def get_prerequisites(self) -> list[str]:
        """Get list of prerequisites for this strategy.

        Returns:
            List of prerequisite descriptions

        Example:
            >>> strategy = TerraformStrategy()
            >>> print(strategy.get_prerequisites())
            ['terraform >= 1.0', 'azure provider configured']
        """
        return []

    def supports_dry_run(self) -> bool:
        """Check if this strategy supports dry-run mode.

        Returns:
            True if dry-run is supported

        Example:
            >>> strategy = TerraformStrategy()
            >>> if strategy.supports_dry_run():
            ...     context.dry_run = True
        """
        return True

    def get_cost_factors(self, context: ExecutionContext) -> dict[str, Any]:
        """Get cost-related factors for this strategy.

        Returns:
            Dictionary of cost factors (resource types, quantities, etc.)

        Example:
            >>> strategy = AzureCLIStrategy()
            >>> factors = strategy.get_cost_factors(context)
            >>> print(factors)
            {'vm_count': 1, 'vm_size': 'Standard_B2s', 'storage_gb': 128}
        """
        return {}
