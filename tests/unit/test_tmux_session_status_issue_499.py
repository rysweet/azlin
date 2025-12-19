"""Unit tests for tmux session connection status (Issue #499).

Tests following TDD methodology - these tests will FAIL until the feature is implemented.

Testing Coverage:
- Parser format detection (new format with attachment flag)
- Parser fallback to old format
- Correct parsing of 'attached' field from new format
- Edge cases (no sessions, malformed output, missing fields)

Feature Requirements:
- Enhanced tmux query: `tmux list-sessions -F "#{session_name}:#{session_attached}:#{session_windows}:#{session_created}"`
- Parser detects format and falls back to old parser if needed
- Display applies Rich formatting based on `attached` status
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from azlin.modules.ssh_connector import SSHConfig
from azlin.remote_exec import RemoteResult, TmuxSession, TmuxSessionExecutor


# ============================================================================
# PARSER FORMAT DETECTION TESTS (60% of unit tests)
# ============================================================================


class TestTmuxParserFormatDetection:
    """Test that parser detects new format and falls back gracefully."""

    def test_parser_detects_new_format_with_colon_separated_fields(self):
        """Test that parser detects new format (name:attached:windows:created)."""
        # New format: session_name:attached_flag:window_count:created_timestamp
        new_format_output = """dev:1:3:1697000000
prod:0:1:1697000100
staging:1:2:1697000200"""

        sessions = TmuxSessionExecutor.parse_tmux_output(new_format_output, "test-vm")

        # Should successfully parse 3 sessions
        assert len(sessions) == 3

        # First session (dev) - attached
        assert sessions[0].session_name == "dev"
        assert sessions[0].attached is True
        assert sessions[0].windows == 3
        assert sessions[0].vm_name == "test-vm"

        # Second session (prod) - not attached
        assert sessions[1].session_name == "prod"
        assert sessions[1].attached is False
        assert sessions[1].windows == 1

        # Third session (staging) - attached
        assert sessions[2].session_name == "staging"
        assert sessions[2].attached is True
        assert sessions[2].windows == 2

    def test_parser_falls_back_to_old_format(self):
        """Test that parser falls back to old format when new format not detected."""
        # Old format: "name: X windows (created Thu Oct 10 10:00:00 2024)"
        old_format_output = """dev: 3 windows (created Thu Oct 10 10:00:00 2024)
prod: 1 window (created Thu Oct 10 11:00:00 2024) (attached)"""

        sessions = TmuxSessionExecutor.parse_tmux_output(old_format_output, "test-vm")

        # Should parse using old format parser
        assert len(sessions) == 2
        assert sessions[0].session_name == "dev"
        assert sessions[0].windows == 3
        assert sessions[1].session_name == "prod"
        assert sessions[1].attached is True  # Old parser detects (attached) suffix

    def test_parser_handles_mixed_format_gracefully(self):
        """Test that parser handles mixed old/new format lines gracefully."""
        # Edge case: mix of formats (should handle gracefully)
        mixed_output = """dev:1:3:1697000000
prod: 1 window (created Thu Oct 10 11:00:00 2024)"""

        sessions = TmuxSessionExecutor.parse_tmux_output(mixed_output, "test-vm")

        # Should parse at least the valid lines
        assert len(sessions) >= 1
        # First line (new format) should parse correctly
        dev_session = next((s for s in sessions if s.session_name == "dev"), None)
        assert dev_session is not None
        assert dev_session.attached is True

    def test_parser_detects_format_by_field_count(self):
        """Test that parser uses colon count to detect format."""
        # New format has exactly 3 colons per line (4 fields)
        new_format = "session:0:2:1697000000"
        # Old format has 1 colon followed by description
        old_format = "session: 2 windows (created Thu Oct 10 10:00:00 2024)"

        new_sessions = TmuxSessionExecutor.parse_tmux_output(new_format, "vm1")
        old_sessions = TmuxSessionExecutor.parse_tmux_output(old_format, "vm2")

        # New format should parse with attached field
        assert len(new_sessions) == 1
        assert new_sessions[0].attached is False

        # Old format should parse using old logic
        assert len(old_sessions) == 1
        assert old_sessions[0].session_name == "session"


# ============================================================================
# ATTACHED FIELD PARSING TESTS (60% of unit tests)
# ============================================================================


class TestAttachedFieldParsing:
    """Test correct parsing of 'attached' field from new format."""

    def test_attached_flag_1_means_connected(self):
        """Test that attached=1 in new format means session is connected."""
        output = "connected:1:2:1697000000"

        sessions = TmuxSessionExecutor.parse_tmux_output(output, "test-vm")

        assert len(sessions) == 1
        assert sessions[0].attached is True

    def test_attached_flag_0_means_disconnected(self):
        """Test that attached=0 in new format means session is disconnected."""
        output = "disconnected:0:2:1697000000"

        sessions = TmuxSessionExecutor.parse_tmux_output(output, "test-vm")

        assert len(sessions) == 1
        assert sessions[0].attached is False

    def test_attached_flag_parsing_preserves_other_fields(self):
        """Test that parsing attached flag doesn't corrupt other fields."""
        output = "mysession:1:5:1697000000"

        sessions = TmuxSessionExecutor.parse_tmux_output(output, "test-vm")

        assert len(sessions) == 1
        assert sessions[0].session_name == "mysession"
        assert sessions[0].attached is True
        assert sessions[0].windows == 5
        assert sessions[0].vm_name == "test-vm"

    def test_multiple_sessions_with_different_attached_states(self):
        """Test parsing multiple sessions with different attached states."""
        output = """session1:1:3:1697000000
session2:0:1:1697000100
session3:1:2:1697000200
session4:0:4:1697000300"""

        sessions = TmuxSessionExecutor.parse_tmux_output(output, "test-vm")

        assert len(sessions) == 4
        assert sessions[0].attached is True  # session1
        assert sessions[1].attached is False  # session2
        assert sessions[2].attached is True  # session3
        assert sessions[3].attached is False  # session4


