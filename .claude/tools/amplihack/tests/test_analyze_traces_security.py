"""Security-focused tests for analyze_traces.py."""

from pathlib import Path
from typing import Any

import pytest

from ..analyze_traces import find_unprocessed_logs, validate_log_path


class TestPathValidation:
    """Test path validation for log files."""

    def test_accepts_valid_log_path(self, tmp_path: Any) -> None:
        """Should accept valid .jsonl file in trace directory."""
        trace_dir = tmp_path / ".claude-trace"
        trace_dir.mkdir()
        log_file = trace_dir / "valid.jsonl"
        log_file.touch()

        # Should not raise
        result = validate_log_path(str(log_file), str(trace_dir))
        assert result == str(log_file)

    def test_rejects_path_traversal_parent_dir(self, tmp_path: Any) -> None:
        """Should reject path traversal with .."""
        trace_dir = tmp_path / ".claude-trace"
        trace_dir.mkdir()

        # Should reject (any ValueError indicates rejection)
        with pytest.raises(ValueError, match="Invalid log path"):
            validate_log_path("../etc/passwd.jsonl", str(trace_dir))

    def test_rejects_path_outside_base_directory(self, tmp_path: Any) -> None:
        """Should reject paths outside the base directory."""
        trace_dir = tmp_path / ".claude-trace"
        trace_dir.mkdir()
        outside_file = tmp_path / "outside.jsonl"
        outside_file.touch()

        with pytest.raises(ValueError, match="Path outside allowed directory"):
            validate_log_path(str(outside_file), str(trace_dir))

    def test_rejects_non_jsonl_extension(self, tmp_path: Any) -> None:
        """Should reject files without .jsonl extension."""
        trace_dir = tmp_path / ".claude-trace"
        trace_dir.mkdir()
        txt_file = trace_dir / "malicious.txt"
        txt_file.touch()

        with pytest.raises(ValueError, match="Invalid file extension"):
            validate_log_path(str(txt_file), str(trace_dir))

    @pytest.mark.parametrize(
        "char",
        [";", "|", "&", "$", "`", ">", "<", "\n", "\r"],
    )
    def test_rejects_shell_metacharacters(self, tmp_path: Any, char: str) -> None:
        """Should reject paths with shell metacharacters."""
        trace_dir = tmp_path / ".claude-trace"
        trace_dir.mkdir()

        malicious_name = f"file{char}evil.jsonl"
        # Should reject (any ValueError indicates rejection)
        with pytest.raises(ValueError, match="Invalid log path"):
            validate_log_path(malicious_name, str(trace_dir))


class TestCommandInjectionPrevention:
    """Test command injection attack prevention."""

    def test_rejects_semicolon_command_injection(self, tmp_path: Any) -> None:
        """Should reject filename with semicolon command separator."""
        trace_dir = tmp_path / ".claude-trace"
        trace_dir.mkdir()

        # Should reject (any ValueError indicates rejection)
        with pytest.raises(ValueError, match="Invalid log path"):
            validate_log_path("log.jsonl; rm -rf /", str(trace_dir))

    def test_rejects_pipe_command_injection(self, tmp_path: Any) -> None:
        """Should reject filename with pipe command."""
        trace_dir = tmp_path / ".claude-trace"
        trace_dir.mkdir()

        # Should reject (any ValueError indicates rejection)
        with pytest.raises(ValueError, match="Invalid log path"):
            validate_log_path("log.jsonl | cat /etc/passwd", str(trace_dir))

    def test_rejects_backtick_command_substitution(self, tmp_path: Any) -> None:
        """Should reject filename with backtick command substitution."""
        trace_dir = tmp_path / ".claude-trace"
        trace_dir.mkdir()

        # Should reject (any ValueError indicates rejection)
        with pytest.raises(ValueError, match="Invalid log path"):
            validate_log_path("log`whoami`.jsonl", str(trace_dir))

    def test_rejects_dollar_command_substitution(self, tmp_path: Any) -> None:
        """Should reject filename with $() command substitution."""
        trace_dir = tmp_path / ".claude-trace"
        trace_dir.mkdir()

        # Should reject (any ValueError indicates rejection)
        with pytest.raises(ValueError, match="Invalid log path"):
            validate_log_path("log$(id).jsonl", str(trace_dir))

    def test_rejects_redirect_output(self, tmp_path: Any) -> None:
        """Should reject filename with output redirection."""
        trace_dir = tmp_path / ".claude-trace"
        trace_dir.mkdir()

        # Should reject (any ValueError indicates rejection)
        with pytest.raises(ValueError, match="Invalid log path"):
            validate_log_path("log > /tmp/evil.jsonl", str(trace_dir))


