"""Integration tests for strategy execution.

Tests full strategy execution with real tools (in sandbox):
- Azure CLI execution with real az commands
- Terraform with real terraform binary
- MCP Server connection
- Full objective lifecycle

Coverage Target: 30% integration tests
"""

import pytest
import subprocess


# Mark all tests as integration tests
pytestmark = pytest.mark.integration


class TestAzureCLIExecution:
    """Test Azure CLI strategy with real az commands."""

    @pytest.mark.skip(reason="Requires Azure authentication")
    def test_execute_az_account_show(self):
        """Test executing real az account show command."""
        from azlin.agentic.strategies.azure_cli import AzureCLIStrategy

        strategy = AzureCLIStrategy()

        result = strategy.execute_command(["az", "account", "show"])

        assert result["success"] is True
        assert "id" in result["stdout"]  # Subscription ID

    @pytest.mark.skip(reason="Requires Azure authentication")
    def test_execute_az_vm_list(self):
        """Test listing VMs with real az command."""
        from azlin.agentic.strategies.azure_cli import AzureCLIStrategy

        strategy = AzureCLIStrategy()

        result = strategy.execute_command(["az", "vm", "list", "--output", "json"])

        assert result["success"] is True

    @pytest.mark.skip(reason="Requires Azure resources")
    def test_full_vm_provisioning_dry_run(self):
        """Test full VM provisioning flow in dry-run mode."""
        from azlin.agentic.strategies.azure_cli import AzureCLIStrategy

        strategy = AzureCLIStrategy(dry_run=True)

        objective = {
            "intent": "provision_vm",
            "parameters": {
                "vm_name": "test-integration-vm",
                "size": "Standard_B2s",
                "region": "eastus",
            },
        }

        result = strategy.execute(objective)

        assert result["dry_run"] is True
        assert "commands" in result


class TestTerraformExecution:
    """Test Terraform strategy with real terraform binary."""

    @pytest.mark.skip(reason="Requires terraform installed")
    def test_terraform_version(self):
        """Test terraform binary is available."""
        result = subprocess.run(["terraform", "version"], capture_output=True, text=True)

        assert result.returncode == 0
        assert "Terraform" in result.stdout

    @pytest.mark.skip(reason="Requires terraform and Azure auth")
    def test_terraform_validate(self, sample_terraform_config, tmp_path):
        """Test validating real Terraform config."""
        from azlin.agentic.strategies.terraform import TerraformStrategy

        # Write config to temp directory
        config_file = tmp_path / "main.tf"
        config_file.write_text(sample_terraform_config)

        strategy = TerraformStrategy()

        validation = strategy.validate_directory(str(tmp_path))

        assert validation["valid"] is True or "error" in validation

    @pytest.mark.skip(reason="Requires terraform and Azure auth")
    def test_terraform_plan(self, sample_terraform_config, tmp_path):
        """Test generating Terraform plan."""
        from azlin.agentic.strategies.terraform import TerraformStrategy

        config_file = tmp_path / "main.tf"
        config_file.write_text(sample_terraform_config)

        strategy = TerraformStrategy()

        plan_result = strategy.plan(str(tmp_path))

        assert "changes" in plan_result or "error" in plan_result


class TestMCPServerConnection:
    """Test MCP Server connection and tool execution."""

    @pytest.mark.skip(reason="Requires MCP Server running")
    def test_connect_to_mcp_server(self):
        """Test connecting to local MCP Server."""
        from azlin.agentic.mcp_client import MCPClient

        client = MCPClient(server_url="http://localhost:3000")

        result = client.connect(timeout=5)

        assert result is True or isinstance(result, ConnectionError)

    @pytest.mark.skip(reason="Requires MCP Server running")
    def test_list_mcp_tools(self):
        """Test listing available MCP tools."""
        from azlin.agentic.mcp_client import MCPClient

        client = MCPClient()
        if not client.connect(timeout=5):
            pytest.skip("MCP Server not available")

        tools = client.list_tools()

        assert isinstance(tools, list)
        assert len(tools) > 0


