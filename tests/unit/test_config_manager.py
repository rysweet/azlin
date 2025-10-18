"""Unit tests for config_manager module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from azlin.config_manager import AzlinConfig, ConfigError, ConfigManager


class TestAzlinConfig:
    """Tests for AzlinConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = AzlinConfig()
        assert config.default_resource_group is None
        assert config.default_region == "westus2"
        assert config.default_vm_size == "Standard_B2s"
        assert config.last_vm_name is None

    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = AzlinConfig(
            default_resource_group="my-rg",
            default_region="westus",
            default_vm_size="Standard_D4s_v3",
            last_vm_name="test-vm",
        )
        data = config.to_dict()
        assert data["default_resource_group"] == "my-rg"
        assert data["default_region"] == "westus"
        assert data["default_vm_size"] == "Standard_D4s_v3"
        assert data["last_vm_name"] == "test-vm"

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "default_resource_group": "my-rg",
            "default_region": "westus",
            "default_vm_size": "Standard_D4s_v3",
            "last_vm_name": "test-vm",
        }
        config = AzlinConfig.from_dict(data)
        assert config.default_resource_group == "my-rg"
        assert config.default_region == "westus"
        assert config.default_vm_size == "Standard_D4s_v3"
        assert config.last_vm_name == "test-vm"

    def test_from_dict_partial(self):
        """Test creation from partial dictionary."""
        data = {"default_resource_group": "my-rg"}
        config = AzlinConfig.from_dict(data)
        assert config.default_resource_group == "my-rg"
        assert config.default_region == "westus2"  # Default
        assert config.default_vm_size == "Standard_B2s"  # Default