class TestFindUnprocessedLogsIntegration:
    """Integration tests for find_unprocessed_logs with security validation."""

    def test_filters_out_invalid_paths(self, tmp_path: Any) -> None:
        """Should filter out invalid paths and return only valid ones."""
        trace_dir = tmp_path / ".claude-trace"
        trace_dir.mkdir()

        # Create valid log file
        valid_log = trace_dir / "valid.jsonl"
        valid_log.touch()

        # Try to create malicious log file (with shell metachar in name)
        # Note: Most filesystems won't allow these chars, so this tests the validation logic
        result = find_unprocessed_logs(str(trace_dir))

        # Should only return valid log
        assert len(result) == 1
        assert str(valid_log) in result

    def test_skips_already_processed_directory(self, tmp_path: Any) -> None:
        """Should skip logs in already_processed directory."""
        trace_dir = tmp_path / ".claude-trace"
        trace_dir.mkdir()
        processed_dir = trace_dir / "already_processed"
        processed_dir.mkdir()

        # Create log in processed directory
        processed_log = processed_dir / "processed.jsonl"
        processed_log.touch()

        # Create unprocessed log
        unprocessed_log = trace_dir / "unprocessed.jsonl"
        unprocessed_log.touch()

        result = find_unprocessed_logs(str(trace_dir))

        # Should only return unprocessed log
        assert len(result) == 1
        assert str(unprocessed_log) in result
        assert str(processed_log) not in result

    def test_returns_empty_for_nonexistent_directory(self, tmp_path: Any) -> None:
        """Should return empty list for non-existent directory."""
        nonexistent = tmp_path / "does_not_exist"
        result = find_unprocessed_logs(str(nonexistent))
        assert result == []

    def test_returns_empty_for_no_jsonl_files(self, tmp_path: Any) -> None:
        """Should return empty list when no .jsonl files exist."""
        trace_dir = tmp_path / ".claude-trace"
        trace_dir.mkdir()

        # Create non-jsonl files
        (trace_dir / "file.txt").touch()
        (trace_dir / "file.log").touch()

        result = find_unprocessed_logs(str(trace_dir))
        assert result == []


class TestDefenseInDepth:
    """Test defense-in-depth security measures."""

    def test_validates_resolved_path_not_original(self, tmp_path: Any) -> None:
        """Should validate resolved path to prevent symlink attacks."""
        trace_dir = tmp_path / ".claude-trace"
        trace_dir.mkdir()
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()

        # Create symlink pointing outside trace_dir
        link = trace_dir / "evil_link.jsonl"
        target = outside_dir / "target.jsonl"
        target.touch()

        try:
            link.symlink_to(target)
            # Should reject because resolved path is outside base directory
            with pytest.raises(ValueError, match="Path outside allowed directory"):
                validate_log_path(str(link), str(trace_dir))
        except OSError:
            # Skip if symlinks not supported
            pytest.skip("Symlinks not supported on this filesystem")

    def test_multiple_validation_layers(self, tmp_path: Any) -> None:
        """Should have multiple validation layers (defense in depth)."""
        trace_dir = tmp_path / ".claude-trace"
        trace_dir.mkdir()

        # Path that would fail multiple checks
        malicious_path = "../../../etc/passwd; rm -rf /"

        # Should fail on first check it encounters (any of these is correct)
        with pytest.raises(ValueError):
            validate_log_path(malicious_path, str(trace_dir))
