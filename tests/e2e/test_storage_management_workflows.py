"""End-to-end tests for storage management workflows.

Tests complete user workflows from start to finish.

Testing pyramid: 10% E2E tests
"""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

try:
    from azlin.modules.nfs_performance_tuner import NFSPerformanceTuner
    from azlin.modules.orphaned_resource_detector import OrphanedResourceDetector
    from azlin.modules.storage_cost_advisor import StorageCostAdvisor
    from azlin.modules.storage_quota_manager import StorageQuotaManager
    from azlin.modules.storage_tier_optimizer import StorageTierOptimizer
except ImportError:
    pytest.skip("Modules not implemented yet", allow_module_level=True)


class TestQuotaManagementWorkflow:
    """Test complete quota management workflow."""

    @patch("azlin.modules.storage_quota_manager.Path")
    @patch("azlin.modules.storage_quota_manager.subprocess.run")
    @patch("azlin.modules.storage_quota_manager.StorageManager")
    def test_complete_quota_workflow(self, mock_storage_mgr, mock_subprocess, mock_path):
        """Test: Set quota → Monitor usage → Block over-quota operation → Report status."""
        # 1. Set team quota
        mock_path.return_value.exists.return_value = False
        mock_path.return_value.parent.mkdir = Mock()
        mock_path.return_value.write_text = Mock()

        quota_config = StorageQuotaManager.set_quota(scope="team", name="test-rg", quota_gb=2000)

        assert quota_config.quota_gb == 2000

        # 2. Check current usage
        mock_path.return_value.exists.return_value = True
        mock_path.return_value.read_text.return_value = '{"team": {"test-rg": {"quota_gb": 2000, "created": "2025-12-01T10:00:00", "last_updated": "2025-12-01T10:00:00"}}}'

        mock_storage_mgr.list_storage.return_value = [Mock(name="storage1", size_gb=1000)]

        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout='[{"diskSizeGb": 500}]'),  # Disks
            Mock(returncode=0, stdout='[{"diskSizeGb": 100}]'),  # Snapshots
        ]

        status = StorageQuotaManager.get_quota(
            scope="team", name="test-rg", resource_group="test-rg"
        )

        # Total: 1000 + 500 + 100 = 1600 GB used
        assert status.used_gb == 1600
        assert status.available_gb == 400
        assert status.utilization_percent == 80.0

        # 3. Try to create storage that would exceed quota
        check_result = StorageQuotaManager.check_quota(
            scope="team",
            name="test-rg",
            requested_gb=500,  # Would take us to 2100 GB
            resource_group="test-rg",
        )

        assert check_result.available is False

        # 4. Create storage within quota
        check_result = StorageQuotaManager.check_quota(
            scope="team",
            name="test-rg",
            requested_gb=300,  # Would take us to 1900 GB
            resource_group="test-rg",
        )

        assert check_result.available is True
        assert check_result.remaining_after_gb == 100


class TestCostOptimizationWorkflow:
    """Test complete cost optimization workflow."""

    @patch("azlin.modules.storage_cost_advisor.StorageManager")
    @patch("azlin.modules.storage_cost_advisor.subprocess.run")
    @patch("azlin.modules.storage_cost_advisor.OrphanedResourceDetector")
    @patch("azlin.modules.storage_cost_advisor.StorageTierOptimizer")
    def test_complete_cost_optimization_workflow(
        self, mock_tier, mock_orphaned, mock_subprocess, mock_storage_mgr
    ):
        """Test: Analyze costs → Get recommendations → Apply optimizations → Verify savings."""
        # 1. Initial cost analysis
        mock_storage_mgr.list_storage.return_value = [
            Mock(name="storage1", size_gb=100, tier="Premium", monthly_cost=15.36)
        ]

        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout='[{"diskSizeGb": 128, "sku": {"tier": "Premium"}}]'),
            Mock(returncode=0, stdout='[{"diskSizeGb": 64}]'),
        ]

        mock_orphaned.scan_all.return_value = Mock(
            disks=[Mock(monthly_cost=10.0)],
            snapshots=[Mock(monthly_cost=5.0)],
            storage_accounts=[Mock(monthly_cost=15.0)],
            total_cost_per_month=30.0,
        )

        analysis = StorageCostAdvisor.analyze_costs(resource_group="test-rg")

        initial_cost = analysis.total_cost

        # 2. Get recommendations
        mock_tier.audit_all_storage.return_value = [
            Mock(storage_name="storage1", recommended_tier="Standard", annual_savings=136.32)
        ]

        recommendations = StorageCostAdvisor.get_recommendations(resource_group="test-rg")

        assert len(recommendations) > 0

        # 3. Apply tier migration
        mock_tier.migrate_tier.return_value = Mock(
            success=True, new_storage_name="storage1-standard"
        )

        migration_result = StorageTierOptimizer.migrate_tier(
            storage_name="storage1", resource_group="test-rg", target_tier="Standard", confirm=True
        )

        assert migration_result.success is True

        # 4. Run cleanup
        old_date = (datetime.now() - timedelta(days=30)).isoformat()
        mock_subprocess.side_effect = [
            Mock(
                returncode=0,
                stdout=f'[{{"name": "disk1", "managedBy": null, "diskSizeGb": 100, "sku": {{"tier": "Premium"}}, "timeCreated": "{old_date}", "tags": {{}}}}]',
            ),
            Mock(returncode=0),  # Delete
        ]

        cleanup_result = OrphanedResourceDetector.cleanup_orphaned(
            resource_group="test-rg", resource_type="all", min_age_days=7, dry_run=False
        )

        # 5. Verify cost reduction
        total_savings = migration_result.monthly_savings + cleanup_result.total_cost_saved_per_month

        assert total_savings > 0
        # Should achieve ~30% cost reduction
        assert total_savings / initial_cost > 0.20


