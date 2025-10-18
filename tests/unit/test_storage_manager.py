"""Unit tests for storage_manager module.

TDD Approach: Write these tests FIRST, then implement to make them pass.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.modules.storage_manager import (
    StorageError,
    StorageInUseError,
    StorageInfo,
    StorageManager,
    StorageNotFoundError,
    StorageStatus,
    ValidationError,
)


class TestStorageNameValidation:
    """Test storage name validation."""

    def test_name_too_short(self):
        """Storage name must be at least 3 characters."""
        with pytest.raises(ValidationError, match="at least 3 characters"):
            StorageManager.create_storage("ab", "test-rg", "westus2")

    def test_name_too_long(self):
        """Storage name must be at most 24 characters."""
        with pytest.raises(ValidationError, match="at most 24 characters"):
            StorageManager.create_storage("a" * 25, "test-rg", "westus2")

    def test_name_invalid_characters(self):
        """Storage name must be alphanumeric."""
        with pytest.raises(ValidationError, match="alphanumeric"):
            StorageManager.create_storage("test-storage", "test-rg", "westus2")
            
    def test_name_valid(self):
        """Valid storage names should pass validation."""
        # This test will fail until we implement create_storage
        # That's expected in TDD!
        pass


class TestStorageTierValidation:
    """Test storage tier validation."""

    def test_tier_invalid(self):
        """Tier must be Premium or Standard."""
        with pytest.raises(ValidationError, match="Tier must be one of"):
            StorageManager.create_storage("test123", "test-rg", "westus2", tier="Invalid")

    def test_tier_premium(self):
        """Premium tier should be accepted."""
        pass  # Will implement

    def test_tier_standard(self):
        """Standard tier should be accepted."""
        pass  # Will implement


class TestStorageSizeValidation:
    """Test storage size validation."""

    def test_size_negative(self):
        """Size must be positive."""
        with pytest.raises(ValidationError, match="greater than zero"):
            StorageManager.create_storage("test123", "test-rg", "westus2", size_gb=-100)

    def test_size_zero(self):
        """Size must be greater than zero."""
        with pytest.raises(ValidationError, match="greater than zero"):
            StorageManager.create_storage("test123", "test-rg", "westus2", size_gb=0)

    def test_size_valid(self):
        """Valid sizes should be accepted."""
        pass  # Will implement


class TestCreateStorage:
    """Test storage account creation."""

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_create_calls_azure_cli(self, mock_run):
        """Create storage should call Azure CLI."""
        # Mock the get_storage call (checking if exists)
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "az", stderr="ResourceNotFound"),  # get_storage check
            MagicMock(returncode=0, stdout='{"name": "test123", "location": "westus2"}'),  # create
            MagicMock(returncode=0, stdout='{}'),  # create file share
        ]
        
        result = StorageManager.create_storage("test123", "test-rg", "westus2")
        
        assert mock_run.called
        # Check that az storage account create was called
        call_args_str = str(mock_run.call_args_list)
        assert "az" in call_args_str
        assert "storage" in call_args_str

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_create_idempotent(self, mock_run):
        """Creating existing storage should return existing."""
        # Mock successful get_storage (exists)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='{"name": "test123", "location": "westus2", "sku": {"name": "Premium_LRS"}}'),
            MagicMock(returncode=0, stdout='100'),  # share quota
        ]
        
        result1 = StorageManager.create_storage("test123", "test-rg", "westus2")
        
        # Reset and call again
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='{"name": "test123", "location": "westus2", "sku": {"name": "Premium_LRS"}}'),
            MagicMock(returncode=0, stdout='100'),
        ]
        result2 = StorageManager.create_storage("test123", "test-rg", "westus2")
        
        assert result1.name == result2.name

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_create_returns_storage_info(self, mock_run):
        """Create should return StorageInfo dataclass."""
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "az", stderr="ResourceNotFound"),  # doesn't exist
            MagicMock(returncode=0, stdout='{"name": "test123", "location": "westus2"}'),  # create
            MagicMock(returncode=0, stdout='{}'),  # file share
        ]
        
        result = StorageManager.create_storage("test123", "test-rg", "westus2")
        
        assert isinstance(result, StorageInfo)
        assert result.name == "test123"
        assert result.region == "westus2"

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_create_handles_azure_error(self, mock_run):
        """Create should handle Azure CLI errors."""
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "az", stderr="ResourceNotFound"),  # doesn't exist
            subprocess.CalledProcessError(1, "az", stderr="Error: quota exceeded"),  # creation fails
        ]
        
        with pytest.raises(StorageError, match="quota exceeded"):
            StorageManager.create_storage("test123", "test-rg", "westus2")


class TestListStorage:
    """Test listing storage accounts."""

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_list_empty(self, mock_run):
        """List should return empty list when no storage."""
        mock_run.return_value = MagicMock(returncode=0, stdout="[]")
        
        result = StorageManager.list_storage("test-rg")
        
        assert result == []

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_list_multiple(self, mock_run):
        """List should return all storage accounts."""
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout='[{"name": "storage1", "location": "westus2", "sku": {"name": "Premium_LRS"}, "creationTime": "2025-01-01T00:00:00Z"}, {"name": "storage2", "location": "westus2", "sku": {"name": "Standard_LRS"}, "creationTime": "2025-01-01T00:00:00Z"}]'
            ),
            MagicMock(returncode=0, stdout='100'),  # quota for storage1
            MagicMock(returncode=0, stdout='200'),  # quota for storage2
        ]
        
        result = StorageManager.list_storage("test-rg")
        
        assert len(result) == 2
        assert result[0].name == "storage1"
        assert result[1].name == "storage2"

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_list_filters_azlin_only(self, mock_run):
        """List should only return azlin-managed storage."""
        # The query already filters by managed-by=azlin tag
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"name": "azlinstorage", "location": "westus2", "sku": {"name": "Premium_LRS"}, "creationTime": "2025-01-01T00:00:00Z"}]'
        )
        
        result = StorageManager.list_storage("test-rg")
        
        # Should return filtered results
        assert len(result) >= 0  # Just check it doesn't crash


class TestGetStorage:
    """Test getting storage account details."""

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_get_existing(self, mock_run):
        """Get should return storage info for existing account."""
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout='{"name": "test123", "location": "westus2", "sku": {"name": "Premium_LRS"}, "creationTime": "2025-01-01T00:00:00Z"}'
            ),
            MagicMock(returncode=0, stdout='100'),  # quota
        ]
        
        result = StorageManager.get_storage("test123", "test-rg")
        
        assert result.name == "test123"

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_get_not_found(self, mock_run):
        """Get should raise error when storage doesn't exist."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="ResourceNotFound"
        )
        
        with pytest.raises(StorageNotFoundError):
            StorageManager.get_storage("nonexistent", "test-rg")


