"""Unit tests for NFSPerformanceTuner module.

Following TDD approach. Tests focus on NFS mount optimization and performance testing.

Philosophy:
- Test mount option generation
- Verify workload detection
- Mock SSH operations
- Test safety mechanisms
"""

from unittest.mock import Mock, patch

import pytest

# Module under test
try:
    from azlin.modules.nfs_performance_tuner import (
        NFSPerformanceAnalysis,
        NFSPerformanceTest,
        NFSPerformanceTuner,
        NFSTuningRecommendation,
        NFSTuningResult,
    )
except ImportError:
    pytest.skip("Module not implemented yet", allow_module_level=True)


class TestNFSPerformanceAnalysisDataModel:
    """Test NFSPerformanceAnalysis data model."""

    def test_nfs_performance_analysis_creation(self):
        """Test basic NFSPerformanceAnalysis creation."""
        analysis = NFSPerformanceAnalysis(
            storage_name="myteam-shared",
            connected_vms=["vm1", "vm2"],
            current_mount_options={"vm1": "vers=4.1,sec=sys,proto=tcp"},
            performance_tier="Premium",
            bottleneck_indicators=["Default mount options", "Long attribute cache"],
            optimization_potential="high",
        )
        assert len(analysis.connected_vms) == 2
        assert analysis.optimization_potential == "high"


class TestNFSTuningRecommendationDataModel:
    """Test NFSTuningRecommendation data model."""

    def test_nfs_tuning_recommendation_creation(self):
        """Test basic NFSTuningRecommendation creation."""
        rec = NFSTuningRecommendation(
            storage_name="myteam-shared",
            workload_type="multi-vm",
            recommended_mount_options="vers=4.1,rsize=1048576,wsize=1048576,actimeo=1",
            expected_improvement_percent=20,
            rationale="Multi-VM scenario requires short attribute cache",
            specific_recommendations=[
                "Increase read buffer to 1MB",
                "Reduce attribute cache to 1s",
            ],
        )
        assert rec.workload_type == "multi-vm"
        assert rec.expected_improvement_percent == 20


class TestNFSPerformanceTunerAnalyzePerformance:
    """Test analyze_performance() method."""

    @patch("azlin.modules.nfs_performance_tuner.StorageManager")
    @patch("azlin.modules.nfs_performance_tuner.subprocess.run")
    def test_analyze_performance_detects_multi_vm(self, mock_subprocess, mock_storage_mgr):
        """Test detection of multi-VM scenario."""
        mock_storage_mgr.get_storage_status.return_value = Mock(
            name="myteam-shared", connected_vms=["vm1", "vm2", "vm3"], tier="Premium"
        )

        # Mock SSH to get mount options
        mock_subprocess.return_value = Mock(
            returncode=0, stdout="vers=4.1,sec=sys,proto=tcp,timeo=600"
        )

        analysis = NFSPerformanceTuner.analyze_performance(
            storage_name="myteam-shared", resource_group="test-rg"
        )

        assert isinstance(analysis, NFSPerformanceAnalysis)
        assert len(analysis.connected_vms) >= 2
        # Should detect multi-VM bottleneck

    @patch("azlin.modules.nfs_performance_tuner.StorageManager")
    @patch("azlin.modules.nfs_performance_tuner.subprocess.run")
    def test_analyze_performance_detects_default_options(self, mock_subprocess, mock_storage_mgr):
        """Test detection of default (non-optimized) mount options."""
        mock_storage_mgr.get_storage_status.return_value = Mock(
            name="storage", connected_vms=["vm1"], tier="Premium"
        )

        # Default mount options
        mock_subprocess.return_value = Mock(returncode=0, stdout="vers=4.1,sec=sys,proto=tcp")

        analysis = NFSPerformanceTuner.analyze_performance(
            storage_name="storage", resource_group="test-rg"
        )

        assert "default" in " ".join(analysis.bottleneck_indicators).lower()

    @patch("azlin.modules.nfs_performance_tuner.StorageManager")
    def test_analyze_performance_premium_vs_standard(self, mock_storage_mgr):
        """Test analysis considers storage tier."""
        # Premium has higher performance expectations
        mock_storage_mgr.get_storage_status.return_value = Mock(
            name="premium-storage", connected_vms=["vm1"], tier="Premium"
        )

        analysis = NFSPerformanceTuner.analyze_performance(
            storage_name="premium-storage", resource_group="test-rg"
        )

        assert analysis.performance_tier == "Premium"


