"""DoIt command - autonomous infrastructure deployment."""

import sys
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console

from azlin.doit import DoItOrchestrator


@click.group(name="doit")
def doit_group():
    """Autonomous Azure infrastructure deployment.

    Use natural language to describe your infrastructure needs,
    and doit will autonomously deploy it using Azure CLI.
    """
    pass


@doit_group.command(name="deploy")
@click.argument("request", required=True)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    help="Output directory for generated artifacts",
)
@click.option(
    "--max-iterations",
    "-m",
    type=int,
    default=50,
    help="Maximum execution iterations",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be deployed without actually deploying",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Reduce output verbosity",
)
def deploy_command(
    request: str,
    output_dir: Path | None,
    max_iterations: int,
    dry_run: bool,
    quiet: bool,
):
    """Deploy infrastructure from natural language request.

    Examples:

        azlin doit deploy "Give me App Service with Cosmos DB"

        azlin doit deploy "Create App Service, Cosmos DB, API Management, Storage, and KeyVault all connected"

        azlin doit deploy "Deploy a web app with database in eastus" --dry-run

    The agent will:
    1. Parse your request into concrete goals
    2. Determine dependencies between resources
    3. Execute deployment using Azure CLI
    4. Verify each step succeeded
    5. Generate production-ready Terraform and Bicep
    6. Provide teaching materials explaining what was done
    """
    console = Console()

    try:
        # Initialize orchestrator
        orchestrator = DoItOrchestrator(
            output_dir=output_dir,
            max_iterations=max_iterations,
            dry_run=dry_run,
            verbose=not quiet,
        )

        # Execute deployment
        state = orchestrator.execute(request)

        # Exit code based on success
        if state.phase.value == "completed":
            console.print("\n[bold green]✓ Deployment completed successfully[/bold green]")
            sys.exit(0)
        else:
            console.print("\n[bold red]✗ Deployment failed or incomplete[/bold red]")
            sys.exit(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]Deployment interrupted by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        if not quiet:
            import traceback

            traceback.print_exc()
        sys.exit(1)


@doit_group.command(name="status")
@click.option(
    "--session",
    "-s",
    help="Session ID to check status",
)
def status_command(session: str | None):
    """Check deployment status using Azure CLI.

    Provides guidance on checking your deployed resources using the Azure CLI.
    For detailed resource information, use 'azlin doit list' instead.
    """
    console = Console()
    console.print("[yellow]For deployment status, use Azure CLI directly:[/yellow]")
    console.print("  az group list --output table")
    console.print("\n[cyan]Or use azlin doit commands:[/cyan]")
    console.print("  azlin doit list        # List all doit-created resources")
    console.print("  azlin doit show <id>   # Show detailed resource info")


@doit_group.command(name="list")
@click.option(
    "--username",
    "-u",
    help="Azure username to filter by (defaults to current user)",
)
def list_command(username: str | None):
    """List all resources created by doit.

    Shows all Azure resources tagged with azlin-doit-owner.
    By default, lists resources for the current Azure user.

    Examples:

        azlin doit list

        azlin doit list --username user@example.com
    """
    console = Console()

    try:
        from rich.table import Table

        from azlin.doit.manager import ResourceManager

        # Initialize resource manager
        manager = ResourceManager(username=username)

        console.print(f"\n[bold]Doit Resources for:[/bold] {manager.username}\n")

        # Get resources
        resources = manager.list_resources()

        if not resources:
            console.print("[yellow]No doit-created resources found[/yellow]")
            return

        # Create table
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Name", style="green")
        table.add_column("Type", style="blue")
        table.add_column("Resource Group", style="magenta")
        table.add_column("Location", style="yellow")
        table.add_column("Created", style="dim")

        for resource in resources:
            # Parse type to show friendly name
            resource_type = resource["type"].split("/")[-1]
            created = resource.get("created", "unknown")
            if created and created != "unknown":
                try:
                    # Try to format ISO timestamp
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    created = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass

            table.add_row(
                resource["name"],
                resource_type,
                resource["resource_group"],
                resource["location"],
                created,
            )

        console.print(table)
        console.print(f"\n[bold]Total:[/bold] {len(resources)} resources\n")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


@doit_group.command(name="show")
@click.argument("resource_id", required=True)
def show_command(resource_id: str):
    """Show detailed information about a doit-created resource.

    Provide the full Azure resource ID to see detailed information.

    Examples:

        azlin doit show /subscriptions/.../resourceGroups/rg-name/providers/Microsoft.Web/sites/my-app
    """
    console = Console()

    try:
        from rich.json import JSON

        from azlin.doit.manager import ResourceManager

        manager = ResourceManager()

        # Get resource details
        console.print("\n[bold]Resource Details:[/bold]\n")
        details = manager.get_resource_details(resource_id)

        # Pretty print JSON
        json_str = JSON.from_data(details)
        console.print(json_str)

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


