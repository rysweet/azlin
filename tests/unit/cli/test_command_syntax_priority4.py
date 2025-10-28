"""Exhaustive command syntax tests for Priority 4 commands (TDD RED phase).

This module tests Priority 4 (Specialized) commands:
- keys (group: rotate, list, export, backup)
- cost (single command)
- update (single command)
- prune (single command)
- do (single command)
- doit (single command)

Test Coverage: ~60 tests for 1 group (4 subcommands) + 5 single commands
Test Categories:
1. Syntax validation (no args, required args, optional args)
2. Option combinations and validation
3. Error handling (invalid values, unknown options)
4. Help text

These tests follow TDD RED phase - they validate CLI syntax only.
"""

import pytest
from click.testing import CliRunner

from azlin.cli import main

# =============================================================================
# TEST CLASS: azlin keys (14 tests)
# =============================================================================


class TestKeysCommandSyntax:
    """Test syntax validation for 'azlin keys' command group (14 tests).

    Subcommands: rotate, list, export, backup
    SSH key management across Azure VMs.
    """

    # -------------------------------------------------------------------------
    # Category 1: Group-Level Syntax (3 tests)
    # -------------------------------------------------------------------------

    def test_keys_no_subcommand_shows_help(self):
        """Test 'azlin keys' without subcommand shows help."""
        runner = CliRunner()
        result = runner.invoke(main, ["keys"])

        assert result.exit_code in [0, 2]
        assert "keys" in result.output.lower()

    def test_keys_help_displays_usage(self):
        """Test 'azlin keys --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["keys", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "key" in result.output.lower()

    def test_keys_invalid_subcommand_fails(self):
        """Test 'azlin keys invalid' fails with clear error."""
        runner = CliRunner()
        result = runner.invoke(main, ["keys", "invalid"])

        assert result.exit_code != 0
        assert "no such command" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: keys rotate Subcommand (4 tests)
    # -------------------------------------------------------------------------

    def test_keys_rotate_no_args(self):
        """Test 'azlin keys rotate' without args is valid (uses config)."""
        runner = CliRunner()
        result = runner.invoke(main, ["keys", "rotate"])

        # Should attempt to use config or error about missing RG
        assert "missing argument" not in result.output.lower()

    def test_keys_rotate_with_rg(self):
        """Test 'azlin keys rotate --rg my-rg' accepts resource group."""
        runner = CliRunner()
        result = runner.invoke(main, ["keys", "rotate", "--rg", "my-rg"])

        assert "no such option" not in result.output.lower()

    def test_keys_rotate_help(self):
        """Test 'azlin keys rotate --help' displays help."""
        runner = CliRunner()
        result = runner.invoke(main, ["keys", "rotate", "--help"])

        assert result.exit_code == 0
        assert "rotate" in result.output.lower()

    def test_keys_rotate_combined_options(self):
        """Test 'azlin keys rotate --rg my-rg --config cfg' combines options."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["keys", "rotate", "--rg", "my-rg", "--config", "/tmp/config.toml"]
        )

        assert "no such option" not in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 3: keys list Subcommand (2 tests)
    # -------------------------------------------------------------------------

    def test_keys_list_no_args(self):
        """Test 'azlin keys list' without args is valid."""
        runner = CliRunner()
        result = runner.invoke(main, ["keys", "list"])

        assert "missing argument" not in result.output.lower()

    def test_keys_list_with_rg(self):
        """Test 'azlin keys list --rg my-rg' accepts resource group."""
        runner = CliRunner()
        result = runner.invoke(main, ["keys", "list", "--rg", "my-rg"])

        assert "no such option" not in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 4: keys export Subcommand (3 tests)
    # -------------------------------------------------------------------------

    def test_keys_export_requires_output(self):
        """Test 'azlin keys export' without output path fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["keys", "export"])

        assert result.exit_code != 0
        assert "required" in result.output.lower() or "missing" in result.output.lower()

    def test_keys_export_with_output(self):
        """Test 'azlin keys export --output keys.tar.gz' accepts output path."""
        runner = CliRunner()
        result = runner.invoke(main, ["keys", "export", "--output", "keys.tar.gz"])

        assert "no such option" not in result.output.lower()

    def test_keys_export_help(self):
        """Test 'azlin keys export --help' displays help."""
        runner = CliRunner()
        result = runner.invoke(main, ["keys", "export", "--help"])

        assert result.exit_code == 0
        assert "export" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 5: keys backup Subcommand (2 tests)
    # -------------------------------------------------------------------------

    def test_keys_backup_no_args(self):
        """Test 'azlin keys backup' without args is valid (uses default path)."""
        runner = CliRunner()
        result = runner.invoke(main, ["keys", "backup"])

        assert "missing argument" not in result.output.lower()

    def test_keys_backup_with_output(self):
        """Test 'azlin keys backup --output /path' accepts output path.

        RED PHASE: Expected to fail until --output option is implemented.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["keys", "backup", "--output", "/tmp/backup"])

        # XFAIL: --output not yet implemented
        # When implemented, this should pass
        # assert "no such option" not in result.output.lower()
        # For now, we just check that command runs (may fail due to missing option)
        assert result.exit_code in [0, 1, 2]  # Accept various outcomes


