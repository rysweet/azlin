"""Exhaustive command syntax tests for Priority 3 commands (TDD RED phase).

This module tests Priority 3 (Advanced) commands - command groups:
- batch (stop, start, command, sync)
- env (set, list, delete, export, import, clear)
- storage (create, list, status, delete, mount, unmount)
- snapshot (enable, disable, sync, status, create, list, restore, delete)
- template (create, list, delete, export, import)

Test Coverage: ~90 tests for 5 command groups (25 subcommands)
Test Categories:
1. Group-level syntax (help, no subcommand)
2. Subcommand invocation (required args, optional args)
3. Option combinations and validation
4. Error handling (invalid values, unknown options)

These tests follow TDD RED phase - they validate CLI syntax only.
"""

import pytest
from click.testing import CliRunner

from azlin.cli import main
from tests.conftest import (
    assert_command_fails,
    assert_command_succeeds,
    assert_invalid_value_error,
    assert_missing_argument_error,
    assert_option_accepted,
    assert_option_rejected,
    assert_unexpected_argument_error,
)

# =============================================================================
# TEST CLASS: azlin batch (18 tests)
# =============================================================================


class TestBatchCommandSyntax:
    """Test syntax validation for 'azlin batch' command group (18 tests).

    Subcommands: stop, start, command, sync
    Common options: --tag, --vm-pattern, --all, --rg, --config
    """

    # -------------------------------------------------------------------------
    # Category 1: Group-Level Syntax (3 tests)
    # -------------------------------------------------------------------------

    def test_batch_no_subcommand_shows_help(self):
        """Test 'azlin batch' without subcommand shows help."""
        runner = CliRunner()
        result = runner.invoke(main, ["batch"])

        # Should show help or list subcommands
        assert result.exit_code in [0, 2]
        assert "batch" in result.output.lower()

    def test_batch_help_displays_usage(self):
        """Test 'azlin batch --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "batch" in result.output.lower()

    def test_batch_invalid_subcommand_fails(self):
        """Test 'azlin batch invalid' fails with clear error."""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "invalid"])

        assert result.exit_code != 0
        assert "no such command" in result.output.lower() or "invalid" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: batch stop Subcommand (5 tests)
    # -------------------------------------------------------------------------

    def test_batch_stop_help(self):
        """Test 'azlin batch stop --help' displays help."""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "stop", "--help"])

        assert result.exit_code == 0
        assert "stop" in result.output.lower()

    def test_batch_stop_with_tag(self):
        """Test 'azlin batch stop --tag env=dev' accepts tag filter."""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "stop", "--tag", "env=dev"])

        assert_option_accepted(result)

    def test_batch_stop_with_pattern(self):
        """Test 'azlin batch stop --vm-pattern test-*' accepts pattern."""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "stop", "--vm-pattern", "test-*"])

        assert_option_accepted(result)

    def test_batch_stop_with_all_flag(self):
        """Test 'azlin batch stop --all' accepts all flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "stop", "--all"])

        assert_option_accepted(result)

    def test_batch_stop_deallocate_flags(self):
        """Test 'azlin batch stop --no-deallocate' accepts deallocate flags."""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "stop", "--no-deallocate"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 3: batch start Subcommand (3 tests)
    # -------------------------------------------------------------------------

    def test_batch_start_help(self):
        """Test 'azlin batch start --help' displays help."""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "start", "--help"])

        assert result.exit_code == 0
        assert "start" in result.output.lower()

    def test_batch_start_with_tag(self):
        """Test 'azlin batch start --tag env=dev' accepts tag filter."""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "start", "--tag", "env=dev"])

        assert_option_accepted(result)

    def test_batch_start_combined_options(self):
        """Test 'azlin batch start --tag env=dev --rg my-rg' combines options."""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "start", "--tag", "env=dev", "--rg", "my-rg"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 4: batch command Subcommand (4 tests)
    # -------------------------------------------------------------------------

    def test_batch_command_requires_command_arg(self):
        """Test 'azlin batch command' without command fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "command"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_batch_command_with_command_arg(self):
        """Test 'azlin batch command git pull' accepts command."""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "command", "git pull"])

        assert_option_accepted(result)

    def test_batch_command_help(self):
        """Test 'azlin batch command --help' displays help."""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "command", "--help"])

        assert result.exit_code == 0
        assert "command" in result.output.lower()

    def test_batch_command_with_filters(self):
        """Test 'azlin batch command ls --tag env=dev' combines command and filter."""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "command", "ls", "--tag", "env=dev"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 5: batch sync Subcommand (3 tests)
    # -------------------------------------------------------------------------

    def test_batch_sync_help(self):
        """Test 'azlin batch sync --help' displays help."""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "sync", "--help"])

        assert result.exit_code == 0
        assert "sync" in result.output.lower()

    def test_batch_sync_with_tag(self):
        """Test 'azlin batch sync --tag env=dev' accepts tag filter."""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "sync", "--tag", "env=dev"])

        assert_option_accepted(result)

    def test_batch_sync_combined_options(self):
        """Test 'azlin batch sync --tag env=dev --rg my-rg' combines options."""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "sync", "--tag", "env=dev", "--rg", "my-rg"])

        assert_option_accepted(result)


# =============================================================================
# TEST CLASS: azlin env (18 tests)
# =============================================================================


class TestEnvCommandSyntax:
    """Test syntax validation for 'azlin env' command group (18 tests).

    Subcommands: set, list, delete, export, import, clear
    All subcommands require vm_identifier as first argument.
    """

    # -------------------------------------------------------------------------
    # Category 1: Group-Level Syntax (3 tests)
    # -------------------------------------------------------------------------

    def test_env_no_subcommand_shows_help(self):
        """Test 'azlin env' without subcommand shows help."""
        runner = CliRunner()
        result = runner.invoke(main, ["env"])

        assert result.exit_code in [0, 2]
        assert "env" in result.output.lower()

    def test_env_help_displays_usage(self):
        """Test 'azlin env --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["env", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "environment" in result.output.lower()

    def test_env_invalid_subcommand_fails(self):
        """Test 'azlin env invalid' fails with clear error."""
        runner = CliRunner()
        result = runner.invoke(main, ["env", "invalid"])

        assert result.exit_code != 0
        assert "no such command" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: env set Subcommand (5 tests)
    # -------------------------------------------------------------------------

    def test_env_set_requires_vm_identifier(self):
        """Test 'azlin env set' without VM identifier fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["env", "set"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_env_set_requires_env_var(self):
        """Test 'azlin env set my-vm' without env var fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["env", "set", "my-vm"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_env_set_with_key_value(self):
        """Test 'azlin env set my-vm KEY=value' accepts key=value format."""
        runner = CliRunner()
        result = runner.invoke(main, ["env", "set", "my-vm", "KEY=value"])

        assert_option_accepted(result)

    def test_env_set_force_flag(self):
        """Test 'azlin env set my-vm KEY=secret --force' accepts force flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["env", "set", "my-vm", "KEY=secret", "--force"])

        assert_option_accepted(result)

    def test_env_set_help(self):
        """Test 'azlin env set --help' displays help."""
        runner = CliRunner()
        result = runner.invoke(main, ["env", "set", "--help"])

        assert result.exit_code == 0
        assert "set" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 3: env list Subcommand (3 tests)
    # -------------------------------------------------------------------------

    def test_env_list_requires_vm_identifier(self):
        """Test 'azlin env list' without VM identifier fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["env", "list"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_env_list_with_vm_identifier(self):
        """Test 'azlin env list my-vm' accepts VM identifier."""
        runner = CliRunner()
        result = runner.invoke(main, ["env", "list", "my-vm"])

        assert_option_accepted(result)

    def test_env_list_show_values_flag(self):
        """Test 'azlin env list my-vm --show-values' accepts show-values flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["env", "list", "my-vm", "--show-values"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 4: env delete Subcommand (2 tests)
    # -------------------------------------------------------------------------

    def test_env_delete_requires_vm_and_key(self):
        """Test 'azlin env delete my-vm' without key fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["env", "delete", "my-vm"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_env_delete_with_vm_and_key(self):
        """Test 'azlin env delete my-vm MY_KEY' accepts both args."""
        runner = CliRunner()
        result = runner.invoke(main, ["env", "delete", "my-vm", "MY_KEY"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 5: env export/import/clear Subcommands (5 tests)
    # -------------------------------------------------------------------------

    def test_env_export_requires_vm_and_output(self):
        """Test 'azlin env export my-vm' without output path fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["env", "export", "my-vm"])

        assert result.exit_code != 0
        # Error could be missing argument, missing VM, or missing resource group
        assert (
            "missing argument" in result.output.lower()
            or "required" in result.output.lower()
            or "not found" in result.output.lower()
        )

    def test_env_export_with_vm_and_output(self):
        """Test 'azlin env export my-vm prod.env' accepts both args."""
        runner = CliRunner()
        result = runner.invoke(main, ["env", "export", "my-vm", "prod.env"])

        assert_option_accepted(result)

    def test_env_import_requires_vm_and_file(self):
        """Test 'azlin env import my-vm' without file fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["env", "import", "my-vm"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_env_import_with_vm_and_file(self):
        """Test 'azlin env import my-vm prod.env' accepts both args."""
        runner = CliRunner()
        result = runner.invoke(main, ["env", "import", "my-vm", "prod.env"])

        # May fail on file existence check, but syntax is OK
        assert_option_accepted(result)

    def test_env_clear_with_vm_identifier(self):
        """Test 'azlin env clear my-vm' accepts VM identifier."""
        runner = CliRunner()
        result = runner.invoke(main, ["env", "clear", "my-vm"])

        assert_option_accepted(result)


# =============================================================================
# TEST CLASS: azlin storage (20 tests)
# =============================================================================


class TestStorageCommandSyntax:
    """Test syntax validation for 'azlin storage' command group (20 tests).

    Subcommands: create, list, status, delete, mount, unmount
    """

    # -------------------------------------------------------------------------
    # Category 1: Group-Level Syntax (3 tests)
    # -------------------------------------------------------------------------

    def test_storage_no_subcommand_shows_help(self):
        """Test 'azlin storage' without subcommand shows help."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage"])

        assert result.exit_code in [0, 2]
        assert "storage" in result.output.lower()

    def test_storage_help_displays_usage(self):
        """Test 'azlin storage --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "storage" in result.output.lower()

    def test_storage_invalid_subcommand_fails(self):
        """Test 'azlin storage invalid' fails with clear error."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "invalid"])

        assert result.exit_code != 0
        assert "no such command" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: storage create Subcommand (6 tests)
    # -------------------------------------------------------------------------

    def test_storage_create_requires_name(self):
        """Test 'azlin storage create' without name fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "create"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_storage_create_with_name(self):
        """Test 'azlin storage create mystore' accepts name."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "create", "mystore"])

        assert_option_accepted(result)

    def test_storage_create_size_option(self):
        """Test 'azlin storage create mystore --size 100' accepts size."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "create", "mystore", "--size", "100"])

        assert_option_accepted(result)

    def test_storage_create_tier_option(self):
        """Test 'azlin storage create mystore --tier Premium' accepts tier."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "create", "mystore", "--tier", "Premium"])

        assert_option_accepted(result)

    def test_storage_create_tier_choice_validation(self):
        """Test 'azlin storage create mystore --tier Invalid' rejects invalid tier."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "create", "mystore", "--tier", "Invalid"])

        assert result.exit_code != 0
        assert (
            "invalid choice" in result.output.lower()
            or "invalid value" in result.output.lower()
            or "choice" in result.output.lower()
        )

    def test_storage_create_help(self):
        """Test 'azlin storage create --help' displays help."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "create", "--help"])

        assert result.exit_code == 0
        assert "create" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 3: storage list Subcommand (2 tests)
    # -------------------------------------------------------------------------

    def test_storage_list_no_args(self):
        """Test 'azlin storage list' without args is valid."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "list"])

        assert "missing argument" not in result.output.lower()

    def test_storage_list_with_rg(self):
        """Test 'azlin storage list --rg my-rg' accepts resource group."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "list", "--rg", "my-rg"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 4: storage status Subcommand (2 tests)
    # -------------------------------------------------------------------------

    def test_storage_status_requires_name(self):
        """Test 'azlin storage status' without name fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "status"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_storage_status_with_name(self):
        """Test 'azlin storage status mystore' accepts name."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "status", "mystore"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 5: storage delete Subcommand (2 tests)
    # -------------------------------------------------------------------------

    def test_storage_delete_requires_name(self):
        """Test 'azlin storage delete' without name fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "delete"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_storage_delete_with_name(self):
        """Test 'azlin storage delete mystore' accepts name."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "delete", "mystore"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 6: storage mount Subcommand (3 tests)
    # -------------------------------------------------------------------------

    def test_storage_mount_requires_name(self):
        """Test 'azlin storage mount' without storage name fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "mount"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_storage_mount_requires_vm_option(self):
        """Test 'azlin storage mount mystore' without --vm fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "mount", "mystore"])

        # Should require --vm option
        assert result.exit_code != 0

    def test_storage_mount_with_name_and_vm(self):
        """Test 'azlin storage mount mystore --vm my-vm' accepts both."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "mount", "mystore", "--vm", "my-vm"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 7: storage unmount Subcommand (2 tests)
    # -------------------------------------------------------------------------

    def test_storage_unmount_requires_vm_option(self):
        """Test 'azlin storage unmount' without --vm fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "unmount"])

        assert result.exit_code != 0
        # Should require --vm option
        assert "required" in result.output.lower() or "missing" in result.output.lower()

    def test_storage_unmount_with_vm(self):
        """Test 'azlin storage unmount --vm my-vm' accepts VM option."""
        runner = CliRunner()
        result = runner.invoke(main, ["storage", "unmount", "--vm", "my-vm"])

        assert_option_accepted(result)


# =============================================================================
# TEST CLASS: azlin snapshot (22 tests)
# =============================================================================


class TestSnapshotCommandSyntax:
    """Test syntax validation for 'azlin snapshot' command group (22 tests).

    Subcommands: enable, disable, sync, status, create, list, restore, delete
    """

    # -------------------------------------------------------------------------
    # Category 1: Group-Level Syntax (3 tests)
    # -------------------------------------------------------------------------

    def test_snapshot_no_subcommand_shows_help(self):
        """Test 'azlin snapshot' without subcommand shows help."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot"])

        assert result.exit_code in [0, 2]
        assert "snapshot" in result.output.lower()

    def test_snapshot_help_displays_usage(self):
        """Test 'azlin snapshot --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "snapshot" in result.output.lower()

    def test_snapshot_invalid_subcommand_fails(self):
        """Test 'azlin snapshot invalid' fails with clear error."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "invalid"])

        assert result.exit_code != 0
        assert "no such command" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: snapshot enable Subcommand (5 tests)
    # -------------------------------------------------------------------------

    def test_snapshot_enable_requires_vm_name(self):
        """Test 'azlin snapshot enable' without VM name fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "enable"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_snapshot_enable_requires_every_option(self):
        """Test 'azlin snapshot enable my-vm' without --every fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "enable", "my-vm"])

        assert result.exit_code != 0
        assert "required" in result.output.lower() or "missing" in result.output.lower()

    def test_snapshot_enable_with_vm_and_interval(self):
        """Test 'azlin snapshot enable my-vm --every 24' accepts interval."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "enable", "my-vm", "--every", "24"])

        assert_option_accepted(result)

    def test_snapshot_enable_keep_option(self):
        """Test 'azlin snapshot enable my-vm --every 24 --keep 5' accepts keep count."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["snapshot", "enable", "my-vm", "--every", "24", "--keep", "5"]
        )

        assert_option_accepted(result)

    def test_snapshot_enable_help(self):
        """Test 'azlin snapshot enable --help' displays help."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "enable", "--help"])

        assert result.exit_code == 0
        assert "enable" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 3: snapshot disable Subcommand (2 tests)
    # -------------------------------------------------------------------------

    def test_snapshot_disable_requires_vm_name(self):
        """Test 'azlin snapshot disable' without VM name fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "disable"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_snapshot_disable_with_vm_name(self):
        """Test 'azlin snapshot disable my-vm' accepts VM name."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "disable", "my-vm"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 4: snapshot sync Subcommand (3 tests)
    # -------------------------------------------------------------------------

    def test_snapshot_sync_no_args(self):
        """Test 'azlin snapshot sync' without args is valid (syncs all)."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "sync"])

        assert "missing argument" not in result.output.lower()

    def test_snapshot_sync_with_vm_option(self):
        """Test 'azlin snapshot sync --vm my-vm' accepts VM filter."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "sync", "--vm", "my-vm"])

        assert_option_accepted(result)

    def test_snapshot_sync_help(self):
        """Test 'azlin snapshot sync --help' displays help."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "sync", "--help"])

        assert result.exit_code == 0
        assert "sync" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 5: snapshot status Subcommand (2 tests)
    # -------------------------------------------------------------------------

    def test_snapshot_status_requires_vm_name(self):
        """Test 'azlin snapshot status' without VM name fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "status"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_snapshot_status_with_vm_name(self):
        """Test 'azlin snapshot status my-vm' accepts VM name."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "status", "my-vm"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 6: snapshot create/list/restore/delete Subcommands (7 tests)
    # -------------------------------------------------------------------------

    def test_snapshot_create_requires_vm_name(self):
        """Test 'azlin snapshot create' without VM name fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "create"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_snapshot_create_with_vm_name(self):
        """Test 'azlin snapshot create my-vm' accepts VM name."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "create", "my-vm"])

        assert_option_accepted(result)

    def test_snapshot_list_requires_vm_name(self):
        """Test 'azlin snapshot list' without VM name fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "list"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_snapshot_list_with_vm_name(self):
        """Test 'azlin snapshot list my-vm' accepts VM name."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "list", "my-vm"])

        assert_option_accepted(result)

    def test_snapshot_restore_requires_vm_name(self):
        """Test 'azlin snapshot restore' without VM name fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "restore"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_snapshot_delete_requires_snapshot_name(self):
        """Test 'azlin snapshot delete' without snapshot name fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "delete"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_snapshot_delete_with_snapshot_name(self):
        """Test 'azlin snapshot delete snap-123' accepts snapshot name."""
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "delete", "snap-123"])

        assert_option_accepted(result)


