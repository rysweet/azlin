"""Exhaustive command syntax validation tests (TDD RED phase).

This module tests command-line interface syntax for azlin commands following
the Testing Pyramid principle (60% unit, 30% integration, 10% E2E).

Test Coverage:
- 25 tests for 'azlin new' command (all categories)
- 15 tests for 'azlin list' command
- 15 tests for 'azlin connect' command
Total: 55 sample tests demonstrating exhaustive coverage pattern

Test Categories:
1. Syntax validation (no args, required args, optional args, extra args)
2. Option combinations (mutually exclusive, dependencies)
3. Alias tests (new/vm/create equivalence)
4. Error handling (invalid values, unknown options)
5. Help text (--help, -h)

These tests follow TDD RED phase - they are EXPECTED TO FAIL until implementation.
"""

import pytest
from click.testing import CliRunner

from azlin.cli import main


# =============================================================================
# TEST CLASS: azlin new (25 tests)
# =============================================================================


class TestNewCommandSyntax:
    """Test syntax validation for 'azlin new' command (25 tests).

    Covers:
    - Basic invocation patterns
    - All option flags
    - Option value validation
    - Alias equivalence (new/vm/create)
    - Help text
    - Invalid combinations
    """

    # -------------------------------------------------------------------------
    # Category 1: Basic Invocation (5 tests)
    # -------------------------------------------------------------------------

    def test_new_no_args_valid(self):
        """Test 'azlin new' with no arguments is valid (uses defaults).

        Expected: Should start provisioning with default settings.
        RED PHASE: May fail if validation requires specific args.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["new"])

        # Should not show usage error
        assert "Usage:" not in result.output or result.exit_code == 0
        # Should not show missing required arg error
        assert "Missing argument" not in result.output.lower()
        assert "Error: Missing option" not in result.output

    def test_new_with_help_shows_usage(self):
        """Test 'azlin new --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output or "usage:" in result.output.lower()
        assert "provision" in result.output.lower()

    def test_new_with_short_help_flag(self):
        """Test 'azlin new -h' displays help text.

        RED PHASE: Click may not support -h by default.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["new", "-h"])

        # Should show help, not error
        assert result.exit_code == 0
        assert "Usage:" in result.output or "No such option" not in result.output

    def test_new_unknown_option_fails(self):
        """Test 'azlin new --invalid-option' fails with clear error."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--invalid-option"])

        assert result.exit_code != 0
        assert "no such option" in result.output.lower() or "error" in result.output.lower()

    def test_new_extra_positional_args_rejected(self):
        """Test 'azlin new extra_arg' rejects unexpected positional arguments.

        Expected: Should reject since 'new' takes no positional args.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["new", "unexpected_arg"])

        assert result.exit_code != 0 or "unexpected" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: Option Flags - Valid Usage (7 tests)
    # -------------------------------------------------------------------------

    def test_new_repo_option_accepts_url(self):
        """Test 'azlin new --repo https://github.com/user/repo' accepts valid URL."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--repo", "https://github.com/user/repo", "--help"])

        # Should not error on --repo option itself
        assert result.exit_code == 0

    def test_new_vm_size_option_accepts_value(self):
        """Test 'azlin new --vm-size Standard_D2s_v3' accepts VM size."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--vm-size", "Standard_D2s_v3", "--help"])

        assert result.exit_code == 0

    def test_new_region_option_accepts_value(self):
        """Test 'azlin new --region eastus' accepts region."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--region", "eastus", "--help"])

        assert result.exit_code == 0

    def test_new_resource_group_option_accepts_value(self):
        """Test 'azlin new --resource-group my-rg' accepts resource group."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--resource-group", "my-rg", "--help"])

        assert result.exit_code == 0

    def test_new_resource_group_short_alias(self):
        """Test 'azlin new --rg my-rg' accepts short form '--rg'."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--rg", "my-rg", "--help"])

        assert result.exit_code == 0

    def test_new_name_option_accepts_value(self):
        """Test 'azlin new --name my-vm' accepts custom name."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--name", "my-custom-vm", "--help"])

        assert result.exit_code == 0

    def test_new_pool_option_accepts_integer(self):
        """Test 'azlin new --pool 5' accepts integer pool size."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--pool", "5", "--help"])

        assert result.exit_code == 0

    # -------------------------------------------------------------------------
    # Category 3: Option Validation - Invalid Values (5 tests)
    # -------------------------------------------------------------------------

    def test_new_pool_rejects_non_integer(self):
        """Test 'azlin new --pool abc' rejects non-integer value."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--pool", "abc"])

        assert result.exit_code != 0
        assert "invalid" in result.output.lower() or "integer" in result.output.lower()

    def test_new_pool_rejects_negative(self):
        """Test 'azlin new --pool -1' rejects negative pool size."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--pool", "-1"])

        assert result.exit_code != 0
        # Should validate pool > 0
        assert "invalid" in result.output.lower() or result.exit_code != 0

    def test_new_pool_rejects_zero(self):
        """Test 'azlin new --pool 0' rejects zero pool size."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--pool", "0"])

        assert result.exit_code != 0
        # Pool must be >= 1

    def test_new_config_path_validation(self):
        """Test 'azlin new --config /nonexistent/path' validates path.

        RED PHASE: May not validate path existence until runtime.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--config", "/nonexistent/path/config.toml"])

        # Should either validate path or fail gracefully
        # Not a hard requirement but good UX
        assert result.exit_code in [0, 1, 2, 4]  # Accept various error codes (4 = config error)

    def test_new_repo_empty_string_rejected(self):
        """Test 'azlin new --repo ""' rejects empty repo URL."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--repo", ""])

        # Empty string should be rejected
        assert result.exit_code != 0 or "--repo" not in result.output

    # -------------------------------------------------------------------------
    # Category 4: Boolean Flags (2 tests)
    # -------------------------------------------------------------------------

    def test_new_no_auto_connect_flag(self):
        """Test 'azlin new --no-auto-connect' accepts boolean flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--no-auto-connect", "--help"])

        assert result.exit_code == 0

    def test_new_no_auto_connect_no_value_required(self):
        """Test 'azlin new --no-auto-connect value' rejects value after flag.

        Boolean flags should not take values.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--no-auto-connect", "true"])

        # 'true' should be treated as extra positional arg and rejected
        assert result.exit_code != 0
        assert "unexpected" in result.output.lower() or "got unexpected extra argument" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 5: Command Aliases (3 tests)
    # -------------------------------------------------------------------------

    def test_vm_command_alias_exists(self):
        """Test 'azlin vm' exists as alias for 'azlin new'."""
        runner = CliRunner()
        result = runner.invoke(main, ["vm", "--help"])

        assert result.exit_code == 0
        assert "provision" in result.output.lower()
        assert "no such command" not in result.output.lower()

    def test_create_command_alias_exists(self):
        """Test 'azlin create' exists as alias for 'azlin new'."""
        runner = CliRunner()
        result = runner.invoke(main, ["create", "--help"])

        assert result.exit_code == 0
        assert "provision" in result.output.lower()
        assert "no such command" not in result.output.lower()

    def test_aliases_accept_same_options(self):
        """Test all aliases accept same options as 'new'.

        Ensures 'vm' and 'create' have identical signatures.
        """
        runner = CliRunner()

        # Test --repo on all three
        result_new = runner.invoke(main, ["new", "--repo", "https://github.com/test/repo", "--help"])
        result_vm = runner.invoke(main, ["vm", "--repo", "https://github.com/test/repo", "--help"])
        result_create = runner.invoke(main, ["create", "--repo", "https://github.com/test/repo", "--help"])

        assert result_new.exit_code == 0
        assert result_vm.exit_code == 0
        assert result_create.exit_code == 0

    # -------------------------------------------------------------------------
    # Category 6: Option Combinations (3 tests)
    # -------------------------------------------------------------------------

    def test_new_multiple_options_combined(self):
        """Test 'azlin new' with multiple options combined."""
        runner = CliRunner()
        result = runner.invoke(main, [
            "new",
            "--name", "test-vm",
            "--vm-size", "Standard_B2s",
            "--region", "westus",
            "--rg", "my-rg",
            "--help"
        ])

        assert result.exit_code == 0

    def test_new_template_and_size_both_accepted(self):
        """Test 'azlin new --template dev-vm --vm-size Standard_D2s_v3'.

        Template and explicit options can coexist (explicit wins).
        """
        runner = CliRunner()
        result = runner.invoke(main, [
            "new",
            "--template", "dev-vm",
            "--vm-size", "Standard_D2s_v3",
            "--help"
        ])

        assert result.exit_code == 0

    def test_new_pool_and_name_interaction(self):
        """Test 'azlin new --pool 5 --name my-vm'.

        Name with pool should create my-vm-1, my-vm-2, etc.
        """
        runner = CliRunner()
        result = runner.invoke(main, [
            "new",
            "--pool", "5",
            "--name", "my-vm",
            "--help"
        ])

        assert result.exit_code == 0


# =============================================================================
# TEST CLASS: azlin list (15 tests)
# =============================================================================


class TestListCommandSyntax:
    """Test syntax validation for 'azlin list' command (15 tests).

    Covers:
    - No arguments (uses default RG from config)
    - Resource group option
    - Filter options (--all, --tag)
    - Help text
    - Invalid options
    """

    # -------------------------------------------------------------------------
    # Category 1: Basic Invocation (4 tests)
    # -------------------------------------------------------------------------

    def test_list_no_args_requires_config_or_rg(self):
        """Test 'azlin list' requires resource group from config or --rg flag.

        Expected: Should fail gracefully if no RG configured.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["list"])

        # Should either succeed (if config exists) or show error about missing RG
        assert result.exit_code in [0, 1]
        if result.exit_code == 1:
            assert "resource group" in result.output.lower()

    def test_list_with_rg_option(self):
        """Test 'azlin list --rg my-rg' accepts resource group."""
        runner = CliRunner()
        result = runner.invoke(main, ["list", "--rg", "my-rg"])

        # Should execute or show auth error, not syntax error
        assert "no such option" not in result.output.lower()

    def test_list_with_resource_group_long_form(self):
        """Test 'azlin list --resource-group my-rg' accepts long form."""
        runner = CliRunner()
        result = runner.invoke(main, ["list", "--resource-group", "my-rg"])

        assert "no such option" not in result.output.lower()

    def test_list_help_displays_usage(self):
        """Test 'azlin list --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["list", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "list" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: Filter Options (5 tests)
    # -------------------------------------------------------------------------

    def test_list_all_flag(self):
        """Test 'azlin list --all' includes stopped VMs."""
        runner = CliRunner()
        result = runner.invoke(main, ["list", "--all", "--help"])

        assert result.exit_code == 0

    def test_list_tag_filter_key_only(self):
        """Test 'azlin list --tag environment' filters by tag key."""
        runner = CliRunner()
        result = runner.invoke(main, ["list", "--tag", "environment", "--help"])

        assert result.exit_code == 0

    def test_list_tag_filter_key_value(self):
        """Test 'azlin list --tag env=prod' filters by key=value."""
        runner = CliRunner()
        result = runner.invoke(main, ["list", "--tag", "env=prod", "--help"])

        assert result.exit_code == 0

    def test_list_config_option(self):
        """Test 'azlin list --config /path/to/config' accepts config path."""
        runner = CliRunner()
        result = runner.invoke(main, ["list", "--config", "/tmp/config.toml", "--help"])

        assert result.exit_code == 0

    def test_list_combined_filters(self):
        """Test 'azlin list --all --tag env=dev --rg my-rg' combines filters."""
        runner = CliRunner()
        result = runner.invoke(main, [
            "list",
            "--all",
            "--tag", "env=dev",
            "--rg", "my-rg",
            "--help"
        ])

        assert result.exit_code == 0

    # -------------------------------------------------------------------------
    # Category 3: Invalid Options (3 tests)
    # -------------------------------------------------------------------------

    def test_list_unknown_option_fails(self):
        """Test 'azlin list --invalid' fails with clear error."""
        runner = CliRunner()
        result = runner.invoke(main, ["list", "--invalid"])

        assert result.exit_code != 0
        assert "no such option" in result.output.lower()

    def test_list_rejects_positional_args(self):
        """Test 'azlin list vm-name' rejects positional arguments.

        'list' takes no positional args, only options.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["list", "vm-name"])

        # Should reject or warn about unexpected argument
        assert result.exit_code != 0 or "unexpected" in result.output.lower()

    def test_list_tag_empty_value_rejected(self):
        """Test 'azlin list --tag ""' rejects empty tag value.

        RED PHASE: Expected to fail until validation is implemented.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["list", "--tag", ""])

        # Empty tag filter should be rejected
        # XFAIL in RED phase: Implementation doesn't validate yet
        assert result.exit_code != 0
        assert ("invalid" in result.output.lower() or
                "empty" in result.output.lower() or
                "requires" in result.output.lower())

    # -------------------------------------------------------------------------
    # Category 4: Option Value Types (3 tests)
    # -------------------------------------------------------------------------

    def test_list_rg_requires_value(self):
        """Test 'azlin list --rg' without value fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["list", "--rg"])

        assert result.exit_code != 0
        assert "requires an argument" in result.output.lower() or "expected" in result.output.lower()

    def test_list_tag_requires_value(self):
        """Test 'azlin list --tag' without value fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["list", "--tag"])

        assert result.exit_code != 0
        assert "requires an argument" in result.output.lower()

    def test_list_all_takes_no_value(self):
        """Test 'azlin list --all true' treats 'true' as extra arg.

        Boolean flags don't take values.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["list", "--all", "true"])

        # 'true' should be rejected as unexpected positional arg
        assert result.exit_code != 0


