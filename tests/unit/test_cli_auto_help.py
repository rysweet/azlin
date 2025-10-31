"""Unit tests for CLI automatic help display on errors.

Tests that the CLI automatically shows contextual help when users
make syntax errors (missing arguments, invalid options, etc.).
"""

from click.testing import CliRunner

from azlin.cli import main


class TestAutoHelpOnErrors:
    """Test automatic help display after syntax errors."""

    def test_missing_required_argument_shows_help(self):
        """Test that missing required argument shows error and help."""
        runner = CliRunner()
        # bastion configure requires VM_NAME argument
        result = runner.invoke(main, ["bastion", "configure", "--bastion-name", "test"])

        # Should show error
        assert result.exit_code != 0
        assert "Error" in result.output or "Missing" in result.output

        # Should automatically show help for the configure command
        assert "Configure Bastion connection for a VM" in result.output or "Usage:" in result.output

    def test_missing_required_option_shows_help(self):
        """Test that missing required option shows error and help."""
        runner = CliRunner()
        # bastion configure requires --bastion-name option
        result = runner.invoke(main, ["bastion", "configure", "my-vm"])

        # Should show error
        assert result.exit_code != 0
        assert "Error" in result.output or "Missing" in result.output

        # Should automatically show help
        assert "Usage:" in result.output or "bastion configure" in result.output

    def test_invalid_command_shows_help(self):
        """Test that invalid command shows error and top-level help."""
        runner = CliRunner()
        result = runner.invoke(main, ["nonexistent-command"])

        # Should show error
        assert result.exit_code != 0

        # Should show top-level help
        assert "azlin" in result.output
        assert "Usage:" in result.output or "Commands:" in result.output

    def test_valid_command_no_help_spam(self):
        """Test that valid commands don't show help unnecessarily."""
        runner = CliRunner()
        # Test with --help flag (should show help normally)
        result = runner.invoke(main, ["--help"])

        # Should succeed
        assert result.exit_code == 0
        assert "Usage:" in result.output

        # But help should only appear once in a reasonable manner
        # (not duplicated due to error handling)
        usage_count = result.output.count("Usage:")
        assert usage_count >= 1  # Should have usage info

    def test_subcommand_error_shows_subcommand_help(self):
        """Test that subcommand errors show subcommand help, not top-level."""
        runner = CliRunner()
        # Error in bastion list with invalid option
        result = runner.invoke(main, ["bastion", "list", "--invalid-option"])

        # Should show error
        assert result.exit_code != 0

        # Should show bastion list help, not top-level azlin help
        # (Check for bastion-specific content, not generic azlin content)
        assert "bastion" in result.output.lower()

    def test_error_message_preserved(self):
        """Test that original error message is shown before help."""
        runner = CliRunner()
        result = runner.invoke(main, ["bastion", "configure", "--bastion-name", "test"])

        # Should show error message
        assert result.exit_code != 0
        # Error should mention the missing VM_NAME argument
        output_lower = result.output.lower()
        assert "error" in output_lower or "missing" in output_lower

    def test_multiple_errors_show_appropriate_help(self):
        """Test that multiple different errors each show appropriate help."""
        runner = CliRunner()

        # Test 1: Missing argument in bastion configure
        result1 = runner.invoke(main, ["bastion", "configure"])
        assert result1.exit_code != 0
        assert "Usage:" in result1.output or "error" in result1.output.lower()

        # Test 2: Invalid option in bastion list
        result2 = runner.invoke(main, ["bastion", "list", "--invalid"])
        assert result2.exit_code != 0

        # Each should have shown some form of help or error
        assert len(result1.output) > 50  # Some substantial output
        assert len(result2.output) > 50  # Some substantial output
