"""Unit tests for azlin list --compact flag feature.

Tests the --compact/-c flag functionality for using narrow column widths
in both single-context and multi-context list displays.

Test Coverage:
- Default behavior (standard widths for Session Name/VM Name/etc)
- Compact mode behavior (reduced widths for all columns)
- Both -c and --compact flags work correctly
- --compact and --wide are mutually exclusive
- Single-context display formatting
- Multi-context display formatting
- Compact mode works with --show-tmux flag
- Compact mode works with --all-contexts flag
"""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from azlin.cli import main
from azlin.context_manager import Context
from azlin.multi_context_display import MultiContextDisplay
from azlin.multi_context_list import ContextVMResult, MultiContextVMResult
from azlin.vm_manager import VMInfo

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_console():
    """Create mock Rich console."""
    console = Mock()
    console.print = Mock()
    return console


@pytest.fixture
def sample_vms():
    """Create sample VMs with long names for truncation testing."""
    return [
        VMInfo(
            name="azlin-very-long-production-vm-name-01",
            resource_group="azlin-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.4",
            vm_size="Standard_D2s_v3",
            session_name="my-very-long-session-name-for-testing",
        ),
        VMInfo(
            name="azlin-short-vm",
            resource_group="azlin-rg",
            location="westus",
            power_state="VM stopped",
            public_ip=None,
            vm_size="Standard_B2s",
            session_name="short",
        ),
    ]


@pytest.fixture
def sample_context():
    """Create sample context."""
    return Context(
        name="production",
        subscription_id="12345678-1234-1234-1234-123456789001",
        tenant_id="87654321-4321-4321-4321-210987654321",
    )


@pytest.fixture
def sample_context_result(sample_context, sample_vms):
    """Create sample context result for testing."""
    return ContextVMResult(
        context_name="production",
        context=sample_context,
        success=True,
        vms=sample_vms,
        duration=1.5,
    )


@pytest.fixture
def multi_result(sample_context_result):
    """Create multi-context result for testing."""
    return MultiContextVMResult(
        context_results=[sample_context_result],
        total_duration=1.5,
    )


# =============================================================================
# TESTS: CLI Integration - Compact Flag
# =============================================================================


class TestListCommandCompactFlag:
    """Test list command --compact/-c flag integration."""

    def test_compact_flag_long_form(self):
        """Test that --compact flag is accepted by CLI."""
        runner = CliRunner()

        # Mock all the dependencies to focus on flag parsing
        with (
            patch("azlin.cli.ContextManager"),
            patch("azlin.cli.ConfigManager"),
            patch("azlin.cli.TagManager"),
            patch("azlin.cli.VMManager"),
            patch("azlin.cli.Console"),
        ):
            # This should not error on flag parsing
            result = runner.invoke(main, ["list", "--compact"])

            # May fail on missing config/auth, but flag should be parsed
            # Check that --compact is not an "unknown option"
            assert "no such option: --compact" not in result.output.lower()

    def test_compact_flag_short_form(self):
        """Test that -c flag is accepted by CLI."""
        runner = CliRunner()

        with (
            patch("azlin.cli.ContextManager"),
            patch("azlin.cli.ConfigManager"),
            patch("azlin.cli.TagManager"),
            patch("azlin.cli.VMManager"),
            patch("azlin.cli.Console"),
        ):
            result = runner.invoke(main, ["list", "-c"])

            # Check that -c is not an "unknown option"
            assert "no such option: -c" not in result.output.lower()

    def test_compact_and_wide_mutually_exclusive(self):
        """Test that --compact and --wide cannot be used together."""
        runner = CliRunner()

        with (
            patch("azlin.cli.ContextManager"),
            patch("azlin.cli.ConfigManager"),
            patch("azlin.cli.TagManager"),
            patch("azlin.cli.VMManager"),
            patch("azlin.cli.Console"),
        ):
            # Try to use both flags together
            result = runner.invoke(main, ["list", "--compact", "--wide"])

            # Should fail with mutual exclusivity error
            assert result.exit_code != 0
            assert "mutually exclusive" in result.output.lower()

    def test_compact_with_all_contexts(self):
        """Test that --compact works with --all-contexts."""
        runner = CliRunner()

        with (
            patch("azlin.cli.ContextManager"),
            patch("azlin.cli.ConfigManager"),
            patch("azlin.cli.TagManager"),
            patch("azlin.cli.VMManager"),
            patch("azlin.cli.Console"),
            patch("azlin.cli._handle_multi_context_list") as mock_handler,
        ):
            result = runner.invoke(main, ["list", "--compact", "--all-contexts"])

            # Should parse both flags without error
            assert "no such option" not in result.output.lower()
            # Handler should be called (may fail later on auth/config)
            assert mock_handler.called or "error" in result.output.lower()

    def test_compact_with_show_tmux(self):
        """Test that --compact works with --show-tmux."""
        runner = CliRunner()

        with (
            patch("azlin.cli.ContextManager"),
            patch("azlin.cli.ConfigManager"),
            patch("azlin.cli.TagManager"),
            patch("azlin.cli.VMManager"),
            patch("azlin.cli.Console"),
        ):
            # Test with both flags
            result = runner.invoke(main, ["list", "--compact", "--show-tmux"])

            # Should parse both flags without error
            assert "no such option" not in result.output.lower()


