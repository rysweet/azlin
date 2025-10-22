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
    1. MCP_CLIENT - When MCP server available (preferred for tool-based execution)
    2. AZURE_CLI - Simple, direct, fast
    3. TERRAFORM - Infrastructure as Code, repeatable
    4. CUSTOM_CODE - Last resort, generated code

    Example:
        >>> selector = StrategySelector()
        >>> intent = Intent(intent="provision_vm", ...)
        >>> plan = selector.select_strategy(intent)
        >>> print(f"Using {plan.primary_strategy}")
    """

    def __init__(self, mcp_server_command: str | list[str] = "mcp-server-azure"):
        """Initialize strategy selector with tool detection.

        Args:
            mcp_server_command: Command to start MCP server (default: mcp-server-azure)
        """
        self._cached_tools: dict[str, bool] | None = None
        self.mcp_server_command = mcp_server_command

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
            "mcp_server": self._check_mcp_server(),
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
                ["az", "account", "show"],
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

    def _check_mcp_server(self) -> bool:
        """Check if MCP server is available.

        Returns:
            True if MCP server can be connected to
        """
        try:
            # Import here to avoid circular dependency
            from azlin.agentic.mcp_client import MCPClient

            # Try to connect to MCP server with short timeout
            client = MCPClient(self.mcp_server_command, timeout=5)
            try:
                client.connect()
                # Try to list tools to verify it's working
                tools = client.list_tools()
                return len(tools) > 0
            finally:
                client.disconnect()
        except Exception:
            # MCP server not available or connection failed
            return False

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

    def _rank_strategies(  # noqa: C901
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
        # Get previously failed strategies to avoid
        failed_strategies = {
            Strategy(f.get("strategy")) for f in previous_failures if f.get("strategy")
        }

        # Detect cloud provider from intent
        cloud_provider = self._detect_cloud_provider(intent)

        # Start with all strategies
        ranking = []

        # MCP Client is preferred when available (provides standardized tool interface)
        if available_tools.get("mcp_server") and Strategy.MCP_CLIENT not in failed_strategies:
            ranking.append(Strategy.MCP_CLIENT)

        # For COMPLEX infrastructure, prefer Terraform (cloud-agnostic)
        if (
            is_complex
            and is_infrastructure
            and available_tools.get("terraform")
            and Strategy.TERRAFORM not in failed_strategies
        ):
            ranking.append(Strategy.TERRAFORM)

        # Add cloud-specific CLI strategies based on detected provider
        if cloud_provider == "aws":
            # AWS-specific ranking
            if available_tools.get("aws_cli") and Strategy.AWS_CLI not in failed_strategies:
                ranking.append(Strategy.AWS_CLI)
            # Fallback to Azure/GCP if multi-cloud
            if available_tools.get("az_cli") and Strategy.AZURE_CLI not in failed_strategies:
                ranking.append(Strategy.AZURE_CLI)
            if available_tools.get("gcp_cli") and Strategy.GCP_CLI not in failed_strategies:
                ranking.append(Strategy.GCP_CLI)

        elif cloud_provider == "gcp":
            # GCP-specific ranking
            if available_tools.get("gcp_cli") and Strategy.GCP_CLI not in failed_strategies:
                ranking.append(Strategy.GCP_CLI)
            # Fallback to Azure/AWS if multi-cloud
            if available_tools.get("az_cli") and Strategy.AZURE_CLI not in failed_strategies:
                ranking.append(Strategy.AZURE_CLI)
            if available_tools.get("aws_cli") and Strategy.AWS_CLI not in failed_strategies:
                ranking.append(Strategy.AWS_CLI)

        else:
            # Azure (default) or multi-cloud
            if available_tools.get("az_cli") and Strategy.AZURE_CLI not in failed_strategies:
                ranking.append(Strategy.AZURE_CLI)
            # Also add AWS and GCP as fallbacks for multi-cloud support
            if available_tools.get("aws_cli") and Strategy.AWS_CLI not in failed_strategies:
                ranking.append(Strategy.AWS_CLI)
            if available_tools.get("gcp_cli") and Strategy.GCP_CLI not in failed_strategies:
                ranking.append(Strategy.GCP_CLI)

        # Add Terraform if not already added
        if (
            Strategy.TERRAFORM not in ranking
            and available_tools.get("terraform")
            and Strategy.TERRAFORM not in failed_strategies
        ):
            ranking.append(Strategy.TERRAFORM)

        # Custom code as last resort
        if Strategy.CUSTOM_CODE not in failed_strategies:
            ranking.append(Strategy.CUSTOM_CODE)

        # Ensure we have at least one strategy
        if not ranking:
            # All strategies failed, try primary cloud CLI again as last resort
            if cloud_provider == "aws":
                ranking.append(Strategy.AWS_CLI)
            elif cloud_provider == "gcp":
                ranking.append(Strategy.GCP_CLI)
            else:
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

        if strategy == Strategy.AWS_CLI:
            if not available_tools.get("aws_cli"):
                return False, "AWS CLI not installed or not configured (run 'aws configure')"
            return True, None

        if strategy == Strategy.GCP_CLI:
            if not available_tools.get("gcp_cli"):
                return False, "gcloud CLI not installed or not configured (run 'gcloud init')"
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

        if strategy == Strategy.MCP_CLIENT:
            if not available_tools.get("mcp_server"):
                return False, "MCP server not available"
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
            Strategy.MCP_CLIENT: 60,  # Medium speed
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
        elif primary_strategy == Strategy.MCP_CLIENT:
            parts.append("MCP Client selected for tool-based execution")
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
