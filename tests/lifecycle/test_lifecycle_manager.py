"""Unit tests for LifecycleManager (60% of test pyramid).

Tests configuration CRUD operations with mocked file I/O.
"""

import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from azlin.lifecycle.lifecycle_manager import (
    LifecycleManager,
    MonitoringConfig,
    MonitoringStatus,
    LifecycleConfigError,
)


class TestLifecycleManager:
    """Test LifecycleManager configuration operations."""

    @pytest.fixture
    def mock_config_path(self, tmp_path):
        """Provide temporary config path."""
        return tmp_path / "lifecycle-config.toml"

    @pytest.fixture
    def manager(self, mock_config_path):
        """Create LifecycleManager with mocked config path."""
        with patch("azlin.lifecycle.lifecycle_manager.LIFECYCLE_CONFIG_PATH", mock_config_path):
            yield LifecycleManager()

    def test_enable_monitoring_creates_config(self, manager, mock_config_path):
        """Test enabling monitoring creates configuration entry."""
        config = MonitoringConfig(
            enabled=True,
            check_interval_seconds=60,
            restart_policy="never",
            ssh_failure_threshold=3,
        )

        manager.enable_monitoring("test-vm", config)

        assert mock_config_path.exists()
        status = manager.get_monitoring_status("test-vm")
        assert status.enabled is True
        assert status.config.check_interval_seconds == 60

    def test_enable_monitoring_default_values(self, manager):
        """Test default configuration values."""
        config = MonitoringConfig(enabled=True)

        manager.enable_monitoring("test-vm", config)

        status = manager.get_monitoring_status("test-vm")
        assert status.config.check_interval_seconds == 60
        assert status.config.restart_policy == "never"
        assert status.config.ssh_failure_threshold == 3

    def test_disable_monitoring_removes_config(self, manager):
        """Test disabling monitoring removes configuration."""
        config = MonitoringConfig(enabled=True)
        manager.enable_monitoring("test-vm", config)

        manager.disable_monitoring("test-vm")

        with pytest.raises(LifecycleConfigError, match="not configured"):
            manager.get_monitoring_status("test-vm")

    def test_update_config_modifies_existing(self, manager):
        """Test updating configuration modifies existing entry."""
        config = MonitoringConfig(enabled=True, check_interval_seconds=60)
        manager.enable_monitoring("test-vm", config)

        updated_config = MonitoringConfig(enabled=True, check_interval_seconds=120)
        manager.update_config("test-vm", updated_config)

        status = manager.get_monitoring_status("test-vm")
        assert status.config.check_interval_seconds == 120

    def test_get_status_nonexistent_vm_raises_error(self, manager):
        """Test getting status for unconfigured VM raises error."""
        with pytest.raises(LifecycleConfigError, match="not configured"):
            manager.get_monitoring_status("nonexistent-vm")

    def test_list_monitored_vms(self, manager):
        """Test listing all monitored VMs."""
        config1 = MonitoringConfig(enabled=True)
        config2 = MonitoringConfig(enabled=True)

        manager.enable_monitoring("vm1", config1)
        manager.enable_monitoring("vm2", config2)

        vms = manager.list_monitored_vms()
        assert len(vms) == 2
        assert "vm1" in vms
        assert "vm2" in vms

    def test_list_monitored_vms_empty(self, manager):
        """Test listing when no VMs configured."""
        vms = manager.list_monitored_vms()
        assert len(vms) == 0

    def test_set_hook_adds_hook_script(self, manager):
        """Test setting a lifecycle hook."""
        config = MonitoringConfig(enabled=True)
        manager.enable_monitoring("test-vm", config)

        manager.set_hook("test-vm", "on_failure", "/path/to/alert.sh")

        status = manager.get_monitoring_status("test-vm")
        assert status.config.hooks["on_failure"] == "/path/to/alert.sh"

    def test_clear_hook_removes_hook(self, manager):
        """Test clearing a lifecycle hook."""
        config = MonitoringConfig(enabled=True, hooks={"on_failure": "/path/to/alert.sh"})
        manager.enable_monitoring("test-vm", config)

        manager.clear_hook("test-vm", "on_failure")

        status = manager.get_monitoring_status("test-vm")
        assert status.config.hooks.get("on_failure") == ""

    def test_validate_restart_policy(self, manager):
        """Test restart policy validation."""
        with pytest.raises(LifecycleConfigError, match="Invalid restart policy"):
            config = MonitoringConfig(enabled=True, restart_policy="invalid")
            manager.enable_monitoring("test-vm", config)

    def test_config_persistence(self, manager, mock_config_path):
        """Test configuration persists across manager instances."""
        config = MonitoringConfig(enabled=True, check_interval_seconds=90)
        manager.enable_monitoring("test-vm", config)

        # Create new manager instance
        new_manager = LifecycleManager()
        status = new_manager.get_monitoring_status("test-vm")

        assert status.config.check_interval_seconds == 90
