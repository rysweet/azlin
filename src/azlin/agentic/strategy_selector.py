"""Strategy selection module for azdoit execution.

Selects the best execution strategy based on intent, prerequisites, and available tools.
"""

import shutil
import subprocess
from typing import Any

from azlin.agentic.types import (
    Intent,
    Strategy,
    StrategyPlan,
)


class StrategySelector:
    """Selects the optimal execution strategy for a given intent.

    Strategy Priority (when all prerequisites met):
    1. AZURE_CLI - Simple, direct, fast
    2. TERRAFORM - Infrastructure as Code, repeatable
    3. CUSTOM_CODE - Last resort, generated code

    Example:
        >>> selector = StrategySelector()
        >>> intent = Intent(intent="provision_vm", ...)
        >>> plan = selector.select_strategy(intent)
        >>> print(f"Using {plan.primary_strategy}")
    """

    def __init__(self):
        """Initialize strategy selector with tool detection."""
        self._cached_tools: dict[str, bool] | None = None

    def select_strategy(
        self,
        intent: Intent,
        resource_group: str | None = None,
        previous_failures: list[dict[str, Any]] | None = None,
    ) -> StrategyPlan:
        """Select the best strategy for the given intent.

        Args:
            intent: Parsed intent from natural language
            resource_group: Azure resource group (optional)
            previous_failures: List of previous execution failures (for fallback)

        Returns:
            StrategyPlan with primary strategy and fallback chain

        Example:
            >>> intent = Intent(intent="provision_vm", parameters={"vm_name": "test"}, ...)
            >>> plan = selector.select_strategy(intent)
            >>> assert plan.primary_strategy == Strategy.AZURE_CLI
        """
        # Detect available tools
        available_tools = self._detect_tools()

        # Determine intent complexity
        is_complex = self._is_complex_intent(intent)
        is_infrastructure = self._is_infrastructure_intent(intent)

        # Build strategy ranking based on intent and prerequisites
        ranked_strategies = self._rank_strategies(
            intent=intent,
            is_complex=is_complex,
            is_infrastructure=is_infrastructure,
            available_tools=available_tools,
            previous_failures=previous_failures or [],
        )

        # Select primary strategy (first valid one)
        primary_strategy = ranked_strategies[0]

        # Build fallback chain (remaining valid strategies)
        fallback_strategies = ranked_strategies[1:]

        # Check if prerequisites are met for primary strategy
        prerequisites_met, prereq_message = self._check_prerequisites(
            primary_strategy, available_tools
        )

        # Estimate duration
        estimated_duration = self._estimate_duration(primary_strategy, intent)

        # Build reasoning
        reasoning = self._build_reasoning(
            primary_strategy=primary_strategy,
            intent=intent,
            is_complex=is_complex,
            is_infrastructure=is_infrastructure,
            prerequisites_met=prerequisites_met,
            prereq_message=prereq_message,
        )

        return StrategyPlan(
            primary_strategy=primary_strategy,
            fallback_strategies=fallback_strategies,
            prerequisites_met=prerequisites_met,
            reasoning=reasoning,
            estimated_duration_seconds=estimated_duration,
        )

    def _detect_tools(self) -> dict[str, bool]:
        """Detect which tools are available on the system.

        Returns:
            Dictionary mapping tool names to availability status

        Example:
            >>> tools = selector._detect_tools()
            >>> assert tools["az_cli"] == True
        """
        if self._cached_tools is not None:
            return self._cached_tools

        tools = {
            "az_cli": self._check_az_cli(),
            "aws_cli": self._check_aws_cli(),
            "gcp_cli": self._check_gcp_cli(),
            "terraform": self._check_terraform(),
        }

        self._cached_tools = tools
        return tools

    def _check_az_cli(self) -> bool:
        """Check if Azure CLI is installed and authenticated."""
        # Check if az command exists
        if not shutil.which("az"):
            return False

        # Check authentication (quick check)
        try:
            result = subprocess.run(
                [get_az_command(), "account", "show"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _check_aws_cli(self) -> bool:
        """Check if AWS CLI is installed and configured."""
        # Check if aws command exists
        if not shutil.which("aws"):
            return False

        # Check configuration (quick check)
        try:
            result = subprocess.run(
                ["aws", "sts", "get-caller-identity"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _check_gcp_cli(self) -> bool:
        """Check if gcloud CLI is installed and configured."""
        # Check if gcloud command exists
        if not shutil.which("gcloud"):
            return False

        # Check configuration (quick check - has active project)
        try:
            result = subprocess.run(
                ["gcloud", "config", "get-value", "project"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            return result.returncode == 0 and bool(result.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _check_terraform(self) -> bool:
        """Check if Terraform is installed."""
        return shutil.which("terraform") is not None

    def _is_complex_intent(self, intent: Intent) -> bool:
        """Determine if intent is complex (multi-resource, multi-step).

        Args:
            intent: Parsed intent

        Returns:
            True if intent is complex
        """
        # Check for multiple resources
        if len(intent.azlin_commands) > 3:
            return True

        # Check for AKS, complex networking, etc.
        complex_keywords = ["aks", "kubernetes", "vnet", "subnet", "load-balancer"]
        intent_lower = intent.intent.lower()
        params_str = str(intent.parameters).lower()

        return any(keyword in intent_lower or keyword in params_str for keyword in complex_keywords)

    def _is_infrastructure_intent(self, intent: Intent) -> bool:
        """Determine if intent is infrastructure-focused (IaC preferred).

        Args:
            intent: Parsed intent

        Returns:
            True if IaC approach is beneficial
        """
        # Terraform is preferred for infrastructure provisioning
        infra_keywords = [
            "provision",
            "infrastructure",
            "deploy",
            "aks",
            "cluster",
            "network",
            "vnet",
        ]
        intent_lower = intent.intent.lower()
        params_str = str(intent.parameters).lower()

        return any(keyword in intent_lower or keyword in params_str for keyword in infra_keywords)

    def _detect_cloud_provider(self, intent: Intent) -> str:
        """Detect target cloud provider from intent.

        Args:
            intent: Parsed intent

        Returns:
            "azure", "aws", "gcp", or "multi-cloud"
        """
        intent_lower = intent.intent.lower()
        params_str = str(intent.parameters).lower()
        user_request_lower = getattr(intent, "user_request", "").lower()

        # Check for AWS indicators
        aws_indicators = ["aws", "ec2", "s3", "lambda", "rds", "dynamodb", "cloudformation", "eks"]
        if any(
            indicator in intent_lower or indicator in params_str or indicator in user_request_lower
            for indicator in aws_indicators
        ):
            return "aws"

        # Check for GCP indicators
        gcp_indicators = [
            "gcp",
            "google cloud",
            "compute engine",
            "gce",
            "cloud storage",
            "gcs",
            "cloud functions",
            "cloud sql",
            "gke",
        ]
        if any(
            indicator in intent_lower or indicator in params_str or indicator in user_request_lower
            for indicator in gcp_indicators
        ):
            return "gcp"

        # Default to Azure (original behavior)
        return "azure"

    def _rank_strategies(
        self,
        intent: Intent,
        is_complex: bool,
        is_infrastructure: bool,
        available_tools: dict[str, bool],
        previous_failures: list[dict[str, Any]],
    ) -> list[Strategy]:
        """Rank strategies based on intent characteristics and failures.

        Args:
            intent: Parsed intent
            is_complex: Whether intent is complex
            is_infrastructure: Whether intent is infrastructure-focused
            available_tools: Available tools
            previous_failures: Previous execution failures

        Returns:
            List of strategies ranked by preference
        """
        failed_strategies = self._extract_failed_strategies(previous_failures)
        cloud_provider = self._detect_cloud_provider(intent)

        ranking: list[Strategy] = []

        # Add Terraform first for complex infrastructure
        self._add_terraform_if_preferred(
            ranking, is_complex, is_infrastructure, available_tools, failed_strategies
        )

        # Add cloud-specific CLI strategies
        self._add_cloud_cli_strategies(ranking, cloud_provider, available_tools, failed_strategies)

        # Add Terraform as fallback if not already added
        self._add_terraform_fallback(ranking, available_tools, failed_strategies)

        # Add custom code as last resort
        self._add_custom_code_fallback(ranking, failed_strategies)

        # Ensure we have at least one strategy
        return self._ensure_fallback_strategy(ranking, cloud_provider)

    def _extract_failed_strategies(self, previous_failures: list[dict[str, Any]]) -> set[Strategy]:
        """Extract set of previously failed strategies.

        Args:
            previous_failures: List of previous failure records

        Returns:
            Set of failed strategies
        """
        return {Strategy(f.get("strategy")) for f in previous_failures if f.get("strategy")}

    def _add_terraform_if_preferred(
        self,
        ranking: list[Strategy],
        is_complex: bool,
        is_infrastructure: bool,
        available_tools: dict[str, bool],
        failed_strategies: set[Strategy],
    ) -> None:
        """Add Terraform to ranking if preferred for complex infrastructure.

        Args:
            ranking: Current ranking list to modify
            is_complex: Whether intent is complex
            is_infrastructure: Whether intent is infrastructure-focused
            available_tools: Available tools
            failed_strategies: Set of failed strategies to avoid
        """
        if (
            is_complex
            and is_infrastructure
            and available_tools.get("terraform")
            and Strategy.TERRAFORM not in failed_strategies
        ):
            ranking.append(Strategy.TERRAFORM)

    def _add_cloud_cli_strategies(
        self,
        ranking: list[Strategy],
        cloud_provider: str,
        available_tools: dict[str, bool],
        failed_strategies: set[Strategy],
    ) -> None:
        """Add cloud-specific CLI strategies based on provider.

        Args:
            ranking: Current ranking list to modify
            cloud_provider: Detected cloud provider
            available_tools: Available tools
            failed_strategies: Set of failed strategies to avoid
        """
        if cloud_provider == "aws":
            self._add_aws_strategies(ranking, available_tools, failed_strategies)
        elif cloud_provider == "gcp":
            self._add_gcp_strategies(ranking, available_tools, failed_strategies)
        else:
            self._add_azure_strategies(ranking, available_tools, failed_strategies)

    def _add_aws_strategies(
        self,
        ranking: list[Strategy],
        available_tools: dict[str, bool],
        failed_strategies: set[Strategy],
    ) -> None:
        """Add AWS-specific strategies with Azure fallback (AWS not implemented)."""
        # AWS CLI strategy not implemented - fall back to Azure
        if available_tools.get("az_cli") and Strategy.AZURE_CLI not in failed_strategies:
            ranking.append(Strategy.AZURE_CLI)

    def _add_gcp_strategies(
        self,
        ranking: list[Strategy],
        available_tools: dict[str, bool],
        failed_strategies: set[Strategy],
    ) -> None:
        """Add GCP-specific strategies with Azure fallback (GCP not implemented)."""
        # GCP CLI strategy not implemented - fall back to Azure
        if available_tools.get("az_cli") and Strategy.AZURE_CLI not in failed_strategies:
            ranking.append(Strategy.AZURE_CLI)

    def _add_azure_strategies(
        self,
        ranking: list[Strategy],
        available_tools: dict[str, bool],
        failed_strategies: set[Strategy],
    ) -> None:
        """Add Azure-specific strategies (no AWS/GCP fallbacks - not implemented)."""
        if available_tools.get("az_cli") and Strategy.AZURE_CLI not in failed_strategies:
            ranking.append(Strategy.AZURE_CLI)

    def _add_terraform_fallback(
        self,
        ranking: list[Strategy],
        available_tools: dict[str, bool],
        failed_strategies: set[Strategy],
    ) -> None:
        """Add Terraform as fallback if not already in ranking."""
        if (
            Strategy.TERRAFORM not in ranking
            and available_tools.get("terraform")
            and Strategy.TERRAFORM not in failed_strategies
        ):
            ranking.append(Strategy.TERRAFORM)

    def _add_custom_code_fallback(
        self, ranking: list[Strategy], failed_strategies: set[Strategy]
    ) -> None:
        """Add custom code as last resort."""
        if Strategy.CUSTOM_CODE not in failed_strategies:
            ranking.append(Strategy.CUSTOM_CODE)

    def _ensure_fallback_strategy(
        self, ranking: list[Strategy], cloud_provider: str
    ) -> list[Strategy]:
        """Ensure ranking has at least one strategy.

        Args:
            ranking: Current ranking list
            cloud_provider: Detected cloud provider

        Returns:
            Ranking with at least one strategy
        """
        if not ranking:
            # All strategies failed, use Azure CLI as last resort
            # (AWS and GCP strategies not implemented)
            ranking.append(Strategy.AZURE_CLI)

        return ranking

    def _check_prerequisites(
        self, strategy: Strategy, available_tools: dict[str, bool]
    ) -> tuple[bool, str | None]:
        """Check if prerequisites are met for the given strategy.

        Args:
            strategy: Strategy to check
            available_tools: Available tools

        Returns:
            Tuple of (prerequisites_met, error_message)
        """
        if strategy == Strategy.AZURE_CLI:
            if not available_tools.get("az_cli"):
                return False, "Azure CLI not installed or not authenticated (run 'az login')"
            return True, None

        if strategy == Strategy.TERRAFORM:
            if not available_tools.get("terraform"):
                return False, "Terraform not installed"
            # Terraform works with any cloud provider that's configured
            if not (
                available_tools.get("az_cli")
                or available_tools.get("aws_cli")
                or available_tools.get("gcp_cli")
            ):
                return False, "At least one cloud CLI required for Terraform (az/aws/gcloud)"
            return True, None

        if strategy == Strategy.CUSTOM_CODE:
            # Custom code has no special prerequisites
            return True, None

        return False, f"Unknown strategy: {strategy}"

    def _estimate_duration(self, strategy: Strategy, intent: Intent) -> int:
        """Estimate execution duration for strategy.

        Args:
            strategy: Selected strategy
            intent: Parsed intent

        Returns:
            Estimated duration in seconds
        """
        # Base durations by strategy
        base_durations = {
            Strategy.AZURE_CLI: 30,  # Fast direct execution
            Strategy.TERRAFORM: 120,  # Slower (init + plan + apply)
            Strategy.CUSTOM_CODE: 90,  # Depends on generated code
        }

        base = base_durations.get(strategy, 60)

        # Adjust for complexity
        if self._is_complex_intent(intent):
            base *= 3

        # Adjust for number of commands
        command_count = len(intent.azlin_commands)
        if command_count > 1:
            base += (command_count - 1) * 10

        return base

    def _build_reasoning(
        self,
        primary_strategy: Strategy,
        intent: Intent,
        is_complex: bool,
        is_infrastructure: bool,
        prerequisites_met: bool,
        prereq_message: str | None,
    ) -> str:
        """Build human-readable reasoning for strategy selection.

        Args:
            primary_strategy: Selected primary strategy
            intent: Parsed intent
            is_complex: Whether intent is complex
            is_infrastructure: Whether intent is infrastructure-focused
            prerequisites_met: Whether prerequisites are met
            prereq_message: Prerequisite error message if any

        Returns:
            Reasoning string
        """
        parts = []

        # Strategy selection reason
        if primary_strategy == Strategy.AZURE_CLI:
            parts.append("Azure CLI selected for direct, fast execution")
        elif primary_strategy == Strategy.TERRAFORM:
            if is_infrastructure:
                parts.append("Terraform selected for infrastructure-as-code approach")
            else:
                parts.append("Terraform selected as fallback strategy")
        elif primary_strategy == Strategy.CUSTOM_CODE:
            parts.append("Custom code generation selected as last resort")

        # Complexity note
        if is_complex:
            parts.append("Intent is complex (multi-resource or advanced configuration)")

        # Prerequisites
        if not prerequisites_met:
            parts.append(f"Prerequisites not met: {prereq_message}")

        return ". ".join(parts)

    def invalidate_cache(self) -> None:
        """Invalidate tool detection cache.

        Call this if tools may have been installed/uninstalled during execution.
        """
        self._cached_tools = None
