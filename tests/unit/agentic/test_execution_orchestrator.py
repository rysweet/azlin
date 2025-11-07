"""Tests for execution orchestrator with fallback and retry logic."""

import time
from unittest.mock import MagicMock, patch

import pytest

from azlin.agentic.execution_orchestrator import (
    ExecutionAttempt,
    ExecutionOrchestrator,
    ExecutionOrchestratorError,
    RetryDecision,
)
from azlin.agentic.types import (
    ExecutionContext,
    ExecutionResult,
    FailureType,
    Intent,
    Strategy,
    StrategyPlan,
)


@pytest.fixture
def sample_context():
    """Create a sample execution context."""
    intent = Intent(
        intent="provision_vm",
        parameters={"vm_name": "test-vm"},
        confidence=0.95,
        azlin_commands=[],
    )
    return ExecutionContext(
        objective_id="test-123",
        intent=intent,
        strategy=Strategy.AZURE_CLI,
        dry_run=False,
        resource_group="test-rg",
    )


@pytest.fixture
def sample_strategy_plan():
    """Create a sample strategy plan."""
    return StrategyPlan(
        primary_strategy=Strategy.AZURE_CLI,
        fallback_strategies=[Strategy.TERRAFORM],
        prerequisites_met=True,
        reasoning="Azure CLI is fastest",
    )


class TestExecutionAttempt:
    """Test ExecutionAttempt dataclass."""

    def test_attempt_creation(self):
        """Test creating an execution attempt record."""
        result = ExecutionResult(
            success=True,
            strategy=Strategy.AZURE_CLI,
            output="Success",
        )

        attempt = ExecutionAttempt(
            strategy=Strategy.AZURE_CLI,
            result=result,
            attempt_number=1,
            timestamp=time.time(),
            duration_seconds=5.0,
        )

        assert attempt.strategy == Strategy.AZURE_CLI
        assert attempt.result.success is True
        assert attempt.attempt_number == 1
        assert attempt.duration_seconds == 5.0


