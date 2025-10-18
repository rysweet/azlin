"""
Unit tests for CLI interface module.

Tests the command-line interface argument parsing, validation,
and help text generation (TDD - RED phase).

Test Coverage:
- Argument parsing with --repo flag
- Argument parsing without --repo flag
- Command validation
- Help text generation
- Error message formatting
- Exit code handling
- Configuration loading from CLI args
"""

import contextlib
from unittest.mock import patch

import pytest

# ============================================================================
# BASIC ARGUMENT PARSING TESTS
# ============================================================================


class TestCLIArgumentParsing:
    """Test CLI argument parsing functionality."""

    def test_cli_accepts_repo_argument(self):
        """Test that CLI accepts --repo argument.

        RED PHASE: This test will fail - no implementation yet.
        """
        from azlin.cli import parse_args

        args = parse_args(["--repo", "https://github.com/user/repo"])

        assert args.repo == "https://github.com/user/repo"
        assert hasattr(args, "vm_size")  # Should have default values
        assert hasattr(args, "region")

    def test_cli_without_repo_argument(self):
        """Test CLI without --repo argument.

        RED PHASE: This test will fail - no implementation yet.
        """
        from azlin.cli import parse_args

        args = parse_args([])

        assert args.repo is None  # No repo specified
        assert hasattr(args, "vm_size")
        assert hasattr(args, "region")

    def test_cli_accepts_vm_size_argument(self):
        """Test that CLI accepts --vm-size argument."""
        from azlin.cli import parse_args

        args = parse_args(["--vm-size", "Standard_D4s_v3"])

        assert args.vm_size == "Standard_D4s_v3"

    def test_cli_accepts_region_argument(self):
        """Test that CLI accepts --region argument."""
        from azlin.cli import parse_args

        args = parse_args(["--region", "westus2"])

        assert args.region == "westus2"

    def test_cli_has_default_vm_size(self):
        """Test that CLI has default VM size."""
        from azlin.cli import parse_args

        args = parse_args([])

        assert args.vm_size == "Standard_D2s_v3"  # Default size

    def test_cli_has_default_region(self):
        """Test that CLI has default region."""
        from azlin.cli import parse_args

        args = parse_args([])

        assert args.region == "eastus"  # Default region


# ============================================================================
# CONFIGURATION OPTIONS TESTS
# ============================================================================


class TestCLIConfigurationOptions:
    """Test CLI configuration options."""

    def test_cli_accepts_no_auto_connect_flag(self):
        """Test --no-auto-connect flag disables SSH auto-connect."""
        from azlin.cli import parse_args

        args = parse_args(["--no-auto-connect"])

        assert args.auto_connect is False

    def test_auto_connect_default_is_true(self):
        """Test that auto-connect defaults to True."""
        from azlin.cli import parse_args

        args = parse_args([])

        assert args.auto_connect is True

    def test_cli_accepts_config_file_argument(self):
        """Test --config argument for custom config file."""
        from azlin.cli import parse_args

        args = parse_args(["--config", "/path/to/config.yaml"])

        assert args.config == "/path/to/config.yaml"

    def test_cli_accepts_resource_group_argument(self):
        """Test --resource-group argument."""
        from azlin.cli import parse_args

        args = parse_args(["--resource-group", "custom-rg"])

        assert args.resource_group == "custom-rg"


# ============================================================================
# HELP AND VERSION TESTS
# ============================================================================


class TestCLIHelpAndVersion:
    """Test CLI help text and version display."""

    def test_cli_shows_help_with_dash_h(self):
        """Test that -h shows help text."""
        from azlin.cli import parse_args

        with pytest.raises(SystemExit) as exc_info:
            parse_args(["-h"])

        assert exc_info.value.code == 0

    def test_cli_shows_help_with_help_flag(self):
        """Test that --help shows help text."""
        from azlin.cli import parse_args

        with pytest.raises(SystemExit) as exc_info:
            parse_args(["--help"])

        assert exc_info.value.code == 0

    def test_cli_shows_version(self):
        """Test that --version shows version."""
        from azlin.cli import parse_args

        with pytest.raises(SystemExit) as exc_info:
            parse_args(["--version"])

        assert exc_info.value.code == 0


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


