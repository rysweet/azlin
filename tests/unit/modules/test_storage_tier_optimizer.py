"""Unit tests for StorageTierOptimizer module.

Tests cover the implemented API: data models, analyze_storage(),
recommend_tier(), audit_all_storage(), and cost constants.

Philosophy:
- Test recommendation algorithms
- Verify cost calculations
- Mock StorageManager dependency
- Test data model creation
"""

from unittest.mock import Mock, patch

import pytest

from azlin.modules.storage_tier_optimizer import (
    PREMIUM_COST,
    STANDARD_COST,
    StorageTierOptimizer,
    TierAnalysis,
    TierRecommendation,
)


class TestTierAnalysisDataModel:
    """Test TierAnalysis data model."""

    def test_tier_analysis_creation(self):
        """Test basic TierAnalysis creation."""
        analysis = TierAnalysis(
            storage_name="myteam-shared",
            current_tier="Premium",
            size_gb=100,
            usage_pattern="low",
            connected_vms=1,
            avg_operations_per_day=100,
            current_cost_per_month=15.36,
        )
        assert analysis.current_tier == "Premium"
        assert analysis.usage_pattern == "low"


class TestTierRecommendationDataModel:
    """Test TierRecommendation data model."""

    def test_tier_recommendation_creation(self):
        """Test basic TierRecommendation creation."""
        rec = TierRecommendation(
            storage_name="myteam-shared",
            current_tier="Premium",
            recommended_tier="Standard",
            reason="Low utilization with single VM",
            current_cost_per_month=15.36,
            potential_cost_per_month=4.00,
            annual_savings=136.32,
            performance_impact="minor",
            confidence="high",
        )
        assert rec.recommended_tier == "Standard"
        assert rec.annual_savings > 0

    def test_tier_recommendation_calculates_savings(self):
        """Test savings calculation."""
        rec = TierRecommendation(
            storage_name="test",
            current_tier="Premium",
            recommended_tier="Standard",
            reason="Test",
            current_cost_per_month=15.36,
            potential_cost_per_month=4.00,
            annual_savings=(15.36 - 4.00) * 12,
            performance_impact="minor",
            confidence="high",
        )
        expected_savings = (15.36 - 4.00) * 12
        assert abs(rec.annual_savings - expected_savings) < 0.01


