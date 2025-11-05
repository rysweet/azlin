"""Tests for NFS storage auto-detection and home directory setup."""

from unittest.mock import MagicMock, patch

import pytest

from azlin.cli import CLIOrchestrator
from azlin.modules.storage_manager import StorageInfo


@pytest.fixture
def mock_storage_info():
    """Create mock storage info."""
    return StorageInfo(
        name="test-storage",
        resource_group="test-rg",
        region="eastus",
        tier="Premium",
        size_gb=100,
        nfs_endpoint="test-storage.file.core.windows.net:/test-share",
        created=None,
    )


class TestNFSAutoDetection:
    """Test NFS storage auto-detection logic."""

    def test_explicit_nfs_storage_used(self, mock_storage_info):
        """Test that explicitly specified NFS storage is used."""
        orchestrator = CLIOrchestrator(nfs_storage="test-storage")

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [mock_storage_info]

            result = orchestrator._resolve_nfs_storage("test-rg", None)
            assert result == "test-storage"

    def test_single_storage_auto_detected(self, mock_storage_info):
        """Test that single NFS storage is auto-detected."""
        orchestrator = CLIOrchestrator()  # No explicit nfs_storage

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [mock_storage_info]

            result = orchestrator._resolve_nfs_storage("test-rg", None)
            assert result == "test-storage"

    def test_multiple_storages_without_explicit_choice_errors(self, mock_storage_info):
        """Test that multiple NFS storages without explicit choice raises error."""
        orchestrator = CLIOrchestrator()  # No explicit nfs_storage

        storage2 = StorageInfo(
            name="test-storage-2",
            resource_group="test-rg",
            region="eastus",
            tier="Premium",
            size_gb=100,
            nfs_endpoint="test-storage-2.file.core.windows.net:/test-share",
            created=None,
        )

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [mock_storage_info, storage2]

            with pytest.raises(ValueError, match="Multiple NFS storage accounts found"):
                orchestrator._resolve_nfs_storage("test-rg", None)

    def test_no_storages_returns_none(self):
        """Test that no NFS storages returns None."""
        orchestrator = CLIOrchestrator()

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = []

            result = orchestrator._resolve_nfs_storage("test-rg", None)
            assert result is None

    def test_config_default_storage_used(self, mock_storage_info):
        """Test that config default_nfs_storage is used."""
        orchestrator = CLIOrchestrator()

        mock_config = MagicMock()
        mock_config.default_nfs_storage = "test-storage"

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [mock_storage_info]

            result = orchestrator._resolve_nfs_storage("test-rg", mock_config)
            assert result == "test-storage"

    def test_explicit_overrides_config(self, mock_storage_info):
        """Test that explicit --nfs-storage overrides config default."""
        orchestrator = CLIOrchestrator(nfs_storage="explicit-storage")

        mock_config = MagicMock()
        mock_config.default_nfs_storage = "config-storage"

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = [
                mock_storage_info,
                StorageInfo(
                    name="explicit-storage",
                    resource_group="test-rg",
                    region="eastus",
                    tier="Premium",
                    size_gb=100,
                    nfs_endpoint="explicit-storage.file.core.windows.net:/test-share",
                    created=None,
                ),
            ]

            result = orchestrator._resolve_nfs_storage("test-rg", mock_config)
            assert result == "explicit-storage"


class TestNFSHomeDirectorySetup:
    """Test NFS home directory initial setup."""

    def test_empty_nfs_gets_home_content(self, mock_storage_info, tmp_path):
        """Test that empty NFS share gets ~/.azlin/home content.

        Note: Requires integration test with actual NFS mount. Skipped in unit tests.
        """
        pytest.skip("Integration test - requires actual NFS mount")

    def test_existing_nfs_content_preserved(self, mock_storage_info):
        """Test that existing NFS content is not overwritten.

        Note: Requires integration test with actual NFS mount. Skipped in unit tests.
        """
        pytest.skip("Integration test - requires actual NFS mount")


class TestBackwardCompatibility:
    """Test backward compatibility without NFS."""

    def test_no_nfs_uses_rsync(self):
        """Test that without NFS, regular rsync is used."""
        orchestrator = CLIOrchestrator()

        with patch("azlin.modules.storage_manager.StorageManager.list_storage") as mock_list:
            mock_list.return_value = []

            result = orchestrator._resolve_nfs_storage("test-rg", None)
            assert result is None
            # Orchestrator should fall back to regular home sync
