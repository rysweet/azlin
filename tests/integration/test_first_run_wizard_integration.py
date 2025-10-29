"""Integration tests for first-run configuration wizard (Issue #197).

These tests verify the complete end-to-end flow of the first-run wizard,
including interactions with Azure APIs, file system operations, and user input.

All tests should FAIL initially until the feature is fully implemented.
"""

import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from azlin.config_manager import AzlinConfig, ConfigError, ConfigManager


class TestWizardAzureIntegration:
    """Integration tests for wizard Azure API interactions (Issue #197).

    Tests wizard integration with Azure APIs for listing and creating resources.
    Tests will FAIL until feature is implemented.
    """

    def test_wizard_lists_existing_resource_groups(self, tmp_path):
        """Test wizard can list existing resource groups from Azure."""
        config_file = tmp_path / "config.toml"

        # Mock Azure resource groups
        mock_rgs = [
            {"name": "rg-prod", "location": "eastus"},
            {"name": "rg-dev", "location": "westus2"},
            {"name": "rg-staging", "location": "centralus"},
        ]

        with patch("azlin.config_manager.list_resource_groups", return_value=mock_rgs):
            # User selects option to view existing RGs
            with patch("builtins.input", side_effect=["2", "1", "", "", "y"]):  # View existing, select first
                result = ConfigManager.run_first_run_wizard(str(config_file))

        assert result["success"] is True
        assert result["config"]["default_resource_group"] == "rg-prod"

    def test_wizard_creates_new_resource_group_via_azure(self, tmp_path):
        """Test wizard can create new resource group via Azure API."""
        config_file = tmp_path / "config.toml"

        # Mock Azure resource group creation
        with patch("azlin.config_manager.create_resource_group", return_value={"name": "new-rg", "location": "westus2"}):
            with patch("builtins.input", side_effect=["new-rg", "westus2", "", "y"]):
                result = ConfigManager.run_first_run_wizard(str(config_file))

        assert result["success"] is True
        assert result["config"]["default_resource_group"] == "new-rg"

    def test_wizard_handles_azure_authentication_required(self, tmp_path):
        """Test wizard prompts for Azure authentication if needed."""
        config_file = tmp_path / "config.toml"

        # Mock Azure auth check
        with patch("azlin.config_manager.check_azure_auth", return_value=False):
            with patch("azlin.config_manager.prompt_azure_login") as mock_login:
                mock_login.return_value = True
                with patch("builtins.input", side_effect=["test-rg", "", "", "y"]):
                    result = ConfigManager.run_first_run_wizard(str(config_file))

        # Verify login was called
        mock_login.assert_called_once()
        assert result["success"] is True

    def test_wizard_handles_azure_subscription_selection(self, tmp_path):
        """Test wizard handles multiple Azure subscriptions."""
        config_file = tmp_path / "config.toml"

        # Mock multiple subscriptions
        mock_subscriptions = [
            {"id": "sub-1", "name": "Production"},
            {"id": "sub-2", "name": "Development"},
        ]

        with patch("azlin.config_manager.list_subscriptions", return_value=mock_subscriptions):
            with patch("builtins.input", side_effect=["1", "test-rg", "", "", "y"]):  # Select first subscription
                result = ConfigManager.run_first_run_wizard(str(config_file))

        assert result["success"] is True
        assert result["subscription_id"] == "sub-1"

    def test_wizard_verifies_resource_group_availability(self, tmp_path):
        """Test wizard verifies resource group name is available."""
        config_file = tmp_path / "config.toml"

        # Mock resource group already exists
        with patch("azlin.config_manager.check_resource_group_exists", side_effect=[True, False]):
            # First input: existing name (rejected), second: available name
            with patch("builtins.input", side_effect=["existing-rg", "new-rg", "", "", "y"]):
                result = ConfigManager.run_first_run_wizard(str(config_file))

        assert result["success"] is True
        assert result["config"]["default_resource_group"] == "new-rg"


