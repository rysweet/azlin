"""Fleet orchestration module for distributed command execution.

This module provides workflow orchestration for fleet operations:
- Dependency chain management (sequential execution)
- Smart VM routing based on load/health
- YAML workflow definitions
- Result aggregation and diff reporting

Security:
- YAML safe loading only
- Command sanitization via remote_exec
- Result sanitization before display
- No arbitrary code execution in conditions

Philosophy:
- Single responsibility: Orchestrate workflows only
- Clear contracts: WorkflowStep and WorkflowResult dataclasses
- Regeneratable: Can be rebuilt from module specification
"""

import difflib
import logging
import yaml
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from azlin.batch_executor import (
    BatchExecutor,
    BatchOperationResult,
    BatchResult,
    ConditionalExecutor,
    VMMetrics,
)
from azlin.vm_manager import VMInfo

logger = logging.getLogger(__name__)


class FleetOrchestratorError(Exception):
    """Raised when fleet orchestration operations fail."""

    pass


@dataclass
class WorkflowStep:
    """Single step in a workflow."""

    name: str
    command: str
    condition: str | None = None  # Optional condition (e.g., 'idle', 'cpu<50')
    depends_on: list[str] = field(default_factory=list)  # Names of prerequisite steps
    parallel: bool = True  # Execute in parallel or sequentially
    retry_on_failure: bool = False
    continue_on_error: bool = False


@dataclass
class WorkflowResult:
    """Result of executing a workflow step."""

    step_name: str
    success: bool
    results: list[BatchOperationResult]
    skipped: bool = False
    skip_reason: str | None = None


