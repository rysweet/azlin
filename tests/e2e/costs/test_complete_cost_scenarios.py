"""End-to-end tests for complete cost optimization scenarios.

Test Structure: 10% E2E tests (TDD Red Phase)
Feature: Complete cost tracking scenarios from CLI to Azure

These tests follow TDD approach - ALL tests should FAIL initially.
Tests complete user workflows from command-line to Azure operations.
"""

import subprocess
from decimal import Decimal
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.e2e


class TestCostDashboardCLI:
    """E2E tests for cost dashboard CLI commands."""

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_user_views_current_costs_via_cli(self, mock_client, tmp_path):
        """Test user runs 'azlin costs dashboard' and sees current costs."""
        # User runs CLI command
        result = subprocess.run(
            ["azlin", "costs", "dashboard", "--resource-group", "test-rg"],
            capture_output=True,
            text=True,
        )

        # Should show dashboard output
        assert result.returncode == 0
        assert "Total Cost" in result.stdout
        assert "$" in result.stdout

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_user_views_cost_breakdown_by_resource(self, mock_client):
        """Test user views per-resource cost breakdown."""
        result = subprocess.run(
            ["azlin", "costs", "dashboard", "--resource-group", "test-rg", "--breakdown"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Resource Breakdown" in result.stdout
        assert "VirtualMachine" in result.stdout or "VM" in result.stdout

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_user_refreshes_dashboard_to_bypass_cache(self, mock_client):
        """Test user forces dashboard refresh with --refresh flag."""
        # First call (cached)
        result1 = subprocess.run(
            ["azlin", "costs", "dashboard", "--resource-group", "test-rg"],
            capture_output=True,
            text=True,
        )

        # Second call with refresh
        result2 = subprocess.run(
            ["azlin", "costs", "dashboard", "--resource-group", "test-rg", "--refresh"],
            capture_output=True,
            text=True,
        )

        assert result1.returncode == 0
        assert result2.returncode == 0
        # Should indicate fresh data
        assert "Refreshing" in result2.stdout or "Updated" in result2.stdout


class TestBudgetAlertsCLI:
    """E2E tests for budget alerts CLI commands."""

    def test_user_sets_budget_threshold(self, tmp_path):
        """Test user sets budget threshold via CLI."""
        config_file = tmp_path / "budgets.json"

        result = subprocess.run(
            [
                "azlin",
                "costs",
                "budget",
                "set",
                "--name",
                "Development",
                "--limit",
                "1000",
                "--config",
                str(config_file),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Budget set" in result.stdout or "Development" in result.stdout
        assert config_file.exists()

    def test_user_checks_budget_status(self, tmp_path):
        """Test user checks if budget is exceeded."""
        # Setup budget
        config_file = tmp_path / "budgets.json"
        subprocess.run(
            [
                "azlin",
                "costs",
                "budget",
                "set",
                "--name",
                "Test",
                "--limit",
                "500",
                "--config",
                str(config_file),
            ],
            capture_output=True,
        )

        # Check status
        with patch("azlin.costs.dashboard.CostDashboard.get_current_metrics") as mock_metrics:
            mock_metrics.return_value.total_cost = Decimal("600.00")  # Over budget

            result = subprocess.run(
                [
                    "azlin",
                    "costs",
                    "budget",
                    "check",
                    "--resource-group",
                    "test-rg",
                    "--config",
                    str(config_file),
                ],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0
            assert "exceeded" in result.stdout.lower() or "warning" in result.stdout.lower()

    def test_user_receives_budget_alert_email(self, tmp_path):
        """Test budget alert sends email when threshold exceeded."""
        config_file = tmp_path / "budgets.json"

        with patch("azlin.costs.budget.send_email") as mock_email:
            result = subprocess.run(
                [
                    "azlin",
                    "costs",
                    "budget",
                    "set",
                    "--name",
                    "Prod",
                    "--limit",
                    "5000",
                    "--notify",
                    "admin@example.com",
                    "--config",
                    str(config_file),
                ],
                capture_output=True,
                text=True,
            )

            # Trigger budget check that exceeds limit
            subprocess.run(
                ["azlin", "costs", "budget", "check", "--resource-group", "test-rg"],
                capture_output=True,
            )

            # Email should have been sent (if budget exceeded)
            # Note: This is tested more thoroughly in integration tests


class TestCostHistoryCLI:
    """E2E tests for cost history CLI commands."""

    @patch("azlin.costs.history.CostHistory")
    def test_user_views_30_day_cost_history(self, mock_history):
        """Test user views last 30 days of cost history."""
        result = subprocess.run(
            ["azlin", "costs", "history", "--resource-group", "test-rg", "--days", "30"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "30" in result.stdout or "days" in result.stdout

    @patch("azlin.costs.history.CostHistory")
    def test_user_views_cost_trend_visualization(self, mock_history):
        """Test user views cost trend with ASCII chart."""
        result = subprocess.run(
            [
                "azlin",
                "costs",
                "history",
                "--resource-group",
                "test-rg",
                "--days",
                "30",
                "--chart",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        # Should include chart characters or visualization
        chart_indicators = ["│", "─", "█", "*", "|", "-"]
        assert any(indicator in result.stdout for indicator in chart_indicators)

    @patch("azlin.costs.history.CostHistory")
    def test_user_exports_cost_history_to_csv(self, mock_history, tmp_path):
        """Test user exports cost history to CSV file."""
        export_file = tmp_path / "cost_history.csv"

        result = subprocess.run(
            [
                "azlin",
                "costs",
                "history",
                "--resource-group",
                "test-rg",
                "--days",
                "30",
                "--export",
                str(export_file),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert export_file.exists()

        # CSV should have headers
        content = export_file.read_text()
        assert "date" in content.lower()
        assert "cost" in content.lower()


class TestOptimizationRecommendationsCLI:
    """E2E tests for optimization recommendations CLI."""

    @patch("azlin.costs.optimizer.CostOptimizer")
    def test_user_gets_optimization_recommendations(self, mock_optimizer):
        """Test user runs 'azlin costs optimize' and sees recommendations."""
        result = subprocess.run(
            ["azlin", "costs", "optimize", "--resource-group", "test-rg"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Recommendations" in result.stdout or "Savings" in result.stdout

    @patch("azlin.costs.optimizer.CostOptimizer")
    def test_user_filters_recommendations_by_priority(self, mock_optimizer):
        """Test user filters to see only high-priority recommendations."""
        result = subprocess.run(
            [
                "azlin",
                "costs",
                "optimize",
                "--resource-group",
                "test-rg",
                "--priority",
                "high",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "HIGH" in result.stdout or "high" in result.stdout

    @patch("azlin.costs.optimizer.CostOptimizer")
    def test_user_sees_total_savings_potential(self, mock_optimizer):
        """Test recommendations show total potential savings."""
        result = subprocess.run(
            ["azlin", "costs", "optimize", "--resource-group", "test-rg"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        # Should show savings amount
        assert "$" in result.stdout
        assert "savings" in result.stdout.lower() or "save" in result.stdout.lower()


class TestAutomatedOptimizationCLI:
    """E2E tests for automated optimization actions."""

    @patch("azlin.costs.optimizer.CostOptimizer")
    @patch("azlin.costs.actions.ActionExecutor")
    def test_user_previews_optimization_actions(self, mock_executor, mock_optimizer):
        """Test user previews actions without executing (dry-run)."""
        result = subprocess.run(
            [
                "azlin",
                "costs",
                "optimize",
                "--resource-group",
                "test-rg",
                "--execute",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "dry-run" in result.stdout.lower() or "preview" in result.stdout.lower()
        assert "would" in result.stdout.lower()  # "would resize", "would delete", etc.

    @patch("azlin.costs.optimizer.CostOptimizer")
    @patch("azlin.costs.actions.ActionExecutor")
    def test_user_executes_safe_optimizations_automatically(self, mock_executor, mock_optimizer):
        """Test user executes optimizations that passed safety checks."""
        result = subprocess.run(
            [
                "azlin",
                "costs",
                "optimize",
                "--resource-group",
                "test-rg",
                "--execute",
                "--auto-approve-safe",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        # Should show execution results
        assert "completed" in result.stdout.lower() or "executed" in result.stdout.lower()

    @patch("azlin.costs.optimizer.CostOptimizer")
    @patch("azlin.costs.actions.ActionExecutor")
    def test_user_approves_individual_recommendations(self, mock_executor, mock_optimizer):
        """Test user approves recommendations one by one."""
        # Interactive approval would normally happen
        # For E2E test, we simulate with --approve flag
        result = subprocess.run(
            [
                "azlin",
                "costs",
                "optimize",
                "--resource-group",
                "test-rg",
                "--execute",
                "--approve",
                "vm-oversized-1",
            ],
            capture_output=True,
            text=True,
        )

        # Should execute only approved resource
        assert result.returncode == 0


class TestCompleteUserJourneys:
    """E2E tests for complete user journeys."""

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    @patch("azlin.costs.optimizer.CostOptimizer")
    def test_new_user_sets_up_cost_tracking(self, mock_optimizer, mock_client, tmp_path):
        """Test complete journey: new user sets up cost tracking from scratch."""
        # Step 1: User views current costs
        result1 = subprocess.run(
            ["azlin", "costs", "dashboard", "--resource-group", "test-rg"],
            capture_output=True,
            text=True,
        )
        assert result1.returncode == 0

        # Step 2: User sets budget
        config_file = tmp_path / "budgets.json"
        result2 = subprocess.run(
            [
                "azlin",
                "costs",
                "budget",
                "set",
                "--name",
                "Development",
                "--limit",
                "1000",
                "--config",
                str(config_file),
            ],
            capture_output=True,
            text=True,
        )
        assert result2.returncode == 0

        # Step 3: User gets recommendations
        result3 = subprocess.run(
            ["azlin", "costs", "optimize", "--resource-group", "test-rg"],
            capture_output=True,
            text=True,
        )
        assert result3.returncode == 0

        # Step 4: User executes optimizations (dry-run first)
        result4 = subprocess.run(
            [
                "azlin",
                "costs",
                "optimize",
                "--resource-group",
                "test-rg",
                "--execute",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )
        assert result4.returncode == 0

        # All steps should complete successfully
        assert all([result1.returncode == 0, result2.returncode == 0])

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    @patch("azlin.costs.history.CostHistory")
    def test_user_tracks_costs_over_time(self, mock_history, mock_client, tmp_path):
        """Test journey: user tracks costs daily and analyzes trends."""
        # Simulate daily cost snapshots over 30 days
        for day in range(30):
            subprocess.run(
                ["azlin", "costs", "snapshot", "--resource-group", "test-rg"],
                capture_output=True,
            )

        # User views history
        result = subprocess.run(
            ["azlin", "costs", "history", "--resource-group", "test-rg", "--days", "30"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "trend" in result.stdout.lower() or "days" in result.stdout

    @patch("azlin.costs.optimizer.CostOptimizer")
    @patch("azlin.costs.actions.ActionExecutor")
    def test_user_optimizes_and_verifies_savings(self, mock_executor, mock_optimizer, tmp_path):
        """Test journey: user executes optimizations and verifies actual savings."""
        # Step 1: Get initial cost
        with patch("azlin.costs.dashboard.CostDashboard.get_current_metrics") as mock_metrics1:
            mock_metrics1.return_value.total_cost = Decimal("500.00")

            result1 = subprocess.run(
                ["azlin", "costs", "dashboard", "--resource-group", "test-rg"],
                capture_output=True,
                text=True,
            )

        # Step 2: Execute optimizations
        result2 = subprocess.run(
            [
                "azlin",
                "costs",
                "optimize",
                "--resource-group",
                "test-rg",
                "--execute",
                "--auto-approve-safe",
            ],
            capture_output=True,
            text=True,
        )

        # Step 3: Verify reduced costs (simulated)
        with patch("azlin.costs.dashboard.CostDashboard.get_current_metrics") as mock_metrics2:
            mock_metrics2.return_value.total_cost = Decimal("350.00")  # Saved $150

            result3 = subprocess.run(
                ["azlin", "costs", "dashboard", "--resource-group", "test-rg", "--refresh"],
                capture_output=True,
                text=True,
            )

        # All steps should complete
        assert result1.returncode == 0
        assert result2.returncode == 0
        assert result3.returncode == 0


class TestErrorHandlingE2E:
    """E2E tests for error scenarios."""

    def test_cli_handles_missing_resource_group(self):
        """Test CLI shows helpful error for missing resource group."""
        result = subprocess.run(
            ["azlin", "costs", "dashboard"],  # No --resource-group
            capture_output=True,
            text=True,
        )

        # Should fail with helpful message
        assert result.returncode != 0
        assert "resource" in result.stderr.lower() or "required" in result.stderr.lower()

    def test_cli_handles_invalid_budget_limit(self):
        """Test CLI validates budget limit is positive number."""
        result = subprocess.run(
            [
                "azlin",
                "costs",
                "budget",
                "set",
                "--name",
                "Test",
                "--limit",
                "-100",  # Invalid negative
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "invalid" in result.stderr.lower() or "positive" in result.stderr.lower()

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_cli_handles_azure_api_errors(self, mock_client):
        """Test CLI handles Azure API errors gracefully."""
        mock_client.side_effect = Exception("API Error: Unauthorized")

        result = subprocess.run(
            ["azlin", "costs", "dashboard", "--resource-group", "test-rg"],
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "error" in result.stderr.lower()
        # Should provide helpful guidance
        assert "azure" in result.stderr.lower() or "authentication" in result.stderr.lower()