class TestWizardFileSystemIntegration:
    """Integration tests for wizard file system operations (Issue #197).

    Tests wizard interactions with the file system for config storage.
    Tests will FAIL until feature is implemented.
    """

    def test_wizard_creates_config_directory(self, tmp_path, monkeypatch):
        """Test wizard creates .azlin directory if it doesn't exist."""
        # Set HOME to tmp_path
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        monkeypatch.setenv("HOME", str(home_dir))

        config_dir = home_dir / ".azlin"
        config_file = config_dir / "config.toml"

        # Directory doesn't exist initially
        assert not config_dir.exists()

        with patch("builtins.input", side_effect=["test-rg", "", "", "y"]):
            with patch.object(ConfigManager, "DEFAULT_CONFIG_DIR", config_dir):
                with patch.object(ConfigManager, "DEFAULT_CONFIG_FILE", config_file):
                    ConfigManager.run_first_run_wizard()

        # Verify directory was created
        assert config_dir.exists()
        assert config_dir.stat().st_mode & 0o777 == 0o700  # Secure permissions

    def test_wizard_writes_config_atomically(self, tmp_path):
        """Test wizard writes config file atomically (temp + rename)."""
        config_file = tmp_path / "config.toml"

        with patch("builtins.input", side_effect=["test-rg", "", "", "y"]):
            ConfigManager.run_first_run_wizard(str(config_file))

        # Verify no .tmp files left behind
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

        # Verify final config exists
        assert config_file.exists()

    def test_wizard_preserves_existing_config_values(self, tmp_path):
        """Test wizard preserves existing config values when updating."""
        config_file = tmp_path / "config.toml"

        # Create existing config with session names
        existing_config = AzlinConfig(
            default_resource_group="old-rg",
            session_names={"vm1": "prod", "vm2": "dev"},
        )
        ConfigManager.save_config(existing_config, str(config_file))

        # Run wizard to update resource group
        with patch("builtins.input", side_effect=["new-rg", "", "", "y"]):
            ConfigManager.run_first_run_wizard(str(config_file))

        # Verify session names preserved
        updated_config = ConfigManager.load_config(str(config_file))
        assert updated_config.default_resource_group == "new-rg"
        assert updated_config.session_names == {"vm1": "prod", "vm2": "dev"}

    def test_wizard_handles_concurrent_config_writes(self, tmp_path):
        """Test wizard handles concurrent writes gracefully."""
        config_file = tmp_path / "config.toml"

        # Simulate another process writing config
        def concurrent_write(*args, **kwargs):
            config_file.write_text('default_resource_group = "concurrent-rg"\n')
            return AzlinConfig(default_resource_group="concurrent-rg")

        with patch("azlin.config_manager.ConfigManager.load_config", side_effect=concurrent_write):
            with patch("builtins.input", side_effect=["test-rg", "", "", "y"]):
                # Wizard should handle the race condition
                result = ConfigManager.run_first_run_wizard(str(config_file))

        assert result["success"] is True

    def test_wizard_respects_file_permissions(self, tmp_path):
        """Test wizard creates config with secure permissions (0600)."""
        config_file = tmp_path / "config.toml"

        with patch("builtins.input", side_effect=["test-rg", "", "", "y"]):
            ConfigManager.run_first_run_wizard(str(config_file))

        # Verify file permissions are secure
        stat = config_file.stat()
        mode = stat.st_mode & 0o777
        assert mode == 0o600


