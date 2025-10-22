"""TDD Tests for Issue #166: azdoit standalone CLI.

These tests follow TDD principles and WILL FAIL until implementation is complete.

Design Requirements:
- Create azdoit_main() entry point in cli.py
- Extract _do_impl() shared implementation
- Add azdoit script to pyproject.toml
- Maintain backward compatibility with azlin do

Test Coverage:
1. azdoit_main() entry point exists and is callable
2. azdoit CLI accepts natural language prompts
3. azdoit delegates to same implementation as azlin do
4. Backward compatibility: azlin do still works
5. Both CLIs share identical behavior
6. Error handling works in both CLIs
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

# Mock all external dependencies before importing cli to allow tests to focus on structure
mock_modules = [
    "anthropic",
    "tomli",
    "tomli_w",
    "azure",
    "azure.identity",
    "azure.mgmt",
    "azure.mgmt.compute",
    "azure.mgmt.network",
    "azure.mgmt.resource",
    "azure.mgmt.costmanagement",
    "rich",
    "rich.console",
    "rich.table",
    "rich.progress",
    "pyyaml",
    "yaml",
]

for mod in mock_modules:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

# Now we can import - tests will use mocks and patches as needed
# ruff: noqa: E402
from click.testing import CliRunner

from azlin.cli import main


class TestAzdoitEntryPoint:
    """Test that azdoit_main() entry point exists (TDD: RED phase)."""

    def test_azdoit_main_exists(self):
        """Test that azdoit_main() function exists in cli module.

        RED PHASE: This will fail - function doesn't exist yet.
        """
        from azlin import cli

        assert hasattr(cli, "azdoit_main"), "azdoit_main() entry point not found in cli.py"
        assert callable(cli.azdoit_main), "azdoit_main must be callable"

    def test_azdoit_main_is_click_command(self):
        """Test that azdoit_main() is a Click command.

        RED PHASE: This will fail - function doesn't exist yet.
        """
        from azlin import cli

        assert hasattr(cli, "azdoit_main")
        # Click commands have a params attribute after @click.command() decoration
        assert hasattr(cli.azdoit_main, "params"), "azdoit_main should be a Click command"

    def test_azdoit_main_accepts_request_argument(self):
        """Test that azdoit_main() accepts REQUEST argument.

        RED PHASE: This will fail - function doesn't exist yet.
        """
        from azlin import cli

        runner = CliRunner()
        # Should accept a request argument without error
        result = runner.invoke(cli.azdoit_main, ["--help"])

        assert result.exit_code == 0
        assert "REQUEST" in result.output or "request" in result.output.lower()


class TestAzdoitCLIBasicUsage:
    """Test that azdoit CLI accepts and processes natural language (TDD: RED phase)."""

    @patch("azlin.cli.IntentParser")
    @patch("azlin.cli.CommandExecutor")
    @patch("azlin.cli.ResultValidator")
    @patch("os.getenv")
    def test_azdoit_accepts_natural_language_request(
        self, mock_getenv, mock_validator, mock_executor, mock_parser
    ):
        """Test that azdoit processes natural language requests.

        RED PHASE: This will fail - azdoit_main doesn't exist yet.
        """
        from azlin import cli

        # Setup mocks
        mock_getenv.return_value = "test-api-key"
        mock_parser_instance = MagicMock()
        mock_parser.return_value = mock_parser_instance
        mock_parser_instance.parse.return_value = {
            "intent": "list_vms",
            "confidence": 0.95,
            "azlin_commands": [{"command": "list", "args": []}],
        }

        mock_executor_instance = MagicMock()
        mock_executor.return_value = mock_executor_instance
        mock_executor_instance.execute_plan.return_value = [
            {"success": True, "command": "list", "stdout": "VM list", "stderr": ""}
        ]

        mock_validator_instance = MagicMock()
        mock_validator.return_value = mock_validator_instance
        mock_validator_instance.validate.return_value = {
            "success": True,
            "message": "Successfully listed VMs",
        }

        runner = CliRunner()
        result = runner.invoke(cli.azdoit_main, ["list all my vms", "--yes"])

        # Should execute successfully
        assert result.exit_code == 0
        assert mock_parser_instance.parse.called
        assert mock_executor_instance.execute_plan.called

    @patch("azlin.cli.IntentParser")
    @patch("os.getenv")
    def test_azdoit_shows_help(self, mock_getenv, mock_parser):
        """Test that azdoit --help shows help text.

        RED PHASE: This will fail - azdoit_main doesn't exist yet.
        """
        from azlin import cli

        runner = CliRunner()
        result = runner.invoke(cli.azdoit_main, ["--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output or "usage:" in result.output.lower()
        # Should describe natural language capability
        assert (
            "natural language" in result.output.lower() or "plain english" in result.output.lower()
        )

    @patch("os.getenv")
    def test_azdoit_requires_api_key(self, mock_getenv):
        """Test that azdoit requires ANTHROPIC_API_KEY.

        RED PHASE: This will fail - azdoit_main doesn't exist yet.
        """
        from azlin import cli

        mock_getenv.return_value = None  # No API key set

        runner = CliRunner()
        result = runner.invoke(cli.azdoit_main, ["list my vms", "--yes"])

        # Should fail with clear error message
        assert result.exit_code != 0
        assert "ANTHROPIC_API_KEY" in result.output


class TestSharedImplementation:
    """Test that azdoit and azlin do share the same implementation (TDD: RED phase)."""

    def test_do_impl_function_exists(self):
        """Test that _do_impl() shared function exists.

        RED PHASE: This will fail - _do_impl doesn't exist yet.
        """
        from azlin import cli

        assert hasattr(cli, "_do_impl"), "_do_impl() shared function not found in cli.py"
        assert callable(cli._do_impl), "_do_impl must be callable"

    @patch("azlin.cli._do_impl")
    @patch("os.getenv")
    def test_azdoit_delegates_to_do_impl(self, mock_getenv, mock_do_impl):
        """Test that azdoit_main() calls _do_impl().

        RED PHASE: This will fail - neither function exists yet.
        """
        from azlin import cli

        mock_getenv.return_value = "test-api-key"
        mock_do_impl.return_value = None

        runner = CliRunner()
        _ = runner.invoke(cli.azdoit_main, ["test request", "--yes", "--dry-run"])

        # Should delegate to shared implementation
        assert mock_do_impl.called
        call_args = mock_do_impl.call_args
        assert call_args is not None

    @patch("azlin.cli._do_impl")
    @patch("os.getenv")
    def test_azlin_do_delegates_to_do_impl(self, mock_getenv, mock_do_impl):
        """Test that 'azlin do' command calls _do_impl().

        RED PHASE: This will fail - _do_impl doesn't exist yet.
        """
        mock_getenv.return_value = "test-api-key"
        mock_do_impl.return_value = None

        runner = CliRunner()
        _ = runner.invoke(main, ["do", "test request", "--yes", "--dry-run"])

        # Should delegate to shared implementation
        assert mock_do_impl.called

    @patch("azlin.cli.IntentParser")
    @patch("azlin.cli.CommandExecutor")
    @patch("azlin.cli.ResultValidator")
    @patch("os.getenv")
    def test_both_clis_produce_identical_behavior(
        self, mock_getenv, mock_validator, mock_executor, mock_parser
    ):
        """Test that azdoit and azlin do produce identical results.

        RED PHASE: This will fail - azdoit_main doesn't exist yet.
        """
        from azlin import cli

        # Setup mocks
        mock_getenv.return_value = "test-api-key"
        mock_parser_instance = MagicMock()
        mock_parser.return_value = mock_parser_instance
        mock_parser_instance.parse.return_value = {
            "intent": "list_vms",
            "confidence": 0.95,
            "azlin_commands": [{"command": "list", "args": []}],
        }

        mock_executor_instance = MagicMock()
        mock_executor.return_value = mock_executor_instance
        mock_executor_instance.execute_plan.return_value = [
            {"success": True, "command": "list", "stdout": "VM list", "stderr": ""}
        ]

        mock_validator_instance = MagicMock()
        mock_validator.return_value = mock_validator_instance
        mock_validator_instance.validate.return_value = {
            "success": True,
            "message": "Successfully listed VMs",
        }

        runner = CliRunner()

        # Test azdoit
        result1 = runner.invoke(cli.azdoit_main, ["list all my vms", "--yes"])

        # Both should succeed
        assert result1.exit_code == 0
        # First command should have called parse
        assert mock_parser_instance.parse.call_count == 1

        # Reset mocks
        mock_parser_instance.reset_mock()
        mock_executor_instance.reset_mock()
        mock_validator_instance.reset_mock()

        # Test azlin do
        result2 = runner.invoke(main, ["do", "list all my vms", "--yes"])

        # Should also succeed
        assert result2.exit_code == 0

        # Second command should also have called parse
        assert mock_parser_instance.parse.call_count == 1


class TestBackwardCompatibility:
    """Test that azlin do command still works (TDD: RED phase but should PASS)."""

    def test_azlin_do_command_exists(self):
        """Test that 'azlin do' command still exists.

        GREEN PHASE: This should pass - azlin do already exists.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["do", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output or "usage:" in result.output.lower()
        assert "natural language" in result.output.lower()

    @patch("azlin.cli.IntentParser")
    @patch("azlin.cli.CommandExecutor")
    @patch("azlin.cli.ResultValidator")
    @patch("os.getenv")
    def test_azlin_do_still_processes_requests(
        self, mock_getenv, mock_validator, mock_executor, mock_parser
    ):
        """Test that 'azlin do' still processes natural language.

        GREEN PHASE: This should pass - azlin do functionality is unchanged.
        """
        # Setup mocks
        mock_getenv.return_value = "test-api-key"
        mock_parser_instance = MagicMock()
        mock_parser.return_value = mock_parser_instance
        mock_parser_instance.parse.return_value = {
            "intent": "list_vms",
            "confidence": 0.95,
            "azlin_commands": [{"command": "list", "args": []}],
        }

        mock_executor_instance = MagicMock()
        mock_executor.return_value = mock_executor_instance
        mock_executor_instance.execute_plan.return_value = [
            {"success": True, "command": "list", "stdout": "VM list", "stderr": ""}
        ]

        mock_validator_instance = MagicMock()
        mock_validator.return_value = mock_validator_instance
        mock_validator_instance.validate.return_value = {
            "success": True,
            "message": "Successfully listed VMs",
        }

        runner = CliRunner()
        result = runner.invoke(main, ["do", "list all my vms", "--yes"])

        # Should work exactly as before
        assert result.exit_code == 0
        assert mock_parser_instance.parse.called
        assert mock_executor_instance.execute_plan.called


class TestCLIOptions:
    """Test that both CLIs support the same options (TDD: RED phase)."""

    @patch("os.getenv")
    def test_azdoit_supports_dry_run(self, mock_getenv):
        """Test that azdoit supports --dry-run option.

        RED PHASE: This will fail - azdoit_main doesn't exist yet.
        """
        from azlin import cli

        mock_getenv.return_value = "test-api-key"

        runner = CliRunner()
        result = runner.invoke(cli.azdoit_main, ["--help"])

        assert result.exit_code == 0
        assert "--dry-run" in result.output

    @patch("os.getenv")
    def test_azdoit_supports_yes_flag(self, mock_getenv):
        """Test that azdoit supports --yes/-y flag.

        RED PHASE: This will fail - azdoit_main doesn't exist yet.
        """
        from azlin import cli

        mock_getenv.return_value = "test-api-key"

        runner = CliRunner()
        result = runner.invoke(cli.azdoit_main, ["--help"])

        assert result.exit_code == 0
        assert "--yes" in result.output or "-y" in result.output

    @patch("os.getenv")
    def test_azdoit_supports_verbose_flag(self, mock_getenv):
        """Test that azdoit supports --verbose/-v flag.

        RED PHASE: This will fail - azdoit_main doesn't exist yet.
        """
        from azlin import cli

        mock_getenv.return_value = "test-api-key"

        runner = CliRunner()
        result = runner.invoke(cli.azdoit_main, ["--help"])

        assert result.exit_code == 0
        assert "--verbose" in result.output or "-v" in result.output

    @patch("os.getenv")
    def test_azdoit_supports_resource_group_option(self, mock_getenv):
        """Test that azdoit supports --resource-group/--rg option.

        RED PHASE: This will fail - azdoit_main doesn't exist yet.
        """
        from azlin import cli

        mock_getenv.return_value = "test-api-key"

        runner = CliRunner()
        result = runner.invoke(cli.azdoit_main, ["--help"])

        assert result.exit_code == 0
        assert "--resource-group" in result.output or "--rg" in result.output

    @patch("os.getenv")
    def test_azdoit_supports_config_option(self, mock_getenv):
        """Test that azdoit supports --config option.

        RED PHASE: This will fail - azdoit_main doesn't exist yet.
        """
        from azlin import cli

        mock_getenv.return_value = "test-api-key"

        runner = CliRunner()
        result = runner.invoke(cli.azdoit_main, ["--help"])

        assert result.exit_code == 0
        assert "--config" in result.output


class TestErrorHandling:
    """Test error handling in both CLIs (TDD: RED phase)."""

    @patch("azlin.cli.IntentParser")
    @patch("os.getenv")
    def test_azdoit_handles_parse_errors(self, mock_getenv, mock_parser):
        """Test that azdoit handles IntentParseError gracefully.

        RED PHASE: This will fail - azdoit_main doesn't exist yet.
        """
        from azlin import cli

        mock_getenv.return_value = "test-api-key"
        mock_parser_instance = MagicMock()
        mock_parser.return_value = mock_parser_instance
        mock_parser_instance.parse.side_effect = cli.IntentParseError("Failed to parse")

        runner = CliRunner()
        result = runner.invoke(cli.azdoit_main, ["invalid gibberish request", "--yes"])

        # Should fail gracefully with helpful message
        assert result.exit_code != 0
        assert "Failed to parse" in result.output

    @patch("azlin.cli.IntentParser")
    @patch("azlin.cli.CommandExecutor")
    @patch("os.getenv")
    def test_azdoit_handles_execution_errors(self, mock_getenv, mock_executor, mock_parser):
        """Test that azdoit handles CommandExecutionError gracefully.

        RED PHASE: This will fail - azdoit_main doesn't exist yet.
        """
        from azlin import cli

        mock_getenv.return_value = "test-api-key"
        mock_parser_instance = MagicMock()
        mock_parser.return_value = mock_parser_instance
        mock_parser_instance.parse.return_value = {
            "intent": "list_vms",
            "confidence": 0.95,
            "azlin_commands": [{"command": "list", "args": []}],
        }

        mock_executor_instance = MagicMock()
        mock_executor.return_value = mock_executor_instance
        mock_executor_instance.execute_plan.side_effect = cli.CommandExecutionError(
            "Execution failed"
        )

        runner = CliRunner()
        result = runner.invoke(cli.azdoit_main, ["list my vms", "--yes"])

        # Should fail gracefully with helpful message
        assert result.exit_code != 0
        assert "Execution failed" in result.output or "execution failed" in result.output.lower()

    @patch("azlin.cli.IntentParser")
    @patch("os.getenv")
    def test_azdoit_handles_low_confidence(self, mock_getenv, mock_parser):
        """Test that azdoit warns on low confidence and requires confirmation.

        RED PHASE: This will fail - azdoit_main doesn't exist yet.
        """
        from azlin import cli

        mock_getenv.return_value = "test-api-key"
        mock_parser_instance = MagicMock()
        mock_parser.return_value = mock_parser_instance
        mock_parser_instance.parse.return_value = {
            "intent": "unknown",
            "confidence": 0.3,  # Low confidence
            "azlin_commands": [],
        }

        runner = CliRunner()
        # User declines to continue (no --yes flag, and input='n')
        result = runner.invoke(cli.azdoit_main, ["ambiguous request"], input="n\n")

        # Should exit without executing
        assert result.exit_code != 0 or "Cancelled" in result.output


class TestPyprojectConfiguration:
    """Test that pyproject.toml is correctly configured (TDD: RED phase)."""

    def test_azdoit_script_defined_in_pyproject(self):
        """Test that azdoit script is defined in pyproject.toml.

        RED PHASE: This will fail - azdoit not in pyproject.toml yet.
        """
        # Use tomllib (Python 3.11+) or tomli
        try:
            import tomllib
        except ImportError:
            # Import real tomli by temporarily removing mock
            import importlib

            mock_tomli = sys.modules.get("tomli")
            if mock_tomli and isinstance(mock_tomli, MagicMock):
                del sys.modules["tomli"]
            tomli = importlib.import_module("tomli")
            if mock_tomli:
                sys.modules["tomli"] = mock_tomli
            tomllib = tomli

        # Find pyproject.toml relative to this test file
        pyproject_path = Path(__file__).parents[2] / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            config = tomllib.load(f)

        scripts = config.get("project", {}).get("scripts", {})

        # Check azdoit is defined
        assert "azdoit" in scripts, "azdoit script not found in pyproject.toml"

        # Check it points to the right entry point
        assert scripts["azdoit"] == "azlin.cli:azdoit_main", (
            "azdoit should point to azlin.cli:azdoit_main"
        )

    def test_azlin_script_still_exists(self):
        """Test that azlin script still exists in pyproject.toml.

        GREEN PHASE: This should pass - azlin already exists.
        """
        # Use tomllib (Python 3.11+) or tomli
        try:
            import tomllib
        except ImportError:
            # Import real tomli by temporarily removing mock
            import importlib

            mock_tomli = sys.modules.get("tomli")
            if mock_tomli and isinstance(mock_tomli, MagicMock):
                del sys.modules["tomli"]
            tomli = importlib.import_module("tomli")
            if mock_tomli:
                sys.modules["tomli"] = mock_tomli
            tomllib = tomli

        # Find pyproject.toml relative to this test file
        pyproject_path = Path(__file__).parents[2] / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            config = tomllib.load(f)

        scripts = config.get("project", {}).get("scripts", {})

        # Check azlin still exists
        assert "azlin" in scripts, "azlin script must remain in pyproject.toml"
        assert scripts["azlin"] == "azlin.cli:main"


class TestDocumentation:
    """Test that help text is appropriate for standalone CLI (TDD: RED phase)."""

    @patch("os.getenv")
    def test_azdoit_help_emphasizes_natural_language(self, mock_getenv):
        """Test that azdoit help text emphasizes natural language usage.

        RED PHASE: This will fail - azdoit_main doesn't exist yet.
        """
        from azlin import cli

        runner = CliRunner()
        result = runner.invoke(cli.azdoit_main, ["--help"])

        assert result.exit_code == 0
        # Should have examples
        assert "example" in result.output.lower()
        # Should mention natural language
        assert (
            "natural language" in result.output.lower() or "plain english" in result.output.lower()
        )

    @patch("os.getenv")
    def test_azdoit_help_shows_quick_start(self, mock_getenv):
        """Test that azdoit help shows quick start guide.

        RED PHASE: This will fail - azdoit_main doesn't exist yet.
        """
        from azlin import cli

        runner = CliRunner()
        result = runner.invoke(cli.azdoit_main, ["--help"])

        assert result.exit_code == 0
        # Should mention API key requirement
        assert "ANTHROPIC_API_KEY" in result.output
        # Should have usage examples
        assert "list" in result.output.lower() or "create" in result.output.lower()


@pytest.mark.integration
class TestEndToEndIntegration:
    """Integration tests to verify both CLIs work identically (TDD: RED phase)."""

    @patch("azlin.cli.IntentParser")
    @patch("azlin.cli.CommandExecutor")
    @patch("azlin.cli.ResultValidator")
    @patch("azlin.cli.ConfigManager")
    @patch("os.getenv")
    def test_complete_workflow_azdoit(
        self, mock_getenv, mock_config, mock_validator, mock_executor, mock_parser
    ):
        """Test complete workflow with azdoit CLI.

        RED PHASE: This will fail - azdoit_main doesn't exist yet.
        """
        from azlin import cli

        # Setup complete mock chain
        mock_getenv.return_value = "test-api-key"
        mock_config.get_resource_group.return_value = "test-rg"

        mock_parser_instance = MagicMock()
        mock_parser.return_value = mock_parser_instance
        mock_parser_instance.parse.return_value = {
            "intent": "list_vms",
            "confidence": 0.98,
            "explanation": "List all VMs",
            "azlin_commands": [{"command": "list", "args": ["--resource-group", "test-rg"]}],
        }

        mock_executor_instance = MagicMock()
        mock_executor.return_value = mock_executor_instance
        mock_executor_instance.execute_plan.return_value = [
            {
                "success": True,
                "command": "list",
                "stdout": "vm1\nvm2",
                "stderr": "",
            }
        ]

        mock_validator_instance = MagicMock()
        mock_validator.return_value = mock_validator_instance
        mock_validator_instance.validate.return_value = {
            "success": True,
            "message": "Successfully listed VMs",
        }

        runner = CliRunner()
        result = runner.invoke(cli.azdoit_main, ["list all my vms", "--yes", "--verbose"])

        # Complete workflow should succeed
        assert result.exit_code == 0
        assert "Successfully listed VMs" in result.output
        assert mock_parser_instance.parse.called
        assert mock_executor_instance.execute_plan.called
        assert mock_validator_instance.validate.called

    @patch("azlin.cli.IntentParser")
    @patch("azlin.cli.CommandExecutor")
    @patch("azlin.cli.ResultValidator")
    @patch("azlin.cli.ConfigManager")
    @patch("os.getenv")
    def test_complete_workflow_azlin_do(
        self, mock_getenv, mock_config, mock_validator, mock_executor, mock_parser
    ):
        """Test complete workflow with azlin do command.

        GREEN PHASE: This should pass - azlin do already works.
        """
        # Setup complete mock chain
        mock_getenv.return_value = "test-api-key"
        mock_config.get_resource_group.return_value = "test-rg"

        mock_parser_instance = MagicMock()
        mock_parser.return_value = mock_parser_instance
        mock_parser_instance.parse.return_value = {
            "intent": "list_vms",
            "confidence": 0.98,
            "explanation": "List all VMs",
            "azlin_commands": [{"command": "list", "args": ["--resource-group", "test-rg"]}],
        }

        mock_executor_instance = MagicMock()
        mock_executor.return_value = mock_executor_instance
        mock_executor_instance.execute_plan.return_value = [
            {
                "success": True,
                "command": "list",
                "stdout": "vm1\nvm2",
                "stderr": "",
            }
        ]

        mock_validator_instance = MagicMock()
        mock_validator.return_value = mock_validator_instance
        mock_validator_instance.validate.return_value = {
            "success": True,
            "message": "Successfully listed VMs",
        }

        runner = CliRunner()
        result = runner.invoke(main, ["do", "list all my vms", "--yes", "--verbose"])

        # Complete workflow should succeed
        assert result.exit_code == 0
        assert "Successfully listed VMs" in result.output
        assert mock_parser_instance.parse.called
        assert mock_executor_instance.execute_plan.called
        assert mock_validator_instance.validate.called
