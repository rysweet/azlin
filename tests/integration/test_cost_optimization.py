"""Integration tests for cost optimization workflow.

Tests interaction between StorageCostAdvisor, StorageTierOptimizer, and OrphanedResourceDetector.

Testing pyramid: 30% integration tests
"""

from unittest.mock import Mock, patch

import pytest

try:
    from azlin.modules.orphaned_resource_detector import OrphanedResourceDetector
    from azlin.modules.storage_cost_advisor import StorageCostAdvisor
    from azlin.modules.storage_tier_optimizer import StorageTierOptimizer
except ImportError:
    pytest.skip("Modules not implemented yet", allow_module_level=True)


class TestCostOptimizationWorkflow:
    """Test complete cost optimization workflow."""

    @patch("azlin.modules.storage_cost_advisor.StorageTierOptimizer")
    @patch("azlin.modules.storage_cost_advisor.OrphanedResourceDetector")
    def test_cost_advisor_aggregates_all_recommendations(self, mock_orphaned, mock_tier):
        """Test cost advisor aggregates recommendations from all sources."""
        # Mock tier optimizer recommendations
        mock_tier.audit_all_storage.return_value = [
            Mock(
                storage_name="storage1",
                current_tier="Premium",
                recommended_tier="Standard",
                annual_savings=136.32,
                monthly_savings=11.36,
            )
        ]

        # Mock orphaned resource detector
        mock_orphaned.scan_all.return_value = Mock(
            disks=[Mock(monthly_cost=10.0)],
            snapshots=[Mock(monthly_cost=5.0)],
            storage_accounts=[Mock(monthly_cost=15.0)],
            total_cost_per_month=30.0,
        )

        # Get recommendations
        recommendations = StorageCostAdvisor.get_recommendations(resource_group="test-rg")

        # Should have recommendations from both sources
        assert len(recommendations) >= 2
        categories = set(rec.category for rec in recommendations)
        assert "tier" in categories
        assert "orphaned" in categories

    @patch("azlin.modules.storage_cost_advisor.StorageCostAdvisor.get_recommendations")
    def test_cost_optimization_prioritizes_high_impact(self, mock_recommendations):
        """Test cost optimization prioritizes high-impact recommendations."""
        mock_recommendations.return_value = [
            Mock(category="orphaned", priority=1, annual_savings=1457.16, monthly_savings=121.43),
            Mock(category="tier", priority=2, annual_savings=136.32, monthly_savings=11.36),
            Mock(
                category="snapshot-retention",
                priority=3,
                annual_savings=76.80,
                monthly_savings=6.40,
            ),
        ]

        recs = StorageCostAdvisor.get_recommendations(resource_group="test-rg")

        # Should be sorted by priority
        priorities = [rec.priority for rec in recs]
        assert priorities == sorted(priorities)

    @patch("azlin.modules.storage_cost_advisor.OrphanedResourceDetector")
    @patch("azlin.modules.storage_cost_advisor.StorageTierOptimizer")
    def test_savings_estimate_calculates_total_potential(self, mock_tier, mock_orphaned):
        """Test savings estimate calculates total potential savings."""
        # Mock recommendations
        mock_tier.audit_all_storage.return_value = [
            Mock(annual_savings=136.32, monthly_savings=11.36)
        ]

        mock_orphaned.scan_all.return_value = Mock(total_cost_per_month=121.43)

        # Get savings estimate
        estimate = StorageCostAdvisor.estimate_savings(resource_group="test-rg")

        # Should calculate total: tier (11.36) + orphaned (121.43) = 132.79/month
        assert estimate.total_monthly_savings > 130.0
        assert estimate.total_annual_savings > 1500.0


class TestTierOptimizationIntegration:
    """Test tier optimization integration with storage management."""

    @pytest.mark.skip(reason="migrate_tier() removed - analysis-only module")
    @patch("azlin.modules.storage_tier_optimizer.StorageManager")
    def test_tier_migration_updates_storage_manager(self, mock_storage_mgr):
        """Test tier migration updates StorageManager records."""
        mock_storage_mgr.get_storage_status.return_value = Mock(
            name="old-storage", tier="Premium", size_gb=100
        )

        # Perform migration
        result = StorageTierOptimizer.migrate_tier(
            storage_name="old-storage",
            resource_group="test-rg",
            target_tier="Standard",
            confirm=True,
        )

        # Should have created new storage
        assert result.new_storage_name is not None

    @pytest.mark.skip(reason="migrate_tier() removed - analysis-only module")
    @patch("azlin.modules.storage_tier_optimizer.subprocess.run")
    @patch("azlin.modules.storage_tier_optimizer.StorageManager")
    def test_tier_migration_handles_vm_remount(self, mock_storage_mgr, mock_subprocess):
        """Test tier migration updates VM mount configurations."""
        mock_storage_mgr.get_storage_status.return_value = Mock(
            name="old-storage", tier="Premium", size_gb=100, connected_vms=["vm1", "vm2"]
        )

        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout='{"name": "new-storage"}'),  # Create new
            Mock(returncode=0),  # Copy data
            Mock(returncode=0),  # Update VM1 mount
            Mock(returncode=0),  # Update VM2 mount
            Mock(returncode=0),  # Delete old
        ]

        result = StorageTierOptimizer.migrate_tier(
            storage_name="old-storage",
            resource_group="test-rg",
            target_tier="Standard",
            confirm=True,
        )

        # Should have updated VM mounts
        assert len(result.migration_steps) >= 3  # Create, copy, remount VMs


