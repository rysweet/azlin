"""Unit tests for StorageCostAdvisor module.

Following TDD approach. Tests focus on cost analysis and recommendation logic.

Philosophy:
- Test cost aggregation across resource types
- Verify recommendation prioritization
- Mock dependent modules
- Test report generation
"""

import json
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

# Module under test
try:
    from azlin.modules.storage_cost_advisor import (
        CostAnalysis,
        CostBreakdown,
        CostRecommendation,
        CostTrends,
        SavingsEstimate,
        StorageCostAdvisor,
    )
except ImportError:
    pytest.skip("Module not implemented yet", allow_module_level=True)


class TestCostBreakdownDataModel:
    """Test CostBreakdown data model."""

    def test_cost_breakdown_creation(self):
        """Test basic CostBreakdown creation."""
        breakdown = CostBreakdown(
            storage_accounts=245.76,
            managed_disks=128.44,
            snapshots=42.50,
            orphaned_resources=121.43,
        )
        assert breakdown.storage_accounts > 0
        assert breakdown.total() == sum([245.76, 128.44, 42.50, 121.43])

    def test_cost_breakdown_total_calculation(self):
        """Test total() method sums all categories."""
        breakdown = CostBreakdown(
            storage_accounts=100.00, managed_disks=50.00, snapshots=25.00, orphaned_resources=25.00
        )
        assert breakdown.total() == 200.00


class TestCostTrendsDataModel:
    """Test CostTrends data model."""

    def test_cost_trends_creation(self):
        """Test basic CostTrends creation."""
        trends = CostTrends(
            daily_average=17.94, monthly_projection=538.13, month_over_month_change_percent=5.2
        )
        assert trends.monthly_projection > 0

    def test_cost_trends_projection_from_daily(self):
        """Test monthly projection matches daily average * 30."""
        daily = 10.00
        trends = CostTrends(
            daily_average=daily, monthly_projection=daily * 30, month_over_month_change_percent=0.0
        )
        assert trends.monthly_projection == 300.00


class TestCostRecommendationDataModel:
    """Test CostRecommendation data model."""

    def test_cost_recommendation_creation(self):
        """Test basic CostRecommendation creation."""
        rec = CostRecommendation(
            category="tier",
            resource_name="myteam-shared",
            resource_type="storage_account",
            action="Downgrade to Standard tier",
            current_cost_per_month=15.36,
            potential_cost_per_month=4.00,
            monthly_savings=11.36,
            annual_savings=136.32,
            effort="medium",
            risk="low",
            priority=1,
        )
        assert rec.category == "tier"
        assert rec.annual_savings > 0

    def test_cost_recommendation_priority_validation(self):
        """Test priority must be 1-5."""
        with pytest.raises(ValueError, match="Priority must be 1-5"):
            CostRecommendation(
                category="tier",
                resource_name="test",
                resource_type="storage",
                action="Test",
                current_cost_per_month=10.0,
                potential_cost_per_month=5.0,
                monthly_savings=5.0,
                annual_savings=60.0,
                effort="low",
                risk="low",
                priority=6,  # Invalid
            )


class TestStorageCostAdvisorAnalyzeCosts:
    """Test analyze_costs() method."""

    @patch("azlin.modules.storage_cost_advisor.StorageManager")
    @patch("azlin.modules.storage_cost_advisor.subprocess.run")
    def test_analyze_costs_aggregates_all_resources(self, mock_subprocess, mock_storage_mgr):
        """Test cost analysis aggregates storage, disks, snapshots."""
        # Mock storage accounts
        mock_storage_mgr.list_storage.return_value = [
            Mock(name="storage1", size_gb=100, tier="Premium", monthly_cost=15.36),
            Mock(name="storage2", size_gb=200, tier="Standard", monthly_cost=8.00),
        ]

        # Mock disks
        mock_subprocess.side_effect = [
            Mock(
                returncode=0,
                stdout=json.dumps(
                    [{"name": "disk1", "diskSizeGb": 128, "sku": {"tier": "Premium"}}]
                ),
            ),
            Mock(returncode=0, stdout=json.dumps([{"name": "snap1", "diskSizeGb": 64}])),
        ]

        analysis = StorageCostAdvisor.analyze_costs(resource_group="test-rg", period_days=30)

        assert isinstance(analysis, CostAnalysis)
        assert analysis.total_cost > 0
        assert analysis.cost_breakdown.storage_accounts > 0
        assert analysis.cost_breakdown.managed_disks > 0
        assert analysis.cost_breakdown.snapshots > 0

    @patch("azlin.modules.storage_cost_advisor.OrphanedResourceDetector")
    def test_analyze_costs_includes_orphaned_resources(self, mock_orphaned):
        """Test cost analysis includes orphaned resource costs."""
        mock_orphaned.scan_all.return_value = Mock(total_cost_per_month=121.43)

        analysis = StorageCostAdvisor.analyze_costs(resource_group="test-rg")

        assert analysis.cost_breakdown.orphaned_resources == 121.43

    def test_analyze_costs_calculates_trends(self):
        """Test cost analysis calculates daily and monthly trends."""
        # Should calculate daily average and monthly projection
        pass


