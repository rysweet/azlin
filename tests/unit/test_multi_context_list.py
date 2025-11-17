"""Unit tests for MultiContextVMQuery module.

Tests parallel VM query execution across multiple contexts.
Follows testing pyramid: 90% unit + 10% integration tests.

Test Coverage:
- Single and multiple context queries
- Parallel execution and result aggregation
- Error handling (subscription switches, VM query failures)
- Filter and sort operations
- Timeout handling
- Per-context success/failure tracking
"""

from unittest.mock import Mock, patch

import pytest

from azlin.context_manager import Context
from azlin.multi_context_list import (
    ContextVMResult,
    MultiContextQueryError,
    MultiContextVMQuery,
    MultiContextVMResult,
)
from azlin.vm_manager import VMInfo, VMManagerError

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_contexts():
    """Create sample contexts for testing."""
    return [
        Context(
            name="production",
            subscription_id="12345678-1234-1234-1234-123456789001",
            tenant_id="87654321-4321-4321-4321-210987654321",
        ),
        Context(
            name="staging",
            subscription_id="12345678-1234-1234-1234-123456789002",
            tenant_id="87654321-4321-4321-4321-210987654321",
        ),
        Context(
            name="development",
            subscription_id="12345678-1234-1234-1234-123456789003",
            tenant_id="87654321-4321-4321-4321-210987654321",
        ),
    ]


@pytest.fixture
def sample_vms():
    """Create sample VMs for testing."""
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
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.5",
            vm_size="Standard_D2s_v3",
        ),
        VMInfo(
            name="azlin-prod-03",
            resource_group="azlin-rg",
            location="eastus",
            power_state="VM stopped",
            public_ip=None,
            vm_size="Standard_D2s_v3",
        ),
    ]


@pytest.fixture
def query_executor(sample_contexts):
    """Create MultiContextVMQuery instance."""
    return MultiContextVMQuery(contexts=sample_contexts, max_workers=3)


# =============================================================================
# TESTS: Initialization
# =============================================================================


class TestInitialization:
    """Test MultiContextVMQuery initialization."""

    def test_init_with_contexts(self, sample_contexts):
        """Test initialization with contexts."""
        executor = MultiContextVMQuery(contexts=sample_contexts)
        assert executor.contexts == sample_contexts
        assert executor.max_workers == 3  # min(5, 3) = 3

    def test_init_with_custom_max_workers(self, sample_contexts):
        """Test initialization with custom max_workers."""
        executor = MultiContextVMQuery(contexts=sample_contexts, max_workers=2)
        assert executor.max_workers == 2

    def test_init_max_workers_capped_by_context_count(self, sample_contexts):
        """Test that max_workers doesn't exceed context count."""
        executor = MultiContextVMQuery(contexts=sample_contexts, max_workers=10)
        assert executor.max_workers == 3  # min(10, 3) = 3

    def test_init_with_single_context(self):
        """Test initialization with single context."""
        context = Context(
            name="production",
            subscription_id="12345678-1234-1234-1234-123456789001",
            tenant_id="87654321-4321-4321-4321-210987654321",
        )
        executor = MultiContextVMQuery(contexts=[context])
        assert len(executor.contexts) == 1
        assert executor.max_workers == 1

    def test_init_with_empty_contexts_raises_error(self):
        """Test that empty contexts list raises error."""
        with pytest.raises(MultiContextQueryError, match="At least one context required"):
            MultiContextVMQuery(contexts=[])


# =============================================================================
# TESTS: Single Context Query
# =============================================================================


