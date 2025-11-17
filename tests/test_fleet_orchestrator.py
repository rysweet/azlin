"""Tests for FleetOrchestrator and WorkflowOrchestrator.

Tests workflow orchestration, dependency chains, YAML loading, and result diffs.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from azlin.batch_executor import BatchOperationResult, VMMetrics
from azlin.fleet_orchestrator import (
    FleetOrchestratorError,
    ResultDiffGenerator,
    WorkflowOrchestrator,
    WorkflowResult,
    WorkflowStep,
)
from azlin.vm_manager import VMInfo


class TestWorkflowStep:
    """Unit tests for WorkflowStep dataclass."""

    def test_workflow_step_creation(self):
        """Test creating a workflow step."""
        step = WorkflowStep(
            name="test-step",
            command="echo hello",
            condition="idle",
            depends_on=["step1"],
            parallel=True,
            retry_on_failure=True,
        )

        assert step.name == "test-step"
        assert step.command == "echo hello"
        assert step.condition == "idle"
        assert step.depends_on == ["step1"]
        assert step.parallel is True
        assert step.retry_on_failure is True

    def test_workflow_step_defaults(self):
        """Test workflow step with default values."""
        step = WorkflowStep(name="simple", command="ls")

        assert step.condition is None
        assert step.depends_on == []
        assert step.parallel is True
        assert step.retry_on_failure is False
        assert step.continue_on_error is False


class TestYAMLWorkflowLoading:
    """Integration tests for YAML workflow loading."""

    def test_load_valid_workflow(self):
        """Test loading a valid YAML workflow."""
        yaml_content = """
steps:
  - name: step1
    command: "echo hello"
    condition: idle
    parallel: true
  - name: step2
    command: "echo world"
    depends_on: [step1]
    retry_on_failure: true
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            workflow_file = Path(f.name)

        try:
            orchestrator = WorkflowOrchestrator()
            steps = orchestrator.load_workflow(workflow_file)

            assert len(steps) == 2
            assert steps[0].name == "step1"
            assert steps[0].command == "echo hello"
            assert steps[0].condition == "idle"
            assert steps[1].name == "step2"
            assert steps[1].depends_on == ["step1"]
            assert steps[1].retry_on_failure is True
        finally:
            workflow_file.unlink()

    def test_load_workflow_file_not_found(self):
        """Test loading non-existent workflow file."""
        orchestrator = WorkflowOrchestrator()

        with pytest.raises(FleetOrchestratorError, match="not found"):
            orchestrator.load_workflow(Path("/nonexistent/file.yaml"))

    def test_load_invalid_yaml(self):
        """Test loading invalid YAML."""
        yaml_content = "invalid: yaml: content: ["

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            workflow_file = Path(f.name)

        try:
            orchestrator = WorkflowOrchestrator()

            with pytest.raises(FleetOrchestratorError, match="parse YAML"):
                orchestrator.load_workflow(workflow_file)
        finally:
            workflow_file.unlink()

    def test_load_workflow_missing_steps(self):
        """Test loading workflow without 'steps' key."""
        yaml_content = """
invalid_key:
  - name: step1
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            workflow_file = Path(f.name)

        try:
            orchestrator = WorkflowOrchestrator()

            with pytest.raises(FleetOrchestratorError, match="steps"):
                orchestrator.load_workflow(workflow_file)
        finally:
            workflow_file.unlink()

    def test_load_workflow_missing_required_fields(self):
        """Test loading workflow with missing required fields."""
        yaml_content = """
steps:
  - name: step1
    # Missing 'command' field
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            workflow_file = Path(f.name)

        try:
            orchestrator = WorkflowOrchestrator()

            with pytest.raises(FleetOrchestratorError, match="name.*command"):
                orchestrator.load_workflow(workflow_file)
        finally:
            workflow_file.unlink()


