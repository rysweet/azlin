"""Tests for autopilot configuration management.

Following TDD approach - these tests define the expected behavior
before implementation.
"""

import pytest

from azlin.autopilot.config import AutoPilotConfig, AutoPilotConfigError, ConfigManager


class TestAutoPilotConfig:
    """Test autopilot configuration data model."""

    def test_config_creation_with_defaults(self):
        """Test creating config with default values."""
        config = AutoPilotConfig(
            enabled=True,
            budget_monthly=500,
            strategy="balanced",
        )

        assert config.enabled is True
        assert config.budget_monthly == 500
        assert config.strategy == "balanced"
        assert config.idle_threshold_minutes == 120  # default
        assert config.cpu_threshold_percent == 20  # default
        assert "production" in config.protected_tags
        assert "critical" in config.protected_tags

    def test_config_validation_budget_positive(self):
        """Test budget must be positive."""
        with pytest.raises(AutoPilotConfigError, match="Budget must be positive"):
            AutoPilotConfig(
                enabled=True,
                budget_monthly=-100,
                strategy="balanced",
            )

    def test_config_validation_strategy(self):
        """Test strategy must be valid option."""
        with pytest.raises(AutoPilotConfigError, match="Invalid strategy"):
            AutoPilotConfig(
                enabled=True,
                budget_monthly=500,
                strategy="invalid",
            )

    def test_config_validation_idle_threshold(self):
        """Test idle threshold must be reasonable."""
        with pytest.raises(AutoPilotConfigError, match="Idle threshold"):
            AutoPilotConfig(
                enabled=True,
                budget_monthly=500,
                strategy="balanced",
                idle_threshold_minutes=10,  # too low
            )

    def test_config_to_dict(self):
        """Test converting config to dictionary."""
        config = AutoPilotConfig(
            enabled=True,
            budget_monthly=500,
            strategy="balanced",
        )

        config_dict = config.to_dict()

        assert config_dict["enabled"] is True
        assert config_dict["budget_monthly"] == 500
        assert config_dict["strategy"] == "balanced"
        assert "work_hours" in config_dict
        assert "notifications" in config_dict

    def test_config_from_dict(self):
        """Test creating config from dictionary."""
        config_dict = {
            "enabled": True,
            "budget_monthly": 500,
            "strategy": "balanced",
            "idle_threshold_minutes": 120,
        }

        config = AutoPilotConfig.from_dict(config_dict)

        assert config.enabled is True
        assert config.budget_monthly == 500
        assert config.strategy == "balanced"


class TestConfigManager:
    """Test autopilot configuration manager."""

    def test_save_and_load_config(self, tmp_path):
        """Test saving and loading configuration."""
        config_file = tmp_path / "autopilot.json"

        config = AutoPilotConfig(
            enabled=True,
            budget_monthly=500,
            strategy="balanced",
        )

        # Save
        ConfigManager.save_config(config, config_file)
        assert config_file.exists()

        # Load
        loaded_config = ConfigManager.load_config(config_file)
        assert loaded_config.enabled == config.enabled
        assert loaded_config.budget_monthly == config.budget_monthly
        assert loaded_config.strategy == config.strategy

    def test_load_config_not_found(self, tmp_path):
        """Test loading config when file doesn't exist."""
        config_file = tmp_path / "nonexistent.json"

        with pytest.raises(AutoPilotConfigError, match="Configuration file not found"):
            ConfigManager.load_config(config_file)

    def test_config_update(self, tmp_path):
        """Test updating configuration."""
        config_file = tmp_path / "autopilot.json"

        # Create initial config
        config = AutoPilotConfig(
            enabled=True,
            budget_monthly=500,
            strategy="balanced",
        )
        ConfigManager.save_config(config, config_file)

        # Update config
        updates = {"budget_monthly": 1000, "strategy": "aggressive"}
        ConfigManager.update_config(config_file, updates)

        # Verify updates
        updated_config = ConfigManager.load_config(config_file)
        assert updated_config.budget_monthly == 1000
        assert updated_config.strategy == "aggressive"
        assert updated_config.enabled is True  # unchanged

    def test_config_delete(self, tmp_path):
        """Test deleting configuration."""
        config_file = tmp_path / "autopilot.json"

        config = AutoPilotConfig(
            enabled=True,
            budget_monthly=500,
            strategy="balanced",
        )
        ConfigManager.save_config(config, config_file)

        assert config_file.exists()

        ConfigManager.delete_config(config_file)

        assert not config_file.exists()

    def test_default_config_path(self):
        """Test getting default configuration path."""
        default_path = ConfigManager.get_default_config_path()

        assert default_path.name == "autopilot.json"
        assert ".azlin" in str(default_path)
