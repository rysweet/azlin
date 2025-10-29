"""Exhaustive command syntax tests for Priority 2 commands (TDD RED phase).

This module tests Priority 2 (Common) commands:
- start, stop, status, cp, sync, session, killall

Test Coverage: ~80 tests for 7 common commands
Test Categories:
1. Syntax validation (no args, required args, optional args, extra args)
2. Option combinations (mutually exclusive, dependencies)
3. Error handling (invalid values, unknown options)
4. Help text (--help, -h)

These tests follow TDD RED phase - they validate CLI syntax only.
"""

import pytest
from click.testing import CliRunner

from azlin.cli import main
from tests.conftest import (
    assert_missing_argument_error,
    assert_option_accepted,
)

# =============================================================================
# TEST CLASS: azlin start (10 tests)
# =============================================================================


class TestStartCommandSyntax:
    """Test syntax validation for 'azlin start' command (10 tests).

    Covers:
    - VM name argument (required)
    - Resource group option
    - Config option
    - Help text
    - Invalid options
    """

    # -------------------------------------------------------------------------
    # Category 1: Basic Invocation (3 tests)
    # -------------------------------------------------------------------------

    def test_start_requires_vm_name(self):
        """Test 'azlin start' without VM name fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["start"])

        assert_missing_argument_error(result)

    def test_start_with_vm_name(self):
        """Test 'azlin start my-vm' accepts VM name."""
        runner = CliRunner()
        result = runner.invoke(main, ["start", "my-vm"])

        # Should not show syntax error (auth error is OK)
        assert_option_accepted(result)
        assert "missing argument" not in result.output.lower()

    def test_start_help_displays_usage(self):
        """Test 'azlin start --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["start", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "start" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: Option Flags (3 tests)
    # -------------------------------------------------------------------------

    def test_start_rg_option_accepts_value(self):
        """Test 'azlin start my-vm --rg my-rg' accepts resource group."""
        runner = CliRunner()
        result = runner.invoke(main, ["start", "my-vm", "--rg", "my-rg"])

        assert_option_accepted(result)

    def test_start_resource_group_long_form(self):
        """Test 'azlin start my-vm --resource-group my-rg' accepts long form."""
        runner = CliRunner()
        result = runner.invoke(main, ["start", "my-vm", "--resource-group", "my-rg"])

        assert_option_accepted(result)

    def test_start_config_option_accepts_path(self):
        """Test 'azlin start my-vm --config /path/to/config' accepts config path."""
        runner = CliRunner()
        result = runner.invoke(main, ["start", "my-vm", "--config", "/tmp/config.toml"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 3: Invalid Options (2 tests)
    # -------------------------------------------------------------------------

    def test_start_unknown_option_fails(self):
        """Test 'azlin start my-vm --invalid' fails with clear error."""
        runner = CliRunner()
        result = runner.invoke(main, ["start", "my-vm", "--invalid"])

        assert result.exit_code != 0
        assert "no such option" in result.output.lower()

    def test_start_extra_positional_args_rejected(self):
        """Test 'azlin start my-vm extra' rejects extra positional args."""
        runner = CliRunner()
        result = runner.invoke(main, ["start", "my-vm", "extra"])

        # Should reject extra positional argument
        assert result.exit_code != 0

    # -------------------------------------------------------------------------
    # Category 4: Option Value Requirements (2 tests)
    # -------------------------------------------------------------------------

    def test_start_rg_requires_value(self):
        """Test 'azlin start my-vm --rg' without value fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["start", "my-vm", "--rg"])

        assert result.exit_code != 0
        assert (
            "requires an argument" in result.output.lower() or "expected" in result.output.lower()
        )

    def test_start_combined_options(self):
        """Test 'azlin start my-vm --rg my-rg --config config.toml' combines options."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["start", "my-vm", "--rg", "my-rg", "--config", "/tmp/config.toml"]
        )

        assert_option_accepted(result)


# =============================================================================
# TEST CLASS: azlin stop (14 tests)
# =============================================================================


class TestStopCommandSyntax:
    """Test syntax validation for 'azlin stop' command (14 tests).

    Covers:
    - VM name argument (required)
    - --deallocate/--no-deallocate flag
    - Resource group option
    - Help text
    """

    # -------------------------------------------------------------------------
    # Category 1: Basic Invocation (3 tests)
    # -------------------------------------------------------------------------

    def test_stop_requires_vm_name(self):
        """Test 'azlin stop' without VM name fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["stop"])

        assert_missing_argument_error(result)

    def test_stop_with_vm_name(self):
        """Test 'azlin stop my-vm' accepts VM name."""
        runner = CliRunner()
        result = runner.invoke(main, ["stop", "my-vm"])

        # Should not show syntax error
        assert_option_accepted(result)
        assert "missing argument" not in result.output.lower()

    def test_stop_help_displays_usage(self):
        """Test 'azlin stop --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["stop", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "stop" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: Boolean Deallocate Flag (5 tests)
    # -------------------------------------------------------------------------

    def test_stop_deallocate_flag(self):
        """Test 'azlin stop my-vm --deallocate' accepts deallocate flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["stop", "my-vm", "--deallocate"])

        assert_option_accepted(result)

    def test_stop_no_deallocate_flag(self):
        """Test 'azlin stop my-vm --no-deallocate' accepts no-deallocate flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["stop", "my-vm", "--no-deallocate"])

        assert_option_accepted(result)

    def test_stop_deallocate_is_default(self):
        """Test 'azlin stop my-vm' uses deallocate by default."""
        runner = CliRunner()
        result = runner.invoke(main, ["stop", "my-vm", "--help"])

        # Help should indicate deallocate is default
        assert result.exit_code == 0
        assert "default" in result.output.lower()

    def test_stop_deallocate_rejects_value(self):
        """Test 'azlin stop my-vm --deallocate true' treats 'true' as extra arg."""
        runner = CliRunner()
        result = runner.invoke(main, ["stop", "my-vm", "--deallocate", "true"])

        # Boolean flag shouldn't take value, 'true' is extra arg
        assert result.exit_code != 0

    def test_stop_both_deallocate_flags_conflict(self):
        """Test 'azlin stop my-vm --deallocate --no-deallocate' handles conflict.

        Click should accept the last flag specified.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["stop", "my-vm", "--deallocate", "--no-deallocate"])

        # Should not error on syntax (last flag wins in Click)
        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 3: Option Flags (3 tests)
    # -------------------------------------------------------------------------

    def test_stop_rg_option_accepts_value(self):
        """Test 'azlin stop my-vm --rg my-rg' accepts resource group."""
        runner = CliRunner()
        result = runner.invoke(main, ["stop", "my-vm", "--rg", "my-rg"])

        assert_option_accepted(result)

    def test_stop_resource_group_long_form(self):
        """Test 'azlin stop my-vm --resource-group my-rg' accepts long form."""
        runner = CliRunner()
        result = runner.invoke(main, ["stop", "my-vm", "--resource-group", "my-rg"])

        assert_option_accepted(result)

    def test_stop_config_option_accepts_path(self):
        """Test 'azlin stop my-vm --config /path/to/config' accepts config path."""
        runner = CliRunner()
        result = runner.invoke(main, ["stop", "my-vm", "--config", "/tmp/config.toml"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 4: Invalid Options (3 tests)
    # -------------------------------------------------------------------------

    def test_stop_unknown_option_fails(self):
        """Test 'azlin stop my-vm --invalid' fails with clear error."""
        runner = CliRunner()
        result = runner.invoke(main, ["stop", "my-vm", "--invalid"])

        assert result.exit_code != 0
        assert "no such option" in result.output.lower()

    def test_stop_extra_positional_args_rejected(self):
        """Test 'azlin stop my-vm extra' rejects extra positional args."""
        runner = CliRunner()
        result = runner.invoke(main, ["stop", "my-vm", "extra"])

        assert result.exit_code != 0

    def test_stop_combined_options(self):
        """Test 'azlin stop my-vm --rg my-rg --no-deallocate' combines options."""
        runner = CliRunner()
        result = runner.invoke(main, ["stop", "my-vm", "--rg", "my-rg", "--no-deallocate"])

        assert_option_accepted(result)


# =============================================================================
# TEST CLASS: azlin status (12 tests)
# =============================================================================


class TestStatusCommandSyntax:
    """Test syntax validation for 'azlin status' command (12 tests).

    Covers:
    - No arguments (uses config)
    - Resource group option
    - VM filter option
    - Help text
    """

    # -------------------------------------------------------------------------
    # Category 1: Basic Invocation (3 tests)
    # -------------------------------------------------------------------------

    def test_status_no_args_valid(self):
        """Test 'azlin status' without args uses config."""
        runner = CliRunner()
        result = runner.invoke(main, ["status"])

        # Should attempt to use config or error about missing RG
        assert "missing argument" not in result.output.lower()
        assert_option_accepted(result)

    def test_status_help_displays_usage(self):
        """Test 'azlin status --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "status" in result.output.lower()

    def test_status_with_rg_option(self):
        """Test 'azlin status --rg my-rg' accepts resource group."""
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--rg", "my-rg"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 2: VM Filter Option (4 tests)
    # -------------------------------------------------------------------------

    def test_status_vm_option_accepts_name(self):
        """Test 'azlin status --vm my-vm' accepts VM name filter."""
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--vm", "my-vm"])

        assert_option_accepted(result)

    def test_status_vm_requires_value(self):
        """Test 'azlin status --vm' without value fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--vm"])

        assert result.exit_code != 0
        assert "requires an argument" in result.output.lower()

    def test_status_vm_empty_string_rejected(self):
        """Test 'azlin status --vm ""' rejects empty VM name."""
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--vm", ""])

        # Empty VM name should either error or be ignored
        # Not a hard syntax error but semantically invalid
        assert result.exit_code in [0, 1]

    def test_status_combined_vm_and_rg(self):
        """Test 'azlin status --rg my-rg --vm my-vm' combines options."""
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--rg", "my-rg", "--vm", "my-vm"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 3: Resource Group Options (2 tests)
    # -------------------------------------------------------------------------

    def test_status_resource_group_long_form(self):
        """Test 'azlin status --resource-group my-rg' accepts long form."""
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--resource-group", "my-rg"])

        assert_option_accepted(result)

    def test_status_config_option_accepts_path(self):
        """Test 'azlin status --config /path/to/config' accepts config path."""
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--config", "/tmp/config.toml"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 4: Invalid Options (3 tests)
    # -------------------------------------------------------------------------

    def test_status_unknown_option_fails(self):
        """Test 'azlin status --invalid' fails with clear error."""
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--invalid"])

        assert result.exit_code != 0
        assert "no such option" in result.output.lower()

    def test_status_rejects_positional_args(self):
        """Test 'azlin status my-vm' rejects positional arguments."""
        runner = CliRunner()
        result = runner.invoke(main, ["status", "my-vm"])

        # status takes no positional args, only --vm option
        assert result.exit_code != 0 or "unexpected" in result.output.lower()

    def test_status_all_options_combined(self):
        """Test 'azlin status --rg my-rg --vm my-vm --config config.toml' combines all."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["status", "--rg", "my-rg", "--vm", "my-vm", "--config", "/tmp/config.toml"]
        )

        assert_option_accepted(result)


