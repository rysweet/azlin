"""CLI tests for 'azlin storage mount local' command.

Tests the CLI interface for local SMB mounting on macOS including:
- Command syntax and help
- Option parsing and validation
- Integration with LocalSMBMount module
- Error handling and user feedback
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from azlin.cli import main
from azlin.modules.local_smb_mount import (
    MountInfo,
    MountResult,
    UnmountResult,
    UnsupportedPlatformError,
)
from azlin.modules.storage_key_manager import StorageKeys


class TestStorageMountLocalCommandHelp:
    """Test help and basic command structure."""

    def test_storage_mount_local_help(self):
        """Test 'azlin storage mount local --help' displays help."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "mount", "local", "--help"])

        assert result.exit_code == 0
        assert "mount" in result.output.lower()
        assert "--mount-point" in result.output

    def test_storage_mount_group_shows_local_subcommand(self):
        """Test 'azlin storage mount --help' shows local subcommand."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "mount", "--help"])

        assert result.exit_code == 0
        assert "local" in result.output.lower()


class TestStorageMountLocalCommandSyntax:
    """Test command syntax and option parsing."""

    @patch("azlin.commands.storage.ContextManager.ensure_subscription_active")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    @patch("azlin.commands.storage.VMManager.get_subscription_id")
    @patch("azlin.commands.storage.StorageManager.list_storage")
    @patch("azlin.commands.storage.StorageKeyManager.get_storage_keys")
    @patch("azlin.commands.storage.LocalSMBMount.mount")
    def test_mount_local_with_mount_point_option(
        self,
        mock_mount,
        mock_get_keys,
        mock_list_storage,
        mock_subscription,
        mock_load_config,
        mock_ensure_sub,
    ):
        """Test 'azlin storage mount local --mount-point ~/azure' syntax."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.default_resource_group = "azlin-rg"
        mock_config.default_nfs_storage = "mystorageaccount"
        mock_load_config.return_value = mock_config

        mock_subscription.return_value = "sub-123"

        mock_storage = MagicMock()
        mock_storage.name = "mystorageaccount"
        mock_storage.nfs_endpoint = "mystorageaccount.file.core.windows.net:/home"
        mock_list_storage.return_value = [mock_storage]

        mock_get_keys.return_value = StorageKeys(key1="key1", key2="key2")

        mock_mount.return_value = MountResult(
            success=True,
            mount_point="/tmp/azure",
            smb_share="//mystorageaccount@mystorageaccount.file.core.windows.net/home",
        )

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["storage", "mount", "local", "--mount-point", "~/azure"])

            # Should succeed with valid syntax
            assert result.exit_code == 0
            assert "mounted" in result.output.lower() or "success" in result.output.lower()

    def test_mount_local_missing_mount_point_fails(self):
        """Test 'azlin storage mount local' without --mount-point fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "mount", "local"])

        # Should fail - mount-point is required
        assert result.exit_code != 0
        assert "mount-point" in result.output.lower() or "required" in result.output.lower()

    @patch("azlin.commands.storage.ContextManager.ensure_subscription_active")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    @patch("azlin.commands.storage.VMManager.get_subscription_id")
    @patch("azlin.commands.storage.StorageManager.list_storage")
    @patch("azlin.commands.storage.StorageKeyManager.get_storage_keys")
    @patch("azlin.commands.storage.LocalSMBMount.mount")
    def test_mount_local_with_storage_option(
        self,
        mock_mount,
        mock_get_keys,
        mock_list_storage,
        mock_subscription,
        mock_load_config,
        mock_ensure_sub,
    ):
        """Test 'azlin storage mount local --mount-point ~/azure --storage myaccount' syntax."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.default_resource_group = "azlin-rg"
        mock_load_config.return_value = mock_config

        mock_subscription.return_value = "sub-123"

        mock_storage = MagicMock()
        mock_storage.name = "myaccount"
        mock_storage.nfs_endpoint = "myaccount.file.core.windows.net:/home"
        mock_list_storage.return_value = [mock_storage]

        mock_get_keys.return_value = StorageKeys(key1="key1", key2="key2")

        mock_mount.return_value = MountResult(
            success=True,
            mount_point="/tmp/azure",
            smb_share="//myaccount@myaccount.file.core.windows.net/home",
        )

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                main, ["storage", "mount", "local", "--mount-point", "~/azure", "--storage", "myaccount"]
            )

            # Should succeed
            assert result.exit_code == 0