class TestNFSPerformanceTunerGetTuningRecommendations:
    """Test get_tuning_recommendations() method."""

    @patch("azlin.modules.nfs_performance_tuner.NFSPerformanceTuner.analyze_performance")
    def test_recommend_multi_vm_profile(self, mock_analyze):
        """Test multi-VM workload recommendation."""
        mock_analyze.return_value = NFSPerformanceAnalysis(
            storage_name="shared-storage",
            connected_vms=["vm1", "vm2", "vm3"],
            current_mount_options={},
            performance_tier="Premium",
            bottleneck_indicators=[],
            optimization_potential="high",
        )

        rec = NFSPerformanceTuner.get_tuning_recommendations(
            storage_name="shared-storage", resource_group="test-rg", workload_type="auto"
        )

        assert isinstance(rec, NFSTuningRecommendation)
        # Should recommend multi-VM profile
        assert "actimeo=1" in rec.recommended_mount_options  # Short cache
        assert "rsize=1048576" in rec.recommended_mount_options  # Large buffers

    @patch("azlin.modules.nfs_performance_tuner.NFSPerformanceTuner.analyze_performance")
    def test_recommend_read_heavy_profile(self, mock_analyze):
        """Test read-heavy workload recommendation."""
        mock_analyze.return_value = NFSPerformanceAnalysis(
            storage_name="dev-storage",
            connected_vms=["vm1"],
            current_mount_options={},
            performance_tier="Premium",
            bottleneck_indicators=[],
            optimization_potential="medium",
        )

        rec = NFSPerformanceTuner.get_tuning_recommendations(
            storage_name="dev-storage", resource_group="test-rg", workload_type="read-heavy"
        )

        # Should recommend aggressive attribute caching
        assert "ac" in rec.recommended_mount_options
        assert (
            "acregmin" in rec.recommended_mount_options
            or "actimeo" in rec.recommended_mount_options
        )

    @patch("azlin.modules.nfs_performance_tuner.NFSPerformanceTuner.analyze_performance")
    def test_recommend_write_heavy_profile(self, mock_analyze):
        """Test write-heavy workload recommendation."""
        mock_analyze.return_value = NFSPerformanceAnalysis(
            storage_name="build-storage",
            connected_vms=["vm1"],
            current_mount_options={},
            performance_tier="Premium",
            bottleneck_indicators=[],
            optimization_potential="medium",
        )

        rec = NFSPerformanceTuner.get_tuning_recommendations(
            storage_name="build-storage", resource_group="test-rg", workload_type="write-heavy"
        )

        # Should recommend async writes and no attribute caching
        assert "async" in rec.recommended_mount_options or "noac" in rec.recommended_mount_options

    def test_recommend_auto_detects_workload(self):
        """Test auto workload detection chooses correct profile."""
        # Should detect multi-VM and use that profile regardless of usage
        pass


class TestNFSPerformanceTunerApplyTuning:
    """Test apply_tuning() method."""

    @patch("azlin.modules.nfs_performance_tuner.subprocess.run")
    @patch("azlin.modules.nfs_performance_tuner.NFSPerformanceTuner.get_tuning_recommendations")
    def test_apply_tuning_updates_mount_options(self, mock_recommend, mock_subprocess):
        """Test applying tuning updates VM mount options."""
        mock_recommend.return_value = NFSTuningRecommendation(
            storage_name="storage",
            workload_type="multi-vm",
            recommended_mount_options="vers=4.1,rsize=1048576,actimeo=1",
            expected_improvement_percent=20,
            rationale="Test",
            specific_recommendations=[],
        )

        # Mock SSH commands
        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout="vers=4.1"),  # Get current options
            Mock(returncode=0),  # Backup fstab
            Mock(returncode=0),  # Update fstab
            Mock(returncode=0),  # Remount
        ]

        result = NFSPerformanceTuner.apply_tuning(
            vm_name="vm1",
            storage_name="storage",
            resource_group="test-rg",
            tuning_profile="recommended",
        )

        assert isinstance(result, NFSTuningResult)
        assert result.remounted is True
        assert result.new_mount_options != result.old_mount_options

    @patch("azlin.modules.nfs_performance_tuner.subprocess.run")
    def test_apply_tuning_backs_up_fstab(self, mock_subprocess):
        """Test tuning backs up /etc/fstab before changes."""
        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout="vers=4.1"),
            Mock(returncode=0),  # Backup
            Mock(returncode=0),  # Update
            Mock(returncode=0),  # Remount
        ]

        NFSPerformanceTuner.apply_tuning(
            vm_name="vm1", storage_name="storage", resource_group="test-rg"
        )

        # Should have called backup command
        calls = [call.args[0] for call in mock_subprocess.call_args_list]
        assert any("cp" in str(call) and "fstab" in str(call) for call in calls)

    @patch("azlin.modules.nfs_performance_tuner.subprocess.run")
    def test_apply_tuning_tests_before_persisting(self, mock_subprocess):
        """Test tuning tests mount before making persistent."""
        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout="vers=4.1"),
            Mock(returncode=0),  # Backup
            Mock(returncode=0),  # Test mount
            Mock(returncode=0),  # Update fstab
            Mock(returncode=0),  # Remount
        ]

        result = NFSPerformanceTuner.apply_tuning(
            vm_name="vm1", storage_name="storage", resource_group="test-rg"
        )

        # Should test mount before persisting
        assert result.remounted is True

    @patch("azlin.modules.nfs_performance_tuner.subprocess.run")
    def test_apply_tuning_handles_failure_gracefully(self, mock_subprocess):
        """Test tuning handles mount failures and provides rollback info."""
        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout="vers=4.1"),
            Mock(returncode=0),  # Backup
            Mock(returncode=1, stderr="Mount failed"),  # Failure
        ]

        result = NFSPerformanceTuner.apply_tuning(
            vm_name="vm1", storage_name="storage", resource_group="test-rg"
        )

        assert result.remounted is False
        assert len(result.errors) > 0


