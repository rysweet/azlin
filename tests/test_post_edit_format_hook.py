"""Tests for post_edit_format hook."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

# Import from the hook module
import sys
from pathlib import Path

# Add amplihack tools to path
hook_path = Path(__file__).parent.parent / ".claude" / "tools"
sys.path.insert(0, str(hook_path))

from amplihack.hooks.post_edit_format import command_exists


class TestCommandExists:
    """Tests for command_exists function."""

    def test_command_exists_returns_true_for_existing_command(self):
        """Test that command_exists returns True for commands that exist."""
        # Python should exist on all systems
        assert command_exists("python3") is True

    def test_command_exists_returns_false_for_nonexistent_command(self):
        """Test that command_exists returns False for commands that don't exist."""
        assert command_exists("this_command_definitely_does_not_exist_12345") is False

    @patch("subprocess.run")
    def test_command_exists_calls_subprocess_only_once(self, mock_run):
        """
        Test that command_exists calls subprocess.run exactly once.

        Regression test for bug where which command was executed twice.
        """
        # Setup mock to return success
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # Call function
        result = command_exists("test_command")

        # Verify subprocess.run called exactly once
        assert mock_run.call_count == 1, (
            f"Expected subprocess.run to be called once, "
            f"but it was called {mock_run.call_count} times"
        )
        assert result is True

    @patch("subprocess.run")
    def test_command_exists_handles_subprocess_error(self, mock_run):
        """Test that command_exists handles subprocess errors gracefully."""
        # Setup mock to raise error
        mock_run.side_effect = subprocess.SubprocessError("Test error")

        # Should return False, not raise exception
        result = command_exists("test_command")
        assert result is False

    @patch("subprocess.run")
    def test_command_exists_handles_os_error(self, mock_run):
        """Test that command_exists handles OS errors gracefully."""
        # Setup mock to raise OSError
        mock_run.side_effect = OSError("Test OS error")

        # Should return False, not raise exception
        result = command_exists("test_command")
        assert result is False

    @patch("subprocess.run")
    def test_command_exists_uses_correct_subprocess_params(self, mock_run):
        """Test that command_exists uses correct subprocess.run parameters."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # Call function
        command_exists("test_command")

        # Verify correct parameters
        mock_run.assert_called_once_with(
            ["which", "test_command"],
            capture_output=True,
            check=False,
            timeout=1,
        )
