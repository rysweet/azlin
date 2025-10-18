"""Integration tests for storage CLI commands.

Tests the CLI interface to storage management commands.
Uses Click's CliRunner for isolated command testing.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from azlin.cli import main
from azlin.modules.storage_manager import StorageInfo, StorageStatus


@pytest.fixture
def runner():
    """Create Click CLI runner."""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock config with default values."""
    config = MagicMock()
    config.default_resource_group = "test-rg"
    config.default_region = "westus2"
    return config


class TestStorageCreateCommand:
    """Test 'azlin storage create' command."""

    @patch("azlin.commands.storage.StorageManager.create_storage")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    def test_create_success(self, mock_load_config, mock_create, runner, mock_config):
        """Creating storage should show success message."""
        mock_load_config.return_value = mock_config
        mock_create.return_value = StorageInfo(
            name="test123",
            resource_group="test-rg",
            region="westus2",
            tier="Premium",
            size_gb=100,
            nfs_endpoint="test123.file.core.windows.net:/test123/home",
            created=datetime.now(),
        )

        result = runner.invoke(main, ["storage", "create", "test123"])

        assert result.exit_code == 0
        assert "Storage account created successfully" in result.output
        assert "test123" in result.output
        assert "test123.file.core.windows.net" in result.output

    @patch("azlin.commands.storage.StorageManager.create_storage")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    def test_create_with_custom_tier(self, mock_load_config, mock_create, runner, mock_config):
        """Creating with --tier should pass tier to manager."""
        mock_load_config.return_value = mock_config
        mock_create.return_value = StorageInfo(
            name="test123",
            resource_group="test-rg",
            region="westus2",
            tier="Standard",
            size_gb=100,
            nfs_endpoint="test123.file.core.windows.net:/test123/home",
            created=datetime.now(),
        )

        result = runner.invoke(main, ["storage", "create", "test123", "--tier", "Standard"])

        assert result.exit_code == 0
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["tier"] == "Standard"

    @patch("azlin.commands.storage.StorageManager.create_storage")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    def test_create_with_custom_size(self, mock_load_config, mock_create, runner, mock_config):
        """Creating with --size should pass size to manager."""
        mock_load_config.return_value = mock_config
        mock_create.return_value = StorageInfo(
            name="test123",
            resource_group="test-rg",
            region="westus2",
            tier="Premium",
            size_gb=500,
            nfs_endpoint="test123.file.core.windows.net:/test123/home",
            created=datetime.now(),
        )

        result = runner.invoke(main, ["storage", "create", "test123", "--size", "500"])

        assert result.exit_code == 0
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["size_gb"] == 500

    @patch("azlin.commands.storage.ConfigManager.load_config")
    def test_create_no_config_no_args(self, mock_load_config, runner):
        """Create without config and without --resource-group should fail."""
        from azlin.config_manager import ConfigError

        mock_load_config.side_effect = ConfigError("No config")

        result = runner.invoke(main, ["storage", "create", "test123"])

        assert result.exit_code != 0
        assert "No config found" in result.output or "Resource group required" in result.output

    @patch("azlin.commands.storage.StorageManager.create_storage")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    def test_create_shows_cost_estimate(self, mock_load_config, mock_create, runner, mock_config):
        """Create should show estimated monthly cost."""
        mock_load_config.return_value = mock_config
        mock_create.return_value = StorageInfo(
            name="test123",
            resource_group="test-rg",
            region="westus2",
            tier="Premium",
            size_gb=100,
            nfs_endpoint="test123.file.core.windows.net:/test123/home",
            created=datetime.now(),
        )

        result = runner.invoke(main, ["storage", "create", "test123", "--size", "100"])

        assert result.exit_code == 0
        assert "Estimated cost:" in result.output
        assert "$" in result.output


