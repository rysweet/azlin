"""Tests for autopilot budget enforcement.

Following TDD approach - these tests define the expected behavior
before implementation.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from azlin.autopilot.config import AutoPilotConfig
from azlin.autopilot.enforcer import Action, ActionResult, BudgetEnforcer, BudgetStatus
from azlin.autopilot.learner import UsagePattern, WorkHours


class TestBudgetStatus:
    """Test budget status calculation."""

    def test_budget_status_under_budget(self):
        """Test when costs are under budget."""
        status = BudgetStatus(
            current_monthly_cost=Decimal("300"),
            budget_monthly=Decimal("500"),
            projected_monthly_cost=Decimal("350"),
            overage=Decimal("0"),
            overage_percent=0.0,
            needs_action=False,
        )

        assert status.current_monthly_cost == Decimal("300")
        assert status.needs_action is False

    def test_budget_status_over_budget(self):
        """Test when costs exceed budget."""
        status = BudgetStatus(
            current_monthly_cost=Decimal("600"),
            budget_monthly=Decimal("500"),
            projected_monthly_cost=Decimal("650"),
            overage=Decimal("100"),
            overage_percent=20.0,
            needs_action=True,
        )

        assert status.overage == Decimal("100")
        assert status.overage_percent == 20.0
        assert status.needs_action is True


class TestBudgetEnforcer:
    """Test budget enforcement logic."""

    @patch("azlin.autopilot.enforcer.CostTracker")
    def test_check_budget_under_limit(self, mock_cost_tracker):
        """Test checking budget when under limit."""
        mock_cost_tracker.estimate_costs.return_value = Mock(
            total_cost=Decimal("300"), get_monthly_estimate=lambda: Decimal("350")
        )

        config = AutoPilotConfig(
            enabled=True,
            budget_monthly=500,
            strategy="balanced",
        )

        enforcer = BudgetEnforcer()
        status = enforcer.check_budget(config, "test-rg")

        assert status.needs_action is False
        assert status.current_monthly_cost < status.budget_monthly

    @patch("azlin.autopilot.enforcer.CostTracker")
    def test_check_budget_over_limit(self, mock_cost_tracker):
        """Test checking budget when over limit."""
        mock_cost_tracker.estimate_costs.return_value = Mock(
            total_cost=Decimal("600"), get_monthly_estimate=lambda: Decimal("650")
        )

        config = AutoPilotConfig(
            enabled=True,
            budget_monthly=500,
            strategy="balanced",
        )

        enforcer = BudgetEnforcer()
        status = enforcer.check_budget(config, "test-rg")

        assert status.needs_action is True
        assert status.overage > 0


class TestActionRecommendation:
    """Test action recommendation logic."""

    def test_recommend_actions_idle_vm(self):
        """Test recommending stop for idle VM."""
        config = AutoPilotConfig(
            enabled=True,
            budget_monthly=500,
            strategy="balanced",
            idle_threshold_minutes=120,
        )

        budget_status = BudgetStatus(
            current_monthly_cost=Decimal("600"),
            budget_monthly=Decimal("500"),
            projected_monthly_cost=Decimal("650"),
            overage=Decimal("100"),
            overage_percent=20.0,
            needs_action=True,
        )

        pattern = UsagePattern(
            vm_name="idle-vm",
            typical_work_hours=WorkHours(
                start_hour=9, end_hour=17, days=["mon", "tue", "wed", "thu", "fri"], confidence=0.8
            ),
            average_idle_minutes=180,  # 3 hours idle
            last_active=datetime.now(),
            cpu_utilization_avg=10.0,
            recommendations=["Consider stopping during idle periods"],
        )

        enforcer = BudgetEnforcer()
        actions = enforcer.recommend_actions([pattern], budget_status, config)

        assert len(actions) > 0
        assert any(action.action_type == "stop" for action in actions)

    def test_recommend_actions_low_cpu(self):
        """Test recommending downsize for low CPU utilization."""
        config = AutoPilotConfig(
            enabled=True,
            budget_monthly=500,
            strategy="balanced",
            cpu_threshold_percent=20,
        )

        budget_status = BudgetStatus(
            current_monthly_cost=Decimal("600"),
            budget_monthly=Decimal("500"),
            projected_monthly_cost=Decimal("650"),
            overage=Decimal("100"),
            overage_percent=20.0,
            needs_action=True,
        )

        pattern = UsagePattern(
            vm_name="underutilized-vm",
            typical_work_hours=WorkHours(
                start_hour=0, end_hour=23, days=["mon", "tue", "wed", "thu", "fri"], confidence=0.9
            ),
            average_idle_minutes=30,
            last_active=datetime.now(),
            cpu_utilization_avg=8.0,  # Very low CPU
            recommendations=["Consider downsizing VM"],
        )

        enforcer = BudgetEnforcer()
        actions = enforcer.recommend_actions([pattern], budget_status, config)

        assert len(actions) > 0
        assert any(action.action_type == "downsize" for action in actions)

    def test_recommend_actions_protected_vm(self):
        """Test that protected VMs are not recommended for action."""
        config = AutoPilotConfig(
            enabled=True,
            budget_monthly=500,
            strategy="balanced",
            protected_tags=["production", "critical"],
        )

        budget_status = BudgetStatus(
            current_monthly_cost=Decimal("600"),
            budget_monthly=Decimal("500"),
            projected_monthly_cost=Decimal("650"),
            overage=Decimal("100"),
            overage_percent=20.0,
            needs_action=True,
        )

        pattern = UsagePattern(
            vm_name="prod-vm",
            typical_work_hours=WorkHours(start_hour=9, end_hour=17, days=[], confidence=0.8),
            average_idle_minutes=180,
            last_active=datetime.now(),
            cpu_utilization_avg=10.0,
            recommendations=[],
        )

        # Mock VM with production tag
        with patch("azlin.autopilot.enforcer.TagManager") as mock_tag_manager:
            mock_tag_manager.get_vm_tags.return_value = {"environment": "production"}

            enforcer = BudgetEnforcer()
            actions = enforcer.recommend_actions([pattern], budget_status, config)

            # Should not recommend actions for production VM
            assert not any(action.vm_name == "prod-vm" for action in actions)


class TestActionExecution:
    """Test action execution."""

    @patch("azlin.autopilot.enforcer.VMManager")
    @patch("azlin.autopilot.enforcer.NotificationHandler")
    def test_execute_action_stop_vm(self, mock_notification, mock_vm_manager):
        """Test executing VM stop action."""
        action = Action(
            action_type="stop",
            vm_name="test-vm",
            reason="VM idle for 3 hours",
            estimated_savings_monthly=Decimal("50"),
            requires_confirmation=True,
            tags={},
        )

        mock_vm_manager.stop_vm.return_value = True

        enforcer = BudgetEnforcer()
        result = enforcer.execute_action(action, "test-rg", dry_run=False)

        assert result.success is True
        mock_vm_manager.stop_vm.assert_called_once()

    @patch("azlin.autopilot.enforcer.VMManager")
    def test_execute_action_dry_run(self, mock_vm_manager):
        """Test executing action in dry-run mode."""
        action = Action(
            action_type="stop",
            vm_name="test-vm",
            reason="VM idle for 3 hours",
            estimated_savings_monthly=Decimal("50"),
            requires_confirmation=False,
            tags={},
        )

        enforcer = BudgetEnforcer()
        result = enforcer.execute_action(action, "test-rg", dry_run=True)

        assert result.success is True
        assert "dry-run" in result.message.lower()
        mock_vm_manager.stop_vm.assert_not_called()

    @patch("azlin.autopilot.enforcer.VMManager")
    def test_execute_action_failure(self, mock_vm_manager):
        """Test handling action execution failure."""
        action = Action(
            action_type="stop",
            vm_name="test-vm",
            reason="VM idle for 3 hours",
            estimated_savings_monthly=Decimal("50"),
            requires_confirmation=False,
            tags={},
        )

        mock_vm_manager.stop_vm.side_effect = Exception("VM not found")

        enforcer = BudgetEnforcer()
        result = enforcer.execute_action(action, "test-rg", dry_run=False)

        assert result.success is False
        assert "VM not found" in result.message


class TestSafetyChecks:
    """Test safety checks and rate limiting."""

    def test_rate_limiting(self):
        """Test that actions are rate limited."""
        enforcer = BudgetEnforcer()

        # Simulate multiple actions in short time
        for i in range(10):
            action = Action(
                action_type="stop",
                vm_name=f"vm-{i}",
                reason="Test",
                estimated_savings_monthly=Decimal("10"),
                requires_confirmation=False,
                tags={},
            )

            with patch("azlin.autopilot.enforcer.VMManager.stop_vm") as mock_stop:
                mock_stop.return_value = True
                enforcer.execute_action(action, "test-rg", dry_run=False)

        # Should respect rate limit (max 5 per hour)
        assert enforcer.action_count_last_hour <= 5

    def test_work_hours_protection(self):
        """Test that VMs are not stopped during work hours."""
        config = AutoPilotConfig(
            enabled=True,
            budget_monthly=500,
            strategy="balanced",
        )

        budget_status = BudgetStatus(
            current_monthly_cost=Decimal("600"),
            budget_monthly=Decimal("500"),
            projected_monthly_cost=Decimal("650"),
            overage=Decimal("100"),
            overage_percent=20.0,
            needs_action=True,
        )

        # Pattern with active work hours
        pattern = UsagePattern(
            vm_name="work-vm",
            typical_work_hours=WorkHours(
                start_hour=9, end_hour=17, days=["mon", "tue", "wed", "thu", "fri"], confidence=0.9
            ),
            average_idle_minutes=180,
            last_active=datetime.now(),
            cpu_utilization_avg=15.0,
            recommendations=[],
        )

        enforcer = BudgetEnforcer()

        # Mock current time to be during work hours (e.g., 2pm)
        with patch("azlin.autopilot.enforcer.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2025, 11, 18, 14, 0)  # Monday 2pm

            actions = enforcer.recommend_actions([pattern], budget_status, config)

            # Should not recommend stop during work hours
            stop_actions = [a for a in actions if a.action_type == "stop"]
            assert len(stop_actions) == 0 or all(not a.requires_confirmation for a in stop_actions)