# =============================================================================
# TESTS: Multi-Context Display - Compact Mode
# =============================================================================


class TestMultiContextDisplayCompactMode:
    """Test compact mode in multi-context display."""

    def test_compact_mode_false_uses_standard_width(self, sample_context_result, mock_console):
        """Test that compact_mode=False uses standard column widths."""
        display = MultiContextDisplay(console=mock_console)

        # Capture table creation by mocking print
        with patch("azlin.multi_context_display.Table") as mock_table_class:
            mock_table = Mock()
            mock_table_class.return_value = mock_table

            display._display_context_vms(sample_context_result, compact_mode=False)

            # Verify table columns have standard widths
            calls = mock_table.add_column.call_args_list
            assert len(calls) >= 2  # At least Session Name and VM Name

            # First column: Session Name with width=14 (standard)
            session_col_call = calls[0]
            assert "Session Name" in session_col_call[0]
            assert session_col_call[1].get("width") == 14
            assert session_col_call[1].get("no_wrap") is not True

            # Second column: VM Name with width=22 (standard)
            vm_col_call = calls[1]
            assert "VM Name" in vm_col_call[0]
            assert vm_col_call[1].get("width") == 22
            assert vm_col_call[1].get("no_wrap") is not True

    def test_compact_mode_true_uses_narrow_columns(self, sample_context_result, mock_console):
        """Test that compact_mode=True uses narrow column widths."""
        display = MultiContextDisplay(console=mock_console)

        with patch("azlin.multi_context_display.Table") as mock_table_class:
            mock_table = Mock()
            mock_table_class.return_value = mock_table

            display._display_context_vms(sample_context_result, compact_mode=True)

            # Verify table columns use compact widths
            calls = mock_table.add_column.call_args_list
            assert len(calls) >= 7  # All columns present

            # Map columns to their specs
            column_specs = {call[0][0]: call[1] for call in calls}

            # Verify compact widths (narrower than standard)
            assert column_specs.get("Session Name", {}).get("width") == 12  # vs 14 standard
            assert column_specs.get("VM Name", {}).get("width") == 18  # vs 22 standard
            assert column_specs.get("Status", {}).get("width") == 8  # vs 10 standard
            assert column_specs.get("IP", {}).get("width") == 13  # vs 15 standard
            assert column_specs.get("Region", {}).get("width") == 8  # vs 10 standard
            assert column_specs.get("SKU", {}).get("width") == 12  # vs 15 standard
            assert column_specs.get("vCPUs", {}).get("width") == 5  # vs 6 standard

    def test_session_name_column_exists_in_compact(self, sample_context_result, mock_console):
        """Test that Session Name column is present in compact mode."""
        display = MultiContextDisplay(console=mock_console)

        with patch("azlin.multi_context_display.Table") as mock_table_class:
            mock_table = Mock()
            mock_table_class.return_value = mock_table

            display._display_context_vms(sample_context_result, compact_mode=True)

            # Verify Session Name column is added
            calls = mock_table.add_column.call_args_list
            session_name_found = any("Session Name" in str(call) for call in calls)
            assert session_name_found, "Session Name column should be present in compact mode"

    def test_vm_rows_include_session_name_in_compact(self, sample_context_result, mock_console):
        """Test that VM rows include session name as first column in compact mode."""
        display = MultiContextDisplay(console=mock_console)

        with patch("azlin.multi_context_display.Table") as mock_table_class:
            mock_table = Mock()
            mock_table_class.return_value = mock_table

            display._display_context_vms(sample_context_result, compact_mode=True)

            # Verify rows include session name
            row_calls = mock_table.add_row.call_args_list
            assert len(row_calls) > 0

            # Check first VM row (skip empty row if present)
            for call in row_calls:
                if call[0] and call[0][0] != "[dim]No VMs found[/dim]":
                    # First column should be session name or "-"
                    first_col = call[0][0]
                    # Should be session name or dash (not VM name)
                    assert first_col in [
                        "my-very-long-session-name-for-testing",
                        "short",
                        "-",
                    ], f"First column should be session name, got: {first_col}"
                    break


# =============================================================================
# TESTS: Display Behavior Verification
# =============================================================================