class TestSingleContextQuery:
    """Test querying a single context."""

    def test_query_single_context_success(self, query_executor, sample_vms):
        """Test successful query for single context."""
        context = query_executor.contexts[0]

        with (
            patch("azlin.multi_context_list.subprocess.run"),
            patch("azlin.multi_context_list.VMManager.list_vms", return_value=sample_vms),
            patch("azlin.multi_context_list.VMManager.filter_by_prefix", return_value=sample_vms),
            patch(
                "azlin.multi_context_list.VMManager.sort_by_created_time", return_value=sample_vms
            ),
        ):
            result = query_executor._query_single_context(
                context=context,
                resource_group="azlin-rg",
                include_stopped=True,
                filter_prefix="azlin",
            )

            assert result.success is True
            assert result.context_name == "production"
            assert result.vm_count == 3
            assert result.error_message is None

    def test_query_single_context_no_resource_group(self, query_executor):
        """Test error when resource group not provided."""
        context = query_executor.contexts[0]

        with patch("azlin.multi_context_list.subprocess.run"):
            result = query_executor._query_single_context(
                context=context,
                resource_group=None,
                include_stopped=True,
                filter_prefix="azlin",
            )

            assert result.success is False
            assert "Resource group required" in result.error_message

    def test_query_single_context_vm_manager_error(self, query_executor):
        """Test handling of VMManager errors."""
        context = query_executor.contexts[0]

        with (
            patch("azlin.multi_context_list.subprocess.run"),
            patch(
                "azlin.multi_context_list.VMManager.list_vms",
                side_effect=VMManagerError("Failed to list VMs"),
            ),
        ):
            result = query_executor._query_single_context(
                context=context,
                resource_group="azlin-rg",
                include_stopped=True,
                filter_prefix="azlin",
            )

            assert result.success is False
            assert "Failed to list VMs" in result.error_message

    def test_query_single_context_records_duration(self, query_executor, sample_vms):
        """Test that query duration is recorded."""
        context = query_executor.contexts[0]

        with (
            patch("azlin.multi_context_list.subprocess.run"),
            patch("azlin.multi_context_list.VMManager.list_vms", return_value=sample_vms),
            patch("azlin.multi_context_list.VMManager.filter_by_prefix", return_value=sample_vms),
            patch(
                "azlin.multi_context_list.VMManager.sort_by_created_time", return_value=sample_vms
            ),
        ):
            result = query_executor._query_single_context(
                context=context,
                resource_group="azlin-rg",
                include_stopped=True,
                filter_prefix="azlin",
            )

            assert result.duration > 0


# =============================================================================
# TESTS: Subscription Switching
# =============================================================================


class TestSubscriptionSwitching:
    """Test Azure subscription switching."""

    def test_switch_subscription_success(self, query_executor):
        """Test successful subscription switch."""
        context = query_executor.contexts[0]

        with patch("azlin.multi_context_list.subprocess.run") as mock_run:
            query_executor._switch_subscription(context)
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "az" in call_args
            assert "account" in call_args
            assert "set" in call_args
            assert context.subscription_id in call_args

    def test_switch_subscription_failure(self, query_executor):
        """Test subscription switch failure."""
        import subprocess

        context = query_executor.contexts[0]

        with patch(
            "azlin.multi_context_list.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "az", stderr="failed"),
        ):
            with pytest.raises(MultiContextQueryError):
                query_executor._switch_subscription(context)

    def test_switch_subscription_timeout(self, query_executor):
        """Test subscription switch timeout."""
        import subprocess

        context = query_executor.contexts[0]

        with patch(
            "azlin.multi_context_list.subprocess.run",
            side_effect=subprocess.TimeoutExpired("az", 10),
        ):
            with pytest.raises(MultiContextQueryError, match="timed out"):
                query_executor._switch_subscription(context)


# =============================================================================
# TESTS: Multi-Context Query Results
# =============================================================================


class TestContextVMResult:
    """Test ContextVMResult dataclass."""

    def test_context_vm_result_success(self, sample_vms):
        """Test successful context result."""
        result = ContextVMResult(
            context_name="production",
            context=Mock(),
            success=True,
            vms=sample_vms,
            duration=1.5,
        )

        assert result.vm_count == 3
        assert result.running_count == 2
        assert result.stopped_count == 1
        assert result.error_message is None

    def test_context_vm_result_failure(self):
        """Test failed context result."""
        result = ContextVMResult(
            context_name="production",
            context=Mock(),
            success=False,
            error_message="Connection failed",
            duration=0.5,
        )

        assert result.vm_count == 0
        assert result.running_count == 0
        assert result.stopped_count == 0
        assert result.error_message == "Connection failed"

    def test_context_vm_result_empty_vms(self):
        """Test context result with no VMs."""
        result = ContextVMResult(
            context_name="production",
            context=Mock(),
            success=True,
            vms=[],
            duration=1.0,
        )

        assert result.vm_count == 0
        assert result.running_count == 0
        assert result.stopped_count == 0