@doit_group.command(name="cleanup")
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Skip confirmation prompt",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be deleted without deleting",
)
@click.option(
    "--username",
    "-u",
    help="Azure username to filter by (defaults to current user)",
)
def cleanup_command(force: bool, dry_run: bool, username: str | None):
    """Delete all doit-created resources.

    By default, prompts for confirmation before deleting.
    Resources are deleted in dependency order (data resources last).

    Examples:

        azlin doit cleanup

        azlin doit cleanup --force

        azlin doit cleanup --dry-run
    """
    console = Console()

    try:
        from rich.table import Table

        from azlin.doit.manager import ResourceManager

        manager = ResourceManager(username=username)

        console.print(f"\n[bold]Cleanup Doit Resources for:[/bold] {manager.username}\n")

        # List resources first
        resources = manager.list_resources()

        if not resources:
            console.print("[yellow]No doit-created resources found to delete[/yellow]")
            return

        # Show what will be deleted
        console.print(f"[bold yellow]Found {len(resources)} resources to delete:[/bold yellow]\n")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Name", style="green")
        table.add_column("Type", style="blue")
        table.add_column("Resource Group", style="magenta")

        for resource in resources:
            resource_type = resource["type"].split("/")[-1]
            table.add_row(
                resource["name"],
                resource_type,
                resource["resource_group"],
            )

        console.print(table)

        # Confirm unless force or dry-run
        if not force and not dry_run:
            console.print(
                "\n[bold red]WARNING:[/bold red] This will permanently delete all listed resources!"
            )
            response = click.prompt(
                "\nAre you sure you want to continue? [y/N]",
                type=str,
                default="n",
            )
            if response.lower() not in ["y", "yes"]:
                console.print("[yellow]Cleanup cancelled[/yellow]")
                return

        # Perform cleanup
        if dry_run:
            console.print("\n[bold cyan]DRY RUN - No resources will be deleted[/bold cyan]")

        console.print("\n[bold]Deleting resources...[/bold]\n")

        result = manager.cleanup_resources(force=True, dry_run=dry_run)

        # Show results
        if result["deleted"]:
            console.print(
                f"\n[bold green]Successfully deleted {len(result['deleted'])} resources:[/bold green]"
            )
            for res in result["deleted"]:
                status = "[dim](would delete)[/dim]" if dry_run else ""
                console.print(f"  [green]✓[/green] {res['name']} {status}")

        if result["failed"]:
            console.print(
                f"\n[bold red]Failed to delete {len(result['failed'])} resources:[/bold red]"
            )
            for res in result["failed"]:
                console.print(f"  [red]✗[/red] {res['name']}: {res.get('error', 'Unknown error')}")

        console.print("\n[bold]Summary:[/bold]")
        console.print(f"  Total resources: {result['total_resources']}")
        console.print(f"  Successfully deleted: {result['successfully_deleted']}")
        console.print(f"  Failed: {result['failed_count']}\n")

        if result["failed_count"] > 0:
            sys.exit(1)

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


# Aliases for cleanup
@doit_group.command(name="destroy")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted")
@click.option("--username", "-u", help="Azure username to filter by")
@click.pass_context
def destroy_command(ctx, force: bool, dry_run: bool, username: str | None):
    """Alias for cleanup - delete all doit-created resources."""
    ctx.invoke(cleanup_command, force=force, dry_run=dry_run, username=username)


@doit_group.command(name="delete")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted")
@click.option("--username", "-u", help="Azure username to filter by")
@click.pass_context
def delete_command(ctx, force: bool, dry_run: bool, username: str | None):
    """Alias for cleanup - delete all doit-created resources."""
    ctx.invoke(cleanup_command, force=force, dry_run=dry_run, username=username)


@doit_group.command(name="examples")
def examples_command():
    """Show example requests."""
    console = Console()

    console.print("\n[bold cyan]azlin doit - Example Requests[/bold cyan]\n")

    examples = [
        {
            "title": "Simple Web App + Database",
            "request": "Give me App Service with Cosmos DB",
            "description": "Deploys: Resource Group, App Service, Cosmos DB, Key Vault, connections",
        },
        {
            "title": "Complete API Platform",
            "request": "Create App Service, Cosmos DB, API Management, Storage, and KeyVault all connected",
            "description": "Full API platform with gateway, storage, and secure connections",
        },
        {
            "title": "Microservices Backend",
            "request": "Deploy 3 App Services behind API Management with shared Cosmos DB",
            "description": "Multiple services fronted by APIM gateway",
        },
        {
            "title": "Serverless Function App",
            "request": "Create Function App with Storage Account and Key Vault",
            "description": "Serverless compute with storage and secrets",
        },
        {
            "title": "Regional Deployment",
            "request": "Give me App Service with Cosmos DB in westus",
            "description": "Specify region for deployment",
        },
        {
            "title": "Production Setup",
            "request": "Create production App Service with Cosmos DB, APIM, and Storage",
            "description": "Production-grade configuration with appropriate SKUs",
        },
    ]

    for ex in examples:
        console.print(f"[bold green]■[/bold green] {ex['title']}")
        console.print(f"  [cyan]Request:[/cyan] {ex['request']}")
        console.print(f"  [dim]{ex['description']}[/dim]\n")

    console.print("[bold]Usage:[/bold]")
    console.print('  azlin doit deploy "<your request here>"\n')
    console.print("[bold]Options:[/bold]")
    console.print("  --dry-run      Show what would be deployed")
    console.print("  --output-dir   Custom output directory")
    console.print("  --quiet        Less verbose output\n")


# Alias for backward compatibility
do = doit_group

__all__ = ["doit_group", "do"]