class TestWizardUserInteractionFlow:
    """Integration tests for wizard user interaction flow (Issue #197).

    Tests complete user interaction scenarios from start to finish.
    Tests will FAIL until feature is implemented.
    """

    def test_wizard_happy_path_new_user(self, tmp_path):
        """Test complete happy path for new user with no existing config."""
        config_file = tmp_path / "config.toml"

        # Simulate new user accepting all defaults
        inputs = [
            "azlin-rg",  # Resource group name
            "",  # Accept default region (westus2)
            "",  # Accept default VM size (Standard_E16as_v5)
            "y",  # Confirm
        ]

        with patch("builtins.input", side_effect=inputs):
            result = ConfigManager.run_first_run_wizard(str(config_file))

        # Verify success
        assert result["success"] is True

        # Verify config file created
        assert config_file.exists()

        # Verify config contents
        config = ConfigManager.load_config(str(config_file))
        assert config.default_resource_group == "azlin-rg"
        assert config.default_region == "westus2"
        assert config.default_vm_size == "Standard_E16as_v5"

    def test_wizard_power_user_custom_values(self, tmp_path):
        """Test complete flow for power user with custom values."""
        config_file = tmp_path / "config.toml"

        # Simulate power user with specific requirements
        inputs = [
            "enterprise-rg",  # Custom resource group
            "eastus",  # Custom region
            "Standard_D32s_v3",  # Custom VM size
            "y",  # Confirm
        ]

        with patch("builtins.input", side_effect=inputs):
            result = ConfigManager.run_first_run_wizard(str(config_file))

        # Verify custom values saved
        config = ConfigManager.load_config(str(config_file))
        assert config.default_resource_group == "enterprise-rg"
        assert config.default_region == "eastus"
        assert config.default_vm_size == "Standard_D32s_v3"

    def test_wizard_user_changes_mind(self, tmp_path):
        """Test user can change their mind during wizard."""
        config_file = tmp_path / "config.toml"

        # User provides values but rejects at confirmation, then tries again
        first_attempt = [
            "first-rg",
            "westus",
            "",
            "n",  # Reject
        ]

        second_attempt = [
            "second-rg",
            "eastus",
            "",
            "y",  # Accept
        ]

        # First attempt - user declines
        with patch("builtins.input", side_effect=first_attempt):
            result = ConfigManager.run_first_run_wizard(str(config_file))

        assert result["success"] is False
        assert not config_file.exists()

        # Second attempt - user accepts
        with patch("builtins.input", side_effect=second_attempt):
            result = ConfigManager.run_first_run_wizard(str(config_file))

        assert result["success"] is True
        config = ConfigManager.load_config(str(config_file))
        assert config.default_resource_group == "second-rg"

    def test_wizard_handles_user_corrections(self, tmp_path):
        """Test wizard allows user to correct mistakes."""
        config_file = tmp_path / "config.toml"

        # User makes typo, wizard validates and prompts again
        inputs = [
            "invalid@rg!",  # Invalid characters
            "valid-rg",  # Corrected
            "invalid-region-123",  # Invalid region
            "westus2",  # Corrected
            "",  # Default VM size
            "y",  # Confirm
        ]

        with patch("builtins.input", side_effect=inputs):
            result = ConfigManager.run_first_run_wizard(str(config_file))

        assert result["success"] is True
        config = ConfigManager.load_config(str(config_file))
        assert config.default_resource_group == "valid-rg"
        assert config.default_region == "westus2"

    def test_wizard_displays_progress_messages(self, tmp_path, capsys):
        """Test wizard displays helpful progress messages."""
        config_file = tmp_path / "config.toml"

        with patch("builtins.input", side_effect=["test-rg", "", "", "y"]):
            ConfigManager.run_first_run_wizard(str(config_file))

        captured = capsys.readouterr()

        # Verify key messages are displayed
        assert "azlin" in captured.out.lower()
        assert "resource group" in captured.out.lower()
        assert "region" in captured.out.lower()
        assert "vm size" in captured.out.lower() or "vm" in captured.out.lower()


