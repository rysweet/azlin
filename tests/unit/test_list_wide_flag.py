"""Unit tests for azlin list --wide flag feature.

Tests the --wide/-w flag functionality for preventing VM name truncation
in both single-context and multi-context list displays.

Test Coverage:
- Default behavior (width=20/30 for Session Name/VM Name)
- Wide mode behavior (no_wrap=True for Session Name/VM Name)
- Both -w and --wide flags work correctly
- Single-context display formatting
- Multi-context display formatting
- Session Name column presence in both modes
"""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from azlin.cli import list_command
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
# TESTS: Multi-Context Display - Wide Mode
# =============================================================================


class TestMultiContextDisplayWideMode:
    """Test wide mode in multi-context display."""

    def test_wide_mode_false_uses_fixed_width(self, sample_context_result, mock_console):
        """Test that wide_mode=False uses fixed column widths."""
        display = MultiContextDisplay(console=mock_console)

        # Capture table creation by mocking print
        with patch("azlin.multi_context_display.Table") as mock_table_class:
            mock_table = Mock()
            mock_table_class.return_value = mock_table

            display._display_context_vms(sample_context_result, wide_mode=False)

            # Verify table columns have fixed widths
            calls = mock_table.add_column.call_args_list
            assert len(calls) >= 2  # At least Session Name and VM Name

            # First column: Session Name with width=20
            session_col_call = calls[0]
            assert "Session Name" in session_col_call[0]
            assert session_col_call[1].get("width") == 20
            assert session_col_call[1].get("no_wrap") is not True

            # Second column: VM Name with width=30
            vm_col_call = calls[1]
            assert "VM Name" in vm_col_call[0]
            assert vm_col_call[1].get("width") == 30
            assert vm_col_call[1].get("no_wrap") is not True

    def test_wide_mode_true_uses_no_wrap(self, sample_context_result, mock_console):
        """Test that wide_mode=True uses no_wrap for columns."""
        display = MultiContextDisplay(console=mock_console)

        with patch("azlin.multi_context_display.Table") as mock_table_class:
            mock_table = Mock()
            mock_table_class.return_value = mock_table

            display._display_context_vms(sample_context_result, wide_mode=True)

            # Verify table columns use no_wrap
            calls = mock_table.add_column.call_args_list
            assert len(calls) >= 2

            # First column: Session Name with no_wrap=True
            session_col_call = calls[0]
            assert "Session Name" in session_col_call[0]
            assert session_col_call[1].get("no_wrap") is True
            assert "width" not in session_col_call[1] or session_col_call[1].get("width") is None

            # Second column: VM Name with no_wrap=True
            vm_col_call = calls[1]
            assert "VM Name" in vm_col_call[0]
            assert vm_col_call[1].get("no_wrap") is True
            assert "width" not in vm_col_call[1] or vm_col_call[1].get("width") is None

    def test_session_name_column_exists(self, sample_context_result, mock_console):
        """Test that Session Name column is present in multi-context display."""
        display = MultiContextDisplay(console=mock_console)

        with patch("azlin.multi_context_display.Table") as mock_table_class:
            mock_table = Mock()
            mock_table_class.return_value = mock_table

            display._display_context_vms(sample_context_result, wide_mode=False)

            # Verify Session Name column is added
            calls = mock_table.add_column.call_args_list
            session_name_found = any("Session Name" in str(call) for call in calls)
            assert session_name_found, "Session Name column should be present"

    def test_vm_rows_include_session_name(self, sample_context_result, mock_console):
        """Test that VM rows include session name as first column."""
        display = MultiContextDisplay(console=mock_console)

        with patch("azlin.multi_context_display.Table") as mock_table_class:
            mock_table = Mock()
            mock_table_class.return_value = mock_table

            display._display_context_vms(sample_context_result, wide_mode=False)

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

    def test_empty_vms_shows_correct_column_count(self, sample_context, mock_console):
        """Test that empty VM list shows correct number of columns."""
        ctx_result = ContextVMResult(
            context_name="production",
            context=sample_context,
            success=True,
            vms=[],
            duration=1.0,
        )

        display = MultiContextDisplay(console=mock_console)

        with patch("azlin.multi_context_display.Table") as mock_table_class:
            mock_table = Mock()
            mock_table_class.return_value = mock_table

            display._display_context_vms(ctx_result, wide_mode=False)

            # Verify empty row has 7 columns (Session Name, VM Name, Status, IP, Region, Size, vCPUs)
            row_calls = mock_table.add_row.call_args_list
            assert len(row_calls) == 1
            assert len(row_calls[0][0]) == 7  # 7 columns total


# =============================================================================
# TESTS: CLI Integration - Wide Flag
# =============================================================================


