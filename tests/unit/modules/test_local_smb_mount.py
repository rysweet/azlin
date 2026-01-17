"""Unit tests for local_smb_mount module.

Tests macOS SMB mounting functionality including:
- Platform validation
- Input validation and security
- Mount operations
- Unmount operations
- Mount status checks
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.modules.local_smb_mount import (
    LocalSMBMount,
    LocalSMBMountError,
    MountInfo,
    MountPointError,
    MountResult,
    UnmountResult,
    UnsupportedPlatformError,
    ValidationError,
)


class TestPlatformValidation:
    """Test platform-specific checks."""

    @patch("azlin.modules.local_smb_mount.platform.system")
    def test_check_platform_darwin_success(self, mock_system):
        """macOS platform should pass validation."""
        mock_system.return_value = "Darwin"
        # Should not raise
        LocalSMBMount._check_platform()

    @patch("azlin.modules.local_smb_mount.platform.system")
    def test_check_platform_linux_raises_error(self, mock_system):
        """Linux platform should raise error."""
        mock_system.return_value = "Linux"
        with pytest.raises(UnsupportedPlatformError, match="only supported on macOS"):
            LocalSMBMount._check_platform()

    @patch("azlin.modules.local_smb_mount.platform.system")
    def test_check_platform_windows_raises_error(self, mock_system):
        """Windows platform should raise error."""
        mock_system.return_value = "Windows"
        with pytest.raises(UnsupportedPlatformError, match="only supported on macOS"):
            LocalSMBMount._check_platform()


class TestStorageAccountValidation:
    """Test storage account name validation."""

    def test_valid_storage_account_names(self):
        """Valid storage account names should pass."""
        valid_names = [
            "abc",  # Minimum length
            "mystorageaccount",
            "storage123",
            "abc123xyz789012345678901",  # Maximum length (24 chars)
        ]
        for name in valid_names:
            # Should not raise
            LocalSMBMount._validate_storage_account(name)

    def test_empty_storage_account_raises_error(self):
        """Empty storage account name should raise error."""
        with pytest.raises(ValidationError, match="Invalid storage account name"):
            LocalSMBMount._validate_storage_account("")

    def test_too_short_storage_account_raises_error(self):
        """Storage account name shorter than 3 chars should raise error."""
        with pytest.raises(ValidationError, match="Invalid storage account name"):
            LocalSMBMount._validate_storage_account("ab")

    def test_too_long_storage_account_raises_error(self):
        """Storage account name longer than 24 chars should raise error."""
        with pytest.raises(ValidationError, match="Invalid storage account name"):
            LocalSMBMount._validate_storage_account("a" * 25)

    def test_uppercase_storage_account_raises_error(self):
        """Uppercase letters should be rejected."""
        with pytest.raises(ValidationError, match="Invalid storage account name"):
            LocalSMBMount._validate_storage_account("MyStorage")

    def test_special_chars_storage_account_raises_error(self):
        """Special characters should be rejected."""
        with pytest.raises(ValidationError, match="Invalid storage account name"):
            LocalSMBMount._validate_storage_account("my-storage")

    def test_command_injection_storage_account_raises_error(self):
        """Command injection attempts should be rejected."""
        malicious_names = [
            "storage;rm",
            "storage&&whoami",
            "storage|cat",
            "storage`whoami`",
            "storage$(whoami)",
        ]
        for name in malicious_names:
            with pytest.raises(ValidationError, match="Invalid storage account name"):
                LocalSMBMount._validate_storage_account(name)


class TestShareNameValidation:
    """Test share name validation."""

    def test_valid_share_names(self):
        """Valid share names should pass."""
        valid_names = [
            "abc",  # Minimum length
            "my-share",
            "share-123",
            "a" + "-" * 60 + "b",  # Maximum length (63 chars)
        ]
        for name in valid_names:
            # Should not raise
            LocalSMBMount._validate_share_name(name)

    def test_empty_share_name_raises_error(self):
        """Empty share name should raise error."""
        with pytest.raises(ValidationError, match="Invalid share name"):
            LocalSMBMount._validate_share_name("")

    def test_too_short_share_name_raises_error(self):
        """Share name shorter than 3 chars should raise error."""
        with pytest.raises(ValidationError, match="Invalid share name"):
            LocalSMBMount._validate_share_name("ab")

    def test_too_long_share_name_raises_error(self):
        """Share name longer than 63 chars should raise error."""
        with pytest.raises(ValidationError, match="Invalid share name"):
            LocalSMBMount._validate_share_name("a" * 64)

    def test_uppercase_share_name_raises_error(self):
        """Uppercase letters should be rejected."""
        with pytest.raises(ValidationError, match="Invalid share name"):
            LocalSMBMount._validate_share_name("My-Share")

    def test_start_with_hyphen_raises_error(self):
        """Share name starting with hyphen should be rejected."""
        with pytest.raises(ValidationError, match="Invalid share name"):
            LocalSMBMount._validate_share_name("-myshare")

    def test_end_with_hyphen_raises_error(self):
        """Share name ending with hyphen should be rejected."""
        with pytest.raises(ValidationError, match="Invalid share name"):
            LocalSMBMount._validate_share_name("myshare-")

    def test_special_chars_share_name_raises_error(self):
        """Special characters other than hyphen should be rejected."""
        with pytest.raises(ValidationError, match="Invalid share name"):
            LocalSMBMount._validate_share_name("my_share")


class TestMountPointValidation:
    """Test mount point validation and creation."""

    def test_validate_mount_point_exists(self, tmp_path):
        """Existing directory should pass validation."""
        # Should not raise
        LocalSMBMount._validate_mount_point(tmp_path)

    def test_validate_mount_point_creates_if_missing(self, tmp_path):
        """Non-existing mount point should be created."""
        mount_point = tmp_path / "new_mount"
        assert not mount_point.exists()

        LocalSMBMount._validate_mount_point(mount_point)

        assert mount_point.exists()
        assert mount_point.is_dir()

    def test_validate_mount_point_parent_not_exists_raises_error(self, tmp_path):
        """Mount point with non-existing parent should raise error."""
        mount_point = tmp_path / "nonexistent" / "mount"

        with pytest.raises(MountPointError, match="Parent directory does not exist"):
            LocalSMBMount._validate_mount_point(mount_point)

    def test_validate_mount_point_not_directory_raises_error(self, tmp_path):
        """Mount point that is a file should raise error."""
        mount_point = tmp_path / "file.txt"
        mount_point.write_text("test")

        with pytest.raises(MountPointError, match="not a directory"):
            LocalSMBMount._validate_mount_point(mount_point)

    def test_validate_mount_point_expands_user_path(self, tmp_path):
        """User paths (~/...) should be expanded."""
        with patch("pathlib.Path.expanduser") as mock_expanduser:
            mock_expanduser.return_value = tmp_path
            LocalSMBMount._validate_mount_point(Path("~/azure"))
            mock_expanduser.assert_called_once()


class TestBuildSMBURL:
    """Test SMB URL construction."""

    def test_build_smb_url_basic(self):
        """Basic SMB URL should be constructed correctly."""
        url = LocalSMBMount._build_smb_url("mystorageaccount", "myshare", "azureuser")

        assert url == "//azureuser@mystorageaccount.file.core.windows.net/myshare"

    def test_build_smb_url_different_username(self):
        """SMB URL with different username should be constructed correctly."""
        url = LocalSMBMount._build_smb_url("storage123", "share-name", "admin")

        assert url == "//admin@storage123.file.core.windows.net/share-name"


class TestMountOperation:
    """Test mount operation."""

    @patch("azlin.modules.local_smb_mount.platform.system")
    @patch("azlin.modules.local_smb_mount.subprocess.run")
    def test_mount_success(self, mock_run, mock_system, tmp_path):
        """Successful mount should return success result."""
        mock_system.return_value = "Darwin"
        mock_run.return_value = MagicMock(returncode=0, stderr=b"", stdout=b"")

        result = LocalSMBMount.mount(
            storage_account="mystorageaccount",
            share_name="myshare",
            storage_key="test-key-123",
            mount_point=tmp_path,
        )

        assert result.success is True
        assert result.mount_point == str(tmp_path)
        assert "mystorageaccount.file.core.windows.net" in result.smb_share
        assert result.errors is None

        # Verify subprocess called with correct arguments
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args.kwargs["input"] == b"test-key-123"
        assert "mount_smbfs" in call_args.args[0]

    @patch("azlin.modules.local_smb_mount.platform.system")
    @patch("azlin.modules.local_smb_mount.subprocess.run")
    def test_mount_failure_returns_error(self, mock_run, mock_system, tmp_path):
        """Failed mount should return error result."""
        mock_system.return_value = "Darwin"
        mock_run.return_value = MagicMock(
            returncode=1, stderr=b"mount error: connection refused", stdout=b""
        )

        result = LocalSMBMount.mount(
            storage_account="mystorageaccount",
            share_name="myshare",
            storage_key="test-key-123",
            mount_point=tmp_path,
        )

        assert result.success is False
        assert result.mount_point == str(tmp_path)
        assert result.errors is not None
        assert len(result.errors) > 0
        assert "mount error" in result.errors[0].lower()

    @patch("azlin.modules.local_smb_mount.platform.system")
    def test_mount_invalid_storage_account_raises_error(self, mock_system, tmp_path):
        """Mount with invalid storage account should raise error."""
        mock_system.return_value = "Darwin"

        with pytest.raises(ValidationError, match="Invalid storage account name"):
            LocalSMBMount.mount(
                storage_account="Invalid-Name",
                share_name="myshare",
                storage_key="test-key-123",
                mount_point=tmp_path,
            )

    @patch("azlin.modules.local_smb_mount.platform.system")
    def test_mount_invalid_share_name_raises_error(self, mock_system, tmp_path):
        """Mount with invalid share name should raise error."""
        mock_system.return_value = "Darwin"

        with pytest.raises(ValidationError, match="Invalid share name"):
            LocalSMBMount.mount(
                storage_account="mystorageaccount",
                share_name="-invalid",
                storage_key="test-key-123",
                mount_point=tmp_path,
            )

    @patch("azlin.modules.local_smb_mount.platform.system")
    def test_mount_empty_storage_key_raises_error(self, mock_system, tmp_path):
        """Mount with empty storage key should raise error."""
        mock_system.return_value = "Darwin"

        with pytest.raises(ValidationError, match="Storage key cannot be empty"):
            LocalSMBMount.mount(
                storage_account="mystorageaccount",
                share_name="myshare",
                storage_key="",
                mount_point=tmp_path,
            )

    @patch("azlin.modules.local_smb_mount.platform.system")
    def test_mount_uses_storage_account_as_default_username(self, mock_system, tmp_path):
        """Mount without username should use storage account name."""
        mock_system.return_value = "Darwin"

        with patch("azlin.modules.local_smb_mount.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr=b"", stdout=b"")

            result = LocalSMBMount.mount(
                storage_account="mystorageaccount",
                share_name="myshare",
                storage_key="test-key-123",
                mount_point=tmp_path,
            )

            assert "mystorageaccount@" in result.smb_share

    @patch("azlin.modules.local_smb_mount.platform.system")
    def test_mount_subprocess_exception_returns_error(self, mock_system, tmp_path):
        """Subprocess exception should return error result."""
        mock_system.return_value = "Darwin"

        with patch("azlin.modules.local_smb_mount.subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Subprocess failed")

            result = LocalSMBMount.mount(
                storage_account="mystorageaccount",
                share_name="myshare",
                storage_key="test-key-123",
                mount_point=tmp_path,
            )

            assert result.success is False
            assert result.errors is not None
            assert "Exception during mount" in result.errors[0]

    @patch("azlin.modules.local_smb_mount.platform.system")
    def test_mount_never_logs_storage_key(self, mock_system, tmp_path):
        """Storage key should never appear in logs."""
        mock_system.return_value = "Darwin"

        with patch("azlin.modules.local_smb_mount.subprocess.run") as mock_run:
            with patch("azlin.modules.local_smb_mount.logger") as mock_logger:
                mock_run.return_value = MagicMock(returncode=0, stderr=b"", stdout=b"")

                LocalSMBMount.mount(
                    storage_account="mystorageaccount",
                    share_name="myshare",
                    storage_key="SECRET-KEY-123",
                    mount_point=tmp_path,
                )

                # Check all log calls - none should contain the key
                for call in mock_logger.info.call_args_list + mock_logger.debug.call_args_list:
                    assert "SECRET-KEY-123" not in str(call)


class TestUnmountOperation:
    """Test unmount operation."""

    @patch("azlin.modules.local_smb_mount.platform.system")
    @patch("azlin.modules.local_smb_mount.subprocess.run")
    def test_unmount_success(self, mock_run, mock_system, tmp_path):
        """Successful unmount should return success result."""
        mock_system.return_value = "Darwin"

        # First call checks mount status (is mounted)
        # Second call performs unmount
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=f"//storage@host/share on {tmp_path} (smbfs)\n"),
            MagicMock(returncode=0, stderr="", stdout=""),
        ]

        result = LocalSMBMount.unmount(mount_point=tmp_path)

        assert result.success is True
        assert result.mount_point == str(tmp_path)
        assert result.was_mounted is True
        assert result.errors is None

    @patch("azlin.modules.local_smb_mount.platform.system")
    @patch("azlin.modules.local_smb_mount.subprocess.run")
    def test_unmount_not_mounted(self, mock_run, mock_system, tmp_path):
        """Unmounting non-mounted point should succeed with warning."""
        mock_system.return_value = "Darwin"

        # Mount check returns no matches
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        result = LocalSMBMount.unmount(mount_point=tmp_path)

        assert result.success is True
        assert result.mount_point == str(tmp_path)
        assert result.was_mounted is False
        assert result.errors is None

    @patch("azlin.modules.local_smb_mount.platform.system")
    @patch("azlin.modules.local_smb_mount.subprocess.run")
    def test_unmount_failure_returns_error(self, mock_run, mock_system, tmp_path):
        """Failed unmount should return error result."""
        mock_system.return_value = "Darwin"

        # First call checks mount status (is mounted)
        # Second call fails to unmount
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=f"//storage@host/share on {tmp_path} (smbfs)\n"),
            MagicMock(returncode=1, stderr="umount: device is busy"),
        ]

        result = LocalSMBMount.unmount(mount_point=tmp_path)

        assert result.success is False
        assert result.was_mounted is True
        assert result.errors is not None
        assert "umount: device is busy" in result.errors[0]

    @patch("azlin.modules.local_smb_mount.platform.system")
    @patch("azlin.modules.local_smb_mount.subprocess.run")
    def test_unmount_force_flag(self, mock_run, mock_system, tmp_path):
        """Force unmount should pass -f flag."""
        mock_system.return_value = "Darwin"

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=f"//storage@host/share on {tmp_path} (smbfs)\n"),
            MagicMock(returncode=0, stderr="", stdout=""),
        ]

        LocalSMBMount.unmount(mount_point=tmp_path, force=True)

        # Second call should be the unmount with -f flag
        unmount_call = mock_run.call_args_list[1]
        assert "-f" in unmount_call.args[0]

    @patch("azlin.modules.local_smb_mount.platform.system")
    def test_unmount_nonexistent_path_raises_error(self, mock_system, tmp_path):
        """Unmounting non-existent path should raise error."""
        mock_system.return_value = "Darwin"

        nonexistent = tmp_path / "nonexistent"

        with pytest.raises(ValidationError, match="does not exist"):
            LocalSMBMount.unmount(mount_point=nonexistent)

    @patch("azlin.modules.local_smb_mount.platform.system")
    def test_unmount_file_path_raises_error(self, mock_system, tmp_path):
        """Unmounting a file path should raise error."""
        mock_system.return_value = "Darwin"

        file_path = tmp_path / "file.txt"
        file_path.write_text("test")

        with pytest.raises(ValidationError, match="not a directory"):
            LocalSMBMount.unmount(mount_point=file_path)


class TestMountStatusCheck:
    """Test mount status checking."""

    @patch("azlin.modules.local_smb_mount.subprocess.run")
    def test_is_mounted_returns_true_when_mounted(self, mock_run, tmp_path):
        """Mount check should return True for mounted path."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout=f"//storage@host/share on {tmp_path} (smbfs, nodev, nosuid)\n"
        )

        result = LocalSMBMount._is_mounted(tmp_path)

        assert result is True

    @patch("azlin.modules.local_smb_mount.subprocess.run")
    def test_is_mounted_returns_false_when_not_mounted(self, mock_run, tmp_path):
        """Mount check should return False for non-mounted path."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        result = LocalSMBMount._is_mounted(tmp_path)

        assert result is False

    @patch("azlin.modules.local_smb_mount.subprocess.run")
    def test_is_mounted_handles_exception(self, mock_run, tmp_path):
        """Mount check should handle exceptions gracefully."""
        mock_run.side_effect = Exception("Command failed")

        result = LocalSMBMount._is_mounted(tmp_path)

        assert result is False


class TestGetMountInfo:
    """Test getting mount information."""

    @patch("azlin.modules.local_smb_mount.platform.system")
    @patch("azlin.modules.local_smb_mount.subprocess.run")
    def test_get_mount_info_mounted(self, mock_run, mock_system, tmp_path):
        """Mount info should return details for mounted path."""
        mock_system.return_value = "Darwin"
        smb_url = "//user@storage.file.core.windows.net/share"
        mock_run.return_value = MagicMock(returncode=0, stdout=f"{smb_url} on {tmp_path} (smbfs)\n")

        info = LocalSMBMount.get_mount_info(tmp_path)

        assert info.mount_point == str(tmp_path)
        assert info.is_mounted is True
        assert info.smb_share == smb_url

    @patch("azlin.modules.local_smb_mount.platform.system")
    @patch("azlin.modules.local_smb_mount.subprocess.run")
    def test_get_mount_info_not_mounted(self, mock_run, mock_system, tmp_path):
        """Mount info should return not mounted for unmounted path."""
        mock_system.return_value = "Darwin"
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        info = LocalSMBMount.get_mount_info(tmp_path)

        assert info.mount_point == str(tmp_path)
        assert info.is_mounted is False
        assert info.smb_share == ""


class TestDataModels:
    """Test data model classes."""

    def test_mount_result_success(self):
        """MountResult should construct correctly for success."""
        result = MountResult(success=True, mount_point="/mnt/test", smb_share="//user@host/share")

        assert result.success is True
        assert result.mount_point == "/mnt/test"
        assert result.smb_share == "//user@host/share"
        assert result.errors is None

    def test_mount_result_failure(self):
        """MountResult should construct correctly for failure."""
        result = MountResult(
            success=False,
            mount_point="/mnt/test",
            smb_share="//user@host/share",
            errors=["Connection refused"],
        )

        assert result.success is False
        assert result.errors == ["Connection refused"]

    def test_unmount_result_success(self):
        """UnmountResult should construct correctly for success."""
        result = UnmountResult(success=True, mount_point="/mnt/test", was_mounted=True)

        assert result.success is True
        assert result.mount_point == "/mnt/test"
        assert result.was_mounted is True
        assert result.errors is None

    def test_mount_info(self):
        """MountInfo should construct correctly."""
        info = MountInfo(mount_point="/mnt/test", smb_share="//user@host/share", is_mounted=True)

        assert info.mount_point == "/mnt/test"
        assert info.smb_share == "//user@host/share"
        assert info.is_mounted is True


class TestSecurityConsiderations:
    """Test security-focused aspects."""

    @patch("azlin.modules.local_smb_mount.platform.system")
    @patch("azlin.modules.local_smb_mount.subprocess.run")
    def test_password_passed_via_stdin_not_command_line(self, mock_run, mock_system, tmp_path):
        """Storage key must be passed via stdin, never on command line."""
        mock_system.return_value = "Darwin"
        mock_run.return_value = MagicMock(returncode=0, stderr=b"", stdout=b"")

        storage_key = "SECRET-KEY-123"
        LocalSMBMount.mount(
            storage_account="mystorageaccount",
            share_name="myshare",
            storage_key=storage_key,
            mount_point=tmp_path,
        )

        # Check subprocess call - key should be in input, not in command args
        call_args = mock_run.call_args
        cmd_list = call_args.args[0]

        # Key should NOT appear in command arguments
        for arg in cmd_list:
            assert storage_key not in str(arg)

        # Key SHOULD be passed via stdin
        assert call_args.kwargs["input"] == storage_key.encode()

    @patch("azlin.modules.local_smb_mount.platform.system")
    def test_path_validation_prevents_injection(self, mock_system, tmp_path):
        """Path validation should prevent injection attacks."""
        mock_system.return_value = "Darwin"

        # These should be caught by validation before any subprocess calls
        malicious_accounts = [
            "storage;whoami",
            "storage&&rm",
            "storage|cat",
        ]

        for account in malicious_accounts:
            with pytest.raises(ValidationError):
                LocalSMBMount.mount(
                    storage_account=account,
                    share_name="myshare",
                    storage_key="key",
                    mount_point=tmp_path,
                )


class TestExceptionHierarchy:
    """Test exception class hierarchy."""

    def test_exception_inheritance(self):
        """All exceptions should inherit from LocalSMBMountError."""
        assert issubclass(UnsupportedPlatformError, LocalSMBMountError)
        assert issubclass(ValidationError, LocalSMBMountError)
        assert issubclass(MountPointError, LocalSMBMountError)

    def test_base_exception_is_exception(self):
        """Base exception should inherit from Exception."""
        assert issubclass(LocalSMBMountError, Exception)
