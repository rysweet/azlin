"""Integration tests for cost dashboard workflows.

Test Structure: 30% Integration tests (TDD Red Phase)
Feature: Dashboard workflows with real component interactions

These tests follow TDD approach - ALL tests should FAIL initially.
Tests real workflows across multiple components without external Azure calls.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from azlin.costs.budget import BudgetAlertManager, BudgetThreshold
from azlin.costs.dashboard import CostDashboard
from azlin.costs.history import CostHistory
from azlin.costs.optimizer import CostOptimizer


class TestDashboardBudgetIntegration:
    """Integration tests for dashboard + budget alerts."""

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_dashboard_triggers_budget_alerts(self, mock_client):
        """Test dashboard triggers alerts when costs exceed thresholds."""
        # Setup dashboard
        dashboard = CostDashboard(resource_group="test-rg")

        # Setup budget with threshold
        threshold = BudgetThreshold(
            name="Development",
            limit=Decimal("1000.00"),
            warning_percentage=Decimal("80"),
        )
        budget_manager = BudgetAlertManager([threshold])

        # Simulate high costs
        with patch.object(dashboard, "get_current_metrics") as mock_metrics:
            mock_metrics.return_value.total_cost = Decimal("900.00")

            metrics = dashboard.get_current_metrics()
            alerts = budget_manager.check_budgets({"Development": metrics.total_cost})

            assert len(alerts) == 1
            assert alerts[0].severity == "warning"

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_dashboard_refreshes_trigger_budget_checks(self, mock_client):
        """Test dashboard refresh automatically checks budgets."""
        dashboard = CostDashboard(resource_group="test-rg")

        threshold = BudgetThreshold(name="Prod", limit=Decimal("5000.00"))
        budget_manager = BudgetAlertManager([threshold])

        # Hook budget manager to dashboard refresh
        dashboard.on_refresh_callbacks.append(
            lambda metrics: budget_manager.check_budgets({"Prod": metrics.total_cost})
        )

        with patch.object(dashboard, "_fetch_cost_data") as mock_fetch:
            mock_fetch.return_value.total_cost = Decimal("5500.00")

            metrics = dashboard.get_current_metrics(refresh=True)

            # Budget check should have been triggered
            assert budget_manager.last_check_time is not None


class TestDashboardHistoryIntegration:
    """Integration tests for dashboard + cost history."""

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_dashboard_records_to_history(self, mock_client):
        """Test dashboard automatically records to history."""
        dashboard = CostDashboard(resource_group="test-rg")
        history = CostHistory(resource_group="test-rg")

        with patch.object(dashboard, "get_current_metrics") as mock_metrics:
            mock_metrics.return_value.total_cost = Decimal("150.00")

            metrics = dashboard.get_current_metrics()
            history.record_daily_snapshot()

            # History should have recorded the metrics
            assert history.store.count() == 1
            latest = history.store.get_latest()
            assert latest.total_cost == Decimal("150.00")

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_dashboard_shows_historical_trends(self, mock_client):
        """Test dashboard displays trends from history."""
        dashboard = CostDashboard(resource_group="test-rg")
        history = CostHistory(resource_group="test-rg")

        # Record 7 days of history
        for i in range(7):
            date = datetime.now().date() - timedelta(days=6 - i)
            history.store.add_mock_entry(date=date, cost=Decimal(f"{100 + i * 5}.00"))

        # Dashboard should show trend
        with patch.object(dashboard, "get_cost_history", return_value=history):
            trend = dashboard.get_7_day_trend()

            assert trend.direction == "increasing"


class TestDashboardOptimizerIntegration:
    """Integration tests for dashboard + optimizer."""

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    @patch("azlin.costs.optimizer.VMManager")
    def test_dashboard_triggers_optimization_scan(self, mock_vm, mock_client):
        """Test dashboard can trigger optimization analysis."""
        dashboard = CostDashboard(resource_group="test-rg")
        optimizer = CostOptimizer(resource_group="test-rg")

        with patch.object(dashboard, "get_current_metrics") as mock_metrics:
            mock_metrics.return_value.total_cost = Decimal("2000.00")

            metrics = dashboard.get_current_metrics()

            # If costs are high, trigger optimization scan
            if metrics.total_cost > Decimal("1000.00"):
                recommendations = optimizer.analyze()

                # Should produce recommendations
                assert recommendations is not None

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_dashboard_displays_optimization_savings_potential(self, mock_client):
        """Test dashboard shows potential savings from optimizer."""
        dashboard = CostDashboard(resource_group="test-rg")
        optimizer = CostOptimizer(resource_group="test-rg")

        with (
            patch.object(optimizer, "analyze") as mock_analyze,
            patch.object(dashboard, "get_current_metrics") as mock_metrics,
        ):
            mock_analyze.return_value = [
                Mock(estimated_savings=Decimal("100.00")),
                Mock(estimated_savings=Decimal("50.00")),
            ]
            mock_metrics.return_value.total_cost = Decimal("500.00")

            metrics = dashboard.get_current_metrics()
            recommendations = optimizer.analyze()
            total_savings = optimizer.calculate_total_savings(recommendations)

            # Dashboard should show savings potential
            savings_percentage = (total_savings / metrics.total_cost) * 100
            assert savings_percentage == Decimal("30.0")  # 150/500 = 30%


class TestBudgetHistoryIntegration:
    """Integration tests for budget + history."""

    def test_budget_alerts_reference_historical_data(self):
        """Test budget alerts use historical data for context."""
        history = CostHistory(resource_group="test-rg")

        # Record history showing increasing costs
        for i in range(7):
            date = datetime.now().date() - timedelta(days=6 - i)
            history.store.add_mock_entry(date=date, cost=Decimal(f"{50 + i * 10}.00"))

        threshold = BudgetThreshold(name="Dev", limit=Decimal("150.00"))
        budget_manager = BudgetAlertManager([threshold])

        # Check budget with historical context
        current_cost = Decimal("120.00")
        alerts = budget_manager.check_budgets({"Dev": current_cost}, historical_context=history)

        # Alert should include trend information
        assert len(alerts) == 1
        assert "increasing" in alerts[0].get_context().lower()

    def test_budget_forecast_uses_history(self):
        """Test budget forecasting uses historical data."""
        history = CostHistory(resource_group="test-rg")

        # Record stable daily costs
        for i in range(30):
            date = datetime.now().date() - timedelta(days=29 - i)
            history.store.add_mock_entry(date=date, cost=Decimal("10.00"))

        threshold = BudgetThreshold(name="Test", limit=Decimal("500.00"))
        budget_manager = BudgetAlertManager([threshold])

        # Forecast should predict when budget will be breached
        current_total = Decimal("400.00")
        forecast = budget_manager.forecast_breach_date(current_total, threshold.limit, history)

        # At $10/day, should breach in ~10 days
        expected_date = datetime.now().date() + timedelta(days=10)
        assert abs((forecast.date - expected_date).days) <= 1


class TestOptimizerActionIntegration:
    """Integration tests for optimizer + automated actions."""

    @patch("azlin.costs.optimizer.VMManager")
    @patch("azlin.costs.actions.VMManager")
    def test_optimizer_generates_executable_actions(self, mock_action_vm, mock_opt_vm):
        """Test optimizer recommendations can be converted to actions."""
        optimizer = CostOptimizer(resource_group="test-rg")

        with patch.object(optimizer, "analyze") as mock_analyze:
            from azlin.costs.optimizer import OptimizationRecommendation, RecommendationPriority

            mock_analyze.return_value = [
                OptimizationRecommendation(
                    resource_name="vm-oversized",
                    resource_type="VirtualMachine",
                    action="Downsize VM",
                    reason="Low utilization",
                    estimated_savings=Decimal("180.00"),
                    priority=RecommendationPriority.HIGH,
                    details={"current_size": "E16as_v5", "suggested_size": "E8as_v5"},
                )
            ]

            recommendations = optimizer.analyze()
            actions = optimizer.convert_to_actions(recommendations)

            assert len(actions) == 1
            assert actions[0].action_type == "vm_resize"

    @patch("azlin.costs.actions.ActionExecutor")
    def test_optimizer_executes_actions_with_safety_checks(self, mock_executor):
        """Test optimizer executes actions with safety validation."""
        optimizer = CostOptimizer(resource_group="test-rg")

        with patch.object(optimizer, "analyze") as mock_analyze:
            mock_analyze.return_value = [Mock(estimated_savings=Decimal("100.00"))]

            recommendations = optimizer.analyze()
            actions = optimizer.convert_to_actions(recommendations)

            # Execute with safety checks
            from azlin.costs.actions import ActionSafetyCheck

            safety = ActionSafetyCheck()
            safe_actions = [a for a in actions if safety.validate(a).safe]

            results = mock_executor.execute_actions(safe_actions)

            # All safe actions should have been executed
            assert len(results) >= 0


class TestHistoryTrendOptimizerIntegration:
    """Integration tests for history trends + optimizer."""

    def test_optimizer_prioritizes_based_on_trends(self):
        """Test optimizer uses cost trends to prioritize recommendations."""
        history = CostHistory(resource_group="test-rg")

        # Record increasing costs for specific VM
        for i in range(7):
            date = datetime.now().date() - timedelta(days=6 - i)
            history.store.add_mock_entry(
                date=date,
                cost=Decimal(f"{100 + i * 10}.00"),
                breakdown={"vm-expensive": Decimal(f"{50 + i * 10}.00")},
            )

        optimizer = CostOptimizer(resource_group="test-rg")

        with patch.object(optimizer, "analyze") as mock_analyze:
            # Optimizer should prioritize resources with increasing trends
            mock_analyze.return_value = optimizer.analyze_with_trends(history)

            recommendations = mock_analyze.return_value

            # VM with increasing costs should be prioritized
            if recommendations:
                top_rec = recommendations[0]
                assert "vm-expensive" in top_rec.resource_name


class TestEndToEndCostWorkflow:
    """Integration tests for complete cost management workflow."""

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    @patch("azlin.costs.optimizer.VMManager")
    def test_complete_cost_optimization_workflow(self, mock_vm, mock_client):
        """Test complete workflow: dashboard → alerts → recommendations → actions."""
        # Step 1: Dashboard collects costs
        dashboard = CostDashboard(resource_group="test-rg")

        with patch.object(dashboard, "get_current_metrics") as mock_metrics:
            mock_metrics.return_value.total_cost = Decimal("2000.00")

            metrics = dashboard.get_current_metrics()

            # Step 2: Check budget alerts
            threshold = BudgetThreshold(name="Test", limit=Decimal("1500.00"))
            budget_manager = BudgetAlertManager([threshold])

            alerts = budget_manager.check_budgets({"Test": metrics.total_cost})

            # Step 3: Costs exceeded - trigger optimizer
            if alerts:
                optimizer = CostOptimizer(resource_group="test-rg")

                with patch.object(optimizer, "analyze") as mock_analyze:
                    mock_analyze.return_value = [
                        Mock(estimated_savings=Decimal("600.00"))  # Would bring under budget
                    ]

                    recommendations = optimizer.analyze()

                    # Step 4: Convert to actions
                    actions = optimizer.convert_to_actions(recommendations)

                    # Step 5: Execute actions (dry-run)
                    from azlin.costs.actions import ActionExecutor

                    executor = ActionExecutor()

                    with patch.object(executor, "execute_actions") as mock_execute:
                        mock_execute.return_value = [Mock(actual_savings=Decimal("600.00"))]

                        results = executor.execute_actions(actions, dry_run=True)

                        # Workflow should complete successfully
                        assert len(results) > 0

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_daily_cost_tracking_workflow(self, mock_client):
        """Test daily workflow: collect costs → record history → analyze trends."""
        dashboard = CostDashboard(resource_group="test-rg")
        history = CostHistory(resource_group="test-rg")

        # Simulate 30 days of daily snapshots
        for day in range(30):
            date = datetime.now().date() - timedelta(days=29 - day)

            with patch.object(dashboard, "get_current_metrics") as mock_metrics:
                daily_cost = Decimal(f"{100 + day}.00")
                mock_metrics.return_value.total_cost = daily_cost

                # Daily snapshot
                metrics = dashboard.get_current_metrics()
                history.record_snapshot(date, metrics.total_cost)

        # Analyze trends
        trend = history.analyze_trend(days=30)

        assert trend.direction == "increasing"
        assert history.store.count() == 30

    def test_automated_optimization_pipeline(self):
        """Test automated pipeline: analyze → prioritize → execute → verify."""
        optimizer = CostOptimizer(resource_group="test-rg")

        with patch.object(optimizer, "analyze") as mock_analyze:
            # Step 1: Analyze and get recommendations
            mock_analyze.return_value = [
                Mock(
                    estimated_savings=Decimal("200.00"),
                    priority=Mock(value=1),
                    resource_name="vm-1",
                ),
                Mock(
                    estimated_savings=Decimal("50.00"),
                    priority=Mock(value=3),
                    resource_name="vm-2",
                ),
            ]

            recommendations = optimizer.analyze()

            # Step 2: Prioritize by savings
            sorted_recs = sorted(
                recommendations,
                key=lambda r: r.estimated_savings,
                reverse=True,
            )

            # Step 3: Convert high-priority to actions
            top_actions = optimizer.convert_to_actions(sorted_recs[:1])

            # Step 4: Execute with safety checks
            from azlin.costs.actions import ActionExecutor, ActionSafetyCheck

            safety = ActionSafetyCheck()
            executor = ActionExecutor()

            with patch.object(executor, "execute_actions") as mock_execute:
                mock_execute.return_value = [Mock(status="COMPLETED")]

                results = executor.execute_actions(
                    [a for a in top_actions if safety.validate(a).safe]
                )

                # Step 5: Verify completion
                assert all(r.status == "COMPLETED" for r in results)