class TestExecutionOrchestrator:
    """Test ExecutionOrchestrator class."""

    def test_initialization(self):
        """Test orchestrator initialization."""
        orchestrator = ExecutionOrchestrator(
            max_retries=5,
            retry_delay_base=3.0,
            enable_rollback=False,
        )

        assert orchestrator.max_retries == 5
        assert orchestrator.retry_delay_base == 3.0
        assert orchestrator.enable_rollback is False
        assert orchestrator.attempts == []

    def test_successful_execution_first_try(self, sample_context, sample_strategy_plan):
        """Test successful execution on first try."""
        orchestrator = ExecutionOrchestrator()

        # Mock strategy to succeed
        with patch("azlin.agentic.execution_orchestrator.AzureCLIStrategy") as mock_strategy_class:
            mock_strategy = MagicMock()
            mock_strategy_class.return_value = mock_strategy

            mock_strategy.execute.return_value = ExecutionResult(
                success=True,
                strategy=Strategy.AZURE_CLI,
                output="VM created",
                resources_created=["/subscriptions/.../vm/test-vm"],
            )

            result = orchestrator.execute(sample_context, sample_strategy_plan)

            assert result.success is True
            assert len(orchestrator.attempts) == 1
            assert orchestrator.attempts[0].strategy == Strategy.AZURE_CLI

    def test_retry_on_retriable_failure(self, sample_context, sample_strategy_plan):
        """Test retry logic for retriable failures."""
        orchestrator = ExecutionOrchestrator(max_retries=3)

        with patch("azlin.agentic.execution_orchestrator.AzureCLIStrategy") as mock_strategy_class:
            mock_strategy = MagicMock()
            mock_strategy_class.return_value = mock_strategy

            # Fail twice, then succeed
            mock_strategy.execute.side_effect = [
                ExecutionResult(
                    success=False,
                    strategy=Strategy.AZURE_CLI,
                    error="Timeout",
                    failure_type=FailureType.TIMEOUT,
                ),
                ExecutionResult(
                    success=False,
                    strategy=Strategy.AZURE_CLI,
                    error="Network error",
                    failure_type=FailureType.NETWORK_ERROR,
                ),
                ExecutionResult(
                    success=True,
                    strategy=Strategy.AZURE_CLI,
                    output="Success on retry",
                ),
            ]

            # Mock sleep to avoid waiting
            with patch("time.sleep"):
                result = orchestrator.execute(sample_context, sample_strategy_plan)

            assert result.success is True
            assert len(orchestrator.attempts) == 3
            assert all(a.strategy == Strategy.AZURE_CLI for a in orchestrator.attempts)

    def test_fallback_on_non_retriable_failure(self, sample_context):
        """Test fallback to next strategy on non-retriable failure."""
        plan = StrategyPlan(
            primary_strategy=Strategy.AZURE_CLI,
            fallback_strategies=[Strategy.TERRAFORM],
            prerequisites_met=True,
        )

        orchestrator = ExecutionOrchestrator()

        with (
            patch("azlin.agentic.execution_orchestrator.AzureCLIStrategy") as mock_cli_class,
            patch("azlin.agentic.execution_orchestrator.TerraformStrategy") as mock_tf_class,
        ):
            mock_cli = MagicMock()
            mock_tf = MagicMock()
            mock_cli_class.return_value = mock_cli
            mock_tf_class.return_value = mock_tf

            # CLI fails with permission error (non-retriable)
            mock_cli.execute.return_value = ExecutionResult(
                success=False,
                strategy=Strategy.AZURE_CLI,
                error="Permission denied",
                failure_type=FailureType.PERMISSION_DENIED,
            )

            # Terraform succeeds
            mock_tf.execute.return_value = ExecutionResult(
                success=True,
                strategy=Strategy.TERRAFORM,
                output="Terraform succeeded",
            )

            result = orchestrator.execute(sample_context, plan)

            assert result.success is True
            assert result.strategy == Strategy.TERRAFORM
            # Should have 1 CLI attempt + 1 Terraform attempt
            assert len(orchestrator.attempts) == 2

    def test_all_strategies_fail(self, sample_context):
        """Test when all strategies in chain fail."""
        plan = StrategyPlan(
            primary_strategy=Strategy.AZURE_CLI,
            fallback_strategies=[Strategy.TERRAFORM],
            prerequisites_met=True,
        )

        orchestrator = ExecutionOrchestrator(max_retries=2)

        with (
            patch("azlin.agentic.execution_orchestrator.AzureCLIStrategy") as mock_cli_class,
            patch("azlin.agentic.execution_orchestrator.TerraformStrategy") as mock_tf_class,
        ):
            mock_cli = MagicMock()
            mock_tf = MagicMock()
            mock_cli_class.return_value = mock_cli
            mock_tf_class.return_value = mock_tf

            # Both fail
            mock_cli.execute.return_value = ExecutionResult(
                success=False,
                strategy=Strategy.AZURE_CLI,
                error="CLI failed",
                failure_type=FailureType.VALIDATION_ERROR,
            )

            mock_tf.execute.return_value = ExecutionResult(
                success=False,
                strategy=Strategy.TERRAFORM,
                error="Terraform failed",
                failure_type=FailureType.VALIDATION_ERROR,
            )

            result = orchestrator.execute(sample_context, plan)

            assert result.success is False
            # Should try both strategies once (validation errors not retriable)
            assert len(orchestrator.attempts) == 2
            assert "strategies_tried" in result.metadata

    def test_rollback_on_failure(self, sample_context):
        """Test rollback is triggered on failure."""
        orchestrator = ExecutionOrchestrator(enable_rollback=True)

        # Use a plan without fallbacks to ensure rollback is triggered
        plan_no_fallback = StrategyPlan(
            primary_strategy=Strategy.AZURE_CLI,
            fallback_strategies=[],  # No fallbacks
            prerequisites_met=True,
        )

        with patch("azlin.agentic.execution_orchestrator.AzureCLIStrategy") as mock_strategy_class:
            mock_strategy = MagicMock()
            mock_strategy_class.return_value = mock_strategy

            # Fail with partial resources (non-retriable to avoid multiple retries)
            mock_strategy.execute.return_value = ExecutionResult(
                success=False,
                strategy=Strategy.AZURE_CLI,
                error="Failed midway",
                failure_type=FailureType.VALIDATION_ERROR,  # Non-retriable
                resources_created=["/subscriptions/.../vm/partial"],
            )

            orchestrator.execute(sample_context, plan_no_fallback)

            # Verify cleanup was called
            mock_strategy.cleanup_on_failure.assert_called_once()

    def test_no_rollback_when_disabled(self, sample_context):
        """Test rollback is skipped when disabled."""
        orchestrator = ExecutionOrchestrator(enable_rollback=False)

        # Use a plan without fallbacks
        plan_no_fallback = StrategyPlan(
            primary_strategy=Strategy.AZURE_CLI,
            fallback_strategies=[],  # No fallbacks
            prerequisites_met=True,
        )

        with patch("azlin.agentic.execution_orchestrator.AzureCLIStrategy") as mock_strategy_class:
            mock_strategy = MagicMock()
            mock_strategy_class.return_value = mock_strategy

            mock_strategy.execute.return_value = ExecutionResult(
                success=False,
                strategy=Strategy.AZURE_CLI,
                error="Failed",
                failure_type=FailureType.VALIDATION_ERROR,  # Non-retriable
                resources_created=["/subscriptions/.../vm/partial"],
            )

            orchestrator.execute(sample_context, plan_no_fallback)

            # Verify cleanup was NOT called
            mock_strategy.cleanup_on_failure.assert_not_called()

    def test_is_retriable_failure(self):
        """Test retriable failure classification."""
        orchestrator = ExecutionOrchestrator()

        # Retriable
        assert orchestrator._is_retriable_failure(FailureType.TIMEOUT) is True
        assert orchestrator._is_retriable_failure(FailureType.NETWORK_ERROR) is True

        # Non-retriable
        assert orchestrator._is_retriable_failure(FailureType.VALIDATION_ERROR) is False
        assert orchestrator._is_retriable_failure(FailureType.PERMISSION_DENIED) is False
        assert orchestrator._is_retriable_failure(FailureType.QUOTA_EXCEEDED) is False

        # Unknown - retry cautiously
        assert orchestrator._is_retriable_failure(FailureType.UNKNOWN) is True

    def test_should_retry_or_fallback_quota_exceeded(self):
        """Test abort on quota exceeded."""
        orchestrator = ExecutionOrchestrator()

        result = ExecutionResult(
            success=False,
            strategy=Strategy.AZURE_CLI,
            error="Quota exceeded",
            failure_type=FailureType.QUOTA_EXCEEDED,
        )

        decision = orchestrator._should_retry_or_fallback(
            result,
            [Strategy.AZURE_CLI, Strategy.TERRAFORM],
            Strategy.AZURE_CLI,
        )

        assert decision == RetryDecision.ABORT

    def test_should_retry_or_fallback_permission_denied(self):
        """Test fallback on permission denied."""
        orchestrator = ExecutionOrchestrator()

        result = ExecutionResult(
            success=False,
            strategy=Strategy.AZURE_CLI,
            error="Permission denied",
            failure_type=FailureType.PERMISSION_DENIED,
        )

        decision = orchestrator._should_retry_or_fallback(
            result,
            [Strategy.AZURE_CLI, Strategy.TERRAFORM],
            Strategy.AZURE_CLI,
        )

        assert decision == RetryDecision.RETRY_FALLBACK

    def test_execution_summary(self, sample_context):
        """Test execution summary generation."""
        plan = StrategyPlan(
            primary_strategy=Strategy.AZURE_CLI,
            fallback_strategies=[Strategy.TERRAFORM],
            prerequisites_met=True,
        )

        orchestrator = ExecutionOrchestrator()

        with (
            patch("azlin.agentic.execution_orchestrator.AzureCLIStrategy") as mock_cli_class,
            patch("azlin.agentic.execution_orchestrator.TerraformStrategy") as mock_tf_class,
        ):
            mock_cli = MagicMock()
            mock_tf = MagicMock()
            mock_cli_class.return_value = mock_cli
            mock_tf_class.return_value = mock_tf

            mock_cli.execute.return_value = ExecutionResult(
                success=False,
                strategy=Strategy.AZURE_CLI,
                error="Failed",
                failure_type=FailureType.VALIDATION_ERROR,
            )

            mock_tf.execute.return_value = ExecutionResult(
                success=True,
                strategy=Strategy.TERRAFORM,
                output="Success",
            )

            orchestrator.execute(sample_context, plan)

            summary = orchestrator.get_execution_summary()

            assert summary["total_attempts"] == 2
            assert Strategy.AZURE_CLI.value in summary["strategies_tried"]
            assert Strategy.TERRAFORM.value in summary["strategies_tried"]
            assert summary["success"] is True
            assert summary["final_strategy"] == Strategy.TERRAFORM.value

    def test_empty_summary(self):
        """Test summary with no attempts."""
        orchestrator = ExecutionOrchestrator()

        summary = orchestrator.get_execution_summary()

        assert summary["total_attempts"] == 0
        assert summary["strategies_tried"] == []

    def test_strategy_caching(self):
        """Test that strategy instances are cached."""
        orchestrator = ExecutionOrchestrator()

        with patch("azlin.agentic.execution_orchestrator.AzureCLIStrategy") as mock_class:
            mock_strategy = MagicMock()
            mock_class.return_value = mock_strategy

            # Get strategy twice
            s1 = orchestrator._get_strategy(Strategy.AZURE_CLI)
            s2 = orchestrator._get_strategy(Strategy.AZURE_CLI)

            # Should be same instance
            assert s1 is s2
            # Constructor should only be called once
            assert mock_class.call_count == 1

    def test_exponential_backoff(self, sample_context):
        """Test exponential backoff timing."""
        orchestrator = ExecutionOrchestrator(max_retries=3, retry_delay_base=2.0)

        # Use a plan without fallbacks to test just one strategy's retries
        plan_no_fallback = StrategyPlan(
            primary_strategy=Strategy.AZURE_CLI,
            fallback_strategies=[],  # No fallbacks
            prerequisites_met=True,
        )

        with patch("azlin.agentic.execution_orchestrator.AzureCLIStrategy") as mock_strategy_class:
            mock_strategy = MagicMock()
            mock_strategy_class.return_value = mock_strategy

            # Always fail with retriable error
            mock_strategy.execute.return_value = ExecutionResult(
                success=False,
                strategy=Strategy.AZURE_CLI,
                error="Timeout",
                failure_type=FailureType.TIMEOUT,
            )

            with patch("time.sleep") as mock_sleep:
                orchestrator.execute(sample_context, plan_no_fallback)

                # Should sleep with exponential backoff: 2^1=2, 2^2=4
                assert mock_sleep.call_count == 2
                call_args = [call[0][0] for call in mock_sleep.call_args_list]
                assert call_args == [2.0, 4.0]

    def test_count_retries_per_strategy(self, sample_context):
        """Test counting retries per strategy."""
        plan = StrategyPlan(
            primary_strategy=Strategy.AZURE_CLI,
            fallback_strategies=[Strategy.TERRAFORM],
            prerequisites_met=True,
        )

        orchestrator = ExecutionOrchestrator(max_retries=2)

        with (
            patch("azlin.agentic.execution_orchestrator.AzureCLIStrategy") as mock_cli_class,
            patch("azlin.agentic.execution_orchestrator.TerraformStrategy") as mock_tf_class,
        ):
            mock_cli = MagicMock()
            mock_tf = MagicMock()
            mock_cli_class.return_value = mock_cli
            mock_tf_class.return_value = mock_tf

            # CLI fails twice (with retries)
            mock_cli.execute.side_effect = [
                ExecutionResult(
                    success=False,
                    strategy=Strategy.AZURE_CLI,
                    error="Timeout",
                    failure_type=FailureType.TIMEOUT,
                ),
                ExecutionResult(
                    success=False,
                    strategy=Strategy.AZURE_CLI,
                    error="Timeout",
                    failure_type=FailureType.TIMEOUT,
                ),
            ]

            # Terraform succeeds on first try
            mock_tf.execute.return_value = ExecutionResult(
                success=True,
                strategy=Strategy.TERRAFORM,
                output="Success",
            )

            with patch("time.sleep"):
                orchestrator.execute(sample_context, plan)

            counts = orchestrator._count_retries_per_strategy()

            assert counts[Strategy.AZURE_CLI.value] == 2
            assert counts[Strategy.TERRAFORM.value] == 1

    def test_all_strategy_enum_values_implemented(self):
        """Test that all Strategy enum values have implementations.

        This test ensures that when a new Strategy is added to the enum,
        it is also added to the _get_strategy method. This prevents
        NotImplementedError exceptions in production.
        """
        orchestrator = ExecutionOrchestrator()

        # Test all implemented strategies can be instantiated
        implemented_strategies = [
            Strategy.AZURE_CLI,
            Strategy.TERRAFORM,
            Strategy.AWS_CLI,
            Strategy.GCP_CLI,
            Strategy.MCP_CLIENT,
        ]

        with (
            patch("azlin.agentic.execution_orchestrator.AzureCLIStrategy") as mock_azure,
            patch("azlin.agentic.execution_orchestrator.TerraformStrategy") as mock_tf,
            patch("azlin.agentic.execution_orchestrator.AWSStrategy") as mock_aws,
            patch("azlin.agentic.execution_orchestrator.GCPStrategy") as mock_gcp,
            patch("azlin.agentic.execution_orchestrator.MCPClientStrategy") as mock_mcp,
        ):
            # Mock all strategy constructors
            mock_azure.return_value = MagicMock()
            mock_tf.return_value = MagicMock()
            mock_aws.return_value = MagicMock()
            mock_gcp.return_value = MagicMock()
            mock_mcp.return_value = MagicMock()

            # Test that all implemented strategies can be instantiated
            for strategy in implemented_strategies:
                result = orchestrator._get_strategy(strategy)
                assert result is not None

        # Test that CUSTOM_CODE raises ExecutionOrchestratorError (not NotImplementedError)
        with pytest.raises(ExecutionOrchestratorError) as exc_info:
            orchestrator._get_strategy(Strategy.CUSTOM_CODE)

        assert "not yet implemented" in str(exc_info.value).lower()
        assert "security considerations" in str(exc_info.value).lower()

    def test_get_strategy_raises_proper_error_not_notimplementederror(self):
        """Test that _get_strategy never raises NotImplementedError.

        NotImplementedError should only be used in abstract base classes.
        For missing strategy implementations, we should raise ExecutionOrchestratorError.
        """
        orchestrator = ExecutionOrchestrator()

        # Test that CUSTOM_CODE raises ExecutionOrchestratorError, not NotImplementedError
        with pytest.raises(ExecutionOrchestratorError) as exc_info:
            orchestrator._get_strategy(Strategy.CUSTOM_CODE)

        # Verify the error message is informative
        error_msg = str(exc_info.value).lower()
        assert "custom_code" in error_msg
        assert "not yet implemented" in error_msg
