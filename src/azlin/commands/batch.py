"""Batch operations commands for azlin CLI.

This module provides batch operations for executing commands on multiple VMs simultaneously:
- batch stop: Stop/deallocate multiple VMs
- batch start: Start multiple VMs
- batch command: Execute shell commands on multiple VMs
- batch sync: Sync home directory to multiple VMs
"""

from __future__ import annotations

import logging
import sys

import click

from azlin.batch_executor import BatchExecutor, BatchExecutorError, BatchResult, BatchSelector
from azlin.config_manager import ConfigManager
from azlin.vm_manager import VMInfo, VMManager, VMManagerError

logger = logging.getLogger(__name__)


# ============================================================================
# BATCH COMMAND GROUP
# ============================================================================


@click.group(name="batch")
def batch():
    """Batch operations on multiple VMs.

    Execute operations on multiple VMs simultaneously using
    tag-based selection, pattern matching, or all VMs.

    \b
    Examples:
        azlin batch stop --tag 'env=dev'
        azlin batch start --vm-pattern 'test-*'
        azlin batch command 'git pull' --all
        azlin batch sync --tag 'env=dev'
    """
    pass


# ============================================================================
# BATCH STOP COMMAND (STUB - Not fully implemented)
# ============================================================================


@batch.command(name="stop")
@click.option("--tag", help="Filter VMs by tag (format: key=value)", type=str)
@click.option("--vm-pattern", help="Filter VMs by name pattern (glob)", type=str)
@click.option("--all", "select_all", is_flag=True, help="Select all VMs in resource group")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option(
    "--deallocate/--no-deallocate", default=True, help="Deallocate to save costs (default: yes)"
)
@click.option("--max-workers", default=10, help="Maximum parallel workers (default: 10)", type=int)
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def batch_stop(
    tag: str | None,
    vm_pattern: str | None,
    select_all: bool,
    resource_group: str | None,
    config: str | None,
    deallocate: bool,
    max_workers: int,
    confirm: bool,
):
    """Batch stop/deallocate VMs.

    Stop multiple VMs simultaneously. By default, VMs are deallocated
    to stop billing for compute resources.

    \b
    Examples:
        azlin batch stop --tag 'env=dev'
        azlin batch stop --vm-pattern 'test-*'
        azlin batch stop --all --confirm
    """
    pass  # TODO: Implement batch stop functionality


# ============================================================================
# BATCH START COMMAND
# ============================================================================


@batch.command(name="start")
@click.option("--tag", help="Filter VMs by tag (format: key=value)", type=str)
@click.option("--vm-pattern", help="Filter VMs by name pattern (glob)", type=str)
@click.option("--all", "select_all", is_flag=True, help="Select all VMs in resource group")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--max-workers", default=10, help="Maximum parallel workers (default: 10)", type=int)
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def batch_start(
    tag: str | None,
    vm_pattern: str | None,
    select_all: bool,
    resource_group: str | None,
    config: str | None,
    max_workers: int,
    confirm: bool,
):
    """Batch start VMs.

    Start multiple stopped/deallocated VMs simultaneously.

    \b
    Examples:
        azlin batch start --tag 'env=dev'
        azlin batch start --vm-pattern 'test-*'
        azlin batch start --all --confirm
    """
    try:
        # Validate selection options
        _validate_batch_selection(tag, vm_pattern, select_all)

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # List and select VMs
        click.echo(f"Loading VMs from resource group: {rg}...")
        all_vms = VMManager.list_vms(rg, include_stopped=True)
        selected_vms, selection_desc = _select_vms_by_criteria(all_vms, tag, vm_pattern, select_all)

        # Filter to only stopped VMs
        stopped_vms = [vm for vm in selected_vms if vm.is_stopped()]
        if not stopped_vms:
            click.echo(f"No stopped VMs found matching {selection_desc}.")
            return

        # Show summary
        click.echo(f"\nFound {len(stopped_vms)} stopped VM(s) matching {selection_desc}:")
        click.echo("=" * 80)
        for vm in stopped_vms:
            click.echo(f"  {vm.name:<35} {vm.power_state:<20} {vm.location}")
        click.echo("=" * 80)

        # Confirmation
        if not _confirm_batch_operation(len(stopped_vms), "start", confirm):
            return

        # Execute batch start
        click.echo(f"\nStarting {len(stopped_vms)} VM(s)...")
        executor = BatchExecutor(max_workers=max_workers)

        def progress_callback(msg: str):
            click.echo(f"  {msg}")

        results = executor.execute_start(stopped_vms, rg, progress_callback=progress_callback)

        # Show results
        batch_result = BatchResult(results)
        _display_batch_summary(batch_result, "Start")

        sys.exit(0 if batch_result.all_succeeded else 1)

    except BatchExecutorError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in batch start")
        sys.exit(1)


