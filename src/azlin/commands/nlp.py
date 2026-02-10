"""Natural language processing command for azlin CLI.

This module provides the 'do' command (via azdoit_main) that allows users to
execute natural language Azure commands using AI.
"""

from __future__ import annotations

import sys

import click


@click.command()
@click.argument("request", type=str)
@click.option("--dry-run", is_flag=True, help="Show execution plan without running commands")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--verbose", "-v", is_flag=True, help="Show detailed execution information")
def azdoit_main(
    request: str,
    dry_run: bool,
    yes: bool,
    resource_group: str | None,
    config: str | None,
    verbose: bool,
):
    """Execute natural language Azure commands using AI (standalone CLI).

    azdoit v2.0 uses amplihack's autonomous goal-seeking engine to iteratively
    pursue Azure infrastructure objectives and generate example scripts.

    \b
    Quick Start:
        1. Set API key: export ANTHROPIC_API_KEY=your-key-here
        2. Get key from: https://console.anthropic.com/
        3. Try: azdoit "create 3 VMs called test-vm-{1,2,3}"

    \b
    Examples:
        azdoit "create a VM called dev-box"
        azdoit "provision an AKS cluster with monitoring"
        azdoit "set up a storage account with blob containers"
        azdoit --max-turns 30 "set up a complete dev environment"

    \b
    How It Works:
        - azdoit constructs a prompt template from your request
        - Delegates to amplihack auto mode for iterative execution
        - Auto mode researches Azure docs and generates example scripts
        - Output includes reusable infrastructure-as-code

    \b
    Requirements:
        - ANTHROPIC_API_KEY environment variable (get from console.anthropic.com)
        - amplihack CLI installed (pip install amplihack)
        - Azure CLI authenticated (az login)

    \b
    For More Information:
        See docs/AZDOIT_REQUIREMENTS_V2.md for architecture details
    """
    # Import the new azdoit CLI module
    from azlin.azdoit.cli import main as azdoit_cli_main

    # Delegate to new implementation
    # Note: The new implementation does not support --dry-run, --yes, --resource-group
    # flags. These are handled by auto mode's internal decision making.
    if dry_run or yes or resource_group or config or verbose:
        click.echo(
            "Warning: azdoit v2.0 does not support --dry-run, --yes, --resource-group, "
            "--config, or --verbose flags.\n"
            "These options were part of the old architecture.\n"
            "The new auto mode handles execution iteratively with built-in safety.\n",
            err=True,
        )

    # Call the new azdoit CLI with just the request
    # This will handle everything internally
    sys.argv = ["azdoit", request]
    azdoit_cli_main()


__all__ = ["azdoit_main"]
