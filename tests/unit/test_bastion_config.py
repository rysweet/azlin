"""Unit tests for BastionConfig class.

Tests for Bastion configuration management including:
- Configuration loading and saving
- VM-to-Bastion mapping
- Configuration validation
- TOML serialization
- Security checks

These tests follow TDD approach - they will FAIL until implementation is complete.
"""

import pytest

from azlin.modules.bastion_config import (
    BastionConfig,
    BastionConfigError,
    BastionMapping,
)


class TestBastionMapping:
    """Test BastionMapping dataclass."""

    def test_mapping_creation(self):
        """Test creating BastionMapping object."""
        mapping = BastionMapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
            enabled=True,
        )

        assert mapping.vm_name == "my-vm"
        assert mapping.vm_resource_group == "my-rg"
        assert mapping.bastion_name == "my-bastion"
        assert mapping.bastion_resource_group == "bastion-rg"
        assert mapping.enabled is True

    def test_mapping_defaults(self):
        """Test default values for BastionMapping."""
        mapping = BastionMapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )

        assert mapping.enabled is True  # Default

    def test_mapping_to_dict(self):
        """Test converting mapping to dictionary."""
        mapping = BastionMapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
            enabled=False,
        )

        data = mapping.to_dict()

        assert data["vm_name"] == "my-vm"
        assert data["vm_resource_group"] == "my-rg"
        assert data["bastion_name"] == "my-bastion"
        assert data["bastion_resource_group"] == "bastion-rg"
        assert data["enabled"] is False

    def test_mapping_from_dict(self):
        """Test creating mapping from dictionary."""
        data = {
            "vm_name": "my-vm",
            "vm_resource_group": "my-rg",
            "bastion_name": "my-bastion",
            "bastion_resource_group": "bastion-rg",
            "enabled": True,
        }

        mapping = BastionMapping.from_dict(data)

        assert mapping.vm_name == "my-vm"
        assert mapping.bastion_name == "my-bastion"
        assert mapping.enabled is True


