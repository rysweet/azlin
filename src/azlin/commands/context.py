"""Context command group for azlin.

This module provides kubectl-style context management commands:
- list: List all contexts
- current: Show current context
- use: Switch to a context
- create: Create new context
- delete: Delete context
- rename: Rename context
- migrate: Migrate from legacy config format

Security:
- No secrets stored (only references to auth profiles)
- All UUIDs validated
- Config file permissions enforced
"""

import logging
import sys

import click
from rich.console import Console
from rich.table import Table

from azlin.click_group import AzlinGroup
from azlin.context_manager import Context, ContextError, ContextManager

logger = logging.getLogger(__name__)
console = Console()


@click.group(name="context", cls=AzlinGroup)
def context_group():
    """Manage kubectl-style contexts for multi-tenant Azure access.

    Contexts allow you to switch between different Azure subscriptions
    and tenants without changing environment variables or config files.

    Each context contains:
    - subscription_id: Azure subscription ID
    - tenant_id: Azure tenant ID
    - auth_profile: Optional service principal profile

    \b
    EXAMPLES:
        # List all contexts
        $ azlin context list

        # Show current context
        $ azlin context current

        # Switch to a context
        $ azlin context use production

        # Create new context
        $ azlin context create staging \\
            --subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \\
            --tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy

        # Create context with auth profile
        $ azlin context create prod \\
            --subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \\
            --tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy \\
            --auth-profile prod-sp

        # Rename context
        $ azlin context rename old-name new-name

        # Delete context
        $ azlin context delete staging

        # Migrate from legacy config
        $ azlin context migrate
    """
    pass


@context_group.command(name="list")
@click.option("--config", help="Custom config file path")
def list_contexts(config: str | None):
    """List all available contexts.

    Shows all configured contexts with their subscription and tenant IDs.
    The current context is marked with an asterisk (*).

    \b
    EXAMPLES:
        $ azlin context list
        $ azlin context list --config ~/custom-config.toml
    """
    try:
        context_config = ContextManager.load(config)

        if not context_config.contexts:
            console.print("[yellow]No contexts configured.[/yellow]")
            console.print("\nCreate a context with:")
            console.print("  azlin context create <name> --subscription <id> --tenant <id>")
            return

        # Create rich table
        table = Table(title="Azlin Contexts")
        table.add_column("Current", style="cyan", width=8)
        table.add_column("Name", style="green", width=20)
        table.add_column("Subscription ID", style="blue", width=38)
        table.add_column("Tenant ID", style="blue", width=38)
        table.add_column("Auth Profile", style="yellow", width=15)

        # Add rows
        for name, ctx in sorted(context_config.contexts.items()):
            current_marker = "*" if name == context_config.current else ""
            auth_profile = ctx.auth_profile or "-"

            table.add_row(
                current_marker,
                name,
                ctx.subscription_id,
                ctx.tenant_id,
                auth_profile,
            )

        console.print(table)

    except ContextError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        logger.error(f"Failed to list contexts: {e}", exc_info=True)
        sys.exit(1)


@context_group.command(name="current")
@click.option("--config", help="Custom config file path")
def show_current(config: str | None):
    """Show current active context.

    Displays the name and details of the currently active context.

    \b
    EXAMPLES:
        $ azlin context current
        $ azlin context current --config ~/custom-config.toml
    """
    try:
        context_config = ContextManager.load(config)

        if context_config.current is None:
            console.print("[yellow]No current context set.[/yellow]")
            console.print("\nSet a context with:")
            console.print("  azlin context use <name>")
            return

        current_ctx = context_config.get_current_context()
        if current_ctx is None:
            console.print(f"[red]Error:[/red] Current context '{context_config.current}' not found")
            sys.exit(1)

        # Display current context
        console.print(f"[green]Current context:[/green] {current_ctx.name}")
        console.print(f"  Subscription ID: {current_ctx.subscription_id}")
        console.print(f"  Tenant ID: {current_ctx.tenant_id}")
        if current_ctx.auth_profile:
            console.print(f"  Auth Profile: {current_ctx.auth_profile}")
        if current_ctx.description:
            console.print(f"  Description: {current_ctx.description}")

    except ContextError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        logger.error(f"Failed to show current context: {e}", exc_info=True)
        sys.exit(1)


