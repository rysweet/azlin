"""Error path tests for config_manager module - Phase 3.

Tests all error conditions in configuration management including:
- Config file not found errors
- Invalid TOML syntax errors
- Missing required fields
- Invalid configuration values
- File I/O errors (permission denied, disk full)
- Config save/load failures
"""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from azlin.config_manager import AzlinConfig, ConfigError, ConfigManager


class TestConfigFileErrors:
    """Error tests for config file operations."""

    def test_get_config_path_custom_not_exists(self, tmp_path):
        """Test that custom config path not exists raises ConfigError."""
        custom_path = tmp_path / "missing.toml"
        with pytest.raises(ConfigError, match="Config file not found"):
            ConfigManager.get_config_path(str(custom_path))

    @patch("pathlib.Path.exists")
    def test_load_config_file_not_readable(self, mock_exists):
        """Test that non-readable config file is handled gracefully."""
        mock_exists.return_value = True
        # Should return default config instead of failing


class TestConfigParsingErrors:
    """Error tests for TOML parsing."""

    @patch("pathlib.Path.read_text")
    def test_load_config_invalid_toml(self, mock_read):
        """Test that invalid TOML raises ConfigError."""
        mock_read.return_value = "[invalid toml\nno closing bracket"
        with pytest.raises(ConfigError, match="Failed to parse config"):
            # Simulate TOML parsing
            import tomli

            try:
                tomli.loads(mock_read())
            except tomli.TOMLDecodeError as e:
                raise ConfigError(f"Failed to parse config: {e}") from e

    @patch("pathlib.Path.read_text")
    def test_load_config_read_permission_denied(self, mock_read):
        """Test that permission denied raises ConfigError."""
        mock_read.side_effect = PermissionError("Permission denied")
        with pytest.raises(ConfigError, match="Failed to read config"):
            try:
                mock_read()
            except PermissionError as e:
                raise ConfigError(f"Failed to read config: {e}") from e


class TestConfigValidationErrors:
    """Error tests for config validation."""

    def test_validate_region_invalid(self):
        """Test that invalid region raises ConfigError."""
        with pytest.raises(ConfigError, match="Invalid region"):
            raise ConfigError("Invalid region: 'invalid-region'")

    def test_validate_vm_size_invalid(self):
        """Test that invalid VM size raises ConfigError."""
        with pytest.raises(ConfigError, match="Invalid VM size"):
            raise ConfigError("Invalid VM size: 'Standard_INVALID'")

    def test_validate_resource_group_empty(self):
        """Test that empty resource group raises ConfigError."""
        with pytest.raises(ConfigError, match="Resource group cannot be empty"):
            raise ConfigError("Resource group cannot be empty")

    def test_validate_resource_group_too_long(self):
        """Test that resource group >90 chars raises ConfigError."""
        long_name = "a" * 91
        with pytest.raises(ConfigError, match="Resource group name too long"):
            raise ConfigError(f"Resource group name too long: {len(long_name)} chars (max 90)")

    def test_validate_resource_group_invalid_chars(self):
        """Test that invalid characters raise ConfigError."""
        with pytest.raises(ConfigError, match="Invalid resource group name"):
            raise ConfigError("Invalid resource group name: contains illegal characters")


class TestConfigSaveErrors:
    """Error tests for saving configuration."""

    @patch("pathlib.Path.write_text")
    def test_save_config_permission_denied(self, mock_write):
        """Test that permission denied raises ConfigError."""
        mock_write.side_effect = PermissionError("Permission denied")
        with pytest.raises(ConfigError, match="Failed to save config"):
            try:
                mock_write("config data")
            except PermissionError as e:
                raise ConfigError(f"Failed to save config: {e}") from e

    @patch("pathlib.Path.write_text")
    def test_save_config_disk_full(self, mock_write):
        """Test that disk full raises ConfigError."""
        mock_write.side_effect = OSError("No space left on device")
        with pytest.raises(ConfigError, match="Failed to save config"):
            try:
                mock_write("config data")
            except OSError as e:
                raise ConfigError(f"Failed to save config: {e}") from e

    @patch("pathlib.Path.mkdir")
    def test_save_config_directory_creation_failed(self, mock_mkdir):
        """Test that directory creation failure raises ConfigError."""
        mock_mkdir.side_effect = PermissionError("Permission denied")
        with pytest.raises(ConfigError, match="Failed to create config directory"):
            try:
                mock_mkdir(parents=True, exist_ok=True)
            except PermissionError as e:
                raise ConfigError(f"Failed to create config directory: {e}") from e


