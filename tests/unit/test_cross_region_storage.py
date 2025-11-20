"""Tests for cross-region storage handling in NFS resolution.

This test suite verifies the fix for Issue #316, ensuring that:
1. Priority 1 (--nfs-storage) strictly rejects cross-region storage
2. Priority 2 (config default) gracefully falls back on cross-region storage
3. Priority 3 (auto-detect) only considers same-region storage
4. All error messages and warnings are clear and actionable
"""

from unittest.mock import MagicMock, patch

import pytest

from azlin.cli import CLIOrchestrator
from azlin.modules.storage_manager import StorageInfo


@pytest.fixture
def storage_eastus():
    """Create mock storage in eastus."""
    return StorageInfo(
        name="storage-eastus",
        resource_group="test-rg",
        region="eastus",
        tier="Premium",
        size_gb=100,
        nfs_endpoint="storage-eastus.file.core.windows.net:/test-share",
        created=None,
    )


@pytest.fixture
def storage_westus():
    """Create mock storage in westus."""
    return StorageInfo(
        name="storage-westus",
        resource_group="test-rg",
        region="westus",
        tier="Premium",
        size_gb=100,
        nfs_endpoint="storage-westus.file.core.windows.net:/test-share",
        created=None,
    )


@pytest.fixture
def storage_westus2():
    """Create another mock storage in westus."""
    return StorageInfo(
        name="storage-westus2",
        resource_group="test-rg",
        region="westus",
        tier="Premium",
        size_gb=100,
        nfs_endpoint="storage-westus2.file.core.windows.net:/test-share",
        created=None,
    )


class TestPriority1ExplicitStorage:
    """Test Priority 1: Explicit --nfs-storage option behavior."""

    def test_explicit_same_region_succeeds(self, storage_eastus):
        """Priority 1: Explicit storage in same region should succeed."""
        orchestrator = CLIOrchestrator(nfs_storage="storage-eastus", region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_eastus]

            result = orchestrator._resolve_nfs_storage("test-rg", None)
            assert result is not None
            assert result.name == "storage-eastus"
            assert result.region == "eastus"

    def test_explicit_cross_region_raises_error(self, storage_westus):
        """Priority 1: Explicit storage in different region should raise ValueError."""
        orchestrator = CLIOrchestrator(nfs_storage="storage-westus", region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_westus]

            with pytest.raises(
                ValueError,
                match="Storage account 'storage-westus' is in region 'westus', but VM will be in region 'eastus'",
            ):
                orchestrator._resolve_nfs_storage("test-rg", None)

    def test_explicit_not_found_raises_error(self):
        """Priority 1: Explicit storage not found should raise ValueError."""
        orchestrator = CLIOrchestrator(nfs_storage="nonexistent", region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = []

            with pytest.raises(
                ValueError,
                match="Storage account 'nonexistent' not found in resource group 'test-rg'",
            ):
                orchestrator._resolve_nfs_storage("test-rg", None)

    def test_explicit_overrides_config(self, storage_eastus, storage_westus):
        """Priority 1: Explicit --nfs-storage should override config default."""
        orchestrator = CLIOrchestrator(nfs_storage="storage-eastus", region="eastus")

        mock_config = MagicMock()
        mock_config.default_nfs_storage = "storage-westus"

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_eastus, storage_westus]

            result = orchestrator._resolve_nfs_storage("test-rg", mock_config)
            assert result is not None
            assert result.name == "storage-eastus"


class TestPriority2ConfigDefault:
    """Test Priority 2: Config file default_nfs_storage behavior."""

    def test_config_same_region_succeeds(self, storage_eastus):
        """Priority 2: Config default in same region should succeed."""
        orchestrator = CLIOrchestrator(region="eastus")

        mock_config = MagicMock()
        mock_config.default_nfs_storage = "storage-eastus"

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_eastus]

            result = orchestrator._resolve_nfs_storage("test-rg", mock_config)
            assert result is not None
            assert result.name == "storage-eastus"
            assert result.region == "eastus"

    def test_config_cross_region_succeeds_with_info_log(
        self, storage_eastus, storage_westus, caplog
    ):
        """Priority 2: Config default in different region should succeed with info log."""
        orchestrator = CLIOrchestrator(region="eastus")

        mock_config = MagicMock()
        mock_config.default_nfs_storage = "storage-westus"

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_westus, storage_eastus]

            result = orchestrator._resolve_nfs_storage("test-rg", mock_config)
            # Should use storage-westus (cross-region now supported)
            assert result is not None
            assert result.name == "storage-westus"
            assert result.region == "westus"

            # Should log info about cross-region mount
            assert any(
                "Cross-region mount will be configured" in record.message
                for record in caplog.records
            )

    def test_config_not_found_falls_back_to_priority3(self, storage_eastus, caplog):
        """Priority 2: Config default not found should fall back to Priority 3."""
        orchestrator = CLIOrchestrator(region="eastus")

        mock_config = MagicMock()
        mock_config.default_nfs_storage = "nonexistent"

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_eastus]

            result = orchestrator._resolve_nfs_storage("test-rg", mock_config)
            # Should auto-detect storage-eastus instead
            assert result is not None
            assert result.name == "storage-eastus"

            # Should log warning about not found
            assert any(
                "Config default storage 'nonexistent' not found" in record.message
                for record in caplog.records
            )

    def test_config_storage_listing_fails_falls_back_to_priority3(self, storage_eastus, caplog):
        """Priority 2: If listing fails, should fall back to Priority 3."""
        orchestrator = CLIOrchestrator(region="eastus")

        mock_config = MagicMock()
        mock_config.default_nfs_storage = "storage-eastus"

        call_count = 0

        def list_storage_side_effect(rg):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call in _try_lookup_storage_by_name fails
                raise Exception("API error")
            # Second call in Priority 3 succeeds
            return [storage_eastus]

        with patch(
            "azlin.modules.storage_manager.StorageManager.list_storage",
            side_effect=list_storage_side_effect,
        ):
            result = orchestrator._resolve_nfs_storage("test-rg", mock_config)
            # Should auto-detect storage-eastus via Priority 3
            assert result is not None
            assert result.name == "storage-eastus"

            # Should log warning about listing failure
            assert any(
                "Could not list storage accounts" in record.message for record in caplog.records
            )


