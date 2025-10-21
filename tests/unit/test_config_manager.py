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


class TestSessionNameValidation:
    """Tests for session name validation (Issue #160)."""

    def test_validate_rejects_self_referential(self):
        """Test validation rejects self-referential mappings."""
        with pytest.raises(ConfigError, match="Self-referential session name not allowed"):
            ConfigManager._validate_session_mapping("simserv", "simserv", {})

    def test_validate_rejects_duplicate_session_names(self):
        """Test validation rejects duplicate session names."""
        existing = {"vm1": "prod", "vm2": "staging"}
        with pytest.raises(
            ConfigError, match="Duplicate session name 'prod' already maps to VM 'vm1'"
        ):
            ConfigManager._validate_session_mapping("vm3", "prod", existing)

    def test_validate_allows_updating_same_vm(self):
        """Test validation allows updating session name for same VM."""
        existing = {"vm2": "staging"}
        # Should not raise - we're updating vm1's session name
        ConfigManager._validate_session_mapping("vm1", "prod", existing)

    def test_validate_rejects_invalid_session_name_format(self):
        """Test validation rejects invalid session name format."""
        with pytest.raises(ConfigError, match="Invalid session name format"):
            ConfigManager._validate_session_mapping("vm1", "invalid@name", {})

    def test_validate_rejects_invalid_vm_name_format(self):
        """Test validation rejects invalid VM name format."""
        with pytest.raises(ConfigError, match="Invalid VM name format"):
            ConfigManager._validate_session_mapping("invalid@vm", "session1", {})

    def test_validate_rejects_empty_session_name(self):
        """Test validation rejects empty session name."""
        with pytest.raises(ConfigError, match="Invalid session name format"):
            ConfigManager._validate_session_mapping("vm1", "", {})

    def test_validate_rejects_too_long_session_name(self):
        """Test validation rejects session name > 64 chars."""
        long_name = "a" * 65
        with pytest.raises(ConfigError, match="Invalid session name format"):
            ConfigManager._validate_session_mapping("vm1", long_name, {})

    def test_validate_accepts_valid_mappings(self):
        """Test validation accepts valid mappings."""
        existing = {"vm1": "prod", "vm2": "staging"}
        # Should not raise
        ConfigManager._validate_session_mapping("vm3", "dev", existing)
        ConfigManager._validate_session_mapping("vm1", "prod-updated", existing)

    def test_set_session_name_rejects_self_referential(self, tmp_path):
        """Test set_session_name rejects self-referential mappings."""
        config_file = tmp_path / "config.toml"
        with pytest.raises(ConfigError, match="Self-referential session name not allowed"):
            ConfigManager.set_session_name("simserv", "simserv", str(config_file))

    def test_set_session_name_rejects_duplicates(self, tmp_path):
        """Test set_session_name rejects duplicate session names."""
        config_file = tmp_path / "config.toml"
        # Create initial mapping
        ConfigManager.set_session_name("vm1", "prod", str(config_file))
        # Try to create duplicate
        with pytest.raises(ConfigError, match="Duplicate session name 'prod'"):
            ConfigManager.set_session_name("vm2", "prod", str(config_file))

    def test_set_session_name_allows_updating_same_vm(self, tmp_path):
        """Test set_session_name allows updating session name for same VM."""
        config_file = tmp_path / "config.toml"
        # Create initial mapping
        ConfigManager.set_session_name("vm1", "prod", str(config_file))
        # Update same VM - should succeed
        ConfigManager.set_session_name("vm1", "production", str(config_file))
        # Verify update
        result = ConfigManager.get_session_name("vm1", str(config_file))
        assert result == "production"

    def test_get_vm_name_by_session_filters_self_referential(self, tmp_path, caplog):
        """Test get_vm_name_by_session filters out self-referential entries."""
        import logging

        caplog.set_level(logging.WARNING)

        config_file = tmp_path / "config.toml"
        # Manually create config with self-referential entry
        config = AzlinConfig(session_names={"simserv": "simserv", "vm1": "prod"})
        ConfigManager.save_config(config, str(config_file))

        # Lookup should filter out self-referential entry
        result = ConfigManager.get_vm_name_by_session("simserv", str(config_file))
        assert result is None
        assert "Ignoring invalid self-referential session mapping" in caplog.text

    def test_get_vm_name_by_session_warns_on_duplicates(self, tmp_path, caplog):
        """Test get_vm_name_by_session warns on duplicate session names."""
        import logging

        caplog.set_level(logging.WARNING)

        config_file = tmp_path / "config.toml"
        # Manually create config with duplicate session names
        config = AzlinConfig(session_names={"vm1": "prod", "vm2": "prod"})
        ConfigManager.save_config(config, str(config_file))

        # Lookup should warn and return first match
        result = ConfigManager.get_vm_name_by_session("prod", str(config_file))
        assert result == "vm1"
        assert "Duplicate session name 'prod'" in caplog.text

    def test_get_vm_name_by_session_normal_flow(self, tmp_path):
        """Test get_vm_name_by_session returns correct VM for valid mapping."""
        config_file = tmp_path / "config.toml"
        ConfigManager.set_session_name("myvm", "mysession", str(config_file))

        result = ConfigManager.get_vm_name_by_session("mysession", str(config_file))
        assert result == "myvm"

    def test_bug_scenario_simserv_self_referential(self, tmp_path):
        """Test the original bug scenario: simserv -> simserv causes connection failure."""
        config_file = tmp_path / "config.toml"

        # Attempt to create self-referential mapping (should be rejected now)
        with pytest.raises(ConfigError, match="Self-referential session name not allowed"):
            ConfigManager.set_session_name("simserv", "simserv", str(config_file))

        # Verify no mapping was created
        result = ConfigManager.get_session_name("simserv", str(config_file))
        assert result is None