class TestStorageMountLocalIntegration:
    """Test integration with LocalSMBMount module."""

    @patch("azlin.commands.storage.ContextManager.ensure_subscription_active")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    @patch("azlin.commands.storage.VMManager.get_subscription_id")
    @patch("azlin.commands.storage.StorageManager.list_storage")
    @patch("azlin.commands.storage.StorageKeyManager.get_storage_keys")
    @patch("azlin.commands.storage.LocalSMBMount.mount")
    def test_mount_local_calls_local_smb_mount(
        self,
        mock_mount,
        mock_get_keys,
        mock_list_storage,
        mock_subscription,
        mock_load_config,
        mock_ensure_sub,
    ):
        """Test command calls LocalSMBMount.mount with correct parameters."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.default_resource_group = "azlin-rg"
        mock_config.default_nfs_storage = "mystorageaccount"
        mock_load_config.return_value = mock_config

        mock_subscription.return_value = "sub-123"

        mock_storage = MagicMock()
        mock_storage.name = "mystorageaccount"
        mock_storage.nfs_endpoint = "mystorageaccount.file.core.windows.net:/home"
        mock_list_storage.return_value = [mock_storage]

        mock_get_keys.return_value = StorageKeys(key1="test-key-123", key2="key2")

        mock_mount.return_value = MountResult(
            success=True,
            mount_point="/tmp/azure",
            smb_share="//mystorageaccount@mystorageaccount.file.core.windows.net/home",
        )

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["storage", "mount", "local", "--mount-point", "~/azure"])

            # Verify LocalSMBMount.mount was called with correct params
            assert mock_mount.called
            call_kwargs = mock_mount.call_args.kwargs
            assert call_kwargs["storage_account"] == "mystorageaccount"
            assert call_kwargs["share_name"] == "home"
            assert call_kwargs["storage_key"] == "test-key-123"
            assert isinstance(call_kwargs["mount_point"], Path)

    @patch("azlin.commands.storage.ContextManager.ensure_subscription_active")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    @patch("azlin.commands.storage.VMManager.get_subscription_id")
    @patch("azlin.commands.storage.StorageManager.list_storage")
    @patch("azlin.commands.storage.StorageKeyManager.get_storage_keys")
    @patch("azlin.commands.storage.LocalSMBMount.mount")
    def test_mount_local_uses_storage_key_from_azure(
        self,
        mock_mount,
        mock_get_keys,
        mock_list_storage,
        mock_subscription,
        mock_load_config,
        mock_ensure_sub,
    ):
        """Test command retrieves storage key from Azure automatically."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.default_resource_group = "azlin-rg"
        mock_config.default_nfs_storage = "mystorageaccount"
        mock_load_config.return_value = mock_config

        mock_subscription.return_value = "sub-123"

        mock_storage = MagicMock()
        mock_storage.name = "mystorageaccount"
        mock_storage.nfs_endpoint = "mystorageaccount.file.core.windows.net:/home"
        mock_list_storage.return_value = [mock_storage]

        mock_get_keys.return_value = StorageKeys(key1="azure-key-abc123", key2="key2")

        mock_mount.return_value = MountResult(
            success=True,
            mount_point="/tmp/azure",
            smb_share="//mystorageaccount@mystorageaccount.file.core.windows.net/home",
        )

        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(main, ["storage", "mount", "local", "--mount-point", "~/azure"])

            # Verify storage key was retrieved from Azure
            assert mock_get_keys.called
            assert mock_get_keys.call_args.kwargs["storage_account_name"] == "mystorageaccount"
            assert mock_get_keys.call_args.kwargs["resource_group"] == "azlin-rg"

            # Verify the retrieved key was passed to mount
            assert mock_mount.call_args.kwargs["storage_key"] == "azure-key-abc123"


