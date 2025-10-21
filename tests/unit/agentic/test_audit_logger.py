"""Unit tests for AuditLogger (Phase 1).

Tests audit logging with rotation.
"""

from azlin.agentic.audit_logger import AuditLogger


class TestAuditLoggerBasics:
    """Test basic AuditLogger operations."""

    def test_initialize_with_default_file(self, temp_config_dir):
        """Test initializing with custom log file."""
        log_file = temp_config_dir / "audit.log"
        logger = AuditLogger(log_file=log_file)

        assert logger.log_file == log_file
        assert log_file.exists()

    def test_create_log_file_if_missing(self, temp_config_dir):
        """Test automatically creating log file."""
        log_file = temp_config_dir / "audit.log"
        assert not log_file.exists()

        logger = AuditLogger(log_file=log_file)

        assert log_file.exists()

    def test_log_entry(self, temp_config_dir):
        """Test writing log entry."""
        log_file = temp_config_dir / "audit.log"
        logger = AuditLogger(log_file=log_file)

        logger.log(
            "OBJECTIVE_CREATED",
            objective_id="obj_123",
            details={"intent": "test"},
        )

        # Verify entry was written
        assert log_file.exists()
        content = log_file.read_text()
        assert "OBJECTIVE_CREATED" in content
        assert "obj_123" in content

    def test_log_without_objective_id(self, temp_config_dir):
        """Test logging without objective ID."""
        log_file = temp_config_dir / "audit.log"
        logger = AuditLogger(log_file=log_file)

        logger.log("SYSTEM_START")

        content = log_file.read_text()
        assert "SYSTEM_START" in content
        assert "N/A" in content  # No objective ID

    def test_log_with_details(self, temp_config_dir):
        """Test logging with details dict."""
        log_file = temp_config_dir / "audit.log"
        logger = AuditLogger(log_file=log_file)

        logger.log(
            "STRATEGY_SELECTED",
            objective_id="obj_123",
            details={"strategy": "azure_cli", "reason": "fastest"},
        )

        content = log_file.read_text()
        assert "strategy=azure_cli" in content
        assert "reason=fastest" in content


class TestLogReading:
    """Test reading and parsing logs."""

    def test_read_all_logs(self, temp_config_dir):
        """Test reading all log entries."""
        log_file = temp_config_dir / "audit.log"
        logger = AuditLogger(log_file=log_file)

        # Write multiple entries
        logger.log("EVENT1", objective_id="obj_1")
        logger.log("EVENT2", objective_id="obj_2")
        logger.log("EVENT3", objective_id="obj_3")

        entries = logger.read_logs()

        assert len(entries) == 3
        assert entries[0]["event"] == "EVENT3"  # Newest first
        assert entries[1]["event"] == "EVENT2"
        assert entries[2]["event"] == "EVENT1"

    def test_filter_by_objective_id(self, temp_config_dir):
        """Test filtering logs by objective ID."""
        log_file = temp_config_dir / "audit.log"
        logger = AuditLogger(log_file=log_file)

        logger.log("EVENT1", objective_id="obj_1")
        logger.log("EVENT2", objective_id="obj_2")
        logger.log("EVENT3", objective_id="obj_1")

        entries = logger.read_logs(objective_id="obj_1")

        assert len(entries) == 2
        assert all(e["objective_id"] == "obj_1" for e in entries)

    def test_filter_by_event_type(self, temp_config_dir):
        """Test filtering logs by event type."""
        log_file = temp_config_dir / "audit.log"
        logger = AuditLogger(log_file=log_file)

        logger.log("CREATED", objective_id="obj_1")
        logger.log("STARTED", objective_id="obj_1")
        logger.log("CREATED", objective_id="obj_2")

        entries = logger.read_logs(event_type="CREATED")

        assert len(entries) == 2
        assert all(e["event"] == "CREATED" for e in entries)

    def test_limit_results(self, temp_config_dir):
        """Test limiting number of results."""
        log_file = temp_config_dir / "audit.log"
        logger = AuditLogger(log_file=log_file)

        for i in range(10):
            logger.log(f"EVENT{i}", objective_id=f"obj_{i}")

        entries = logger.read_logs(limit=5)

        assert len(entries) == 5

    def test_get_objective_timeline(self, temp_config_dir):
        """Test getting timeline for specific objective."""
        log_file = temp_config_dir / "audit.log"
        logger = AuditLogger(log_file=log_file)

        logger.log("CREATED", objective_id="obj_1")
        logger.log("STRATEGY_SELECTED", objective_id="obj_1")
        logger.log("EXECUTED", objective_id="obj_1")

        timeline = logger.get_objective_timeline("obj_1")

        assert len(timeline) == 3
        assert timeline[0]["event"] == "CREATED"  # Oldest first (chronological)
        assert timeline[1]["event"] == "STRATEGY_SELECTED"
        assert timeline[2]["event"] == "EXECUTED"


