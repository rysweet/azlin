"""Docker Compose multi-VM orchestration CLI commands.

This module provides the `azlin compose` command group for deploying
multi-container applications across multiple Azure VMs.

Usage:
    azlin compose up --file docker-compose.azlin.yml
    azlin compose down --file docker-compose.azlin.yml
    azlin compose ps --file docker-compose.azlin.yml

Philosophy:
- Familiar docker-compose CLI interface
- Clear progress reporting
- Fail-fast with actionable errors
"""

import logging
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from azlin.modules.compose import ComposeOrchestrator

logger = logging.getLogger(__name__)
console = Console()


@click.group(name="compose")
def compose_group():
    """Multi-VM docker-compose orchestration commands.

    Deploy and manage multi-container applications across multiple VMs
    using extended docker-compose syntax.

    Example docker-compose.azlin.yml:

    \b
    version: '3.8'
    services:
      web:
        image: nginx:latest
        vm: web-server-1
        ports:
          - "80:80"
      api:
        image: myapi:latest
        vm: api-server-*
        replicas: 3
    """
    pass


@compose_group.command(name="up")
@click.option(
    "--file",
    "-f",
    "compose_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to docker-compose.azlin.yml file",
)
@click.option(
    "--resource-group",
    "-g",
    help="Azure resource group (uses current context if not specified)",
)
def compose_up(compose_file: Path, resource_group: str | None):
    """Deploy services from docker-compose.azlin.yml.

    This command:
    1. Parses the compose file with VM targeting
    2. Resolves VM selectors and plans service placement
    3. Deploys containers across VMs in parallel
    4. Configures inter-service networking
    5. Performs health checks
    """
    try:
        # Resource group is required for compose operations
        if not resource_group:
            console.print(
                "[red]Error:[/red] Resource group must be specified with --resource-group"
            )
            console.print("Example: azlin compose up -f docker-compose.azlin.yml -g my-rg")
            raise click.Abort

        console.print(f"[bold]Deploying services from:[/bold] {compose_file}")
        console.print(f"[bold]Resource group:[/bold] {resource_group}")
        console.print()

        # Create orchestrator
        orchestrator = ComposeOrchestrator(
            compose_file=compose_file,
            resource_group=resource_group,
        )

        # Parse compose file
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Parsing compose file...", total=None)
            services = orchestrator.parse_compose_file()

        console.print(f"[green]✓[/green] Found {len(services)} service(s)")
        console.print()

        # Show service plan
        table = Table(title="Service Deployment Plan")
        table.add_column("Service", style="cyan")
        table.add_column("Image", style="white")
        table.add_column("VM Selector", style="yellow")
        table.add_column("Replicas", justify="right", style="magenta")

        for service_name, service_config in services.items():
            table.add_row(
                service_name,
                service_config.image,
                service_config.vm_selector,
                str(service_config.replicas),
            )

        console.print(table)
        console.print()

        # Deploy services
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Deploying services...", total=None)
            result = orchestrator.deploy()

        # Show results
        if result.success:
            console.print(
                f"[green]✓ Successfully deployed {len(result.deployed_services)} service(s)[/green]"
            )
            console.print()

            # Show deployed services
            deployed_table = Table(title="Deployed Services")
            deployed_table.add_column("Service", style="cyan")
            deployed_table.add_column("VM", style="yellow")
            deployed_table.add_column("IP Address", style="white")
            deployed_table.add_column("Status", style="green")

            for service in result.deployed_services:
                deployed_table.add_row(
                    service.service_name,
                    service.vm_name,
                    service.vm_ip,
                    service.status,
                )

            console.print(deployed_table)

            if result.warnings:
                console.print()
                console.print("[yellow]Warnings:[/yellow]")
                for warning in result.warnings:
                    console.print(f"  [yellow]![/yellow] {warning}")

        else:
            console.print(f"[red]✗ Deployment failed:[/red] {result.error_message}")
            if result.failed_services:
                console.print()
                console.print("[red]Failed services:[/red]")
                for failed in result.failed_services:
                    console.print(f"  [red]✗[/red] {failed}")
            raise click.Abort

    except Exception as e:
        console.print(f"[red]Error:[/red] {e!s}")
        logger.exception("Compose up command failed")
        raise click.Abort from e


@compose_group.command(name="down")
@click.option(
    "--file",
    "-f",
    "compose_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to docker-compose.azlin.yml file",
)
@click.option(
    "--resource-group",
    "-g",
    help="Azure resource group (uses current context if not specified)",
)
def compose_down(compose_file: Path, resource_group: str | None):
    """Stop and remove services deployed from docker-compose.azlin.yml.

    This command tears down all services defined in the compose file.
    """
    console.print("[yellow]compose down: Not yet implemented[/yellow]")
    console.print("This feature will stop and remove deployed containers.")


@compose_group.command(name="ps")
@click.option(
    "--file",
    "-f",
    "compose_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to docker-compose.azlin.yml file",
)
@click.option(
    "--resource-group",
    "-g",
    help="Azure resource group (uses current context if not specified)",
)
def compose_ps(compose_file: Path, resource_group: str | None):
    """Show status of services from docker-compose.azlin.yml.

    This command displays the current status of all deployed services.
    """
    console.print("[yellow]compose ps: Not yet implemented[/yellow]")
    console.print("This feature will show service status and health.")


__all__ = ["compose_group"]