class TestStorageMountLocalErrorHandling:
    """Test error handling and user feedback."""

    @patch("azlin.commands.storage.ContextManager.ensure_subscription_active")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    def test_mount_local_no_config_fails_gracefully(self, mock_load_config, mock_ensure_sub):
        """Test command fails gracefully when config is missing."""
        from azlin.config_manager import ConfigError

        mock_load_config.side_effect = ConfigError("No config found")

        runner = CliRunner()
        result = runner.invoke(main, ["storage", "mount", "local", "--mount-point", "~/azure"])

        assert result.exit_code != 0
        assert "error" in result.output.lower()
        assert "config" in result.output.lower() or "azlin new" in result.output.lower()

    @patch("azlin.commands.storage.ContextManager.ensure_subscription_active")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    @patch("azlin.commands.storage.VMManager.get_subscription_id")
    @patch("azlin.commands.storage.StorageManager.list_storage")
    def test_mount_local_storage_not_found_fails_gracefully(
        self, mock_list_storage, mock_subscription, mock_load_config, mock_ensure_sub
    ):
        """Test command fails gracefully when storage account not found."""
        mock_config = MagicMock()
        mock_config.default_resource_group = "azlin-rg"
        mock_config.default_nfs_storage = "nonexistent"
        mock_load_config.return_value = mock_config

        mock_subscription.return_value = "sub-123"
        mock_list_storage.return_value = []  # No storage accounts

        runner = CliRunner()
        result = runner.invoke(main, ["storage", "mount", "local", "--mount-point", "~/azure"])

        assert result.exit_code != 0
        assert "error" in result.output.lower()
        assert "not found" in result.output.lower()

    @patch("azlin.commands.storage.ContextManager.ensure_subscription_active")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    @patch("azlin.commands.storage.VMManager.get_subscription_id")
    @patch("azlin.commands.storage.StorageManager.list_storage")
    @patch("azlin.commands.storage.StorageKeyManager.get_storage_keys")
    @patch("azlin.commands.storage.LocalSMBMount.mount")
    def test_mount_local_unsupported_platform_fails_gracefully(
        self,
        mock_mount,
        mock_get_keys,
        mock_list_storage,
        mock_subscription,
        mock_load_config,
        mock_ensure_sub,
    ):
        """Test command fails gracefully on unsupported platform."""
        mock_config = MagicMock()
        mock_config.default_resource_group = "azlin-rg"
        mock_config.default_nfs_storage = "mystorageaccount"
        mock_load_config.return_value = mock_config

        mock_subscription.return_value = "sub-123"

        mock_storage = MagicMock()
        mock_storage.name = "mystorageaccount"
        mock_storage.nfs_endpoint = "mystorageaccount.file.core.windows.net:/home"
        mock_list_storage.return_value = [mock_storage]

        mock_get_keys.return_value = StorageKeys(key1="key1", key2="key2")

        # Simulate platform error
        mock_mount.side_effect = UnsupportedPlatformError("Not macOS")

        runner = CliRunner()
        result = runner.invoke(main, ["storage", "mount", "local", "--mount-point", "~/azure"])

        assert result.exit_code != 0
        assert "error" in result.output.lower()
        assert "macos" in result.output.lower()

    @patch("azlin.commands.storage.ContextManager.ensure_subscription_active")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    @patch("azlin.commands.storage.VMManager.get_subscription_id")
    @patch("azlin.commands.storage.StorageManager.list_storage")
    @patch("azlin.commands.storage.StorageKeyManager.get_storage_keys")
    @patch("azlin.commands.storage.LocalSMBMount.mount")
    def test_mount_local_mount_failure_shows_errors(
        self,
        mock_mount,
        mock_get_keys,
        mock_list_storage,
        mock_subscription,
        mock_load_config,
        mock_ensure_sub,
    ):
        """Test command displays mount errors to user."""
        mock_config = MagicMock()
        mock_config.default_resource_group = "azlin-rg"
        mock_config.default_nfs_storage = "mystorageaccount"
        mock_load_config.return_value = mock_config

        mock_subscription.return_value = "sub-123"

        mock_storage = MagicMock()
        mock_storage.name = "mystorageaccount"
        mock_storage.nfs_endpoint = "mystorageaccount.file.core.windows.net:/home"
        mock_list_storage.return_value = [mock_storage]

        mock_get_keys.return_value = StorageKeys(key1="key1", key2="key2")

        # Simulate mount failure
        mock_mount.return_value = MountResult(
            success=False,
            mount_point="/tmp/azure",
            smb_share="//mystorageaccount@mystorageaccount.file.core.windows.net/home",
            errors=["Connection refused", "Network unreachable"],
        )

        runner = CliRunner()
        result = runner.invoke(main, ["storage", "mount", "local", "--mount-point", "~/azure"])

        assert result.exit_code != 0
        assert "error" in result.output.lower() or "failed" in result.output.lower()


