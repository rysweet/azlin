"""Unit tests for platform-specific notification command defaults (Issue #283)."""

from unittest.mock import patch

from azlin.config_manager import AzlinConfig, ConfigManager, get_default_notification_command


class TestDefaultNotificationCommand:
    """Tests for get_default_notification_command() function."""

    def test_default_for_macos(self):
        """Test default notification command for macOS (darwin)."""
        result = get_default_notification_command("darwin")
        assert result == 'osascript -e \'display notification "{}" with title "Azlin"\''

    def test_default_for_macos_alias(self):
        """Test default notification command for macOS (macos alias)."""
        result = get_default_notification_command("macos")
        assert result == 'osascript -e \'display notification "{}" with title "Azlin"\''

    def test_default_for_linux(self):
        """Test default notification command for Linux."""
        result = get_default_notification_command("linux")
        assert result == "notify-send 'Azlin' '{}'"

    def test_default_for_wsl(self):
        """Test default notification command for WSL."""
        result = get_default_notification_command("wsl")
        assert result == "powershell.exe -Command \"New-BurntToastNotification -Text '{}'\""

    def test_default_for_windows(self):
        """Test default notification command for Windows."""
        result = get_default_notification_command("windows")
        assert result == "powershell -Command \"New-BurntToastNotification -Text '{}'\""

    def test_default_for_unknown_platform(self):
        """Test fallback for unknown platform."""
        result = get_default_notification_command("unknown")
        assert result == "echo 'Notification: {}'"

    def test_auto_detect_platform_darwin(self):
        """Test auto-detection of macOS platform."""
        with patch(
            "azlin.modules.prerequisites.PrerequisiteChecker.detect_platform", return_value="darwin"
        ):
            result = get_default_notification_command()
            assert result == 'osascript -e \'display notification "{}" with title "Azlin"\''

    def test_auto_detect_platform_linux(self):
        """Test auto-detection of Linux platform."""
        with patch(
            "azlin.modules.prerequisites.PrerequisiteChecker.detect_platform", return_value="linux"
        ):
            result = get_default_notification_command()
            assert result == "notify-send 'Azlin' '{}'"

    def test_auto_detect_platform_wsl(self):
        """Test auto-detection of WSL platform."""
        with patch(
            "azlin.modules.prerequisites.PrerequisiteChecker.detect_platform", return_value="wsl"
        ):
            result = get_default_notification_command()
            assert result == "powershell.exe -Command \"New-BurntToastNotification -Text '{}'\""

    def test_auto_detect_platform_windows(self):
        """Test auto-detection of Windows platform."""
        with patch(
            "azlin.modules.prerequisites.PrerequisiteChecker.detect_platform",
            return_value="windows",
        ):
            result = get_default_notification_command()
            assert result == "powershell -Command \"New-BurntToastNotification -Text '{}'\""

    def test_auto_detect_fallback_on_unknown(self):
        """Test auto-detection falls back for unknown platform."""
        with patch(
            "azlin.modules.prerequisites.PrerequisiteChecker.detect_platform",
            return_value="unknown",
        ):
            result = get_default_notification_command()
            assert result == "echo 'Notification: {}'"


class TestAzlinConfigDefaultNotification:
    """Tests for AzlinConfig dataclass with default notification command."""

    def test_new_config_gets_platform_default(self):
        """Test new config gets platform-appropriate default."""
        with patch(
            "azlin.modules.prerequisites.PrerequisiteChecker.detect_platform", return_value="darwin"
        ):
            config = AzlinConfig()
            assert (
                config.notification_command
                == 'osascript -e \'display notification "{}" with title "Azlin"\''
            )

    def test_new_config_linux_default(self):
        """Test new config on Linux gets Linux default."""
        with patch(
            "azlin.modules.prerequisites.PrerequisiteChecker.detect_platform", return_value="linux"
        ):
            config = AzlinConfig()
            assert config.notification_command == "notify-send 'Azlin' '{}'"

    def test_new_config_wsl_default(self):
        """Test new config on WSL gets WSL default."""
        with patch(
            "azlin.modules.prerequisites.PrerequisiteChecker.detect_platform", return_value="wsl"
        ):
            config = AzlinConfig()
            assert (
                config.notification_command
                == "powershell.exe -Command \"New-BurntToastNotification -Text '{}'\""
            )

    def test_new_config_windows_default(self):
        """Test new config on Windows gets Windows default."""
        with patch(
            "azlin.modules.prerequisites.PrerequisiteChecker.detect_platform",
            return_value="windows",
        ):
            config = AzlinConfig()
            assert (
                config.notification_command
                == "powershell -Command \"New-BurntToastNotification -Text '{}'\""
            )

    def test_existing_config_preserves_custom_command(self):
        """Test existing custom notification command is preserved."""
        config = AzlinConfig(notification_command="custom_notify")
        assert config.notification_command == "custom_notify"

    def test_existing_config_preserves_imessr(self):
        """Test backward compatibility - existing 'imessR' configs are preserved."""
        config = AzlinConfig(notification_command="imessR")
        assert config.notification_command == "imessR"


