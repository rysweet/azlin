"""Unit tests for enhanced security audit logging.

Tests the SecurityAuditLogger class that logs security events with integrity verification.
These tests follow TDD RED phase - they will fail until implementation is complete.

Coverage targets:
- Event logging to JSONL format
- Integrity checksums
- Audit log backup
- Query interface
- Compliance reporting
- File permissions (0600)
"""

import hashlib
import json
from datetime import datetime
from unittest.mock import mock_open, patch

import pytest

# Mark all tests as TDD RED phase (expected to fail)
pytestmark = [pytest.mark.unit, pytest.mark.tdd_red]


class TestAuditEventDataclass:
    """Test AuditEvent dataclass and serialization."""

    def test_audit_event_creation(self):
        """AuditEvent should be created with all required fields."""
        from azlin.network_security.security_audit import AuditEvent, AuditEventType

        event = AuditEvent(
            event_id="test-123",
            timestamp=datetime.now(),
            event_type=AuditEventType.BASTION_TUNNEL_CREATE,
            user="test-user",
            resource="test-bastion",
            action="create_tunnel",
            outcome="success",
            details={"port": 50000},
            severity="info",
            compliance_tags=["SOC2-CC6.6"],
        )

        assert event.event_id == "test-123"
        assert event.user == "test-user"
        assert event.outcome == "success"

    def test_audit_event_to_dict(self):
        """AuditEvent should serialize to dictionary correctly."""
        from azlin.network_security.security_audit import AuditEvent, AuditEventType

        timestamp = datetime.now()
        event = AuditEvent(
            event_id="test-123",
            timestamp=timestamp,
            event_type=AuditEventType.NSG_RULE_APPLY,
            user="test-user",
            resource="test-nsg",
            action="apply_template",
            outcome="success",
            details={"template": "web-server.yaml"},
            severity="info",
            compliance_tags=["CIS-6.2"],
        )

        event_dict = event.to_dict()

        assert event_dict["event_id"] == "test-123"
        assert event_dict["user"] == "test-user"
        assert "Z" in event_dict["timestamp"]  # UTC timezone


class TestSecurityAuditLoggerInitialization:
    """Test SecurityAuditLogger initialization and directory setup."""

    @patch("pathlib.Path.mkdir")
    @patch("os.chmod")
    def test_logger_creates_audit_directory(self, mock_chmod, mock_mkdir):
        """Logger should create audit directory with secure permissions."""
        from azlin.network_security.security_audit import SecurityAuditLogger

        logger = SecurityAuditLogger()

        # Should create both audit file parent and backup directories
        assert mock_mkdir.call_count >= 2
        # Should set directory permissions to 0o700 (owner-only)
        assert any(call[0][1] == 0o700 for call in mock_chmod.call_args_list)

    def test_audit_file_path_in_home_directory(self):
        """Audit file should be in ~/.azlin/security_audit.jsonl."""
        from azlin.network_security.security_audit import SecurityAuditLogger

        logger = SecurityAuditLogger()

        assert ".azlin" in str(logger.AUDIT_FILE)
        assert "security_audit.jsonl" in str(logger.AUDIT_FILE)


class TestSecurityAuditLoggerEventLogging:
    """Test event logging to JSONL format."""

    @patch("builtins.open", new_callable=mock_open)
    @patch("os.chmod")
    def test_log_event_writes_jsonl_format(self, mock_chmod, mock_file):
        """Events should be logged in JSONL format (one JSON per line)."""
        from azlin.network_security.security_audit import (
            AuditEvent,
            AuditEventType,
            SecurityAuditLogger,
        )

        logger = SecurityAuditLogger()
        event = AuditEvent(
            event_id="test-123",
            timestamp=datetime.now(),
            event_type=AuditEventType.BASTION_TUNNEL_CREATE,
            user="test-user",
            resource="test-bastion",
            action="create_tunnel",
            outcome="success",
            details={},
            severity="info",
            compliance_tags=[],
        )

        logger.log_event(event)

        # Verify file was opened in append mode
        mock_file.assert_called()
        # Verify JSON was written with newline
        written_data = "".join(call[0][0] for call in mock_file().write.call_args_list)
        assert written_data.endswith("\n")

    @patch("builtins.open", new_callable=mock_open)
    @patch("os.chmod")
    def test_log_event_sets_secure_permissions(self, mock_chmod, mock_file):
        """Audit log file should have 0600 permissions (owner-only)."""
        from azlin.network_security.security_audit import (
            AuditEvent,
            AuditEventType,
            SecurityAuditLogger,
        )

        logger = SecurityAuditLogger()
        event = AuditEvent(
            event_id="test-123",
            timestamp=datetime.now(),
            event_type=AuditEventType.BASTION_TUNNEL_CREATE,
            user="test-user",
            resource="test-bastion",
            action="create_tunnel",
            outcome="success",
            details={},
            severity="info",
            compliance_tags=[],
        )

        logger.log_event(event)

        # Verify file permissions set to 0o600
        assert any(call[0][1] == 0o600 for call in mock_chmod.call_args_list)


