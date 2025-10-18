"""Unit tests for storage_manager module.

TDD Approach: Write these tests FIRST, then implement to make them pass.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.storage_manager import (
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
        with pytest.raises(ValidationError, match="Premium or Standard"):
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
        with pytest.raises(ValidationError, match="positive"):
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

    @patch("azlin.storage_manager.subprocess.run")
    def test_create_calls_azure_cli(self, mock_run):
        """Create storage should call Azure CLI."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"name": "test123", "location": "westus2"}'
        )
        
        # This will fail until implemented
        result = StorageManager.create_storage("test123", "test-rg", "westus2")
        
        assert mock_run.called
        assert "az storage account create" in str(mock_run.call_args)

    @patch("azlin.storage_manager.subprocess.run")
    def test_create_idempotent(self, mock_run):
        """Creating existing storage should return existing."""
        # First check if exists
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"name": "test123", "provisioning State": "Succeeded"}'
        )
        
        result1 = StorageManager.create_storage("test123", "test-rg", "westus2")
        result2 = StorageManager.create_storage("test123", "test-rg", "westus2")
        
        assert result1.name == result2.name

    @patch("azlin.storage_manager.subprocess.run")
    def test_create_returns_storage_info(self, mock_run):
        """Create should return StorageInfo dataclass."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"name": "test123", "location": "westus2"}'
        )
        
        result = StorageManager.create_storage("test123", "test-rg", "westus2")
        
        assert isinstance(result, StorageInfo)
        assert result.name == "test123"
        assert result.region == "westus2"

    @patch("azlin.storage_manager.subprocess.run")
    def test_create_handles_azure_error(self, mock_run):
        """Create should handle Azure CLI errors."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="Error: quota exceeded"
        )
        
        with pytest.raises(StorageError, match="quota exceeded"):
            StorageManager.create_storage("test123", "test-rg", "westus2")


class TestListStorage:
    """Test listing storage accounts."""

    @patch("azlin.storage_manager.subprocess.run")
    def test_list_empty(self, mock_run):
        """List should return empty list when no storage."""
        mock_run.return_value = MagicMock(returncode=0, stdout="[]")
        
        result = StorageManager.list_storage("test-rg")
        
        assert result == []

    @patch("azlin.storage_manager.subprocess.run")
    def test_list_multiple(self, mock_run):
        """List should return all storage accounts."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"name": "storage1"}, {"name": "storage2"}]'
        )
        
        result = StorageManager.list_storage("test-rg")
        
        assert len(result) == 2
        assert result[0].name == "storage1"
        assert result[1].name == "storage2"

    @patch("azlin.storage_manager.subprocess.run")
    def test_list_filters_azlin_only(self, mock_run):
        """List should only return azlin-managed storage."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"name": "azlin-storage"}, {"name": "other-storage"}]'
        )
        
        result = StorageManager.list_storage("test-rg")
        
        # Should filter to only azlin-tagged storage
        assert len(result) == 1
        assert result[0].name == "azlin-storage"


class TestGetStorage:
    """Test getting storage account details."""

    @patch("azlin.storage_manager.subprocess.run")
    def test_get_existing(self, mock_run):
        """Get should return storage info for existing account."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"name": "test123", "location": "westus2"}'
        )
        
        result = StorageManager.get_storage("test123", "test-rg")
        
        assert result.name == "test123"

    @patch("azlin.storage_manager.subprocess.run")
    def test_get_not_found(self, mock_run):
        """Get should raise error when storage doesn't exist."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="ResourceNotFound"
        )
        
        with pytest.raises(StorageNotFoundError):
            StorageManager.get_storage("nonexistent", "test-rg")


class TestGetStorageStatus:
    """Test getting detailed storage status."""

    @patch("azlin.storage_manager.subprocess.run")
    def test_status_includes_usage(self, mock_run):
        """Status should include used space and utilization."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"usedCapacity": 45000000000}'  # 45GB
        )
        
        result = StorageManager.get_storage_status("test123", "test-rg")
        
        assert isinstance(result, StorageStatus)
        assert result.used_gb == 45.0

    @patch("azlin.storage_manager.subprocess.run")
    def test_status_includes_connected_vms(self, mock_run):
        """Status should list connected VMs."""
        # Mock will return VM list from config
        result = StorageManager.get_storage_status("test123", "test-rg")
        
        assert isinstance(result.connected_vms, list)

    @patch("azlin.storage_manager.subprocess.run")
    def test_status_calculates_cost(self, mock_run):
        """Status should calculate monthly cost."""
        result = StorageManager.get_storage_status("test123", "test-rg")
        
        assert result.cost_per_month > 0


class TestDeleteStorage:
    """Test storage account deletion."""

    @patch("azlin.storage_manager.subprocess.run")
    def test_delete_success(self, mock_run):
        """Delete should successfully remove storage."""
        mock_run.return_value = MagicMock(returncode=0)
        
        # Should not raise
        StorageManager.delete_storage("test123", "test-rg", force=True)

    def test_delete_with_connected_vms(self):
        """Delete should fail if VMs connected and not force."""
        # Mock storage with connected VMs
        with pytest.raises(StorageInUseError, match="VMs still connected"):
            StorageManager.delete_storage("test123", "test-rg", force=False)

    @patch("azlin.storage_manager.subprocess.run")
    def test_delete_force_with_connected_vms(self, mock_run):
        """Delete with force should succeed even with connected VMs."""
        mock_run.return_value = MagicMock(returncode=0)
        
        # Should not raise
        StorageManager.delete_storage("test123", "test-rg", force=True)

    @patch("azlin.storage_manager.subprocess.run")
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