class TestVMRouting:
    """Tests for smart VM routing by load."""

    def test_route_vms_by_load(self):
        """Test routing VMs by load (least loaded first)."""
        vm1 = Mock(spec=VMInfo)
        vm1.name = "high-load"

        vm2 = Mock(spec=VMInfo)
        vm2.name = "low-load"

        vm3 = Mock(spec=VMInfo)
        vm3.name = "medium-load"

        vms = [vm1, vm2, vm3]

        metrics = {
            "high-load": VMMetrics(
                vm_name="high-load",
                load_avg=(3.0, 3.1, 3.2),
                cpu_percent=80.0,
                memory_percent=70.0,
                is_idle=False,
                success=True,
            ),
            "low-load": VMMetrics(
                vm_name="low-load",
                load_avg=(0.2, 0.3, 0.4),
                cpu_percent=10.0,
                memory_percent=30.0,
                is_idle=False,
                success=True,
            ),
            "medium-load": VMMetrics(
                vm_name="medium-load",
                load_avg=(1.5, 1.6, 1.7),
                cpu_percent=50.0,
                memory_percent=50.0,
                is_idle=False,
                success=True,
            ),
        }

        orchestrator = WorkflowOrchestrator()
        routed_vms = orchestrator.route_vms_by_load(vms, metrics)

        # Should be ordered: low-load, medium-load, high-load
        assert len(routed_vms) == 3
        assert routed_vms[0].name == "low-load"
        assert routed_vms[1].name == "medium-load"
        assert routed_vms[2].name == "high-load"

    def test_route_vms_with_count_limit(self):
        """Test routing with count limit."""
        vm1 = Mock(spec=VMInfo)
        vm1.name = "vm1"

        vm2 = Mock(spec=VMInfo)
        vm2.name = "vm2"

        vm3 = Mock(spec=VMInfo)
        vm3.name = "vm3"

        vms = [vm1, vm2, vm3]

        metrics = {
            "vm1": VMMetrics(
                vm_name="vm1",
                load_avg=(2.0, 2.0, 2.0),
                cpu_percent=50.0,
                memory_percent=50.0,
                is_idle=False,
                success=True,
            ),
            "vm2": VMMetrics(
                vm_name="vm2",
                load_avg=(0.5, 0.5, 0.5),
                cpu_percent=10.0,
                memory_percent=20.0,
                is_idle=False,
                success=True,
            ),
            "vm3": VMMetrics(
                vm_name="vm3",
                load_avg=(1.0, 1.0, 1.0),
                cpu_percent=30.0,
                memory_percent=40.0,
                is_idle=False,
                success=True,
            ),
        }

        orchestrator = WorkflowOrchestrator()
        routed_vms = orchestrator.route_vms_by_load(vms, metrics, count=2)

        # Should return only 2 VMs: vm2, vm3
        assert len(routed_vms) == 2
        assert routed_vms[0].name == "vm2"
        assert routed_vms[1].name == "vm3"