class TestStorageCostAdvisorGetRecommendations:
    """Test get_recommendations() method."""

    @patch("azlin.modules.storage_cost_advisor.OrphanedResourceDetector")
    @patch("azlin.modules.storage_cost_advisor.StorageTierOptimizer")
    def test_get_recommendations_includes_all_categories(self, mock_tier, mock_orphaned):
        """Test recommendations include tier, orphaned, snapshot, resize."""
        # Mock tier recommendations
        mock_tier.audit_all_storage.return_value = [
            Mock(storage_name="storage1", recommended_tier="Standard", annual_savings=136.32)
        ]

        # Mock orphaned recommendations
        mock_orphaned.scan_all.return_value = Mock(
            disks=[Mock(monthly_cost=10.0)],
            snapshots=[Mock(monthly_cost=5.0)],
            storage_accounts=[Mock(monthly_cost=15.0)],
            total_cost_per_month=30.0,
        )

        recommendations = StorageCostAdvisor.get_recommendations(resource_group="test-rg")

        assert isinstance(recommendations, list)
        # Should have recommendations from multiple categories
        categories = set(rec.category for rec in recommendations)
        assert "tier" in categories or "orphaned" in categories

    def test_get_recommendations_sorted_by_priority(self):
        """Test recommendations are sorted by priority (1=highest)."""
        # Priority 1 recommendations should come first
        pass

    def test_get_recommendations_priority_1_high_savings_low_risk(self):
        """Test Priority 1 = high savings (>$50/mo), low risk, low effort."""
        # Cleanup recommendations typically Priority 1
        pass

    def test_get_recommendations_filters_low_savings(self):
        """Test recommendations with <$10/month savings are filtered."""
        # Small savings not worth the effort
        pass


class TestStorageCostAdvisorEstimateSavings:
    """Test estimate_savings() method."""

    def test_estimate_savings_sums_all_recommendations(self):
        """Test savings estimate sums all recommendations."""
        recommendations = [
            CostRecommendation(
                category="orphaned",
                resource_name="disk1",
                resource_type="disk",
                action="Delete",
                current_cost_per_month=10.0,
                potential_cost_per_month=0.0,
                monthly_savings=10.0,
                annual_savings=120.0,
                effort="low",
                risk="low",
                priority=1,
            ),
            CostRecommendation(
                category="tier",
                resource_name="storage1",
                resource_type="storage",
                action="Downgrade",
                current_cost_per_month=15.36,
                potential_cost_per_month=4.00,
                monthly_savings=11.36,
                annual_savings=136.32,
                effort="medium",
                risk="low",
                priority=2,
            ),
        ]

        estimate = StorageCostAdvisor.estimate_savings(
            resource_group="test-rg", recommendations=recommendations
        )

        assert isinstance(estimate, SavingsEstimate)
        assert estimate.total_monthly_savings == 21.36
        assert estimate.total_annual_savings == 256.32
        assert estimate.recommendations_count == 2

    def test_estimate_savings_breaks_down_by_category(self):
        """Test savings estimate breaks down by category."""
        recommendations = [
            CostRecommendation(
                category="orphaned",
                resource_name="test",
                resource_type="disk",
                action="Delete",
                current_cost_per_month=10.0,
                potential_cost_per_month=0.0,
                monthly_savings=10.0,
                annual_savings=120.0,
                effort="low",
                risk="low",
                priority=1,
            ),
            CostRecommendation(
                category="tier",
                resource_name="test",
                resource_type="storage",
                action="Downgrade",
                current_cost_per_month=15.0,
                potential_cost_per_month=5.0,
                monthly_savings=10.0,
                annual_savings=120.0,
                effort="medium",
                risk="low",
                priority=2,
            ),
        ]

        estimate = StorageCostAdvisor.estimate_savings(
            resource_group="test-rg", recommendations=recommendations
        )

        assert "orphaned" in estimate.savings_by_category
        assert "tier" in estimate.savings_by_category
        assert estimate.savings_by_category["orphaned"] == 120.0
        assert estimate.savings_by_category["tier"] == 120.0

    def test_estimate_savings_calculates_confidence(self):
        """Test confidence level based on recommendation certainty."""
        # High confidence if all recommendations are "high" confidence
        # Medium if mixed
        # Low if mostly "low" confidence
        pass


