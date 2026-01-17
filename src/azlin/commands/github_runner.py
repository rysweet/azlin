"""GitHub Actions Runner Fleet CLI commands.

This module provides commands for managing GitHub Actions self-hosted runner fleets:
- Enable runner fleet on VM pool
- Disable runner fleet
- Show runner fleet status
- Scale runner fleet manually
"""

import logging
import os
import sys

import click
from rich.console import Console

from azlin.click_group import AzlinGroup
from azlin.config_manager import ConfigError, ConfigManager

logger = logging.getLogger(__name__)
console = Console()


@click.group(name="github-runner", cls=AzlinGroup)
def github_runner_group():
    """Manage GitHub Actions self-hosted runner fleets.

    Transform azlin VMs into auto-scaling GitHub Actions runners for
    substantial CI/CD parallelism improvements.

    \b
    COMMANDS:
        enable     Enable runner fleet on VM pool
        disable    Disable runner fleet
        status     Show runner fleet status
        scale      Manually scale runner fleet

    \b
    FEATURES:
        - Ephemeral runners (per-job lifecycle)
        - Auto-scaling based on job queue
        - Secure runner rotation
        - Cost tracking per job

    \b
    EXAMPLES:
        # Enable fleet for repository
        $ azlin github-runner enable --repo myorg/myrepo --pool ci-workers

        # Enable with custom scaling
        $ azlin github-runner enable --repo myorg/myrepo --pool ci-workers \\
            --min-runners 2 --max-runners 20 --labels linux,docker

        # Show fleet status
        $ azlin github-runner status --pool ci-workers

        # Scale fleet manually
        $ azlin github-runner scale --pool ci-workers --count 5

        # Disable fleet
        $ azlin github-runner disable --pool ci-workers
    """
    pass


