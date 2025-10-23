"""Unit tests for azdoit CLI module."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from azlin.azdoit.cli import main


class TestCLIBasics:
    """Test basic CLI functionality."""

    def test_missing_request_argument(self):
        """Test that CLI errors when request argument is missing."""
        runner = CliRunner()
        result = runner.invoke(main, [])

        assert result.exit_code == 1
        assert "Error: Missing required argument 'REQUEST'" in result.output

    def test_empty_request_argument(self):
        """Test that CLI errors when request is empty."""
        runner = CliRunner()
        result = runner.invoke(main, ["   "])  # Whitespace only

        assert result.exit_code == 1
        assert "Error: Request cannot be empty" in result.output

    def test_version_flag(self):
        """Test --version flag shows version and exits."""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])

        assert result.exit_code == 0
        assert "azdoit version 2.0.0" in result.output

    def test_help_flag(self):
        """Test --help flag shows usage information."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "azdoit" in result.output
        assert "Azure infrastructure automation" in result.output
        assert "--max-turns" in result.output


class TestCLIOptions:
    """Test CLI option parsing."""

    @patch("azlin.azdoit.cli.check_amplihack_available")
    @patch("azlin.azdoit.cli.execute_auto_mode")
    def test_max_turns_default(self, mock_execute, mock_check):
        """Test that default max_turns value is 15."""
        mock_check.return_value = True
        runner = CliRunner()

        runner.invoke(main, ["test request"])

        # Check that execute_auto_mode was called with default max_turns
        assert mock_execute.called
        call_kwargs = mock_execute.call_args[1]
        assert call_kwargs["max_turns"] == 15

    @patch("azlin.azdoit.cli.check_amplihack_available")
    @patch("azlin.azdoit.cli.execute_auto_mode")
    def test_max_turns_custom(self, mock_execute, mock_check):
        """Test that custom max_turns value is respected."""
        mock_check.return_value = True
        runner = CliRunner()

        runner.invoke(main, ["--max-turns", "30", "test request"])

        # Check that execute_auto_mode was called with custom max_turns
        assert mock_execute.called
        call_kwargs = mock_execute.call_args[1]
        assert call_kwargs["max_turns"] == 30

    @patch("azlin.azdoit.cli.check_amplihack_available")
    @patch("azlin.azdoit.cli.execute_auto_mode")
    def test_max_turns_validation(self, mock_execute, mock_check):
        """Test that max_turns must be an integer."""
        mock_check.return_value = True
        runner = CliRunner()

        result = runner.invoke(main, ["--max-turns", "not-a-number", "test"])

        assert result.exit_code != 0
        # Click should reject non-integer values


class TestEnvironmentChecks:
    """Test environment validation."""

    @patch("azlin.azdoit.cli.check_amplihack_available")
    @patch("azlin.azdoit.cli.execute_auto_mode")
    @patch("azlin.azdoit.cli.os.environ.get")
    def test_missing_api_key_warning(self, mock_env_get, mock_execute, mock_check):
        """Test that missing ANTHROPIC_API_KEY shows warning."""
        mock_check.return_value = True
        mock_env_get.return_value = None  # API key not set
        runner = CliRunner()

        result = runner.invoke(main, ["test request"])

        assert "Warning: ANTHROPIC_API_KEY environment variable not set" in result.output

    @patch("azlin.azdoit.cli.check_amplihack_available")
    @patch("azlin.azdoit.cli.execute_auto_mode")
    @patch("azlin.azdoit.cli.os.environ.get")
    def test_api_key_present_no_warning(self, mock_env_get, mock_execute, mock_check):
        """Test that present ANTHROPIC_API_KEY does not show warning."""
        mock_check.return_value = True
        mock_env_get.return_value = "sk-ant-test-key"  # API key is set
        runner = CliRunner()

        result = runner.invoke(main, ["test request"])

        assert "Warning: ANTHROPIC_API_KEY" not in result.output

    @patch("azlin.azdoit.cli.check_amplihack_available")
    def test_amplihack_not_available(self, mock_check):
        """Test that missing amplihack shows error and exits."""
        mock_check.return_value = False
        runner = CliRunner()

        result = runner.invoke(main, ["test request"])

        assert result.exit_code == 1
        assert "Error: amplihack is not installed" in result.output
        assert "pip install amplihack" in result.output


