"""Comprehensive tests for stop hook."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Import the module under test
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from stop import StopHook


class TestStopHook:
    """Tests for StopHook class."""

    @pytest.fixture
    def temp_project_root(self):
        """Create a temporary project root directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # Create .claude structure
            claude_dir = root / ".claude" / "tools" / "amplihack"
            claude_dir.mkdir(parents=True)
            runtime_dir = root / ".claude" / "runtime"
            (runtime_dir / "logs").mkdir(parents=True)
            (runtime_dir / "metrics").mkdir(parents=True)
            (runtime_dir / "analysis").mkdir(parents=True)
            yield root

    @pytest.fixture
    def stop_hook(self, temp_project_root):
        """Create StopHook instance with mocked project root."""
        with patch.object(StopHook, "__init__", lambda self: None):
            hook = StopHook()
            hook.hook_name = "stop"
            hook.project_root = temp_project_root
            hook.log_dir = temp_project_root / ".claude" / "runtime" / "logs"
            hook.metrics_dir = temp_project_root / ".claude" / "runtime" / "metrics"
            hook.analysis_dir = temp_project_root / ".claude" / "runtime" / "analysis"
            hook.log_file = hook.log_dir / "stop.log"
            hook.lock_flag = temp_project_root / ".claude" / "tools" / "amplihack" / ".lock_active"
            return hook

    def test_process_lock_exists(self, stop_hook):
        """Test process returns block decision when lock exists."""
        # Create lock file
        stop_hook.lock_flag.touch()

        result = stop_hook.process({})

        assert result["decision"] == "block"
        assert "continue" in result
        assert result["continue"] is True
        assert "reason" in result

    def test_process_no_lock(self, stop_hook):
        """Test process returns allow decision when no lock."""
        # Ensure lock doesn't exist
        if stop_hook.lock_flag.exists():
            stop_hook.lock_flag.unlink()

        result = stop_hook.process({})

        assert result["decision"] == "allow"
        assert result["continue"] is False

    def test_process_lock_permission_error(self, stop_hook):
        """Test process handles permission errors gracefully."""
        with patch.object(Path, "exists", side_effect=PermissionError("Access denied")):
            result = stop_hook.process({})

            # Should fail-safe to allow
            assert result["decision"] == "allow"
            assert result["continue"] is False

    def test_display_decision_summary_no_file(self, stop_hook):
        """Test display_decision_summary returns empty when no file exists."""
        result = stop_hook.display_decision_summary("nonexistent_session")

        assert result == ""

    def test_display_decision_summary_with_session_id(self, stop_hook, temp_project_root):
        """Test display_decision_summary with specific session ID."""
        # Create session-specific DECISIONS.md
        session_id = "test_session_123"
        session_dir = temp_project_root / ".claude" / "runtime" / "logs" / session_id
        session_dir.mkdir(parents=True)
        decisions_file = session_dir / "DECISIONS.md"

        decisions_content = """# Decisions

## Decision: Implemented feature X using approach Y
## Decision: Fixed bug in module Z by refactoring
## Decision: Added tests for functionality W
"""
        decisions_file.write_text(decisions_content)

        result = stop_hook.display_decision_summary(session_id)

        assert result != ""
        assert "Decision Records Summary" in result
        assert "Total Decisions: 3" in result
        assert "file://" in result
        assert decisions_file.name in result

    def test_display_decision_summary_finds_most_recent(self, stop_hook, temp_project_root):
        """Test display_decision_summary finds most recent when no session_id."""
        logs_dir = temp_project_root / ".claude" / "runtime" / "logs"

        # Create two session directories with DECISIONS.md
        session1_dir = logs_dir / "session_001"
        session1_dir.mkdir(parents=True)
        decisions1 = session1_dir / "DECISIONS.md"
        decisions1.write_text("## Decision: Old decision")

        session2_dir = logs_dir / "session_002"
        session2_dir.mkdir(parents=True)
        decisions2 = session2_dir / "DECISIONS.md"
        decisions2.write_text("## Decision: Recent decision")

        # Make session2 newer by updating timestamp
        import time

        time.sleep(0.01)
        decisions2.touch()

        result = stop_hook.display_decision_summary()

        assert result != ""
        assert "Recent decision" in result or "Total Decisions: 1" in result

    def test_display_decision_summary_no_decisions(self, stop_hook, temp_project_root):
        """Test display_decision_summary with empty file."""
        session_dir = temp_project_root / ".claude" / "runtime" / "logs" / "empty_session"
        session_dir.mkdir(parents=True)
        decisions_file = session_dir / "DECISIONS.md"
        decisions_file.write_text("# Decisions\n\n")

        result = stop_hook.display_decision_summary("empty_session")

        assert result == ""  # No decisions to display

    def test_display_decision_summary_preview_truncation(self, stop_hook, temp_project_root):
        """Test that long decisions are truncated in preview."""
        session_dir = temp_project_root / ".claude" / "runtime" / "logs" / "long_session"
        session_dir.mkdir(parents=True)
        decisions_file = session_dir / "DECISIONS.md"

        # Create a very long decision
        long_text = "A" * 100
        decisions_file.write_text(f"## Decision: {long_text}")

        result = stop_hook.display_decision_summary("long_session")

        assert result != ""
        # Should be truncated to 80 chars + "..."
        assert "..." in result

    def test_extract_learnings_with_reflection(self, stop_hook):
        """Test extract_learnings uses reflection module when available."""
        # Create messages that will trigger patterns
        messages = []
        for i in range(5):
            messages.append({"role": "assistant", "content": "<function_calls><Bash>cmd</Bash></function_calls>"})

        learnings = stop_hook.extract_learnings(messages)

        # Should detect repeated bash usage
        assert len(learnings) > 0
        assert any(l["type"] == "repeated_tool_use" for l in learnings)

    def test_extract_learnings_fallback(self, stop_hook):
        """Test extract_learnings falls back to simple extraction when import fails."""
        messages = [
            {"role": "user", "content": "I discovered that the issue was in the config"},
            {"role": "assistant", "content": "The solution was to update the settings"},
        ]

        # Mock the import to raise ImportError at import time
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "reflection":
                raise ImportError("Module not found")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            learnings = stop_hook.extract_learnings(messages)

            assert len(learnings) > 0
            assert any("discovered" in l.get("keyword", "") for l in learnings)

    def test_extract_learnings_simple(self, stop_hook):
        """Test simple fallback learning extraction."""
        messages = [
            {"role": "user", "content": "I learned that Python uses indentation"},
            {"role": "assistant", "content": "We found that the API requires authentication"},
            {"role": "user", "content": "The issue was a missing import"},
            {"role": "assistant", "content": "The solution was to add the dependency"},
        ]

        learnings = stop_hook.extract_learnings_simple(messages)

        assert len(learnings) > 0
        keywords_found = {l["keyword"] for l in learnings}
        assert any(kw in ["learned", "found that", "issue was", "solution was"] for kw in keywords_found)

    def test_get_priority_emoji(self, stop_hook):
        """Test priority emoji mapping."""
        assert stop_hook.get_priority_emoji("high") == "🔴"
        assert stop_hook.get_priority_emoji("HIGH") == "🔴"
        assert stop_hook.get_priority_emoji("medium") == "🟡"
        assert stop_hook.get_priority_emoji("low") == "🟢"
        assert stop_hook.get_priority_emoji("unknown") == "⚪"

    def test_extract_recommendations_from_patterns(self, stop_hook):
        """Test extracting top recommendations from patterns."""
        patterns = [
            {"type": "issue1", "priority": "low", "suggestion": "Fix this"},
            {"type": "issue2", "priority": "high", "suggestion": "Critical fix"},
            {"type": "issue3", "priority": "medium", "suggestion": "Improve that"},
            {"type": "issue4", "priority": "high", "suggestion": "Important change"},
        ]

        recommendations = stop_hook.extract_recommendations_from_patterns(patterns, limit=2)

        assert len(recommendations) == 2
        # Should be sorted by priority (high first)
        assert recommendations[0]["priority"] == "high"
        assert recommendations[1]["priority"] == "high"

    def test_extract_recommendations_empty(self, stop_hook):
        """Test recommendations extraction with empty patterns."""
        assert stop_hook.extract_recommendations_from_patterns([]) == []

    def test_format_recommendations_message(self, stop_hook):
        """Test formatting recommendations as readable message."""
        recommendations = [
            {"type": "repeated_bash", "priority": "high", "suggestion": "Create automation script"},
            {"type": "error_pattern", "priority": "medium", "suggestion": "Add error handling"},
        ]

        message = stop_hook.format_recommendations_message(recommendations)

        assert message != ""
        assert "Improvement Recommendations" in message
        assert "🔴" in message  # High priority emoji
        assert "🟡" in message  # Medium priority emoji
        assert "repeated_bash" in message
        assert "Create automation script" in message

    def test_format_recommendations_empty(self, stop_hook):
        """Test formatting empty recommendations returns empty string."""
        assert stop_hook.format_recommendations_message([]) == ""

    def test_save_session_analysis(self, stop_hook):
        """Test saving session analysis to file."""
        messages = [
            {"role": "user", "content": "Test message"},
            {"role": "assistant", "content": "<function_calls><Bash>test</Bash></function_calls>"},
            {"role": "assistant", "content": "An error occurred here"},
        ]

        with patch.object(stop_hook, "extract_learnings", return_value=[{"type": "test", "suggestion": "fix"}]):
            stop_hook.save_session_analysis(messages)

        # Check analysis file was created
        analysis_files = list(stop_hook.analysis_dir.glob("session_*.json"))
        assert len(analysis_files) == 1

        # Verify content
        with open(analysis_files[0]) as f:
            analysis = json.load(f)

        assert analysis["stats"]["message_count"] == 3
        assert "tool_uses" in analysis["stats"]
        assert "errors" in analysis["stats"]
        assert "learnings" in analysis

    def test_read_transcript_json_array(self, stop_hook, temp_project_root):
        """Test reading transcript in JSON array format."""
        transcript_file = temp_project_root / "transcript.json"
        messages = [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}]
        transcript_file.write_text(json.dumps(messages))

        result = stop_hook.read_transcript(str(transcript_file))

        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

    def test_read_transcript_json_wrapped(self, stop_hook, temp_project_root):
        """Test reading transcript in wrapped JSON format."""
        transcript_file = temp_project_root / "transcript.json"
        data = {"messages": [{"role": "user", "content": "Test"}]}
        transcript_file.write_text(json.dumps(data))

        result = stop_hook.read_transcript(str(transcript_file))

        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_read_transcript_jsonl(self, stop_hook, temp_project_root):
        """Test reading transcript in JSONL format (Claude Code format)."""
        transcript_file = temp_project_root / "transcript.jsonl"

        lines = [
            json.dumps({"message": {"role": "user", "content": "Hello"}}),
            json.dumps({"message": {"role": "assistant", "content": "Hi"}}),
            json.dumps({"type": "metadata", "timestamp": "2024-01-15"}),  # Should be skipped
        ]
        transcript_file.write_text("\n".join(lines))

        result = stop_hook.read_transcript(str(transcript_file))

        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

    def test_read_transcript_empty_file(self, stop_hook, temp_project_root):
        """Test reading empty transcript file."""
        transcript_file = temp_project_root / "empty.json"
        transcript_file.write_text("")

        result = stop_hook.read_transcript(str(transcript_file))

        assert result == []

    def test_read_transcript_not_found(self, stop_hook):
        """Test reading non-existent transcript file."""
        result = stop_hook.read_transcript("/nonexistent/transcript.json")

        assert result == []

    def test_read_transcript_no_path(self, stop_hook):
        """Test reading transcript with empty path."""
        result = stop_hook.read_transcript("")

        assert result == []

    def test_read_transcript_invalid_json(self, stop_hook, temp_project_root):
        """Test reading transcript with invalid JSON."""
        transcript_file = temp_project_root / "invalid.json"
        transcript_file.write_text("not valid json {{{")

        result = stop_hook.read_transcript(str(transcript_file))

        # Should try JSONL parsing and return empty
        assert result == []

    def test_read_transcript_external_allowed_paths(self, stop_hook):
        """Test reading transcript from allowed external locations."""
        import tempfile

        # Create temp file in system temp directory
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([{"role": "user", "content": "test"}], f)
            temp_path = f.name

        try:
            result = stop_hook.read_transcript(temp_path)
            assert len(result) == 1
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_find_session_transcript_by_id(self, stop_hook, temp_project_root):
        """Test finding transcript by session ID."""
        session_id = "session_12345"
        transcript_dir = temp_project_root / ".claude" / "runtime" / "transcripts"
        transcript_dir.mkdir(parents=True)
        transcript_file = transcript_dir / f"{session_id}.json"
        transcript_file.write_text('{"messages": []}')

        result = stop_hook.find_session_transcript(session_id)

        assert result == transcript_file

    def test_find_session_transcript_not_found(self, stop_hook):
        """Test finding non-existent transcript."""
        result = stop_hook.find_session_transcript("nonexistent_session")

        assert result is None

    def test_find_session_transcript_no_session_id(self, stop_hook):
        """Test finding transcript with no session ID."""
        result = stop_hook.find_session_transcript("")

        assert result is None

    def test_get_session_messages_from_transcript_path(self, stop_hook, temp_project_root):
        """Test getting session messages from transcript_path."""
        transcript_file = temp_project_root / "test_transcript.json"
        messages = [{"role": "user", "content": "test"}]
        transcript_file.write_text(json.dumps(messages))

        input_data = {"transcript_path": str(transcript_file)}
        result = stop_hook.get_session_messages(input_data)

        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_get_session_messages_from_session_id(self, stop_hook, temp_project_root):
        """Test getting session messages from session_id."""
        session_id = "test_session"
        transcript_dir = temp_project_root / ".claude" / "runtime" / "transcripts"
        transcript_dir.mkdir(parents=True)
        transcript_file = transcript_dir / f"{session_id}.json"
        messages = [{"role": "user", "content": "test"}]
        transcript_file.write_text(json.dumps(messages))

        input_data = {"session_id": session_id}
        result = stop_hook.get_session_messages(input_data)

        assert len(result) == 1

    def test_get_session_messages_from_direct_messages(self, stop_hook):
        """Test getting session messages from direct messages in input."""
        messages = [{"role": "user", "content": "test"}]
        input_data = {"messages": messages}

        result = stop_hook.get_session_messages(input_data)

        assert result == messages

    def test_get_session_messages_no_messages(self, stop_hook):
        """Test getting session messages when no source available."""
        input_data = {}

        result = stop_hook.get_session_messages(input_data)

        assert result == []

    def test_integration_lock_workflow(self, stop_hook):
        """Integration test for complete lock workflow."""
        # Initial state: no lock
        result1 = stop_hook.process({})
        assert result1["decision"] == "allow"

        # Create lock
        stop_hook.lock_flag.touch()
        result2 = stop_hook.process({})
        assert result2["decision"] == "block"

        # Remove lock
        stop_hook.lock_flag.unlink()
        result3 = stop_hook.process({})
        assert result3["decision"] == "allow"