class TestConfigManager:
    """Tests for ConfigManager class."""

    def test_get_config_path_default(self):
        """Test default config path."""
        path = ConfigManager.get_config_path()
        assert path == Path.home() / ".azlin" / "config.toml"

    def test_get_config_path_custom(self, tmp_path):
        """Test custom config path."""
        # Change to tmp_path to make it the current directory
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            custom_path = tmp_path / "custom.toml"
            custom_path.touch()
            path = ConfigManager.get_config_path(str(custom_path))
            assert path == custom_path
        finally:
            os.chdir(original_cwd)

    def test_get_config_path_custom_not_exists(self, tmp_path):
        """Test custom config path that doesn't exist."""
        # Change to tmp_path to make it the current directory
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            custom_path = tmp_path / "missing.toml"
            with pytest.raises(ConfigError, match="Config file not found"):
                ConfigManager.get_config_path(str(custom_path))
        finally:
            os.chdir(original_cwd)

    def test_load_config_not_exists(self, tmp_path):
        """Test loading config when file doesn't exist."""
        with patch.object(ConfigManager, "get_config_path", return_value=tmp_path / "missing.toml"):
            config = ConfigManager.load_config()
            assert isinstance(config, AzlinConfig)
            assert config.default_resource_group is None

    def test_get_resource_group_cli_override(self):
        """Test CLI value overrides config."""
        result = ConfigManager.get_resource_group("cli-rg")
        assert result == "cli-rg"

    def test_get_region_cli_override(self):
        """Test CLI value overrides config."""
        result = ConfigManager.get_region("westus")
        assert result == "westus"

    def test_get_vm_size_cli_override(self):
        """Test CLI value overrides config."""
        result = ConfigManager.get_vm_size("Standard_D4s_v3")
        assert result == "Standard_D4s_v3"

    def test_get_region_from_config(self, tmp_path):
        """Test getting region from config."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('default_region = "westus2"')

        with patch.object(ConfigManager, "DEFAULT_CONFIG_FILE", config_file):
            result = ConfigManager.get_region(None)
            assert result == "westus2"

    def test_get_vm_size_default(self, tmp_path):
        """Test default VM size."""
        config_file = tmp_path / "missing.toml"

        with patch.object(ConfigManager, "DEFAULT_CONFIG_FILE", config_file):
            result = ConfigManager.get_vm_size(None)
            assert result == "Standard_B2s"


class TestConfigManagerSecurity:
    """Security tests for ConfigManager path validation."""

    def test_path_traversal_relative_attack(self, tmp_path):
        """Test that relative path traversal attacks are blocked."""
        # Create a config file in tmp_path
        config_file = tmp_path / "config.toml"
        config_file.write_text('default_region = "test"')

        # Try to use path traversal to escape
        malicious_path = str(tmp_path / ".." / ".." / ".." / "etc" / "passwd")

        with pytest.raises(ConfigError, match="outside allowed directories"):
            ConfigManager.get_config_path(malicious_path)

    def test_path_traversal_absolute_outside_home(self, tmp_path):
        """Test that absolute paths outside home directory are blocked."""
        # Create a file in /tmp to try to access
        test_file = tmp_path / "evil.toml"
        test_file.write_text('default_region = "hacked"')

        with pytest.raises(ConfigError, match="outside allowed directories"):
            ConfigManager.get_config_path(str(test_file))

    def test_symlink_attack_to_sensitive_file(self, tmp_path):
        """Test that symlinks to sensitive files are blocked."""
        # Create a symlink to /etc/passwd
        symlink_path = tmp_path / "malicious.toml"
        target = Path("/etc/passwd")

        if target.exists():  # Only run on systems with /etc/passwd
            try:
                symlink_path.symlink_to(target)
                with pytest.raises(ConfigError, match="outside allowed directories"):
                    ConfigManager.get_config_path(str(symlink_path))
            except OSError:
                pytest.skip("Cannot create symlinks (permission denied)")

    def test_valid_path_in_azlin_config_dir(self, tmp_path):
        """Test that valid paths in ~/.azlin/ are accepted."""
        # Mock the home directory to use tmp_path
        azlin_dir = tmp_path / ".azlin"
        azlin_dir.mkdir()
        config_file = azlin_dir / "config.toml"
        config_file.write_text('default_region = "test"')

        with patch.object(ConfigManager, "DEFAULT_CONFIG_DIR", azlin_dir):
            # This should succeed
            path = ConfigManager.get_config_path(str(config_file))
            assert path == config_file.resolve()

    def test_valid_path_in_current_directory(self, tmp_path):
        """Test that paths in current working directory are accepted."""
        config_file = tmp_path / "test_config.toml"
        config_file.write_text('default_region = "test"')

        # Change to tmp_path as current directory
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            # This should succeed since we're in the current directory
            path = ConfigManager.get_config_path(str(config_file))
            assert path == config_file.resolve()
        finally:
            os.chdir(original_cwd)

    def test_save_config_blocks_path_traversal(self, tmp_path):
        """Test that save_config blocks path traversal attacks."""
        config = AzlinConfig(default_region="test")
        malicious_path = str(tmp_path / ".." / ".." / ".." / "tmp" / "evil.toml")

        with pytest.raises(ConfigError, match="outside allowed directories"):
            ConfigManager.save_config(config, malicious_path)

    def test_save_config_blocks_absolute_outside_home(self, tmp_path):
        """Test that save_config blocks absolute paths outside home."""
        config = AzlinConfig(default_region="test")
        evil_path = "/tmp/evil_config.toml"  # noqa: S108 - testing path validation

        with pytest.raises(ConfigError, match="outside allowed directories"):
            ConfigManager.save_config(config, evil_path)

    def test_update_config_blocks_path_traversal(self, tmp_path):
        """Test that update_config blocks path traversal attacks."""
        malicious_path = str(tmp_path / ".." / ".." / ".." / "tmp" / "evil.toml")

        with pytest.raises(ConfigError, match="outside allowed directories"):
            ConfigManager.update_config(malicious_path, default_region="hacked")

    def test_mixed_traversal_attack(self, tmp_path):
        """Test mixed path traversal with valid and invalid segments."""
        # Create valid azlin directory
        azlin_dir = tmp_path / ".azlin"
        azlin_dir.mkdir()

        # Try to traverse out and back in
        malicious_path = str(azlin_dir / ".." / ".." / "etc" / "passwd")

        with pytest.raises(ConfigError, match="outside allowed directories"):
            ConfigManager.get_config_path(malicious_path)

    def test_valid_subdirectory_in_azlin_dir(self, tmp_path):
        """Test that subdirectories in ~/.azlin/ are accepted."""
        azlin_dir = tmp_path / ".azlin"
        azlin_dir.mkdir()
        subdir = azlin_dir / "backups"
        subdir.mkdir()
        config_file = subdir / "backup.toml"
        config_file.write_text('default_region = "test"')

        with patch.object(ConfigManager, "DEFAULT_CONFIG_DIR", azlin_dir):
            # This should succeed - subdirectories are allowed
            path = ConfigManager.get_config_path(str(config_file))
            assert path == config_file.resolve()

    def test_empty_path_rejected(self):
        """Test that empty custom path is handled properly."""
        # Empty string should use default path
        path = ConfigManager.get_config_path("")
        assert path == ConfigManager.DEFAULT_CONFIG_FILE

    def test_relative_path_in_current_dir_accepted(self, tmp_path):
        """Test that relative paths within current directory are accepted."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('default_region = "test"')

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            # Relative path in current directory should work
            path = ConfigManager.get_config_path("./config.toml")
            assert path == config_file.resolve()
        finally:
            os.chdir(original_cwd)