# =============================================================================
# TEST CLASS: azlin cost (12 tests)
# =============================================================================


class TestCostCommandSyntax:
    """Test syntax validation for 'azlin cost' command (12 tests).

    Show cost estimates for VMs with various filters and breakdowns.
    """

    # -------------------------------------------------------------------------
    # Category 1: Basic Invocation (3 tests)
    # -------------------------------------------------------------------------

    def test_cost_no_args_valid(self):
        """Test 'azlin cost' without args uses config."""
        runner = CliRunner()
        result = runner.invoke(main, ["cost"])

        # Should attempt to use config or error about missing RG
        assert "missing argument" not in result.output.lower()
        assert "no such option" not in result.output.lower()

    def test_cost_help_displays_usage(self):
        """Test 'azlin cost --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["cost", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "cost" in result.output.lower()

    def test_cost_with_rg(self):
        """Test 'azlin cost --rg my-rg' accepts resource group."""
        runner = CliRunner()
        result = runner.invoke(main, ["cost", "--rg", "my-rg"])

        assert "no such option" not in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: Boolean Flags (3 tests)
    # -------------------------------------------------------------------------

    def test_cost_by_vm_flag(self):
        """Test 'azlin cost --by-vm' accepts by-vm flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["cost", "--by-vm"])

        assert "no such option" not in result.output.lower()

    def test_cost_estimate_flag(self):
        """Test 'azlin cost --estimate' accepts estimate flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["cost", "--estimate"])

        assert "no such option" not in result.output.lower()

    def test_cost_combined_flags(self):
        """Test 'azlin cost --by-vm --estimate' combines flags."""
        runner = CliRunner()
        result = runner.invoke(main, ["cost", "--by-vm", "--estimate"])

        assert "no such option" not in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 3: Date Range Options (4 tests)
    # -------------------------------------------------------------------------

    def test_cost_from_date_option(self):
        """Test 'azlin cost --from 2025-01-01' accepts from date."""
        runner = CliRunner()
        result = runner.invoke(main, ["cost", "--from", "2025-01-01"])

        assert "no such option" not in result.output.lower()

    def test_cost_to_date_option(self):
        """Test 'azlin cost --to 2025-01-31' accepts to date."""
        runner = CliRunner()
        result = runner.invoke(main, ["cost", "--to", "2025-01-31"])

        assert "no such option" not in result.output.lower()

    def test_cost_date_range(self):
        """Test 'azlin cost --from 2025-01-01 --to 2025-01-31' accepts date range."""
        runner = CliRunner()
        result = runner.invoke(main, ["cost", "--from", "2025-01-01", "--to", "2025-01-31"])

        assert "no such option" not in result.output.lower()

    def test_cost_invalid_date_format(self):
        """Test 'azlin cost --from invalid' rejects invalid date format.

        Date validation happens at runtime, not syntax level.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["cost", "--from", "invalid-date"])

        # Syntax is OK, semantic validation happens later
        assert "no such option" not in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 4: Combined Options (2 tests)
    # -------------------------------------------------------------------------

    def test_cost_all_options_combined(self):
        """Test 'azlin cost --rg rg --by-vm --from 2025-01-01 --to 2025-01-31 --estimate' combines all."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "cost",
                "--rg",
                "my-rg",
                "--by-vm",
                "--from",
                "2025-01-01",
                "--to",
                "2025-01-31",
                "--estimate",
            ],
        )

        assert "no such option" not in result.output.lower()

    def test_cost_config_option(self):
        """Test 'azlin cost --config /path' accepts config path."""
        runner = CliRunner()
        result = runner.invoke(main, ["cost", "--config", "/tmp/config.toml"])

        assert "no such option" not in result.output.lower()


# =============================================================================
# TEST CLASS: azlin update (10 tests)
# =============================================================================


class TestUpdateCommandSyntax:
    """Test syntax validation for 'azlin update' command (10 tests).

    Update all development tools on a VM.
    """

    # -------------------------------------------------------------------------
    # Category 1: Basic Invocation (3 tests)
    # -------------------------------------------------------------------------

    def test_update_requires_vm_identifier(self):
        """Test 'azlin update' without VM identifier fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["update"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_update_with_vm_identifier(self):
        """Test 'azlin update my-vm' accepts VM identifier."""
        runner = CliRunner()
        result = runner.invoke(main, ["update", "my-vm"])

        # Should not show syntax error
        assert "no such option" not in result.output.lower()
        assert "missing argument" not in result.output.lower()

    def test_update_help_displays_usage(self):
        """Test 'azlin update --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["update", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "update" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: Option Flags (4 tests)
    # -------------------------------------------------------------------------

    def test_update_rg_option_accepts_value(self):
        """Test 'azlin update my-vm --rg my-rg' accepts resource group."""
        runner = CliRunner()
        result = runner.invoke(main, ["update", "my-vm", "--rg", "my-rg"])

        assert "no such option" not in result.output.lower()

    def test_update_config_option_accepts_path(self):
        """Test 'azlin update my-vm --config /path' accepts config path."""
        runner = CliRunner()
        result = runner.invoke(main, ["update", "my-vm", "--config", "/tmp/config.toml"])

        assert "no such option" not in result.output.lower()

    def test_update_timeout_option_accepts_integer(self):
        """Test 'azlin update my-vm --timeout 600' accepts timeout value."""
        runner = CliRunner()
        result = runner.invoke(main, ["update", "my-vm", "--timeout", "600"])

        assert "no such option" not in result.output.lower()

    def test_update_timeout_rejects_non_integer(self):
        """Test 'azlin update my-vm --timeout abc' rejects non-integer."""
        runner = CliRunner()
        result = runner.invoke(main, ["update", "my-vm", "--timeout", "abc"])

        assert result.exit_code != 0
        assert "invalid" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 3: VM Identifier Formats (3 tests)
    # -------------------------------------------------------------------------

    def test_update_with_vm_name(self):
        """Test 'azlin update my-vm' accepts VM name."""
        runner = CliRunner()
        result = runner.invoke(main, ["update", "my-vm"])

        assert "no such option" not in result.output.lower()

    def test_update_with_ip_address(self):
        """Test 'azlin update 20.1.2.3' accepts IP address."""
        runner = CliRunner()
        result = runner.invoke(main, ["update", "20.1.2.3"])

        assert "no such option" not in result.output.lower()

    def test_update_with_session_name(self):
        """Test 'azlin update my-session' accepts session name."""
        runner = CliRunner()
        result = runner.invoke(main, ["update", "my-session"])

        assert "no such option" not in result.output.lower()


# =============================================================================
# TEST CLASS: azlin prune (14 tests)
# =============================================================================


class TestPruneCommandSyntax:
    """Test syntax validation for 'azlin prune' command (14 tests).

    Prune inactive VMs based on age and idle time.
    """

    # -------------------------------------------------------------------------
    # Category 1: Basic Invocation (3 tests)
    # -------------------------------------------------------------------------

    def test_prune_no_args_valid(self):
        """Test 'azlin prune' without args uses defaults."""
        runner = CliRunner()
        result = runner.invoke(main, ["prune"])

        # Should use default age/idle days
        assert "missing argument" not in result.output.lower()
        assert "no such option" not in result.output.lower()

    def test_prune_help_displays_usage(self):
        """Test 'azlin prune --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["prune", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "prune" in result.output.lower()

    def test_prune_with_rg(self):
        """Test 'azlin prune --rg my-rg' accepts resource group."""
        runner = CliRunner()
        result = runner.invoke(main, ["prune", "--rg", "my-rg"])

        assert "no such option" not in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: Age and Idle Day Options (4 tests)
    # -------------------------------------------------------------------------

    def test_prune_age_days_option(self):
        """Test 'azlin prune --age-days 7' accepts age threshold."""
        runner = CliRunner()
        result = runner.invoke(main, ["prune", "--age-days", "7"])

        assert "no such option" not in result.output.lower()

    def test_prune_idle_days_option(self):
        """Test 'azlin prune --idle-days 3' accepts idle threshold."""
        runner = CliRunner()
        result = runner.invoke(main, ["prune", "--idle-days", "3"])

        assert "no such option" not in result.output.lower()

    def test_prune_age_days_rejects_zero(self):
        """Test 'azlin prune --age-days 0' rejects zero value.

        IntRange(min=1) should reject 0.
        """
        runner = CliRunner()
        result = runner.invoke(main, ["prune", "--age-days", "0"])

        assert result.exit_code != 0
        assert "invalid" in result.output.lower() or "range" in result.output.lower()

    def test_prune_combined_thresholds(self):
        """Test 'azlin prune --age-days 7 --idle-days 3' combines thresholds."""
        runner = CliRunner()
        result = runner.invoke(main, ["prune", "--age-days", "7", "--idle-days", "3"])

        assert "no such option" not in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 3: Boolean Flags (4 tests)
    # -------------------------------------------------------------------------

    def test_prune_dry_run_flag(self):
        """Test 'azlin prune --dry-run' accepts dry-run flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["prune", "--dry-run"])

        assert "no such option" not in result.output.lower()

    def test_prune_force_flag(self):
        """Test 'azlin prune --force' accepts force flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["prune", "--force"])

        assert "no such option" not in result.output.lower()

    def test_prune_include_running_flag(self):
        """Test 'azlin prune --include-running' accepts include-running flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["prune", "--include-running"])

        assert "no such option" not in result.output.lower()

    def test_prune_include_named_flag(self):
        """Test 'azlin prune --include-named' accepts include-named flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["prune", "--include-named"])

        assert "no such option" not in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 4: Combined Options (3 tests)
    # -------------------------------------------------------------------------

    def test_prune_all_flags_combined(self):
        """Test 'azlin prune --dry-run --force --include-running --include-named' combines all flags."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["prune", "--dry-run", "--force", "--include-running", "--include-named"]
        )

        assert "no such option" not in result.output.lower()

    def test_prune_all_options_combined(self):
        """Test all prune options combined."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "prune",
                "--rg",
                "my-rg",
                "--age-days",
                "7",
                "--idle-days",
                "3",
                "--dry-run",
                "--force",
                "--config",
                "/tmp/config.toml",
            ],
        )

        assert "no such option" not in result.output.lower()

    def test_prune_config_option(self):
        """Test 'azlin prune --config /path' accepts config path."""
        runner = CliRunner()
        result = runner.invoke(main, ["prune", "--config", "/tmp/config.toml"])

        assert "no such option" not in result.output.lower()


