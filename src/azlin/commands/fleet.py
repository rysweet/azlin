"""Fleet command orchestration CLI commands.

This module provides commands for distributed fleet operations:
- Execute commands across VM fleets with conditions
- Smart VM routing based on load
- Dependency chain management
- YAML workflow execution
- Result diff reporting
"""

import logging
import sys
from pathlib import Path

import click
from rich.console import Console

from azlin.batch_executor import BatchSelector, ConditionalExecutor
from azlin.click_group import AzlinGroup
from azlin.config_manager import ConfigError, ConfigManager
from azlin.fleet_orchestrator import (
    FleetOrchestratorError,
    ResultDiffGenerator,
    WorkflowOrchestrator,
)
from azlin.vm_manager import VMManager, VMManagerError

logger = logging.getLogger(__name__)
console = Console()


@click.group(name="fleet", cls=AzlinGroup)
def fleet_group():
    """Distributed command orchestration across VM fleets.

    Execute commands across multiple VMs with advanced features:
    - Conditional execution based on VM state
    - Smart routing to least-loaded VMs
    - Sequential dependency chains
    - YAML workflow definitions
    - Result diff reports

    \b
    COMMANDS:
        run        Execute command across fleet
        workflow   Execute YAML workflow definition

    \b
    EXAMPLES:
        # Run tests on idle VMs only
        $ azlin fleet run "npm test" --if-idle --parallel 5

        # Deploy to web servers with retry
        $ azlin fleet run "deploy.sh" --tag role=web --retry-failed

        # Execute on least-loaded VMs
        $ azlin fleet run "backup.sh" --smart-route --count 3

        # Run workflow from YAML
        $ azlin fleet workflow deploy.yaml --tag env=staging
    """
    pass