class TestDisplayBehaviorWithCompactMode:
    """Test display behavior differences between normal and compact modes."""

    def test_display_results_passes_compact_mode_to_context_vms(self, multi_result, mock_console):
        """Test that display_results passes compact_mode to _display_context_vms."""
        display = MultiContextDisplay(console=mock_console)

        with patch.object(display, "_display_context_vms") as mock_display_ctx:
            display.display_results(multi_result, show_summary=False, compact_mode=True)

            # Verify _display_context_vms was called with compact_mode=True
            assert mock_display_ctx.called
            call_kwargs = mock_display_ctx.call_args[1]
            assert call_kwargs.get("compact_mode") is True

    def test_display_results_default_compact_mode_false(self, multi_result, mock_console):
        """Test that display_results defaults to compact_mode=False."""
        display = MultiContextDisplay(console=mock_console)

        with patch.object(display, "_display_context_vms") as mock_display_ctx:
            display.display_results(multi_result, show_summary=False)

            # Verify _display_context_vms was called with compact_mode=False (default)
            assert mock_display_ctx.called
            call_kwargs = mock_display_ctx.call_args[1]
            assert call_kwargs.get("compact_mode") is False

    def test_compact_mode_parameter_in_signature(self, sample_context_result, mock_console):
        """Test that _display_context_vms accepts compact_mode parameter."""
        display = MultiContextDisplay(console=mock_console)

        # Should not raise TypeError for unexpected keyword argument
        try:
            display._display_context_vms(sample_context_result, compact_mode=True)
            display._display_context_vms(sample_context_result, compact_mode=False)
        except TypeError as e:
            pytest.fail(f"compact_mode parameter not accepted: {e}")


# =============================================================================
# TESTS: Regression Tests
# =============================================================================


class TestRegressionCompactMode:
    """Regression tests to ensure compact mode doesn't break existing functionality."""

    def test_compact_mode_false_preserves_original_behavior(
        self, sample_context_result, mock_console
    ):
        """Test that compact_mode=False maintains original column widths."""
        display = MultiContextDisplay(console=mock_console)

        with patch("azlin.multi_context_display.Table") as mock_table_class:
            mock_table = Mock()
            mock_table_class.return_value = mock_table

            # Call with compact_mode=False (should match original behavior)
            display._display_context_vms(sample_context_result, compact_mode=False)

            # Verify columns match original spec
            calls = mock_table.add_column.call_args_list

            # Map columns to their specs
            column_specs = {call[0][0]: call[1] for call in calls}

            # Verify key columns have expected standard widths
            assert column_specs.get("Session Name", {}).get("width") == 14
            assert column_specs.get("VM Name", {}).get("width") == 22
            assert column_specs.get("Status", {}).get("width") == 10
            assert column_specs.get("IP", {}).get("width") == 15

    def test_vm_with_no_session_name_shows_dash_in_compact(self, sample_context, mock_console):
        """Test that VMs without session_name show '-' in Session Name column in compact mode."""
        vm_no_session = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.4",
            vm_size="Standard_D2s_v3",
        )
        # Explicitly set session_name to None
        vm_no_session.session_name = None

        ctx_result = ContextVMResult(
            context_name="test",
            context=sample_context,
            success=True,
            vms=[vm_no_session],
            duration=1.0,
        )

        display = MultiContextDisplay(console=mock_console)

        with patch("azlin.multi_context_display.Table") as mock_table_class:
            mock_table = Mock()
            mock_table_class.return_value = mock_table

            display._display_context_vms(ctx_result, compact_mode=True)

            # Verify row shows "-" for missing session name
            row_calls = mock_table.add_row.call_args_list
            assert len(row_calls) > 0
            first_row = row_calls[0][0]
            assert first_row[0] == "-", "Missing session name should show as '-' in compact mode"

    def test_wide_and_compact_are_independent(self, sample_context_result, mock_console):
        """Test that wide_mode and compact_mode are independent modes."""
        display = MultiContextDisplay(console=mock_console)

        with patch("azlin.multi_context_display.Table") as mock_table_class:
            mock_table = Mock()
            mock_table_class.return_value = mock_table

            # Wide mode should use no_wrap
            display._display_context_vms(sample_context_result, wide_mode=True, compact_mode=False)
            wide_calls = mock_table.add_column.call_args_list
            mock_table.reset_mock()

            # Compact mode should use narrow widths
            display._display_context_vms(sample_context_result, wide_mode=False, compact_mode=True)
            compact_calls = mock_table.add_column.call_args_list

            # Verify they produce different column specs
            wide_first = wide_calls[0][1]
            compact_first = compact_calls[0][1]

            assert wide_first.get("no_wrap") is True
            assert compact_first.get("width") == 12
            assert compact_first.get("no_wrap") is not True