class TestBastionConfig:
    """Test BastionConfig class."""

    @pytest.fixture
    def temp_config_file(self, tmp_path):
        """Create temporary config file."""
        config_file = tmp_path / "bastion_config.toml"
        return config_file

    def test_init_empty_config(self):
        """Test initializing empty config."""
        config = BastionConfig()

        assert config.mappings == {}
        assert config.default_bastion is None
        assert config.auto_detect is True
        assert config.prefer_bastion is False

    def test_add_mapping(self):
        """Test adding VM-to-Bastion mapping."""
        # Arrange
        config = BastionConfig()

        # Act
        config.add_mapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )

        # Assert
        assert "my-vm" in config.mappings
        mapping = config.mappings["my-vm"]
        assert mapping.vm_name == "my-vm"
        assert mapping.bastion_name == "my-bastion"
        assert mapping.enabled is True

    def test_add_mapping_duplicate_overwrites(self):
        """Test adding duplicate mapping overwrites existing."""
        # Arrange
        config = BastionConfig()
        config.add_mapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="old-bastion",
            bastion_resource_group="bastion-rg",
        )

        # Act
        config.add_mapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="new-bastion",
            bastion_resource_group="bastion-rg",
        )

        # Assert
        assert config.mappings["my-vm"].bastion_name == "new-bastion"

    def test_remove_mapping(self):
        """Test removing VM-to-Bastion mapping."""
        # Arrange
        config = BastionConfig()
        config.add_mapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )

        # Act
        config.remove_mapping("my-vm")

        # Assert
        assert "my-vm" not in config.mappings

    def test_remove_mapping_nonexistent(self):
        """Test removing nonexistent mapping (no error)."""
        # Arrange
        config = BastionConfig()

        # Act (should not raise)
        config.remove_mapping("nonexistent-vm")

        # Assert
        assert len(config.mappings) == 0

    def test_get_mapping(self):
        """Test getting mapping for VM."""
        # Arrange
        config = BastionConfig()
        config.add_mapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )

        # Act
        mapping = config.get_mapping("my-vm")

        # Assert
        assert mapping is not None
        assert mapping.bastion_name == "my-bastion"

    def test_get_mapping_not_found(self):
        """Test getting mapping for unmapped VM."""
        # Arrange
        config = BastionConfig()

        # Act
        mapping = config.get_mapping("nonexistent-vm")

        # Assert
        assert mapping is None

    def test_get_mapping_disabled(self):
        """Test getting disabled mapping returns None."""
        # Arrange
        config = BastionConfig()
        config.add_mapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )
        config.disable_mapping("my-vm")

        # Act
        mapping = config.get_mapping("my-vm")

        # Assert
        assert mapping is None

    def test_enable_mapping(self):
        """Test enabling disabled mapping."""
        # Arrange
        config = BastionConfig()
        config.add_mapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )
        config.disable_mapping("my-vm")

        # Act
        config.enable_mapping("my-vm")

        # Assert
        mapping = config.get_mapping("my-vm")
        assert mapping is not None
        assert mapping.enabled is True

    def test_disable_mapping(self):
        """Test disabling mapping."""
        # Arrange
        config = BastionConfig()
        config.add_mapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )

        # Act
        config.disable_mapping("my-vm")

        # Assert
        assert config.mappings["my-vm"].enabled is False

    def test_list_mappings(self):
        """Test listing all mappings."""
        # Arrange
        config = BastionConfig()
        config.add_mapping(
            vm_name="vm1",
            vm_resource_group="rg1",
            bastion_name="bastion1",
            bastion_resource_group="brg1",
        )
        config.add_mapping(
            vm_name="vm2",
            vm_resource_group="rg2",
            bastion_name="bastion2",
            bastion_resource_group="brg2",
        )

        # Act
        mappings = config.list_mappings()

        # Assert
        assert len(mappings) == 2
        assert any(m.vm_name == "vm1" for m in mappings)
        assert any(m.vm_name == "vm2" for m in mappings)

    def test_list_mappings_only_enabled(self):
        """Test listing only enabled mappings."""
        # Arrange
        config = BastionConfig()
        config.add_mapping(
            vm_name="vm1",
            vm_resource_group="rg1",
            bastion_name="bastion1",
            bastion_resource_group="brg1",
        )
        config.add_mapping(
            vm_name="vm2",
            vm_resource_group="rg2",
            bastion_name="bastion2",
            bastion_resource_group="brg2",
        )
        config.disable_mapping("vm2")

        # Act
        mappings = config.list_mappings(only_enabled=True)

        # Assert
        assert len(mappings) == 1
        assert mappings[0].vm_name == "vm1"

    def test_set_default_bastion(self):
        """Test setting default Bastion host."""
        # Arrange
        config = BastionConfig()

        # Act
        config.set_default_bastion("my-bastion", "bastion-rg")

        # Assert
        assert config.default_bastion == ("my-bastion", "bastion-rg")

    def test_clear_default_bastion(self):
        """Test clearing default Bastion host."""
        # Arrange
        config = BastionConfig()
        config.set_default_bastion("my-bastion", "bastion-rg")

        # Act
        config.clear_default_bastion()

        # Assert
        assert config.default_bastion is None

    def test_to_dict(self):
        """Test converting config to dictionary."""
        # Arrange
        config = BastionConfig()
        config.add_mapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )
        config.set_default_bastion("default-bastion", "default-rg")
        config.auto_detect = False
        config.prefer_bastion = True

        # Act
        data = config.to_dict()

        # Assert
        assert "mappings" in data
        assert "my-vm" in data["mappings"]
        assert data["default_bastion"]["name"] == "default-bastion"
        assert data["default_bastion"]["resource_group"] == "default-rg"
        assert data["auto_detect"] is False
        assert data["prefer_bastion"] is True

    def test_from_dict(self):
        """Test creating config from dictionary."""
        # Arrange
        data = {
            "mappings": {
                "my-vm": {
                    "vm_name": "my-vm",
                    "vm_resource_group": "my-rg",
                    "bastion_name": "my-bastion",
                    "bastion_resource_group": "bastion-rg",
                    "enabled": True,
                }
            },
            "default_bastion": {"name": "default-bastion", "resource_group": "default-rg"},
            "auto_detect": False,
            "prefer_bastion": True,
        }

        # Act
        config = BastionConfig.from_dict(data)

        # Assert
        assert "my-vm" in config.mappings
        assert config.default_bastion == ("default-bastion", "default-rg")
        assert config.auto_detect is False
        assert config.prefer_bastion is True

    def test_save_config(self, temp_config_file):
        """Test saving config to file."""
        # Arrange
        config = BastionConfig()
        config.add_mapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )

        # Act
        config.save(temp_config_file)

        # Assert
        assert temp_config_file.exists()
        assert temp_config_file.stat().st_mode & 0o777 == 0o600  # Secure permissions

    def test_load_config(self, temp_config_file):
        """Test loading config from file."""
        # Arrange
        config1 = BastionConfig()
        config1.add_mapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )
        config1.save(temp_config_file)

        # Act
        config2 = BastionConfig.load(temp_config_file)

        # Assert
        assert "my-vm" in config2.mappings
        assert config2.mappings["my-vm"].bastion_name == "my-bastion"

    def test_load_config_not_exists(self, tmp_path):
        """Test loading nonexistent config returns empty config."""
        # Arrange
        nonexistent_file = tmp_path / "missing.toml"

        # Act
        config = BastionConfig.load(nonexistent_file)

        # Assert
        assert len(config.mappings) == 0
        assert config.default_bastion is None

    def test_load_config_invalid_format(self, temp_config_file):
        """Test error loading malformed config file."""
        # Arrange
        temp_config_file.write_text("invalid toml content {]}")

        # Act & Assert
        with pytest.raises(BastionConfigError, match="Failed to load config"):
            BastionConfig.load(temp_config_file)

    def test_validate_config(self):
        """Test config validation."""
        # Arrange
        config = BastionConfig()
        config.add_mapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )

        # Act
        is_valid = config.validate()

        # Assert
        assert is_valid is True

    def test_validate_config_invalid_mapping(self):
        """Test validation fails with invalid mapping."""
        # Arrange
        config = BastionConfig()
        config.mappings[""] = BastionMapping(
            vm_name="",  # Invalid
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )

        # Act
        is_valid = config.validate()

        # Assert
        assert is_valid is False

    def test_merge_configs(self):
        """Test merging two configs."""
        # Arrange
        config1 = BastionConfig()
        config1.add_mapping(
            vm_name="vm1",
            vm_resource_group="rg1",
            bastion_name="bastion1",
            bastion_resource_group="brg1",
        )

        config2 = BastionConfig()
        config2.add_mapping(
            vm_name="vm2",
            vm_resource_group="rg2",
            bastion_name="bastion2",
            bastion_resource_group="brg2",
        )

        # Act
        config1.merge(config2)

        # Assert
        assert "vm1" in config1.mappings
        assert "vm2" in config1.mappings

    def test_merge_configs_overwrites_duplicates(self):
        """Test merging overwrites duplicate entries."""
        # Arrange
        config1 = BastionConfig()
        config1.add_mapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="old-bastion",
            bastion_resource_group="old-rg",
        )

        config2 = BastionConfig()
        config2.add_mapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="new-bastion",
            bastion_resource_group="new-rg",
        )

        # Act
        config1.merge(config2)

        # Assert
        assert config1.mappings["my-vm"].bastion_name == "new-bastion"


class TestBastionConfigEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_vm_name(self):
        """Test error with empty VM name."""
        config = BastionConfig()

        with pytest.raises(BastionConfigError, match="VM name cannot be empty"):
            config.add_mapping(
                vm_name="",
                vm_resource_group="my-rg",
                bastion_name="my-bastion",
                bastion_resource_group="bastion-rg",
            )

    def test_empty_bastion_name(self):
        """Test error with empty Bastion name."""
        config = BastionConfig()

        with pytest.raises(BastionConfigError, match="Bastion name cannot be empty"):
            config.add_mapping(
                vm_name="my-vm",
                vm_resource_group="my-rg",
                bastion_name="",
                bastion_resource_group="bastion-rg",
            )

    def test_empty_resource_group(self):
        """Test error with empty resource group."""
        config = BastionConfig()

        with pytest.raises(BastionConfigError, match="Resource group cannot be empty"):
            config.add_mapping(
                vm_name="my-vm",
                vm_resource_group="",
                bastion_name="my-bastion",
                bastion_resource_group="bastion-rg",
            )

    def test_config_file_permissions(self, tmp_path):
        """Test config file has secure permissions."""
        # Arrange
        config_file = tmp_path / "bastion_config.toml"
        config = BastionConfig()
        config.add_mapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )

        # Act
        config.save(config_file)

        # Assert
        mode = config_file.stat().st_mode & 0o777
        assert mode == 0o600  # Owner read/write only

    def test_save_to_readonly_directory(self, tmp_path):
        """Test error saving to readonly directory."""
        # Arrange
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir(mode=0o555)  # Read-only
        config_file = readonly_dir / "config.toml"

        config = BastionConfig()

        # Act & Assert
        with pytest.raises(BastionConfigError, match="Permission denied"):
            config.save(config_file)

    def test_load_from_insecure_file(self, tmp_path):
        """Test warning when loading from insecure file."""
        # Arrange
        config_file = tmp_path / "bastion_config.toml"
        config = BastionConfig()
        config.save(config_file)
        config_file.chmod(0o644)  # Insecure permissions

        # Act
        with pytest.warns(UserWarning, match="insecure permissions"):
            BastionConfig.load(config_file)

    def test_special_characters_in_names(self):
        """Test handling special characters in names."""
        # Arrange
        config = BastionConfig()

        # Act
        config.add_mapping(
            vm_name="my-vm_test.123",
            vm_resource_group="my-rg-test",
            bastion_name="bastion-test_1",
            bastion_resource_group="bastion-rg-test",
        )

        # Assert
        assert "my-vm_test.123" in config.mappings

    def test_unicode_in_names(self):
        """Test handling unicode characters in names."""
        # Arrange
        config = BastionConfig()

        # Act & Assert - should handle or reject gracefully
        with pytest.raises(BastionConfigError, match="Invalid characters"):
            config.add_mapping(
                vm_name="my-vm-测试",
                vm_resource_group="my-rg",
                bastion_name="my-bastion",
                bastion_resource_group="bastion-rg",
            )

    def test_very_long_names(self):
        """Test handling very long names."""
        # Arrange
        config = BastionConfig()
        long_name = "a" * 500

        # Act & Assert
        with pytest.raises(BastionConfigError, match="Name too long"):
            config.add_mapping(
                vm_name=long_name,
                vm_resource_group="my-rg",
                bastion_name="my-bastion",
                bastion_resource_group="bastion-rg",
            )

    def test_concurrent_config_access(self, tmp_path):
        """Test thread-safe config access."""
        # Arrange
        config_file = tmp_path / "bastion_config.toml"
        config = BastionConfig()
        config.add_mapping(
            vm_name="my-vm",
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="bastion-rg",
        )

        # Act - save and load simultaneously (thread safety test)
        import threading

        def save_config():
            config.save(config_file)

        def load_config():
            BastionConfig.load(config_file)

        threads = [threading.Thread(target=save_config), threading.Thread(target=load_config)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert - no errors occurred
        assert config_file.exists()