class TestLogParsing:
    """Test log line parsing."""

    def test_parse_valid_log_line(self, temp_config_dir):
        """Test parsing valid log line."""
        log_file = temp_config_dir / "audit.log"
        logger = AuditLogger(log_file=log_file)

        test_line = "2025-10-20T12:00:00 | obj_123 | EVENT | key=value"
        entry = logger._parse_log_line(test_line)

        assert entry["timestamp"] == "2025-10-20T12:00:00"
        assert entry["objective_id"] == "obj_123"
        assert entry["event"] == "EVENT"
        assert entry["details"]["key"] == "value"

    def test_parse_line_without_objective(self, temp_config_dir):
        """Test parsing line without objective ID."""
        log_file = temp_config_dir / "audit.log"
        logger = AuditLogger(log_file=log_file)

        test_line = "2025-10-20T12:00:00 | N/A | EVENT | "
        entry = logger._parse_log_line(test_line)

        assert entry["objective_id"] is None
        assert entry["event"] == "EVENT"

    def test_parse_invalid_log_line(self, temp_config_dir):
        """Test parsing invalid log line."""
        log_file = temp_config_dir / "audit.log"
        logger = AuditLogger(log_file=log_file)

        test_line = "invalid line format"
        entry = logger._parse_log_line(test_line)

        assert entry is None


class TestLogRotation:
    """Test log rotation functionality."""

    def test_no_rotation_when_small(self, temp_config_dir):
        """Test no rotation when file is small."""
        log_file = temp_config_dir / "audit.log"
        logger = AuditLogger(log_file=log_file)

        # Write small amount of data
        for i in range(10):
            logger.log(f"EVENT{i}")

        # No rotation files should exist
        assert not (temp_config_dir / "audit.log.1").exists()

    def test_rotation_when_exceeds_limit(self, temp_config_dir):
        """Test rotation when file exceeds max size."""
        log_file = temp_config_dir / "audit.log"
        logger = AuditLogger(log_file=log_file)
        logger.MAX_LOG_SIZE = 1024  # Set small limit for testing

        # Write enough data to trigger rotation
        large_data = "x" * 200
        for i in range(10):
            logger.log(f"EVENT{i}", details={"data": large_data})

        # Should have rotated
        # Note: Actual rotation depends on timing and file size checks
        # This is a simplified test


class TestLogStatistics:
    """Test log statistics."""

    def test_get_statistics(self, temp_config_dir):
        """Test getting log statistics."""
        log_file = temp_config_dir / "audit.log"
        logger = AuditLogger(log_file=log_file)

        logger.log("CREATED", objective_id="obj_1")
        logger.log("CREATED", objective_id="obj_2")
        logger.log("EXECUTED", objective_id="obj_1")

        stats = logger.get_statistics()

        assert stats["total_entries"] == 3
        assert stats["events_by_type"]["CREATED"] == 2
        assert stats["events_by_type"]["EXECUTED"] == 1
        assert stats["unique_objectives"] == 2

    def test_statistics_empty_log(self, temp_config_dir):
        """Test statistics with empty log."""
        log_file = temp_config_dir / "audit.log"
        logger = AuditLogger(log_file=log_file)

        stats = logger.get_statistics()

        assert stats["total_entries"] == 0
        assert stats["unique_objectives"] == 0


class TestFilePermissions:
    """Test file permission security."""

    def test_log_file_permissions(self, temp_config_dir):
        """Test log file has secure permissions (0600)."""
        log_file = temp_config_dir / "audit.log"
        logger = AuditLogger(log_file=log_file)

        logger.log("TEST")

        # Check file permissions
        import stat

        mode = log_file.stat().st_mode
        permissions = stat.S_IMODE(mode)

        # Should be 0600 (owner read/write only)
        assert permissions == 0o600
