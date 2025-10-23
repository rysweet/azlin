"""Unit tests for azdoit executor module."""

import subprocess
import sys
from unittest.mock import Mock, patch

import pytest

from azlin.azdoit.executor import check_amplihack_available, execute_auto_mode


class TestCheckAmplihackAvailable:
    """Test amplihack availability checking."""

    @patch("azlin.azdoit.executor.subprocess.run")
    def test_amplihack_available(self, mock_run):
        """Test when amplihack is installed and working."""
        mock_run.return_value = Mock(returncode=0)

        result = check_amplihack_available()

        assert result is True
        mock_run.assert_called_once_with(
            ["amplihack", "--version"],
            capture_output=True,
            timeout=5
        )

    @patch("azlin.azdoit.executor.subprocess.run")
    def test_amplihack_not_found(self, mock_run):
        """Test when amplihack is not installed."""
        mock_run.side_effect = FileNotFoundError("amplihack not found")

        result = check_amplihack_available()

        assert result is False

    @patch("azlin.azdoit.executor.subprocess.run")
    def test_amplihack_returns_error(self, mock_run):
        """Test when amplihack command returns non-zero exit code."""
        mock_run.return_value = Mock(returncode=1)

        result = check_amplihack_available()

        assert result is False

    @patch("azlin.azdoit.executor.subprocess.run")
    def test_amplihack_timeout(self, mock_run):
        """Test when amplihack version check times out."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["amplihack", "--version"],
            timeout=5
        )

        result = check_amplihack_available()

        assert result is False


class TestExecuteAutoMode:
    """Test auto mode execution."""

    @patch("azlin.azdoit.executor.subprocess.run")
    @patch("azlin.azdoit.executor.sys.exit")
    def test_command_construction(self, mock_exit, mock_run):
        """Test that the amplihack command is constructed correctly."""
        mock_run.return_value = Mock(returncode=0)

        execute_auto_mode("test prompt", max_turns=20)

        # Verify command structure
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args == [
            "amplihack",
            "claude",
            "--auto",
            "--max-turns",
            "20",
            "--",
            "-p",
            "test prompt"
        ]
        assert mock_run.call_args[1]["check"] is False

    @patch("azlin.azdoit.executor.subprocess.run")
    @patch("azlin.azdoit.executor.sys.exit")
    def test_default_max_turns(self, mock_exit, mock_run):
        """Test that default max_turns value is used."""
        mock_run.return_value = Mock(returncode=0)

        execute_auto_mode("test prompt")

        call_args = mock_run.call_args[0][0]
        assert "15" in call_args  # Default max_turns
        assert call_args[4] == "15"

    @patch("azlin.azdoit.executor.subprocess.run")
    @patch("azlin.azdoit.executor.sys.exit")
    def test_exit_code_propagation_success(self, mock_exit, mock_run):
        """Test that successful exit code is propagated."""
        mock_run.return_value = Mock(returncode=0)

        execute_auto_mode("test prompt", max_turns=10)

        mock_exit.assert_called_once_with(0)

    @patch("azlin.azdoit.executor.subprocess.run")
    @patch("azlin.azdoit.executor.sys.exit")
    def test_exit_code_propagation_failure(self, mock_exit, mock_run):
        """Test that non-zero exit code is propagated."""
        mock_run.return_value = Mock(returncode=42)

        execute_auto_mode("test prompt", max_turns=10)

        mock_exit.assert_called_once_with(42)

    @patch("azlin.azdoit.executor.subprocess.run")
    @patch("azlin.azdoit.executor.sys.exit")
    def test_keyboard_interrupt_handling(self, mock_exit, mock_run):
        """Test that KeyboardInterrupt is handled gracefully."""
        mock_run.side_effect = KeyboardInterrupt()

        execute_auto_mode("test prompt", max_turns=10)

        mock_exit.assert_called_once_with(130)

    @patch("azlin.azdoit.executor.subprocess.run")
    @patch("azlin.azdoit.executor.sys.exit")
    def test_file_not_found_handling(self, mock_exit, mock_run):
        """Test that FileNotFoundError is handled with helpful message."""
        mock_run.side_effect = FileNotFoundError("amplihack not found")

        execute_auto_mode("test prompt", max_turns=10)

        mock_exit.assert_called_once_with(1)

    @patch("azlin.azdoit.executor.subprocess.run")
    @patch("azlin.azdoit.executor.sys.exit")
    def test_prompt_passed_correctly(self, mock_exit, mock_run):
        """Test that the prompt is passed correctly to amplihack."""
        mock_run.return_value = Mock(returncode=0)

        long_prompt = "This is a multi-line\nprompt with\nspecial characters: $@!"
        execute_auto_mode(long_prompt, max_turns=5)

        call_args = mock_run.call_args[0][0]
        # Prompt should be the last argument after -p
        assert call_args[-1] == long_prompt
        assert call_args[-2] == "-p"

    @patch("azlin.azdoit.executor.subprocess.run")
    @patch("azlin.azdoit.executor.sys.exit")
    def test_output_not_captured(self, mock_exit, mock_run):
        """Test that subprocess output is not captured (streams to terminal)."""
        mock_run.return_value = Mock(returncode=0)

        execute_auto_mode("test prompt", max_turns=10)

        # Verify that capture_output is not set (defaults to False)
        call_kwargs = mock_run.call_args[1]
        assert "capture_output" not in call_kwargs or call_kwargs["capture_output"] is False
