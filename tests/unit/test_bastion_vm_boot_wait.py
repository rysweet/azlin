"""Unit tests for Bastion VM boot wait functionality.

This test suite validates the VM boot wait feature for newly provisioned Bastion VMs.
These tests follow TDD approach and will FAIL until implementation is complete.

Architecture:
- BastionManager.wait_for_vm_boot() provides configurable boot wait
- CLI._wait_for_cloud_init() calls boot wait for newly provisioned Bastion VMs
- Default wait is 75 seconds, configurable via AZLIN_VM_BOOT_WAIT env var
- Only applies to newly provisioned VMs with Bastion connections

Key Requirements:
1. Fix SSH timeout for newly provisioned Bastion VMs
2. Maintain backward compatibility (existing VMs, direct SSH)
3. Clear logging for diagnosability
4. Environment variable override support
"""

import os
from unittest.mock import call, patch

import pytest

from azlin.modules.bastion_manager import BastionManager


class TestBastionManagerVMBootWait:
    """Test suite for BastionManager VM boot wait functionality."""

    def test_wait_for_vm_boot_uses_default_75_seconds(self):
        """Test that wait_for_vm_boot() waits for default 75 seconds."""
        # Arrange
        manager = BastionManager()

        # Act
        with patch("time.sleep") as mock_sleep:
            manager.wait_for_vm_boot()

        # Assert
        mock_sleep.assert_called_once_with(75)

    def test_wait_for_vm_boot_respects_custom_wait_period(self):
        """Test that wait_for_vm_boot() respects custom wait period."""
        # Arrange
        manager = BastionManager()
        custom_wait = 120

        # Act
        with patch("time.sleep") as mock_sleep:
            manager.wait_for_vm_boot(wait_seconds=custom_wait)

        # Assert
        mock_sleep.assert_called_once_with(120)

    def test_wait_for_vm_boot_logs_progress_messages(self, caplog):
        """Test that wait_for_vm_boot() logs informative progress messages."""
        # Arrange
        manager = BastionManager()

        # Act
        with patch("time.sleep"):
            manager.wait_for_vm_boot(wait_seconds=75)

        # Assert - Check log messages
        log_output = caplog.text.lower()
        assert "waiting" in log_output or "boot" in log_output
        assert "75" in caplog.text or "second" in log_output

    def test_wait_for_vm_boot_respects_env_var_override(self):
        """Test that AZLIN_VM_BOOT_WAIT environment variable overrides default."""
        # Arrange
        manager = BastionManager()

        # Act
        with patch.dict(os.environ, {"AZLIN_VM_BOOT_WAIT": "90"}):
            with patch("time.sleep") as mock_sleep:
                manager.wait_for_vm_boot()

        # Assert
        mock_sleep.assert_called_once_with(90)

    def test_wait_for_vm_boot_env_var_invalid_uses_default(self, caplog):
        """Test that invalid AZLIN_VM_BOOT_WAIT value falls back to default."""
        # Arrange
        manager = BastionManager()

        # Act
        with patch.dict(os.environ, {"AZLIN_VM_BOOT_WAIT": "not_a_number"}):
            with patch("time.sleep") as mock_sleep:
                manager.wait_for_vm_boot()

        # Assert
        mock_sleep.assert_called_once_with(75)  # Falls back to default
        # Should log warning about invalid value
        assert "warning" in caplog.text.lower() or "invalid" in caplog.text.lower()

    def test_wait_for_vm_boot_zero_seconds_skips_wait(self):
        """Test that wait_seconds=0 skips the wait entirely."""
        # Arrange
        manager = BastionManager()

        # Act
        with patch("time.sleep") as mock_sleep:
            manager.wait_for_vm_boot(wait_seconds=0)

        # Assert
        mock_sleep.assert_not_called()

    def test_wait_for_vm_boot_negative_seconds_raises_error(self):
        """Test that negative wait_seconds raises ValueError."""
        # Arrange
        manager = BastionManager()

        # Act & Assert
        with pytest.raises(ValueError, match="wait_seconds.*negative"):
            manager.wait_for_vm_boot(wait_seconds=-10)

    def test_wait_for_vm_boot_logs_start_and_completion(self, caplog):
        """Test that wait_for_vm_boot() logs both start and completion."""
        # Arrange
        manager = BastionManager()

        # Act
        with patch("time.sleep"):
            manager.wait_for_vm_boot(wait_seconds=30)

        # Assert - Should have start and completion messages
        log_messages = [record.message for record in caplog.records]
        assert len(log_messages) >= 2  # At least start and completion

        # Check for indicative keywords
        log_text = " ".join(log_messages).lower()
        assert "wait" in log_text or "waiting" in log_text
        assert "complete" in log_text or "ready" in log_text or "done" in log_text

    def test_wait_for_vm_boot_method_exists_and_callable(self):
        """Test that wait_for_vm_boot method exists on BastionManager."""
        # Arrange
        manager = BastionManager()

        # Assert
        assert hasattr(manager, "wait_for_vm_boot")
        assert callable(manager.wait_for_vm_boot)