class TestCLIErrorHandling:
    """Test CLI error handling and validation."""

    def test_cli_rejects_invalid_vm_size(self):
        """Test that invalid VM size is rejected."""
        from azlin.cli import CLIError, parse_args

        with pytest.raises((CLIError, SystemExit)):
            parse_args(["--vm-size", "InvalidSize"])

    def test_cli_rejects_invalid_region(self):
        """Test that invalid region is rejected."""
        from azlin.cli import CLIError, parse_args

        with pytest.raises((CLIError, SystemExit)):
            parse_args(["--region", "invalid-region"])

    def test_cli_rejects_invalid_repo_url(self):
        """Test that invalid repository URL is rejected."""
        from azlin.cli import CLIError, parse_args

        with pytest.raises((CLIError, SystemExit)):
            parse_args(["--repo", "not-a-valid-url"])


# ============================================================================
# MAIN ENTRY POINT TESTS
# ============================================================================


class TestCLIMainEntryPoint:
    """Test CLI main entry point."""

    def test_main_function_exists(self):
        """Test that main() function exists."""
        from azlin.cli import main

        assert callable(main)

    @patch("azlin.cli.AzlinOrchestrator")
    def test_main_creates_orchestrator(self, mock_orchestrator):
        """Test that main() creates AzlinOrchestrator."""
        from azlin.cli import main

        # Mock sys.argv
        with patch("sys.argv", ["azlin", "--repo", "https://github.com/user/repo"]), contextlib.suppress(SystemExit):
            main()

        mock_orchestrator.assert_called_once()

    @patch("azlin.cli.AzlinOrchestrator")
    def test_main_handles_keyboard_interrupt(self, mock_orchestrator):
        """Test that main() handles KeyboardInterrupt gracefully."""
        from azlin.cli import main

        mock_orchestrator.return_value.run.side_effect = KeyboardInterrupt()

        with patch("sys.argv", ["azlin"]), pytest.raises(SystemExit) as exc_info:
            main()

        # Should exit with code 130 (128 + SIGINT)
        assert exc_info.value.code in (130, 1)

    @patch("azlin.cli.AzlinOrchestrator")
    def test_main_handles_general_exception(self, mock_orchestrator):
        """Test that main() handles general exceptions."""
        from azlin.cli import main

        mock_orchestrator.return_value.run.side_effect = Exception("Test error")

        with patch("sys.argv", ["azlin"]), pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1


# ============================================================================
# CONFIGURATION MERGING TESTS
# ============================================================================


class TestCLIConfigurationMerging:
    """Test merging of CLI args with config file."""

    def test_cli_args_override_config_file(self, tmp_path):
        """Test that CLI arguments override config file values."""
        from azlin.cli import load_config

        # Create a config file
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
vm:
  size: Standard_D2s_v3
  region: eastus
"""
        )

        # Load config with CLI overrides
        config = load_config(
            config_file=str(config_file), vm_size="Standard_D4s_v3", region="westus2"
        )

        assert config["vm"]["size"] == "Standard_D4s_v3"  # CLI override
        assert config["vm"]["region"] == "westus2"  # CLI override

    def test_config_file_provides_defaults(self, tmp_path):
        """Test that config file provides defaults when CLI args not specified."""
        from azlin.cli import load_config

        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
vm:
  size: Standard_D4s_v3
  region: westus2
tools:
  - git
  - python3
"""
        )

        config = load_config(config_file=str(config_file))

        assert config["vm"]["size"] == "Standard_D4s_v3"
        assert config["vm"]["region"] == "westus2"
        assert "git" in config["tools"]