class WorkflowOrchestrator:
    """Orchestrate complex workflows across VM fleets.

    This class provides:
    - Sequential dependency chains
    - Smart VM routing by load
    - YAML workflow loading
    - Result diff reporting
    """

    def __init__(self, max_workers: int = 10):
        """Initialize workflow orchestrator.

        Args:
            max_workers: Maximum number of parallel workers
        """
        self.max_workers = max_workers
        self.batch_executor = BatchExecutor(max_workers=max_workers)
        self.conditional_executor = ConditionalExecutor(max_workers=max_workers)

    @staticmethod
    def load_workflow(workflow_file: Path) -> list[WorkflowStep]:
        """Load workflow from YAML file.

        Args:
            workflow_file: Path to YAML workflow file

        Returns:
            List of WorkflowStep objects

        Raises:
            FleetOrchestratorError: If workflow file is invalid

        Security:
            Uses yaml.safe_load() to prevent arbitrary code execution
        """
        if not workflow_file.exists():
            raise FleetOrchestratorError(f"Workflow file not found: {workflow_file}")

        try:
            with workflow_file.open() as f:
                data = yaml.safe_load(f)

            if not isinstance(data, dict) or "steps" not in data:
                raise FleetOrchestratorError("Workflow must contain 'steps' key")

            steps = []
            for step_data in data["steps"]:
                if not isinstance(step_data, dict):
                    raise FleetOrchestratorError("Each step must be a dictionary")

                if "name" not in step_data or "command" not in step_data:
                    raise FleetOrchestratorError("Each step must have 'name' and 'command'")

                step = WorkflowStep(
                    name=step_data["name"],
                    command=step_data["command"],
                    condition=step_data.get("condition"),
                    depends_on=step_data.get("depends_on", []),
                    parallel=step_data.get("parallel", True),
                    retry_on_failure=step_data.get("retry_on_failure", False),
                    continue_on_error=step_data.get("continue_on_error", False),
                )
                steps.append(step)

            return steps

        except yaml.YAMLError as e:
            raise FleetOrchestratorError(f"Failed to parse YAML: {e}")
        except Exception as e:
            raise FleetOrchestratorError(f"Failed to load workflow: {e}")

    def route_vms_by_load(
        self, vms: list[VMInfo], metrics: dict[str, VMMetrics], count: int | None = None
    ) -> list[VMInfo]:
        """Route VMs by selecting least loaded first.

        Args:
            vms: List of available VMs
            metrics: VM metrics dictionary
            count: Number of VMs to select (None = all)

        Returns:
            List of VMs sorted by load (least loaded first)
        """
        if not vms:
            return []

        # Filter to VMs with successful metrics
        vm_with_metrics = [
            (vm, metrics.get(vm.name))
            for vm in vms
            if vm.name in metrics and metrics[vm.name].success
        ]

        # Sort by load (use 1-minute load average)
        # VMs without load data go to end
        sorted_vms = sorted(
            vm_with_metrics,
            key=lambda x: x[1].load_avg[0] if x[1].load_avg else float("inf"),
        )

        # Extract just the VMs
        result_vms = [vm for vm, _ in sorted_vms]

        # Limit to requested count
        if count is not None:
            result_vms = result_vms[:count]

        return result_vms

    def execute_workflow(
        self,
        steps: list[WorkflowStep],
        vms: list[VMInfo],
        resource_group: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[WorkflowResult]:
        """Execute multi-step workflow with dependency management.

        Args:
            steps: Workflow steps to execute
            vms: VMs to execute on
            resource_group: Resource group name
            progress_callback: Optional progress callback

        Returns:
            List of WorkflowResult objects
        """
        if not steps:
            return []

        results = {}  # step_name -> WorkflowResult
        executed_steps = set()

        def can_execute(step: WorkflowStep) -> tuple[bool, str | None]:
            """Check if step dependencies are satisfied."""
            for dep in step.depends_on:
                if dep not in executed_steps:
                    return False, f"Waiting for dependency: {dep}"

                # Check if dependency succeeded
                dep_result = results.get(dep)
                if dep_result and not dep_result.success:
                    return False, f"Dependency failed: {dep}"

            return True, None

        # Execute steps respecting dependencies
        remaining_steps = steps.copy()

        while remaining_steps:
            # Find steps ready to execute
            ready_steps = []
            for step in remaining_steps:
                can_run, reason = can_execute(step)
                if can_run:
                    ready_steps.append(step)

            if not ready_steps:
                # Check for circular dependencies
                if remaining_steps:
                    pending_names = [s.name for s in remaining_steps]
                    raise FleetOrchestratorError(
                        f"Circular dependency or missing dependencies: {pending_names}"
                    )
                break

            # Execute ready steps
            for step in ready_steps:
                result = self._execute_step(step, vms, resource_group, progress_callback)
                results[step.name] = result
                executed_steps.add(step.name)
                remaining_steps.remove(step)

                # Stop if step failed and should not continue
                if not result.success and not step.continue_on_error:
                    # Mark remaining steps as skipped
                    for remaining in remaining_steps:
                        results[remaining.name] = WorkflowResult(
                            step_name=remaining.name,
                            success=False,
                            results=[],
                            skipped=True,
                            skip_reason=f"Skipped due to failure in step: {step.name}",
                        )
                    return list(results.values())

        return list(results.values())

    def _execute_step(
        self,
        step: WorkflowStep,
        vms: list[VMInfo],
        resource_group: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> WorkflowResult:
        """Execute a single workflow step.

        Args:
            step: Workflow step to execute
            vms: VMs to execute on
            resource_group: Resource group name
            progress_callback: Optional progress callback

        Returns:
            WorkflowResult object
        """
        if progress_callback:
            progress_callback(f"Executing step: {step.name}")

        # Apply condition filter if specified
        target_vms = vms
        if step.condition:
            filtered_vms, _ = self.conditional_executor.filter_by_condition(
                vms, step.condition, resource_group
            )

            if not filtered_vms:
                if progress_callback:
                    progress_callback(
                        f"Step {step.name} skipped: No VMs meet condition '{step.condition}'"
                    )

                return WorkflowResult(
                    step_name=step.name,
                    success=True,
                    results=[],
                    skipped=True,
                    skip_reason=f"No VMs meet condition: {step.condition}",
                )

            target_vms = filtered_vms

        # Execute command on target VMs
        batch_results = self.batch_executor.execute_command(
            vms=target_vms,
            command=step.command,
            resource_group=resource_group,
            progress_callback=progress_callback,
        )

        # Handle retry on failure
        if step.retry_on_failure:
            failed_vms = [
                vm for vm in target_vms if not any(r.vm_name == vm.name and r.success for r in batch_results)
            ]

            if failed_vms:
                if progress_callback:
                    progress_callback(f"Retrying failed VMs for step: {step.name}")

                retry_results = self.batch_executor.execute_command(
                    vms=failed_vms,
                    command=step.command,
                    resource_group=resource_group,
                    progress_callback=progress_callback,
                )

                # Update results with retry attempts
                for retry_result in retry_results:
                    # Replace original failure with retry result
                    for i, orig_result in enumerate(batch_results):
                        if orig_result.vm_name == retry_result.vm_name:
                            batch_results[i] = retry_result
                            break

        success = all(r.success for r in batch_results)

        return WorkflowResult(
            step_name=step.name,
            success=success,
            results=batch_results,
        )


class ResultDiffGenerator:
    """Generate diff reports for command results across VMs."""

    @staticmethod
    def generate_diff(results: list[BatchOperationResult], sanitize: bool = True) -> str:
        """Generate diff report showing differences in command outputs.

        Args:
            results: List of batch operation results
            sanitize: Whether to sanitize output before diff

        Returns:
            Formatted diff report
        """
        if len(results) < 2:
            return "Cannot generate diff: Need at least 2 results"

        # Group by output
        output_groups: dict[str, list[str]] = {}
        for result in results:
            output = result.output or ""

            # Sanitize if requested
            if sanitize:
                output = ResultDiffGenerator._sanitize_output(output)

            if output not in output_groups:
                output_groups[output] = []
            output_groups[output].append(result.vm_name)

        # If all outputs are identical
        if len(output_groups) == 1:
            return "All VM outputs are identical - no differences found"

        # Generate diff report
        report_lines = ["Command Output Differences:", "=" * 60, ""]

        # Show output groups
        for i, (output, vm_names) in enumerate(output_groups.items(), 1):
            report_lines.append(f"Output Group {i} (VMs: {', '.join(vm_names)}):")
            report_lines.append("-" * 60)
            report_lines.append(output[:500])  # Limit output length
            if len(output) > 500:
                report_lines.append("... (truncated)")
            report_lines.append("")

        # Generate unified diff between first two groups
        if len(output_groups) >= 2:
            outputs = list(output_groups.keys())
            diff = difflib.unified_diff(
                outputs[0].splitlines(),
                outputs[1].splitlines(),
                fromfile="Group 1",
                tofile="Group 2",
                lineterm="",
            )

            report_lines.append("Unified Diff (Group 1 vs Group 2):")
            report_lines.append("-" * 60)
            report_lines.extend(list(diff))

        return "\n".join(report_lines)

    @staticmethod
    def _sanitize_output(output: str) -> str:
        """Sanitize output by removing potential sensitive data.

        Args:
            output: Output string to sanitize

        Returns:
            Sanitized output
        """
        import re

        # Remove potential secrets
        patterns = [
            (r"password[=:]\S+", "password=***"),
            (r"token[=:]\S+", "token=***"),
            (r"api[_-]?key[=:]\S+", "api_key=***"),
            (r"secret[=:]\S+", "secret=***"),
        ]

        sanitized = output
        for pattern, replacement in patterns:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

        return sanitized


__all__ = [
    "FleetOrchestratorError",
    "ResultDiffGenerator",
    "WorkflowOrchestrator",
    "WorkflowResult",
    "WorkflowStep",
]
