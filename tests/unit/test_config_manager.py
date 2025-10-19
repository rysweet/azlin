"""Unit tests for config_manager module."""

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
        custom_path = tmp_path / "custom.toml"
        custom_path.touch()
        path = ConfigManager.get_config_path(str(custom_path))
        assert path == custom_path

    def test_get_config_path_custom_not_exists(self, tmp_path):
        """Test custom config path that doesn't exist."""
        custom_path = tmp_path / "missing.toml"
        with pytest.raises(ConfigError, match="Config file not found"):
            ConfigManager.get_config_path(str(custom_path))

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