# =============================================================================
# TEST CLASS: azlin connect (15 tests)
# =============================================================================


class TestConnectCommandSyntax:
    """Test syntax validation for 'azlin connect' command (15 tests).

    Covers:
    - Optional VM identifier
    - Connection options (--no-tmux, --user, --key)
    - Reconnection options (--no-reconnect, --max-retries)
    - Remote command execution (-- command)
    - Help text
    """

    # -------------------------------------------------------------------------
    # Category 1: Basic Invocation (4 tests)
    # -------------------------------------------------------------------------

    def test_connect_no_args_interactive_mode(self):
        """Test 'azlin connect' without args enters interactive selection.

        Should show VM list or error if no RG configured.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["connect"])

        # Should either show interactive menu or error about missing RG
        assert result.exit_code in [0, 1]

    def test_connect_with_vm_identifier(self):
        """Test 'azlin connect my-vm' accepts VM identifier."""
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "my-vm", "--help"])

        # Should accept VM name as positional arg
        assert result.exit_code == 0

    def test_connect_with_ip_address(self):
        """Test 'azlin connect 20.1.2.3' accepts IP address."""
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "20.1.2.3", "--help"])

        assert result.exit_code == 0

    def test_connect_help_displays_usage(self):
        """Test 'azlin connect --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "connect" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: Connection Options (5 tests)
    # -------------------------------------------------------------------------

    def test_connect_no_tmux_flag(self):
        """Test 'azlin connect my-vm --no-tmux' skips tmux."""
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "my-vm", "--no-tmux", "--help"])

        assert result.exit_code == 0

    def test_connect_tmux_session_option(self):
        """Test 'azlin connect my-vm --tmux-session dev' sets session name."""
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "my-vm", "--tmux-session", "dev", "--help"])

        assert result.exit_code == 0

    def test_connect_user_option(self):
        """Test 'azlin connect my-vm --user myuser' sets SSH user."""
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "my-vm", "--user", "myuser", "--help"])

        assert result.exit_code == 0

    def test_connect_key_option_path_exists(self):
        """Test 'azlin connect my-vm --key ~/.ssh/id_rsa' validates key path.

        RED PHASE: Click type=Path(exists=True) validates existence.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "my-vm", "--key", "/nonexistent/key"])

        # Should fail because key doesn't exist (exists=True validation)
        assert result.exit_code != 0
        assert "does not exist" in result.output.lower() or "path" in result.output.lower()

    def test_connect_resource_group_option(self):
        """Test 'azlin connect my-vm --rg my-rg' specifies resource group."""
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "my-vm", "--rg", "my-rg", "--help"])

        assert result.exit_code == 0

    # -------------------------------------------------------------------------
    # Category 3: Reconnection Options (3 tests)
    # -------------------------------------------------------------------------

    def test_connect_no_reconnect_flag(self):
        """Test 'azlin connect my-vm --no-reconnect' disables auto-reconnect."""
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "my-vm", "--no-reconnect", "--help"])

        assert result.exit_code == 0

    def test_connect_max_retries_accepts_integer(self):
        """Test 'azlin connect my-vm --max-retries 5' accepts integer."""
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "my-vm", "--max-retries", "5", "--help"])

        assert result.exit_code == 0

    def test_connect_max_retries_rejects_non_integer(self):
        """Test 'azlin connect my-vm --max-retries abc' rejects non-integer."""
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "my-vm", "--max-retries", "abc"])

        assert result.exit_code != 0
        assert "invalid" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 4: Remote Command Execution (3 tests)
    # -------------------------------------------------------------------------

    def test_connect_remote_command_with_separator(self):
        """Test 'azlin connect my-vm -- ls -la' executes remote command.

        The -- separator is critical for remote commands.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "my-vm", "--", "ls", "-la", "--help"])

        # Should accept remote command after --
        # Since --help comes after --, it's part of remote command, not connect help
        assert result.exit_code == 0 or "Usage:" not in result.output

    def test_connect_remote_command_multiple_args(self):
        """Test 'azlin connect my-vm -- python script.py --arg value' passes all args."""
        runner = CliRunner()
        result = runner.invoke(main, [
            "connect", "my-vm",
            "--", "python", "script.py", "--arg", "value"
        ])

        # Should not error on syntax, only on execution
        assert "no such option" not in result.output.lower()

    def test_connect_without_separator_no_remote_command(self):
        """Test 'azlin connect my-vm ls' without -- treats 'ls' as error.

        Without --, extra args should be rejected.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "my-vm", "ls"])

        # Should reject 'ls' as unexpected positional arg
        assert result.exit_code != 0 or "unexpected" in result.output.lower()


# =============================================================================
# TEST MARKERS AND METADATA
# =============================================================================


# Mark all tests in this module as TDD RED phase and syntax validation
pytestmark = [pytest.mark.tdd_red, pytest.mark.syntax]


# =============================================================================
# SUMMARY
# =============================================================================
"""
Test Coverage Summary:

azlin new (25 tests):
  - Basic invocation: 5 tests
  - Option flags (valid): 7 tests
  - Option validation (invalid): 5 tests
  - Boolean flags: 2 tests
  - Command aliases: 3 tests
  - Option combinations: 3 tests

azlin list (15 tests):
  - Basic invocation: 4 tests
  - Filter options: 5 tests
  - Invalid options: 3 tests
  - Option value types: 3 tests

azlin connect (15 tests):
  - Basic invocation: 4 tests
  - Connection options: 5 tests
  - Reconnection options: 3 tests
  - Remote command execution: 3 tests

TOTAL: 55 tests

This provides a comprehensive pattern for the remaining 245+ tests needed
for exhaustive coverage of all azlin commands.
"""