class TestStorageListCommand:
    """Test 'azlin storage list' command."""

    @patch("azlin.commands.storage.StorageManager.list_storage")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    def test_list_empty(self, mock_load_config, mock_list, runner, mock_config):
        """Listing with no storage should show appropriate message."""
        mock_load_config.return_value = mock_config
        mock_list.return_value = []

        result = runner.invoke(main, ["storage", "list"])

        assert result.exit_code == 0
        assert "No NFS storage accounts found" in result.output

    @patch("azlin.commands.storage.StorageManager.list_storage")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    def test_list_multiple(self, mock_load_config, mock_list, runner, mock_config):
        """Listing multiple storage accounts should show all."""
        mock_load_config.return_value = mock_config
        mock_list.return_value = [
            StorageInfo(
                name="storage1",
                resource_group="test-rg",
                region="westus2",
                tier="Premium",
                size_gb=100,
                nfs_endpoint="storage1.file.core.windows.net:/storage1/home",
                created=datetime.now(),
            ),
            StorageInfo(
                name="storage2",
                resource_group="test-rg",
                region="eastus",
                tier="Standard",
                size_gb=200,
                nfs_endpoint="storage2.file.core.windows.net:/storage2/home",
                created=datetime.now(),
            ),
        ]

        result = runner.invoke(main, ["storage", "list"])

        assert result.exit_code == 0
        assert "storage1" in result.output
        assert "storage2" in result.output
        assert "Total: 2 storage account(s)" in result.output

    @patch("azlin.commands.storage.StorageManager.list_storage")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    def test_list_shows_correct_attributes(self, mock_load_config, mock_list, runner, mock_config):
        """List should show region, not location."""
        mock_load_config.return_value = mock_config
        mock_list.return_value = [
            StorageInfo(
                name="storage1",
                resource_group="test-rg",
                region="westus2",
                tier="Premium",
                size_gb=100,
                nfs_endpoint="storage1.file.core.windows.net:/storage1/home",
                created=datetime.now(),
            ),
        ]

        result = runner.invoke(main, ["storage", "list"])

        assert result.exit_code == 0
        assert "Region:" in result.output
        assert "westus2" in result.output
        # Should NOT have "Location:"
        assert "Location:" not in result.output


class TestStorageStatusCommand:
    """Test 'azlin storage status' command."""

    @patch("azlin.commands.storage.StorageManager.get_storage_status")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    def test_status_shows_full_info(self, mock_load_config, mock_get_status, runner, mock_config):
        """Status should show all storage information."""
        mock_load_config.return_value = mock_config

        storage_info = StorageInfo(
            name="test123",
            resource_group="test-rg",
            region="westus2",
            tier="Premium",
            size_gb=100,
            nfs_endpoint="test123.file.core.windows.net:/test123/home",
            created=datetime.now(),
        )

        mock_get_status.return_value = StorageStatus(
            info=storage_info,
            used_gb=45.5,
            utilization_percent=45.5,
            connected_vms=["vm1", "vm2"],
            cost_per_month=15.36,
        )

        result = runner.invoke(main, ["storage", "status", "test123"])

        assert result.exit_code == 0
        assert "test123" in result.output
        assert "45.5" in result.output  # Used GB
        assert "45.5%" in result.output  # Utilization
        assert "vm1" in result.output
        assert "vm2" in result.output
        assert "$15.36" in result.output

    @patch("azlin.commands.storage.StorageManager.get_storage_status")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    def test_status_shows_region_not_location(self, mock_load_config, mock_get_status, runner, mock_config):
        """Status should show 'Region:', not 'Location:'."""
        mock_load_config.return_value = mock_config

        storage_info = StorageInfo(
            name="test123",
            resource_group="test-rg",
            region="westus2",
            tier="Premium",
            size_gb=100,
            nfs_endpoint="test123.file.core.windows.net:/test123/home",
            created=datetime.now(),
        )

        mock_get_status.return_value = StorageStatus(
            info=storage_info,
            used_gb=0.0,
            utilization_percent=0.0,
            connected_vms=[],
            cost_per_month=15.36,
        )

        result = runner.invoke(main, ["storage", "status", "test123"])

        assert result.exit_code == 0
        assert "Region:" in result.output
        assert "westus2" in result.output
        # Should NOT have "Location:"
        assert "Location:" not in result.output

    @patch("azlin.commands.storage.StorageManager.get_storage_status")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    def test_status_no_connected_vms(self, mock_load_config, mock_get_status, runner, mock_config):
        """Status with no connected VMs should show (none)."""
        mock_load_config.return_value = mock_config

        storage_info = StorageInfo(
            name="test123",
            resource_group="test-rg",
            region="westus2",
            tier="Premium",
            size_gb=100,
            nfs_endpoint="test123.file.core.windows.net:/test123/home",
            created=datetime.now(),
        )

        mock_get_status.return_value = StorageStatus(
            info=storage_info,
            used_gb=0.0,
            utilization_percent=0.0,
            connected_vms=[],
            cost_per_month=15.36,
        )

        result = runner.invoke(main, ["storage", "status", "test123"])

        assert result.exit_code == 0
        assert "(none)" in result.output


