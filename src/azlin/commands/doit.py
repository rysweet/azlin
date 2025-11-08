"""DoIt command - autonomous infrastructure deployment."""

import sys
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
    """Check status of a deployment session.

    TODO: Implement session tracking.
    """
    console = Console()
    console.print("[yellow]Session status tracking not yet implemented[/yellow]")
    console.print("For now, use: az group list --output table")


@doit_group.command(name="list")
def list_command():
    """List recent deployment sessions.

    TODO: Implement session listing.
    """
    console = Console()
    console.print("[yellow]Session listing not yet implemented[/yellow]")


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