@context_group.command(name="use")
@click.argument("name")
@click.option("--config", help="Custom config file path")
def use_context(name: str, config: str | None):
    """Switch to a different context.

    Sets the specified context as the current active context. All subsequent
    azlin commands will use this context's subscription and tenant.

    \b
    EXAMPLES:
        $ azlin context use production
        $ azlin context use dev --config ~/custom-config.toml
    """
    try:
        context_config = ContextManager.load(config)

        # Validate context exists
        if name not in context_config.contexts:
            available = list(context_config.contexts.keys())
            console.print(f"[red]Error:[/red] Context '{name}' not found")
            if available:
                console.print(f"\nAvailable contexts: {', '.join(available)}")
            sys.exit(1)

        # Set current context
        context_config.set_current_context(name)

        # Save config
        ContextManager.save(context_config, config)

        console.print(f"[green]Switched to context:[/green] {name}")

        # Show context details
        ctx = context_config.contexts[name]
        console.print(f"  Subscription ID: {ctx.subscription_id}")
        console.print(f"  Tenant ID: {ctx.tenant_id}")
        if ctx.auth_profile:
            console.print(f"  Auth Profile: {ctx.auth_profile}")

    except ContextError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        logger.error(f"Failed to use context: {e}", exc_info=True)
        sys.exit(1)


@context_group.command(name="create")
@click.argument("name")
@click.option(
    "--subscription",
    "--subscription-id",
    required=True,
    help="Azure subscription ID (UUID)",
)
@click.option(
    "--tenant",
    "--tenant-id",
    required=True,
    help="Azure tenant ID (UUID)",
)
@click.option(
    "--auth-profile",
    help="Service principal auth profile name (optional)",
)
@click.option(
    "--description",
    help="Human-readable description (optional)",
)
@click.option(
    "--set-current",
    is_flag=True,
    help="Set as current context after creation",
)
@click.option("--config", help="Custom config file path")
def create_context(
    name: str,
    subscription: str,
    tenant: str,
    auth_profile: str | None,
    description: str | None,
    set_current: bool,
    config: str | None,
):
    """Create a new context.

    Creates a new context with the specified subscription and tenant IDs.
    Optionally associates an authentication profile for service principal auth.

    \b
    EXAMPLES:
        # Basic context
        $ azlin context create staging \\
            --subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \\
            --tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy

        # With auth profile
        $ azlin context create prod \\
            --subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \\
            --tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy \\
            --auth-profile prod-sp

        # With description and set as current
        $ azlin context create dev \\
            --subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \\
            --tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy \\
            --description "Development environment" \\
            --set-current
    """
    try:
        # Load existing config
        context_config = ContextManager.load(config)

        # Check if context already exists
        if name in context_config.contexts:
            console.print(f"[red]Error:[/red] Context '{name}' already exists")
            console.print("\nUse a different name or delete the existing context:")
            console.print(f"  azlin context delete {name}")
            sys.exit(1)

        # Create new context (validation happens in __post_init__)
        new_context = Context(
            name=name,
            subscription_id=subscription,
            tenant_id=tenant,
            auth_profile=auth_profile,
            description=description,
        )

        # Add to config
        context_config.add_context(new_context)

        # Set as current if requested
        if set_current:
            context_config.set_current_context(name)

        # Save config
        ContextManager.save(context_config, config)

        console.print(f"[green]Created context:[/green] {name}")
        console.print(f"  Subscription ID: {subscription}")
        console.print(f"  Tenant ID: {tenant}")
        if auth_profile:
            console.print(f"  Auth Profile: {auth_profile}")
        if description:
            console.print(f"  Description: {description}")
        if set_current:
            console.print("\n[green]Set as current context[/green]")

    except ContextError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        logger.error(f"Failed to create context: {e}", exc_info=True)
        sys.exit(1)