class TestMultiContextVMResult:
    """Test MultiContextVMResult aggregation."""

    def test_aggregate_results_all_success(self, sample_vms):
        """Test aggregating all successful results."""
        # sample_vms has 2 running and 1 stopped
        results = [
            ContextVMResult(
                context_name="production",
                context=Mock(),
                success=True,
                vms=sample_vms[:2],  # 2 running
                duration=1.0,
            ),
            ContextVMResult(
                context_name="staging",
                context=Mock(),
                success=True,
                vms=sample_vms[2:],  # 1 stopped
                duration=0.8,
            ),
        ]

        aggregate = MultiContextVMResult(context_results=results, total_duration=2.0)

        assert aggregate.total_vms == 3
        assert aggregate.total_running == 2  # Both from first result (2 running)
        assert aggregate.total_stopped == 1  # From second result (1 stopped)
        assert aggregate.successful_contexts == 2
        assert aggregate.failed_contexts == 0
        assert aggregate.all_succeeded is True

    def test_aggregate_results_mixed_success(self, sample_vms):
        """Test aggregating mixed success/failure results."""
        results = [
            ContextVMResult(
                context_name="production",
                context=Mock(),
                success=True,
                vms=sample_vms,
                duration=1.0,
            ),
            ContextVMResult(
                context_name="staging",
                context=Mock(),
                success=False,
                error_message="Connection failed",
                duration=0.5,
            ),
        ]

        aggregate = MultiContextVMResult(context_results=results, total_duration=1.5)

        assert aggregate.total_vms == 3
        assert aggregate.successful_contexts == 1
        assert aggregate.failed_contexts == 1
        assert aggregate.all_succeeded is False

    def test_aggregate_results_all_failed(self):
        """Test aggregating all failed results."""
        results = [
            ContextVMResult(
                context_name="production",
                context=Mock(),
                success=False,
                error_message="Error 1",
                duration=0.5,
            ),
            ContextVMResult(
                context_name="staging",
                context=Mock(),
                success=False,
                error_message="Error 2",
                duration=0.5,
            ),
        ]

        aggregate = MultiContextVMResult(context_results=results, total_duration=1.0)

        assert aggregate.total_vms == 0
        assert aggregate.successful_contexts == 0
        assert aggregate.failed_contexts == 2
        assert aggregate.all_succeeded is False

    def test_get_failures(self, sample_vms):
        """Test retrieving only failed results."""
        results = [
            ContextVMResult(
                context_name="production",
                context=Mock(),
                success=True,
                vms=sample_vms,
                duration=1.0,
            ),
            ContextVMResult(
                context_name="staging",
                context=Mock(),
                success=False,
                error_message="Error",
                duration=0.5,
            ),
        ]

        aggregate = MultiContextVMResult(context_results=results)
        failures = aggregate.get_failures()

        assert len(failures) == 1
        assert failures[0].context_name == "staging"

    def test_get_successes(self, sample_vms):
        """Test retrieving only successful results."""
        results = [
            ContextVMResult(
                context_name="production",
                context=Mock(),
                success=True,
                vms=sample_vms,
                duration=1.0,
            ),
            ContextVMResult(
                context_name="staging",
                context=Mock(),
                success=False,
                error_message="Error",
                duration=0.5,
            ),
        ]

        aggregate = MultiContextVMResult(context_results=results)
        successes = aggregate.get_successes()

        assert len(successes) == 1
        assert successes[0].context_name == "production"


# =============================================================================
# TESTS: Parallel Execution
# =============================================================================


class TestParallelExecution:
    """Test parallel query execution."""

    def test_query_all_contexts_success(self, query_executor, sample_vms):
        """Test successful query of all contexts."""
        with patch.object(query_executor, "_query_single_context") as mock_query:
            # Create mock results
            mock_query.side_effect = [
                ContextVMResult(
                    context_name="production",
                    context=query_executor.contexts[0],
                    success=True,
                    vms=sample_vms,
                    duration=1.0,
                ),
                ContextVMResult(
                    context_name="staging",
                    context=query_executor.contexts[1],
                    success=True,
                    vms=sample_vms,
                    duration=0.9,
                ),
                ContextVMResult(
                    context_name="development",
                    context=query_executor.contexts[2],
                    success=True,
                    vms=sample_vms,
                    duration=0.8,
                ),
            ]

            result = query_executor.query_all_contexts(resource_group="azlin-rg")

            assert result.total_vms == 9  # 3 VMs * 3 contexts
            assert result.successful_contexts == 3
            assert result.failed_contexts == 0
            assert result.all_succeeded is True
            assert mock_query.call_count == 3

    def test_query_all_contexts_partial_failure(self, query_executor, sample_vms):
        """Test query with some failures."""
        with patch.object(query_executor, "_query_single_context") as mock_query:
            mock_query.side_effect = [
                ContextVMResult(
                    context_name="production",
                    context=query_executor.contexts[0],
                    success=True,
                    vms=sample_vms,
                    duration=1.0,
                ),
                ContextVMResult(
                    context_name="staging",
                    context=query_executor.contexts[1],
                    success=False,
                    error_message="Connection failed",
                    duration=0.5,
                ),
                ContextVMResult(
                    context_name="development",
                    context=query_executor.contexts[2],
                    success=True,
                    vms=sample_vms[:1],
                    duration=0.8,
                ),
            ]

            result = query_executor.query_all_contexts(resource_group="azlin-rg")

            assert result.total_vms == 4  # 3 + 0 + 1
            assert result.successful_contexts == 2
            assert result.failed_contexts == 1
            assert result.all_succeeded is False

    def test_query_results_are_sorted_by_context_name(self, query_executor, sample_vms):
        """Test that results are sorted by context name."""
        # Reverse order of contexts to test sorting
        unsorted_contexts = list(reversed(query_executor.contexts))
        query_executor.contexts = unsorted_contexts

        with patch.object(query_executor, "_query_single_context") as mock_query:
            # Return results in reverse order
            mock_query.side_effect = [
                ContextVMResult(
                    context_name="development",
                    context=unsorted_contexts[0],
                    success=True,
                    vms=[],
                    duration=1.0,
                ),
                ContextVMResult(
                    context_name="staging",
                    context=unsorted_contexts[1],
                    success=True,
                    vms=[],
                    duration=1.0,
                ),
                ContextVMResult(
                    context_name="production",
                    context=unsorted_contexts[2],
                    success=True,
                    vms=[],
                    duration=1.0,
                ),
            ]

            result = query_executor.query_all_contexts(resource_group="azlin-rg")

            names = [r.context_name for r in result.context_results]
            assert names == ["development", "production", "staging"]  # Sorted order


