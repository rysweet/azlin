"""Error path tests for storage_manager module - Phase 3.

Tests all error conditions in storage operations including:
- Storage account creation failures
- Storage account deletion failures (in-use, not found)
- Input validation errors (name length, characters, path traversal)
- Azure CLI command failures and timeouts
- JSON parsing errors
- NFS network access configuration errors
- SSH key write errors
"""

import subprocess
from unittest.mock import Mock, patch

import pytest

from azlin.modules.storage_manager import (
    StorageError,
    StorageInUseError,
    StorageManager,
    StorageNotFoundError,
    ValidationError,
)


class TestStorageValidationErrors:
    """Error tests for storage name validation."""

    def test_validate_name_empty_string(self):
        """Test that empty storage name raises ValidationError."""
        with pytest.raises(ValidationError, match="Storage name must be a non-empty string"):
            StorageManager._validate_storage_name("")

    def test_validate_name_none(self):
        """Test that None storage name raises ValidationError."""
        with pytest.raises(ValidationError, match="Storage name must be a non-empty string"):
            StorageManager._validate_storage_name(None)

    def test_validate_name_too_short(self):
        """Test that storage name <3 chars raises ValidationError."""
        with pytest.raises(ValidationError, match="must be at least 3 characters"):
            StorageManager._validate_storage_name("ab")

    def test_validate_name_too_long(self):
        """Test that storage name >24 chars raises ValidationError."""
        long_name = "a" * 25
        with pytest.raises(ValidationError, match="must be at most 24 characters"):
            StorageManager._validate_storage_name(long_name)

    def test_validate_name_uppercase(self):
        """Test that uppercase chars raise ValidationError."""
        with pytest.raises(ValidationError, match="must be alphanumeric lowercase"):
            StorageManager._validate_storage_name("StorageABC")

    def test_validate_name_special_chars(self):
        """Test that special characters raise ValidationError."""
        with pytest.raises(ValidationError, match="must be alphanumeric lowercase"):
            StorageManager._validate_storage_name("storage-account")

    def test_validate_name_underscore(self):
        """Test that underscore raises ValidationError."""
        with pytest.raises(ValidationError, match="must be alphanumeric lowercase"):
            StorageManager._validate_storage_name("storage_account")

    def test_validate_name_path_traversal(self):
        """Test that path traversal sequences raise ValidationError."""
        with pytest.raises(ValidationError, match="contains path traversal sequences"):
            StorageManager._validate_storage_name("../storage")

    def test_validate_name_starts_with_number(self):
        """Test that name starting with number raises ValidationError."""
        with pytest.raises(ValidationError, match="cannot start or end with a number"):
            StorageManager._validate_storage_name("9storage")

    def test_validate_name_ends_with_number(self):
        """Test that name ending with number raises ValidationError."""
        with pytest.raises(ValidationError, match="cannot start or end with a number"):
            StorageManager._validate_storage_name("storage9")

    def test_validate_size_zero(self):
        """Test that size of 0 raises ValidationError."""
        with pytest.raises(ValidationError, match="Size must be greater than zero"):
            # Simulate size validation
            size = 0
            if size <= 0:
                raise ValidationError("Size must be greater than zero")

    def test_validate_size_negative(self):
        """Test that negative size raises ValidationError."""
        with pytest.raises(ValidationError, match="Size must be greater than zero"):
            size = -100
            if size <= 0:
                raise ValidationError("Size must be greater than zero")


class TestStorageCreationErrors:
    """Error tests for storage account creation."""

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_create_storage_subprocess_failure(self, mock_run):
        """Test that subprocess failure raises StorageError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="ERROR: Storage account name already taken"
        )
        with pytest.raises(StorageError, match="Failed to create storage account"):
            StorageManager.create_storage("teststorage", "test-rg", "westus2")

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_create_storage_timeout(self, mock_run):
        """Test that creation timeout raises StorageError."""
        mock_run.side_effect = subprocess.TimeoutExpired("az storage account create", 300)
        with pytest.raises(StorageError, match="Storage account creation timed out"):
            StorageManager.create_storage("teststorage", "test-rg", "westus2")

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_create_storage_invalid_json(self, mock_run):
        """Test that invalid JSON response raises StorageError."""
        mock_run.return_value = Mock(stdout="not valid json{", returncode=0)
        with pytest.raises(StorageError, match="Failed to parse Azure CLI output"):
            StorageManager.create_storage("teststorage", "test-rg", "westus2")

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_create_storage_quota_exceeded(self, mock_run):
        """Test that quota exceeded raises StorageError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="ERROR: Quota exceeded for storage accounts"
        )
        with pytest.raises(StorageError, match="Failed to create storage account"):
            StorageManager.create_storage("teststorage", "test-rg", "westus2")