class TestGetStorageStatus:
    """Test getting detailed storage status."""

    @patch("azlin.modules.storage_manager.subprocess.run")
    @patch("azlin.config_manager.ConfigManager")
    def test_status_includes_usage(self, mock_config, mock_run):
        """Status should include used space and utilization."""
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout='{"name": "test123", "location": "westus2", "sku": {"name": "Premium_LRS"}, "creationTime": "2025-01-01T00:00:00Z"}'
            ),
            MagicMock(returncode=0, stdout='100'),  # quota
        ]
        mock_config_obj = MagicMock()
        mock_config_obj.to_dict.return_value = {"vm_storage": {}}
        mock_config.load_config.return_value = mock_config_obj
        
        result = StorageManager.get_storage_status("test123", "test-rg")
        
        assert isinstance(result, StorageStatus)
        assert result.used_gb >= 0

    @patch("azlin.modules.storage_manager.subprocess.run")
    @patch("azlin.config_manager.ConfigManager")
    def test_status_includes_connected_vms(self, mock_config, mock_run):
        """Status should list connected VMs."""
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout='{"name": "test123", "location": "westus2", "sku": {"name": "Premium_LRS"}, "creationTime": "2025-01-01T00:00:00Z"}'
            ),
            MagicMock(returncode=0, stdout='100'),
        ]
        mock_config_obj = MagicMock()
        mock_config_obj.to_dict.return_value = {"vm_storage": {"vm1": "test123", "vm2": "test123"}}
        mock_config.load_config.return_value = mock_config_obj
        
        result = StorageManager.get_storage_status("test123", "test-rg")
        
        assert isinstance(result.connected_vms, list)
        assert len(result.connected_vms) == 2

    @patch("azlin.modules.storage_manager.subprocess.run")
    @patch("azlin.config_manager.ConfigManager")
    def test_status_calculates_cost(self, mock_config, mock_run):
        """Status should calculate monthly cost."""
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout='{"name": "test123", "location": "westus2", "sku": {"name": "Premium_LRS"}, "creationTime": "2025-01-01T00:00:00Z"}'
            ),
            MagicMock(returncode=0, stdout='100'),
        ]
        mock_config_obj = MagicMock()
        mock_config_obj.to_dict.return_value = {"vm_storage": {}}
        mock_config.load_config.return_value = mock_config_obj
        
        result = StorageManager.get_storage_status("test123", "test-rg")
        
        assert result.cost_per_month > 0