# ============================================================================
# BATCH COMMAND COMMAND
# ============================================================================


@batch.command(name="command")
@click.argument("command", type=str)
@click.option("--tag", help="Filter VMs by tag (format: key=value)", type=str)
@click.option("--vm-pattern", help="Filter VMs by name pattern (glob)", type=str)
@click.option("--all", "select_all", is_flag=True, help="Select all VMs in resource group")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--max-workers", default=10, help="Maximum parallel workers (default: 10)", type=int)
@click.option("--timeout", default=300, help="Command timeout in seconds (default: 300)", type=int)
@click.option("--show-output", is_flag=True, help="Show command output from each VM")
def batch_command(
    command: str,
    tag: str | None,
    vm_pattern: str | None,
    select_all: bool,
    resource_group: str | None,
    config: str | None,
    max_workers: int,
    timeout: int,
    show_output: bool,
):
    """Execute command on multiple VMs.

    Execute a shell command on multiple VMs simultaneously.

    \b
    Examples:
        azlin batch command 'git pull' --tag 'env=dev'
        azlin batch command 'df -h' --vm-pattern 'web-*'
        azlin batch command 'uptime' --all --show-output
    """
    try:
        # Validate selection options
        _validate_batch_selection(tag, vm_pattern, select_all)

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # List and select VMs
        click.echo(f"Loading VMs from resource group: {rg}...")
        all_vms = VMManager.list_vms(rg, include_stopped=False)
        selected_vms, selection_desc = _select_vms_by_criteria(all_vms, tag, vm_pattern, select_all)

        # Filter to running VMs with IPs
        running_vms = [vm for vm in selected_vms if vm.is_running() and vm.public_ip]
        if not running_vms:
            click.echo(f"No running VMs with public IPs found matching {selection_desc}.")
            return

        # Show summary
        click.echo(f"\nFound {len(running_vms)} VM(s) matching {selection_desc}:")
        click.echo("=" * 80)
        for vm in running_vms:
            click.echo(f"  {vm.name:<35} {vm.public_ip:<15}")
        click.echo("=" * 80)
        click.echo(f"\nCommand: {command}")

        # Execute batch command
        click.echo(f"\nExecuting command on {len(running_vms)} VM(s)...")
        executor = BatchExecutor(max_workers=max_workers)

        def progress_callback(msg: str):
            click.echo(f"  {msg}")

        results = executor.execute_command(
            running_vms, command, rg, timeout=timeout, progress_callback=progress_callback
        )

        # Show results
        batch_result = BatchResult(results)
        _display_batch_summary(batch_result, "Command")

        # Show output if requested
        if show_output:
            click.echo("\nCommand Output:")
            click.echo("=" * 80)
            for result in results:
                click.echo(f"\n[{result.vm_name}]")
                if result.output:
                    click.echo(result.output)
                else:
                    click.echo("  (no output)")
            click.echo("=" * 80)

        sys.exit(0 if batch_result.all_succeeded else 1)

    except BatchExecutorError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in batch command")
        sys.exit(1)


# ============================================================================
# BATCH SYNC COMMAND
# ============================================================================