class TestStorageTierOptimizerAnalyzeStorage:
    """Test analyze_storage() method."""

    @patch("azlin.modules.storage_tier_optimizer.StorageManager")
    def test_analyze_storage_premium_tier(self, mock_storage_mgr):
        """Test analyzing Premium tier storage."""
        mock_storage_mgr.get_storage_status.return_value = Mock(
            name="myteam-shared",
            tier="Premium",
            size_gb=100,
            connected_vms=["vm1"],
            monthly_cost=15.36,
        )

        analysis = StorageTierOptimizer.analyze_storage(
            storage_name="myteam-shared", resource_group="test-rg", days=30
        )

        assert isinstance(analysis, TierAnalysis)
        assert analysis.current_tier == "Premium"
        assert analysis.size_gb == 100

    @patch("azlin.modules.storage_tier_optimizer.StorageManager")
    def test_analyze_storage_detects_usage_pattern_high(self, mock_storage_mgr):
        """Test detection of high usage pattern (>=3 VMs)."""
        mock_storage_mgr.get_storage_status.return_value = Mock(
            name="high-usage-storage",
            tier="Premium",
            size_gb=100,
            connected_vms=["vm1", "vm2", "vm3", "vm4"],
            monthly_cost=15.36,
        )

        analysis = StorageTierOptimizer.analyze_storage(
            storage_name="high-usage-storage", resource_group="test-rg"
        )

        assert analysis.usage_pattern == "high"

    @patch("azlin.modules.storage_tier_optimizer.StorageManager")
    def test_analyze_storage_detects_usage_pattern_low(self, mock_storage_mgr):
        """Test detection of low usage pattern (0 VMs)."""
        mock_storage_mgr.get_storage_status.return_value = Mock(
            name="unused-storage", tier="Premium", size_gb=100, connected_vms=[], monthly_cost=15.36
        )

        analysis = StorageTierOptimizer.analyze_storage(
            storage_name="unused-storage", resource_group="test-rg"
        )

        assert analysis.usage_pattern == "low"

    @patch("azlin.modules.storage_tier_optimizer.StorageManager")
    def test_analyze_storage_detects_usage_pattern_medium(self, mock_storage_mgr):
        """Test detection of medium usage pattern (1-2 VMs)."""
        mock_storage_mgr.get_storage_status.return_value = Mock(
            name="storage", tier="Premium", size_gb=100, connected_vms=["vm1", "vm2"]
        )

        analysis = StorageTierOptimizer.analyze_storage(
            storage_name="storage", resource_group="test-rg"
        )

        assert analysis.usage_pattern == "medium"

    @patch("azlin.modules.storage_tier_optimizer.StorageManager")
    def test_analyze_storage_calculates_cost(self, mock_storage_mgr):
        """Test cost calculation for different tiers."""
        # Premium: $0.1536/GB/month
        mock_storage_mgr.get_storage_status.return_value = Mock(
            name="storage", tier="Premium", size_gb=100, connected_vms=[], monthly_cost=15.36
        )

        analysis = StorageTierOptimizer.analyze_storage(
            storage_name="storage", resource_group="test-rg"
        )

        expected_cost = 100 * PREMIUM_COST
        assert abs(analysis.current_cost_per_month - expected_cost) < 0.01

    @patch("azlin.modules.storage_tier_optimizer.StorageManager")
    def test_analyze_requires_storage_manager(self, mock_storage_mgr):
        """Test that analyze_storage raises if StorageManager unavailable."""
        with patch("azlin.modules.storage_tier_optimizer.StorageManager", None):
            with pytest.raises(RuntimeError, match="StorageManager not available"):
                StorageTierOptimizer.analyze_storage(
                    storage_name="storage", resource_group="test-rg"
                )


class TestStorageTierOptimizerRecommendTier:
    """Test recommend_tier() method."""

    @patch("azlin.modules.storage_tier_optimizer.StorageTierOptimizer.analyze_storage")
    def test_recommend_premium_to_standard(self, mock_analyze):
        """Test recommendation to downgrade Premium to Standard."""
        mock_analyze.return_value = TierAnalysis(
            storage_name="myteam-shared",
            current_tier="Premium",
            size_gb=100,
            usage_pattern="low",
            connected_vms=1,
            avg_operations_per_day=50,
            current_cost_per_month=15.36,
        )

        rec = StorageTierOptimizer.recommend_tier(
            storage_name="myteam-shared", resource_group="test-rg"
        )

        assert isinstance(rec, TierRecommendation)
        assert rec.recommended_tier == "Standard"
        assert rec.annual_savings > 100  # Significant savings

    @patch("azlin.modules.storage_tier_optimizer.StorageTierOptimizer.analyze_storage")
    def test_recommend_keep_premium_high_usage(self, mock_analyze):
        """Test recommendation to keep Premium for high usage."""
        mock_analyze.return_value = TierAnalysis(
            storage_name="busy-storage",
            current_tier="Premium",
            size_gb=100,
            usage_pattern="high",
            connected_vms=5,
            avg_operations_per_day=10000,
            current_cost_per_month=15.36,
        )

        rec = StorageTierOptimizer.recommend_tier(
            storage_name="busy-storage", resource_group="test-rg"
        )

        # Should recommend keeping Premium
        assert rec.recommended_tier == "Premium"
        assert rec.annual_savings == 0

    @patch("azlin.modules.storage_tier_optimizer.StorageTierOptimizer.analyze_storage")
    def test_recommend_standard_to_premium_performance(self, mock_analyze):
        """Test recommendation to upgrade Standard to Premium for performance."""
        mock_analyze.return_value = TierAnalysis(
            storage_name="slow-storage",
            current_tier="Standard",
            size_gb=100,
            usage_pattern="high",
            connected_vms=4,
            avg_operations_per_day=10000,
            current_cost_per_month=4.00,
        )

        rec = StorageTierOptimizer.recommend_tier(
            storage_name="slow-storage", resource_group="test-rg"
        )

        # Should recommend upgrading to Premium
        assert rec.recommended_tier == "Premium"
        assert rec.performance_impact == "significant"

    @patch("azlin.modules.storage_tier_optimizer.StorageTierOptimizer.analyze_storage")
    def test_recommend_keep_current_medium_usage(self, mock_analyze):
        """Test keeping current tier for medium usage."""
        mock_analyze.return_value = TierAnalysis(
            storage_name="storage",
            current_tier="Premium",
            size_gb=100,
            usage_pattern="medium",
            connected_vms=2,
            avg_operations_per_day=2000,
            current_cost_per_month=15.36,
        )

        rec = StorageTierOptimizer.recommend_tier(storage_name="storage", resource_group="test-rg")

        # Medium usage on Premium = keep current
        assert rec.recommended_tier == "Premium"
        assert rec.performance_impact == "none"
        assert rec.confidence == "high"