class TestConfigFromDictWithNotificationDefaults:
    """Tests for AzlinConfig.from_dict() with notification defaults."""

    def test_from_dict_missing_notification_command(self):
        """Test from_dict applies default when notification_command is missing."""
        with patch(
            "azlin.modules.prerequisites.PrerequisiteChecker.detect_platform", return_value="darwin"
        ):
            data = {
                "default_resource_group": "my-rg",
                "default_region": "westus2",
            }
            config = AzlinConfig.from_dict(data)
            assert (
                config.notification_command
                == 'osascript -e \'display notification "{}" with title "Azlin"\''
            )

    def test_from_dict_empty_notification_command(self):
        """Test from_dict applies default when notification_command is empty."""
        with patch(
            "azlin.modules.prerequisites.PrerequisiteChecker.detect_platform", return_value="linux"
        ):
            data = {
                "default_resource_group": "my-rg",
                "default_region": "westus2",
                "notification_command": "",
            }
            config = AzlinConfig.from_dict(data)
            assert config.notification_command == "notify-send 'Azlin' '{}'"

    def test_from_dict_preserves_imessr(self):
        """Test from_dict preserves existing 'imessR' config (backward compatibility)."""
        data = {
            "default_resource_group": "my-rg",
            "default_region": "westus2",
            "notification_command": "imessR",
        }
        config = AzlinConfig.from_dict(data)
        assert config.notification_command == "imessR"

    def test_from_dict_preserves_custom_command(self):
        """Test from_dict preserves custom notification commands."""
        custom_commands = [
            "custom_notify",
            "/usr/local/bin/my-notifier",
            "ntfy send",
            "telegram-send",
        ]

        for custom_cmd in custom_commands:
            data = {
                "default_resource_group": "my-rg",
                "default_region": "westus2",
                "notification_command": custom_cmd,
            }
            config = AzlinConfig.from_dict(data)
            assert config.notification_command == custom_cmd