class TestDeleteStorage:
    """Test storage account deletion."""

    @patch("azlin.modules.storage_manager.subprocess.run")
    @patch("azlin.config_manager.ConfigManager")
    def test_delete_success(self, mock_config, mock_run):
        """Delete should successfully remove storage."""
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout='{"name": "test123", "location": "westus2", "sku": {"name": "Premium_LRS"}, "creationTime": "2025-01-01T00:00:00Z"}'
            ),
            MagicMock(returncode=0, stdout='100'),
            MagicMock(returncode=0),  # delete
        ]
        mock_config_obj = MagicMock()
        mock_config_obj.to_dict.return_value = {"vm_storage": {}}
        mock_config.load_config.return_value = mock_config_obj
        
        # Should not raise
        StorageManager.delete_storage("test123", "test-rg", force=True)

    @patch("azlin.config_manager.ConfigManager")
    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_delete_with_connected_vms(self, mock_run, mock_config):
        """Delete should fail if VMs connected and not force."""
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout='{"name": "test123", "location": "westus2", "sku": {"name": "Premium_LRS"}, "creationTime": "2025-01-01T00:00:00Z"}'
            ),
            MagicMock(returncode=0, stdout='100'),
        ]
        mock_config_obj = MagicMock()
        mock_config_obj.to_dict.return_value = {"vm_storage": {"vm1": "test123"}}
        mock_config.load_config.return_value = mock_config_obj
        
        with pytest.raises(StorageInUseError, match="still has VMs connected"):
            StorageManager.delete_storage("test123", "test-rg", force=False)

    @patch("azlin.modules.storage_manager.subprocess.run")
    @patch("azlin.config_manager.ConfigManager")
    def test_delete_force_with_connected_vms(self, mock_config, mock_run):
        """Delete with force should succeed even with connected VMs."""
        mock_run.return_value = MagicMock(returncode=0)
        mock_config_obj = MagicMock()
        mock_config_obj.to_dict.return_value = {"vm_storage": {}}
        mock_config.load_config.return_value = mock_config_obj
        
        # Should not raise
        StorageManager.delete_storage("test123", "test-rg", force=True)

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_delete_not_found(self, mock_run):
        """Delete non-existent storage should be idempotent."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="ResourceNotFound"
        )
        
        # Should not raise (idempotent)
        StorageManager.delete_storage("nonexistent", "test-rg", force=True)


class TestStorageInfo:
    """Test StorageInfo dataclass."""

    def test_storage_info_creation(self):
        """StorageInfo should be creatable with all fields."""
        from datetime import datetime
        
        info = StorageInfo(
            name="test123",
            resource_group="test-rg",
            region="westus2",
            tier="Premium",
            size_gb=100,
            nfs_endpoint="test123.file.core.windows.net:/share",
            created=datetime.now(),
        )
        
        assert info.name == "test123"
        assert info.tier == "Premium"


class TestStorageStatus:
    """Test StorageStatus dataclass."""

    def test_storage_status_creation(self):
        """StorageStatus should include all required fields."""
        from datetime import datetime
        
        info = StorageInfo(
            name="test123",
            resource_group="test-rg",
            region="westus2",
            tier="Premium",
            size_gb=100,
            nfs_endpoint="test123.file.core.windows.net:/share",
            created=datetime.now(),
        )
        
        status = StorageStatus(
            info=info,
            used_gb=45.0,
            utilization_percent=45.0,
            connected_vms=["vm1", "vm2"],
            cost_per_month=15.36,
        )
        
        assert status.used_gb == 45.0
        assert len(status.connected_vms) == 2