class TestStorageDeleteCommand:
    """Test 'azlin storage delete' command."""

    @patch("azlin.commands.storage.click.confirm")
    @patch("azlin.commands.storage.StorageManager.delete_storage")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    def test_delete_requires_confirmation(
        self, mock_load_config, mock_delete, mock_confirm, runner, mock_config
    ):
        """Delete should require confirmation."""
        mock_load_config.return_value = mock_config
        mock_confirm.return_value = True

        result = runner.invoke(main, ["storage", "delete", "test123"])

        assert result.exit_code == 0
        mock_confirm.assert_called_once()
        mock_delete.assert_called_once()

    @patch("azlin.commands.storage.click.confirm")
    @patch("azlin.commands.storage.StorageManager.delete_storage")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    def test_delete_cancelled(
        self, mock_load_config, mock_delete, mock_confirm, runner, mock_config
    ):
        """Delete cancelled should not delete."""
        mock_load_config.return_value = mock_config
        mock_confirm.return_value = False

        runner.invoke(main, ["storage", "delete", "test123"])

        # Should still succeed but not call delete
        mock_delete.assert_not_called()

    @patch("azlin.commands.storage.StorageManager.delete_storage")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    def test_delete_force(self, mock_load_config, mock_delete, runner, mock_config):
        """Delete with --force should skip confirmation."""
        mock_load_config.return_value = mock_config

        result = runner.invoke(main, ["storage", "delete", "test123", "--force"])

        assert result.exit_code == 0
        # Force should pass force=True to manager
        mock_delete.assert_called_once()
        call_kwargs = mock_delete.call_args[1]
        assert call_kwargs.get("force") is True


class TestStorageMountCommand:
    """Test 'azlin storage mount' command."""

    @patch("azlin.commands.storage.NFSMountManager.mount_storage")
    @patch("azlin.commands.storage.StorageManager.get_storage")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    def test_mount_success(self, mock_load_config, mock_get_storage, mock_mount, runner, mock_config):
        """Mount should call NFSMountManager."""
        mock_load_config.return_value = mock_config
        mock_get_storage.return_value = StorageInfo(
            name="test123",
            resource_group="test-rg",
            region="westus2",
            tier="Premium",
            size_gb=100,
            nfs_endpoint="test123.file.core.windows.net:/test123/home",
            created=datetime.now(),
        )

        result = runner.invoke(main, ["storage", "mount", "test123", "--vm", "my-vm"])

        assert result.exit_code == 0
        mock_mount.assert_called_once()


class TestStorageUnmountCommand:
    """Test 'azlin storage unmount' command."""

    @patch("azlin.commands.storage.NFSMountManager.unmount_storage")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    def test_unmount_success(self, mock_load_config, mock_unmount, runner, mock_config):
        """Unmount should call NFSMountManager."""
        mock_load_config.return_value = mock_config

        result = runner.invoke(main, ["storage", "unmount", "my-vm"])

        assert result.exit_code == 0
        mock_unmount.assert_called_once()