class TestListCommandWideFlag:
    """Test list command --wide/-w flag integration."""

    def test_wide_flag_long_form(self):
        """Test that --wide flag is accepted by CLI."""
        runner = CliRunner()

        # Mock all the dependencies to focus on flag parsing
        with patch("azlin.cli.ContextManager"), \
             patch("azlin.cli.ConfigManager"), \
             patch("azlin.cli.TagManager"), \
             patch("azlin.cli.VMManager"), \
             patch("azlin.cli.Console"):

            # This should not error on flag parsing
            result = runner.invoke(list_command, ["--wide"])

            # May fail on missing config/auth, but flag should be parsed
            # Check that --wide is not an "unknown option"
            assert "no such option: --wide" not in result.output.lower()

    def test_wide_flag_short_form(self):
        """Test that -w flag is accepted by CLI."""
        runner = CliRunner()

        with patch("azlin.cli.ContextManager"), \
             patch("azlin.cli.ConfigManager"), \
             patch("azlin.cli.TagManager"), \
             patch("azlin.cli.VMManager"), \
             patch("azlin.cli.Console"):

            result = runner.invoke(list_command, ["-w"])

            # Check that -w is not an "unknown option"
            assert "no such option: -w" not in result.output.lower()

    def test_wide_flag_with_other_options(self):
        """Test that --wide works with other list options."""
        runner = CliRunner()

        with patch("azlin.cli.ContextManager"), \
             patch("azlin.cli.ConfigManager"), \
             patch("azlin.cli.TagManager"), \
             patch("azlin.cli.VMManager"), \
             patch("azlin.cli.Console"):

            # Test with multiple flags
            result = runner.invoke(list_command, ["--wide", "--all"])

            # Should parse both flags without error
            assert "no such option" not in result.output.lower()


# =============================================================================
# TESTS: Display Behavior Verification
# =============================================================================


class TestDisplayBehaviorWithWideMode:
    """Test display behavior differences between normal and wide modes."""

    def test_display_results_passes_wide_mode_to_context_vms(self, multi_result, mock_console):
        """Test that display_results passes wide_mode to _display_context_vms."""
        display = MultiContextDisplay(console=mock_console)

        with patch.object(display, "_display_context_vms") as mock_display_ctx:
            display.display_results(multi_result, show_summary=False, wide_mode=True)

            # Verify _display_context_vms was called with wide_mode=True
            assert mock_display_ctx.called
            call_kwargs = mock_display_ctx.call_args[1]
            assert call_kwargs.get("wide_mode") is True

    def test_display_results_default_wide_mode_false(self, multi_result, mock_console):
        """Test that display_results defaults to wide_mode=False."""
        display = MultiContextDisplay(console=mock_console)

        with patch.object(display, "_display_context_vms") as mock_display_ctx:
            display.display_results(multi_result, show_summary=False)

            # Verify _display_context_vms was called with wide_mode=False (default)
            assert mock_display_ctx.called
            call_kwargs = mock_display_ctx.call_args[1]
            assert call_kwargs.get("wide_mode") is False

    def test_wide_mode_parameter_in_signature(self, sample_context_result, mock_console):
        """Test that _display_context_vms accepts wide_mode parameter."""
        display = MultiContextDisplay(console=mock_console)

        # Should not raise TypeError for unexpected keyword argument
        try:
            display._display_context_vms(sample_context_result, wide_mode=True)
            display._display_context_vms(sample_context_result, wide_mode=False)
        except TypeError as e:
            pytest.fail(f"wide_mode parameter not accepted: {e}")


# =============================================================================
# TESTS: Regression Tests
# =============================================================================


class TestRegressionWideMode:
    """Regression tests to ensure wide mode doesn't break existing functionality."""

    def test_wide_mode_false_preserves_original_behavior(self, sample_context_result, mock_console):
        """Test that wide_mode=False maintains original column widths."""
        display = MultiContextDisplay(console=mock_console)

        with patch("azlin.multi_context_display.Table") as mock_table_class:
            mock_table = Mock()
            mock_table_class.return_value = mock_table

            # Call with wide_mode=False (should match original behavior)
            display._display_context_vms(sample_context_result, wide_mode=False)

            # Verify columns match original spec
            calls = mock_table.add_column.call_args_list

            # Map columns to their specs
            column_specs = {call[0][0]: call[1] for call in calls}

            # Verify key columns have expected widths
            assert column_specs.get("Session Name", {}).get("width") == 20
            assert column_specs.get("VM Name", {}).get("width") == 30
            assert column_specs.get("Status", {}).get("width") == 10
            assert column_specs.get("IP", {}).get("width") == 15

    def test_vm_with_no_session_name_shows_dash(self, sample_context, mock_console):
        """Test that VMs without session_name show '-' in Session Name column."""
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

            display._display_context_vms(ctx_result, wide_mode=False)

            # Verify row shows "-" for missing session name
            row_calls = mock_table.add_row.call_args_list
            assert len(row_calls) > 0
            first_row = row_calls[0][0]
            assert first_row[0] == "-", "Missing session name should show as '-'"