@batch.command(name="sync")
@click.option("--tag", help="Filter VMs by tag (format: key=value)", type=str)
@click.option("--vm-pattern", help="Filter VMs by name pattern (glob)", type=str)
@click.option("--all", "select_all", is_flag=True, help="Select all VMs in resource group")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--max-workers", default=10, help="Maximum parallel workers (default: 10)", type=int)
@click.option("--dry-run", is_flag=True, help="Show what would be synced without syncing")
def batch_sync(
    tag: str | None,
    vm_pattern: str | None,
    select_all: bool,
    resource_group: str | None,
    config: str | None,
    max_workers: int,
    dry_run: bool,
):
    """Batch sync home directory to VMs.

    Sync ~/.azlin/home/ to multiple VMs simultaneously.

    \b
    Examples:
        azlin batch sync --tag 'env=dev'
        azlin batch sync --vm-pattern 'web-*'
        azlin batch sync --all --dry-run
    """
    try:
        # Validate selection options
        _validate_batch_selection(tag, vm_pattern, select_all)

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # List and select VMs
        click.echo(f"Loading VMs from resource group: {rg}...")
        all_vms = VMManager.list_vms(rg, include_stopped=False)
        selected_vms, selection_desc = _select_vms_by_criteria(all_vms, tag, vm_pattern, select_all)

        # Filter to running VMs with IPs
        running_vms = [vm for vm in selected_vms if vm.is_running() and vm.public_ip]
        if not running_vms:
            click.echo(f"No running VMs with public IPs found matching {selection_desc}.")
            return

        # Show summary
        click.echo(f"\nFound {len(running_vms)} VM(s) matching {selection_desc}:")
        click.echo("=" * 80)
        for vm in running_vms:
            click.echo(f"  {vm.name:<35} {vm.public_ip:<15}")
        click.echo("=" * 80)

        if dry_run:
            click.echo("\n[DRY RUN] No files will be synced")

        # Execute batch sync
        click.echo(f"\nSyncing to {len(running_vms)} VM(s)...")
        executor = BatchExecutor(max_workers=max_workers)

        def progress_callback(msg: str):
            click.echo(f"  {msg}")

        results = executor.execute_sync(
            running_vms, rg, dry_run=dry_run, progress_callback=progress_callback
        )

        # Show results
        batch_result = BatchResult(results)
        _display_batch_summary(batch_result, "Sync")

        sys.exit(0 if batch_result.all_succeeded else 1)

    except BatchExecutorError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in batch sync")
        sys.exit(1)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _validate_batch_selection(tag: str | None, vm_pattern: str | None, select_all: bool):
    """Validate that exactly one batch selection option is provided."""
    selection_count = sum([bool(tag), bool(vm_pattern), select_all])
    if selection_count == 0:
        click.echo("Error: Must specify --tag, --vm-pattern, or --all", err=True)
        sys.exit(1)
    if selection_count > 1:
        click.echo("Error: Can only use one of --tag, --vm-pattern, or --all", err=True)
        sys.exit(1)


def _select_vms_by_criteria(
    all_vms: list[VMInfo], tag: str | None, vm_pattern: str | None, select_all: bool
) -> tuple[list[VMInfo], str]:
    """Select VMs based on criteria and return (selected_vms, selection_description)."""
    if tag:
        selected_vms = BatchSelector.select_by_tag(all_vms, tag)
        selection_desc = f"tag '{tag}'"
    elif vm_pattern:
        selected_vms = BatchSelector.select_by_pattern(all_vms, vm_pattern)
        selection_desc = f"pattern '{vm_pattern}'"
    else:  # select_all
        selected_vms = all_vms
        selection_desc = "all VMs"
    return selected_vms, selection_desc


def _confirm_batch_operation(num_vms: int, operation: str, confirm: bool) -> bool:
    """Confirm batch operation with user. Returns True if should proceed."""
    if not confirm:
        click.echo(f"\nThis will {operation} {num_vms} VM(s).")
        confirm_input = input("Continue? [y/N]: ").lower()
        if confirm_input not in ["y", "yes"]:
            click.echo("Cancelled.")
            return False
    return True


def _display_batch_summary(batch_result: BatchResult, operation_name: str) -> None:
    """Display batch operation summary."""
    click.echo("\n" + "=" * 80)
    click.echo(f"Batch {operation_name} Summary")
    click.echo("=" * 80)
    click.echo(batch_result.format_summary())
    click.echo("=" * 80)

    if batch_result.failed > 0:
        click.echo("\nFailed VMs:")
        for failure in batch_result.get_failures():
            click.echo(f"  - {failure.vm_name}: {failure.message}")


__all__ = [
    "batch",
    "batch_command",
    "batch_start",
    "batch_stop",
    "batch_sync",
]