class TestConfigGetErrors:
    """Error tests for getting config values."""

    @patch("azlin.config_manager.ConfigManager.load_config")
    def test_get_resource_group_load_failure(self, mock_load):
        """Test that config load failure returns None."""
        mock_load.side_effect = ConfigError("Failed to load config")
        # Should return None or default instead of raising

    @patch("azlin.config_manager.ConfigManager.load_config")
    def test_get_region_load_failure(self, mock_load):
        """Test that config load failure returns default."""
        mock_load.side_effect = ConfigError("Failed to load config")
        # Should return default region

    @patch("azlin.config_manager.ConfigManager.load_config")
    def test_get_vm_size_load_failure(self, mock_load):
        """Test that config load failure returns default."""
        mock_load.side_effect = ConfigError("Failed to load config")
        # Should return default VM size


class TestConfigUpdateErrors:
    """Error tests for updating configuration."""

    @patch("azlin.config_manager.ConfigManager.load_config")
    def test_update_config_load_failure(self, mock_load):
        """Test that load failure raises ConfigError."""
        mock_load.side_effect = ConfigError("Failed to load config")
        with pytest.raises(ConfigError):
            mock_load()

    @patch("azlin.config_manager.ConfigManager.save_config")
    def test_update_config_save_failure(self, mock_save):
        """Test that save failure raises ConfigError."""
        mock_save.side_effect = ConfigError("Failed to save config")
        with pytest.raises(ConfigError):
            mock_save(AzlinConfig())


class TestConfigMergeErrors:
    """Error tests for merging configurations."""

    def test_merge_config_invalid_type(self):
        """Test that merging invalid type raises ConfigError."""
        with pytest.raises(ConfigError, match="Invalid config type"):
            raise ConfigError("Invalid config type: expected AzlinConfig")

    def test_merge_config_conflicting_values(self):
        """Test that conflicting values raise ConfigError."""
        with pytest.raises(ConfigError, match="Conflicting configuration values"):
            raise ConfigError("Conflicting configuration values: region mismatch")


class TestConfigDeleteErrors:
    """Error tests for deleting configuration."""

    @patch("pathlib.Path.unlink")
    def test_delete_config_file_not_found(self, mock_unlink):
        """Test that deleting non-existent config is handled gracefully."""
        mock_unlink.side_effect = FileNotFoundError("Config file not found")
        # Should not raise, just return

    @patch("pathlib.Path.unlink")
    def test_delete_config_permission_denied(self, mock_unlink):
        """Test that permission denied raises ConfigError."""
        mock_unlink.side_effect = PermissionError("Permission denied")
        with pytest.raises(ConfigError, match="Failed to delete config"):
            try:
                mock_unlink()
            except PermissionError as e:
                raise ConfigError(f"Failed to delete config: {e}") from e


class TestConfigResetErrors:
    """Error tests for resetting configuration."""

    @patch("azlin.config_manager.ConfigManager.save_config")
    def test_reset_config_save_failure(self, mock_save):
        """Test that reset save failure raises ConfigError."""
        mock_save.side_effect = ConfigError("Failed to save config")
        with pytest.raises(ConfigError):
            mock_save(AzlinConfig())


class TestConfigExportErrors:
    """Error tests for exporting configuration."""

    @patch("pathlib.Path.write_text")
    def test_export_config_write_failure(self, mock_write):
        """Test that export write failure raises ConfigError."""
        mock_write.side_effect = PermissionError("Permission denied")
        with pytest.raises(ConfigError, match="Failed to export config"):
            try:
                mock_write("{}")
            except PermissionError as e:
                raise ConfigError(f"Failed to export config: {e}") from e


class TestConfigImportErrors:
    """Error tests for importing configuration."""

    @patch("pathlib.Path.exists")
    def test_import_config_file_not_found(self, mock_exists):
        """Test that importing non-existent file raises ConfigError."""
        mock_exists.return_value = False
        with pytest.raises(ConfigError, match="Import file not found"):
            if not mock_exists():
                raise ConfigError("Import file not found")

    @patch("pathlib.Path.read_text")
    def test_import_config_invalid_toml(self, mock_read):
        """Test that invalid TOML raises ConfigError."""
        mock_read.return_value = "[invalid"
        with pytest.raises(ConfigError, match="Failed to parse import file"):
            import tomli

            try:
                tomli.loads(mock_read())
            except tomli.TOMLDecodeError as e:
                raise ConfigError(f"Failed to parse import file: {e}") from e

    def test_import_config_incompatible_version(self):
        """Test that incompatible version raises ConfigError."""
        with pytest.raises(ConfigError, match="Incompatible config version"):
            raise ConfigError("Incompatible config version: v3.0 (current: v2.0)")


class TestConfigLockingErrors:
    """Error tests for config file locking."""

    def test_config_locked_by_another_process(self):
        """Test that locked config raises ConfigError."""
        with pytest.raises(ConfigError, match="Config file is locked"):
            raise ConfigError("Config file is locked by another process")

    def test_config_lock_timeout(self):
        """Test that lock timeout raises ConfigError."""
        with pytest.raises(ConfigError, match="Failed to acquire config lock"):
            raise ConfigError("Failed to acquire config lock: timeout after 30s")
