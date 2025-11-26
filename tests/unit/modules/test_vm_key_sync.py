"""Unit tests for vm_key_sync module - GENERATED WITH WORKING IMPLEMENTATIONS"""

import json
import subprocess
from unittest.mock import Mock, mock_open, patch

import pytest

from azlin.modules.vm_key_sync import (
    VMKeySync,
    VMKeySyncError,
)


class TestEnsureKeyAuthorized:
    """Test VMKeySync.ensure_key_authorized() - main entry point."""

    def test_new_key_synced_successfully(self):
        """Test appending new key to VM succeeds."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                # check_key_exists call
                Mock(returncode=0, stdout=json.dumps({"value": [{"message": "KEY_NOT_FOUND"}]})),
                # append_key_to_vm call
                Mock(
                    returncode=0,
                    stdout=json.dumps({"value": [{"code": "ProvisioningState/succeeded"}]}),
                ),
            ]

            vm_sync = VMKeySync()
            result = vm_sync.ensure_key_authorized(
                "test-vm", "test-rg", "ssh-ed25519 AAAA" + ("C" * 36) + " test@host"
            )

            assert result.synced is True
            assert result.already_present is False

    def test_existing_key_skipped_idempotent(self):
        """Test when key already exists, no sync is performed."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0, stdout=json.dumps({"value": [{"message": "KEY_FOUND"}]})
            )

            vm_sync = VMKeySync()
            result = vm_sync.ensure_key_authorized(
                "test-vm", "test-rg", "ssh-ed25519 AAAA" + ("C" * 36) + " test@host"
            )

            assert result.synced is False
            assert result.already_present is True

    def test_sync_timeout_returns_error_result(self):
        """Test sync operation timeout returns error result."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="az", timeout=30)

            vm_sync = VMKeySync()
            result = vm_sync.ensure_key_authorized(
                "test-vm", "test-rg", "ssh-ed25519 AAAA" + ("C" * 36) + " test@host"
            )

            assert result.synced is False
            assert "timed out" in result.error.lower()

    def test_dry_run_mode_no_modifications(self):
        """Test dry-run mode checks only."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0, stdout=json.dumps({"value": [{"message": "KEY_NOT_FOUND"}]})
            )

            vm_sync = VMKeySync()
            result = vm_sync.ensure_key_authorized(
                "test-vm", "test-rg", "ssh-ed25519 AAAA" + ("C" * 36) + " test@host", dry_run=True
            )

            assert result.synced is False
            assert result.method == "dry-run"

    def test_duration_tracking(self):
        """Test operation duration is tracked."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0, stdout=json.dumps({"value": [{"message": "KEY_FOUND"}]})
            )

            vm_sync = VMKeySync()
            result = vm_sync.ensure_key_authorized(
                "test-vm", "test-rg", "ssh-ed25519 AAAA" + ("C" * 36) + " test@host"
            )

            assert result.duration_ms >= 0


class TestCheckKeyExists:
    """Test VMKeySync.check_key_exists()."""

    def test_key_exists_returns_true(self):
        """Test returns True when key found."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0, stdout=json.dumps({"value": [{"message": "KEY_FOUND"}]})
            )

            vm_sync = VMKeySync()
            result = vm_sync.check_key_exists(
                "test-vm", "test-rg", "ssh-ed25519 AAAA" + ("C" * 36) + " test@host"
            )

            assert result is True

    def test_key_missing_returns_false(self):
        """Test returns False when key not found."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=json.dumps({"value": []}))

            vm_sync = VMKeySync()
            result = vm_sync.check_key_exists(
                "test-vm", "test-rg", "ssh-ed25519 AAAA" + ("C" * 36) + " test@host"
            )

            assert result is False


class TestAppendKeyToVM:
    """Test VMKeySync.append_key_to_vm()."""

    def test_append_succeeds(self):
        """Test key is appended successfully."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=json.dumps({"value": [{"code": "ProvisioningState/succeeded"}]}),
            )

            vm_sync = VMKeySync()
            # Should not raise
            vm_sync.append_key_to_vm(
                "test-vm", "test-rg", "ssh-ed25519 AAAA" + ("C" * 36) + " test@host"
            )

    def test_validates_key_format_before_append(self):
        """Test validates public key format."""
        vm_sync = VMKeySync()

        with pytest.raises(VMKeySyncError):
            vm_sync.append_key_to_vm("test-vm", "test-rg", "invalid-key")


class TestValidation:
    """Test input validation."""

    def test_empty_vm_name_raises_error(self):
        """Test empty VM name raises ValueError."""
        vm_sync = VMKeySync()

        with pytest.raises(ValueError, match="VM name"):
            vm_sync.ensure_key_authorized("", "rg", "ssh-ed25519 AAAA" + ("C" * 36))

    def test_empty_resource_group_raises_error(self):
        """Test empty resource group raises ValueError."""
        vm_sync = VMKeySync()

        with pytest.raises(ValueError, match="Resource group"):
            vm_sync.ensure_key_authorized("vm", "", "ssh-ed25519 AAAA" + ("C" * 36))

    def test_empty_public_key_raises_error(self):
        """Test empty public key raises ValueError."""
        vm_sync = VMKeySync()

        with pytest.raises(ValueError, match="Public key"):
            vm_sync.ensure_key_authorized("vm", "rg", "")


class TestAuditLogging:
    """Test audit logging."""

    def test_logs_successful_sync(self):
        """Test logs successful key sync operations."""
        with patch("subprocess.run") as mock_run, patch("builtins.open", mock_open()) as mock_file:
            mock_run.side_effect = [
                Mock(returncode=0, stdout=json.dumps({"value": [{"message": "KEY_NOT_FOUND"}]})),
                Mock(
                    returncode=0,
                    stdout=json.dumps({"value": [{"code": "ProvisioningState/succeeded"}]}),
                ),
            ]

            vm_sync = VMKeySync()
            vm_sync.ensure_key_authorized(
                "test-vm", "test-rg", "ssh-ed25519 AAAA" + ("C" * 36) + " test@host"
            )

            # Audit log should be written
            assert mock_file.called


# Placeholder tests for comprehensive coverage
class TestEdgeCases:
    """Test edge cases."""

    pass


class TestConfigurationIntegration:
    """Test configuration integration."""

    pass


class TestErrorMessages:
    """Test error messages."""

    pass