class TestStorageUnmountLocalCommand:
    """Test 'azlin storage unmount local' command."""

    def test_unmount_local_help(self):
        """Test 'azlin storage unmount local --help' displays help."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "unmount-file", "local", "--help"])

        assert result.exit_code == 0
        assert "unmount" in result.output.lower()

    @patch("azlin.commands.storage.LocalSMBMount.get_mount_info")
    @patch("azlin.commands.storage.LocalSMBMount.unmount")
    def test_unmount_local_with_mount_point(self, mock_unmount, mock_get_info):
        """Test 'azlin storage unmount local --mount-point ~/azure' syntax."""
        mock_get_info.return_value = MountInfo(
            mount_point="/tmp/azure",
            smb_share="//storage@host/share",
            is_mounted=True,
        )

        mock_unmount.return_value = UnmountResult(
            success=True,
            mount_point="/tmp/azure",
            was_mounted=True,
        )

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                main, ["storage", "unmount-file", "local", "--mount-point", "~/azure"]
            )

            assert result.exit_code == 0
            assert "unmount" in result.output.lower()

    @patch("azlin.commands.storage.LocalSMBMount.get_mount_info")
    @patch("azlin.commands.storage.LocalSMBMount.unmount")
    def test_unmount_local_with_force_flag(self, mock_unmount, mock_get_info):
        """Test 'azlin storage unmount local --force' syntax."""
        mock_get_info.return_value = MountInfo(
            mount_point="/tmp/azure",
            smb_share="//storage@host/share",
            is_mounted=True,
        )

        mock_unmount.return_value = UnmountResult(
            success=True,
            mount_point="/tmp/azure",
            was_mounted=True,
        )

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                main, ["storage", "unmount-file", "local", "--mount-point", "~/azure", "--force"]
            )

            assert result.exit_code == 0
            # Verify force flag was passed
            assert mock_unmount.call_args.kwargs.get("force") is True

    @patch("azlin.commands.storage.LocalSMBMount.get_mount_info")
    @patch("azlin.commands.storage.LocalSMBMount.unmount")
    def test_unmount_local_not_mounted_succeeds(self, mock_unmount, mock_get_info):
        """Test unmounting non-mounted path succeeds gracefully."""
        mock_get_info.return_value = MountInfo(
            mount_point="/tmp/azure",
            smb_share="",
            is_mounted=False,
        )

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                main, ["storage", "unmount-file", "local", "--mount-point", "~/azure"]
            )

            assert result.exit_code == 0
            assert "not" in result.output.lower()
            assert "mounted" in result.output.lower()


class TestFinderIntegration:
    """Test Finder integration aspects."""

    @patch("azlin.commands.storage.ContextManager.ensure_subscription_active")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    @patch("azlin.commands.storage.VMManager.get_subscription_id")
    @patch("azlin.commands.storage.StorageManager.list_storage")
    @patch("azlin.commands.storage.StorageKeyManager.get_storage_keys")
    @patch("azlin.commands.storage.LocalSMBMount.mount")
    def test_mount_creates_finder_accessible_mount(
        self,
        mock_mount,
        mock_get_keys,
        mock_list_storage,
        mock_subscription,
        mock_load_config,
        mock_ensure_sub,
    ):
        """Test mounted share is accessible from Finder (via SMB)."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.default_resource_group = "azlin-rg"
        mock_config.default_nfs_storage = "mystorageaccount"
        mock_load_config.return_value = mock_config

        mock_subscription.return_value = "sub-123"

        mock_storage = MagicMock()
        mock_storage.name = "mystorageaccount"
        mock_storage.nfs_endpoint = "mystorageaccount.file.core.windows.net:/home"
        mock_list_storage.return_value = [mock_storage]

        mock_get_keys.return_value = StorageKeys(key1="key1", key2="key2")

        # SMB mount should create Finder-accessible mount
        mock_mount.return_value = MountResult(
            success=True,
            mount_point="/Volumes/azure",  # Standard macOS mount location
            smb_share="//mystorageaccount@mystorageaccount.file.core.windows.net/home",
        )

        runner = CliRunner()
        result = runner.invoke(main, ["storage", "mount", "local", "--mount-point", "~/azure"])

        # Verify mount was successful (Finder integration happens via mount_smbfs)
        assert result.exit_code == 0
        assert "mounted" in result.output.lower() or "success" in result.output.lower()