class TestPriority3AutoDetect:
    """Test Priority 3: Auto-detection behavior."""

    def test_auto_detect_single_same_region(self, storage_eastus):
        """Priority 3: Single storage in same region should be auto-detected."""
        orchestrator = CLIOrchestrator(region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_eastus]

            result = orchestrator._resolve_nfs_storage("test-rg", None)
            assert result is not None
            assert result.name == "storage-eastus"

    def test_auto_detect_ignores_cross_region(self, storage_westus):
        """Priority 3: Should ignore cross-region storage and return None."""
        orchestrator = CLIOrchestrator(region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_westus]

            result = orchestrator._resolve_nfs_storage("test-rg", None)
            assert result is None

    def test_auto_detect_prefers_same_region(self, storage_eastus, storage_westus):
        """Priority 3: Should prefer same-region storage over cross-region."""
        orchestrator = CLIOrchestrator(region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_westus, storage_eastus]

            result = orchestrator._resolve_nfs_storage("test-rg", None)
            assert result is not None
            assert result.name == "storage-eastus"
            assert result.region == "eastus"

    def test_auto_detect_multiple_same_region_raises_error(self, storage_westus, storage_westus2):
        """Priority 3: Multiple same-region storages without explicit choice should raise ValueError."""
        orchestrator = CLIOrchestrator(region="westus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_westus, storage_westus2]

            with pytest.raises(
                ValueError,
                match="Multiple NFS storage accounts found in region 'westus'",
            ):
                orchestrator._resolve_nfs_storage("test-rg", None)

    def test_auto_detect_no_storage_returns_none(self):
        """Priority 3: No storage accounts should return None."""
        orchestrator = CLIOrchestrator(region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = []

            result = orchestrator._resolve_nfs_storage("test-rg", None)
            assert result is None

    def test_auto_detect_listing_fails_returns_none(self):
        """Priority 3: If storage listing fails, should return None."""
        orchestrator = CLIOrchestrator(region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.side_effect = Exception("API error")

            result = orchestrator._resolve_nfs_storage("test-rg", None)
            assert result is None


class TestLookupStorageByNameMethod:
    """Test the _lookup_storage_by_name() method directly."""

    def test_lookup_same_region_with_require_same_region_true(self, storage_eastus):
        """Should succeed when storage is in same region and require_same_region=True."""
        orchestrator = CLIOrchestrator(region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_eastus]

            result = orchestrator._lookup_storage_by_name("test-rg", "storage-eastus")
            assert result.name == "storage-eastus"

    def test_lookup_cross_region_with_require_same_region_true(self, storage_westus):
        """Should raise ValueError when storage is cross-region and require_same_region=True."""
        orchestrator = CLIOrchestrator(region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_westus]

            with pytest.raises(
                ValueError,
                match="Cross-region NFS storage is not supported",
            ):
                orchestrator._lookup_storage_by_name("test-rg", "storage-westus")

    def test_lookup_cross_region_with_require_same_region_false(self, storage_westus):
        """Should succeed with info log when storage is cross-region and require_same_region=False."""
        orchestrator = CLIOrchestrator(region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_westus]

            result = orchestrator._lookup_storage_by_name(
                "test-rg", "storage-westus", require_same_region=False
            )
            assert result.name == "storage-westus"

    def test_lookup_not_found_raises_error(self):
        """Should raise ValueError when storage not found."""
        orchestrator = CLIOrchestrator(region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = []

            with pytest.raises(
                ValueError,
                match="Storage account 'nonexistent' not found",
            ):
                orchestrator._lookup_storage_by_name("test-rg", "nonexistent")


class TestTryLookupStorageByNameMethod:
    """Test the _try_lookup_storage_by_name() method directly."""

    def test_try_lookup_same_region_succeeds(self, storage_eastus):
        """Should return storage when found in same region."""
        orchestrator = CLIOrchestrator(region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_eastus]

            result = orchestrator._try_lookup_storage_by_name("test-rg", "storage-eastus")
            assert result is not None
            assert result.name == "storage-eastus"

    def test_try_lookup_cross_region_returns_storage(self, storage_westus, caplog):
        """Should return storage with info log when storage is cross-region."""
        orchestrator = CLIOrchestrator(region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_westus]

            result = orchestrator._try_lookup_storage_by_name("test-rg", "storage-westus")
            assert result is not None
            assert result.name == "storage-westus"

            # Should log info about cross-region mount
            assert any(
                "Cross-region mount will be configured" in record.message
                for record in caplog.records
            )

    def test_try_lookup_not_found_returns_none(self, caplog):
        """Should return None with warning when storage not found."""
        orchestrator = CLIOrchestrator(region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = []

            result = orchestrator._try_lookup_storage_by_name("test-rg", "nonexistent")
            assert result is None

            # Should log warning
            assert any(
                "Config default storage 'nonexistent' not found" in record.message
                for record in caplog.records
            )

    def test_try_lookup_listing_fails_returns_none(self, caplog):
        """Should return None with warning when listing fails."""
        orchestrator = CLIOrchestrator(region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.side_effect = Exception("API error")

            result = orchestrator._try_lookup_storage_by_name("test-rg", "storage-eastus")
            assert result is None

            # Should log warning
            assert any(
                "Could not list storage accounts" in record.message for record in caplog.records
            )


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_case_insensitive_region_matching(self, storage_eastus):
        """Should handle region comparison case-insensitively."""
        # Storage is "eastus", VM is "EastUS"
        orchestrator = CLIOrchestrator(region="EastUS")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_eastus]

            result = orchestrator._resolve_nfs_storage("test-rg", None)
            assert result is not None
            assert result.name == "storage-eastus"

    def test_no_config_skips_priority2(self, storage_eastus):
        """Should skip Priority 2 when config is None."""
        orchestrator = CLIOrchestrator(region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_eastus]

            result = orchestrator._resolve_nfs_storage("test-rg", None)
            # Should go directly to Priority 3
            assert result is not None
            assert result.name == "storage-eastus"

    def test_empty_config_default_nfs_storage_skips_priority2(self, storage_eastus):
        """Should skip Priority 2 when config.default_nfs_storage is None."""
        orchestrator = CLIOrchestrator(region="eastus")

        mock_config = MagicMock()
        mock_config.default_nfs_storage = None

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_eastus]

            result = orchestrator._resolve_nfs_storage("test-rg", mock_config)
            # Should go directly to Priority 3
            assert result is not None
            assert result.name == "storage-eastus"

    def test_priority2_with_only_cross_region_storage_succeeds(self, storage_westus, caplog):
        """Priority 2 should succeed even when only cross-region storage exists."""
        orchestrator = CLIOrchestrator(region="eastus")

        mock_config = MagicMock()
        mock_config.default_nfs_storage = "storage-westus"

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_westus]

            result = orchestrator._resolve_nfs_storage("test-rg", mock_config)
            # Priority 2 now accepts cross-region storage
            assert result is not None
            assert result.name == "storage-westus"
            assert result.region == "westus"

            # Should log info about cross-region mount from Priority 2
            assert any(
                "Cross-region mount will be configured" in record.message
                for record in caplog.records
            )


class TestBackwardCompatibility:
    """Test that changes maintain backward compatibility."""

    def test_explicit_storage_behavior_unchanged(self, storage_eastus):
        """Explicit storage behavior should be unchanged for same-region."""
        orchestrator = CLIOrchestrator(nfs_storage="storage-eastus", region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_eastus]

            result = orchestrator._resolve_nfs_storage("test-rg", None)
            assert result is not None
            assert result.name == "storage-eastus"

    def test_auto_detect_behavior_unchanged(self, storage_eastus):
        """Auto-detect behavior should be unchanged for same-region."""
        orchestrator = CLIOrchestrator(region="eastus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_eastus]

            result = orchestrator._resolve_nfs_storage("test-rg", None)
            assert result is not None
            assert result.name == "storage-eastus"

    def test_multiple_storages_error_unchanged(self, storage_westus, storage_westus2):
        """Multiple storages error should be unchanged."""
        orchestrator = CLIOrchestrator(region="westus")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [storage_westus, storage_westus2]

            with pytest.raises(ValueError, match="Multiple NFS storage accounts found"):
                orchestrator._resolve_nfs_storage("test-rg", None)
