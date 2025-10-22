#!/usr/bin/env python3
"""
azdoit - AI-powered Azure automation CLI.

This is the standalone entry point for the AZDOIT agentic automation system.
Invoked as: uvx azdoit <natural language prompt>

Examples:
    uvx azdoit "spin up 3 dev VMs in eastus"
    uvx azdoit "stop all VMs matching dev-*"
    uvx azdoit "create snapshot of production VM"
"""

import sys
import click
from azlin.cli import do as azlin_do_command


@click.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("prompt", nargs=-1, required=False)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--yes", "-y", is_flag=True, help="Auto-confirm actions")
@click.option("--dry-run", is_flag=True, help="Show what would be done without executing")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.pass_context
def main(ctx, prompt, resource_group, config, yes, dry_run, verbose):
    """azdoit - AI-powered Azure automation.
    
    Natural language interface to Azure VM operations.
    
    \b
    Examples:
        azdoit "spin up 3 dev VMs"
        azdoit "stop all VMs matching pattern dev-*"
        azdoit "create snapshot of my-vm"
    """
    # Join prompt parts
    prompt_str = " ".join(prompt) if prompt else None
    
    if not prompt_str:
        click.echo("azdoit - AI-powered Azure automation")
        click.echo("")
        click.echo("Usage: azdoit <natural language prompt>")
        click.echo("")
        click.echo("Examples:")
        click.echo('  azdoit "spin up 3 dev VMs in eastus"')
        click.echo('  azdoit "stop all VMs matching dev-*"')
        click.echo('  azdoit "create snapshot of production"')
        click.echo("")
        click.echo("This is equivalent to: azlin do <prompt>")
        click.echo("")
        click.echo("For more help: azlin --help")
        sys.exit(0)
    
    # Invoke the azlin do command with all options
    ctx.invoke(
        azlin_do_command,
        prompt=prompt_str,
        resource_group=resource_group,
        config=config,
        yes=yes,
        dry_run=dry_run,
        verbose=verbose,
    )


if __name__ == "__main__":
    main()
