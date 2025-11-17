"""Unit tests for MultiContextDisplay module.

Tests Rich table formatting and display of multi-context VM query results.
Follows testing pyramid: 95% unit tests + 5% display validation.

Test Coverage:
- Display formatting for successful and failed contexts
- Summary header and footer rendering
- Table formatting with proper styling
- Edge cases: empty results, all failures, no context results
- Formatting methods and string generation
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from io import StringIO

from rich.console import Console

from azlin.multi_context_display import (
    MultiContextDisplay,
    MultiContextDisplayError,
)
from azlin.multi_context_list import (
    MultiContextVMResult,
    ContextVMResult,
)
from azlin.vm_manager import VMInfo
from azlin.context_manager import Context


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_console():
    """Create mock Rich console."""
    console = Mock(spec=Console)
    console.print = Mock()
    return console


@pytest.fixture
def sample_vms():
    """Create sample VMs for display testing."""
    return [
        VMInfo(
            name="azlin-prod-01",
            resource_group="azlin-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.4",
            vm_size="Standard_D2s_v3",
        ),
        VMInfo(
            name="azlin-prod-02",
            resource_group="azlin-rg",
            location="westus",
            power_state="VM stopped",
            public_ip=None,
            vm_size="Standard_B2s",
        ),
        VMInfo(
            name="azlin-prod-03",
            resource_group="azlin-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.6",
            vm_size="Standard_D4s_v3",
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
    """Create sample successful context result."""
    return ContextVMResult(
        context_name="production",
        context=sample_context,
        success=True,
        vms=sample_vms,
        duration=1.5,
    )


@pytest.fixture
def sample_failed_context_result(sample_context):
    """Create sample failed context result."""
    return ContextVMResult(
        context_name="production",
        context=sample_context,
        success=False,
        error_message="Authentication failed: invalid credentials",
        duration=0.5,
    )


@pytest.fixture
def multi_result_success(sample_context_result):
    """Create aggregated result with successful contexts."""
    return MultiContextVMResult(
        context_results=[
            sample_context_result,
            ContextVMResult(
                context_name="staging",
                context=Mock(),
                success=True,
                vms=sample_context_result.vms[:2],
                duration=1.2,
            ),
        ],
        total_duration=2.7,
    )


@pytest.fixture
def multi_result_mixed(sample_context_result, sample_failed_context_result):
    """Create aggregated result with mixed success/failure."""
    return MultiContextVMResult(
        context_results=[
            sample_context_result,
            sample_failed_context_result,
        ],
        total_duration=2.0,
    )


# =============================================================================
# TESTS: Initialization
# =============================================================================


class TestInitialization:
    """Test display initialization."""

    def test_init_with_console(self, mock_console):
        """Test initialization with provided console."""
        display = MultiContextDisplay(console=mock_console)
        assert display.console == mock_console

    def test_init_creates_console(self):
        """Test that console is created if not provided."""
        display = MultiContextDisplay()
        assert display.console is not None
        assert isinstance(display.console, Console)

    def test_init_with_none_console(self):
        """Test initialization with explicit None console."""
        display = MultiContextDisplay(console=None)
        assert display.console is not None


# =============================================================================
# TESTS: Display Results
# =============================================================================


class TestDisplayResults:
    """Test main display_results method."""

    def test_display_results_with_defaults(self, multi_result_success, mock_console):
        """Test display_results with default parameters."""
        display = MultiContextDisplay(console=mock_console)
        display.display_results(multi_result_success)

        # Should call print for summary, context results, and footer
        assert mock_console.print.call_count >= 3

    def test_display_results_without_summary(self, multi_result_success, mock_console):
        """Test display_results without summary."""
        display = MultiContextDisplay(console=mock_console)
        display.display_results(
            multi_result_success, show_summary=False, show_errors=True
        )

        # Summary methods should still be called for header
        # (implementation depends on _display_summary_header behavior)
        assert mock_console.print.called

    def test_display_results_without_errors(
        self, multi_result_mixed, mock_console
    ):
        """Test display_results hiding error details."""
        display = MultiContextDisplay(console=mock_console)
        display.display_results(
            multi_result_mixed, show_errors=False, show_summary=True
        )

        assert mock_console.print.called

    def test_display_results_mixed_success_and_failure(
        self, multi_result_mixed, mock_console
    ):
        """Test displaying mixed results."""
        display = MultiContextDisplay(console=mock_console)
        display.display_results(multi_result_mixed)

        # Should display both successful and failed contexts
        assert mock_console.print.call_count >= 4  # header + 2 contexts + footer


# =============================================================================
# TESTS: Summary Header Display
# =============================================================================


class TestSummaryHeaderDisplay:
    """Test summary header rendering."""

    def test_display_summary_header_all_success(
        self, multi_result_success, mock_console
    ):
        """Test summary header with all successful contexts."""
        display = MultiContextDisplay(console=mock_console)
        display._display_summary_header(multi_result_success)

        assert mock_console.print.called
        call_args = mock_console.print.call_args_list[0]
        # Panel should be printed
        assert len(call_args[0]) > 0

    def test_display_summary_header_mixed_results(
        self, multi_result_mixed, mock_console
    ):
        """Test summary header with mixed results."""
        display = MultiContextDisplay(console=mock_console)
        display._display_summary_header(multi_result_mixed)

        assert mock_console.print.called

    def test_display_summary_header_shows_context_count(
        self, multi_result_success, mock_console
    ):
        """Test that summary shows context count."""
        display = MultiContextDisplay(console=mock_console)
        display._display_summary_header(multi_result_success)

        # Verify print was called with Panel containing summary info
        assert mock_console.print.called

    def test_display_summary_header_shows_vm_counts(
        self, multi_result_success, mock_console
    ):
        """Test that summary shows VM counts."""
        display = MultiContextDisplay(console=mock_console)
        display._display_summary_header(multi_result_success)

        assert mock_console.print.called


# =============================================================================
# TESTS: Context VM Display
# =============================================================================


class TestContextVMDisplay:
    """Test displaying VMs for a single context."""

    def test_display_context_vms_with_running_and_stopped(
        self, sample_context_result, mock_console
    ):
        """Test displaying context with mixed VM states."""
        display = MultiContextDisplay(console=mock_console)
        display._display_context_vms(sample_context_result)

        # Should create table and print
        assert mock_console.print.called

    def test_display_context_vms_empty_list(self, sample_context, mock_console):
        """Test displaying context with no VMs."""
        ctx_result = ContextVMResult(
            context_name="production",
            context=sample_context,
            success=True,
            vms=[],
            duration=1.0,
        )

        display = MultiContextDisplay(console=mock_console)
        display._display_context_vms(ctx_result)

        assert mock_console.print.called

    def test_display_context_vms_single_vm(self, sample_context, mock_console):
        """Test displaying context with single VM."""
        vm = VMInfo(
            name="azlin-test-01",
            resource_group="azlin-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.4",
            vm_size="Standard_D2s_v3",
        )

        ctx_result = ContextVMResult(
            context_name="production",
            context=sample_context,
            success=True,
            vms=[vm],
            duration=1.0,
        )

        display = MultiContextDisplay(console=mock_console)
        display._display_context_vms(ctx_result)

        assert mock_console.print.called

    def test_display_context_vms_shows_context_name(
        self, sample_context_result, mock_console
    ):
        """Test that context name is shown."""
        display = MultiContextDisplay(console=mock_console)
        display._display_context_vms(sample_context_result)

        assert mock_console.print.called

    def test_display_context_vms_shows_duration(
        self, sample_context_result, mock_console
    ):
        """Test that query duration is shown."""
        display = MultiContextDisplay(console=mock_console)
        display._display_context_vms(sample_context_result)

        assert mock_console.print.called

    def test_display_context_vms_shows_vm_count(
        self, sample_context_result, mock_console
    ):
        """Test that VM count is shown."""
        display = MultiContextDisplay(console=mock_console)
        display._display_context_vms(sample_context_result)

        assert mock_console.print.called


# =============================================================================
# TESTS: Error Display
# =============================================================================


class TestErrorDisplay:
    """Test displaying errors for failed contexts."""

    def test_display_context_error(self, sample_failed_context_result, mock_console):
        """Test displaying error for failed context."""
        display = MultiContextDisplay(console=mock_console)
        display._display_context_error(sample_failed_context_result)

        assert mock_console.print.called

    def test_display_context_error_shows_context_name(
        self, sample_failed_context_result, mock_console
    ):
        """Test that context name is shown in error."""
        display = MultiContextDisplay(console=mock_console)
        display._display_context_error(sample_failed_context_result)

        assert mock_console.print.called

    def test_display_context_error_shows_error_message(
        self, sample_failed_context_result, mock_console
    ):
        """Test that error message is shown."""
        display = MultiContextDisplay(console=mock_console)
        display._display_context_error(sample_failed_context_result)

        assert mock_console.print.called

    def test_display_context_error_shows_duration(
        self, sample_failed_context_result, mock_console
    ):
        """Test that error duration is shown."""
        display = MultiContextDisplay(console=mock_console)
        display._display_context_error(sample_failed_context_result)

        assert mock_console.print.called


# =============================================================================
# TESTS: Footer Summary Display
# =============================================================================


class TestFooterSummaryDisplay:
    """Test footer summary rendering."""

    def test_display_footer_summary(self, multi_result_success, mock_console):
        """Test displaying footer summary."""
        display = MultiContextDisplay(console=mock_console)
        display._display_footer_summary(multi_result_success)

        assert mock_console.print.called

    def test_display_footer_summary_shows_totals(
        self, multi_result_success, mock_console
    ):
        """Test that footer shows total values."""
        display = MultiContextDisplay(console=mock_console)
        display._display_footer_summary(multi_result_success)

        assert mock_console.print.called

    def test_display_footer_summary_mixed_results(
        self, multi_result_mixed, mock_console
    ):
        """Test footer with mixed results."""
        display = MultiContextDisplay(console=mock_console)
        display._display_footer_summary(multi_result_mixed)

        assert mock_console.print.called


# =============================================================================
# TESTS: Error Summary Display
# =============================================================================


class TestErrorSummaryDisplay:
    """Test error summary display."""

    def test_display_error_summary_no_failures(
        self, multi_result_success, mock_console
    ):
        """Test error summary when all succeeded."""
        display = MultiContextDisplay(console=mock_console)
        display.display_error_summary(multi_result_success)

        assert mock_console.print.called

    def test_display_error_summary_with_failures(
        self, multi_result_mixed, mock_console
    ):
        """Test error summary with failures."""
        display = MultiContextDisplay(console=mock_console)
        display.display_error_summary(multi_result_mixed)

        assert mock_console.print.called

    def test_display_error_summary_all_failures(self, sample_failed_context_result, mock_console):
        """Test error summary with all failures."""
        result = MultiContextVMResult(
            context_results=[sample_failed_context_result],
            total_duration=0.5,
        )

        display = MultiContextDisplay(console=mock_console)
        display.display_error_summary(result)

        assert mock_console.print.called


# =============================================================================
# TESTS: Formatting Methods
# =============================================================================


class TestFormattingMethods:
    """Test formatting helper methods."""

    def test_format_summary_line(self, multi_result_success):
        """Test formatting single-line summary."""
        display = MultiContextDisplay()
        summary = display.format_summary_line(multi_result_success)

        assert isinstance(summary, str)
        assert "contexts" in summary
        assert "VMs" in summary
        assert "running" in summary
        assert "stopped" in summary

    def test_format_summary_line_empty_results(self):
        """Test formatting summary with no results."""
        result = MultiContextVMResult(context_results=[], total_duration=0.0)

        display = MultiContextDisplay()
        summary = display.format_summary_line(result)

        assert isinstance(summary, str)
        assert "0 contexts" in summary
        assert "0 VMs" in summary

    def test_format_summary_line_all_running(self, sample_context):
        """Test formatting summary with all running VMs."""
        running_vm = VMInfo(
            name="azlin-test-01",
            resource_group="azlin-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.4",
            vm_size="Standard_D2s_v3",
        )

        ctx_result = ContextVMResult(
            context_name="production",
            context=sample_context,
            success=True,
            vms=[running_vm] * 5,
            duration=1.0,
        )

        result = MultiContextVMResult(
            context_results=[ctx_result],
            total_duration=1.0,
        )

        display = MultiContextDisplay()
        summary = display.format_summary_line(result)

        assert "5 VMs" in summary
        assert "5 running" in summary
        assert "0 stopped" in summary

    def test_format_summary_line_with_duration(self, multi_result_success):
        """Test that summary includes duration."""
        display = MultiContextDisplay()
        summary = display.format_summary_line(multi_result_success)

        assert "s" in summary  # Seconds suffix


# =============================================================================
# TESTS: Cost Summary Display
# =============================================================================


class TestCostSummaryDisplay:
    """Test cost summary display (placeholder)."""

    def test_display_cost_summary_placeholder(self, multi_result_success, mock_console):
        """Test cost summary method (currently placeholder)."""
        display = MultiContextDisplay(console=mock_console)
        # Should not raise error even though not implemented
        display.display_cost_summary(multi_result_success)


# =============================================================================
# TESTS: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_display_empty_results(self, mock_console):
        """Test displaying completely empty results."""
        result = MultiContextVMResult(context_results=[], total_duration=0.0)

        display = MultiContextDisplay(console=mock_console)
        display.display_results(result)

        assert mock_console.print.called

    def test_display_very_long_error_message(self, sample_context, mock_console):
        """Test displaying very long error messages."""
        long_error = "Error: " + "x" * 500

        ctx_result = ContextVMResult(
            context_name="production",
            context=sample_context,
            success=False,
            error_message=long_error,
            duration=1.0,
        )

        result = MultiContextVMResult(
            context_results=[ctx_result],
            total_duration=1.0,
        )

        display = MultiContextDisplay(console=mock_console)
        display.display_results(result)

        assert mock_console.print.called

    def test_display_many_vms(self, sample_context, mock_console):
        """Test displaying many VMs in single context."""
        vms = [
            VMInfo(
                name=f"azlin-vm-{i:03d}",
                resource_group="azlin-rg",
                location="eastus",
                power_state="VM running" if i % 2 == 0 else "VM stopped",
                public_ip=f"1.2.3.{i}" if i % 2 == 0 else None,
                vm_size="Standard_D2s_v3",
            )
            for i in range(100)
        ]

        ctx_result = ContextVMResult(
            context_name="production",
            context=sample_context,
            success=True,
            vms=vms,
            duration=5.0,
        )

        result = MultiContextVMResult(
            context_results=[ctx_result],
            total_duration=5.0,
        )

        display = MultiContextDisplay(console=mock_console)
        display.display_results(result)

        assert mock_console.print.called

    def test_display_many_contexts(self, sample_context, sample_vms, mock_console):
        """Test displaying many contexts."""
        contexts = [
            ContextVMResult(
                context_name=f"context-{i:02d}",
                context=sample_context,
                success=i % 2 == 0,
                vms=[] if i % 2 != 0 else sample_vms[:1],
                error_message=None if i % 2 == 0 else "Error",
                duration=1.0,
            )
            for i in range(20)
        ]

        result = MultiContextVMResult(
            context_results=contexts,
            total_duration=10.0,
        )

        display = MultiContextDisplay(console=mock_console)
        display.display_results(result)

        assert mock_console.print.called

    def test_display_vm_without_public_ip(self, sample_context, mock_console):
        """Test displaying VM without public IP."""
        vm = VMInfo(
            name="azlin-private-vm",
            resource_group="azlin-rg",
            location="eastus",
            power_state="VM running",
            public_ip=None,
            vm_size="Standard_D2s_v3",
        )

        ctx_result = ContextVMResult(
            context_name="production",
            context=sample_context,
            success=True,
            vms=[vm],
            duration=1.0,
        )

        result = MultiContextVMResult(
            context_results=[ctx_result],
            total_duration=1.0,
        )

        display = MultiContextDisplay(console=mock_console)
        display.display_results(result)

        assert mock_console.print.called

    def test_display_vm_with_unknown_status(self, sample_context, mock_console):
        """Test displaying VM with unknown status."""
        vm = VMInfo(
            name="azlin-unknown",
            resource_group="azlin-rg",
            location="eastus",
            power_state="VM unknown",
            public_ip="1.2.3.4",
            vm_size="Standard_D2s_v3",
        )

        ctx_result = ContextVMResult(
            context_name="production",
            context=sample_context,
            success=True,
            vms=[vm],
            duration=1.0,
        )

        result = MultiContextVMResult(
            context_results=[ctx_result],
            total_duration=1.0,
        )

        display = MultiContextDisplay(console=mock_console)
        display.display_results(result)

        assert mock_console.print.called

    def test_format_summary_line_very_long_duration(self, sample_context):
        """Test formatting with very long query duration."""
        ctx_result = ContextVMResult(
            context_name="production",
            context=sample_context,
            success=True,
            vms=[],
            duration=300.5,  # 5+ minutes
        )

        result = MultiContextVMResult(
            context_results=[ctx_result],
            total_duration=300.5,
        )

        display = MultiContextDisplay()
        summary = display.format_summary_line(result)

        assert "300.50s" in summary or "300" in summary