class TestSecurityAuditLoggerIntegrityVerification:
    """Test integrity checksums and tamper detection."""

    def test_compute_checksum_generates_sha256(self):
        """Checksum should be SHA256 hash of event data."""
        from azlin.network_security.security_audit import SecurityAuditLogger

        logger = SecurityAuditLogger()
        event_dict = {
            "event_id": "test-123",
            "timestamp": "2025-12-01T12:00:00Z",
            "user": "test-user",
        }

        checksum = logger._compute_checksum(event_dict)

        # SHA256 produces 64-character hex string
        assert len(checksum) == 64
        assert all(c in "0123456789abcdef" for c in checksum)

    def test_compute_checksum_excludes_checksum_field(self):
        """Checksum computation should exclude checksum field itself."""
        from azlin.network_security.security_audit import SecurityAuditLogger

        logger = SecurityAuditLogger()
        event_dict = {
            "event_id": "test-123",
            "timestamp": "2025-12-01T12:00:00Z",
            "checksum": "old-checksum",
        }

        checksum = logger._compute_checksum(event_dict)

        # Verify checksum field was excluded
        event_json = json.dumps(
            {k: v for k, v in event_dict.items() if k != "checksum"},
            sort_keys=True,
        )
        expected = hashlib.sha256(event_json.encode()).hexdigest()
        assert checksum == expected

    @patch("pathlib.Path.exists", return_value=True)
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='{"event_id": "1", "checksum": "abc123"}\n',
    )
    def test_verify_integrity_detects_corrupted_events(self, mock_file, mock_exists):
        """Integrity verification should detect corrupted events."""
        from azlin.network_security.security_audit import SecurityAuditLogger

        logger = SecurityAuditLogger()

        with patch.object(logger, "_compute_checksum", return_value="different-checksum"):
            is_valid, corrupted = logger.verify_integrity()

        assert is_valid is False
        assert len(corrupted) > 0

    @patch("pathlib.Path.exists", return_value=True)
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='{"event_id": "1", "checksum": "valid-checksum"}\n',
    )
    def test_verify_integrity_passes_for_valid_events(self, mock_file, mock_exists):
        """Integrity verification should pass for valid events."""
        from azlin.network_security.security_audit import SecurityAuditLogger

        logger = SecurityAuditLogger()

        with patch.object(logger, "_compute_checksum", return_value="valid-checksum"):
            is_valid, corrupted = logger.verify_integrity()

        assert is_valid is True
        assert len(corrupted) == 0


