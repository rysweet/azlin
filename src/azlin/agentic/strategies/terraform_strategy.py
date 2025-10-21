"""Terraform strategy implementation.

Phase 2 Implementation (not yet implemented).

Generates and applies Terraform configurations for infrastructure.
"""

from azlin.agentic.strategies.base_strategy import ExecutionStrategy
from azlin.agentic.types import (
    ExecutionContext,
    ExecutionResult,
    Strategy,
)


class TerraformStrategy(ExecutionStrategy):
    """Execute using Terraform IaC.

    Phase 2 will implement:
    - Generate Terraform configs from intent
    - Run terraform init, plan, apply
    - Parse state for created resources
    - Handle state file management

    Example (when implemented):
        >>> strategy = TerraformStrategy()
        >>> context = ExecutionContext(...)
        >>> if strategy.can_handle(context):
        ...     result = strategy.execute(context)
    """

    def can_handle(self, context: ExecutionContext) -> bool:
        """Check if Terraform can handle this intent.

        TODO Phase 2:
        - Check if terraform is installed
        - Verify Azure provider configured
        - Check if intent is suitable for IaC

        Args:
            context: Execution context

        Returns:
            True if Terraform can handle

        Raises:
            NotImplementedError: Phase 2 not yet implemented
        """
        raise NotImplementedError("Phase 2 - Terraform strategy not yet implemented")

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute using Terraform.

        TODO Phase 2:
        - Generate .tf files
        - Run terraform init
        - Run terraform plan (if dry_run)
        - Run terraform apply
        - Parse state for resources

        Args:
            context: Execution context

        Returns:
            ExecutionResult

        Raises:
            NotImplementedError: Phase 2 not yet implemented
        """
        raise NotImplementedError("Phase 2 - Terraform execution not yet implemented")

    def validate(self, context: ExecutionContext) -> tuple[bool, str | None]:
        """Validate Terraform prerequisites.

        TODO Phase 2:
        - Check terraform installed
        - Verify Azure provider configured
        - Check authentication

        Args:
            context: Execution context

        Returns:
            Tuple of (is_valid, error_message)

        Raises:
            NotImplementedError: Phase 2 not yet implemented
        """
        raise NotImplementedError("Phase 2 - Terraform validation not yet implemented")

    def estimate_duration(self, context: ExecutionContext) -> int:
        """Estimate Terraform execution duration.

        TODO Phase 2:
        - Longer than CLI due to planning
        - VM: ~400s
        - AKS: ~800s
        - Complex resources: +100s per resource

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
            Strategy.TERRAFORM
        """
        return Strategy.TERRAFORM

    def get_prerequisites(self) -> list[str]:
        """Get Terraform prerequisites.

        Returns:
            List of prerequisites
        """
        return [
            "terraform >= 1.0.0",
            "Azure provider configured",
            "Azure authentication (az login or service principal)",
        ]