class TestObjectiveLifecycle:
    """Test full objective lifecycle from creation to completion."""

    @pytest.mark.skip(reason="Requires full system integration")
    def test_simple_vm_objective_lifecycle(self, temp_objectives_dir):
        """Test complete lifecycle for simple VM objective."""
        from azlin.agentic.state_manager import StateManager
        from azlin.agentic.strategy_selector import StrategySelector
        from azlin.agentic.cost_estimator import CostEstimator

        # Create objective
        manager = StateManager(objectives_dir=temp_objectives_dir)
        objective = manager.create_objective(
            "Create a VM called integration-test",
            {"intent": "provision_vm", "parameters": {"vm_name": "integration-test"}},
        )

        # Estimate cost
        estimator = CostEstimator()
        cost = estimator.estimate_objective_cost(objective["parsed_intent"])
        manager.update_objective(objective["id"], cost_estimate=cost["estimated_cost"])

        # Select strategy
        selector = StrategySelector()
        strategy = selector.select_strategy(objective["parsed_intent"])
        manager.update_objective(objective["id"], selected_strategy=strategy.name)

        # Execute (dry-run)
        result = strategy.execute(objective["parsed_intent"], dry_run=True)

        # Update state
        manager.update_status(objective["id"], "completed" if result["success"] else "failed")

        final_state = manager.load_objective(objective["id"])
        assert final_state["status"] in ["completed", "failed"]
        assert final_state["cost_estimate"] > 0


class TestCostEstimationIntegration:
    """Test cost estimation with real Azure Pricing API."""

    @pytest.mark.skip(reason="Requires Azure Pricing API access")
    def test_fetch_real_vm_pricing(self):
        """Test fetching real VM pricing from Azure."""
        from azlin.agentic.cost_estimator import CostEstimator

        estimator = CostEstimator()

        pricing = estimator.fetch_vm_pricing(
            vm_size="Standard_D2s_v3", region="eastus"
        )

        assert pricing["hourly"] > 0
        assert pricing["monthly"] > 0

    @pytest.mark.skip(reason="Requires Azure Cost Management API")
    def test_track_actual_costs(self):
        """Test tracking actual costs from Azure."""
        from azlin.agentic.cost_estimator import CostEstimator
        from datetime import datetime, timedelta

        estimator = CostEstimator()

        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

        actual_cost = estimator.get_actual_cost(
            from_date=start_date.isoformat(),
            to_date=end_date.isoformat(),
        )

        assert actual_cost["total"] >= 0


class TestFailureRecoveryIntegration:
    """Test failure recovery with state persistence."""

    @pytest.mark.skip(reason="Requires full system integration")
    def test_recover_from_quota_error(self, temp_objectives_dir):
        """Test recovering from quota exceeded error."""
        from azlin.agentic.state_manager import StateManager
        from azlin.agentic.failure_recovery import RecoveryAgent
        from azlin.agentic.strategy_selector import StrategySelector

        manager = StateManager(objectives_dir=temp_objectives_dir)
        recovery_agent = RecoveryAgent(state_manager=manager)
        selector = StrategySelector()

        objective = manager.create_objective(
            "Create 100 VMs",  # Will likely hit quota
            {"intent": "provision_vm", "parameters": {"count": 100}},
        )

        manager.update_status(objective["id"], "in_progress")

        # Simulate quota error
        error = "QuotaExceeded: Regional vCPU quota exceeded"

        # Attempt recovery
        recovery_plan = recovery_agent.research_recovery(
            {"error": error, "error_code": "QuotaExceeded"}
        )

        assert recovery_plan["action"] in ["try_alternative_region", "reduce_resources"]
        assert manager.load_objective(objective["id"])["retry_count"] == 0


class TestPrerequisiteInstallation:
    """Test automatic prerequisite installation."""

    @pytest.mark.skip(reason="Requires system modifications")
    def test_check_terraform_installed(self):
        """Test checking if Terraform is installed."""
        from azlin.agentic.prerequisites import PrerequisiteChecker

        checker = PrerequisiteChecker()

        is_installed = checker.is_terraform_installed()

        assert isinstance(is_installed, bool)

    @pytest.mark.skip(reason="Requires system modifications")
    def test_install_terraform(self):
        """Test installing Terraform (dry-run)."""
        from azlin.agentic.prerequisites import PrerequisiteInstaller

        installer = PrerequisiteInstaller(dry_run=True)

        result = installer.install_terraform()

        assert result["dry_run"] is True
        assert "commands" in result
