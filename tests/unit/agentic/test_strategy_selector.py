"""Tests for StrategySelector module.

Tests strategy selection logic, prerequisite checking, and tool detection.
"""

from unittest.mock import Mock, patch

from azlin.agentic.strategy_selector import StrategySelector
from azlin.agentic.types import Intent, Strategy


class TestToolDetection:
    """Tests for tool detection logic."""

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_detect_az_cli_installed_and_authenticated(self, mock_run, mock_which):
        """Azure CLI installed and authenticated."""
        # Mock which to return paths only for az
        mock_which.side_effect = lambda cmd: "/usr/bin/az" if cmd == "az" else None
        mock_run.return_value = Mock(returncode=0)

        selector = StrategySelector()
        tools = selector._detect_tools()

        assert tools["az_cli"] is True
        # shutil.which is called for az, aws, gcloud, terraform, and other tools
        assert mock_which.call_count >= 1
        assert any(call[0][0] == "az" for call in mock_which.call_args_list)
        # subprocess.run is only called for az since aws/gcloud don't have binaries
        mock_run.assert_called_once_with(
            ["az", "account", "show"],
            capture_output=True,
            timeout=5,
            check=False,
        )

    @patch("shutil.which")
    def test_detect_az_cli_not_installed(self, mock_which):
        """Azure CLI not installed."""
        mock_which.return_value = None

        selector = StrategySelector()
        tools = selector._detect_tools()

        assert tools["az_cli"] is False

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_detect_az_cli_not_authenticated(self, mock_run, mock_which):
        """Azure CLI installed but not authenticated."""
        mock_which.return_value = "/usr/bin/az"
        mock_run.return_value = Mock(returncode=1)

        selector = StrategySelector()
        tools = selector._detect_tools()

        assert tools["az_cli"] is False

    @patch("shutil.which")
    def test_detect_terraform_installed(self, mock_which):
        """Terraform installed."""
        mock_which.side_effect = lambda cmd: "/usr/bin/terraform" if cmd == "terraform" else None

        selector = StrategySelector()
        tools = selector._detect_tools()

        assert tools["terraform"] is True

    @patch("shutil.which")
    def test_detect_terraform_not_installed(self, mock_which):
        """Terraform not installed."""
        mock_which.return_value = None

        selector = StrategySelector()
        tools = selector._detect_tools()

        assert tools["terraform"] is False

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_tool_detection_caching(self, mock_run, mock_which):
        """Tool detection results are cached."""
        # Only mock az as installed
        mock_which.side_effect = lambda cmd: "/usr/bin/az" if cmd == "az" else None
        mock_run.return_value = Mock(returncode=0)

        selector = StrategySelector()

        # First call
        tools1 = selector._detect_tools()
        # Second call (should use cache)
        tools2 = selector._detect_tools()

        assert tools1 == tools2
        # Should only call subprocess once due to caching (only for az)
        mock_run.assert_called_once_with(
            ["az", "account", "show"],
            capture_output=True,
            timeout=5,
            check=False,
        )


class TestIntentClassification:
    """Tests for intent classification."""

    def test_is_complex_intent_multiple_commands(self):
        """Intent with >3 commands is complex."""
        selector = StrategySelector()
        intent = Intent(
            intent="provision_vm",
            parameters={},
            confidence=0.9,
            azlin_commands=[
                {"command": "azlin", "args": []},
                {"command": "azlin", "args": []},
                {"command": "azlin", "args": []},
                {"command": "azlin", "args": []},
            ],  # 4 commands
        )

        assert selector._is_complex_intent(intent) is True

    def test_is_complex_intent_aks(self):
        """AKS provisioning is complex."""
        selector = StrategySelector()
        intent = Intent(
            intent="provision_aks_cluster",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )

        assert selector._is_complex_intent(intent) is True

    def test_is_complex_intent_kubernetes(self):
        """Kubernetes provisioning is complex."""
        selector = StrategySelector()
        intent = Intent(
            intent="provision_kubernetes",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )

        assert selector._is_complex_intent(intent) is True

    def test_is_simple_intent(self):
        """Simple VM provisioning is not complex."""
        selector = StrategySelector()
        intent = Intent(
            intent="provision_vm",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],  # 1 command
        )

        assert selector._is_complex_intent(intent) is False

    def test_is_infrastructure_intent_provision(self):
        """Provisioning is infrastructure intent."""
        selector = StrategySelector()
        intent = Intent(
            intent="provision_vm",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )

        assert selector._is_infrastructure_intent(intent) is True

    def test_is_infrastructure_intent_aks(self):
        """AKS is infrastructure intent."""
        selector = StrategySelector()
        intent = Intent(
            intent="create_aks_cluster",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )

        assert selector._is_infrastructure_intent(intent) is True

    def test_is_not_infrastructure_intent(self):
        """List VMs is not infrastructure intent."""
        selector = StrategySelector()
        intent = Intent(
            intent="list_vms",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )

        assert selector._is_infrastructure_intent(intent) is False