class TestWorkflowExecution:
    """Integration tests for workflow execution with dependencies."""

    @patch("azlin.fleet_orchestrator.WorkflowOrchestrator._execute_step")
    def test_execute_simple_workflow(self, mock_execute_step):
        """Test executing simple workflow without dependencies."""
        step1 = WorkflowStep(name="step1", command="echo hello")
        step2 = WorkflowStep(name="step2", command="echo world")

        # Mock successful execution
        def mock_execute_side_effect(step, vms, rg, callback):
            return WorkflowResult(
                step_name=step.name,
                success=True,
                results=[],
            )

        mock_execute_step.side_effect = mock_execute_side_effect

        orchestrator = WorkflowOrchestrator()
        results = orchestrator.execute_workflow([step1, step2], [], "test-rg")

        assert len(results) == 2
        assert all(r.success for r in results)

    @patch("azlin.fleet_orchestrator.WorkflowOrchestrator._execute_step")
    def test_execute_workflow_with_dependencies(self, mock_execute_step):
        """Test executing workflow with dependencies."""
        step1 = WorkflowStep(name="step1", command="echo first")
        step2 = WorkflowStep(
            name="step2",
            command="echo second",
            depends_on=["step1"],
        )

        executed_order = []

        def mock_execute_side_effect(step, vms, rg, callback):
            executed_order.append(step.name)
            return WorkflowResult(
                step_name=step.name,
                success=True,
                results=[],
            )

        mock_execute_step.side_effect = mock_execute_side_effect

        orchestrator = WorkflowOrchestrator()
        results = orchestrator.execute_workflow([step2, step1], [], "test-rg")

        # step1 should execute before step2 despite order in list
        assert executed_order == ["step1", "step2"]

    @patch("azlin.fleet_orchestrator.WorkflowOrchestrator._execute_step")
    def test_execute_workflow_failure_stops_execution(self, mock_execute_step):
        """Test that workflow stops when step fails and continue_on_error=False."""
        step1 = WorkflowStep(name="step1", command="failing command")
        step2 = WorkflowStep(
            name="step2",
            command="should skip",
            depends_on=["step1"],
        )

        def mock_execute_side_effect(step, vms, rg, callback):
            if step.name == "step1":
                return WorkflowResult(
                    step_name="step1",
                    success=False,
                    results=[],
                )
            return WorkflowResult(
                step_name=step.name,
                success=True,
                results=[],
            )

        mock_execute_step.side_effect = mock_execute_side_effect

        orchestrator = WorkflowOrchestrator()
        results = orchestrator.execute_workflow([step1, step2], [], "test-rg")

        assert len(results) == 2
        assert results[0].success is False
        assert results[1].skipped is True
        assert "failure" in results[1].skip_reason.lower()

    @patch("azlin.fleet_orchestrator.WorkflowOrchestrator._execute_step")
    def test_execute_workflow_circular_dependency(self, mock_execute_step):
        """Test that circular dependencies are detected."""
        step1 = WorkflowStep(
            name="step1",
            command="echo first",
            depends_on=["step2"],
        )
        step2 = WorkflowStep(
            name="step2",
            command="echo second",
            depends_on=["step1"],
        )

        orchestrator = WorkflowOrchestrator()

        with pytest.raises(FleetOrchestratorError, match="Circular dependency"):
            orchestrator.execute_workflow([step1, step2], [], "test-rg")


class TestResultDiffGenerator:
    """Tests for result diff generation."""

    def test_generate_diff_identical_outputs(self):
        """Test diff generation when all outputs are identical."""
        results = [
            BatchOperationResult(
                vm_name="vm1",
                success=True,
                message="",
                output="Hello world",
            ),
            BatchOperationResult(
                vm_name="vm2",
                success=True,
                message="",
                output="Hello world",
            ),
        ]

        diff = ResultDiffGenerator.generate_diff(results)
        assert "identical" in diff.lower()

    def test_generate_diff_different_outputs(self):
        """Test diff generation with different outputs."""
        results = [
            BatchOperationResult(
                vm_name="vm1",
                success=True,
                message="",
                output="Version 1.0.0",
            ),
            BatchOperationResult(
                vm_name="vm2",
                success=True,
                message="",
                output="Version 2.0.0",
            ),
        ]

        diff = ResultDiffGenerator.generate_diff(results)
        assert "differences" in diff.lower() or "diff" in diff.lower()
        assert "vm1" in diff
        assert "vm2" in diff

    def test_generate_diff_insufficient_results(self):
        """Test diff generation with insufficient results."""
        results = [
            BatchOperationResult(
                vm_name="vm1",
                success=True,
                message="",
                output="Only one",
            ),
        ]

        diff = ResultDiffGenerator.generate_diff(results)
        assert "at least 2" in diff.lower()

    def test_sanitize_output(self):
        """Test that sensitive data is sanitized in diffs."""
        output_with_secret = "password=secret123 token=abc123"  # noqa: S105
        sanitized = ResultDiffGenerator._sanitize_output(output_with_secret)

        assert "secret123" not in sanitized
        assert "abc123" not in sanitized
        assert "***" in sanitized
