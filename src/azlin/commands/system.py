"""System-level commands for azlin.

This module provides commands for system operations like help, OS updates,
and development tool updates.

Commands:
    help - Show help for commands
    os-update - Update OS packages on a VM
    update - Update all development tools on a VM
"""

import logging
import sys

import click

from azlin.cli_helpers import _get_ssh_config_for_vm
from azlin.config_manager import ConfigError, ConfigManager
from azlin.modules.progress import ProgressDisplay
from azlin.modules.ssh_keys import SSHKeyError
from azlin.remote_exec import OSUpdateExecutor, RemoteExecError
from azlin.vm_manager import VMManagerError

logger = logging.getLogger(__name__)


@click.command(name="help")
@click.argument("command_name", required=False, type=str)
@click.pass_context
def help_command(ctx: click.Context, command_name: str | None) -> None:
    """Show help for commands.

    Display general help or help for a specific command.

    \b
    Examples:
        azlin help              # Show general help
        azlin help connect      # Show help for connect command
        azlin help list         # Show help for list command
    """
    if command_name is None:
        click.echo(ctx.parent.get_help())
    else:
        # Show help for specific command
        cmd = ctx.parent.command.commands.get(command_name)  # type: ignore[union-attr]

        if cmd is None:
            click.echo(f"Error: No such command '{command_name}'.", err=True)
            ctx.exit(1)

        # Create a context for the command and show its help
        cmd_ctx = click.Context(cmd, info_name=command_name, parent=ctx.parent)  # type: ignore[arg-type]
        click.echo(cmd.get_help(cmd_ctx))  # type: ignore[union-attr]


@click.command(name="os-update")
@click.argument("vm_identifier", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--timeout", help="Timeout in seconds (default 300)", type=int, default=300)
def os_update(vm_identifier: str, resource_group: str | None, config: str | None, timeout: int):
    """Update OS packages on a VM.

    Runs 'apt update && apt upgrade -y' on Ubuntu VMs to update all packages.

    VM_IDENTIFIER can be:
    - Session name (resolved to VM)
    - VM name (requires --resource-group or default config)
    - IP address (direct connection)

    \b
    Examples:
        azlin os-update my-session
        azlin os-update azlin-myvm --rg my-resource-group
        azlin os-update 20.1.2.3
        azlin os-update my-vm --timeout 600  # 10 minute timeout
    """
    try:
        # Get SSH config for VM
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        click.echo(f"Updating OS packages on {vm_identifier}...")
        click.echo("This may take several minutes...\n")

        # Execute OS update
        result = OSUpdateExecutor.execute_os_update(ssh_config, timeout=timeout)

        # Format and display output
        output = OSUpdateExecutor.format_output(result)
        click.echo(output)

        # Exit with appropriate code
        if not result.success:
            sys.exit(1)

    except RemoteExecError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except SSHKeyError as e:
        click.echo(f"SSH key error: {e}", err=True)
        sys.exit(1)
    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@click.command(name="update")
@click.argument("vm_identifier", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--timeout", help="Timeout per update in seconds", type=int, default=300)
def update(vm_identifier: str, resource_group: str | None, config: str | None, timeout: int):
    """Update all development tools on a VM.

    Updates system packages, programming languages, CLIs, and other dev tools
    that were installed during VM provisioning.

    VM_IDENTIFIER can be:
    - VM name (requires --resource-group or default config)
    - Session name (will be resolved to VM name)
    - IP address (direct connection)

    Tools updated:
    - System packages (apt)
    - Azure CLI
    - GitHub CLI
    - npm and npm packages (Copilot, Codex, Claude Code)
    - Rust toolchain
    - astral-uv

    \b
    Examples:
        # Update VM by name
        azlin update my-vm

        # Update VM by session name
        azlin update my-project

        # Update VM by IP
        azlin update 20.1.2.3

        # Update with custom timeout (default 300s per tool)
        azlin update my-vm --timeout 600

        # Update with explicit resource group
        azlin update my-vm --rg my-resource-group
    """
    from azlin.vm_updater import VMUpdater, VMUpdaterError

    try:
        # Resolve VM identifier to SSH config
        # Try session name first, then VM name, then IP
        original_identifier = vm_identifier

        # Try to resolve as session name
        try:
            session_vm = ConfigManager.get_vm_name_by_session(vm_identifier, config)
            if session_vm:
                vm_identifier = session_vm
                click.echo(f"Resolved session '{original_identifier}' to VM '{vm_identifier}'")
        except Exception as e:
            logger.debug(f"Not a session name, trying as VM name or IP: {e}")

        # Get SSH config for VM
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        # Display info
        display_name = (
            original_identifier if original_identifier != vm_identifier else vm_identifier
        )
        click.echo(f"\nUpdating tools on {display_name}...")
        click.echo("This may take several minutes.\n")

        # Create progress display
        progress = ProgressDisplay()

        # Create updater with progress callback
        def progress_callback(message: str):
            click.echo(f"  {message}")

        updater = VMUpdater(
            ssh_config=ssh_config, timeout=timeout, progress_callback=progress_callback
        )

        # Perform update
        progress.start_operation("Updating VM tools", estimated_seconds=180)
        summary = updater.update_vm()
        progress.complete(
            success=summary.all_succeeded,
            message=f"Update completed in {summary.total_duration:.1f}s",
        )

        # Display results
        click.echo("\n" + "=" * 60)
        click.echo("UPDATE SUMMARY")
        click.echo("=" * 60)

        if summary.successful:
            click.echo(f"\n✓ Successful updates ({len(summary.successful)}):")
            for result in summary.successful:
                click.echo(f"  {result.tool_name:<20} {result.duration:>6.1f}s")

        if summary.failed:
            click.echo(f"\n✗ Failed updates ({len(summary.failed)}):")
            for result in summary.failed:
                click.echo(f"  {result.tool_name:<20} {result.message[:40]}")

        click.echo(f"\nTotal time: {summary.total_duration:.1f}s")
        click.echo("=" * 60 + "\n")

        # Exit with appropriate code
        if summary.all_succeeded:
            click.echo("All updates completed successfully!")
            sys.exit(0)
        elif summary.any_failed:
            if summary.success_count > 0:
                click.echo(
                    f"Partial success: {summary.success_count}/{summary.total_updates} updates succeeded"
                )
                sys.exit(1)
            else:
                click.echo("All updates failed!")
                sys.exit(2)

    except VMUpdaterError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in update command")
        sys.exit(1)


__all__ = [
    "help_command",
    "os_update",
    "update",
]
