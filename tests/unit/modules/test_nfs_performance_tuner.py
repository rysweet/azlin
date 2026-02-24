"""Unit tests for NFSPerformanceTuner module.

Tests cover the implemented API: data models, analyze_performance(),
get_tuning_recommendations(), and PROFILES mount option constants.

Philosophy:
- Test mount option generation
- Verify workload detection via recommendations
- Mock StorageManager dependency
- Test data model creation
"""

from unittest.mock import Mock, patch

import pytest

from azlin.modules.nfs_performance_tuner import (
    PROFILES,
    NFSPerformanceAnalysis,
    NFSPerformanceTuner,
    NFSTuningRecommendation,
)


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
    def test_analyze_performance_detects_multi_vm(self, mock_storage_mgr):
        """Test detection of multi-VM scenario."""
        mock_storage_mgr.get_storage_status.return_value = Mock(
            name="myteam-shared", connected_vms=["vm1", "vm2", "vm3"], tier="Premium"
        )

        analysis = NFSPerformanceTuner.analyze_performance(
            storage_name="myteam-shared", resource_group="test-rg"
        )

        assert isinstance(analysis, NFSPerformanceAnalysis)
        assert len(analysis.connected_vms) == 3
        # Should detect multi-VM bottleneck
        assert any("Multi-VM" in b for b in analysis.bottleneck_indicators)

    @patch("azlin.modules.nfs_performance_tuner.StorageManager")
    def test_analyze_performance_detects_default_options(self, mock_storage_mgr):
        """Test detection of default (non-optimized) mount options.

        The implementation uses _get_mount_options which returns the baseline profile
        (no rsize/wsize), so default options bottleneck should be detected.
        """
        mock_storage_mgr.get_storage_status.return_value = Mock(
            name="storage", connected_vms=["vm1"], tier="Premium"
        )

        analysis = NFSPerformanceTuner.analyze_performance(
            storage_name="storage", resource_group="test-rg"
        )

        # Baseline profile lacks rsize/wsize, so "Default mount options" should appear
        assert any("default" in b.lower() for b in analysis.bottleneck_indicators)

    @patch("azlin.modules.nfs_performance_tuner.StorageManager")
    def test_analyze_performance_premium_vs_standard(self, mock_storage_mgr):
        """Test analysis considers storage tier."""
        mock_storage_mgr.get_storage_status.return_value = Mock(
            name="premium-storage", connected_vms=["vm1"], tier="Premium"
        )

        analysis = NFSPerformanceTuner.analyze_performance(
            storage_name="premium-storage", resource_group="test-rg"
        )

        assert analysis.performance_tier == "Premium"

    @patch("azlin.modules.nfs_performance_tuner.StorageManager")
    def test_analyze_performance_optimization_potential_high(self, mock_storage_mgr):
        """Test high optimization potential with multiple bottlenecks."""
        mock_storage_mgr.get_storage_status.return_value = Mock(
            name="storage", connected_vms=["vm1", "vm2"], tier="Premium"
        )

        analysis = NFSPerformanceTuner.analyze_performance(
            storage_name="storage", resource_group="test-rg"
        )

        # Multi-VM + default options = high potential
        assert analysis.optimization_potential == "high"

    @patch("azlin.modules.nfs_performance_tuner.StorageManager")
    def test_analyze_requires_storage_manager(self, mock_storage_mgr):
        """Test that analyze_performance raises if StorageManager unavailable."""
        # Temporarily set StorageManager to None
        with patch("azlin.modules.nfs_performance_tuner.StorageManager", None):
            with pytest.raises(RuntimeError, match="StorageManager not available"):
                NFSPerformanceTuner.analyze_performance(
                    storage_name="storage", resource_group="test-rg"
                )


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

    @patch("azlin.modules.nfs_performance_tuner.NFSPerformanceTuner.analyze_performance")
    def test_recommend_auto_detects_multi_vm(self, mock_analyze):
        """Test auto workload detection chooses multi-vm for multiple VMs."""
        mock_analyze.return_value = NFSPerformanceAnalysis(
            storage_name="storage",
            connected_vms=["vm1", "vm2"],
            current_mount_options={},
            performance_tier="Premium",
            bottleneck_indicators=[],
            optimization_potential="medium",
        )

        rec = NFSPerformanceTuner.get_tuning_recommendations(
            storage_name="storage", resource_group="test-rg", workload_type="auto"
        )

        assert rec.workload_type == "multi-vm"

    @patch("azlin.modules.nfs_performance_tuner.NFSPerformanceTuner.analyze_performance")
    def test_recommend_auto_defaults_to_mixed(self, mock_analyze):
        """Test auto workload detection defaults to mixed for single VM."""
        mock_analyze.return_value = NFSPerformanceAnalysis(
            storage_name="storage",
            connected_vms=["vm1"],
            current_mount_options={},
            performance_tier="Premium",
            bottleneck_indicators=[],
            optimization_potential="low",
        )

        rec = NFSPerformanceTuner.get_tuning_recommendations(
            storage_name="storage", resource_group="test-rg", workload_type="auto"
        )

        assert rec.workload_type == "mixed"

    @patch("azlin.modules.nfs_performance_tuner.NFSPerformanceTuner.analyze_performance")
    def test_recommend_includes_specific_recommendations(self, mock_analyze):
        """Test that recommendations include specific actionable items."""
        mock_analyze.return_value = NFSPerformanceAnalysis(
            storage_name="storage",
            connected_vms=["vm1", "vm2"],
            current_mount_options={},
            performance_tier="Premium",
            bottleneck_indicators=[],
            optimization_potential="high",
        )

        rec = NFSPerformanceTuner.get_tuning_recommendations(
            storage_name="storage", resource_group="test-rg", workload_type="auto"
        )

        assert len(rec.specific_recommendations) > 0
        assert rec.expected_improvement_percent > 0
        assert len(rec.rationale) > 0


class TestNFSPerformanceTunerMountOptions:
    """Test mount option profiles for different workloads."""

    def test_multi_vm_mount_options(self):
        """Test multi-VM mount options have short attribute cache."""
        options = PROFILES["multi-vm"]
        assert "actimeo=1" in options
        assert "rsize=1048576" in options
        assert "wsize=1048576" in options

    def test_read_heavy_mount_options(self):
        """Test read-heavy mount options have aggressive caching."""
        options = PROFILES["read-heavy"]
        assert "ac" in options
        assert "acregmin" in options or "actimeo" in options
        assert "rsize=1048576" in options

    def test_write_heavy_mount_options(self):
        """Test write-heavy mount options optimize writes."""
        options = PROFILES["write-heavy"]
        assert "wsize=1048576" in options
        assert "async" in options or "noac" in options

    def test_balanced_mount_options(self):
        """Test balanced mount options for mixed workload."""
        options = PROFILES["mixed"]
        assert "rsize=1048576" in options
        assert "wsize=1048576" in options
        assert "hard" in options

    def test_mount_options_always_include_base(self):
        """Test all mount options include base requirements."""
        for workload in ["multi-vm", "read-heavy", "write-heavy", "mixed"]:
            options = PROFILES[workload]
            assert "vers=4.1" in options
            assert "proto=tcp" in options
            assert "hard" in options

    def test_baseline_profile_exists(self):
        """Test baseline profile is available."""
        assert "baseline" in PROFILES
        options = PROFILES["baseline"]
        assert "vers=4.1" in options
        assert "sec=sys" in options