# ============================================================================
# EDGE CASE TESTS (60% of unit tests)
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_output_returns_empty_list(self):
        """Test that empty output returns empty list."""
        sessions = TmuxSessionExecutor.parse_tmux_output("", "test-vm")

        assert sessions == []

    def test_no_sessions_message_returns_empty_list(self):
        """Test that 'No sessions' message returns empty list."""
        sessions = TmuxSessionExecutor.parse_tmux_output("No sessions", "test-vm")

        assert sessions == []

    def test_malformed_new_format_skipped_gracefully(self):
        """Test that malformed new format lines are skipped without crashing."""
        # Missing fields (only 2 colons instead of 3)
        malformed = """bad:format:only
good:1:3:1697000000"""

        sessions = TmuxSessionExecutor.parse_tmux_output(malformed, "test-vm")

        # Should parse only the valid line
        assert len(sessions) == 1
        assert sessions[0].session_name == "good"

    def test_invalid_attached_flag_defaults_to_false(self):
        """Test that invalid attached flag (non-0/1) defaults to False."""
        output = "session:invalid:2:1697000000"

        sessions = TmuxSessionExecutor.parse_tmux_output(output, "test-vm")

        # Should handle gracefully - either skip or default to False
        if len(sessions) > 0:
            assert sessions[0].attached is False

    def test_session_name_with_colons_in_new_format(self):
        """Test that session names with colons fall back to old parser."""
        # Session name with colons - should NOT be detected as new format
        # because parts[1] is 'session' (not '0' or '1')
        output = "my:session:1:2:1697000000"

        sessions = TmuxSessionExecutor.parse_tmux_output(output, "test-vm")

        # Should fall back to old parser and skip (no "window" keyword pattern)
        # Old parser looks for specific patterns like "(attached)" which aren't present
        assert len(sessions) == 0

    def test_whitespace_handling(self):
        """Test that leading/trailing whitespace is handled correctly."""
        output = """  session1:1:3:1697000000
session2:0:1:1697000100
  """

        sessions = TmuxSessionExecutor.parse_tmux_output(output, "test-vm")

        assert len(sessions) == 2
        assert sessions[0].session_name == "session1"
        assert sessions[1].session_name == "session2"


# ============================================================================
# GET_SESSIONS_PARALLEL TESTS (60% of unit tests)
# ============================================================================


class TestGetSessionsParallelWithNewFormat:
    """Test that get_sessions_parallel uses enhanced tmux command."""

    def test_get_sessions_parallel_uses_new_format_command(self, monkeypatch):
        """Test that get_sessions_parallel executes new tmux format command."""
        from azlin.modules.ssh_connector import SSHConfig
        from azlin.remote_exec import RemoteExecutor, RemoteResult

        # Track what command was executed
        executed_command = None

        def mock_execute_parallel(ssh_configs, command, timeout=5, max_workers=10):
            nonlocal executed_command
            executed_command = command
            # Return mock results
            return [
                RemoteResult(
                    vm_name="test-vm",
                    success=True,
                    stdout="session1:1:3:1697000000",
                    stderr="",
                    exit_code=0,
                )
            ]

        monkeypatch.setattr(RemoteExecutor, "execute_parallel", mock_execute_parallel)

        # Execute
        ssh_config = SSHConfig(host="test-vm", port=22, user="test", key_path="/tmp/key")
        sessions = TmuxSessionExecutor.get_sessions_parallel([ssh_config])

        # Verify new format command was used
        assert executed_command is not None
        assert "-F" in executed_command  # Format flag
        assert "session_name" in executed_command
        assert "session_attached" in executed_command
        assert "session_windows" in executed_command
        assert "session_created" in executed_command

        # Verify parsing worked
        assert len(sessions) == 1
        assert sessions[0].attached is True
