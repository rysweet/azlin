"""Comprehensive tests for reflection hook."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the module under test
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from reflection import SessionReflector, save_reflection_summary


class TestSessionReflector:
    """Tests for SessionReflector class."""

    @pytest.fixture
    def reflector(self):
        """Create a SessionReflector instance with reflection enabled."""
        with patch.dict(os.environ, {}, clear=False):
            # Ensure CLAUDE_REFLECTION_MODE is not set
            if "CLAUDE_REFLECTION_MODE" in os.environ:
                del os.environ["CLAUDE_REFLECTION_MODE"]
            return SessionReflector()

    @pytest.fixture
    def reflector_disabled(self):
        """Create a SessionReflector with reflection disabled (loop prevention)."""
        with patch.dict(os.environ, {"CLAUDE_REFLECTION_MODE": "1"}):
            return SessionReflector()

    @pytest.fixture
    def sample_messages(self):
        """Sample conversation messages for testing."""
        return [
            {"role": "user", "content": "Hello, can you help me?"},
            {
                "role": "assistant",
                "content": "I'll help you. <function_calls><Bash>ls -la</Bash></function_calls>",
            },
            {"role": "user", "content": "That doesn't work, try again"},
            {
                "role": "assistant",
                "content": "Let me retry. <function_calls><Bash>ls -l</Bash></function_calls>",
            },
            {"role": "user", "content": "Still failing, this is broken"},
            {
                "role": "assistant",
                "content": "I see an error occurred. <function_calls><Read>file.txt</Read></function_calls>",
            },
        ]

    def test_initialization_enabled(self, reflector):
        """Test reflector initializes with reflection enabled."""
        assert reflector.enabled is True

    def test_initialization_disabled(self, reflector_disabled):
        """Test reflector disables when CLAUDE_REFLECTION_MODE=1."""
        assert reflector_disabled.enabled is False

    def test_analyze_session_when_disabled(self, reflector_disabled, sample_messages):
        """Test analyze_session returns skip info when disabled."""
        result = reflector_disabled.analyze_session(sample_messages)

        assert result["skipped"] is True
        assert result["reason"] == "reflection_loop_prevention"

    def test_analyze_session_structure(self, reflector, sample_messages):
        """Test analyze_session returns expected structure."""
        result = reflector.analyze_session(sample_messages)

        assert "timestamp" in result
        assert "patterns" in result
        assert "metrics" in result
        assert "suggestions" in result
        assert isinstance(result["patterns"], list)
        assert isinstance(result["suggestions"], list)

    def test_metrics_extraction(self, reflector, sample_messages):
        """Test basic metrics extraction."""
        result = reflector.analyze_session(sample_messages)
        metrics = result["metrics"]

        assert metrics["total_messages"] == 6
        assert metrics["user_messages"] == 3
        assert metrics["assistant_messages"] == 3
        assert metrics["tool_uses"] >= 3  # At least 3 tool uses visible

    def test_extract_tool_uses(self, reflector):
        """Test tool use extraction from messages."""
        messages = [
            {"role": "assistant", "content": "<function_calls><Bash>echo test</Bash></function_calls>"},
            {"role": "assistant", "content": "<function_calls><Read>file.py</Read></function_calls>"},
            {"role": "assistant", "content": "<function_calls><Write>out.txt</Write></function_calls>"},
            {"role": "assistant", "content": "<function_calls><Edit>code.py</Edit></function_calls>"},
            {"role": "assistant", "content": "<function_calls><Grep>pattern</Grep></function_calls>"},
            {"role": "assistant", "content": "<function_calls><Glob>*.py</Glob></function_calls>"},
            {"role": "assistant", "content": "<function_calls><TodoWrite>task</TodoWrite></function_calls>"},
            {"role": "user", "content": "Regular message"},
        ]

        tools = reflector._extract_tool_uses(messages)

        assert "bash" in tools
        assert "read" in tools
        assert "write" in tools
        assert "edit" in tools
        assert "grep" in tools
        assert "glob" in tools
        assert "todo" in tools

    def test_find_repetitions(self, reflector):
        """Test finding repeated tool uses."""
        items = ["bash", "bash", "bash", "bash", "read", "read", "write"]

        repeated = reflector._find_repetitions(items)

        assert "bash" in repeated
        assert repeated["bash"] == 4
        assert "read" not in repeated  # Below threshold (3)
        assert "write" not in repeated  # Below threshold

    def test_find_repetitions_empty(self, reflector):
        """Test repetition detection with empty list."""
        assert reflector._find_repetitions([]) == {}

    def test_error_pattern_detection(self, reflector):
        """Test detection of error-related patterns."""
        messages = [
            {"role": "assistant", "content": "Got an error when running command"},
            {"role": "assistant", "content": "Failed to execute, will retry"},
            {"role": "assistant", "content": "Exception occurred in the script"},
            {"role": "user", "content": "Try again please"},
        ]

        result = reflector._find_error_patterns(messages)

        assert result is not None
        assert result["count"] >= 3
        assert len(result["samples"]) > 0
        assert len(result["samples"]) <= 3  # Max 3 samples

    def test_error_pattern_below_threshold(self, reflector):
        """Test error detection when below threshold."""
        messages = [
            {"role": "assistant", "content": "Got an error"},
            {"role": "user", "content": "ok"},
        ]

        result = reflector._find_error_patterns(messages)

        assert result is None  # Below threshold

    def test_frustration_detection(self, reflector):
        """Test user frustration indicator detection."""
        messages = [
            {"role": "user", "content": "This doesn't work at all"},
            {"role": "user", "content": "It's still failing, why isn't this working?"},
            {"role": "user", "content": "I'm confused about this broken behavior"},
        ]

        result = reflector._find_frustration_patterns(messages)

        assert result is not None
        assert result["count"] >= 2

    def test_frustration_detection_assistant_messages(self, reflector):
        """Test that frustration detection only counts user messages."""
        messages = [
            {"role": "assistant", "content": "This doesn't work"},
            {"role": "assistant", "content": "Still failing"},
            {"role": "user", "content": "Regular message"},
        ]

        result = reflector._find_frustration_patterns(messages)

        assert result is None  # Assistant messages shouldn't count

    def test_long_session_detection(self, reflector):
        """Test detection of long sessions."""
        # Create 101 messages (above threshold of 100)
        long_messages = [{"role": "user", "content": f"Message {i}"} for i in range(101)]

        result = reflector.analyze_session(long_messages)

        long_session_patterns = [p for p in result["patterns"] if p["type"] == "long_session"]
        assert len(long_session_patterns) == 1
        assert long_session_patterns[0]["message_count"] == 101

    def test_repeated_tool_use_detection(self, reflector):
        """Test detection of repeated tool uses."""
        messages = []
        # Create 5 bash tool uses (above threshold)
        for i in range(5):
            messages.append(
                {"role": "assistant", "content": f"<function_calls><Bash>cmd{i}</Bash></function_calls>"}
            )

        result = reflector.analyze_session(messages)

        bash_patterns = [
            p for p in result["patterns"] if p["type"] == "repeated_tool_use" and p["tool"] == "bash"
        ]
        assert len(bash_patterns) == 1
        assert bash_patterns[0]["count"] == 5

    def test_generate_suggestions_frustration(self, reflector):
        """Test suggestion generation prioritizes frustration."""
        patterns = [{"type": "user_frustration", "indicators": 3}]

        suggestions = reflector._generate_suggestions(patterns)

        assert len(suggestions) > 0
        assert any("HIGH PRIORITY" in s for s in suggestions)
        assert any("frustration" in s.lower() for s in suggestions)

    def test_generate_suggestions_errors(self, reflector):
        """Test suggestion generation for error patterns."""
        patterns = [{"type": "error_patterns", "count": 5}]

        suggestions = reflector._generate_suggestions(patterns)

        assert len(suggestions) > 0
        assert any("error" in s.lower() for s in suggestions)

    def test_generate_suggestions_repeated_bash(self, reflector):
        """Test suggestion generation for repeated bash commands."""
        patterns = [{"type": "repeated_tool_use", "tool": "bash", "count": 5}]

        suggestions = reflector._generate_suggestions(patterns)

        assert len(suggestions) > 0
        assert any("script" in s.lower() for s in suggestions)

    def test_generate_suggestions_repeated_read(self, reflector):
        """Test suggestion generation for repeated read operations."""
        patterns = [{"type": "repeated_tool_use", "tool": "read", "count": 6}]

        suggestions = reflector._generate_suggestions(patterns)

        assert len(suggestions) > 0
        assert any("caching" in s.lower() or "search" in s.lower() for s in suggestions)

    def test_generate_suggestions_long_session(self, reflector):
        """Test suggestion generation for long sessions."""
        patterns = [{"type": "long_session", "message_count": 150}]

        suggestions = reflector._generate_suggestions(patterns)

        assert len(suggestions) > 0
        assert any("decomposition" in s.lower() or "todowrite" in s.lower() for s in suggestions)

    def test_analyze_session_comprehensive(self, reflector):
        """Test comprehensive analysis with multiple patterns."""
        messages = []

        # Add user frustration
        messages.append({"role": "user", "content": "This doesn't work"})
        messages.append({"role": "user", "content": "Still broken"})

        # Add errors
        messages.append({"role": "assistant", "content": "Error occurred"})
        messages.append({"role": "assistant", "content": "Failed again"})
        messages.append({"role": "assistant", "content": "Exception raised"})

        # Add repeated tool uses
        for i in range(5):
            messages.append({"role": "assistant", "content": "<function_calls><Bash>cmd</Bash></function_calls>"})

        result = reflector.analyze_session(messages)

        # Should detect multiple patterns
        pattern_types = [p["type"] for p in result["patterns"]]
        assert "user_frustration" in pattern_types
        assert "error_patterns" in pattern_types
        assert "repeated_tool_use" in pattern_types

        # Should generate suggestions
        assert len(result["suggestions"]) > 0


class TestSaveReflectionSummary:
    """Tests for save_reflection_summary function."""

    @pytest.fixture
    def temp_dir(self):
        """Temporary directory for output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_save_reflection_summary_skipped(self, temp_dir):
        """Test saving skipped analysis returns None."""
        analysis = {"skipped": True, "reason": "test"}

        result = save_reflection_summary(analysis, temp_dir)

        assert result is None
        assert len(list(temp_dir.glob("*"))) == 0  # No files created

    def test_save_reflection_summary_success(self, temp_dir):
        """Test saving successful analysis."""
        analysis = {
            "timestamp": "2024-01-15T10:30:00",
            "metrics": {"total_messages": 50, "tool_uses": 10},
            "patterns": [
                {"type": "repeated_tool_use", "tool": "bash", "count": 5, "suggestion": "Create a script"}
            ],
            "suggestions": ["Consider automation"],
        }

        result = save_reflection_summary(analysis, temp_dir)

        assert result is not None
        assert result.exists()
        assert result.suffix == ".json"
        assert "reflection_" in result.name

        # Verify content
        with open(result) as f:
            saved = json.load(f)

        assert saved["session_time"] == "2024-01-15T10:30:00"
        assert saved["metrics"]["total_messages"] == 50
        assert saved["patterns_found"] == 1
        assert len(saved["patterns"]) == 1
        assert len(saved["suggestions"]) == 1
        assert len(saved["action_items"]) == 1

    def test_save_reflection_summary_action_items(self, temp_dir):
        """Test action items generation in saved summary."""
        analysis = {
            "timestamp": "2024-01-15T10:30:00",
            "metrics": {},
            "patterns": [
                {
                    "type": "user_frustration",
                    "indicators": 3,
                    "suggestion": "Review approach",
                },
                {
                    "type": "error_patterns",
                    "count": 5,
                    "suggestion": "Add error handling",
                },
            ],
            "suggestions": [],
        }

        result = save_reflection_summary(analysis, temp_dir)

        with open(result) as f:
            saved = json.load(f)

        assert len(saved["action_items"]) == 2

        # Check frustration has high priority
        frustration_items = [a for a in saved["action_items"] if a["issue"] == "user_frustration"]
        assert len(frustration_items) == 1
        assert frustration_items[0]["priority"] == "high"

        # Check error has normal priority
        error_items = [a for a in saved["action_items"] if a["issue"] == "error_patterns"]
        assert len(error_items) == 1
        assert error_items[0]["priority"] == "normal"

    def test_save_reflection_summary_empty_patterns(self, temp_dir):
        """Test saving summary with no patterns."""
        analysis = {
            "timestamp": "2024-01-15T10:30:00",
            "metrics": {"total_messages": 5},
            "patterns": [],
            "suggestions": [],
        }

        result = save_reflection_summary(analysis, temp_dir)

        assert result is not None
        with open(result) as f:
            saved = json.load(f)

        assert saved["patterns_found"] == 0
        assert saved["patterns"] == []
        assert saved["action_items"] == []