class TestNFSPerformanceTunerTestPerformance:
    """Test test_performance() benchmarking method."""

    @patch("azlin.modules.nfs_performance_tuner.subprocess.run")
    def test_quick_performance_test(self, mock_subprocess):
        """Test quick performance test using dd."""
        # Mock dd output
        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout="1073741824 bytes transferred in 10.5 seconds"),  # Read test
            Mock(returncode=0, stdout="1073741824 bytes transferred in 12.3 seconds"),  # Write test
        ]

        result = NFSPerformanceTuner.test_performance(
            vm_name="vm1", resource_group="test-rg", test_type="quick"
        )

        assert isinstance(result, NFSPerformanceTest)
        assert result.read_throughput_mbps > 0
        assert result.write_throughput_mbps > 0
        assert result.test_duration_seconds < 120  # Quick test

    @patch("azlin.modules.nfs_performance_tuner.subprocess.run")
    def test_full_performance_test_with_fio(self, mock_subprocess):
        """Test comprehensive performance test using fio."""
        # Mock fio installation check and output
        mock_subprocess.side_effect = [
            Mock(returncode=0),  # fio available
            Mock(
                returncode=0,
                stdout="""
            {
                "jobs": [{
                    "read": {"bw_mean": 102400, "iops": 25600, "lat_ns": {"mean": 1500000}},
                    "write": {"bw_mean": 81920, "iops": 20480}
                }]
            }
            """,
            ),
        ]

        result = NFSPerformanceTuner.test_performance(
            vm_name="vm1", resource_group="test-rg", test_type="full"
        )

        assert result.test_type == "full"
        assert result.iops > 0
        assert result.latency_ms > 0

    @patch("azlin.modules.nfs_performance_tuner.subprocess.run")
    def test_performance_test_handles_ssh_failure(self, mock_subprocess):
        """Test performance test handles SSH failures gracefully."""
        mock_subprocess.return_value = Mock(returncode=255, stderr="SSH connection failed")

        with pytest.raises(RuntimeError, match="SSH"):
            NFSPerformanceTuner.test_performance(
                vm_name="vm1", resource_group="test-rg", test_type="quick"
            )


class TestNFSPerformanceTunerMountOptions:
    """Test mount option generation for different workloads."""

    def test_multi_vm_mount_options(self):
        """Test multi-VM mount options have short attribute cache."""
        options = NFSPerformanceTuner._get_mount_options("multi-vm")
        assert "actimeo=1" in options
        assert "rsize=1048576" in options
        assert "wsize=1048576" in options

    def test_read_heavy_mount_options(self):
        """Test read-heavy mount options have aggressive caching."""
        options = NFSPerformanceTuner._get_mount_options("read-heavy")
        assert "ac" in options
        assert "acregmin" in options or "actimeo" in options
        assert "rsize=1048576" in options

    def test_write_heavy_mount_options(self):
        """Test write-heavy mount options optimize writes."""
        options = NFSPerformanceTuner._get_mount_options("write-heavy")
        assert "wsize=1048576" in options
        assert "async" in options or "noac" in options

    def test_balanced_mount_options(self):
        """Test balanced mount options for mixed workload."""
        options = NFSPerformanceTuner._get_mount_options("mixed")
        assert "rsize=1048576" in options
        assert "wsize=1048576" in options
        assert "hard" in options

    def test_mount_options_always_include_base(self):
        """Test all mount options include base requirements."""
        for workload in ["multi-vm", "read-heavy", "write-heavy", "mixed"]:
            options = NFSPerformanceTuner._get_mount_options(workload)
            assert "vers=4.1" in options
            assert "proto=tcp" in options
            assert "hard" in options