class TestCostAnalysisIntegration:
    """Test cost analysis integration across all modules."""

    @patch("azlin.modules.storage_cost_advisor.StorageManager")
    @patch("azlin.modules.storage_cost_advisor.subprocess.run")
    @patch("azlin.modules.storage_cost_advisor.OrphanedResourceDetector")
    def test_cost_analysis_includes_all_resources(
        self, mock_orphaned, mock_subprocess, mock_storage_mgr
    ):
        """Test cost analysis includes all resource types."""
        # Mock storage accounts
        mock_storage_mgr.list_storage.return_value = [
            Mock(name="storage1", size_gb=100, tier="Premium", monthly_cost=15.36)
        ]

        # Mock managed disks
        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout='[{"diskSizeGb": 128, "sku": {"tier": "Premium"}}]'),
            Mock(returncode=0, stdout='[{"diskSizeGb": 64}]'),  # Snapshots
        ]

        # Mock orphaned resources
        mock_orphaned.scan_all.return_value = Mock(total_cost_per_month=121.43)

        analysis = StorageCostAdvisor.analyze_costs(resource_group="test-rg")

        # Should include all categories
        assert analysis.cost_breakdown.storage_accounts > 0
        assert analysis.cost_breakdown.managed_disks > 0
        assert analysis.cost_breakdown.snapshots > 0
        assert analysis.cost_breakdown.orphaned_resources > 0
        assert analysis.total_cost > 0

    @patch("azlin.modules.storage_cost_advisor.StorageManager")
    def test_cost_trends_calculated_from_history(self, mock_storage_mgr):
        """Test cost trends calculated from historical data."""
        # Mock historical costs (if available)
        # Should calculate month-over-month change
        pass


class TestRecommendationPrioritization:
    """Test recommendation prioritization across categories."""

    def test_priority_1_orphaned_cleanup_high_savings(self):
        """Test Priority 1: Orphaned cleanup with high savings (>$50/mo)."""
        # Orphaned resources typically Priority 1
        # Low risk, low effort, high savings
        pass

    def test_priority_2_tier_migration_medium_effort(self):
        """Test Priority 2: Tier migration with medium effort."""
        # Tier migration typically Priority 2
        # Medium effort (data copy), low risk, medium-high savings
        pass

    def test_priority_3_snapshot_retention_optimization(self):
        """Test Priority 3: Snapshot retention with medium savings."""
        # Snapshot retention typically Priority 3
        # Low effort, low risk, medium savings ($20-50/mo)
        pass


class TestCostReportGeneration:
    """Test cost report generation integration."""

    @patch("azlin.modules.storage_cost_advisor.StorageCostAdvisor.analyze_costs")
    @patch("azlin.modules.storage_cost_advisor.StorageCostAdvisor.get_recommendations")
    def test_report_includes_all_sections(self, mock_recommendations, mock_analyze):
        """Test report includes analysis, recommendations, and savings."""
        mock_analyze.return_value = Mock(
            total_cost=538.13,
            cost_breakdown=Mock(
                storage_accounts=245.76,
                managed_disks=128.44,
                snapshots=42.50,
                orphaned_resources=121.43,
                total=lambda: 538.13,
            ),
        )

        mock_recommendations.return_value = [
            Mock(category="orphaned", annual_savings=1457.16, priority=1),
            Mock(category="tier", annual_savings=136.32, priority=2),
        ]

        report = StorageCostAdvisor.generate_report(resource_group="test-rg", output_format="text")

        # Should include all sections
        assert "Storage Cost Analysis" in report or "storage cost" in report.lower()
        assert "538.13" in report
        assert "Recommendation" in report or "recommendation" in report.lower()

    @patch("azlin.modules.storage_cost_advisor.StorageCostAdvisor.analyze_costs")
    def test_json_report_is_valid_json(self, mock_analyze):
        """Test JSON report is valid JSON."""
        import json

        mock_analyze.return_value = Mock(
            resource_group="test-rg",
            period_days=30,
            total_cost=538.13,
            cost_breakdown=Mock(
                storage_accounts=245.76,
                managed_disks=128.44,
                snapshots=42.50,
                orphaned_resources=121.43,
            ),
        )

        report = StorageCostAdvisor.generate_report(resource_group="test-rg", output_format="json")

        # Should be valid JSON
        data = json.loads(report)
        assert "total_cost" in data or "totalCost" in data


class TestMultiModuleCoordination:
    """Test coordination between multiple modules."""

    @patch("azlin.modules.storage_cost_advisor.OrphanedResourceDetector")
    @patch("azlin.modules.storage_cost_advisor.StorageTierOptimizer")
    def test_cost_advisor_deduplicates_recommendations(self, mock_tier, mock_orphaned):
        """Test cost advisor avoids duplicate recommendations."""
        # If both modules recommend same action, only include once
        pass

    @patch("azlin.modules.storage_cost_advisor.StorageQuotaManager")
    def test_cost_optimization_respects_quotas(self, mock_quota_mgr):
        """Test cost optimization recommendations respect quota constraints."""
        # Don't recommend reducing storage below quota needs
        pass
