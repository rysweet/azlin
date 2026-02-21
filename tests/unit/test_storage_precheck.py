"""Tests for storage account pre-check before VM provisioning.

This test module verifies that storage accounts are checked and optionally
created BEFORE VM provisioning starts, preventing late failures after
expensive VM creation.

Issue: #296
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from azlin.config_manager import AzlinConfig
from azlin.modules.storage_manager import StorageInfo
from azlin.orchestrator import CLIOrchestrator


@pytest.fixture
def orchestrator():
    """Create orchestrator with mocked dependencies."""
    with patch("azlin.orchestrator.AzureAuthenticator"):
        with patch("azlin.orchestrator.VMProvisioner"):
            with patch("azlin.orchestrator.ProgressDisplay"):
                orch = CLIOrchestrator(
                    resource_group="test-rg",
                    region="westus2",
                    vm_size="Standard_B2s",
                    repo=None,
                    nfs_storage=None,
                    no_nfs=False,
                    auto_connect=False,
                    session_name=None,
                    config_file=None,
                )
                return orch


def make_storage_info(name="test-storage", region="westus2"):
    """Helper to create StorageInfo with all required fields."""
    return StorageInfo(
        name=name,
        resource_group="test-rg",
        region=region,
        size_gb=100,
        tier="Premium",
        nfs_endpoint=f"{name}.file.core.windows.net",
        created=datetime.now(),
    )


class TestStoragePrecheck:
    """Test storage pre-check functionality."""

    @patch("azlin.modules.storage_manager.StorageManager.list_storage")
    def test_storage_exists_no_action_needed(self, mock_list, orchestrator):
        """Test that pre-check passes when storage exists."""
        config = AzlinConfig(default_nfs_storage="test-storage")

        # Storage exists
        mock_list.return_value = [make_storage_info("test-storage")]

        # Should not raise any exception
        orchestrator._check_and_create_storage_if_needed("test-rg", config)

        # Should have checked for storage
        mock_list.assert_called_once_with("test-rg")

    @patch("azlin.modules.storage_manager.StorageManager.list_storage")
    def test_no_storage_configured_skips_precheck(self, mock_list, orchestrator):
        """Test that pre-check is skipped when no storage is configured."""
        config = AzlinConfig()  # No default_nfs_storage

        # Should return early without checking
        orchestrator._check_and_create_storage_if_needed("test-rg", config)

        # Should NOT have tried to list storage
        mock_list.assert_not_called()

    @patch("azlin.modules.storage_manager.StorageManager.list_storage")
    def test_explicit_nfs_storage_checked(self, mock_list, orchestrator):
        """Test that explicit --nfs-storage option is checked."""
        orchestrator.nfs_storage = "explicit-storage"
        config = AzlinConfig(default_nfs_storage="default-storage")

        # Explicit storage exists
        mock_list.return_value = [make_storage_info("explicit-storage")]

        orchestrator._check_and_create_storage_if_needed("test-rg", config)

        # Should have checked for storage
        mock_list.assert_called_once_with("test-rg")

    @patch("azlin.modules.storage_manager.StorageManager.create_storage")
    @patch("azlin.modules.storage_manager.StorageManager.list_storage")
    @patch("click.confirm")
    @patch("click.echo")
    def test_storage_missing_user_accepts_creation(
        self, mock_echo, mock_confirm, mock_list, mock_create, orchestrator
    ):
        """Test storage creation when user accepts prompt."""
        config = AzlinConfig(default_nfs_storage="new-storage")
        mock_confirm.return_value = True  # User accepts

        # Storage doesn't exist initially
        mock_list.return_value = []
        # Mock successful creation
        mock_create.return_value = make_storage_info("new-storage")

        orchestrator._check_and_create_storage_if_needed("test-rg", config)

        # Should have prompted user
        mock_confirm.assert_called_once()

        # Should have created storage
        mock_create.assert_called_once_with(
            name="new-storage",
            resource_group="test-rg",
            region="westus2",
            tier="Premium",
            size_gb=100,
        )

        # Should have shown success message
        assert any("✓ Storage account created" in str(call) for call in mock_echo.call_args_list)

    @patch("azlin.modules.storage_manager.StorageManager.list_storage")
    @patch("click.confirm")
    @patch("click.echo")
    def test_storage_missing_user_declines_creation(
        self, mock_echo, mock_confirm, mock_list, orchestrator
    ):
        """Test that ValueError is raised when user declines storage creation."""
        config = AzlinConfig(default_nfs_storage="new-storage")
        mock_confirm.return_value = False  # User declines

        # Storage doesn't exist
        mock_list.return_value = []

        # Should raise ValueError with helpful message
        with pytest.raises(ValueError, match="new-storage.*required but was not created"):
            orchestrator._check_and_create_storage_if_needed("test-rg", config)

    @patch("azlin.modules.storage_manager.StorageManager.create_storage")
    @patch("azlin.modules.storage_manager.StorageManager.list_storage")
    @patch("click.confirm")
    def test_storage_creation_fails_with_helpful_error(
        self, mock_confirm, mock_list, mock_create, orchestrator
    ):
        """Test that storage creation failure provides helpful error message."""
        config = AzlinConfig(default_nfs_storage="new-storage")
        mock_confirm.return_value = True  # User accepts

        # Storage doesn't exist
        mock_list.return_value = []
        # Creation fails
        mock_create.side_effect = Exception("Quota exceeded in westus2")

        # Should raise ValueError with helpful message
        with pytest.raises(ValueError, match="Failed to create storage account.*new-storage"):
            orchestrator._check_and_create_storage_if_needed("test-rg", config)

    @patch("azlin.modules.storage_manager.StorageManager.list_storage")
    def test_storage_list_fails_gracefully(self, mock_list, orchestrator):
        """Test that storage list failure doesn't block provisioning."""
        config = AzlinConfig(default_nfs_storage="test-storage")

        # List operation fails
        mock_list.side_effect = Exception("API timeout")

        # Should not raise - allows proceeding to VM provisioning
        orchestrator._check_and_create_storage_if_needed("test-rg", config)


class TestStoragePrecheckEdgeCases:
    """Test edge cases for storage pre-check."""

    @patch("azlin.modules.storage_manager.StorageManager.list_storage")
    def test_multiple_storages_exist_including_target(self, mock_list, orchestrator):
        """Test pre-check when multiple storages exist including target."""
        config = AzlinConfig(default_nfs_storage="target-storage")

        storage1 = make_storage_info("other-storage")
        storage2 = make_storage_info("target-storage")
        mock_list.return_value = [storage1, storage2]

        # Should pass without attempting creation
        orchestrator._check_and_create_storage_if_needed("test-rg", config)

        # Should have listed storage
        mock_list.assert_called_once_with("test-rg")

    @patch("azlin.modules.storage_manager.StorageManager.list_storage")
    def test_cross_region_storage_still_prechecked(self, mock_list, orchestrator):
        """Test that cross-region storage is still pre-checked for existence."""
        config = AzlinConfig(default_nfs_storage="cross-region-storage")
        orchestrator.region = "westus2"

        # Storage exists but in different region
        cross_region_storage = make_storage_info("cross-region-storage", "eastus")
        mock_list.return_value = [cross_region_storage]

        # Should pass - existence is verified even if region differs
        orchestrator._check_and_create_storage_if_needed("test-rg", config)

        # Should have listed storage
        mock_list.assert_called_once_with("test-rg")