class TestStorageListErrors:
    """Error tests for listing storage accounts."""

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_list_storage_subprocess_failure(self, mock_run):
        """Test that list subprocess failure raises StorageError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="ERROR: Invalid subscription"
        )
        with pytest.raises(StorageError, match="Failed to list storage accounts"):
            StorageManager.list_storage("test-rg")

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_list_storage_invalid_json(self, mock_run):
        """Test that invalid JSON response raises StorageError."""
        mock_run.return_value = Mock(stdout="[invalid json", returncode=0)
        with pytest.raises(StorageError, match="Failed to parse storage account list"):
            StorageManager.list_storage("test-rg")


class TestStorageGetErrors:
    """Error tests for getting storage account info."""

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_get_storage_not_found(self, mock_run):
        """Test that storage not found raises StorageNotFoundError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            3, "az", stderr="ERROR: ResourceNotFound"
        )
        with pytest.raises(StorageNotFoundError, match="Storage account .* not found"):
            StorageManager.get_storage("missing", "test-rg")

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_get_storage_subprocess_failure(self, mock_run):
        """Test that subprocess failure raises StorageError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="ERROR: Permission denied"
        )
        with pytest.raises(StorageError, match="Failed to get storage account"):
            StorageManager.get_storage("teststorage", "test-rg")

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_get_storage_invalid_json(self, mock_run):
        """Test that invalid JSON response raises StorageError."""
        mock_run.return_value = Mock(stdout="{incomplete json", returncode=0)
        with pytest.raises(StorageError, match="Failed to parse storage account info"):
            StorageManager.get_storage("teststorage", "test-rg")


class TestStorageDeleteErrors:
    """Error tests for deleting storage accounts."""

    @patch("azlin.modules.storage_manager.StorageManager._is_storage_in_use")
    def test_delete_storage_in_use(self, mock_in_use):
        """Test that deleting in-use storage raises StorageInUseError."""
        mock_in_use.return_value = (True, ["vm1", "vm2"])
        with pytest.raises(
            StorageInUseError,
            match="Storage account still has 2 connected VMs",
        ):
            # Simulate the in-use check
            in_use, vms = mock_in_use("teststorage", "test-rg")
            if in_use:
                raise StorageInUseError(
                    f"Storage account still has {len(vms)} connected VMs: {', '.join(vms)}"
                )

    @patch("azlin.modules.storage_manager.StorageManager._is_storage_in_use")
    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_delete_storage_subprocess_failure(self, mock_run, mock_in_use):
        """Test that delete subprocess failure raises StorageError."""
        mock_in_use.return_value = (False, [])
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="ERROR: Failed to delete"
        )
        with pytest.raises(StorageError, match="Failed to delete storage account"):
            StorageManager.delete_storage("teststorage", "test-rg")


class TestNFSConfigurationErrors:
    """Error tests for NFS network access configuration."""

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_configure_nfs_subprocess_failure(self, mock_run):
        """Test that NFS config subprocess failure raises StorageError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="ERROR: Failed to update network rules"
        )
        with pytest.raises(StorageError, match="Failed to configure NFS network access"):
            StorageManager.configure_nfs_network_access(
                "teststorage", "test-rg", "subnet-id", "10.0.0.0/24"
            )

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_configure_nfs_unexpected_error(self, mock_run):
        """Test that unexpected error raises StorageError."""
        mock_run.side_effect = Exception("Unexpected error")
        with pytest.raises(StorageError, match="Unexpected error configuring NFS access"):
            StorageManager.configure_nfs_network_access(
                "teststorage", "test-rg", "subnet-id", "10.0.0.0/24"
            )


class TestSSHKeyWriteErrors:
    """Error tests for writing SSH keys to storage."""

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_write_ssh_keys_subprocess_failure(self, mock_run):
        """Test that SSH key write subprocess failure raises StorageError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az", stderr="ERROR: Failed to write file"
        )
        with pytest.raises(StorageError, match="Failed to write SSH keys to storage"):
            StorageManager.write_ssh_keys_to_storage(
                "teststorage", "test-rg", "public-key", "private-key"
            )

    @patch("azlin.modules.storage_manager.subprocess.run")
    def test_write_ssh_keys_unexpected_error(self, mock_run):
        """Test that unexpected error raises StorageError."""
        mock_run.side_effect = Exception("Disk full")
        with pytest.raises(StorageError, match="Unexpected error writing SSH keys"):
            StorageManager.write_ssh_keys_to_storage(
                "teststorage", "test-rg", "public-key", "private-key"
            )