class TestConfigLoadWithNotificationDefaults:
    """Tests for ConfigManager.load_config() with notification defaults."""

    def test_load_config_missing_file_gets_default(self, tmp_path):
        """Test loading non-existent config gets platform default."""
        config_file = tmp_path / "config.toml"

        with patch(
            "azlin.modules.prerequisites.PrerequisiteChecker.detect_platform", return_value="darwin"
        ):
            with patch.object(ConfigManager, "get_config_path", return_value=config_file):
                config = ConfigManager.load_config()
                assert (
                    config.notification_command
                    == 'osascript -e \'display notification "{}" with title "Azlin"\''
                )

    def test_load_config_without_notification_field(self, tmp_path):
        """Test loading config without notification_command field gets default."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('default_resource_group = "my-rg"\ndefault_region = "westus2"\n')

        with patch(
            "azlin.modules.prerequisites.PrerequisiteChecker.detect_platform", return_value="linux"
        ):
            with patch.object(ConfigManager, "DEFAULT_CONFIG_FILE", config_file):
                config = ConfigManager.load_config()
                assert config.notification_command == "notify-send 'Azlin' '{}'"

    def test_load_config_preserves_imessr(self, tmp_path):
        """Test loading config with 'imessR' preserves it (backward compatibility)."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'default_resource_group = "my-rg"\n'
            'default_region = "westus2"\n'
            'notification_command = "imessR"\n'
        )

        with patch.object(ConfigManager, "DEFAULT_CONFIG_FILE", config_file):
            config = ConfigManager.load_config()
            assert config.notification_command == "imessR"

    def test_load_config_preserves_custom_command(self, tmp_path):
        """Test loading config with custom command preserves it."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'default_resource_group = "my-rg"\n'
            'default_region = "westus2"\n'
            'notification_command = "custom_notify"\n'
        )

        with patch.object(ConfigManager, "DEFAULT_CONFIG_FILE", config_file):
            config = ConfigManager.load_config()
            assert config.notification_command == "custom_notify"


class TestConfigSavePreservesNotificationCommand:
    """Tests for ConfigManager.save_config() preserving notification commands."""

    def test_save_preserves_imessr(self, tmp_path):
        """Test saving config preserves 'imessR' command."""
        config_file = tmp_path / "config.toml"
        config = AzlinConfig(
            default_resource_group="my-rg",
            default_region="westus2",
            notification_command="imessR",
        )

        ConfigManager.save_config(config, str(config_file))

        # Load and verify
        loaded_config = ConfigManager.load_config(str(config_file))
        assert loaded_config.notification_command == "imessR"

    def test_save_preserves_custom_command(self, tmp_path):
        """Test saving config preserves custom notification commands."""
        config_file = tmp_path / "config.toml"
        config = AzlinConfig(
            default_resource_group="my-rg",
            default_region="westus2",
            notification_command="custom_notify",
        )

        ConfigManager.save_config(config, str(config_file))

        # Load and verify
        loaded_config = ConfigManager.load_config(str(config_file))
        assert loaded_config.notification_command == "custom_notify"

    def test_save_preserves_platform_default(self, tmp_path):
        """Test saving config preserves platform-specific default."""
        config_file = tmp_path / "config.toml"

        with patch(
            "azlin.modules.prerequisites.PrerequisiteChecker.detect_platform", return_value="darwin"
        ):
            config = AzlinConfig(
                default_resource_group="my-rg",
                default_region="westus2",
            )

            ConfigManager.save_config(config, str(config_file))

            # Load and verify
            loaded_config = ConfigManager.load_config(str(config_file))
            assert (
                loaded_config.notification_command
                == 'osascript -e \'display notification "{}" with title "Azlin"\''
            )


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing configs."""

    def test_existing_imessr_configs_not_modified(self, tmp_path):
        """Test existing 'imessR' configs are NOT automatically changed."""
        config_file = tmp_path / "config.toml"
        # Simulate existing config file with imessR
        config_file.write_text(
            'default_resource_group = "my-rg"\n'
            'default_region = "westus2"\n'
            'notification_command = "imessR"\n'
        )

        # Load config
        config = ConfigManager.load_config(str(config_file))
        assert config.notification_command == "imessR"

        # Save config back (simulating any update operation)
        ConfigManager.save_config(config, str(config_file))

        # Verify imessR is still preserved
        loaded_config = ConfigManager.load_config(str(config_file))
        assert loaded_config.notification_command == "imessR"

    def test_update_config_preserves_notification_command(self, tmp_path):
        """Test update_config preserves existing notification_command."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'default_resource_group = "my-rg"\n'
            'default_region = "westus2"\n'
            'notification_command = "imessR"\n'
        )

        # Update some other field
        updated_config = ConfigManager.update_config(
            str(config_file), default_vm_size="Standard_D4s_v3"
        )

        # Verify notification_command is unchanged
        assert updated_config.notification_command == "imessR"


class TestNotificationsModuleIntegration:
    """Tests for notifications.py integration with config defaults."""

    def test_notification_handler_uses_platform_default(self, tmp_path):
        """Test NotificationHandler uses platform-appropriate default."""
        from azlin.modules.notifications import NotificationHandler

        config_file = tmp_path / "config.toml"
        # Create config without notification_command
        config_file.write_text('default_resource_group = "my-rg"\n')

        with patch(
            "azlin.modules.prerequisites.PrerequisiteChecker.detect_platform", return_value="darwin"
        ):
            with patch.object(ConfigManager, "DEFAULT_CONFIG_FILE", config_file):
                cmd = NotificationHandler._get_notification_command()
                assert cmd == 'osascript -e \'display notification "{}" with title "Azlin"\''

    def test_notification_handler_preserves_custom_command(self, tmp_path):
        """Test NotificationHandler preserves custom notification command."""
        from azlin.modules.notifications import NotificationHandler

        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'default_resource_group = "my-rg"\nnotification_command = "custom_notify"\n'
        )

        with patch.object(ConfigManager, "DEFAULT_CONFIG_FILE", config_file):
            cmd = NotificationHandler._get_notification_command()
            assert cmd == "custom_notify"


class TestPlatformDetectionMapping:
    """Tests for platform name mapping consistency."""

    def test_platform_names_match_prerequisites(self):
        """Test platform names match PrerequisiteChecker.detect_platform() output."""
        # Verify the platform names we use match what PrerequisiteChecker returns
        expected_platforms = ["darwin", "linux", "wsl", "windows", "unknown"]

        for platform in expected_platforms:
            # Should not raise an exception
            result = get_default_notification_command(platform)
            assert result is not None
            assert isinstance(result, str)
            assert "{}" in result  # All commands should have placeholder

    def test_all_platforms_have_placeholder(self):
        """Test all platform commands include message placeholder."""
        platforms = ["darwin", "linux", "wsl", "windows", "unknown"]

        for platform in platforms:
            cmd = get_default_notification_command(platform)
            assert "{}" in cmd, f"Platform {platform} command missing placeholder: {cmd}"