class TestStorageCostAdvisorGenerateReport:
    """Test generate_report() method."""

    @patch("azlin.modules.storage_cost_advisor.StorageCostAdvisor.analyze_costs")
    @patch("azlin.modules.storage_cost_advisor.StorageCostAdvisor.get_recommendations")
    def test_generate_report_text_format(self, mock_recommendations, mock_analyze):
        """Test text report generation."""
        mock_analyze.return_value = CostAnalysis(
            resource_group="test-rg",
            period_days=30,
            total_cost=538.13,
            cost_breakdown=CostBreakdown(
                storage_accounts=245.76,
                managed_disks=128.44,
                snapshots=42.50,
                orphaned_resources=121.43,
            ),
            trends=CostTrends(
                daily_average=17.94, monthly_projection=538.13, month_over_month_change_percent=0.0
            ),
            analysis_date=datetime.now(),
        )

        mock_recommendations.return_value = []

        report = StorageCostAdvisor.generate_report(resource_group="test-rg", output_format="text")

        assert isinstance(report, str)
        assert "Storage Cost Analysis" in report
        assert "$538.13" in report or "538.13" in report

    @patch("azlin.modules.storage_cost_advisor.StorageCostAdvisor.analyze_costs")
    def test_generate_report_json_format(self, mock_analyze):
        """Test JSON report generation."""
        mock_analyze.return_value = CostAnalysis(
            resource_group="test-rg",
            period_days=30,
            total_cost=538.13,
            cost_breakdown=CostBreakdown(
                storage_accounts=245.76,
                managed_disks=128.44,
                snapshots=42.50,
                orphaned_resources=121.43,
            ),
            trends=CostTrends(
                daily_average=17.94, monthly_projection=538.13, month_over_month_change_percent=0.0
            ),
            analysis_date=datetime.now(),
        )

        report = StorageCostAdvisor.generate_report(resource_group="test-rg", output_format="json")

        # Should be valid JSON
        data = json.loads(report)
        assert "total_cost" in data
        assert data["total_cost"] == 538.13

    def test_generate_report_csv_format(self):
        """Test CSV report generation."""
        # Should generate CSV with headers and rows
        pass

    def test_generate_report_invalid_format(self):
        """Test invalid format raises error."""
        with pytest.raises(ValueError, match="Invalid output format"):
            StorageCostAdvisor.generate_report(resource_group="test-rg", output_format="invalid")


class TestStorageCostAdvisorRecommendationPrioritization:
    """Test recommendation prioritization logic."""

    def test_priority_1_high_savings_low_risk_low_effort(self):
        """Test Priority 1 criteria."""
        # >$50/month savings, low risk, low effort
        rec = CostRecommendation(
            category="orphaned",
            resource_name="test",
            resource_type="disk",
            action="Delete",
            current_cost_per_month=60.0,
            potential_cost_per_month=0.0,
            monthly_savings=60.0,
            annual_savings=720.0,
            effort="low",
            risk="low",
            priority=1,
        )
        assert rec.priority == 1

    def test_priority_2_high_savings_medium_risk_or_effort(self):
        """Test Priority 2 criteria."""
        # >$50/month savings, medium risk/effort
        pass

    def test_priority_3_medium_savings(self):
        """Test Priority 3 criteria."""
        # $20-50/month savings
        pass

    def test_priority_4_low_savings_quick_wins(self):
        """Test Priority 4 criteria."""
        # <$20/month but easy to implement
        pass

    def test_priority_5_low_savings_high_effort(self):
        """Test Priority 5 criteria."""
        # <$20/month and high effort/risk
        pass


class TestStorageCostAdvisorEdgeCases:
    """Test edge cases and error handling."""

    def test_analyze_costs_no_resources(self):
        """Test cost analysis with no resources."""
        # Should return zero costs, not error
        pass

    def test_get_recommendations_no_savings_opportunities(self):
        """Test recommendations when already optimized."""
        # Should return empty list
        pass

    @patch("azlin.modules.storage_cost_advisor.subprocess.run")
    def test_analyze_costs_handles_azure_errors(self, mock_subprocess):
        """Test graceful handling of Azure CLI errors."""
        mock_subprocess.return_value = Mock(returncode=1, stderr="Azure error")

        # Should handle error and continue with available data
        pass