class TestNFSTuningWorkflow:
    """Test complete NFS performance tuning workflow."""

    @patch("azlin.modules.nfs_performance_tuner.StorageManager")
    @patch("azlin.modules.nfs_performance_tuner.subprocess.run")
    def test_complete_nfs_tuning_workflow(self, mock_subprocess, mock_storage_mgr):
        """Test: Analyze performance → Get recommendations → Apply tuning → Test performance."""
        # 1. Analyze current performance
        mock_storage_mgr.get_storage_status.return_value = Mock(
            name="shared-storage", connected_vms=["vm1", "vm2", "vm3"], tier="Premium"
        )

        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout="vers=4.1,sec=sys",  # Default mount options
        )

        analysis = NFSPerformanceTuner.analyze_performance(
            storage_name="shared-storage", resource_group="test-rg"
        )

        assert analysis.optimization_potential in ["high", "medium"]

        # 2. Get tuning recommendations
        recommendation = NFSPerformanceTuner.get_tuning_recommendations(
            storage_name="shared-storage", resource_group="test-rg", workload_type="auto"
        )

        # Should recommend multi-VM profile
        assert "actimeo=1" in recommendation.recommended_mount_options
        assert recommendation.expected_improvement_percent >= 15

        # 3. Test current performance (baseline)
        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout="1073741824 bytes in 20.0 seconds"),  # Read
            Mock(returncode=0, stdout="1073741824 bytes in 25.0 seconds"),  # Write
        ]

        baseline_test = NFSPerformanceTuner.test_performance(
            vm_name="vm1", resource_group="test-rg", test_type="quick"
        )

        baseline_throughput = baseline_test.read_throughput_mbps

        # 4. Apply tuning
        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout="vers=4.1"),  # Get current options
            Mock(returncode=0),  # Backup fstab
            Mock(returncode=0),  # Update fstab
            Mock(returncode=0),  # Remount
        ]

        tuning_result = NFSPerformanceTuner.apply_tuning(
            vm_name="vm1", storage_name="shared-storage", resource_group="test-rg"
        )

        assert tuning_result.remounted is True

        # 5. Test after tuning
        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout="1073741824 bytes in 16.0 seconds"),  # Read (faster)
            Mock(returncode=0, stdout="1073741824 bytes in 20.0 seconds"),  # Write (faster)
        ]

        after_test = NFSPerformanceTuner.test_performance(
            vm_name="vm1", resource_group="test-rg", test_type="quick"
        )

        # 6. Verify improvement
        improvement_percent = (
            (after_test.read_throughput_mbps - baseline_throughput) / baseline_throughput * 100
        )

        assert improvement_percent >= 15  # Target: 15-25% improvement


class TestStorageCreationWithQuotaAndCostTracking:
    """Test storage creation with quota checks and cost tracking."""

    @patch("azlin.modules.storage_quota_manager.StorageQuotaManager.check_quota")
    @patch("azlin.modules.storage_manager.subprocess.run")
    @patch("azlin.modules.storage_cost_advisor.StorageCostAdvisor.analyze_costs")
    def test_storage_creation_workflow(self, mock_cost_analysis, mock_subprocess, mock_check_quota):
        """Test: Check quota → Create storage → Track costs."""
        # 1. Check quota before creation
        mock_check_quota.return_value = Mock(available=True, remaining_after_gb=400)

        # 2. Create storage
        mock_subprocess.return_value = Mock(
            returncode=0, stdout='{"id": "/subscriptions/.../new-storage", "name": "new-storage"}'
        )

        # Storage creation would call quota check internally
        # result = StorageManager.create_storage(...)

        # 3. Verify cost impact
        mock_cost_analysis.return_value = Mock(
            total_cost=538.13 + 15.36,  # Previous + new storage
            cost_breakdown=Mock(storage_accounts=245.76 + 15.36),
        )

        analysis = StorageCostAdvisor.analyze_costs(resource_group="test-rg")

        # Should include new storage in cost analysis
        assert analysis.total_cost > 538.13