class TestStrategyRanking:
    """Tests for strategy ranking logic."""

    def test_rank_strategies_simple_vm_with_az_cli(self):
        """Simple VM provision: prefer Azure CLI."""
        selector = StrategySelector()
        intent = Intent(
            intent="provision_vm",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )

        ranking = selector._rank_strategies(
            intent=intent,
            is_complex=False,
            is_infrastructure=True,
            available_tools={"az_cli": True, "terraform": True},
            previous_failures=[],
        )

        # Azure CLI should be first for simple operations
        assert ranking[0] == Strategy.AZURE_CLI
        assert Strategy.TERRAFORM in ranking

    def test_rank_strategies_aks_with_terraform(self):
        """AKS cluster: prefer Terraform."""
        selector = StrategySelector()
        intent = Intent(
            intent="provision_aks_cluster",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )

        ranking = selector._rank_strategies(
            intent=intent,
            is_complex=True,
            is_infrastructure=True,
            available_tools={"az_cli": True, "terraform": True},
            previous_failures=[],
        )

        # Terraform should be first for complex infrastructure
        assert ranking[0] == Strategy.TERRAFORM

    def test_rank_strategies_no_terraform_fallback_to_cli(self):
        """No Terraform: fallback to Azure CLI."""
        selector = StrategySelector()
        intent = Intent(
            intent="provision_aks_cluster",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )

        ranking = selector._rank_strategies(
            intent=intent,
            is_complex=True,
            is_infrastructure=True,
            available_tools={"az_cli": True, "terraform": False},
            previous_failures=[],
        )

        # Azure CLI is the fallback
        assert Strategy.AZURE_CLI in ranking
        assert Strategy.TERRAFORM not in ranking

    def test_rank_strategies_with_previous_failure(self):
        """Avoid previously failed strategy."""
        selector = StrategySelector()
        intent = Intent(
            intent="provision_vm",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )

        ranking = selector._rank_strategies(
            intent=intent,
            is_complex=False,
            is_infrastructure=True,
            available_tools={"az_cli": True, "terraform": True},
            previous_failures=[{"strategy": "azure_cli"}],
        )

        # Azure CLI failed, so should not be in ranking
        assert Strategy.AZURE_CLI not in ranking
        # Terraform should be first
        assert ranking[0] == Strategy.TERRAFORM

    def test_rank_strategies_all_failed_retry_cli(self):
        """All strategies failed: retry Azure CLI as last resort."""
        selector = StrategySelector()
        intent = Intent(
            intent="provision_vm",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )

        ranking = selector._rank_strategies(
            intent=intent,
            is_complex=False,
            is_infrastructure=True,
            available_tools={"az_cli": True, "terraform": False},
            previous_failures=[
                {"strategy": "azure_cli"},
                {"strategy": "terraform"},
                {"strategy": "custom_code"},
            ],
        )

        # Should retry Azure CLI as last resort
        assert len(ranking) >= 1
        assert Strategy.AZURE_CLI in ranking


class TestPrerequisiteChecking:
    """Tests for prerequisite checking."""

    def test_prerequisites_azure_cli_met(self):
        """Azure CLI prerequisites met."""
        selector = StrategySelector()
        tools = {"az_cli": True, "terraform": False}

        met, error = selector._check_prerequisites(Strategy.AZURE_CLI, tools)

        assert met is True
        assert error is None

    def test_prerequisites_azure_cli_not_met(self):
        """Azure CLI not installed."""
        selector = StrategySelector()
        tools = {"az_cli": False, "terraform": False}

        met, error = selector._check_prerequisites(Strategy.AZURE_CLI, tools)

        assert met is False
        assert "not installed" in error.lower() or "not authenticated" in error.lower()

    def test_prerequisites_terraform_met(self):
        """Terraform prerequisites met."""
        selector = StrategySelector()
        tools = {"az_cli": True, "terraform": True}

        met, error = selector._check_prerequisites(Strategy.TERRAFORM, tools)

        assert met is True
        assert error is None

    def test_prerequisites_terraform_not_installed(self):
        """Terraform not installed."""
        selector = StrategySelector()
        tools = {"az_cli": True, "terraform": False}

        met, error = selector._check_prerequisites(Strategy.TERRAFORM, tools)

        assert met is False
        assert "terraform" in error.lower()

    def test_prerequisites_terraform_no_azure_cli(self):
        """Terraform needs at least one cloud CLI (Azure, AWS, or GCP)."""
        selector = StrategySelector()
        tools = {
            "az_cli": False,
            "aws_cli": False,
            "gcp_cli": False,
            "terraform": True,
            "mcp_server": False,
        }

        met, error = selector._check_prerequisites(Strategy.TERRAFORM, tools)

        assert met is False
        # Updated message to reflect multi-cloud support
        assert "at least one cloud cli" in error.lower() or "az/aws/gcloud" in error.lower()

    def test_prerequisites_custom_code_always_met(self):
        """Custom code has no prerequisites."""
        selector = StrategySelector()
        tools = {"az_cli": False, "terraform": False}

        met, error = selector._check_prerequisites(Strategy.CUSTOM_CODE, tools)

        assert met is True
        assert error is None


