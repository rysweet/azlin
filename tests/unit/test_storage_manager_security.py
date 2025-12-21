"""Security tests for storage_manager.py path traversal protection and blob public access.

Tests verify that storage name validation prevents all path traversal attacks,
enforces Azure naming requirements, and ensures blob public access is disabled
for Azure policy compliance (Issue #508).
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from azlin.modules.storage_manager import StorageManager, ValidationError


class TestStorageNamePathTraversalProtection:
    """Test path traversal attack prevention in storage name validation."""

    def test_rejects_parent_directory_traversal(self):
        """Should reject names containing .. (parent directory)."""
        with pytest.raises(ValidationError, match="path traversal"):
            StorageManager._validate_name("../etc")

    def test_rejects_double_dot_in_middle(self):
        """Should reject names with .. in the middle."""
        with pytest.raises(ValidationError, match="path traversal"):
            StorageManager._validate_name("foo..bar")

    def test_rejects_forward_slash(self):
        """Should reject names containing forward slash."""
        with pytest.raises(ValidationError, match="path traversal"):
            StorageManager._validate_name("foo/bar")

    def test_rejects_backslash(self):
        """Should reject names containing backslash."""
        with pytest.raises(ValidationError, match="path traversal"):
            StorageManager._validate_name("foo\\bar")

    def test_rejects_absolute_path_unix(self):
        """Should reject Unix absolute paths."""
        with pytest.raises(ValidationError, match=r"path traversal|alphanumeric"):
            StorageManager._validate_name("/etc/passwd")

    def test_rejects_absolute_path_windows(self):
        """Should reject Windows absolute paths."""
        with pytest.raises(ValidationError, match=r"path traversal|alphanumeric"):
            StorageManager._validate_name("C:\\Windows")

    def test_rejects_complex_traversal(self):
        """Should reject complex traversal patterns."""
        with pytest.raises(ValidationError, match=r"path traversal|alphanumeric"):
            StorageManager._validate_name("foo/../../etc/passwd")

    def test_rejects_url_encoded_traversal(self):
        """Should reject URL-encoded path traversal attempts."""
        # The regex will catch these as they contain non-alphanumeric chars
        with pytest.raises(ValidationError, match="alphanumeric"):
            StorageManager._validate_name("foo%2e%2e%2fbar")

    def test_rejects_unicode_traversal(self):
        """Should reject Unicode path traversal attempts."""
        with pytest.raises(ValidationError, match="alphanumeric"):
            StorageManager._validate_name("foo\u2025bar")  # Two dot leader


class TestStorageNameValidation:
    """Test storage name validation against Azure requirements."""

    def test_accepts_valid_lowercase_alphanumeric(self):
        """Should accept valid lowercase alphanumeric names."""
        # Should not raise
        StorageManager._validate_name("validname123")
        StorageManager._validate_name("abc")
        StorageManager._validate_name("123")
        StorageManager._validate_name("a1b2c3")

    def test_rejects_empty_name(self):
        """Should reject empty name."""
        with pytest.raises(ValidationError, match="non-empty string"):
            StorageManager._validate_name("")

    def test_rejects_none_name(self):
        """Should reject None name."""
        with pytest.raises(ValidationError, match="non-empty string"):
            StorageManager._validate_name(None)

    def test_rejects_non_string(self):
        """Should reject non-string name."""
        with pytest.raises(ValidationError, match="non-empty string"):
            StorageManager._validate_name(123)

    def test_rejects_too_short_name(self):
        """Should reject names shorter than 3 characters."""
        with pytest.raises(ValidationError, match="at least 3"):
            StorageManager._validate_name("ab")

    def test_rejects_too_long_name(self):
        """Should reject names longer than 24 characters."""
        with pytest.raises(ValidationError, match="at most 24"):
            StorageManager._validate_name("a" * 25)

    def test_accepts_minimum_length(self):
        """Should accept 3-character name (minimum)."""
        StorageManager._validate_name("abc")

    def test_accepts_maximum_length(self):
        """Should accept 24-character name (maximum)."""
        StorageManager._validate_name("a" * 24)

    def test_rejects_uppercase_letters(self):
        """Should reject uppercase letters."""
        with pytest.raises(ValidationError, match="alphanumeric lowercase"):
            StorageManager._validate_name("MyStorage")

    def test_rejects_hyphens(self):
        """Should reject hyphens (Azure storage accounts don't allow them)."""
        with pytest.raises(ValidationError, match="alphanumeric lowercase"):
            StorageManager._validate_name("my-storage")

    def test_rejects_underscores(self):
        """Should reject underscores."""
        with pytest.raises(ValidationError, match="alphanumeric lowercase"):
            StorageManager._validate_name("my_storage")

    def test_rejects_spaces(self):
        """Should reject spaces."""
        with pytest.raises(ValidationError, match="alphanumeric lowercase"):
            StorageManager._validate_name("my storage")

    def test_rejects_special_characters(self):
        """Should reject special characters."""
        special_chars = "!@#$%^&*()+=[]{}|;:'\",.<>?"
        for char in special_chars:
            with pytest.raises(ValidationError, match="alphanumeric lowercase"):
                StorageManager._validate_name(f"storage{char}name")

    def test_rejects_dots(self):
        """Should reject dots (could be used for domain-like names)."""
        with pytest.raises(ValidationError, match="alphanumeric lowercase"):
            StorageManager._validate_name("storage.name")


class TestStorageNameEdgeCases:
    """Test edge cases in storage name validation."""

    def test_rejects_whitespace_only(self):
        """Should reject whitespace-only name."""
        with pytest.raises(ValidationError, match=r"non-empty string|alphanumeric"):
            StorageManager._validate_name("   ")

    def test_rejects_newline_in_name(self):
        """Should reject names containing newlines."""
        with pytest.raises(ValidationError, match="alphanumeric"):
            StorageManager._validate_name("foo\nbar")

    def test_rejects_tab_in_name(self):
        """Should reject names containing tabs."""
        with pytest.raises(ValidationError, match="alphanumeric"):
            StorageManager._validate_name("foo\tbar")

    def test_rejects_null_byte(self):
        """Should reject names containing null bytes."""
        with pytest.raises(ValidationError, match="alphanumeric"):
            StorageManager._validate_name("foo\x00bar")

    def test_all_numbers_valid(self):
        """Should accept all-numeric names."""
        StorageManager._validate_name("123456")

    def test_all_letters_valid(self):
        """Should accept all-letter names."""
        StorageManager._validate_name("abcdefgh")


class TestRealWorldAttackVectors:
    """Test real-world path traversal attack vectors."""

    def test_linux_etc_passwd(self):
        """Should reject attempt to access /etc/passwd."""
        with pytest.raises(ValidationError):
            StorageManager._validate_name("../../../etc/passwd")

    def test_windows_system32(self):
        """Should reject attempt to access Windows System32."""
        with pytest.raises(ValidationError):
            StorageManager._validate_name("..\\..\\Windows\\System32")

    def test_home_directory_escape(self):
        """Should reject attempt to escape to home directory."""
        with pytest.raises(ValidationError):
            StorageManager._validate_name("../../home/user")

    def test_root_directory(self):
        """Should reject attempt to access root directory."""
        with pytest.raises(ValidationError):
            StorageManager._validate_name("../../../")

    def test_current_directory_notation(self):
        """Should reject current directory notation."""
        with pytest.raises(ValidationError, match="path traversal"):
            StorageManager._validate_name("./storage")

    def test_mixed_slash_types(self):
        """Should reject mixed forward and backslashes."""
        with pytest.raises(ValidationError):
            StorageManager._validate_name("foo/bar\\baz")


class TestBlobPublicAccessSecurity:
    """Test blob public access security parameter (Issue #508).

    Verifies that storage account creation includes --allow-blob-public-access false
    for Azure policy compliance. Tests follow TDD approach.
    """

    @patch("azlin.modules.storage_manager.StorageManager.get_storage")
    @patch("subprocess.run")
    @patch("azlin.modules.storage_manager.StorageManager._create_nfs_file_share")
    def test_blob_public_access_parameter_present_premium(self, mock_share, mock_run, mock_get):
        """Verify --allow-blob-public-access parameter exists in Premium tier command."""
        # Mock get_storage to raise NotFoundError (storage doesn't exist yet)
        from azlin.modules.storage_manager import StorageNotFoundError

        mock_get.side_effect = StorageNotFoundError("Storage not found")

        # Mock successful storage account creation
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(
                {
                    "id": "test-id",
                    "name": "teststorage",
                    "location": "eastus",
                    "sku": {"name": "Premium_ZRS"},
                    "kind": "FileStorage",
                }
            ),
        )
        mock_share.return_value = None

        # Create Premium storage
        StorageManager.create_storage(
            name="teststorage",
            resource_group="test-rg",
            region="eastus",
            tier="Premium",
            size_gb=100,
        )

        # Verify command includes security parameter
        actual_cmd = mock_run.call_args[0][0]
        assert "--allow-blob-public-access" in actual_cmd, (
            "Command must include --allow-blob-public-access parameter for Azure policy compliance"
        )

    @patch("azlin.modules.storage_manager.StorageManager.get_storage")
    @patch("subprocess.run")
    @patch("azlin.modules.storage_manager.StorageManager._create_nfs_file_share")
    def test_blob_public_access_parameter_value_false(self, mock_share, mock_run, mock_get):
        """Verify --allow-blob-public-access value is exactly 'false'."""
        from azlin.modules.storage_manager import StorageNotFoundError

        mock_get.side_effect = StorageNotFoundError("Storage not found")

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(
                {
                    "id": "test-id",
                    "name": "teststorage",
                    "location": "eastus",
                    "sku": {"name": "Premium_ZRS"},
                    "kind": "FileStorage",
                }
            ),
        )
        mock_share.return_value = None

        StorageManager.create_storage(
            name="teststorage",
            resource_group="test-rg",
            region="eastus",
            tier="Premium",
            size_gb=100,
        )

        actual_cmd = mock_run.call_args[0][0]
        blob_idx = actual_cmd.index("--allow-blob-public-access")
        assert actual_cmd[blob_idx + 1] == "false", (
            "Blob public access must be disabled (value='false') for Azure policy compliance"
        )

    @patch("azlin.modules.storage_manager.StorageManager.get_storage")
    @patch("subprocess.run")
    @patch("azlin.modules.storage_manager.StorageManager._create_nfs_file_share")
    def test_blob_public_access_parameter_position(self, mock_share, mock_run, mock_get):
        """Verify parameter appears after --kind and before --https-only."""
        from azlin.modules.storage_manager import StorageNotFoundError

        mock_get.side_effect = StorageNotFoundError("Storage not found")

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(
                {
                    "id": "test-id",
                    "name": "teststorage",
                    "location": "eastus",
                    "sku": {"name": "Premium_ZRS"},
                    "kind": "FileStorage",
                }
            ),
        )
        mock_share.return_value = None

        StorageManager.create_storage(
            name="teststorage",
            resource_group="test-rg",
            region="eastus",
            tier="Premium",
            size_gb=100,
        )

        actual_cmd = mock_run.call_args[0][0]
        kind_idx = actual_cmd.index("--kind")
        https_idx = actual_cmd.index("--https-only")
        blob_idx = actual_cmd.index("--allow-blob-public-access")

        # Verify: --kind < --allow-blob-public-access < --https-only
        assert kind_idx < blob_idx < https_idx, (
            "Security parameters should be grouped: --kind, --allow-blob-public-access, --https-only"
        )

    @patch("azlin.modules.storage_manager.StorageManager.get_storage")
    @patch("subprocess.run")
    @patch("azlin.modules.storage_manager.StorageManager._create_nfs_container")
    def test_blob_public_access_parameter_present_standard(
        self, mock_container, mock_run, mock_get
    ):
        """Verify parameter exists in Standard tier command (StorageV2)."""
        from azlin.modules.storage_manager import StorageNotFoundError

        mock_get.side_effect = StorageNotFoundError("Storage not found")

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(
                {
                    "id": "test-id",
                    "name": "teststorage",
                    "location": "eastus",
                    "sku": {"name": "Standard_LRS"},
                    "kind": "StorageV2",
                }
            ),
        )
        mock_container.return_value = None

        # Create Standard storage
        StorageManager.create_storage(
            name="teststorage",
            resource_group="test-rg",
            region="eastus",
            tier="Standard",
            size_gb=100,
        )

        # Verify command includes security parameter
        actual_cmd = mock_run.call_args[0][0]
        assert "--allow-blob-public-access" in actual_cmd, (
            "Standard tier must also include --allow-blob-public-access parameter"
        )

    @patch("azlin.modules.storage_manager.StorageManager.get_storage")
    @patch("subprocess.run")
    @patch("azlin.modules.storage_manager.StorageManager._create_nfs_file_share")
    def test_blob_public_access_command_structure_premium(self, mock_share, mock_run, mock_get):
        """Verify complete command structure for Premium/FileStorage with security parameter."""
        from azlin.modules.storage_manager import StorageNotFoundError

        mock_get.side_effect = StorageNotFoundError("Storage not found")

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(
                {
                    "id": "test-id",
                    "name": "teststorage",
                    "location": "eastus",
                    "sku": {"name": "Premium_ZRS"},
                    "kind": "FileStorage",
                }
            ),
        )
        mock_share.return_value = None

        StorageManager.create_storage(
            name="teststorage",
            resource_group="test-rg",
            region="eastus",
            tier="Premium",
            size_gb=100,
        )

        actual_cmd = mock_run.call_args[0][0]

        # Verify all required parameters present
        required_params = [
            "--name",
            "--resource-group",
            "--location",
            "--sku",
            "--kind",
            "--allow-blob-public-access",  # Security parameter
            "--https-only",
            "--default-action",
        ]

        for param in required_params:
            assert param in actual_cmd, f"Command must include {param} parameter"

    @patch("azlin.modules.storage_manager.StorageManager.get_storage")
    @patch("subprocess.run")
    @patch("azlin.modules.storage_manager.StorageManager._create_nfs_container")
    def test_blob_public_access_command_structure_standard(
        self, mock_container, mock_run, mock_get
    ):
        """Verify complete command structure for Standard/StorageV2 with security parameter."""
        from azlin.modules.storage_manager import StorageNotFoundError

        mock_get.side_effect = StorageNotFoundError("Storage not found")

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(
                {
                    "id": "test-id",
                    "name": "teststorage",
                    "location": "eastus",
                    "sku": {"name": "Standard_LRS"},
                    "kind": "StorageV2",
                }
            ),
        )
        mock_container.return_value = None

        StorageManager.create_storage(
            name="teststorage",
            resource_group="test-rg",
            region="eastus",
            tier="Standard",
            size_gb=100,
        )

        actual_cmd = mock_run.call_args[0][0]

        # Verify all required parameters present
        required_params = [
            "--name",
            "--resource-group",
            "--location",
            "--sku",
            "--kind",
            "--allow-blob-public-access",  # Security parameter
            "--https-only",
            "--default-action",
        ]

        for param in required_params:
            assert param in actual_cmd, f"Command must include {param} parameter"
