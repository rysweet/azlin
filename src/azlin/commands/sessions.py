"""Session management commands for azlin.

This module provides commands to save and restore VM/tmux session configurations.

Commands:
    - save: Save current VM/session state to file
    - load: Restore VMs from saved session file
    - list: List saved sessions
"""

import logging
import sys

import click
from rich.console import Console
from rich.table import Table

from azlin.commands.monitoring import get_vm_session_pairs
from azlin.config_manager import ConfigManager
from azlin.session_manager import SessionManager, SessionManagerError

logger = logging.getLogger(__name__)

__all__ = ["session_group"]


@click.group(name="sessions")
def session_group():
    """Manage VM/session configurations.

    Save and restore complete development environments including VMs and tmux sessions.

    \b
    Examples:
        azlin sessions save dev-env          # Save current state
        azlin sessions load dev-env          # Restore environment
        azlin sessions list                  # Show saved sessions
    """
    pass


@session_group.command(name="save")
@click.argument("session_name", type=str)
@click.option("--resource-group", "--rg", help="Resource group (default from config)", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def save_command(session_name: str, resource_group: str | None, config: str | None) -> None:
    """Save current VM/session state to file.

    Saves VM configurations and tmux sessions to ~/.azlin/sessions/<session-name>.toml.
    The saved session can be restored later with 'azlin sessions load'.

    \b
    Examples:
        azlin sessions save my-dev-env
        azlin sessions save project-x --rg my-resource-group
    """
    console = Console()

    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            console.print("[red]Error: No resource group specified.[/red]")
            console.print("Use --resource-group or set default in ~/.azlin/config.toml")
            sys.exit(1)

        console.print(f"[dim]Collecting VM/session state from {rg}...[/dim]")

        # Collect current state using existing function
        vm_session_pairs = get_vm_session_pairs(
            resource_group=rg, config_path=config, include_stopped=False
        )

        if not vm_session_pairs:
            console.print("[yellow]No running VMs found to save.[/yellow]")
            sys.exit(1)

        # Save session
        session_file = SessionManager.save_session(
            session_name=session_name, vm_session_pairs=vm_session_pairs, resource_group=rg
        )

        # Display summary
        vm_count = len(vm_session_pairs)
        tmux_count = sum(len(sessions) for _, sessions in vm_session_pairs)

        console.print()
        console.print(f"[green]✓[/green] Saved {vm_count} VMs to [cyan]{session_file}[/cyan]")

        if tmux_count > 0:
            console.print(f"[dim]  ({tmux_count} tmux sessions saved)[/dim]")

    except SessionManagerError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        logger.exception("Session save failed")
        sys.exit(1)


@session_group.command(name="load")
@click.argument("session_name", type=str)
def load_command(session_name: str) -> None:
    """Restore VMs from saved session.

    Loads session configuration and provisions any missing VMs.
    Existing VMs are noted but not modified.

    \b
    Examples:
        azlin sessions load my-dev-env
    """
    console = Console()

    try:
        # Load session file
        console.print(f"[dim]Loading session: {session_name}...[/dim]")
        session_config = SessionManager.load_session(session_name)

        # Display session info
        console.print()
        console.print(f"[bold]Session:[/bold] {session_config.name}")
        console.print(f"[dim]Saved at:[/dim] {session_config.saved_at}")
        console.print(f"[dim]Resource group:[/dim] {session_config.resource_group}")
        console.print(f"[dim]Total VMs:[/dim] {len(session_config.vms)}")
        console.print()

        # Restore VMs
        console.print("[dim]Restoring VMs...[/dim]")

        def progress_callback(msg: str) -> None:
            console.print(f"[dim]  {msg}[/dim]")

        result = SessionManager.restore_session(session_config, progress_callback=progress_callback)

        # Display summary
        console.print()
        console.print("[bold]" + "=" * 70 + "[/bold]")
        console.print("[bold cyan]RESTORE SUMMARY[/bold cyan]")
        console.print("[bold]" + "=" * 70 + "[/bold]")
        console.print()

        # Existing VMs
        if result.existing_vms:
            console.print(f"[green]Existing VMs ({len(result.existing_vms)}):[/green]")
            for vm_name in result.existing_vms:
                console.print(f"  [green]✓[/green] {vm_name}")
            console.print()

        # Created VMs
        if result.created_vms:
            console.print(f"[cyan]Created VMs ({len(result.created_vms)}):[/cyan]")
            for vm_name in result.created_vms:
                console.print(f"  [cyan]+[/cyan] {vm_name}")
            console.print()

        # Failed VMs
        if result.failed_vms:
            console.print(f"[red]Failed VMs ({len(result.failed_vms)}):[/red]")
            for vm_name, error in result.failed_vms:
                console.print(f"  [red]✗[/red] {vm_name}: {error}")
            console.print()

        console.print("[bold]" + "=" * 70 + "[/bold]")
        console.print()

        # Exit code
        if result.failed_vms:
            sys.exit(1)

    except SessionManagerError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        logger.exception("Session load failed")
        sys.exit(1)


@session_group.command(name="list")
def list_sessions_command() -> None:
    """List all saved sessions.

    Shows all session files in ~/.azlin/sessions/.

    \b
    Examples:
        azlin sessions list
    """
    console = Console()

    try:
        sessions = SessionManager.list_sessions()

        if not sessions:
            console.print("[yellow]No saved sessions found.[/yellow]")
            console.print(f"[dim]Sessions are saved to {SessionManager.SESSIONS_DIR}[/dim]")
            return

        # Create table
        table = Table(title="Saved Sessions", show_header=True, header_style="bold")
        table.add_column("Session Name", style="cyan")
        table.add_column("File Path", style="dim")

        for session_name in sorted(sessions):
            session_file = SessionManager.SESSIONS_DIR / f"{session_name}.toml"
            table.add_row(session_name, str(session_file))

        console.print(table)
        console.print()
        console.print(f"[dim]Total: {len(sessions)} sessions[/dim]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Failed to list sessions")
        sys.exit(1)