class TestSecurityAuditLoggerBackup:
    """Test audit log backup functionality."""

    def test_should_backup_returns_true_after_24_hours(self):
        """Backup should be triggered after 24 hours."""
        from azlin.network_security.security_audit import SecurityAuditLogger

        logger = SecurityAuditLogger()

        with patch("pathlib.Path.exists", return_value=True):
            with patch("os.path.getmtime") as mock_mtime:
                # Mock file modified 25 hours ago
                mock_mtime.return_value = datetime.now().timestamp() - 90000

                result = logger._should_backup()

        assert result is True

    def test_should_backup_returns_false_within_24_hours(self):
        """Backup should not be triggered within 24 hours."""
        from azlin.network_security.security_audit import SecurityAuditLogger

        logger = SecurityAuditLogger()

        with patch("pathlib.Path.exists", return_value=True):
            with patch("os.path.getmtime") as mock_mtime:
                # Mock file modified 1 hour ago
                mock_mtime.return_value = datetime.now().timestamp() - 3600

                result = logger._should_backup()

        assert result is False

    def test_backup_audit_log_creates_timestamped_backup(self, tmp_path):
        """Backup should create timestamped copy with secure permissions."""
        from azlin.network_security.security_audit import SecurityAuditLogger

        # Create actual audit file in temp directory
        audit_file = tmp_path / "security_audit.jsonl"
        audit_file.write_text('{"event_id": "test", "timestamp": "2025-12-01T12:00:00Z"}\n')

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        with patch("azlin.network_security.security_audit.SecurityAuditLogger.AUDIT_FILE", audit_file):
            with patch("azlin.network_security.security_audit.SecurityAuditLogger.BACKUP_DIR", backup_dir):
                with patch("azlin.network_security.security_audit.datetime") as mock_datetime:
                    # Mock datetime.now(UTC).strftime()
                    mock_datetime.now.return_value.strftime.return_value = "20251201_120000"

                    logger = SecurityAuditLogger()
                    logger._backup_audit_log()

                    # Verify backup was created
                    backup_file = backup_dir / "security_audit_20251201_120000.jsonl"
                    assert backup_file.exists()

                    # Verify backup has correct permissions (0o600)
                    import stat
                    assert stat.S_IMODE(backup_file.stat().st_mode) == 0o600


class TestSecurityAuditLoggerQueryInterface:
    """Test querying audit logs with filters."""

    @patch("pathlib.Path.exists", return_value=True)
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='{"event_id": "1", "event_type": "bastion_tunnel_create", "user": "alice", "resource": "bastion-1", "action": "create_tunnel", "outcome": "success", "timestamp": "2025-12-01T12:00:00Z", "severity": "info"}\n{"event_id": "2", "event_type": "nsg_rule_apply", "user": "bob", "resource": "nsg-1", "action": "apply_rule", "outcome": "success", "timestamp": "2025-12-02T12:00:00Z", "severity": "warning"}\n',
    )
    def test_query_events_filters_by_event_type(self, mock_file, mock_exists):
        """Query should filter events by event_type."""
        from azlin.network_security.security_audit import (
            AuditEventType,
            SecurityAuditLogger,
        )

        logger = SecurityAuditLogger()

        events = logger.query_events(event_type=AuditEventType.BASTION_TUNNEL_CREATE)

        assert len(events) == 1
        assert events[0].event_type == AuditEventType.BASTION_TUNNEL_CREATE

    @patch("pathlib.Path.exists", return_value=True)
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='{"event_id": "1", "event_type": "bastion_tunnel_create", "user": "alice", "resource": "bastion-1", "action": "create_tunnel", "outcome": "success", "timestamp": "2025-12-01T12:00:00Z", "severity": "info"}\n{"event_id": "2", "event_type": "nsg_rule_apply", "user": "bob", "resource": "nsg-1", "action": "apply_rule", "outcome": "success", "timestamp": "2025-12-02T12:00:00Z", "severity": "warning"}\n',
    )
    def test_query_events_filters_by_user(self, mock_file, mock_exists):
        """Query should filter events by user."""
        from azlin.network_security.security_audit import SecurityAuditLogger

        logger = SecurityAuditLogger()

        events = logger.query_events(user="alice")

        assert len(events) == 1
        assert events[0].user == "alice"

    @patch("pathlib.Path.exists", return_value=True)
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='{"event_id": "1", "event_type": "bastion_tunnel_create", "user": "alice", "resource": "bastion-1", "action": "create_tunnel", "outcome": "success", "timestamp": "2025-12-01T12:00:00Z", "severity": "critical"}\n{"event_id": "2", "event_type": "nsg_rule_apply", "user": "bob", "resource": "nsg-1", "action": "apply_rule", "outcome": "success", "timestamp": "2025-12-02T12:00:00Z", "severity": "info"}\n',
    )
    def test_query_events_filters_by_severity(self, mock_file, mock_exists):
        """Query should filter events by severity."""
        from azlin.network_security.security_audit import SecurityAuditLogger

        logger = SecurityAuditLogger()

        events = logger.query_events(severity="critical")

        assert len(events) == 1
        assert events[0].severity == "critical"

    @patch("pathlib.Path.exists", return_value=True)
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='{"event_id": "1", "event_type": "bastion_tunnel_create", "user": "alice", "resource": "bastion-1", "action": "create_tunnel", "outcome": "success", "timestamp": "2025-12-01T12:00:00Z", "severity": "info"}\n{"event_id": "2", "event_type": "nsg_rule_apply", "user": "bob", "resource": "nsg-1", "action": "apply_rule", "outcome": "success", "timestamp": "2025-12-03T12:00:00Z", "severity": "warning"}\n',
    )
    def test_query_events_filters_by_time_range(self, mock_file, mock_exists):
        """Query should filter events by start_time and end_time."""
        from azlin.network_security.security_audit import SecurityAuditLogger

        logger = SecurityAuditLogger()

        start = datetime(2025, 12, 2)
        end = datetime(2025, 12, 4)

        events = logger.query_events(start_time=start, end_time=end)

        assert len(events) == 1
        assert events[0].event_id == "2"


