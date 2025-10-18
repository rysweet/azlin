"""Prune operations command for azlin CLI.

This module provides the prune command for cleaning up idle VMs.
"""

import sys

import click

from azlin.config_manager import ConfigManager
from azlin.prune import PruneManager
from azlin.vm_manager import VMManagerError


def register_prune_command(main: click.Group) -> None:
    """Register prune command with main CLI group.

    Args:
        main: The main CLI group to register commands with
    """

    @main.command()
    @click.option("--resource-group", "--rg", help="Resource group", type=str)
    @click.option("--config", help="Config file path", type=click.Path())
    @click.option(
        "--age-days", default=1, help="Minimum VM age in days (default: 1)", type=int
    )
    @click.option(
        "--idle-days", default=1, help="Minimum idle time in days (default: 1)", type=int
    )
    @click.option("--dry-run", is_flag=True, help="Preview without deleting")
    @click.option("--force", is_flag=True, help="Skip confirmation prompt")
    @click.option("--include-running", is_flag=True, help="Include running VMs")
    @click.option("--include-named", is_flag=True, help="Include named sessions")
    def prune(
        resource_group: str | None,
        config: str | None,
        age_days: int,
        idle_days: int,
        dry_run: bool,
        force: bool,
        include_running: bool,
        include_named: bool,
    ):
        """Prune inactive VMs based on age and idle time.

        Identifies and optionally deletes VMs that are:
        - Older than --age-days (default: 1)
        - Idle for longer than --idle-days (default: 1)
        - Stopped/deallocated (unless --include-running)
        - Without named sessions (unless --include-named)

        \b
        Examples:
            azlin prune --dry-run                    # Preview what would be deleted
            azlin prune                              # Delete VMs idle for 1+ days (default)
            azlin prune --age-days 7 --idle-days 3   # Custom thresholds
            azlin prune --force                      # Skip confirmation
            azlin prune --include-running            # Include running VMs
        """
        try:
            # Get resource group
            rg = ConfigManager.get_resource_group(resource_group, config)

            if not rg:
                click.echo("Error: No resource group specified.", err=True)
                click.echo("Set default with: azlin config set default_resource_group <name>")
                click.echo("Or specify with --resource-group option.")
                sys.exit(1)

            # Get candidates (single API call)
            candidates, connection_data = PruneManager.get_candidates(
                resource_group=rg,
                age_days=age_days,
                idle_days=idle_days,
                include_running=include_running,
                include_named=include_named,
            )

            # If no candidates, exit early
            if not candidates:
                click.echo("No VMs eligible for pruning.")
                return

            # Display table
            table = PruneManager.format_prune_table(candidates, connection_data)
            click.echo("\n" + table + "\n")

            # In dry-run mode, just show what would be deleted
            if dry_run:
                click.echo(f"DRY RUN: {len(candidates)} VM(s) would be deleted.")
                click.echo("Run without --dry-run to actually delete these VMs.")
                return

            # If not force mode, ask for confirmation
            if not force:
                click.echo(f"This will delete {len(candidates)} VM(s) and their associated resources.")
                click.echo("This action cannot be undone.\n")

                if not click.confirm(
                    f"Are you sure you want to delete {len(candidates)} VM(s)?", default=False
                ):
                    click.echo("Cancelled.")
                    return

            # Execute deletion
            click.echo(f"\nDeleting {len(candidates)} VM(s)...")
            result = PruneManager.execute_prune(candidates, rg)

            # Display deletion summary
            deleted = result["deleted"]
            failed = result["failed"]

            click.echo("\n" + "=" * 80)
            click.echo("Deletion Summary")
            click.echo("=" * 80)
            click.echo(f"Total VMs:     {len(candidates)}")
            click.echo(f"Succeeded:     {deleted}")
            click.echo(f"Failed:        {failed}")
            click.echo("=" * 80)

            # Show errors if any
            if result["errors"]:
                click.echo("\nErrors:")
                for error in result["errors"]:
                    click.echo(f"  - {error}")

            # Exit with error code if any failed
            if failed > 0:
                sys.exit(1)

        except VMManagerError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        except KeyboardInterrupt:
            click.echo("\nCancelled by user.")
            sys.exit(130)
        except Exception as e:
            click.echo(f"Unexpected error: {e}", err=True)
            sys.exit(1)
