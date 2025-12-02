"""Unit tests for cost history and trends.

Test Structure: 60% Unit tests (TDD Red Phase)
Feature: Cost history tracking and trend analysis (30/60/90 days)

These tests follow TDD approach - ALL tests should FAIL initially until
the history tracking implementation is complete.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from azlin.costs.history import (
    CostHistory,
    CostHistoryEntry,
    CostHistoryStore,
    CostTrend,
    TrendAnalyzer,
    TimeRange,
)


class TestCostHistoryEntry:
    """Tests for individual cost history entries."""

    def test_entry_initialization(self):
        """Test history entry initializes with correct data."""
        entry = CostHistoryEntry(
            resource_group="test-rg",
            date=datetime.now().date(),
            total_cost=Decimal("150.50"),
            resource_breakdown={"VirtualMachine": Decimal("100.00"), "Storage": Decimal("50.50")},
        )

        assert entry.resource_group == "test-rg"
        assert entry.total_cost == Decimal("150.50")
        assert len(entry.resource_breakdown) == 2

    def test_entry_supports_comparison(self):
        """Test entries can be compared by date."""
        entry1 = CostHistoryEntry(
            resource_group="test-rg",
            date=datetime(2024, 1, 1).date(),
            total_cost=Decimal("100.00"),
        )

        entry2 = CostHistoryEntry(
            resource_group="test-rg",
            date=datetime(2024, 1, 2).date(),
            total_cost=Decimal("110.00"),
        )

        assert entry2 > entry1
        assert entry1 < entry2

    def test_entry_calculates_day_over_day_change(self):
        """Test entry can calculate change from previous day."""
        previous = CostHistoryEntry(
            resource_group="test-rg",
            date=datetime(2024, 1, 1).date(),
            total_cost=Decimal("100.00"),
        )

        current = CostHistoryEntry(
            resource_group="test-rg",
            date=datetime(2024, 1, 2).date(),
            total_cost=Decimal("110.00"),
        )

        change = current.calculate_change_from(previous)
        assert change == Decimal("10.00")

        percentage = current.calculate_percentage_change_from(previous)
        assert percentage == Decimal("10.0")  # 10% increase


class TestCostHistoryStore:
    """Tests for cost history storage."""

    def test_store_initialization(self):
        """Test store initializes empty."""
        store = CostHistoryStore()
        assert store.is_empty()

    def test_store_adds_entries(self):
        """Test store can add history entries."""
        store = CostHistoryStore()

        entry = CostHistoryEntry(
            resource_group="test-rg",
            date=datetime.now().date(),
            total_cost=Decimal("150.00"),
        )

        store.add(entry)
        assert not store.is_empty()
        assert store.count() == 1

    def test_store_prevents_duplicate_dates(self):
        """Test store updates duplicate entries for same date."""
        store = CostHistoryStore()
        date = datetime.now().date()

        entry1 = CostHistoryEntry(resource_group="test-rg", date=date, total_cost=Decimal("100.00"))

        entry2 = CostHistoryEntry(resource_group="test-rg", date=date, total_cost=Decimal("110.00"))

        store.add(entry1)
        assert store.count() == 1

        # Adding duplicate date updates existing entry
        store.add(entry2)
        assert store.count() == 1  # Still only 1 entry

        # Verify updated value
        entries = store.get_all()
        assert entries[0].total_cost == Decimal("110.00")

    def test_store_retrieves_by_date_range(self):
        """Test store can retrieve entries by date range."""
        store = CostHistoryStore()

        for i in range(10):
            date = datetime.now().date() - timedelta(days=i)
            entry = CostHistoryEntry(
                resource_group="test-rg", date=date, total_cost=Decimal(f"{100 + i}.00")
            )
            store.add(entry)

        # Get last 7 days
        start = datetime.now().date() - timedelta(days=6)
        end = datetime.now().date()

        entries = store.get_range(start, end)
        assert len(entries) == 7

    def test_store_sorts_entries_chronologically(self):
        """Test store returns entries in chronological order."""
        store = CostHistoryStore()

        # Add entries out of order
        dates = [
            datetime.now().date() - timedelta(days=2),
            datetime.now().date(),
            datetime.now().date() - timedelta(days=1),
        ]

        for date in dates:
            entry = CostHistoryEntry(resource_group="test-rg", date=date, total_cost=Decimal("100.00"))
            store.add(entry)

        all_entries = store.get_all()
        assert all_entries[0].date < all_entries[1].date < all_entries[2].date

    def test_store_persists_to_disk(self, tmp_path):
        """Test store can persist history to disk."""
        store_file = tmp_path / "cost_history.json"
        store = CostHistoryStore(store_path=store_file)

        entry = CostHistoryEntry(
            resource_group="test-rg",
            date=datetime.now().date(),
            total_cost=Decimal("150.00"),
        )

        store.add(entry)
        store.save()

        assert store_file.exists()

    def test_store_loads_from_disk(self, tmp_path):
        """Test store can load persisted history."""
        store_file = tmp_path / "cost_history.json"

        # Create and save
        store1 = CostHistoryStore(store_path=store_file)
        entry = CostHistoryEntry(
            resource_group="test-rg",
            date=datetime.now().date(),
            total_cost=Decimal("150.00"),
        )
        store1.add(entry)
        store1.save()

        # Load in new instance
        store2 = CostHistoryStore(store_path=store_file)
        store2.load()

        assert store2.count() == 1
        assert store2.get_all()[0].total_cost == Decimal("150.00")


class TestTimeRange:
    """Tests for time range helpers."""

    def test_time_range_30_days(self):
        """Test 30-day time range calculation."""
        time_range = TimeRange.last_30_days()

        assert time_range.days == 30
        assert time_range.end_date == datetime.now().date()
        assert time_range.start_date == datetime.now().date() - timedelta(days=29)

    def test_time_range_60_days(self):
        """Test 60-day time range calculation."""
        time_range = TimeRange.last_60_days()

        assert time_range.days == 60
        assert time_range.end_date == datetime.now().date()
        assert time_range.start_date == datetime.now().date() - timedelta(days=59)

    def test_time_range_90_days(self):
        """Test 90-day time range calculation."""
        time_range = TimeRange.last_90_days()

        assert time_range.days == 90

    def test_time_range_custom(self):
        """Test custom time range."""
        start = datetime(2024, 1, 1).date()
        end = datetime(2024, 1, 31).date()

        time_range = TimeRange.custom(start, end)

        assert time_range.start_date == start
        assert time_range.end_date == end
        assert time_range.days == 31  # Jan 1-31 inclusive is 31 days

    def test_time_range_validates_dates(self):
        """Test time range validates start before end."""
        with pytest.raises(ValueError) as exc_info:
            TimeRange.custom(
                start_date=datetime(2024, 2, 1).date(),
                end_date=datetime(2024, 1, 1).date(),  # Before start
            )

        assert "start" in str(exc_info.value).lower()


class TestCostHistory:
    """Tests for main cost history interface."""

    def test_history_initialization(self):
        """Test history initializes with store."""
        history = CostHistory(resource_group="test-rg")
        assert history.resource_group == "test-rg"

    @patch("azlin.costs.dashboard.CostDashboard")
    def test_history_records_daily_snapshot(self, mock_dashboard, tmp_path):
        """Test history records daily cost snapshot."""
        mock_dashboard.return_value.get_current_metrics.return_value = Mock(
            total_cost=Decimal("150.00"),
            resource_breakdown=[]
        )

        # Use temporary store path to ensure clean state
        store_path = tmp_path / "cost_history.json"
        history = CostHistory(resource_group="test-rg", store_path=store_path)
        history.record_daily_snapshot()

        assert history.store.count() == 1

    def test_history_retrieves_30_day_range(self):
        """Test history retrieves last 30 days."""
        history = CostHistory(resource_group="test-rg")

        # Add 30 days of entries
        for i in range(30):
            date = datetime.now().date() - timedelta(days=i)
            entry = CostHistoryEntry(
                resource_group="test-rg", date=date, total_cost=Decimal(f"{100 + i}.00")
            )
            history.store.add(entry)

        entries = history.get_last_30_days()
        assert len(entries) == 30

    def test_history_retrieves_60_day_range(self):
        """Test history retrieves last 60 days."""
        history = CostHistory(resource_group="test-rg")

        for i in range(60):
            date = datetime.now().date() - timedelta(days=i)
            entry = CostHistoryEntry(
                resource_group="test-rg", date=date, total_cost=Decimal(f"{100 + i}.00")
            )
            history.store.add(entry)

        entries = history.get_last_60_days()
        assert len(entries) == 60

    def test_history_retrieves_90_day_range(self):
        """Test history retrieves last 90 days."""
        history = CostHistory(resource_group="test-rg")

        for i in range(90):
            date = datetime.now().date() - timedelta(days=i)
            entry = CostHistoryEntry(
                resource_group="test-rg", date=date, total_cost=Decimal(f"{100 + i}.00")
            )
            history.store.add(entry)

        entries = history.get_last_90_days()
        assert len(entries) == 90

    def test_history_calculates_average_daily_cost(self):
        """Test history calculates average daily cost over period."""
        history = CostHistory(resource_group="test-rg")

        for i in range(7):
            date = datetime.now().date() - timedelta(days=i)
            entry = CostHistoryEntry(resource_group="test-rg", date=date, total_cost=Decimal("100.00"))
            history.store.add(entry)

        avg = history.get_average_daily_cost(days=7)
        assert avg == Decimal("100.00")

    def test_history_calculates_total_cost_for_period(self):
        """Test history calculates total cost for time period."""
        history = CostHistory(resource_group="test-rg")

        for i in range(7):
            date = datetime.now().date() - timedelta(days=i)
            entry = CostHistoryEntry(
                resource_group="test-rg", date=date, total_cost=Decimal("10.00")
            )
            history.store.add(entry)

        total = history.get_total_cost(days=7)
        assert total == Decimal("70.00")  # 7 days * $10


class TestTrendAnalyzer:
    """Tests for cost trend analysis."""

    def test_analyzer_detects_increasing_trend(self):
        """Test analyzer detects increasing cost trend."""
        entries = []
        for i in range(30):
            date = datetime.now().date() - timedelta(days=29 - i)
            # Increasing costs
            entry = CostHistoryEntry(
                resource_group="test-rg", date=date, total_cost=Decimal(f"{100 + i * 2}.00")
            )
            entries.append(entry)

        analyzer = TrendAnalyzer(entries)
        trend = analyzer.analyze()

        assert trend.direction == "increasing"
        assert trend.slope > 0

    def test_analyzer_detects_decreasing_trend(self):
        """Test analyzer detects decreasing cost trend."""
        entries = []
        for i in range(30):
            date = datetime.now().date() - timedelta(days=29 - i)
            # Decreasing costs
            entry = CostHistoryEntry(
                resource_group="test-rg", date=date, total_cost=Decimal(f"{200 - i * 2}.00")
            )
            entries.append(entry)

        analyzer = TrendAnalyzer(entries)
        trend = analyzer.analyze()

        assert trend.direction == "decreasing"
        assert trend.slope < 0

    def test_analyzer_detects_stable_trend(self):
        """Test analyzer detects stable cost trend."""
        entries = []
        for i in range(30):
            date = datetime.now().date() - timedelta(days=29 - i)
            # Stable costs (small variations)
            entry = CostHistoryEntry(
                resource_group="test-rg", date=date, total_cost=Decimal("100.00")
            )
            entries.append(entry)

        analyzer = TrendAnalyzer(entries)
        trend = analyzer.analyze()

        assert trend.direction == "stable"
        assert abs(trend.slope) < 0.1  # Very small slope

    def test_analyzer_calculates_rate_of_change(self):
        """Test analyzer calculates daily rate of change."""
        entries = []
        for i in range(30):
            date = datetime.now().date() - timedelta(days=29 - i)
            entry = CostHistoryEntry(
                resource_group="test-rg", date=date, total_cost=Decimal(f"{100 + i}.00")
            )
            entries.append(entry)

        analyzer = TrendAnalyzer(entries)
        rate = analyzer.get_daily_change_rate()

        # Should be approximately $1/day
        assert abs(rate - Decimal("1.00")) < Decimal("0.10")

    def test_analyzer_identifies_anomalies(self):
        """Test analyzer identifies cost anomalies (spikes/drops)."""
        entries = []
        for i in range(30):
            date = datetime.now().date() - timedelta(days=29 - i)
            # Normal cost except for one spike
            cost = Decimal("100.00")
            if i == 15:
                cost = Decimal("500.00")  # Anomaly spike

            entry = CostHistoryEntry(resource_group="test-rg", date=date, total_cost=cost)
            entries.append(entry)

        analyzer = TrendAnalyzer(entries)
        anomalies = analyzer.detect_anomalies()

        assert len(anomalies) == 1
        assert anomalies[0].date == (datetime.now().date() - timedelta(days=14))

    def test_analyzer_projects_future_costs(self):
        """Test analyzer projects future costs based on trend."""
        entries = []
        for i in range(30):
            date = datetime.now().date() - timedelta(days=29 - i)
            # Linear increase
            entry = CostHistoryEntry(
                resource_group="test-rg", date=date, total_cost=Decimal(f"{100 + i}.00")
            )
            entries.append(entry)

        analyzer = TrendAnalyzer(entries)
        projection = analyzer.project_cost(days=30)

        # Should project continued linear growth
        assert projection > Decimal("130.00")  # Current + 30 days of growth


class TestCostTrend:
    """Tests for cost trend data structure."""

    def test_trend_initialization(self):
        """Test trend initializes with analysis data."""
        trend = CostTrend(
            direction="increasing",
            slope=Decimal("2.50"),
            confidence=Decimal("0.95"),
            start_cost=Decimal("100.00"),
            end_cost=Decimal("175.00"),
            days_analyzed=30,
        )

        assert trend.direction == "increasing"
        assert trend.slope == Decimal("2.50")
        assert trend.confidence == Decimal("0.95")

    def test_trend_calculates_total_change(self):
        """Test trend calculates total cost change over period."""
        trend = CostTrend(
            direction="increasing",
            slope=Decimal("2.50"),
            confidence=Decimal("0.95"),
            start_cost=Decimal("100.00"),
            end_cost=Decimal("175.00"),
            days_analyzed=30,
        )

        total_change = trend.get_total_change()
        assert total_change == Decimal("75.00")

    def test_trend_calculates_percentage_change(self):
        """Test trend calculates percentage change."""
        trend = CostTrend(
            direction="increasing",
            slope=Decimal("2.50"),
            confidence=Decimal("0.95"),
            start_cost=Decimal("100.00"),
            end_cost=Decimal("150.00"),
            days_analyzed=30,
        )

        percentage = trend.get_percentage_change()
        assert percentage == Decimal("50.0")  # 50% increase

    def test_trend_formats_for_display(self):
        """Test trend formats nicely for display."""
        trend = CostTrend(
            direction="decreasing",
            slope=Decimal("-1.50"),
            confidence=Decimal("0.90"),
            start_cost=Decimal("200.00"),
            end_cost=Decimal("155.00"),
            days_analyzed=30,
        )

        formatted = trend.format()

        assert "decreasing" in formatted.lower()
        assert "-$1.50/day" in formatted or "$1.50" in formatted
        assert "30 days" in formatted