# =============================================================================
# TEST CLASS: azlin template (16 tests)
# =============================================================================


class TestTemplateCommandSyntax:
    """Test syntax validation for 'azlin template' command group (16 tests).

    Subcommands: create, list, delete, export, import
    """

    # -------------------------------------------------------------------------
    # Category 1: Group-Level Syntax (3 tests)
    # -------------------------------------------------------------------------

    def test_template_no_subcommand_shows_help(self):
        """Test 'azlin template' without subcommand shows help."""
        runner = CliRunner()
        result = runner.invoke(main, ["template"])

        assert result.exit_code in [0, 2]
        assert "template" in result.output.lower()

    def test_template_help_displays_usage(self):
        """Test 'azlin template --help' displays help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["template", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "template" in result.output.lower()

    def test_template_invalid_subcommand_fails(self):
        """Test 'azlin template invalid' fails with clear error."""
        runner = CliRunner()
        result = runner.invoke(main, ["template", "invalid"])

        assert result.exit_code != 0
        assert "no such command" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 2: template create Subcommand (4 tests)
    # -------------------------------------------------------------------------

    def test_template_create_requires_name(self):
        """Test 'azlin template create' without name fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["template", "create"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_template_create_with_name(self):
        """Test 'azlin template create dev-vm' accepts name."""
        runner = CliRunner()
        result = runner.invoke(main, ["template", "create", "dev-vm"])

        assert_option_accepted(result)

    def test_template_create_help(self):
        """Test 'azlin template create --help' displays help."""
        runner = CliRunner()
        result = runner.invoke(main, ["template", "create", "--help"])

        assert result.exit_code == 0
        assert "create" in result.output.lower()

    def test_template_create_extra_args_rejected(self):
        """Test 'azlin template create name extra' rejects extra args."""
        runner = CliRunner()
        result = runner.invoke(main, ["template", "create", "name", "extra"])

        assert result.exit_code != 0

    # -------------------------------------------------------------------------
    # Category 3: template list Subcommand (2 tests)
    # -------------------------------------------------------------------------

    def test_template_list_no_args(self):
        """Test 'azlin template list' without args is valid."""
        runner = CliRunner()
        result = runner.invoke(main, ["template", "list"])

        assert "missing argument" not in result.output.lower()

    def test_template_list_help(self):
        """Test 'azlin template list --help' displays help."""
        runner = CliRunner()
        result = runner.invoke(main, ["template", "list", "--help"])

        assert result.exit_code == 0
        assert "list" in result.output.lower()

    # -------------------------------------------------------------------------
    # Category 4: template delete Subcommand (2 tests)
    # -------------------------------------------------------------------------

    def test_template_delete_requires_name(self):
        """Test 'azlin template delete' without name fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["template", "delete"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_template_delete_with_name(self):
        """Test 'azlin template delete dev-vm' accepts name."""
        runner = CliRunner()
        result = runner.invoke(main, ["template", "delete", "dev-vm"])

        assert_option_accepted(result)

    # -------------------------------------------------------------------------
    # Category 5: template export/import Subcommands (5 tests)
    # -------------------------------------------------------------------------

    def test_template_export_requires_name(self):
        """Test 'azlin template export' without name fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["template", "export"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_template_export_requires_output_path(self):
        """Test 'azlin template export dev-vm' without output path fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["template", "export", "dev-vm"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_template_export_with_name_and_path(self):
        """Test 'azlin template export dev-vm template.yaml' accepts both args."""
        runner = CliRunner()
        result = runner.invoke(main, ["template", "export", "dev-vm", "template.yaml"])

        assert_option_accepted(result)

    def test_template_import_requires_file(self):
        """Test 'azlin template import' without file fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["template", "import"])

        assert result.exit_code != 0
        assert "missing argument" in result.output.lower()

    def test_template_import_with_file(self):
        """Test 'azlin template import template.yaml' accepts file."""
        runner = CliRunner()
        result = runner.invoke(main, ["template", "import", "template.yaml"])

        # May fail on file existence check, but syntax is OK
        assert_option_accepted(result)


# =============================================================================
# TEST MARKERS AND METADATA
# =============================================================================


# Mark all tests in this module as TDD RED phase and syntax validation
pytestmark = [pytest.mark.tdd_red, pytest.mark.syntax, pytest.mark.priority3]


# =============================================================================
# SUMMARY
# =============================================================================
"""
Test Coverage Summary (Priority 3 Commands):

azlin batch (18 tests):
  - Group-level syntax: 3 tests
  - batch stop: 5 tests
  - batch start: 3 tests
  - batch command: 4 tests
  - batch sync: 3 tests

azlin env (18 tests):
  - Group-level syntax: 3 tests
  - env set: 5 tests
  - env list: 3 tests
  - env delete: 2 tests
  - env export/import/clear: 5 tests

azlin storage (20 tests):
  - Group-level syntax: 3 tests
  - storage create: 6 tests
  - storage list: 2 tests
  - storage status: 2 tests
  - storage delete: 2 tests
  - storage mount: 3 tests
  - storage unmount: 2 tests

azlin snapshot (22 tests):
  - Group-level syntax: 3 tests
  - snapshot enable: 5 tests
  - snapshot disable: 2 tests
  - snapshot sync: 3 tests
  - snapshot status: 2 tests
  - snapshot create/list/restore/delete: 7 tests

azlin template (16 tests):
  - Group-level syntax: 3 tests
  - template create: 4 tests
  - template list: 2 tests
  - template delete: 2 tests
  - template export/import: 5 tests

TOTAL: 94 tests for Priority 3 commands
Running Total: 55 (original) + 100 (priority2) + 94 (priority3) = 249 tests
"""