@fleet_group.command(name="run")
@click.argument("command", type=str)
@click.option("--resource-group", "--rg", help="Azure resource group")
@click.option("--tag", "tag_filter", help="Filter VMs by tag (format: key=value)")
@click.option("--pattern", help="Filter VMs by name pattern (glob)")
@click.option("--all", "all_vms", is_flag=True, help="Run on all VMs")
@click.option("--parallel", type=int, default=10, help="Max parallel workers (default: 10)")
@click.option("--if-idle", is_flag=True, help="Only run on idle VMs")
@click.option("--if-cpu-below", type=int, metavar="PERCENT", help="Only run if CPU below threshold")
@click.option(
    "--if-mem-below",
    type=int,
    metavar="PERCENT",
    help="Only run if memory below threshold",
)
@click.option("--smart-route", is_flag=True, help="Route to least-loaded VMs first")
@click.option("--count", type=int, help="Limit execution to N VMs")
@click.option("--retry-failed", is_flag=True, help="Retry failed VMs once")
@click.option("--show-diff", is_flag=True, help="Show diff of command outputs")
@click.option("--timeout", type=int, default=300, help="Command timeout in seconds")
@click.option("--dry-run", is_flag=True, help="Show what would be executed")
def run_command(
    command: str,
    resource_group: str | None,
    tag_filter: str | None,
    pattern: str | None,
    all_vms: bool,
    parallel: int,
    if_idle: bool,
    if_cpu_below: int | None,
    if_mem_below: int | None,
    smart_route: bool,
    count: int | None,
    retry_failed: bool,
    show_diff: bool,
    timeout: int,
    dry_run: bool,
):
    """Execute command across fleet of VMs.

    Runs the specified command on selected VMs with optional conditions,
    smart routing, and result aggregation.

    \b
    COMMAND is the shell command to execute remotely.

    \b
    Selection Options:
      --tag          Filter by tag (e.g., role=web)
      --pattern      Filter by name pattern (e.g., 'web-*')
      --all          Run on all VMs

    \b
    Condition Options:
      --if-idle          Only run on idle VMs (no active users)
      --if-cpu-below N   Only run if CPU usage below N%
      --if-mem-below N   Only run if memory usage below N%

    \b
    Routing Options:
      --smart-route  Route to least-loaded VMs first
      --count N      Limit to N VMs

    \b
    Execution Options:
      --parallel N     Max parallel workers (default: 10)
      --retry-failed   Retry failed VMs once
      --timeout N      Command timeout in seconds (default: 300)
      --dry-run        Show what would be executed

    \b
    Output Options:
      --show-diff    Show diff of command outputs across VMs

    \b
    Examples:
      # Run tests on all idle web servers
      $ azlin fleet run "npm test" --tag role=web --if-idle

      # Deploy to 3 least-loaded staging VMs
      $ azlin fleet run "deploy.sh" --tag env=staging --smart-route --count 3

      # Backup with retry on failure
      $ azlin fleet run "backup.sh" --pattern 'db-*' --retry-failed

      # Check versions with diff report
      $ azlin fleet run "node --version" --all --show-diff
    """
    try:
        # Get config
        try:
            config = ConfigManager.load_config()
            if resource_group is None:
                resource_group = config.resource_group
        except ConfigError:
            if resource_group is None:
                console.print("[red]Error: No resource group configured[/red]")
                console.print("Run 'azlin config set-rg <name>' or use --resource-group")
                sys.exit(1)

        # Ensure resource_group is not None after config loading
        if resource_group is None:
            console.print("[red]Error: No resource group configured[/red]")
            console.print("Run 'azlin config set-rg <name>' or use --resource-group")
            sys.exit(1)

        # Validate selection
        selection_count = sum([bool(tag_filter), bool(pattern), all_vms])
        if selection_count == 0:
            console.print("[red]Error: Must specify VM selection[/red]")
            console.print("Use --tag, --pattern, or --all")
            sys.exit(1)

        if selection_count > 1:
            console.print("[red]Error: Use only one selection method[/red]")
            sys.exit(1)

        # Get VMs
        all_vm_list = VMManager.list_vms(resource_group)

        # Apply selection filter
        if tag_filter:
            selected_vms = BatchSelector.select_by_tag(all_vm_list, tag_filter)
        elif pattern:
            selected_vms = BatchSelector.select_by_pattern(all_vm_list, pattern)
        else:  # all_vms
            selected_vms = BatchSelector.select_running_only(all_vm_list)

        if not selected_vms:
            console.print("[yellow]No VMs match selection criteria[/yellow]")
            sys.exit(0)

        console.print(f"[cyan]Selected {len(selected_vms)} VMs[/cyan]")

        # Build condition string from CLI options
        condition = None
        if if_idle:
            condition = "idle"
        elif if_cpu_below is not None:
            condition = f"cpu<{if_cpu_below}"
        elif if_mem_below is not None:
            condition = f"mem<{if_mem_below}"

        # Apply conditional filtering if specified
        target_vms = selected_vms
        metrics = {}
        if condition or smart_route:
            console.print("[cyan]Collecting VM metrics...[/cyan]")
            conditional_executor = ConditionalExecutor(max_workers=parallel)

            if condition:
                filtered_vms, metrics = conditional_executor.filter_by_condition(
                    selected_vms, condition, resource_group
                )

                console.print(f"[cyan]{len(filtered_vms)} VMs meet condition '{condition}'[/cyan]")

                if not filtered_vms:
                    console.print("[yellow]No VMs meet specified condition[/yellow]")
                    sys.exit(0)

                target_vms = filtered_vms
            else:
                # Just collect metrics for smart routing
                _, metrics = conditional_executor.filter_by_condition(
                    selected_vms,
                    "idle",
                    resource_group,  # Use idle as dummy condition
                )

        # Apply smart routing if requested
        if smart_route and metrics:
            orchestrator = WorkflowOrchestrator(max_workers=parallel)
            target_vms = orchestrator.route_vms_by_load(target_vms, metrics, count)
            console.print(f"[cyan]Smart routing selected {len(target_vms)} least-loaded VMs[/cyan]")
        elif count:
            target_vms = target_vms[:count]
            console.print(f"[cyan]Limited to {len(target_vms)} VMs[/cyan]")

        # Dry run
        if dry_run:
            console.print("\n[yellow]DRY RUN - Would execute on:[/yellow]")
            for vm in target_vms:
                console.print(f"  - {vm.name}")
            console.print(f"\n[yellow]Command:[/yellow] {command}")
            console.print(f"[yellow]Timeout:[/yellow] {timeout}s")
            console.print(f"[yellow]Retry failed:[/yellow] {retry_failed}")
            sys.exit(0)

        # Execute command
        console.print(f"\n[cyan]Executing command on {len(target_vms)} VMs...[/cyan]")

        orchestrator = WorkflowOrchestrator(max_workers=parallel)

        # Create workflow step for execution
        from azlin.fleet_orchestrator import WorkflowStep

        step = WorkflowStep(
            name="fleet_run",
            command=command,
            retry_on_failure=retry_failed,
            continue_on_error=True,
        )

        def progress(msg: str):
            console.print(f"  {msg}")

        result = orchestrator._execute_step(step, target_vms, resource_group, progress)

        # Display results
        console.print("\n[cyan]Results:[/cyan]")
        success_count = sum(1 for r in result.results if r.success)
        fail_count = len(result.results) - success_count

        console.print(f"  Success: [green]{success_count}[/green]")
        console.print(f"  Failed: [red]{fail_count}[/red]")

        # Show failures
        if fail_count > 0:
            console.print("\n[red]Failed VMs:[/red]")
            for r in result.results:
                if not r.success:
                    console.print(f"  - {r.vm_name}: {r.message}")

        # Show diff if requested
        if show_diff and result.results:
            console.print("\n[cyan]Output Differences:[/cyan]")
            diff = ResultDiffGenerator.generate_diff(result.results)
            console.print(diff)

        sys.exit(0 if fail_count == 0 else 1)

    except (VMManagerError, FleetOrchestratorError) as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error in fleet run")
        console.print(f"[red]Unexpected error: {e}[/red]")
        sys.exit(1)


