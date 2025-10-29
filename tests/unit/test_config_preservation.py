"""Test that ConfigManager preserves all fields during updates.

This test ensures that update_config() doesn't lose fields like default_nfs_storage
when updating other fields like default_resource_group.

Regression test for: User config being overwritten and losing default_nfs_storage.
"""

import pytest
from pathlib import Path

from azlin.config_manager import AzlinConfig, ConfigManager


class TestConfigPreservation:
    """Test config field preservation during updates."""

    def test_update_config_preserves_all_fields(self, tmp_path):
        """Test that update_config preserves fields not being updated."""
        config_file = tmp_path / "config.toml"

        # Create initial config with all fields set
        initial = AzlinConfig(
            default_resource_group="initial-rg",
            default_region="westus2",
            default_vm_size="Standard_E16as_v5",
            notification_command="imessR",
            default_nfs_storage="my-nfs-storage",  # Critical field
            session_names={"vm1": "session1"},
            vm_storage={"vm1": "storage1"},
        )
        ConfigManager.save_config(initial, str(config_file))

        # Update only resource_group (simulating 'azlin new' behavior)
        ConfigManager.update_config(
            str(config_file),
            default_resource_group="updated-rg",
            last_vm_name="new-vm"
        )

        # Load and verify ALL fields preserved
        loaded = ConfigManager.load_config(str(config_file))

        # Updated fields
        assert loaded.default_resource_group == "updated-rg"
        assert loaded.last_vm_name == "new-vm"

        # Preserved fields (MUST NOT BE LOST)
        assert loaded.default_region == "westus2", "default_region was lost!"
        assert loaded.default_vm_size == "Standard_E16as_v5", "default_vm_size was lost!"
        assert loaded.notification_command == "imessR", "notification_command was lost!"
        assert loaded.default_nfs_storage == "my-nfs-storage", "default_nfs_storage was lost!"
        assert loaded.session_names == {"vm1": "session1"}, "session_names was lost!"
        assert loaded.vm_storage == {"vm1": "storage1"}, "vm_storage was lost!"

    def test_update_config_with_none_values_preserved(self, tmp_path):
        """Test that fields with None values are properly handled."""
        config_file = tmp_path / "config.toml"

        # Create config with some None fields
        initial = AzlinConfig(
            default_resource_group=None,  # None value
            default_region="eastus",
            default_nfs_storage="storage1",
        )
        ConfigManager.save_config(initial, str(config_file))

        # Update one field
        ConfigManager.update_config(str(config_file), default_region="westus")

        # Load and verify
        loaded = ConfigManager.load_config(str(config_file))
        assert loaded.default_region == "westus"
        assert loaded.default_nfs_storage == "storage1", "default_nfs_storage was lost!"

    def test_save_config_preserves_all_non_none_fields(self, tmp_path):
        """Test that save_config preserves all non-None fields."""
        config_file = tmp_path / "config.toml"

        # Create config with all fields
        config = AzlinConfig(
            default_resource_group="my-rg",
            default_region="westus2",
            default_vm_size="Standard_E16as_v5",
            last_vm_name="last-vm",
            notification_command="imessR",
            session_names={"vm1": "s1", "vm2": "s2"},
            vm_storage={"vm1": "st1"},
            default_nfs_storage="nfs-storage",
        )

        ConfigManager.save_config(config, str(config_file))
        loaded = ConfigManager.load_config(str(config_file))

        # Verify all fields preserved
        assert loaded.default_resource_group == "my-rg"
        assert loaded.default_region == "westus2"
        assert loaded.default_vm_size == "Standard_E16as_v5"
        assert loaded.last_vm_name == "last-vm"
        assert loaded.notification_command == "imessR"
        assert loaded.session_names == {"vm1": "s1", "vm2": "s2"}
        assert loaded.vm_storage == {"vm1": "st1"}
        assert loaded.default_nfs_storage == "nfs-storage"

    def test_multiple_updates_preserve_fields(self, tmp_path):
        """Test that multiple sequential updates preserve all fields."""
        config_file = tmp_path / "config.toml"

        # Initial config
        initial = AzlinConfig(
            default_resource_group="rg1",
            default_nfs_storage="storage1",
            default_region="eastus",
        )
        ConfigManager.save_config(initial, str(config_file))

        # Update 1: Change RG
        ConfigManager.update_config(str(config_file), default_resource_group="rg2")

        # Update 2: Change region
        ConfigManager.update_config(str(config_file), default_region="westus")

        # Update 3: Add VM name
        ConfigManager.update_config(str(config_file), last_vm_name="vm1")

        # Verify all preserved
        loaded = ConfigManager.load_config(str(config_file))
        assert loaded.default_resource_group == "rg2"
        assert loaded.default_region == "westus"
        assert loaded.last_vm_name == "vm1"
        assert loaded.default_nfs_storage == "storage1", "Lost after multiple updates!"