class TestPromptConstruction:
    """Test prompt construction and execution flow."""

    @patch("azlin.azdoit.cli.execute_auto_mode")
    @patch("azlin.azdoit.cli.check_amplihack_available")
    def test_prompt_formatting(self, mock_check, mock_execute):
        """Test that user request is formatted into prompt correctly."""
        mock_check.return_value = True
        runner = CliRunner(env={"ANTHROPIC_API_KEY": "test-key"})

        user_request = "create 3 VMs called test-vm-{1,2,3}"
        runner.invoke(main, [user_request])

        # Check that execute_auto_mode was called with formatted prompt
        assert mock_execute.called
        call_args = mock_execute.call_args[0]
        prompt = call_args[0]

        # Prompt should contain the user request in OBJECTIVE section
        assert f"OBJECTIVE: {user_request}" in prompt
        assert "CONTEXT:" in prompt
        assert "REQUIREMENTS:" in prompt

    @patch("azlin.azdoit.cli.execute_auto_mode")
    @patch("azlin.azdoit.cli.check_amplihack_available")
    def test_execution_flow(self, mock_check, mock_execute):
        """Test the complete execution flow."""
        mock_check.return_value = True
        runner = CliRunner(env={"ANTHROPIC_API_KEY": "test-key"})

        result = runner.invoke(main, ["--max-turns", "20", "test objective"])

        # Verify execution flow
        assert mock_check.called  # Availability was checked
        assert mock_execute.called  # Auto mode was executed

        # Verify output shows objective and delegation message
        assert "Objective: test objective" in result.output
        assert "Delegating to amplihack auto mode" in result.output
        assert "max 20 turns" in result.output

    @patch("azlin.azdoit.cli.execute_auto_mode")
    @patch("azlin.azdoit.cli.check_amplihack_available")
    def test_special_characters_in_request(self, mock_check, mock_execute):
        """Test that special characters in request are handled correctly."""
        mock_check.return_value = True
        runner = CliRunner(env={"ANTHROPIC_API_KEY": "test-key"})

        request_with_special_chars = 'create VM "test-1" with $pecial ch@rs'
        runner.invoke(main, [request_with_special_chars])

        assert mock_execute.called
        call_args = mock_execute.call_args[0]
        prompt = call_args[0]

        # Special characters should be preserved in prompt
        assert 'create VM "test-1" with $pecial ch@rs' in prompt


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @patch("azlin.azdoit.cli.execute_auto_mode")
    @patch("azlin.azdoit.cli.check_amplihack_available")
    def test_very_long_request(self, mock_check, mock_execute):
        """Test that very long requests are handled."""
        mock_check.return_value = True
        runner = CliRunner(env={"ANTHROPIC_API_KEY": "test-key"})

        long_request = "create " + "VM " * 100 + "with monitoring"
        runner.invoke(main, [long_request])

        assert mock_execute.called
        call_args = mock_execute.call_args[0]
        prompt = call_args[0]
        assert long_request in prompt

    @patch("azlin.azdoit.cli.execute_auto_mode")
    @patch("azlin.azdoit.cli.check_amplihack_available")
    def test_max_turns_boundary_values(self, mock_check, mock_execute):
        """Test boundary values for max_turns."""
        mock_check.return_value = True
        runner = CliRunner(env={"ANTHROPIC_API_KEY": "test-key"})

        # Test with max_turns = 1
        runner.invoke(main, ["--max-turns", "1", "test"])
        assert mock_execute.called
        call_kwargs = mock_execute.call_args[1]
        assert call_kwargs["max_turns"] == 1

        mock_execute.reset_mock()

        # Test with max_turns = 100
        runner.invoke(main, ["--max-turns", "100", "test"])
        call_kwargs = mock_execute.call_args[1]
        assert call_kwargs["max_turns"] == 100