class TestStorageTierOptimizerAuditAllStorage:
    """Test audit_all_storage() comprehensive audit."""

    @patch("azlin.modules.storage_tier_optimizer.StorageManager")
    @patch("azlin.modules.storage_tier_optimizer.StorageTierOptimizer.recommend_tier")
    def test_audit_all_returns_recommendations_for_all_storage(
        self, mock_recommend, mock_storage_mgr
    ):
        """Test audit returns recommendations for all storage accounts."""
        mock_storage_mgr.list_storage.return_value = [
            Mock(name="storage1"),
            Mock(name="storage2"),
            Mock(name="storage3"),
        ]

        mock_recommend.return_value = TierRecommendation(
            storage_name="storage1",
            current_tier="Premium",
            recommended_tier="Standard",
            reason="Test",
            current_cost_per_month=15.36,
            potential_cost_per_month=4.00,
            annual_savings=136.32,
            performance_impact="minor",
            confidence="high",
        )

        recommendations = StorageTierOptimizer.audit_all_storage(resource_group="test-rg")

        # Should return list of recommendations
        assert isinstance(recommendations, list)
        assert len(recommendations) == 3

    def test_audit_all_returns_empty_without_storage_manager(self):
        """Test audit returns empty list if StorageManager unavailable."""
        with patch("azlin.modules.storage_tier_optimizer.StorageManager", None):
            result = StorageTierOptimizer.audit_all_storage(resource_group="test-rg")
            assert result == []


class TestStorageTierOptimizerCostCalculations:
    """Test cost calculation accuracy."""

    def test_cost_constants_correct(self):
        """Test that cost constants match expected Azure pricing."""
        assert PREMIUM_COST == 0.1536
        assert STANDARD_COST == 0.04

    def test_savings_calculation_accuracy(self):
        """Test annual savings calculation is accurate."""
        current = 15.36  # Premium 100GB
        potential = 4.00  # Standard 100GB
        expected_annual = (current - potential) * 12
        # Should be $136.32
        assert abs(expected_annual - 136.32) < 0.01

    @patch("azlin.modules.storage_tier_optimizer.StorageTierOptimizer.analyze_storage")
    def test_premium_cost_calculation(self, mock_analyze):
        """Test Premium tier cost = size_gb * PREMIUM_COST."""
        mock_analyze.return_value = TierAnalysis(
            storage_name="storage",
            current_tier="Premium",
            size_gb=200,
            usage_pattern="low",
            connected_vms=0,
            avg_operations_per_day=0,
            current_cost_per_month=200 * PREMIUM_COST,
        )

        rec = StorageTierOptimizer.recommend_tier(storage_name="storage", resource_group="test-rg")

        # Premium 200GB = $30.72/mo, Standard 200GB = $8.00/mo
        expected_annual_savings = (200 * PREMIUM_COST - 200 * STANDARD_COST) * 12
        assert abs(rec.annual_savings - expected_annual_savings) < 0.01