class TestAutomaticCredentials:
    """Test automatic credentials handling."""

    @patch("azlin.commands.storage.ContextManager.ensure_subscription_active")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    @patch("azlin.commands.storage.VMManager.get_subscription_id")
    @patch("azlin.commands.storage.StorageManager.list_storage")
    @patch("azlin.commands.storage.StorageKeyManager.get_storage_keys")
    @patch("azlin.commands.storage.LocalSMBMount.mount")
    def test_mount_retrieves_credentials_automatically(
        self,
        mock_mount,
        mock_get_keys,
        mock_list_storage,
        mock_subscription,
        mock_load_config,
        mock_ensure_sub,
    ):
        """Test credentials are retrieved automatically from Azure."""
        mock_config = MagicMock()
        mock_config.default_resource_group = "azlin-rg"
        mock_config.default_nfs_storage = "mystorageaccount"
        mock_load_config.return_value = mock_config

        mock_subscription.return_value = "sub-123"

        mock_storage = MagicMock()
        mock_storage.name = "mystorageaccount"
        mock_storage.nfs_endpoint = "mystorageaccount.file.core.windows.net:/home"
        mock_list_storage.return_value = [mock_storage]

        # Automatic credential retrieval
        mock_get_keys.return_value = StorageKeys(key1="auto-retrieved-key", key2="key2")

        mock_mount.return_value = MountResult(
            success=True,
            mount_point="/tmp/azure",
            smb_share="//mystorageaccount@mystorageaccount.file.core.windows.net/home",
        )

        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(main, ["storage", "mount", "local", "--mount-point", "~/azure"])

            # Verify credentials were retrieved automatically
            assert mock_get_keys.called

            # Verify retrieved credentials were used
            assert mock_mount.call_args.kwargs["storage_key"] == "auto-retrieved-key"

    @patch("azlin.commands.storage.ContextManager.ensure_subscription_active")
    @patch("azlin.commands.storage.ConfigManager.load_config")
    @patch("azlin.commands.storage.VMManager.get_subscription_id")
    @patch("azlin.commands.storage.StorageManager.list_storage")
    @patch("azlin.commands.storage.StorageKeyManager.get_storage_keys")
    def test_mount_no_manual_credentials_required(
        self, mock_get_keys, mock_list_storage, mock_subscription, mock_load_config, mock_ensure_sub
    ):
        """Test user never needs to provide credentials manually."""
        mock_config = MagicMock()
        mock_config.default_resource_group = "azlin-rg"
        mock_config.default_nfs_storage = "mystorageaccount"
        mock_load_config.return_value = mock_config

        mock_subscription.return_value = "sub-123"

        mock_storage = MagicMock()
        mock_storage.name = "mystorageaccount"
        mock_storage.nfs_endpoint = "mystorageaccount.file.core.windows.net:/home"
        mock_list_storage.return_value = [mock_storage]

        mock_get_keys.return_value = StorageKeys(key1="key1", key2="key2")

        runner = CliRunner()
        result = runner.invoke(main, ["storage", "mount", "local", "--help"])

        # Verify no password/key options in CLI
        assert "--password" not in result.output.lower()
        assert "--key" not in result.output.lower()
        assert "--credentials" not in result.output.lower()