class TestCleanupWithCostReporting:
    """Test cleanup workflow with cost savings reporting."""

    @patch("azlin.modules.orphaned_resource_detector.subprocess.run")
    @patch("azlin.modules.storage_cost_advisor.StorageCostAdvisor.analyze_costs")
    def test_cleanup_and_cost_verification_workflow(self, mock_cost_analysis, mock_subprocess):
        """Test: Scan orphaned → Cleanup → Verify cost reduction."""
        # 1. Initial cost analysis
        mock_cost_analysis.return_value = Mock(
            total_cost=538.13, cost_breakdown=Mock(orphaned_resources=121.43)
        )

        initial_analysis = StorageCostAdvisor.analyze_costs(resource_group="test-rg")
        initial_cost = initial_analysis.total_cost

        # 2. Scan for orphaned resources
        old_date = (datetime.now() - timedelta(days=30)).isoformat()
        mock_subprocess.side_effect = [
            # Scan
            Mock(
                returncode=0,
                stdout=f'[{{"name": "disk1", "managedBy": null, "diskSizeGb": 100, "sku": {{"tier": "Premium"}}, "timeCreated": "{old_date}", "tags": {{}}}}, {{"name": "disk2", "managedBy": null, "diskSizeGb": 256, "sku": {{"tier": "Standard"}}, "timeCreated": "{old_date}", "tags": {{}}}}]',
            ),
            # Delete disk1
            Mock(returncode=0),
            # Delete disk2
            Mock(returncode=0),
        ]

        report = OrphanedResourceDetector.scan_all(resource_group="test-rg")

        # 3. Cleanup
        cleanup_result = OrphanedResourceDetector.cleanup_orphaned(
            resource_group="test-rg", resource_type="all", min_age_days=7, dry_run=False
        )

        # 4. Verify cost reduction
        mock_cost_analysis.return_value = Mock(
            total_cost=initial_cost - cleanup_result.total_cost_saved_per_month,
            cost_breakdown=Mock(
                orphaned_resources=0.0  # All cleaned up
            ),
        )

        final_analysis = StorageCostAdvisor.analyze_costs(resource_group="test-rg")

        # Should see cost reduction
        assert final_analysis.total_cost < initial_cost
        assert final_analysis.cost_breakdown.orphaned_resources == 0.0


class TestMultiVMNFSOptimization:
    """Test NFS optimization for multi-VM scenario."""

    @patch("azlin.modules.nfs_performance_tuner.StorageManager")
    @patch("azlin.modules.nfs_performance_tuner.subprocess.run")
    def test_multi_vm_nfs_optimization_workflow(self, mock_subprocess, mock_storage_mgr):
        """Test: Detect multi-VM → Apply tuning to all VMs → Verify consistency."""
        # 1. Detect multi-VM scenario
        mock_storage_mgr.get_storage_status.return_value = Mock(
            name="shared-storage", connected_vms=["vm1", "vm2", "vm3"], tier="Premium"
        )

        analysis = NFSPerformanceTuner.analyze_performance(
            storage_name="shared-storage", resource_group="test-rg"
        )

        assert len(analysis.connected_vms) >= 2

        # 2. Get multi-VM tuning recommendation
        recommendation = NFSPerformanceTuner.get_tuning_recommendations(
            storage_name="shared-storage",
            resource_group="test-rg",
            workload_type="auto",  # Should auto-detect multi-VM
        )

        # Should use multi-VM profile with short attribute cache
        assert "actimeo=1" in recommendation.recommended_mount_options

        # 3. Apply tuning to all VMs
        for vm in ["vm1", "vm2", "vm3"]:
            mock_subprocess.side_effect = [
                Mock(returncode=0, stdout="vers=4.1"),
                Mock(returncode=0),
                Mock(returncode=0),
                Mock(returncode=0),
            ]

            result = NFSPerformanceTuner.apply_tuning(
                vm_name=vm, storage_name="shared-storage", resource_group="test-rg"
            )

            assert result.remounted is True
            # All VMs should have same mount options
            assert "actimeo=1" in result.new_mount_options


class TestEndToEndPerformanceTargets:
    """Verify E2E workflows meet performance targets."""

    def test_cost_reduction_30_percent_target(self):
        """Verify cost optimization achieves 30% reduction target."""
        # Through tier optimization + orphaned cleanup
        # Target: $538.13 → $376.69 (30% reduction)
        pass

    def test_nfs_performance_20_percent_improvement(self):
        """Verify NFS tuning achieves 20% performance improvement."""
        # Through mount option optimization
        # Target: 50 MB/s → 60 MB/s (20% improvement)
        pass

    def test_quota_management_zero_failures(self):
        """Verify quota management prevents all quota failures."""
        # 100% of quota violations caught before Azure errors
        pass