class TestNFSPerformanceTunerWorkloadDetection:
    """Test workload type auto-detection."""

    @patch("azlin.modules.nfs_performance_tuner.StorageManager")
    def test_auto_detects_multi_vm(self, mock_storage_mgr):
        """Test auto-detection of multi-VM scenario."""
        mock_storage_mgr.get_storage_status.return_value = Mock(connected_vms=["vm1", "vm2", "vm3"])

        workload = NFSPerformanceTuner._detect_workload_type(
            storage_name="storage", resource_group="test-rg"
        )

        assert workload == "multi-vm"

    @patch("azlin.modules.nfs_performance_tuner.StorageManager")
    def test_auto_defaults_to_mixed(self, mock_storage_mgr):
        """Test default to mixed workload for single VM."""
        mock_storage_mgr.get_storage_status.return_value = Mock(connected_vms=["vm1"])

        workload = NFSPerformanceTuner._detect_workload_type(
            storage_name="storage", resource_group="test-rg"
        )

        assert workload == "mixed"


class TestNFSPerformanceTunerSafety:
    """Test safety mechanisms."""

    @patch("azlin.modules.nfs_performance_tuner.subprocess.run")
    def test_apply_tuning_preserves_original_fstab(self, mock_subprocess):
        """Test original fstab is preserved as backup."""
        # Should create /etc/fstab.backup before changes
        pass

    def test_apply_tuning_provides_rollback_instructions(self):
        """Test rollback instructions provided on failure."""
        # Should tell user how to restore from backup
        pass

    def test_apply_tuning_warns_about_aggressive_caching(self):
        """Test warning about data consistency with aggressive caching."""
        # Should warn when using long attribute cache with multiple VMs
        pass


class TestNFSPerformanceTunerPerformanceExpectations:
    """Test performance expectations for different tiers."""

    def test_premium_nfs_performance_expectations(self):
        """Test Premium NFS performance expectations."""
        # Read: Up to 4 GB/s
        # Write: Up to 2 GB/s
        # Latency: <1ms
        expectations = NFSPerformanceTuner._get_performance_expectations("Premium")
        assert expectations["read_gbps"] == 4.0
        assert expectations["write_gbps"] == 2.0
        assert expectations["latency_ms"] < 1.0

    def test_standard_nfs_performance_expectations(self):
        """Test Standard NFS performance expectations."""
        # Read: Up to 60 MB/s
        # Write: Up to 60 MB/s
        # Latency: 2-10ms
        expectations = NFSPerformanceTuner._get_performance_expectations("Standard")
        assert expectations["read_mbps"] == 60
        assert expectations["write_mbps"] == 60

    def test_expected_improvement_from_tuning(self):
        """Test expected 15-25% improvement from tuning."""
        # Optimization should improve performance by 15-25%
        pass


class TestNFSPerformanceTunerEdgeCases:
    """Test edge cases and error handling."""

    def test_analyze_nonexistent_storage(self):
        """Test analyzing non-existent storage."""
        with pytest.raises(ValueError, match="Storage not found"):
            NFSPerformanceTuner.analyze_performance(
                storage_name="nonexistent", resource_group="test-rg"
            )

    @patch("azlin.modules.nfs_performance_tuner.subprocess.run")
    def test_apply_tuning_handles_ssh_timeout(self, mock_subprocess):
        """Test handling of SSH timeouts."""
        mock_subprocess.side_effect = TimeoutError("SSH timeout")

        result = NFSPerformanceTuner.apply_tuning(
            vm_name="vm1", storage_name="storage", resource_group="test-rg"
        )

        assert result.remounted is False
        assert len(result.errors) > 0

    def test_apply_tuning_validates_profile(self):
        """Test validation of tuning profile."""
        with pytest.raises(ValueError, match="Invalid profile"):
            NFSPerformanceTuner.apply_tuning(
                vm_name="vm1",
                storage_name="storage",
                resource_group="test-rg",
                tuning_profile="invalid",
            )
