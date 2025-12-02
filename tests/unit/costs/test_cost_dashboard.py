"""Unit tests for real-time cost dashboard.

Test Structure: 60% Unit tests (TDD Red Phase)
Feature: Real-time cost dashboard with Azure API integration and caching

These tests follow TDD approach - ALL tests should FAIL initially until
the dashboard implementation is complete.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest

from azlin.costs.dashboard import (
    CostDashboard,
    CostDashboardCache,
    CostDashboardError,
    DashboardMetrics,
    ResourceCostBreakdown,
)


class TestCostDashboardCache:
    """Tests for dashboard caching mechanism (60% Unit)."""

    def test_cache_initialization(self):
        """Test cache initializes with correct TTL."""
        cache = CostDashboardCache(ttl_seconds=300)
        assert cache.ttl_seconds == 300
        assert cache.is_empty()

    def test_cache_stores_metrics(self):
        """Test cache can store dashboard metrics."""
        cache = CostDashboardCache(ttl_seconds=300)
        metrics = DashboardMetrics(
            total_cost=Decimal("100.50"),
            daily_cost=Decimal("3.50"),
            monthly_projection=Decimal("105.00"),
            resource_breakdown=[],
            last_updated=datetime.now(),
        )

        cache.set("rg-test", metrics)
        cached = cache.get("rg-test")

        assert cached is not None
        assert cached.total_cost == Decimal("100.50")
        assert cached.daily_cost == Decimal("3.50")

    def test_cache_expiration(self):
        """Test cache entries expire after TTL."""
        cache = CostDashboardCache(ttl_seconds=1)
        metrics = DashboardMetrics(
            total_cost=Decimal("100.50"),
            daily_cost=Decimal("3.50"),
            monthly_projection=Decimal("105.00"),
            resource_breakdown=[],
            last_updated=datetime.now(),
        )

        cache.set("rg-test", metrics)
        assert cache.get("rg-test") is not None

        # Wait for expiration
        import time
        time.sleep(1.1)

        assert cache.get("rg-test") is None
        assert cache.is_expired("rg-test")

    def test_cache_invalidation(self):
        """Test manual cache invalidation."""
        cache = CostDashboardCache(ttl_seconds=300)
        metrics = DashboardMetrics(
            total_cost=Decimal("100.50"),
            daily_cost=Decimal("3.50"),
            monthly_projection=Decimal("105.00"),
            resource_breakdown=[],
            last_updated=datetime.now(),
        )

        cache.set("rg-test", metrics)
        cache.invalidate("rg-test")

        assert cache.get("rg-test") is None

    def test_cache_clear_all(self):
        """Test clearing entire cache."""
        cache = CostDashboardCache(ttl_seconds=300)

        for i in range(5):
            metrics = DashboardMetrics(
                total_cost=Decimal(f"{i * 10}.00"),
                daily_cost=Decimal("3.50"),
                monthly_projection=Decimal("105.00"),
                resource_breakdown=[],
                last_updated=datetime.now(),
            )
            cache.set(f"rg-{i}", metrics)

        cache.clear()
        assert cache.is_empty()


class TestDashboardMetrics:
    """Tests for dashboard metrics data structure."""

    def test_metrics_initialization(self):
        """Test metrics object initialization."""
        now = datetime.now()
        metrics = DashboardMetrics(
            total_cost=Decimal("250.75"),
            daily_cost=Decimal("8.50"),
            monthly_projection=Decimal("255.00"),
            resource_breakdown=[],
            last_updated=now,
        )

        assert metrics.total_cost == Decimal("250.75")
        assert metrics.daily_cost == Decimal("8.50")
        assert metrics.monthly_projection == Decimal("255.00")
        assert metrics.last_updated == now

    def test_metrics_calculates_cost_trend(self):
        """Test cost trend calculation (increasing/decreasing)."""
        metrics = DashboardMetrics(
            total_cost=Decimal("250.75"),
            daily_cost=Decimal("8.50"),
            monthly_projection=Decimal("255.00"),
            previous_day_cost=Decimal("7.00"),
            resource_breakdown=[],
            last_updated=datetime.now(),
        )

        trend = metrics.get_cost_trend()
        assert trend == "increasing"
        assert metrics.get_cost_change_percent() > 0

    def test_metrics_with_resource_breakdown(self):
        """Test metrics includes resource breakdown."""
        breakdown = [
            ResourceCostBreakdown(
                resource_type="VirtualMachine",
                resource_name="azlin-vm-1",
                cost=Decimal("50.00"),
                percentage=Decimal("20.0"),
            ),
            ResourceCostBreakdown(
                resource_type="Storage",
                resource_name="storage-account-1",
                cost=Decimal("25.00"),
                percentage=Decimal("10.0"),
            ),
        ]

        metrics = DashboardMetrics(
            total_cost=Decimal("250.75"),
            daily_cost=Decimal("8.50"),
            monthly_projection=Decimal("255.00"),
            resource_breakdown=breakdown,
            last_updated=datetime.now(),
        )

        assert len(metrics.resource_breakdown) == 2
        assert metrics.get_top_resources(1)[0].resource_name == "azlin-vm-1"


class TestCostDashboard:
    """Tests for main cost dashboard functionality."""

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_dashboard_initialization(self, mock_client):
        """Test dashboard initializes with Azure client."""
        dashboard = CostDashboard(resource_group="test-rg")

        assert dashboard.resource_group == "test-rg"
        assert dashboard.cache is not None
        mock_client.assert_called_once()

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_dashboard_fetches_current_costs(self, mock_client):
        """Test dashboard fetches current costs from Azure API."""
        mock_client_instance = Mock()
        mock_client.return_value = mock_client_instance

        mock_cost_data = {
            "properties": {
                "rows": [
                    [Decimal("150.50"), "VirtualMachine", "azlin-vm-1"],
                    [Decimal("50.25"), "Storage", "storage-1"],
                ]
            }
        }
        mock_client_instance.usage.list.return_value = [mock_cost_data]

        dashboard = CostDashboard(resource_group="test-rg")
        metrics = dashboard.get_current_metrics()

        assert metrics.total_cost > 0
        assert len(metrics.resource_breakdown) == 2

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_dashboard_uses_cache_for_repeated_requests(self, mock_client):
        """Test dashboard uses cache to avoid repeated API calls."""
        dashboard = CostDashboard(resource_group="test-rg", cache_ttl=300)

        # First call - hits API
        metrics1 = dashboard.get_current_metrics()

        # Second call - should use cache
        metrics2 = dashboard.get_current_metrics()

        assert metrics1 == metrics2
        # Azure API should only be called once due to caching
        mock_client.return_value.usage.list.assert_called_once()

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_dashboard_handles_api_errors(self, mock_client):
        """Test dashboard handles Azure API errors gracefully."""
        mock_client.return_value.usage.list.side_effect = Exception("API Error")

        dashboard = CostDashboard(resource_group="test-rg")

        with pytest.raises(CostDashboardError) as exc_info:
            dashboard.get_current_metrics()

        assert "Failed to fetch cost data" in str(exc_info.value)

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_dashboard_calculates_daily_average(self, mock_client):
        """Test dashboard calculates daily cost average."""
        dashboard = CostDashboard(resource_group="test-rg")

        # Mock 7 days of cost data
        daily_costs = [Decimal("10.50")] * 7

        with patch.object(dashboard, "_fetch_daily_costs", return_value=daily_costs):
            avg = dashboard.get_daily_average(days=7)
            assert avg == Decimal("10.50")

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_dashboard_calculates_monthly_projection(self, mock_client):
        """Test dashboard projects monthly cost from current usage."""
        dashboard = CostDashboard(resource_group="test-rg")

        daily_avg = Decimal("8.50")
        projection = dashboard.calculate_monthly_projection(daily_avg)

        # 30 days * daily average
        expected = daily_avg * 30
        assert projection == expected

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_dashboard_filters_by_resource_type(self, mock_client):
        """Test dashboard can filter costs by resource type."""
        dashboard = CostDashboard(resource_group="test-rg")

        metrics = dashboard.get_current_metrics()
        vm_costs = dashboard.filter_by_resource_type(metrics, "VirtualMachine")

        assert all(r.resource_type == "VirtualMachine" for r in vm_costs)

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_dashboard_refresh_forces_cache_bypass(self, mock_client):
        """Test refresh=True bypasses cache and fetches fresh data."""
        dashboard = CostDashboard(resource_group="test-rg", cache_ttl=300)

        # First call
        metrics1 = dashboard.get_current_metrics()

        # Refresh call should bypass cache
        metrics2 = dashboard.get_current_metrics(refresh=True)

        # API should be called twice
        assert mock_client.return_value.usage.list.call_count == 2


class TestResourceCostBreakdown:
    """Tests for resource cost breakdown."""

    def test_breakdown_initialization(self):
        """Test breakdown object initialization."""
        breakdown = ResourceCostBreakdown(
            resource_type="VirtualMachine",
            resource_name="azlin-vm-1",
            cost=Decimal("150.00"),
            percentage=Decimal("30.0"),
        )

        assert breakdown.resource_type == "VirtualMachine"
        assert breakdown.resource_name == "azlin-vm-1"
        assert breakdown.cost == Decimal("150.00")
        assert breakdown.percentage == Decimal("30.0")

    def test_breakdown_comparison(self):
        """Test breakdown objects can be compared by cost."""
        b1 = ResourceCostBreakdown(
            resource_type="VM", resource_name="vm-1", cost=Decimal("100.00"), percentage=Decimal("50.0")
        )
        b2 = ResourceCostBreakdown(
            resource_type="VM", resource_name="vm-2", cost=Decimal("150.00"), percentage=Decimal("50.0")
        )

        assert b2 > b1
        assert b1 < b2

    def test_breakdown_formatting(self):
        """Test breakdown formats nicely for display."""
        breakdown = ResourceCostBreakdown(
            resource_type="VirtualMachine",
            resource_name="azlin-vm-production-01",
            cost=Decimal("150.50"),
            percentage=Decimal("33.5"),
        )

        formatted = breakdown.format()
        assert "VirtualMachine" in formatted
        assert "azlin-vm-production-01" in formatted
        assert "$150.50" in formatted
        assert "33.5%" in formatted


class TestDashboardIntegrationPoints:
    """Tests for dashboard integration with other modules."""

    @patch("azlin.costs.dashboard.CostTracker")
    def test_dashboard_integrates_with_cost_tracker(self, mock_tracker):
        """Test dashboard uses CostTracker for VM-specific costs."""
        dashboard = CostDashboard(resource_group="test-rg")

        vm_costs = dashboard.get_vm_costs()

        mock_tracker.estimate_costs.assert_called_once_with("test-rg")

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_dashboard_exports_metrics_to_json(self, mock_client):
        """Test dashboard can export metrics as JSON."""
        dashboard = CostDashboard(resource_group="test-rg")
        metrics = dashboard.get_current_metrics()

        json_export = dashboard.export_to_json(metrics)

        assert "total_cost" in json_export
        assert "daily_cost" in json_export
        assert "resource_breakdown" in json_export

    @patch("azlin.costs.dashboard.AzureCostManagementClient")
    def test_dashboard_supports_multiple_resource_groups(self, mock_client):
        """Test dashboard can track multiple resource groups."""
        dashboard1 = CostDashboard(resource_group="rg-1")
        dashboard2 = CostDashboard(resource_group="rg-2")

        metrics1 = dashboard1.get_current_metrics()
        metrics2 = dashboard2.get_current_metrics()

        # Should maintain separate metrics for each RG
        assert metrics1 != metrics2