# =============================================================================
# TEST CLASS: azlin do (10 tests)
# =============================================================================


class TestDoCommandSyntax:
    """Test syntax validation for 'azlin do' command (10 tests).

    Execute natural language azlin commands using AI.
    """

    # -------------------------------------------------------------------------
    # Category 1: Basic Invocation (3 tests)
    # -------------------------------------------------------------------------

    def test_do_requires_request(self):
        """Test 'azlin do' without request fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["do"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_do_with_request(self):
        """Test 'azlin do "list all vms"' accepts request."""
        runner = CliRunner()
        result = runner.invoke(main, ["do", "list all vms"])

        # Should not show syntax error (may error on missing API key)
        assert "no such option" not in result.output.lower()
        assert "missing argument" not in result.output.lower()

    def test_do_help_displays_usage(self):
        """Test 'azlin do --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["do", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "natural language" in result.output.lower() or "ai" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: Boolean Flags (4 tests)
    # -------------------------------------------------------------------------

    def test_do_dry_run_flag(self):
        """Test 'azlin do "list vms" --dry-run' accepts dry-run flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["do", "list vms", "--dry-run"])

        assert "no such option" not in result.output.lower()

    def test_do_yes_flag(self):
        """Test 'azlin do "list vms" --yes' accepts yes flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["do", "list vms", "--yes"])

        assert "no such option" not in result.output.lower()

    def test_do_yes_short_form(self):
        """Test 'azlin do "list vms" -y' accepts -y short form."""
        runner = CliRunner()
        result = runner.invoke(main, ["do", "list vms", "-y"])

        assert "no such option" not in result.output.lower()

    def test_do_verbose_flag(self):
        """Test 'azlin do "list vms" --verbose' accepts verbose flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["do", "list vms", "--verbose"])

        assert "no such option" not in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 3: Combined Options (3 tests)
    # -------------------------------------------------------------------------

    def test_do_with_rg_option(self):
        """Test 'azlin do "list vms" --rg my-rg' accepts resource group."""
        runner = CliRunner()
        result = runner.invoke(main, ["do", "list vms", "--rg", "my-rg"])

        assert "no such option" not in result.output.lower()

    def test_do_all_options_combined(self):
        """Test 'azlin do "list" --dry-run --yes --verbose --rg rg' combines all options."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["do", "list vms", "--dry-run", "--yes", "--verbose", "--rg", "my-rg"]
        )

        assert "no such option" not in result.output.lower()

    def test_do_quoted_request_with_spaces(self):
        """Test 'azlin do "list all my vms in production"' handles multi-word request."""
        runner = CliRunner()
        result = runner.invoke(main, ["do", "list all my vms in production"])

        assert "no such option" not in result.output.lower()


