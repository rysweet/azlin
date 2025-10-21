"""Tests for budget monitoring module."""

import json
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from azlin.agentic.budget_monitor import (
    AlertLevel,
    BudgetAlert,
    BudgetConfig,
    BudgetMonitor,
    BudgetPeriod,
)
from azlin.agentic.types import CostEstimate


class TestBudgetConfig:
    """Test BudgetConfig dataclass."""

    def test_default_thresholds(self):
        """Test default alert thresholds."""
        config = BudgetConfig(monthly_limit=1000.0)

        assert config.monthly_limit == 1000.0
        assert config.alert_thresholds == [50, 80, 100]

    def test_custom_thresholds(self):
        """Test custom alert thresholds."""
        config = BudgetConfig(
            monthly_limit=500.0,
            alert_thresholds=[60, 90],
        )

        assert config.alert_thresholds == [60, 90]

    def test_resource_group_limits(self):
        """Test per-resource-group limits."""
        config = BudgetConfig(
            monthly_limit=1000.0,
            resource_group_limits={"dev": 100.0, "prod": 500.0},
        )

        assert config.resource_group_limits["dev"] == 100.0
        assert config.resource_group_limits["prod"] == 500.0


class TestBudgetAlert:
    """Test BudgetAlert dataclass."""

    def test_alert_creation(self):
        """Test creating a budget alert."""
        alert = BudgetAlert(
            level=AlertLevel.WARNING,
            message="Budget warning",
            current_spend=600.0,
            budget_limit=1000.0,
            percentage_used=60.0,
            recommended_action="Monitor closely",
        )

        assert alert.level == AlertLevel.WARNING
        assert alert.percentage_used == 60.0