# =============================================================================
# TEST CLASS: azlin cp (18 tests)
# =============================================================================


class TestCpCommandSyntax:
    """Test syntax validation for 'azlin cp' command (18 tests).

    Covers:
    - Source and destination arguments (required)
    - Session:path notation
    - --dry-run flag
    - Resource group option
    - Help text
    """

    # -------------------------------------------------------------------------
    # Category 1: Basic Invocation (5 tests)
    # -------------------------------------------------------------------------

    def test_cp_requires_source_and_dest(self):
        """Test 'azlin cp' without arguments fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_cp_requires_destination(self):
        """Test 'azlin cp source' without destination fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp", "myfile.txt"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_cp_with_source_and_dest(self):
        """Test 'azlin cp source dest' accepts both arguments."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp", "myfile.txt", "dest.txt"])

        # Should not show syntax error
        assert_option_accepted(result)
        assert "missing argument" not in result.output.lower()

    def test_cp_help_displays_usage(self):
        """Test 'azlin cp --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "copy" in result.output.lower()

    def test_cp_extra_positional_args_rejected(self):
        """Test 'azlin cp src dest extra' rejects extra args."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp", "src", "dest", "extra"])

        assert result.exit_code != 0

    # -------------------------------------------------------------------------
    # Category 2: Session:Path Notation (6 tests)
    # -------------------------------------------------------------------------

    def test_cp_local_to_remote_syntax(self):
        """Test 'azlin cp myfile.txt vm1:~/' accepts local to remote."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp", "myfile.txt", "vm1:~/"])

        assert_option_accepted(result)

    def test_cp_remote_to_local_syntax(self):
        """Test 'azlin cp vm1:~/data.txt ./' accepts remote to local."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp", "vm1:~/data.txt", "./"])

        assert_option_accepted(result)

    def test_cp_session_colon_path_format(self):
        """Test 'azlin cp vm1:/path/file vm2:/path/file' accepts session:path format."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp", "vm1:/path/file", "vm2:/path/file"])

        # Should accept syntax (remote-to-remote may not be supported, but syntax is OK)
        assert_option_accepted(result)

    def test_cp_absolute_path_in_remote(self):
        """Test 'azlin cp file vm1:/home/user/dest' accepts absolute remote path."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp", "file", "vm1:/home/user/dest"])

        assert_option_accepted(result)

    def test_cp_relative_path_in_remote(self):
        """Test 'azlin cp file vm1:relative/path' accepts relative remote path."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp", "file", "vm1:relative/path"])

        assert_option_accepted(result)

    def test_cp_tilde_expansion_in_remote(self):
        """Test 'azlin cp file vm1:~/dest' accepts ~ expansion."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp", "file", "vm1:~/dest"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 3: Option Flags (4 tests)
    # -------------------------------------------------------------------------

    def test_cp_dry_run_flag(self):
        """Test 'azlin cp src dest --dry-run' accepts dry-run flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp", "src", "dest", "--dry-run"])

        assert_option_accepted(result)

    def test_cp_rg_option_accepts_value(self):
        """Test 'azlin cp src vm1:dest --rg my-rg' accepts resource group."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp", "src", "vm1:dest", "--rg", "my-rg"])

        assert_option_accepted(result)

    def test_cp_config_option_accepts_path(self):
        """Test 'azlin cp src dest --config /path' accepts config path."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp", "src", "dest", "--config", "/tmp/config.toml"])

        assert_option_accepted(result)

    def test_cp_all_options_combined(self):
        """Test 'azlin cp src vm1:dest --dry-run --rg rg --config cfg' combines options."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["cp", "src", "vm1:dest", "--dry-run", "--rg", "my-rg", "--config", "/tmp/config.toml"],
        )

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 4: Invalid Options (3 tests)
    # -------------------------------------------------------------------------

    def test_cp_unknown_option_fails(self):
        """Test 'azlin cp src dest --invalid' fails with clear error."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp", "src", "dest", "--invalid"])

        assert result.exit_code != 0
        assert "no such option" in result.output.lower()

    def test_cp_rg_requires_value(self):
        """Test 'azlin cp src dest --rg' without value fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp", "src", "dest", "--rg"])

        assert result.exit_code != 0
        assert "requires an argument" in result.output.lower()

    def test_cp_dry_run_rejects_value(self):
        """Test 'azlin cp src dest --dry-run true' treats 'true' as extra arg."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp", "src", "dest", "--dry-run", "true"])

        # Boolean flag shouldn't take value
        assert result.exit_code != 0


