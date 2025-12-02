"""Unit tests for budget alerts and forecasting.

Test Structure: 60% Unit tests (TDD Red Phase)
Feature: Budget alerts with thresholds and cost projections

These tests follow TDD approach - ALL tests should FAIL initially until
the budget alert implementation is complete.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from azlin.costs.budget import (
    BudgetAlert,
    BudgetAlertManager,
    BudgetAlertTrigger,
    BudgetForecast,
    BudgetThreshold,
    BudgetViolation,
)


class TestBudgetThreshold:
    """Tests for budget threshold definition."""

    def test_threshold_initialization(self):
        """Test threshold initializes with correct values."""
        threshold = BudgetThreshold(
            name="Development",
            limit=Decimal("1000.00"),
            warning_percentage=Decimal("80"),
            critical_percentage=Decimal("95"),
        )

        assert threshold.name == "Development"
        assert threshold.limit == Decimal("1000.00")
        assert threshold.warning_percentage == Decimal("80")
        assert threshold.critical_percentage == Decimal("95")

    def test_threshold_calculates_warning_amount(self):
        """Test threshold calculates warning dollar amount."""
        threshold = BudgetThreshold(
            name="Production", limit=Decimal("5000.00"), warning_percentage=Decimal("80")
        )

        warning_amount = threshold.get_warning_amount()
        assert warning_amount == Decimal("4000.00")  # 80% of 5000

    def test_threshold_calculates_critical_amount(self):
        """Test threshold calculates critical dollar amount."""
        threshold = BudgetThreshold(
            name="Production", limit=Decimal("5000.00"), critical_percentage=Decimal("95")
        )

        critical_amount = threshold.get_critical_amount()
        assert critical_amount == Decimal("4750.00")  # 95% of 5000

    def test_threshold_validates_percentages(self):
        """Test threshold validates percentage ranges."""
        with pytest.raises(ValueError, match="percentage"):
            BudgetThreshold(
                name="Invalid",
                limit=Decimal("1000.00"),
                warning_percentage=Decimal("110"),  # Invalid
            )

    def test_threshold_enforces_warning_before_critical(self):
        """Test warning percentage must be less than critical."""
        with pytest.raises(ValueError, match="warning"):
            BudgetThreshold(
                name="Invalid",
                limit=Decimal("1000.00"),
                warning_percentage=Decimal("95"),
                critical_percentage=Decimal("80"),  # Should be > warning
            )


class TestBudgetAlert:
    """Tests for budget alert notifications."""

    def test_alert_initialization(self):
        """Test alert initializes with correct data."""
        alert = BudgetAlert(
            threshold_name="Development",
            severity="warning",
            current_cost=Decimal("850.00"),
            limit=Decimal("1000.00"),
            percentage_used=Decimal("85.0"),
            triggered_at=datetime.now(),
        )

        assert alert.severity == "warning"
        assert alert.current_cost == Decimal("850.00")
        assert alert.percentage_used == Decimal("85.0")

    def test_alert_severity_levels(self):
        """Test alert supports warning, critical, and exceeded levels."""
        alert_warning = BudgetAlert(
            threshold_name="Dev",
            severity="warning",
            current_cost=Decimal("800.00"),
            limit=Decimal("1000.00"),
            percentage_used=Decimal("80.0"),
            triggered_at=datetime.now(),
        )

        alert_critical = BudgetAlert(
            threshold_name="Dev",
            severity="critical",
            current_cost=Decimal("950.00"),
            limit=Decimal("1000.00"),
            percentage_used=Decimal("95.0"),
            triggered_at=datetime.now(),
        )

        alert_exceeded = BudgetAlert(
            threshold_name="Dev",
            severity="exceeded",
            current_cost=Decimal("1100.00"),
            limit=Decimal("1000.00"),
            percentage_used=Decimal("110.0"),
            triggered_at=datetime.now(),
        )

        assert alert_warning.is_warning()
        assert alert_critical.is_critical()
        assert alert_exceeded.is_exceeded()

    def test_alert_formatting(self):
        """Test alert formats message for display."""
        alert = BudgetAlert(
            threshold_name="Development",
            severity="critical",
            current_cost=Decimal("950.00"),
            limit=Decimal("1000.00"),
            percentage_used=Decimal("95.0"),
            triggered_at=datetime.now(),
        )

        message = alert.format_message()
        assert "Development" in message
        assert "95.0%" in message
        assert "$950.00" in message
        assert "critical" in message.lower()

    def test_alert_includes_recommendation(self):
        """Test alert includes cost reduction recommendations."""
        alert = BudgetAlert(
            threshold_name="Production",
            severity="exceeded",
            current_cost=Decimal("5500.00"),
            limit=Decimal("5000.00"),
            percentage_used=Decimal("110.0"),
            triggered_at=datetime.now(),
        )

        recommendations = alert.get_recommendations()
        assert len(recommendations) > 0
        assert any("stop" in r.lower() or "delete" in r.lower() for r in recommendations)


class TestBudgetAlertTrigger:
    """Tests for alert trigger conditions."""

    def test_trigger_evaluates_thresholds(self):
        """Test trigger evaluates current cost against thresholds."""
        threshold = BudgetThreshold(
            name="Dev", limit=Decimal("1000.00"), warning_percentage=Decimal("80")
        )

        trigger = BudgetAlertTrigger(threshold)

        # Under warning - no alert
        alert = trigger.evaluate(Decimal("500.00"))
        assert alert is None

        # At warning - trigger alert
        alert = trigger.evaluate(Decimal("850.00"))
        assert alert is not None
        assert alert.severity == "warning"

    def test_trigger_detects_critical_level(self):
        """Test trigger detects critical threshold breach."""
        threshold = BudgetThreshold(
            name="Prod", limit=Decimal("5000.00"), critical_percentage=Decimal("95")
        )

        trigger = BudgetAlertTrigger(threshold)

        alert = trigger.evaluate(Decimal("4800.00"))
        assert alert is not None
        assert alert.severity == "critical"

    def test_trigger_detects_budget_exceeded(self):
        """Test trigger detects when budget is exceeded."""
        threshold = BudgetThreshold(name="Test", limit=Decimal("100.00"))

        trigger = BudgetAlertTrigger(threshold)

        alert = trigger.evaluate(Decimal("110.00"))
        assert alert is not None
        assert alert.severity == "exceeded"

    def test_trigger_cooldown_prevents_spam(self):
        """Test trigger has cooldown to prevent alert spam."""
        threshold = BudgetThreshold(name="Dev", limit=Decimal("1000.00"))
        trigger = BudgetAlertTrigger(threshold, cooldown_minutes=5)

        # First alert triggers
        alert1 = trigger.evaluate(Decimal("900.00"))
        assert alert1 is not None

        # Second alert within cooldown - suppressed
        alert2 = trigger.evaluate(Decimal("910.00"))
        assert alert2 is None

    def test_trigger_resets_after_cost_decrease(self):
        """Test trigger resets when cost drops below threshold."""
        threshold = BudgetThreshold(
            name="Dev", limit=Decimal("1000.00"), warning_percentage=Decimal("80")
        )
        trigger = BudgetAlertTrigger(threshold)

        # Trigger warning
        alert1 = trigger.evaluate(Decimal("850.00"))
        assert alert1 is not None

        # Cost drops - trigger resets
        trigger.reset()

        # Can trigger again
        alert2 = trigger.evaluate(Decimal("860.00"))
        assert alert2 is not None


class TestBudgetForecast:
    """Tests for budget forecasting."""

    def test_forecast_initialization(self):
        """Test forecast initializes with historical data."""
        daily_costs = [Decimal("10.00")] * 7

        forecast = BudgetForecast(daily_costs)
        assert forecast.days == 7
        assert len(forecast.daily_costs) == 7

    def test_forecast_calculates_daily_average(self):
        """Test forecast calculates daily average from history."""
        daily_costs = [Decimal("10.00"), Decimal("12.00"), Decimal("11.00")]

        forecast = BudgetForecast(daily_costs)
        avg = forecast.get_daily_average()

        assert avg == Decimal("11.00")  # (10 + 12 + 11) / 3

    def test_forecast_projects_30_day_cost(self):
        """Test forecast projects cost for next 30 days."""
        daily_costs = [Decimal("15.00")] * 7

        forecast = BudgetForecast(daily_costs)
        projection = forecast.project_30_days()

        expected = Decimal("15.00") * 30  # Daily avg * 30
        assert projection == expected

    def test_forecast_projects_60_day_cost(self):
        """Test forecast projects cost for next 60 days."""
        daily_costs = [Decimal("20.00")] * 14

        forecast = BudgetForecast(daily_costs)
        projection = forecast.project_60_days()

        expected = Decimal("20.00") * 60
        assert projection == expected

    def test_forecast_projects_90_day_cost(self):
        """Test forecast projects cost for next 90 days."""
        daily_costs = [Decimal("25.00")] * 30

        forecast = BudgetForecast(daily_costs)
        projection = forecast.project_90_days()

        expected = Decimal("25.00") * 90
        assert projection == expected

    def test_forecast_detects_increasing_trend(self):
        """Test forecast detects increasing cost trend."""
        daily_costs = [Decimal(f"{i * 10}.00") for i in range(1, 8)]  # 10, 20, 30...70

        forecast = BudgetForecast(daily_costs)
        trend = forecast.get_trend()

        assert trend == "increasing"
        assert forecast.get_trend_percentage() > 0

    def test_forecast_detects_decreasing_trend(self):
        """Test forecast detects decreasing cost trend."""
        daily_costs = [Decimal(f"{70 - i * 10}.00") for i in range(7)]  # 70, 60, 50...10

        forecast = BudgetForecast(daily_costs)
        trend = forecast.get_trend()

        assert trend == "decreasing"
        assert forecast.get_trend_percentage() < 0

    def test_forecast_predicts_budget_breach_date(self):
        """Test forecast predicts when budget will be breached."""
        daily_costs = [Decimal("10.00")] * 7
        current_cost = Decimal("100.00")
        budget_limit = Decimal("500.00")

        forecast = BudgetForecast(daily_costs)
        breach_date = forecast.predict_breach_date(current_cost, budget_limit)

        # Should breach in (500-100)/10 = 40 days
        expected_date = datetime.now().date() + timedelta(days=40)
        assert breach_date.date() == expected_date


class TestBudgetAlertManager:
    """Tests for budget alert management system."""

    def test_manager_initialization(self):
        """Test manager initializes with thresholds."""
        thresholds = [
            BudgetThreshold(name="Dev", limit=Decimal("1000.00")),
            BudgetThreshold(name="Prod", limit=Decimal("5000.00")),
        ]

        manager = BudgetAlertManager(thresholds)
        assert len(manager.thresholds) == 2

    def test_manager_checks_all_thresholds(self):
        """Test manager checks cost against all thresholds."""
        thresholds = [
            BudgetThreshold(name="Dev", limit=Decimal("1000.00"), warning_percentage=Decimal("80")),
            BudgetThreshold(name="Prod", limit=Decimal("5000.00"), warning_percentage=Decimal("80")),
        ]

        manager = BudgetAlertManager(thresholds)
        alerts = manager.check_budgets({"Dev": Decimal("900.00"), "Prod": Decimal("4500.00")})

        # Both should trigger warning alerts
        assert len(alerts) == 2

    def test_manager_tracks_alert_history(self):
        """Test manager maintains history of triggered alerts."""
        threshold = BudgetThreshold(name="Dev", limit=Decimal("1000.00"))
        manager = BudgetAlertManager([threshold])

        manager.check_budgets({"Dev": Decimal("900.00")})
        manager.check_budgets({"Dev": Decimal("950.00")})

        history = manager.get_alert_history("Dev")
        assert len(history) >= 2

    @patch("azlin.costs.notifications.send_email")
    def test_manager_sends_email_notifications(self, mock_email):
        """Test manager sends email notifications for alerts."""
        threshold = BudgetThreshold(name="Prod", limit=Decimal("5000.00"))
        manager = BudgetAlertManager([threshold], notify_email="admin@example.com")

        manager.check_budgets({"Prod": Decimal("5500.00")})

        mock_email.assert_called_once()
        call_args = mock_email.call_args[0]
        assert "exceeded" in call_args[2].lower()  # Email body contains "exceeded"

    def test_manager_supports_custom_notification_handlers(self):
        """Test manager supports custom notification callbacks."""
        threshold = BudgetThreshold(name="Dev", limit=Decimal("1000.00"))
        notifications = []

        def custom_handler(alert):
            notifications.append(alert)

        manager = BudgetAlertManager([threshold], notification_handler=custom_handler)
        manager.check_budgets({"Dev": Decimal("900.00")})

        assert len(notifications) == 1
        assert notifications[0].threshold_name == "Dev"


class TestBudgetViolation:
    """Tests for budget violation tracking."""

    def test_violation_records_breach_details(self):
        """Test violation records when and how budget was breached."""
        violation = BudgetViolation(
            threshold_name="Production",
            limit=Decimal("5000.00"),
            actual_cost=Decimal("5500.00"),
            overage=Decimal("500.00"),
            overage_percentage=Decimal("10.0"),
            detected_at=datetime.now(),
        )

        assert violation.overage == Decimal("500.00")
        assert violation.overage_percentage == Decimal("10.0")

    def test_violation_generates_remediation_plan(self):
        """Test violation generates plan to return to budget."""
        violation = BudgetViolation(
            threshold_name="Dev",
            limit=Decimal("1000.00"),
            actual_cost=Decimal("1200.00"),
            overage=Decimal("200.00"),
            overage_percentage=Decimal("20.0"),
            detected_at=datetime.now(),
        )

        plan = violation.get_remediation_plan()

        assert "reduce" in plan.lower() or "stop" in plan.lower()
        assert "$200.00" in plan  # Shows amount to save

    def test_violation_tracks_resolution(self):
        """Test violation can track when it's resolved."""
        violation = BudgetViolation(
            threshold_name="Test",
            limit=Decimal("100.00"),
            actual_cost=Decimal("120.00"),
            overage=Decimal("20.00"),
            overage_percentage=Decimal("20.0"),
            detected_at=datetime.now(),
        )

        assert not violation.is_resolved()

        violation.mark_resolved(datetime.now())
        assert violation.is_resolved()