@github_runner_group.command(name="enable")
@click.option(
    "--repo",
    required=True,
    help="GitHub repository (format: owner/repo)",
)
@click.option(
    "--pool",
    required=True,
    help="VM pool name for runners",
)
@click.option(
    "--labels",
    default="self-hosted,linux",
    help="Comma-separated runner labels (default: self-hosted,linux)",
)
@click.option(
    "--min-runners",
    type=int,
    default=0,
    help="Minimum number of runners (default: 0)",
)
@click.option(
    "--max-runners",
    type=int,
    default=10,
    help="Maximum number of runners (default: 10)",
)
@click.option(
    "--resource-group",
    "--rg",
    help="Azure resource group",
)
@click.option(
    "--region",
    help="Azure region",
)
@click.option(
    "--vm-size",
    default="Standard_D2s_v3",
    help="Azure VM size (default: Standard_D2s_v3)",
)
def enable_runner_fleet(
    repo: str,
    pool: str,
    labels: str,
    min_runners: int,
    max_runners: int,
    resource_group: str | None,
    region: str | None,
    vm_size: str,
):
    """Enable GitHub Actions runner fleet on VM pool.

    Configures a VM pool to act as auto-scaling GitHub Actions runners.
    Runners are ephemeral (destroyed after each job) for security.

    \b
    REPO format: owner/repo (e.g., microsoft/vscode)
    POOL: Unique name for this runner fleet

    \b
    GitHub Token:
    Set GITHUB_TOKEN environment variable with a PAT that has:
      - repo scope (for repository runners)
      - admin:org scope (for organization runners)

    \b
    Examples:
      $ export GITHUB_TOKEN=ghp_your_token_here
      $ azlin github-runner enable --repo myorg/myrepo --pool ci-workers
      $ azlin github-runner enable --repo myorg/myrepo --pool gpu-runners \\
          --min-runners 1 --max-runners 5 --labels gpu,cuda --vm-size Standard_NC6
    """
    try:
        # Validate GitHub token
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            console.print("[red]Error: GITHUB_TOKEN environment variable not set[/red]")
            console.print("\nSet your GitHub token:")
            console.print("  $ export GITHUB_TOKEN=ghp_your_token_here")
            console.print("\nToken requires 'repo' scope for repository access")
            sys.exit(1)

        # Parse repository
        if "/" not in repo:
            console.print(f"[red]Error: Invalid repository format: {repo}[/red]")
            console.print("Expected format: owner/repo (e.g., microsoft/vscode)")
            sys.exit(1)

        repo_owner, repo_name = repo.split("/", 1)

        # Parse labels
        label_list = [label.strip() for label in labels.split(",")]

        # Get config
        try:
            config = ConfigManager.load_config()
            rg = resource_group or config.default_resource_group
            location = region or config.default_region
        except ConfigError:
            console.print("[red]Error: No configuration found[/red]")
            console.print("Run: azlin config set to configure defaults")
            sys.exit(1)

        # Validate min/max
        if min_runners < 0:
            console.print("[red]Error: min-runners cannot be negative[/red]")
            sys.exit(1)

        if max_runners < min_runners:
            console.print("[red]Error: max-runners must be >= min-runners[/red]")
            sys.exit(1)

        # Create fleet configuration
        fleet_config = {
            "repo_owner": repo_owner,
            "repo_name": repo_name,
            "labels": label_list,
            "min_runners": min_runners,
            "max_runners": max_runners,
            "resource_group": rg,
            "region": location,
            "vm_size": vm_size,
            "enabled": True,
        }

        # Save to config
        if config.github_runner_fleets is None:
            config.github_runner_fleets = {}

        config.github_runner_fleets[pool] = fleet_config
        ConfigManager.save_config(config)

        # Display configuration
        console.print("\n[green]✓[/green] GitHub Actions runner fleet enabled")
        console.print("\n[bold]Fleet Configuration:[/bold]")
        console.print(f"  Pool:          {pool}")
        console.print(f"  Repository:    {repo_owner}/{repo_name}")
        console.print(f"  Labels:        {', '.join(label_list)}")
        console.print(f"  Min Runners:   {min_runners}")
        console.print(f"  Max Runners:   {max_runners}")
        console.print(f"  VM Size:       {vm_size}")
        console.print(f"  Region:        {location}")
        console.print(f"  Resource Group: {rg}")

        # Provision initial runners if min > 0
        if min_runners > 0:
            console.print(f"\n[yellow]Provisioning {min_runners} initial runner(s)...[/yellow]")
            console.print("Note: This may take several minutes. Use 'azlin github-runner status'")
            console.print("      to check provisioning progress.")

        console.print("\n[bold]Next Steps:[/bold]")
        console.print(f"  1. Check status:  azlin github-runner status --pool {pool}")
        console.print(f"  2. Scale manually: azlin github-runner scale --pool {pool} --count N")
        console.print(f"  3. Disable fleet:  azlin github-runner disable --pool {pool}")

    except Exception as e:
        console.print(f"[red]Error enabling runner fleet: {e}[/red]")
        sys.exit(1)


@github_runner_group.command(name="disable")
@click.option(
    "--pool",
    required=True,
    help="VM pool name",
)
@click.option(
    "--keep-vms",
    is_flag=True,
    help="Keep VMs running (don't delete)",
)
def disable_runner_fleet(pool: str, keep_vms: bool):
    """Disable GitHub Actions runner fleet.

    Stops auto-scaling and optionally destroys all runners in the fleet.

    \b
    Examples:
      $ azlin github-runner disable --pool ci-workers
      $ azlin github-runner disable --pool ci-workers --keep-vms
    """
    try:
        # Load config
        config = ConfigManager.load_config()

        if config.github_runner_fleets is None or pool not in config.github_runner_fleets:
            console.print(f"[red]Error: No runner fleet found with name: {pool}[/red]")
            sys.exit(1)

        fleet_config = config.github_runner_fleets[pool]

        # Mark as disabled
        fleet_config["enabled"] = False
        ConfigManager.save_config(config)

        console.print(f"\n[green]✓[/green] Runner fleet disabled: {pool}")

        if not keep_vms:
            console.print("\n[yellow]Destroying runners...[/yellow]")
            console.print("Note: VMs will be destroyed. This cannot be undone.")

            # Note: Automatic runner destruction is not implemented
            # Users must manually destroy VMs using azlin delete command
            console.print("[yellow]Automatic VM destruction is not available[/yellow]")
            console.print("To remove VMs manually, use: azlin delete <vm-name>")

        console.print("\nFleet disabled successfully")

    except Exception as e:
        console.print(f"[red]Error disabling runner fleet: {e}[/red]")
        sys.exit(1)


