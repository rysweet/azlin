"""CLI entry point for azdoit."""

import os
import sys
from typing import NoReturn, Optional

import click

from .executor import check_amplihack_available, execute_auto_mode
from .templates import format_objective_prompt

# Avoid circular import by defining version here
__version__ = "2.0.0"


@click.command(name="azdoit")
@click.argument("request", required=False)
@click.option(
    "--max-turns",
    type=int,
    default=15,
    help="Maximum number of auto mode turns (default: 15)"
)
@click.option(
    "--version",
    is_flag=True,
    help="Show version and exit"
)
def main(
    request: Optional[str],
    max_turns: int,
    version: bool
) -> NoReturn:
    """azdoit - Simple Azure infrastructure automation via amplihack auto mode.

    Delegates to amplihack's autonomous goal-seeking engine to iteratively
    pursue Azure infrastructure objectives and generate example scripts.

    Examples:

        azdoit "create 3 VMs called test-vm-{1,2,3}"

        azdoit "provision an AKS cluster with monitoring"

        azdoit --max-turns 30 "set up a complete dev environment"
    """
    # Handle --version flag
    if version:
        click.echo(f"azdoit version {__version__}")
        sys.exit(0)

    # Validate request argument
    if not request:
        click.echo("Error: Missing required argument 'REQUEST'.", err=True)
        click.echo("\nUsage: azdoit [OPTIONS] REQUEST", err=True)
        click.echo("\nTry 'azdoit --help' for more information.", err=True)
        sys.exit(1)

    if not request.strip():
        click.echo("Error: Request cannot be empty.", err=True)
        sys.exit(1)

    # Environment checks
    if not os.environ.get("ANTHROPIC_API_KEY"):
        click.echo(
            "Warning: ANTHROPIC_API_KEY environment variable not set.\n"
            "Auto mode requires a Claude API key to function.\n"
            "Set it with: export ANTHROPIC_API_KEY=your-key-here\n",
            err=True
        )

    # Check amplihack availability
    if not check_amplihack_available():
        click.echo(
            "Error: amplihack is not installed or not in PATH.\n"
            "Install it with: pip install amplihack\n"
            "Or ensure it is accessible in your PATH.",
            err=True
        )
        sys.exit(1)

    # Display what we're doing
    click.echo(f"Objective: {request}\n")
    click.echo(f"Delegating to amplihack auto mode (max {max_turns} turns)...\n")
    click.echo("=" * 70)
    click.echo()

    # Construct prompt from template
    prompt = format_objective_prompt(request)

    # Execute auto mode (does not return)
    execute_auto_mode(prompt, max_turns=max_turns)


if __name__ == "__main__":
    main()