class TestSecurityAuditLoggerComplianceReporting:
    """Test compliance report generation."""

    @patch("pathlib.Path.exists", return_value=True)
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='{"event_id": "1", "event_type": "nsg_rule_apply", "user": "alice", "resource": "nsg-1", "action": "apply", "outcome": "success", "details": {}, "timestamp": "2025-11-15T12:00:00Z", "severity": "info", "compliance_tags": ["CIS-6.2", "SOC2-CC6.6"]}\n{"event_id": "2", "event_type": "policy_violation", "user": "bob", "resource": "nsg-2", "action": "attempt", "outcome": "blocked", "details": {}, "timestamp": "2025-11-20T12:00:00Z", "severity": "critical", "compliance_tags": ["CIS-6.1"]}\n',
    )
    def test_generate_compliance_report_filters_by_framework(self, mock_file, mock_exists):
        """Compliance report should filter events by framework tags."""
        from azlin.network_security.security_audit import SecurityAuditLogger

        logger = SecurityAuditLogger()

        report = logger.generate_compliance_report(
            framework="CIS",
            start_date=datetime(2025, 11, 1),
            end_date=datetime(2025, 11, 30),
        )

        assert report["framework"] == "CIS"
        assert report["total_events"] == 2  # Both events have CIS tags

    @patch("pathlib.Path.exists", return_value=True)
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='{"event_id": "1", "event_type": "nsg_rule_apply", "user": "alice", "resource": "nsg-1", "action": "apply", "outcome": "success", "details": {}, "timestamp": "2025-11-15T12:00:00Z", "severity": "info", "compliance_tags": ["CIS-6.2"]}\n{"event_id": "2", "event_type": "policy_violation", "user": "bob", "resource": "nsg-2", "action": "attempt", "outcome": "blocked", "details": {}, "timestamp": "2025-11-20T12:00:00Z", "severity": "critical", "compliance_tags": ["CIS-6.1"]}\n',
    )
    def test_generate_compliance_report_counts_critical_findings(self, mock_file, mock_exists):
        """Compliance report should count critical findings."""
        from azlin.network_security.security_audit import SecurityAuditLogger

        logger = SecurityAuditLogger()

        report = logger.generate_compliance_report(
            framework="CIS",
            start_date=datetime(2025, 11, 1),
            end_date=datetime(2025, 11, 30),
        )

        assert report["critical_findings"] == 1  # Only event 2 is critical

    @patch("pathlib.Path.exists", return_value=True)
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='{"event_id": "1", "event_type": "policy_violation", "user": "alice", "resource": "nsg-1", "action": "attempt", "outcome": "blocked", "details": {}, "timestamp": "2025-11-15T12:00:00Z", "severity": "critical", "compliance_tags": ["SOC2-CC6.6"]}\n{"event_id": "2", "event_type": "policy_violation", "user": "bob", "resource": "nsg-2", "action": "attempt", "outcome": "blocked", "details": {}, "timestamp": "2025-11-20T12:00:00Z", "severity": "critical", "compliance_tags": ["SOC2-CC6.7"]}\n',
    )
    def test_generate_compliance_report_counts_policy_violations(self, mock_file, mock_exists):
        """Compliance report should count policy violations."""
        from azlin.network_security.security_audit import (
            SecurityAuditLogger,
        )

        logger = SecurityAuditLogger()

        report = logger.generate_compliance_report(
            framework="SOC2",
            start_date=datetime(2025, 11, 1),
            end_date=datetime(2025, 11, 30),
        )

        assert report["policy_violations"] == 2
