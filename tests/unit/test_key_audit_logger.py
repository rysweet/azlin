"""Unit tests for key_audit_logger module.

Tests verify comprehensive SSH key audit logging functionality:
- Key generation logging
- Key rotation logging with success/failure tracking
- Key access logging
- Key deletion logging
- Key backup logging
- VM key update logging
- Permission fix logging
- Tamper-evident log integrity
- Compliance reporting
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.modules.key_audit_logger import KeyAuditLogger, SSHKeyEventType


class TestKeyAuditLogger:
    """Tests for KeyAuditLogger class."""

    @pytest.fixture
    def audit_logger(self, tmp_path, monkeypatch):
        """Create audit logger with temporary audit file."""
        audit_file = tmp_path / ".azlin" / "security_audit.jsonl"
        backup_dir = tmp_path / ".azlin" / "audit_backups"

        audit_file.parent.mkdir(parents=True, exist_ok=True)
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Monkeypatch SecurityAuditLogger paths
        with patch("azlin.modules.key_audit_logger.SecurityAuditLogger") as mock_logger_class:
            mock_logger = MagicMock()
            mock_logger.AUDIT_FILE = audit_file
            mock_logger.BACKUP_DIR = backup_dir
            mock_logger.verify_integrity.return_value = (True, [])
            mock_logger_class.return_value = mock_logger

            logger = KeyAuditLogger()
            logger._audit_logger = mock_logger

            yield logger, mock_logger

    def test_log_key_generation_creates_audit_entry(self, audit_logger):
        """Test that key generation creates audit entry."""
        logger, mock_audit = audit_logger

        logger.log_key_generation(
            vm_name="test-vm", key_path=Path("/home/user/.ssh/azlin_key"), algorithm="ed25519"
        )

        # Verify log_event was called
        mock_audit.log_event.assert_called_once()
        event = mock_audit.log_event.call_args[0][0]

        # Verify event structure
        assert event.resource == "test-vm"
        assert event.action == "generate_ssh_key"
        assert event.outcome == "success"
        assert event.details["algorithm"] == "ed25519"
        assert event.details["key_path"] == "/home/user/.ssh/azlin_key"
        assert "SOC2" in event.compliance_tags
        assert "ISO27001" in event.compliance_tags

    def test_log_key_generation_with_custom_user(self, audit_logger):
        """Test key generation logging with custom user."""
        logger, mock_audit = audit_logger

        logger.log_key_generation(
            vm_name="test-vm",
            key_path=Path("/home/user/.ssh/azlin_key"),
            user="custom_user",
        )

        event = mock_audit.log_event.call_args[0][0]
        assert event.user == "custom_user"

    def test_log_key_rotation_success(self, audit_logger):
        """Test successful key rotation logging."""
        logger, mock_audit = audit_logger

        logger.log_key_rotation(
            resource_group="my-rg",
            success=True,
            vms_updated=["vm1", "vm2", "vm3"],
            vms_failed=[],
            new_key_path=Path("/home/user/.ssh/azlin_key_new"),
            backup_path=Path("/home/user/.azlin/key_backups/20250101"),
        )

        event = mock_audit.log_event.call_args[0][0]
        assert event.resource == "my-rg"
        assert event.action == "rotate_ssh_keys"
        assert event.outcome == "success"
        assert event.severity == "info"
        assert event.details["vms_updated_count"] == 3
        assert event.details["vms_failed_count"] == 0
        assert "KEY_ROTATION" in event.compliance_tags

    def test_log_key_rotation_failure(self, audit_logger):
        """Test failed key rotation logging."""
        logger, mock_audit = audit_logger

        logger.log_key_rotation(
            resource_group="my-rg",
            success=False,
            vms_updated=["vm1"],
            vms_failed=["vm2", "vm3"],
            new_key_path=Path("/home/user/.ssh/azlin_key_new"),
        )

        event = mock_audit.log_event.call_args[0][0]
        assert event.outcome == "failure"
        assert event.severity == "critical"
        assert event.details["vms_updated_count"] == 1
        assert event.details["vms_failed_count"] == 2
        assert "vm2" in event.details["vms_failed"]
        assert "vm3" in event.details["vms_failed"]

    def test_log_key_rotation_partial_failure(self, audit_logger):
        """Test partial key rotation failure logging."""
        logger, mock_audit = audit_logger

        logger.log_key_rotation(
            resource_group="my-rg",
            success=True,  # Overall success despite some failures
            vms_updated=["vm1", "vm2"],
            vms_failed=["vm3"],  # One failure
        )

        event = mock_audit.log_event.call_args[0][0]
        assert event.outcome == "success"
        assert event.severity == "warning"  # Partial failure gets warning

    def test_log_key_access(self, audit_logger):
        """Test key access logging."""
        logger, mock_audit = audit_logger

        logger.log_key_access(
            vm_name="test-vm",
            key_path=Path("/home/user/.ssh/azlin_key"),
            operation="read_public_key",
        )

        event = mock_audit.log_event.call_args[0][0]
        assert event.resource == "test-vm"
        assert event.action == "access_ssh_key_read_public_key"
        assert event.details["operation"] == "read_public_key"
        assert event.severity == "info"

    def test_log_key_deletion(self, audit_logger):
        """Test key deletion logging."""
        logger, mock_audit = audit_logger

        logger.log_key_deletion(
            vm_name="test-vm",
            key_path=Path("/home/user/.ssh/azlin_key_old"),
            reason="key_rotation_cleanup",
        )

        event = mock_audit.log_event.call_args[0][0]
        assert event.resource == "test-vm"
        assert event.action == "delete_ssh_key"
        assert event.details["reason"] == "key_rotation_cleanup"
        assert event.severity == "warning"  # Deletion is notable

    def test_log_key_backup(self, audit_logger):
        """Test key backup logging."""
        logger, mock_audit = audit_logger

        logger.log_key_backup(
            backup_dir=Path("/home/user/.azlin/key_backups/20250101"), key_count=2
        )

        event = mock_audit.log_event.call_args[0][0]
        assert event.resource == "ssh_keys"
        assert event.action == "backup_ssh_keys"
        assert event.details["key_count"] == 2
        assert "KEY_ROTATION" in event.compliance_tags

    def test_log_vm_key_update_success(self, audit_logger):
        """Test successful VM key update logging."""
        logger, mock_audit = audit_logger

        logger.log_vm_key_update(vm_name="test-vm", resource_group="my-rg", success=True)

        event = mock_audit.log_event.call_args[0][0]
        assert event.resource == "test-vm"
        assert event.action == "update_vm_ssh_key"
        assert event.outcome == "success"
        assert event.severity == "info"
        assert event.details["resource_group"] == "my-rg"

    def test_log_vm_key_update_failure(self, audit_logger):
        """Test failed VM key update logging."""
        logger, mock_audit = audit_logger

        logger.log_vm_key_update(
            vm_name="test-vm",
            resource_group="my-rg",
            success=False,
            error="VM not found",
        )

        event = mock_audit.log_event.call_args[0][0]
        assert event.outcome == "failure"
        assert event.severity == "critical"
        assert event.details["error"] == "VM not found"

    def test_log_permission_fix(self, audit_logger):
        """Test permission fix logging."""
        logger, mock_audit = audit_logger

        logger.log_permission_fix(
            key_path=Path("/home/user/.ssh/azlin_key"),
            old_permissions="0o644",
            new_permissions="0o600",
        )

        event = mock_audit.log_event.call_args[0][0]
        assert event.action == "fix_ssh_key_permissions"
        assert event.details["old_permissions"] == "0o644"
        assert event.details["new_permissions"] == "0o600"
        assert event.severity == "warning"  # Insecure permissions are notable
        assert "SECURITY" in event.compliance_tags

    def test_generate_compliance_report(self, audit_logger):
        """Test compliance report generation."""
        logger, mock_audit = audit_logger

        start_date = datetime.now(UTC) - timedelta(days=30)
        end_date = datetime.now(UTC)

        mock_audit.generate_compliance_report.return_value = {
            "framework": "SOC2",
            "total_events": 42,
            "critical_findings": 2,
        }

        report = logger.generate_compliance_report("SOC2", start_date, end_date)

        mock_audit.generate_compliance_report.assert_called_once_with("SOC2", start_date, end_date)
        assert report["framework"] == "SOC2"
        assert report["total_events"] == 42

    def test_verify_integrity(self, audit_logger):
        """Test audit log integrity verification."""
        logger, mock_audit = audit_logger

        mock_audit.verify_integrity.return_value = (True, [])

        is_valid, corrupted = logger.verify_integrity()

        mock_audit.verify_integrity.assert_called_once()
        assert is_valid is True
        assert corrupted == []

    def test_verify_integrity_with_corruption(self, audit_logger):
        """Test integrity verification with corrupted events."""
        logger, mock_audit = audit_logger

        mock_audit.verify_integrity.return_value = (False, ["event_1", "event_2"])

        is_valid, corrupted = logger.verify_integrity()

        assert is_valid is False
        assert len(corrupted) == 2
        assert "event_1" in corrupted

    def test_event_id_generation(self, audit_logger):
        """Test unique event ID generation."""
        logger, mock_audit = audit_logger

        logger.log_key_generation(
            vm_name="vm1", key_path=Path("/home/user/.ssh/key1"), algorithm="ed25519"
        )
        event1 = mock_audit.log_event.call_args[0][0]

        logger.log_key_generation(
            vm_name="vm2", key_path=Path("/home/user/.ssh/key2"), algorithm="ed25519"
        )
        event2 = mock_audit.log_event.call_args[0][0]

        # Event IDs should be unique
        assert event1.event_id != event2.event_id
        assert event1.event_id.startswith("key_gen_")
        assert event2.event_id.startswith("key_gen_")

    def test_custom_details(self, audit_logger):
        """Test logging with custom details."""
        logger, mock_audit = audit_logger

        custom_details = {"custom_field": "custom_value", "operation_id": "12345"}

        logger.log_key_generation(
            vm_name="test-vm",
            key_path=Path("/home/user/.ssh/azlin_key"),
            details=custom_details,
        )

        event = mock_audit.log_event.call_args[0][0]
        assert event.details["custom_field"] == "custom_value"
        assert event.details["operation_id"] == "12345"
        assert event.details["algorithm"] == "ed25519"  # Default still present

    def test_default_user_detection(self, audit_logger, monkeypatch):
        """Test default user detection from environment."""
        logger, mock_audit = audit_logger

        monkeypatch.setenv("USER", "testuser")

        logger.log_key_generation(vm_name="test-vm", key_path=Path("/home/user/.ssh/azlin_key"))

        event = mock_audit.log_event.call_args[0][0]
        assert event.user == "testuser"

    def test_timestamp_format(self, audit_logger):
        """Test that timestamps are in correct UTC format."""
        logger, mock_audit = audit_logger

        logger.log_key_generation(vm_name="test-vm", key_path=Path("/home/user/.ssh/azlin_key"))

        event = mock_audit.log_event.call_args[0][0]
        assert event.timestamp.tzinfo is not None  # Timezone-aware
        assert event.timestamp.tzinfo == UTC


class TestSSHKeyEventType:
    """Tests for SSHKeyEventType enumeration."""

    def test_event_types_defined(self):
        """Test that all SSH key event types are defined."""
        assert hasattr(SSHKeyEventType, "SSH_KEY_GENERATE")
        assert hasattr(SSHKeyEventType, "SSH_KEY_ROTATE")
        assert hasattr(SSHKeyEventType, "SSH_KEY_ACCESS")
        assert hasattr(SSHKeyEventType, "SSH_KEY_DELETE")
        assert hasattr(SSHKeyEventType, "SSH_KEY_BACKUP")
        assert hasattr(SSHKeyEventType, "SSH_KEY_UPDATE_VM")
        assert hasattr(SSHKeyEventType, "SSH_KEY_PERMISSION_FIX")

    def test_event_type_values(self):
        """Test event type string values."""
        assert SSHKeyEventType.SSH_KEY_GENERATE == "ssh_key_generate"
        assert SSHKeyEventType.SSH_KEY_ROTATE == "ssh_key_rotate"
        assert SSHKeyEventType.SSH_KEY_ACCESS == "ssh_key_access"
        assert SSHKeyEventType.SSH_KEY_DELETE == "ssh_key_delete"
        assert SSHKeyEventType.SSH_KEY_BACKUP == "ssh_key_backup"
        assert SSHKeyEventType.SSH_KEY_UPDATE_VM == "ssh_key_update_vm"
        assert SSHKeyEventType.SSH_KEY_PERMISSION_FIX == "ssh_key_permission_fix"