class TestStrategySelection:
    """Tests for end-to-end strategy selection."""

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_select_strategy_simple_vm(self, mock_run, mock_which):
        """Simple VM: select Azure CLI."""
        mock_which.return_value = "/usr/bin/az"
        mock_run.return_value = Mock(returncode=0)

        selector = StrategySelector()
        intent = Intent(
            intent="provision_vm",
            parameters={"vm_name": "test"},
            confidence=0.9,
            azlin_commands=[{"command": "new", "args": ["--name", "test"]}],
        )

        plan = selector.select_strategy(intent)

        assert plan.primary_strategy == Strategy.AZURE_CLI
        assert plan.prerequisites_met is True
        assert plan.reasoning is not None
        assert Strategy.TERRAFORM in plan.fallback_strategies

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_select_strategy_aks_cluster(self, mock_run, mock_which):
        """AKS cluster: prefer Terraform."""
        mock_which.side_effect = lambda cmd: (
            "/usr/bin/terraform" if cmd == "terraform" else "/usr/bin/az" if cmd == "az" else None
        )
        mock_run.return_value = Mock(returncode=0)

        selector = StrategySelector()
        intent = Intent(
            intent="provision_aks_cluster",
            parameters={"cluster_name": "my-cluster"},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )

        plan = selector.select_strategy(intent)

        assert plan.primary_strategy == Strategy.TERRAFORM
        assert plan.prerequisites_met is True
        assert "terraform" in plan.reasoning.lower()

    @patch("shutil.which")
    def test_select_strategy_no_tools(self, mock_which):
        """No tools available: falls back to custom code."""
        mock_which.return_value = None

        selector = StrategySelector()
        intent = Intent(
            intent="provision_vm",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )

        plan = selector.select_strategy(intent)

        # Custom code has no prerequisites, so it's always available as fallback
        assert plan.primary_strategy == Strategy.CUSTOM_CODE
        assert plan.prerequisites_met is True
        assert "custom code" in plan.reasoning.lower()

    def test_estimate_duration_azure_cli(self):
        """Estimate duration for Azure CLI."""
        selector = StrategySelector()
        intent = Intent(
            intent="list_vms",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )

        duration = selector._estimate_duration(Strategy.AZURE_CLI, intent)

        # Should be relatively fast
        assert duration > 0
        assert duration < 120  # Less than 2 minutes for simple operations

    def test_estimate_duration_terraform_complex(self):
        """Estimate duration for complex Terraform."""
        selector = StrategySelector()
        intent = Intent(
            intent="provision_aks_cluster",
            parameters={},
            confidence=0.9,
            azlin_commands=[
                {"command": "azlin", "args": []},
                {"command": "azlin", "args": []},
                {"command": "azlin", "args": []},
                {"command": "azlin", "args": []},
            ],  # 4 commands
        )

        duration = selector._estimate_duration(Strategy.TERRAFORM, intent)

        # Should be longer for complex operations
        assert duration >= 120  # At least 2 minutes

    def test_invalidate_cache(self):
        """Cache can be invalidated."""
        selector = StrategySelector()

        # Set up cache
        selector._cached_tools = {"az_cli": True}

        # Invalidate
        selector.invalidate_cache()

        # Cache should be None
        assert selector._cached_tools is None


class TestReasoningGeneration:
    """Tests for reasoning text generation."""

    def test_build_reasoning_azure_cli(self):
        """Reasoning for Azure CLI selection."""
        selector = StrategySelector()
        intent = Intent(
            intent="provision_vm",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )

        reasoning = selector._build_reasoning(
            primary_strategy=Strategy.AZURE_CLI,
            intent=intent,
            is_complex=False,
            is_infrastructure=True,
            prerequisites_met=True,
            prereq_message=None,
        )

        assert "azure cli" in reasoning.lower()
        assert len(reasoning) > 0

    def test_build_reasoning_terraform(self):
        """Reasoning for Terraform selection."""
        selector = StrategySelector()
        intent = Intent(
            intent="provision_aks_cluster",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )

        reasoning = selector._build_reasoning(
            primary_strategy=Strategy.TERRAFORM,
            intent=intent,
            is_complex=True,
            is_infrastructure=True,
            prerequisites_met=True,
            prereq_message=None,
        )

        assert "terraform" in reasoning.lower()
        assert "infrastructure" in reasoning.lower()

    def test_build_reasoning_prerequisites_not_met(self):
        """Reasoning when prerequisites not met."""
        selector = StrategySelector()
        intent = Intent(
            intent="provision_vm",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )

        reasoning = selector._build_reasoning(
            primary_strategy=Strategy.AZURE_CLI,
            intent=intent,
            is_complex=False,
            is_infrastructure=True,
            prerequisites_met=False,
            prereq_message="Azure CLI not installed",
        )

        assert "prerequisites not met" in reasoning.lower()
        assert "azure cli not installed" in reasoning.lower()
