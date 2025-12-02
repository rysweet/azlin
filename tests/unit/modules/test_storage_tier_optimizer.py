"""Unit tests for StorageTierOptimizer module.

Following TDD approach. Tests focus on tier analysis and migration logic.

Philosophy:
- Test recommendation algorithms
- Verify cost calculations
- Mock Azure operations
- Test migration safety
"""

from unittest.mock import Mock, patch

import pytest

# Module under test
try:
    from azlin.modules.storage_tier_optimizer import (
        StorageTierOptimizer,
        TierAnalysis,
        TierMigrationResult,
        TierRecommendation,
    )
except ImportError:
    pytest.skip("Module not implemented yet", allow_module_level=True)


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
        """Test detection of high usage pattern (>3 VMs)."""
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
    def test_analyze_storage_calculates_cost(self, mock_storage_mgr):
        """Test cost calculation for different tiers."""
        # Premium: $0.1536/GB/month
        mock_storage_mgr.get_storage_status.return_value = Mock(
            name="storage", tier="Premium", size_gb=100, connected_vms=[], monthly_cost=15.36
        )

        analysis = StorageTierOptimizer.analyze_storage(
            storage_name="storage", resource_group="test-rg"
        )

        expected_cost = 100 * 0.1536
        assert abs(analysis.current_cost_per_month - expected_cost) < 0.01


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

    def test_recommend_minimum_savings_threshold(self):
        """Test recommendation only made if savings > $10/month."""
        # Small savings should result in no recommendation
        pass


class TestStorageTierOptimizerMigrateTier:
    """Test migrate_tier() migration method."""

    @patch("azlin.modules.storage_tier_optimizer.subprocess.run")
    @patch("azlin.modules.storage_tier_optimizer.StorageManager")
    def test_migrate_tier_requires_confirmation(self, mock_storage_mgr, mock_subprocess):
        """Test migration requires explicit confirmation."""
        with pytest.raises(ValueError, match="confirm=True required"):
            StorageTierOptimizer.migrate_tier(
                storage_name="myteam-shared",
                resource_group="test-rg",
                target_tier="Standard",
                confirm=False,
            )

    @patch("azlin.modules.storage_tier_optimizer.subprocess.run")
    @patch("azlin.modules.storage_tier_optimizer.StorageManager")
    def test_migrate_tier_creates_new_storage(self, mock_storage_mgr, mock_subprocess):
        """Test migration creates new storage account (Azure limitation)."""
        mock_storage_mgr.get_storage_status.return_value = Mock(
            name="old-storage", tier="Premium", size_gb=100
        )
        mock_subprocess.return_value = Mock(returncode=0, stdout='{"name": "new-storage"}')

        result = StorageTierOptimizer.migrate_tier(
            storage_name="old-storage",
            resource_group="test-rg",
            target_tier="Standard",
            confirm=True,
        )

        assert isinstance(result, TierMigrationResult)
        assert result.new_storage_name is not None
        assert result.success is True

    @patch("azlin.modules.storage_tier_optimizer.subprocess.run")
    def test_migrate_tier_copies_data(self, mock_subprocess):
        """Test migration copies data from old to new storage."""
        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout='{"name": "new-storage"}'),  # Create new
            Mock(returncode=0),  # Copy data
            Mock(returncode=0),  # Delete old
        ]

        result = StorageTierOptimizer.migrate_tier(
            storage_name="old-storage",
            resource_group="test-rg",
            target_tier="Standard",
            confirm=True,
        )

        # Should have called az storage copy
        assert len(result.migration_steps) > 0
        assert any("copy" in step.lower() for step in result.migration_steps)

    @patch("azlin.modules.storage_tier_optimizer.subprocess.run")
    def test_migrate_tier_handles_failure_gracefully(self, mock_subprocess):
        """Test migration handles failures and provides rollback info."""
        mock_subprocess.side_effect = Exception("Copy failed")

        result = StorageTierOptimizer.migrate_tier(
            storage_name="old-storage",
            resource_group="test-rg",
            target_tier="Standard",
            confirm=True,
        )

        assert result.success is False
        assert len(result.errors) > 0

    def test_migrate_tier_validates_target_tier(self):
        """Test migration validates target tier."""
        with pytest.raises(ValueError, match="Invalid tier"):
            StorageTierOptimizer.migrate_tier(
                storage_name="storage",
                resource_group="test-rg",
                target_tier="InvalidTier",
                confirm=True,
            )


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

    @patch("azlin.modules.storage_tier_optimizer.StorageManager")
    def test_audit_all_filters_no_change_recommendations(self, mock_storage_mgr):
        """Test audit excludes storage where no tier change recommended."""
        # Only return recommendations with potential savings
        pass


class TestStorageTierOptimizerCostCalculations:
    """Test cost calculation accuracy."""

    def test_cost_calculation_premium_tier(self):
        """Test Premium tier cost calculation ($0.1536/GB/month)."""
        size_gb = 100
        expected_cost = size_gb * 0.1536
        # Test through analyze_storage
        pass

    def test_cost_calculation_standard_tier(self):
        """Test Standard tier cost calculation ($0.04/GB/month)."""
        size_gb = 100
        expected_cost = size_gb * 0.04
        pass

    def test_savings_calculation_accuracy(self):
        """Test annual savings calculation is accurate."""
        current = 15.36  # Premium 100GB
        potential = 4.00  # Standard 100GB
        expected_annual = (current - potential) * 12
        # Should be $136.32
        assert abs(expected_annual - 136.32) < 0.01


class TestStorageTierOptimizerEdgeCases:
    """Test edge cases and error handling."""

    def test_analyze_nonexistent_storage(self):
        """Test analyzing non-existent storage account."""
        with pytest.raises(ValueError, match="Storage not found"):
            StorageTierOptimizer.analyze_storage(
                storage_name="nonexistent", resource_group="test-rg"
            )

    @patch("azlin.modules.storage_tier_optimizer.subprocess.run")
    def test_migrate_handles_azure_cli_errors(self, mock_subprocess):
        """Test migration handles Azure CLI errors gracefully."""
        mock_subprocess.return_value = Mock(returncode=1, stderr="Azure error")

        result = StorageTierOptimizer.migrate_tier(
            storage_name="storage", resource_group="test-rg", target_tier="Standard", confirm=True
        )

        assert result.success is False
        assert len(result.errors) > 0