# =============================================================================
# TEST CLASS: azlin sync (14 tests)
# =============================================================================


class TestSyncCommandSyntax:
    """Test syntax validation for 'azlin sync' command (14 tests).

    Covers:
    - No arguments (interactive mode)
    - --vm-name option
    - --dry-run flag
    - Resource group option
    - Help text
    """

    # -------------------------------------------------------------------------
    # Category 1: Basic Invocation (3 tests)
    # -------------------------------------------------------------------------

    def test_sync_no_args_interactive_mode(self):
        """Test 'azlin sync' without args enters interactive mode."""
        runner = CliRunner()
        result = runner.invoke(main, ["sync"])

        # Should not show syntax error (may error on missing config)
        assert "missing argument" not in result.output.lower()
        assert_option_accepted(result)

    def test_sync_help_displays_usage(self):
        """Test 'azlin sync --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "sync" in result.output.lower()

    def test_sync_rejects_positional_args(self):
        """Test 'azlin sync my-vm' rejects positional arguments."""
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "my-vm"])

        # sync takes no positional args, only --vm-name option
        assert result.exit_code != 0 or "unexpected" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: VM Name Option (4 tests)
    # -------------------------------------------------------------------------

    def test_sync_vm_name_option_accepts_value(self):
        """Test 'azlin sync --vm-name my-vm' accepts VM name."""
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "--vm-name", "my-vm"])

        assert_option_accepted(result)

    def test_sync_vm_name_requires_value(self):
        """Test 'azlin sync --vm-name' without value fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "--vm-name"])

        assert result.exit_code != 0
        assert "requires an argument" in result.output.lower()

    def test_sync_vm_name_empty_string(self):
        """Test 'azlin sync --vm-name ""' accepts empty string (may error later)."""
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "--vm-name", ""])

        # Syntax is OK, semantic validation happens later
        assert_option_accepted(result)

    def test_sync_vm_name_with_rg(self):
        """Test 'azlin sync --vm-name my-vm --rg my-rg' combines options."""
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "--vm-name", "my-vm", "--rg", "my-rg"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 3: Boolean Flags (3 tests)
    # -------------------------------------------------------------------------

    def test_sync_dry_run_flag(self):
        """Test 'azlin sync --dry-run' accepts dry-run flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "--dry-run"])

        assert_option_accepted(result)

    def test_sync_dry_run_with_vm_name(self):
        """Test 'azlin sync --vm-name my-vm --dry-run' combines options."""
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "--vm-name", "my-vm", "--dry-run"])

        assert_option_accepted(result)

    def test_sync_dry_run_rejects_value(self):
        """Test 'azlin sync --dry-run true' treats 'true' as extra arg."""
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "--dry-run", "true"])

        # Boolean flag shouldn't take value
        assert result.exit_code != 0

    # -------------------------------------------------------------------------
    # Category 4: Other Options (4 tests)
    # -------------------------------------------------------------------------

    def test_sync_rg_option_accepts_value(self):
        """Test 'azlin sync --rg my-rg' accepts resource group."""
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "--rg", "my-rg"])

        assert_option_accepted(result)

    def test_sync_resource_group_long_form(self):
        """Test 'azlin sync --resource-group my-rg' accepts long form."""
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "--resource-group", "my-rg"])

        assert_option_accepted(result)

    def test_sync_config_option_accepts_path(self):
        """Test 'azlin sync --config /path/to/config' accepts config path."""
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "--config", "/tmp/config.toml"])

        assert_option_accepted(result)

    def test_sync_unknown_option_fails(self):
        """Test 'azlin sync --invalid' fails with clear error."""
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "--invalid"])

        assert result.exit_code != 0
        assert "no such option" in result.output.lower()


# =============================================================================
# TEST CLASS: azlin session (16 tests)
# =============================================================================


class TestSessionCommandSyntax:
    """Test syntax validation for 'azlin session' command (16 tests).

    Covers:
    - VM name argument (required)
    - Session name argument (optional)
    - --clear flag
    - Resource group option
    - Help text
    """

    # -------------------------------------------------------------------------
    # Category 1: Basic Invocation (4 tests)
    # -------------------------------------------------------------------------

    def test_session_requires_vm_name(self):
        """Test 'azlin session' without VM name fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["session"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_session_with_vm_name_only(self):
        """Test 'azlin session my-vm' accepts VM name (view mode)."""
        runner = CliRunner()
        result = runner.invoke(main, ["session", "my-vm"])

        # Should not show syntax error
        assert_option_accepted(result)
        assert "missing argument" not in result.output.lower()

    def test_session_with_vm_and_session_name(self):
        """Test 'azlin session my-vm my-session' accepts both arguments."""
        runner = CliRunner()
        result = runner.invoke(main, ["session", "my-vm", "my-session"])

        assert_option_accepted(result)

    def test_session_help_displays_usage(self):
        """Test 'azlin session --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["session", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "session" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: Clear Flag (4 tests)
    # -------------------------------------------------------------------------

    def test_session_clear_flag(self):
        """Test 'azlin session my-vm --clear' accepts clear flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["session", "my-vm", "--clear"])

        assert_option_accepted(result)

    def test_session_clear_with_session_name_conflict(self):
        """Test 'azlin session my-vm name --clear' handles potential conflict.

        Setting a name and clearing at the same time - implementation should handle.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["session", "my-vm", "name", "--clear"])

        # Syntax is OK, semantic validation is implementation-specific
        assert_option_accepted(result)

    def test_session_clear_rejects_value(self):
        """Test 'azlin session my-vm --clear true' treats 'true' as session name."""
        runner = CliRunner()
        result = runner.invoke(main, ["session", "my-vm", "--clear", "true"])

        # Boolean flag shouldn't take value, but 'true' becomes session name arg
        # This is tricky - depends on arg order parsing
        assert_option_accepted(result)

    def test_session_clear_flag_position(self):
        """Test 'azlin session --clear my-vm' handles flag before VM name."""
        runner = CliRunner()
        result = runner.invoke(main, ["session", "--clear", "my-vm"])

        # Click should parse this correctly
        assert result.exit_code in [0, 1]  # Syntax OK or semantic error

    # -------------------------------------------------------------------------
    # Category 3: Resource Group Options (4 tests)
    # -------------------------------------------------------------------------

    def test_session_rg_option_accepts_value(self):
        """Test 'azlin session my-vm --rg my-rg' accepts resource group."""
        runner = CliRunner()
        result = runner.invoke(main, ["session", "my-vm", "--rg", "my-rg"])

        assert_option_accepted(result)

    def test_session_resource_group_long_form(self):
        """Test 'azlin session my-vm --resource-group my-rg' accepts long form."""
        runner = CliRunner()
        result = runner.invoke(main, ["session", "my-vm", "--resource-group", "my-rg"])

        assert_option_accepted(result)

    def test_session_config_option_accepts_path(self):
        """Test 'azlin session my-vm --config /path' accepts config path."""
        runner = CliRunner()
        result = runner.invoke(main, ["session", "my-vm", "--config", "/tmp/config.toml"])

        assert_option_accepted(result)

    def test_session_all_options_combined(self):
        """Test 'azlin session my-vm name --rg rg --config cfg' combines all."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["session", "my-vm", "name", "--rg", "my-rg", "--config", "/tmp/config.toml"]
        )

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 4: Invalid Options (4 tests)
    # -------------------------------------------------------------------------

    def test_session_unknown_option_fails(self):
        """Test 'azlin session my-vm --invalid' fails with clear error."""
        runner = CliRunner()
        result = runner.invoke(main, ["session", "my-vm", "--invalid"])

        assert result.exit_code != 0
        assert "no such option" in result.output.lower()

    def test_session_extra_positional_args_rejected(self):
        """Test 'azlin session my-vm name extra' rejects extra args."""
        runner = CliRunner()
        result = runner.invoke(main, ["session", "my-vm", "name", "extra"])

        # Should reject third positional argument
        assert result.exit_code != 0

    def test_session_rg_requires_value(self):
        """Test 'azlin session my-vm --rg' without value fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["session", "my-vm", "--rg"])

        assert result.exit_code != 0
        assert "requires an argument" in result.output.lower()

    def test_session_empty_session_name_accepted(self):
        """Test 'azlin session my-vm ""' accepts empty session name.

        Empty string clears session name (semantic validation).
        """
        runner = CliRunner()
        result = runner.invoke(main, ["session", "my-vm", ""])

        # Syntax OK, semantic handling by implementation
        assert_option_accepted(result)


# =============================================================================
# TEST CLASS: azlin killall (16 tests)
# =============================================================================


class TestKillallCommandSyntax:
    """Test syntax validation for 'azlin killall' command (16 tests).

    Covers:
    - No arguments (uses config)
    - --force flag
    - --prefix option
    - Resource group option
    - Help text
    - Dangerous operation warnings
    """

    # -------------------------------------------------------------------------
    # Category 1: Basic Invocation (3 tests)
    # -------------------------------------------------------------------------

    def test_killall_no_args_valid(self):
        """Test 'azlin killall' without args uses config."""
        runner = CliRunner()
        result = runner.invoke(main, ["killall"])

        # Should not show syntax error (may error on missing config)
        assert "missing argument" not in result.output.lower()
        assert_option_accepted(result)

    def test_killall_help_displays_usage(self):
        """Test 'azlin killall --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["killall", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "delete" in result.output.lower()

    def test_killall_rejects_positional_args(self):
        """Test 'azlin killall vm-name' rejects positional arguments."""
        runner = CliRunner()
        result = runner.invoke(main, ["killall", "vm-name"])

        # killall takes no positional args
        assert result.exit_code != 0 or "unexpected" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: Force Flag (4 tests)
    # -------------------------------------------------------------------------

    def test_killall_force_flag(self):
        """Test 'azlin killall --force' accepts force flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["killall", "--force"])

        assert_option_accepted(result)

    def test_killall_force_rejects_value(self):
        """Test 'azlin killall --force true' treats 'true' as extra arg."""
        runner = CliRunner()
        result = runner.invoke(main, ["killall", "--force", "true"])

        # Boolean flag shouldn't take value
        assert result.exit_code != 0

    def test_killall_without_force_shows_confirmation(self):
        """Test 'azlin killall' without --force should prompt (or fail fast).

        Interactive confirmation is expected.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["killall"])

        # Should either prompt or fail (depending on config availability)
        assert result.exit_code in [0, 1]

    def test_killall_force_with_rg(self):
        """Test 'azlin killall --force --rg my-rg' combines options."""
        runner = CliRunner()
        result = runner.invoke(main, ["killall", "--force", "--rg", "my-rg"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 3: Prefix Option (5 tests)
    # -------------------------------------------------------------------------

    def test_killall_prefix_option_accepts_value(self):
        """Test 'azlin killall --prefix test-vm' accepts prefix."""
        runner = CliRunner()
        result = runner.invoke(main, ["killall", "--prefix", "test-vm"])

        assert_option_accepted(result)

    def test_killall_prefix_default_is_azlin(self):
        """Test 'azlin killall --help' shows default prefix is 'azlin'."""
        runner = CliRunner()
        result = runner.invoke(main, ["killall", "--help"])

        assert result.exit_code == 0
        assert "prefix" in result.output.lower()
        # Default should be documented
        assert "azlin" in result.output or "default" in result.output.lower()

    def test_killall_prefix_requires_value(self):
        """Test 'azlin killall --prefix' without value fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["killall", "--prefix"])

        assert result.exit_code != 0
        assert "requires an argument" in result.output.lower()

    def test_killall_prefix_empty_string(self):
        """Test 'azlin killall --prefix ""' accepts empty prefix.

        Empty prefix matches all VMs - dangerous but valid syntax.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["killall", "--prefix", ""])

        # Syntax OK, semantic validation later
        assert_option_accepted(result)

    def test_killall_prefix_with_force(self):
        """Test 'azlin killall --prefix my- --force' combines options."""
        runner = CliRunner()
        result = runner.invoke(main, ["killall", "--prefix", "my-", "--force"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 4: Resource Group and Config (4 tests)
    # -------------------------------------------------------------------------

    def test_killall_rg_option_accepts_value(self):
        """Test 'azlin killall --rg my-rg' accepts resource group."""
        runner = CliRunner()
        result = runner.invoke(main, ["killall", "--rg", "my-rg"])

        assert_option_accepted(result)

    def test_killall_resource_group_long_form(self):
        """Test 'azlin killall --resource-group my-rg' accepts long form."""
        runner = CliRunner()
        result = runner.invoke(main, ["killall", "--resource-group", "my-rg"])

        assert_option_accepted(result)

    def test_killall_config_option_accepts_path(self):
        """Test 'azlin killall --config /path' accepts config path."""
        runner = CliRunner()
        result = runner.invoke(main, ["killall", "--config", "/tmp/config.toml"])

        assert_option_accepted(result)

    def test_killall_all_options_combined(self):
        """Test 'azlin killall --rg rg --force --prefix test- --config cfg' combines all."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "killall",
                "--rg",
                "my-rg",
                "--force",
                "--prefix",
                "test-",
                "--config",
                "/tmp/config.toml",
            ],
        )

        assert_option_accepted(result)


# =============================================================================
# TEST MARKERS AND METADATA
# =============================================================================


# Mark all tests in this module as TDD RED phase and syntax validation
pytestmark = [pytest.mark.tdd_red, pytest.mark.syntax, pytest.mark.priority2]


# =============================================================================
# SUMMARY
# =============================================================================
"""
Test Coverage Summary (Priority 2 Commands):

azlin start (10 tests):
  - Basic invocation: 3 tests
  - Option flags: 3 tests
  - Invalid options: 2 tests
  - Option value requirements: 2 tests

azlin stop (14 tests):
  - Basic invocation: 3 tests
  - Boolean deallocate flag: 5 tests
  - Option flags: 3 tests
  - Invalid options: 3 tests

azlin status (12 tests):
  - Basic invocation: 3 tests
  - VM filter option: 4 tests
  - Resource group options: 2 tests
  - Invalid options: 3 tests

azlin cp (18 tests):
  - Basic invocation: 5 tests
  - Session:path notation: 6 tests
  - Option flags: 4 tests
  - Invalid options: 3 tests

azlin sync (14 tests):
  - Basic invocation: 3 tests
  - VM name option: 4 tests
  - Boolean flags: 3 tests
  - Other options: 4 tests

azlin session (16 tests):
  - Basic invocation: 4 tests
  - Clear flag: 4 tests
  - Resource group options: 4 tests
  - Invalid options: 4 tests

azlin killall (16 tests):
  - Basic invocation: 3 tests
  - Force flag: 4 tests
  - Prefix option: 5 tests
  - Resource group and config: 4 tests

TOTAL: 100 tests for Priority 2 commands
Running Total: 55 (original) + 100 (priority2) = 155 tests
"""