@fleet_group.command(name="workflow")
@click.argument("workflow_file", type=click.Path(exists=True, path_type=Path))
@click.option("--resource-group", "--rg", help="Azure resource group")
@click.option("--tag", "tag_filter", help="Filter VMs by tag (format: key=value)")
@click.option("--pattern", help="Filter VMs by name pattern (glob)")
@click.option("--all", "all_vms", is_flag=True, help="Run on all VMs")
@click.option("--parallel", type=int, default=10, help="Max parallel workers (default: 10)")
@click.option("--show-diff", is_flag=True, help="Show diff of final step outputs")
@click.option("--dry-run", is_flag=True, help="Show workflow without executing")
def run_workflow(
    workflow_file: Path,
    resource_group: str | None,
    tag_filter: str | None,
    pattern: str | None,
    all_vms: bool,
    parallel: int,
    show_diff: bool,
    dry_run: bool,
):
    """Execute YAML workflow definition.

    Loads and executes a multi-step workflow defined in YAML format.
    Supports dependency chains, conditions, and parallel execution.

    \b
    WORKFLOW_FILE is the path to YAML workflow definition.

    \b
    Workflow YAML Format:
      steps:
        - name: step1
          command: "echo hello"
          condition: idle           # Optional
          depends_on: []            # Optional
          parallel: true            # Optional (default: true)
          retry_on_failure: false   # Optional (default: false)
          continue_on_error: false  # Optional (default: false)

    \b
    Examples:
      # Run deploy workflow on staging
      $ azlin fleet workflow deploy.yaml --tag env=staging

      # Dry run to see workflow steps
      $ azlin fleet workflow deploy.yaml --all --dry-run

      # Run with diff on final step
      $ azlin fleet workflow test.yaml --pattern 'web-*' --show-diff
    """
    try:
        # Get config
        try:
            config = ConfigManager.load_config()
            if resource_group is None:
                resource_group = config.resource_group
        except ConfigError:
            if resource_group is None:
                console.print("[red]Error: No resource group configured[/red]")
                console.print("Run 'azlin config set-rg <name>' or use --resource-group")
                sys.exit(1)

        # Ensure resource_group is not None after config loading
        if resource_group is None:
            console.print("[red]Error: No resource group configured[/red]")
            console.print("Run 'azlin config set-rg <name>' or use --resource-group")
            sys.exit(1)

        # Load workflow
        orchestrator = WorkflowOrchestrator(max_workers=parallel)
        steps = orchestrator.load_workflow(workflow_file)

        console.print(f"[cyan]Loaded workflow with {len(steps)} steps[/cyan]")

        # Dry run
        if dry_run:
            console.print("\n[yellow]DRY RUN - Workflow steps:[/yellow]")
            for i, step in enumerate(steps, 1):
                console.print(f"\n[cyan]Step {i}: {step.name}[/cyan]")
                console.print(f"  Command: {step.command}")
                if step.condition:
                    console.print(f"  Condition: {step.condition}")
                if step.depends_on:
                    console.print(f"  Depends on: {', '.join(step.depends_on)}")
                console.print(f"  Parallel: {step.parallel}")
                console.print(f"  Retry on failure: {step.retry_on_failure}")
            sys.exit(0)

        # Validate selection
        selection_count = sum([bool(tag_filter), bool(pattern), all_vms])
        if selection_count == 0:
            console.print("[red]Error: Must specify VM selection[/red]")
            console.print("Use --tag, --pattern, or --all")
            sys.exit(1)

        if selection_count > 1:
            console.print("[red]Error: Use only one selection method[/red]")
            sys.exit(1)

        # Get VMs
        all_vm_list = VMManager.list_vms(resource_group)

        # Apply selection filter
        if tag_filter:
            selected_vms = BatchSelector.select_by_tag(all_vm_list, tag_filter)
        elif pattern:
            selected_vms = BatchSelector.select_by_pattern(all_vm_list, pattern)
        else:  # all_vms
            selected_vms = BatchSelector.select_running_only(all_vm_list)

        if not selected_vms:
            console.print("[yellow]No VMs match selection criteria[/yellow]")
            sys.exit(0)

        console.print(f"[cyan]Selected {len(selected_vms)} VMs[/cyan]")

        # Execute workflow
        console.print("\n[cyan]Executing workflow...[/cyan]")

        def progress(msg: str):
            console.print(f"  {msg}")

        results = orchestrator.execute_workflow(steps, selected_vms, resource_group, progress)

        # Display results
        console.print("\n[cyan]Workflow Results:[/cyan]")
        for result in results:
            if result.skipped:
                console.print(
                    f"  [yellow]{result.step_name}: Skipped ({result.skip_reason})[/yellow]"
                )
            elif result.success:
                console.print(f"  [green]{result.step_name}: Success[/green]")
            else:
                console.print(f"  [red]{result.step_name}: Failed[/red]")

        # Show diff for last successful step if requested
        if show_diff:
            for result in reversed(results):
                if result.success and not result.skipped and result.results:
                    console.print(f"\n[cyan]Output Diff for '{result.step_name}':[/cyan]")
                    diff = ResultDiffGenerator.generate_diff(result.results)
                    console.print(diff)
                    break

        # Exit with error if any step failed
        any_failed = any(not r.success and not r.skipped for r in results)
        sys.exit(1 if any_failed else 0)

    except (VMManagerError, FleetOrchestratorError) as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error in fleet workflow")
        console.print(f"[red]Unexpected error: {e}[/red]")
        sys.exit(1)


__all__ = ["fleet_group"]