class TestWizardEdgeCases:
    """Integration tests for wizard edge cases (Issue #197).

    Tests unusual but valid scenarios and boundary conditions.
    Tests will FAIL until feature is implemented.
    """

    def test_wizard_with_very_long_resource_group_name(self, tmp_path):
        """Test wizard handles maximum length resource group names."""
        config_file = tmp_path / "config.toml"

        # Azure allows up to 90 characters
        max_length_name = "a" * 90

        with patch("builtins.input", side_effect=[max_length_name, "", "", "y"]):
            result = ConfigManager.run_first_run_wizard(str(config_file))

        assert result["success"] is True
        config = ConfigManager.load_config(str(config_file))
        assert config.default_resource_group == max_length_name

    def test_wizard_with_unicode_in_resource_group(self, tmp_path):
        """Test wizard handles unicode characters in resource group names."""
        config_file = tmp_path / "config.toml"

        # Azure resource groups should be ASCII only
        unicode_name = "rg-with-emoji-😀"

        with patch("builtins.input", side_effect=[unicode_name, "valid-rg", "", "", "y"]):
            result = ConfigManager.run_first_run_wizard(str(config_file))

        # Should reject unicode and accept valid name
        assert result["success"] is True
        config = ConfigManager.load_config(str(config_file))
        assert config.default_resource_group == "valid-rg"

    def test_wizard_when_home_dir_is_readonly(self, tmp_path):
        """Test wizard handles readonly home directory."""
        config_dir = tmp_path / ".azlin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"

        # Make directory readonly
        config_dir.chmod(0o555)

        try:
            with patch("builtins.input", side_effect=["test-rg", "", "", "y"]):
                with pytest.raises(ConfigError, match="Failed to save"):
                    with patch.object(ConfigManager, "DEFAULT_CONFIG_DIR", config_dir):
                        ConfigManager.run_first_run_wizard()
        finally:
            # Restore permissions for cleanup
            config_dir.chmod(0o755)

    def test_wizard_with_existing_partial_config(self, tmp_path):
        """Test wizard handles partial existing configuration."""
        config_file = tmp_path / "config.toml"

        # Create partial config (missing resource group)
        config_file.write_text('default_region = "centralus"\n')

        # Wizard should detect missing resource group
        assert ConfigManager.needs_first_run_setup(str(config_file)) is True

        with patch("builtins.input", side_effect=["new-rg", "", "", "y"]):
            result = ConfigManager.run_first_run_wizard(str(config_file))

        # Should add resource group, keep existing region
        config = ConfigManager.load_config(str(config_file))
        assert config.default_resource_group == "new-rg"
        assert config.default_region == "centralus"  # Preserved

    def test_wizard_recovery_after_crash(self, tmp_path):
        """Test wizard can recover if interrupted mid-save."""
        config_file = tmp_path / "config.toml"

        # Simulate crash by creating temp file
        temp_file = config_file.with_suffix(".tmp")
        temp_file.write_text("partial data")

        # Wizard should clean up and proceed
        with patch("builtins.input", side_effect=["test-rg", "", "", "y"]):
            result = ConfigManager.run_first_run_wizard(str(config_file))

        assert result["success"] is True
        assert not temp_file.exists()  # Temp file cleaned up
        assert config_file.exists()  # Final config exists


class TestWizardCLIIntegration:
    """Integration tests for wizard CLI integration (Issue #197).

    Tests how wizard integrates with CLI commands.
    Tests will FAIL until feature is implemented.
    """

    def test_wizard_triggered_on_first_azlin_command(self, tmp_path):
        """Test wizard is triggered when running azlin command without config."""
        config_file = tmp_path / "config.toml"

        # Mock CLI command execution
        with patch("azlin.config_manager.ConfigManager.needs_first_run_setup", return_value=True):
            with patch("azlin.config_manager.ConfigManager.run_first_run_wizard") as mock_wizard:
                mock_wizard.return_value = {"success": True, "config": {"default_resource_group": "test-rg"}}

                # Simulate CLI command
                result = ConfigManager.get_resource_group(None, str(config_file))

                # Wizard should have been called
                mock_wizard.assert_called_once()

    def test_wizard_can_be_skipped_with_cli_flag(self, tmp_path):
        """Test wizard can be skipped with --no-wizard flag."""
        config_file = tmp_path / "config.toml"

        # Mock CLI with --no-wizard flag
        with patch("builtins.input", side_effect=["test-rg", "", "", "y"]):
            result = ConfigManager.run_first_run_wizard(str(config_file), skip=True)

        assert result["skipped"] is True
        assert not config_file.exists()

    def test_wizard_respects_noninteractive_mode(self, tmp_path):
        """Test wizard respects non-interactive mode (CI/CD)."""
        config_file = tmp_path / "config.toml"

        # Set non-interactive environment
        with patch.dict(os.environ, {"AZLIN_NONINTERACTIVE": "1"}):
            result = ConfigManager.run_first_run_wizard(str(config_file))

        # Should skip wizard in non-interactive mode
        assert result["skipped"] is True or result["success"] is False

    def test_wizard_provides_config_via_environment(self, tmp_path, monkeypatch):
        """Test wizard can use environment variables for non-interactive setup."""
        config_file = tmp_path / "config.toml"

        # Set config via environment
        monkeypatch.setenv("AZLIN_DEFAULT_RESOURCE_GROUP", "env-rg")
        monkeypatch.setenv("AZLIN_DEFAULT_REGION", "westus2")
        monkeypatch.setenv("AZLIN_DEFAULT_VM_SIZE", "Standard_D4s_v3")

        result = ConfigManager.run_first_run_wizard(str(config_file), use_env=True)

        assert result["success"] is True
        config = ConfigManager.load_config(str(config_file))
        assert config.default_resource_group == "env-rg"
        assert config.default_region == "westus2"
        assert config.default_vm_size == "Standard_D4s_v3"