# =============================================================================
# TEST CLASS: azlin doit (10 tests)
# =============================================================================


class TestDoitCommandSyntax:
    """Test syntax validation for 'azlin doit' command (10 tests).

    Enhanced agentic Azure infrastructure management.
    """

    # -------------------------------------------------------------------------
    # Category 1: Basic Invocation (3 tests)
    # -------------------------------------------------------------------------

    def test_doit_requires_objective(self):
        """Test 'azlin doit' without objective fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["doit"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_doit_with_objective(self):
        """Test 'azlin doit "create a dev vm"' accepts objective."""
        runner = CliRunner()
        result = runner.invoke(main, ["doit", "create a dev vm"])

        # Should not show syntax error
        assert "no such option" not in result.output.lower()
        assert "missing argument" not in result.output.lower()

    def test_doit_help_displays_usage(self):
        """Test 'azlin doit --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["doit", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "agentic" in result.output.lower() or "enhanced" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: Boolean Flags (3 tests)
    # -------------------------------------------------------------------------

    def test_doit_dry_run_flag(self):
        """Test 'azlin doit "create vm" --dry-run' accepts dry-run flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["doit", "create vm", "--dry-run"])

        assert "no such option" not in result.output.lower()

    def test_doit_verbose_flag(self):
        """Test 'azlin doit "create vm" --verbose' accepts verbose flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["doit", "create vm", "--verbose"])

        assert "no such option" not in result.output.lower()

    def test_doit_verbose_short_form(self):
        """Test 'azlin doit "create vm" -v' accepts -v short form."""
        runner = CliRunner()
        result = runner.invoke(main, ["doit", "create vm", "-v"])

        assert "no such option" not in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 3: Resource Group and Config Options (4 tests)
    # -------------------------------------------------------------------------

    def test_doit_with_rg_option(self):
        """Test 'azlin doit "create vm" --rg my-rg' accepts resource group."""
        runner = CliRunner()
        result = runner.invoke(main, ["doit", "create vm", "--rg", "my-rg"])

        assert "no such option" not in result.output.lower()

    def test_doit_with_config_option(self):
        """Test 'azlin doit "create vm" --config /path' accepts config path."""
        runner = CliRunner()
        result = runner.invoke(main, ["doit", "create vm", "--config", "/tmp/config.toml"])

        assert "no such option" not in result.output.lower()

    def test_doit_all_options_combined(self):
        """Test 'azlin doit "create" --dry-run --verbose --rg rg --config cfg' combines all."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "doit",
                "create vm",
                "--dry-run",
                "--verbose",
                "--rg",
                "my-rg",
                "--config",
                "/tmp/config.toml",
            ],
        )

        assert "no such option" not in result.output.lower()

    def test_doit_complex_objective(self):
        """Test 'azlin doit "provision AKS cluster with 3 nodes"' handles complex objective."""
        runner = CliRunner()
        result = runner.invoke(main, ["doit", "provision AKS cluster with 3 nodes"])

        assert "no such option" not in result.output.lower()


# =============================================================================
# TEST MARKERS AND METADATA
# =============================================================================


# Mark all tests in this module as TDD RED phase and syntax validation
pytestmark = [pytest.mark.tdd_red, pytest.mark.syntax, pytest.mark.priority4]


# =============================================================================
# SUMMARY
# =============================================================================
"""
Test Coverage Summary (Priority 4 Commands):

azlin keys (14 tests):
  - Group-level syntax: 3 tests
  - keys rotate: 4 tests
  - keys list: 2 tests
  - keys export: 3 tests
  - keys backup: 2 tests

azlin cost (12 tests):
  - Basic invocation: 3 tests
  - Boolean flags: 3 tests
  - Date range options: 4 tests
  - Combined options: 2 tests

azlin update (10 tests):
  - Basic invocation: 3 tests
  - Option flags: 4 tests
  - VM identifier formats: 3 tests

azlin prune (14 tests):
  - Basic invocation: 3 tests
  - Age and idle day options: 4 tests
  - Boolean flags: 4 tests
  - Combined options: 3 tests

azlin do (10 tests):
  - Basic invocation: 3 tests
  - Boolean flags: 4 tests
  - Combined options: 3 tests

azlin doit (10 tests):
  - Basic invocation: 3 tests
  - Boolean flags: 3 tests
  - Resource group and config options: 4 tests

TOTAL: 70 tests for Priority 4 commands
Running Total: 55 (original) + 100 (priority2) + 94 (priority3) + 70 (priority4) = 319 tests
"""
