"""Tests for parallel tool detection in PrerequisiteChecker.

Verifies that check_all() runs tool checks concurrently using ThreadPoolExecutor
while maintaining the same public API and return types.
"""

import time
from unittest.mock import patch

import pytest

from azlin.modules.prerequisites import PrerequisiteChecker, PrerequisiteResult


class TestParallelCheckAll:
    """Tests for parallel execution in check_all()."""

    @patch.object(PrerequisiteChecker, "detect_platform", return_value="linux")
    @patch("azlin.modules.prerequisites.shutil.which")
    def test_check_all_returns_prerequisite_result(self, mock_which, mock_platform):
        """check_all() must return a PrerequisiteResult regardless of parallelism."""
        mock_which.return_value = "/usr/bin/tool"
        result = PrerequisiteChecker.check_all()
        assert isinstance(result, PrerequisiteResult)
        assert mock_platform.called

    @patch.object(PrerequisiteChecker, "detect_platform", return_value="linux")
    @patch("azlin.modules.prerequisites.shutil.which")
    def test_check_all_finds_all_available_tools(self, mock_which, mock_platform):
        """All tools found should appear in available list."""
        mock_which.return_value = "/usr/bin/tool"
        result = PrerequisiteChecker.check_all()
        assert result.all_available is True
        assert len(result.missing) == 0
        for tool in PrerequisiteChecker.REQUIRED_TOOLS:
            assert tool in result.available
        assert mock_platform.called

    @patch.object(PrerequisiteChecker, "detect_platform", return_value="linux")
    @patch("azlin.modules.prerequisites.shutil.which")
    def test_check_all_reports_missing_tools(self, mock_which, mock_platform):
        """Missing tools should appear in missing list."""

        def side_effect(tool_name):
            if tool_name == "az":
                return None
            return f"/usr/bin/{tool_name}"

        mock_which.side_effect = side_effect
        result = PrerequisiteChecker.check_all()
        assert result.all_available is False
        assert "az" in result.missing
        assert "az" not in result.available
        assert mock_platform.called

    @patch.object(PrerequisiteChecker, "detect_platform", return_value="linux")
    @patch("azlin.modules.prerequisites.shutil.which")
    def test_check_all_runs_in_parallel(self, mock_which, mock_platform):
        """Parallel execution should be faster than sequential with slow checks."""
        delay_per_tool = 0.5
        total_tools = len(PrerequisiteChecker.REQUIRED_TOOLS) + len(
            PrerequisiteChecker.OPTIONAL_TOOLS
        )

        def slow_which(tool_name):
            time.sleep(delay_per_tool)
            return f"/usr/bin/{tool_name}"

        mock_which.side_effect = slow_which

        start = time.monotonic()
        result = PrerequisiteChecker.check_all()
        elapsed = time.monotonic() - start

        # If sequential, would take total_tools * delay_per_tool (~2.5s for 5 tools)
        # If parallel, should take ~delay_per_tool (~0.5s) + overhead
        sequential_time = total_tools * delay_per_tool
        assert elapsed < sequential_time * 0.5, (
            f"check_all() took {elapsed:.2f}s, expected < {sequential_time * 0.5:.2f}s "
            f"for parallel execution (sequential would be ~{sequential_time:.2f}s)"
        )
        assert result.all_available is True
        assert mock_platform.called

    @patch.object(PrerequisiteChecker, "detect_platform", return_value="linux")
    @patch("azlin.modules.prerequisites.shutil.which")
    def test_check_all_includes_optional_tools_when_available(self, mock_which, mock_platform):
        """Optional tools should appear in available when found."""
        mock_which.return_value = "/usr/bin/tool"
        result = PrerequisiteChecker.check_all()
        for tool in PrerequisiteChecker.OPTIONAL_TOOLS:
            assert tool in result.available
        assert mock_platform.called

    @patch.object(PrerequisiteChecker, "detect_platform", return_value="linux")
    @patch("azlin.modules.prerequisites.shutil.which")
    def test_check_all_missing_optional_does_not_fail(self, mock_which, mock_platform):
        """Missing optional tools should NOT cause all_available to be False."""

        def side_effect(tool_name):
            if tool_name in PrerequisiteChecker.OPTIONAL_TOOLS:
                return None
            return f"/usr/bin/{tool_name}"

        mock_which.side_effect = side_effect
        result = PrerequisiteChecker.check_all()
        assert result.all_available is True
        assert len(result.missing) == 0
        assert mock_platform.called

    @patch.object(PrerequisiteChecker, "detect_platform", return_value="linux")
    @patch("azlin.modules.prerequisites.shutil.which")
    def test_check_all_handles_exception_in_tool_check(self, mock_which, mock_platform):
        """If a tool check raises an exception, it should be treated as missing."""

        def side_effect(tool_name):
            if tool_name == "git":
                raise OSError("Permission denied")
            return f"/usr/bin/{tool_name}"

        mock_which.side_effect = side_effect
        result = PrerequisiteChecker.check_all()
        assert "git" in result.missing
        assert mock_platform.called

    @patch.object(PrerequisiteChecker, "detect_platform", return_value="linux")
    @patch("azlin.modules.prerequisites.shutil.which")
    def test_check_all_preserves_platform_name(self, mock_which, mock_platform):
        """Platform name should still be set correctly."""
        mock_which.return_value = "/usr/bin/tool"
        result = PrerequisiteChecker.check_all()
        assert result.platform_name == "linux"
        assert mock_platform.called


@pytest.mark.unit
class TestCheckToolUnchanged:
    """Verify check_tool() behavior is unchanged by parallelization."""

    @patch("azlin.modules.prerequisites.shutil.which", return_value="/usr/bin/git")
    def test_check_tool_returns_true_when_found(self, mock_which):
        assert PrerequisiteChecker.check_tool("git") is True
        assert mock_which.called

    @patch("azlin.modules.prerequisites.shutil.which", return_value=None)
    def test_check_tool_returns_false_when_missing(self, mock_which):
        assert PrerequisiteChecker.check_tool("nonexistent") is False
        assert mock_which.called