# =============================================================================
# TESTS: Query Parameters
# =============================================================================


class TestQueryParameters:
    """Test various query parameters."""

    def test_query_with_resource_group(self, query_executor):
        """Test query with specific resource group."""
        with patch.object(query_executor, "_query_single_context") as mock_query:
            mock_query.return_value = ContextVMResult(
                context_name="production",
                context=query_executor.contexts[0],
                success=True,
                vms=[],
                duration=1.0,
            )

            query_executor.query_all_contexts(resource_group="custom-rg")

            # Verify resource_group was passed as positional arg (2nd arg after context)
            call_args = mock_query.call_args_list[0][0]
            # Args are: context, resource_group, include_stopped, filter_prefix
            assert call_args[1] == "custom-rg"

    def test_query_include_stopped_false(self, query_executor):
        """Test query excluding stopped VMs."""
        with patch.object(query_executor, "_query_single_context") as mock_query:
            mock_query.return_value = ContextVMResult(
                context_name="production",
                context=query_executor.contexts[0],
                success=True,
                vms=[],
                duration=1.0,
            )

            query_executor.query_all_contexts(resource_group="azlin-rg", include_stopped=False)

            # Args are: context, resource_group, include_stopped, filter_prefix
            call_args = mock_query.call_args_list[0][0]
            assert call_args[2] is False

    def test_query_with_custom_filter_prefix(self, query_executor):
        """Test query with custom VM name prefix filter."""
        with patch.object(query_executor, "_query_single_context") as mock_query:
            mock_query.return_value = ContextVMResult(
                context_name="production",
                context=query_executor.contexts[0],
                success=True,
                vms=[],
                duration=1.0,
            )

            query_executor.query_all_contexts(resource_group="azlin-rg", filter_prefix="custom")

            # Args are: context, resource_group, include_stopped, filter_prefix
            call_args = mock_query.call_args_list[0][0]
            assert call_args[3] == "custom"


# =============================================================================
# TESTS: Error Aggregation
# =============================================================================


class TestErrorAggregation:
    """Test error handling and aggregation."""

    def test_single_context_error_doesnt_break_others(self, query_executor, sample_vms):
        """Test that error in one context doesn't affect others."""
        with patch.object(query_executor, "_query_single_context") as mock_query:
            mock_query.side_effect = [
                ContextVMResult(
                    context_name="production",
                    context=query_executor.contexts[0],
                    success=True,
                    vms=sample_vms,
                    duration=1.0,
                ),
                ContextVMResult(
                    context_name="staging",
                    context=query_executor.contexts[1],
                    success=False,
                    error_message="Auth error",
                    duration=0.5,
                ),
                ContextVMResult(
                    context_name="development",
                    context=query_executor.contexts[2],
                    success=True,
                    vms=sample_vms,
                    duration=1.0,
                ),
            ]

            result = query_executor.query_all_contexts(resource_group="azlin-rg")

            # Verify all contexts were processed
            assert len(result.context_results) == 3
            failures = result.get_failures()
            assert len(failures) == 1
            assert failures[0].context_name == "staging"

    def test_error_message_preserved(self, query_executor):
        """Test that error messages are preserved."""
        error_msg = "Connection timeout: failed to authenticate"

        with patch.object(query_executor, "_query_single_context") as mock_query:
            mock_query.return_value = ContextVMResult(
                context_name="production",
                context=query_executor.contexts[0],
                success=False,
                error_message=error_msg,
                duration=1.0,
            )

            result = query_executor.query_all_contexts(resource_group="azlin-rg")

            assert result.context_results[0].error_message == error_msg