class TestBastionManagerEdgeCases:
    """Test edge cases for VM boot wait functionality."""

    def test_wait_for_vm_boot_very_large_value(self):
        """Test that very large wait values are handled correctly."""
        # Arrange
        manager = BastionManager()

        # Act - Should not raise error
        with patch("time.sleep") as mock_sleep:
            manager.wait_for_vm_boot(wait_seconds=3600)  # 1 hour

        # Assert
        mock_sleep.assert_called_once_with(3600)

    def test_wait_for_vm_boot_interrupted_by_keyboard_interrupt(self):
        """Test that KeyboardInterrupt during wait is propagated."""
        # Arrange
        manager = BastionManager()

        # Act & Assert
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                manager.wait_for_vm_boot(wait_seconds=75)

    def test_wait_for_vm_boot_multiple_calls_independent(self):
        """Test that multiple wait_for_vm_boot calls work independently."""
        # Arrange
        manager = BastionManager()

        # Act
        with patch("time.sleep") as mock_sleep:
            manager.wait_for_vm_boot(wait_seconds=30)
            manager.wait_for_vm_boot(wait_seconds=45)
            manager.wait_for_vm_boot(wait_seconds=60)

        # Assert
        assert mock_sleep.call_count == 3
        mock_sleep.assert_has_calls([call(30), call(45), call(60)])

    def test_wait_for_vm_boot_env_var_precedence_over_default(self):
        """Test that env var takes precedence over default but not explicit param."""
        # Arrange
        manager = BastionManager()

        # Act & Assert - Env var overrides default
        with patch.dict(os.environ, {"AZLIN_VM_BOOT_WAIT": "100"}):
            with patch("time.sleep") as mock_sleep:
                manager.wait_for_vm_boot()
                assert mock_sleep.call_args[0][0] == 100

        # Act & Assert - Explicit param overrides env var
        with patch.dict(os.environ, {"AZLIN_VM_BOOT_WAIT": "100"}):
            with patch("time.sleep") as mock_sleep:
                manager.wait_for_vm_boot(wait_seconds=50)
                assert mock_sleep.call_args[0][0] == 50


class TestBastionManagerLoggingDetail:
    """Test detailed logging behavior for VM boot wait."""

    def test_wait_for_vm_boot_logs_reason_for_wait(self, caplog):
        """Test that log messages explain why we're waiting."""
        # Arrange
        manager = BastionManager()

        # Act
        with patch("time.sleep"):
            manager.wait_for_vm_boot()

        # Assert - Should explain this is for VM boot/initialization
        log_text = caplog.text.lower()
        # Looking for keywords that indicate VM initialization
        has_explanation = any(
            keyword in log_text
            for keyword in ["boot", "initialize", "startup", "ready", "provision"]
        )
        assert has_explanation, "Log should explain reason for wait"

    def test_wait_for_vm_boot_logs_at_info_level(self, caplog):
        """Test that wait messages are logged at INFO level."""
        # Arrange
        manager = BastionManager()

        # Act
        with patch("time.sleep"):
            import logging

            with caplog.at_level(logging.INFO):
                manager.wait_for_vm_boot()

        # Assert - Should have INFO level logs
        info_logs = [record for record in caplog.records if record.levelname == "INFO"]
        assert len(info_logs) > 0, "Should have INFO level log messages"

    def test_wait_for_vm_boot_includes_duration_in_log(self, caplog):
        """Test that log messages include the wait duration."""
        # Arrange
        manager = BastionManager()
        wait_time = 45

        # Act
        with patch("time.sleep"):
            manager.wait_for_vm_boot(wait_seconds=wait_time)

        # Assert
        assert str(wait_time) in caplog.text or f"{wait_time}" in caplog.text