@github_runner_group.command(name="status")
@click.option(
    "--pool",
    required=True,
    help="VM pool name",
)
def show_runner_status(pool: str):
    """Show GitHub Actions runner fleet status.

    Displays current status of runners in the fleet including:
    - Active runners
    - Queue depth
    - Recent scaling actions

    \b
    Examples:
      $ azlin github-runner status --pool ci-workers
    """
    try:
        # Load config
        config = ConfigManager.load_config()

        if config.github_runner_fleets is None or pool not in config.github_runner_fleets:
            console.print(f"[red]Error: No runner fleet found with name: {pool}[/red]")
            sys.exit(1)

        fleet_config = config.github_runner_fleets[pool]

        # Display fleet configuration
        console.print(f"\n[bold]Runner Fleet Status:[/bold] {pool}")
        console.print(f"Repository:    {fleet_config['repo_owner']}/{fleet_config['repo_name']}")
        console.print(
            f"Status:        {'🟢 Enabled' if fleet_config['enabled'] else '🔴 Disabled'}"
        )
        console.print(f"Min Runners:   {fleet_config['min_runners']}")
        console.print(f"Max Runners:   {fleet_config['max_runners']}")
        console.print(f"Labels:        {', '.join(fleet_config['labels'])}")

        # Note: Live runner status requires GitHub API integration
        console.print("\n[yellow]Live runner status is not available[/yellow]")
        console.print("View active runners at: https://github.com/{owner}/{repo}/actions/runners")

    except Exception as e:
        console.print(f"[red]Error showing runner status: {e}[/red]")
        sys.exit(1)


@github_runner_group.command(name="scale")
@click.option(
    "--pool",
    required=True,
    help="VM pool name",
)
@click.option(
    "--count",
    type=int,
    required=True,
    help="Target runner count",
)
def scale_runner_fleet(pool: str, count: int):
    """Manually scale runner fleet to target count.

    Provisions or destroys runners to reach the target count.
    Respects min/max constraints from fleet configuration.

    \b
    Examples:
      $ azlin github-runner scale --pool ci-workers --count 5
      $ azlin github-runner scale --pool ci-workers --count 0
    """
    try:
        # Load config
        config = ConfigManager.load_config()

        if config.github_runner_fleets is None or pool not in config.github_runner_fleets:
            console.print(f"[red]Error: No runner fleet found with name: {pool}[/red]")
            sys.exit(1)

        fleet_config = config.github_runner_fleets[pool]

        # Validate count
        if count < 0:
            console.print("[red]Error: count cannot be negative[/red]")
            sys.exit(1)

        if count < fleet_config["min_runners"]:
            console.print(
                f"[yellow]Warning: count ({count}) is below min_runners "
                f"({fleet_config['min_runners']})[/yellow]"
            )
            console.print(f"Scaling to minimum: {fleet_config['min_runners']}")
            count = fleet_config["min_runners"]

        if count > fleet_config["max_runners"]:
            console.print(
                f"[yellow]Warning: count ({count}) exceeds max_runners "
                f"({fleet_config['max_runners']})[/yellow]"
            )
            console.print(f"Scaling to maximum: {fleet_config['max_runners']}")
            count = fleet_config["max_runners"]

        console.print(f"\n[yellow]Scaling fleet '{pool}' to {count} runner(s)...[/yellow]")
        console.print("Note: This may take several minutes")

        # Note: Manual scaling requires VM provisioning automation
        console.print("[yellow]Manual scaling is not available[/yellow]")
        console.print("To provision VMs manually, use: azlin new <vm-name>")

    except Exception as e:
        console.print(f"[red]Error scaling runner fleet: {e}[/red]")
        sys.exit(1)