@context_group.command(name="delete")
@click.argument("name")
@click.option("--config", help="Custom config file path")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
def delete_context(name: str, config: str | None, force: bool):
    """Delete a context.

    Removes the specified context from the configuration. If the context
    is currently active, the current context will be unset.

    \b
    EXAMPLES:
        $ azlin context delete staging
        $ azlin context delete old-context --force
        $ azlin context delete test --config ~/custom-config.toml
    """
    try:
        # Load config
        context_config = ContextManager.load(config)

        # Check if context exists
        if name not in context_config.contexts:
            console.print(f"[red]Error:[/red] Context '{name}' not found")
            available = list(context_config.contexts.keys())
            if available:
                console.print(f"\nAvailable contexts: {', '.join(available)}")
            sys.exit(1)

        # Confirm deletion unless --force
        if not force:
            ctx = context_config.contexts[name]
            console.print(f"[yellow]About to delete context:[/yellow] {name}")
            console.print(f"  Subscription ID: {ctx.subscription_id}")
            console.print(f"  Tenant ID: {ctx.tenant_id}")
            if name == context_config.current:
                console.print("\n[yellow]Warning:[/yellow] This is the current context")

            if not click.confirm("\nAre you sure?", default=False):
                console.print("Cancelled")
                return

        # Delete context
        context_config.delete_context(name)

        # Save config
        ContextManager.save(context_config, config)

        console.print(f"[green]Deleted context:[/green] {name}")
        if name == context_config.current:
            console.print("[yellow]Current context has been unset[/yellow]")
            console.print("\nSet a new current context with:")
            console.print("  azlin context use <name>")

    except ContextError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        logger.error(f"Failed to delete context: {e}", exc_info=True)
        sys.exit(1)


@context_group.command(name="rename")
@click.argument("old_name")
@click.argument("new_name")
@click.option("--config", help="Custom config file path")
def rename_context(old_name: str, new_name: str, config: str | None):
    """Rename a context.

    Changes the name of an existing context. If the context is currently
    active, the current context pointer is updated automatically.

    \b
    EXAMPLES:
        $ azlin context rename staging stage
        $ azlin context rename old-prod production
        $ azlin context rename dev development --config ~/custom-config.toml
    """
    try:
        # Load config
        context_config = ContextManager.load(config)

        # Rename (validation happens in method)
        context_config.rename_context(old_name, new_name)

        # Save config
        ContextManager.save(context_config, config)

        console.print(f"[green]Renamed context:[/green] {old_name} -> {new_name}")
        if context_config.current == new_name:
            console.print("[green]Current context updated[/green]")

    except ContextError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        logger.error(f"Failed to rename context: {e}", exc_info=True)
        sys.exit(1)


@context_group.command(name="migrate")
@click.option("--config", help="Custom config file path")
@click.option("--force", "-f", is_flag=True, help="Force migration even if contexts exist")
def migrate_legacy(config: str | None, force: bool):
    """Migrate from legacy config format.

    Checks for legacy subscription_id and tenant_id fields in config.toml
    and creates a 'default' context from them. This provides backward
    compatibility with existing azlin configurations.

    The legacy fields are preserved for backward compatibility with older
    azlin versions.

    \b
    EXAMPLES:
        $ azlin context migrate
        $ azlin context migrate --config ~/custom-config.toml
        $ azlin context migrate --force
    """
    try:
        # Attempt migration
        migrated = ContextManager.migrate_from_legacy(config)

        if migrated:
            console.print("[green]Migration successful![/green]")
            console.print("\nCreated 'default' context from legacy config:")
            console.print("  Run 'azlin context list' to see all contexts")
            console.print("  Run 'azlin context current' to see current context")
        else:
            console.print("[yellow]No migration needed[/yellow]")
            console.print("\nPossible reasons:")
            console.print("  - Config already has contexts")
            console.print("  - No legacy subscription_id/tenant_id found")
            console.print("  - Config file doesn't exist")

    except ContextError as e:
        console.print(f"[red]Migration failed:[/red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        logger.error(f"Failed to migrate: {e}", exc_info=True)
        sys.exit(1)


__all__ = ["context_group"]