class TestBudgetMonitor:
    """Test BudgetMonitor class."""

    @pytest.fixture
    def temp_budget_file(self):
        """Create temporary budget config file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            budget_data = {
                "monthly_limit": 1000.0,
                "daily_limit": 50.0,
                "alert_thresholds": [50, 80, 100],
                "resource_group_limits": {"test-rg": 200.0},
            }
            json.dump(budget_data, f)
            temp_path = Path(f.name)

        # Temporarily rename to budget.json in ~/.azlin
        azlin_dir = Path.home() / ".azlin"
        azlin_dir.mkdir(exist_ok=True)
        budget_file = azlin_dir / "budget.json"

        # Backup existing if present
        backup = None
        if budget_file.exists():
            backup = budget_file.read_text()

        budget_file.write_text(temp_path.read_text())
        temp_path.unlink()

        yield budget_file

        # Restore or delete
        if backup:
            budget_file.write_text(backup)
        else:
            budget_file.unlink()

    def test_initialization_no_config(self):
        """Test monitor without config file."""
        # Ensure no budget config exists
        budget_file = Path.home() / ".azlin" / "budget.json"
        if budget_file.exists():
            pytest.skip("Budget config already exists")

        monitor = BudgetMonitor()
        assert monitor.budget_config is None

    def test_initialization_with_config(self, temp_budget_file):
        """Test monitor with config file."""
        monitor = BudgetMonitor()

        assert monitor.budget_config is not None
        assert monitor.budget_config.monthly_limit == 1000.0
        assert monitor.budget_config.daily_limit == 50.0

    def test_check_budget_no_config(self):
        """Test budget check returns None without config."""
        # Create monitor without config
        monitor = BudgetMonitor()
        monitor.budget_config = None

        estimate = CostEstimate(
            total_hourly=Decimal("0.10"),
            total_monthly=Decimal("73.00"),
            breakdown={},
            confidence="high",
        )

        alert = monitor.check_budget(estimate, BudgetPeriod.MONTHLY)
        assert alert is None

    def test_check_budget_within_limit(self, temp_budget_file):
        """Test no alert when within budget."""
        monitor = BudgetMonitor()

        # Small cost estimate
        estimate = CostEstimate(
            total_hourly=Decimal("0.05"),
            total_monthly=Decimal("40.00"),  # 4% of $1000 budget
            breakdown={},
            confidence="high",
        )

        alert = monitor.check_budget(estimate, BudgetPeriod.MONTHLY)
        assert alert is None  # Below 50% threshold

    def test_check_budget_warning_level(self, temp_budget_file):
        """Test WARNING alert at 50-80% of budget."""
        monitor = BudgetMonitor()

        # 60% of budget
        estimate = CostEstimate(
            total_hourly=Decimal("0.82"),  # ~600/month
            total_monthly=Decimal("600.00"),
            breakdown={},
            confidence="high",
        )

        alert = monitor.check_budget(estimate, BudgetPeriod.MONTHLY)

        assert alert is not None
        assert alert.level == AlertLevel.WARNING
        assert 50 <= alert.percentage_used < 80

    def test_check_budget_critical_level(self, temp_budget_file):
        """Test CRITICAL alert at 80-100% of budget."""
        monitor = BudgetMonitor()

        # 85% of budget
        estimate = CostEstimate(
            total_hourly=Decimal("1.16"),  # ~850/month
            total_monthly=Decimal("850.00"),
            breakdown={},
            confidence="high",
        )

        alert = monitor.check_budget(estimate, BudgetPeriod.MONTHLY)

        assert alert is not None
        assert alert.level == AlertLevel.CRITICAL
        assert 80 <= alert.percentage_used < 100

    def test_check_budget_exceeded(self, temp_budget_file):
        """Test EXCEEDED alert when over budget."""
        monitor = BudgetMonitor()

        # 120% of budget
        estimate = CostEstimate(
            total_hourly=Decimal("1.64"),  # ~1200/month
            total_monthly=Decimal("1200.00"),
            breakdown={},
            confidence="high",
        )

        alert = monitor.check_budget(estimate, BudgetPeriod.MONTHLY)

        assert alert is not None
        assert alert.level == AlertLevel.EXCEEDED
        assert alert.percentage_used > 100

    def test_check_budget_resource_group_limit(self, temp_budget_file):
        """Test resource group specific limits."""
        monitor = BudgetMonitor()

        # Test RG has $200 limit
        estimate = CostEstimate(
            total_hourly=Decimal("0.35"),  # ~250/month
            total_monthly=Decimal("250.00"),
            breakdown={},
            confidence="high",
        )

        alert = monitor.check_budget(
            estimate,
            BudgetPeriod.MONTHLY,
            resource_group="test-rg",
        )

        assert alert is not None
        assert alert.level == AlertLevel.EXCEEDED  # 250 > 200
        assert alert.budget_limit == 200.0

    def test_check_budget_daily_period(self, temp_budget_file):
        """Test daily budget checking."""
        monitor = BudgetMonitor()

        # Daily budget is $50
        estimate = CostEstimate(
            total_hourly=Decimal("2.5"),  # $60/day
            total_monthly=Decimal("1825.00"),
            breakdown={},
            confidence="high",
        )

        alert = monitor.check_budget(estimate, BudgetPeriod.DAILY)

        assert alert is not None
        # 60/50 = 120%
        assert alert.level == AlertLevel.EXCEEDED

    def test_get_alert_level(self):
        """Test alert level determination."""
        monitor = BudgetMonitor()

        assert monitor._get_alert_level(30) == AlertLevel.INFO
        assert monitor._get_alert_level(50) == AlertLevel.WARNING
        assert monitor._get_alert_level(70) == AlertLevel.WARNING
        assert monitor._get_alert_level(80) == AlertLevel.CRITICAL
        assert monitor._get_alert_level(95) == AlertLevel.CRITICAL
        assert monitor._get_alert_level(100) == AlertLevel.CRITICAL
        assert monitor._get_alert_level(110) == AlertLevel.EXCEEDED

    def test_create_alert_exceeded(self, temp_budget_file):
        """Test creating EXCEEDED alert with proper messaging."""
        monitor = BudgetMonitor()

        alert = monitor._create_alert(
            level=AlertLevel.EXCEEDED,
            projected_spend=1200.0,
            budget_limit=1000.0,
            percentage_used=120.0,
            period=BudgetPeriod.MONTHLY,
            resource_group=None,
        )

        assert "Budget would be exceeded" in alert.recommended_action
        assert "$1200.00" in alert.message
        assert "120.0%" in alert.message

    def test_create_alert_with_resource_group(self, temp_budget_file):
        """Test alert message includes resource group."""
        monitor = BudgetMonitor()

        alert = monitor._create_alert(
            level=AlertLevel.WARNING,
            projected_spend=150.0,
            budget_limit=200.0,
            percentage_used=75.0,
            period=BudgetPeriod.MONTHLY,
            resource_group="test-rg",
        )

        assert "test-rg" in alert.message

    def test_record_spending(self):
        """Test recording spending history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "spending_history.json"

            monitor = BudgetMonitor()
            monitor.spending_history_path = history_path

            # Record some spending
            monitor.record_spending(
                amount=150.0,
                resource_group="test-rg",
                details={"vm_count": 2},
            )

            # Verify recorded
            assert history_path.exists()
            with history_path.open() as f:
                data = json.load(f)

            assert len(data["records"]) == 1
            record = data["records"][0]
            assert record["amount"] == 150.0
            assert record["resource_group"] == "test-rg"
            assert record["details"]["vm_count"] == 2

    def test_record_multiple_spending_entries(self):
        """Test recording multiple spending entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "spending_history.json"

            monitor = BudgetMonitor()
            monitor.spending_history_path = history_path

            # Record multiple entries
            monitor.record_spending(100.0, "rg1")
            monitor.record_spending(200.0, "rg2")
            monitor.record_spending(150.0, "rg1")

            # Verify all recorded
            with history_path.open() as f:
                data = json.load(f)

            assert len(data["records"]) == 3
            amounts = [r["amount"] for r in data["records"]]
            assert amounts == [100.0, 200.0, 150.0]

    def test_get_spending_summary_no_config(self):
        """Test spending summary without config."""
        monitor = BudgetMonitor()
        monitor.budget_config = None

        summary = monitor.get_spending_summary(BudgetPeriod.MONTHLY)

        assert summary["configured"] is False
        assert "No budget configured" in summary["message"]

    def test_get_spending_summary_with_config(self, temp_budget_file):
        """Test spending summary with config."""
        monitor = BudgetMonitor()

        summary = monitor.get_spending_summary(BudgetPeriod.MONTHLY)

        assert summary["configured"] is True
        assert summary["period"] == "monthly"
        assert summary["budget_limit"] == 1000.0
        # Current spend is 0 in MVP (no historical tracking)
        assert summary["current_spend"] == 0.0
        assert summary["remaining"] == 1000.0
