"""Natural language processing commands for azlin.

This module contains NLP-related CLI commands extracted from cli.py.
Part of Issue #423 - cli.py decomposition.

Commands:
    - do: Execute natural language azlin commands using AI
    - azdoit_main: Standalone entry point for azdoit CLI

Internal Functions:
    - _do_impl: Shared implementation for natural language command execution
"""

import logging
import sys
from typing import Any

import click

from azlin.agentic import (
    ClarificationResult,
    CommandExecutionError,
    CommandExecutor,
    IntentParseError,
    IntentParser,
    RequestClarificationError,
    RequestClarifier,
    ResultValidator,
)
from azlin.config_manager import ConfigManager
from azlin.vm_manager import VMManager

logger = logging.getLogger(__name__)

__all__ = [
    "azdoit_main",
    "do",
]


def _do_impl(
    request: str,
    dry_run: bool,
    yes: bool,
    resource_group: str | None,
    config: str | None,
    verbose: bool,
):
    """Shared implementation for natural language command execution.

    This function contains the core logic used by both 'azlin do' and 'azdoit'
    commands to parse and execute natural language requests.

    Args:
        request: Natural language request describing desired action
        dry_run: If True, show execution plan without running commands
        yes: If True, skip confirmation prompts
        resource_group: Azure resource group name (optional)
        config: Path to config file (optional)
        verbose: If True, show detailed execution information

    Raises:
        SystemExit: On various error conditions with appropriate exit codes
    """
    try:
        # Check for API key
        import os

        if not os.getenv("ANTHROPIC_API_KEY"):
            click.echo("Error: ANTHROPIC_API_KEY environment variable is required", err=True)
            click.echo("\nSet your API key with:", err=True)
            click.echo("  export ANTHROPIC_API_KEY=your-key-here", err=True)
            sys.exit(1)

        # Get resource group for context
        rg = ConfigManager.get_resource_group(resource_group, config)

        # Build context for parser
        context = {}
        if rg:
            context["resource_group"] = rg
            # Get current VMs for context
            try:
                vms = VMManager.list_vms(rg, include_stopped=True)
                context["current_vms"] = [
                    {"name": v.name, "status": v.power_state, "ip": v.public_ip} for v in vms
                ]
            except Exception:
                # Context is optional - continue without VM list
                context["current_vms"] = []

        # Phase 1: Request Clarification (for complex/ambiguous requests)
        clarification_result: ClarificationResult | None = None
        clarified_request = request  # Use original by default

        # Check if clarification is disabled via environment variable
        disable_clarification = os.getenv("AZLIN_DISABLE_CLARIFICATION", "").lower() in (
            "1",
            "true",
            "yes",
        )

        # Track whether we need to parse intent (or if we can reuse initial_intent)
        initial_intent = None
        needs_parsing = True

        if not disable_clarification:
            try:
                clarifier = RequestClarifier()

                # Quick check if clarification might be needed
                # We'll do a fast initial parse to get confidence
                parser = IntentParser()
                initial_confidence = None
                commands_empty = False

                try:
                    initial_intent = parser.parse(request, context=context)
                    initial_confidence = initial_intent.get("confidence")
                    commands_empty = not initial_intent.get("azlin_commands", [])
                except Exception:
                    # If initial parse fails, we should definitely try clarification
                    initial_confidence = 0.0
                    commands_empty = True

                # Determine if clarification is needed
                if clarifier.should_clarify(
                    request, confidence=initial_confidence, commands_empty=commands_empty
                ):
                    if verbose:
                        click.echo("Complex request detected - initiating clarification phase...")

                    # Get clarification
                    clarification_result = clarifier.clarify(
                        request, context=context, auto_confirm=yes
                    )

                    # If user didn't confirm, exit
                    if not clarification_result.user_confirmed:
                        click.echo("Cancelled.")
                        sys.exit(0)

                    # Use clarified request for parsing
                    if clarification_result.clarified_request:
                        clarified_request = clarification_result.clarified_request
                        if verbose:
                            click.echo("\nUsing clarified request for command generation...")
                else:
                    # No clarification needed - reuse initial_intent to avoid double parsing
                    if initial_intent is not None:
                        needs_parsing = False
                        if verbose:
                            click.echo("Request is clear - proceeding with direct parsing...")

            except RequestClarificationError as e:
                # Clarification failed - fall back to direct parsing with warning
                # Always inform user when fallback occurs, not just in verbose mode
                click.echo(f"Clarification unavailable: {e}", err=True)
                click.echo("Continuing with direct parsing...", err=True)
                if verbose:
                    logger.exception("Clarification error details:")

        # Phase 2: Parse natural language intent (possibly clarified)
        # Only parse if we didn't already parse successfully above
        intent: dict[str, Any]
        if needs_parsing:
            if verbose:
                click.echo(f"\nParsing request: {clarified_request}")

            parser = IntentParser()
            intent = parser.parse(clarified_request, context=context)
        else:
            # Reuse the initial intent we already parsed
            if initial_intent is None:
                # This shouldn't happen, but if it does, parse again
                parser = IntentParser()
                intent = parser.parse(clarified_request, context=context)
            else:
                intent = initial_intent

        if verbose:
            click.echo("\nParsed Intent:")
            click.echo(f"  Type: {intent['intent']}")
            click.echo(f"  Confidence: {intent['confidence']:.1%}")
            if "explanation" in intent:
                click.echo(f"  Plan: {intent['explanation']}")

        # Check confidence (only warn if we didn't already clarify)
        if not clarification_result and intent["confidence"] < 0.7:
            click.echo(
                f"\nWarning: Low confidence ({intent['confidence']:.1%}) in understanding your request.",
                err=True,
            )
            if not yes and not click.confirm("Continue anyway?"):
                sys.exit(1)

        # Show commands to be executed
        click.echo("\nCommands to execute:")
        for i, cmd in enumerate(intent["azlin_commands"], 1):
            cmd_str = f"{cmd['command']} {' '.join(cmd['args'])}"
            click.echo(f"  {i}. {cmd_str}")

        if dry_run:
            click.echo("\n[DRY RUN] Would execute the above commands.")
            sys.exit(0)

        # Confirm execution
        if not yes and not click.confirm("\nExecute these commands?"):
            click.echo("Cancelled.")
            sys.exit(0)

        # Execute commands
        click.echo("\nExecuting commands...\n")
        executor = CommandExecutor(dry_run=False)
        results = executor.execute_plan(intent["azlin_commands"])

        # Display results
        for i, result in enumerate(results, 1):
            click.echo(f"\nCommand {i}: {result['command']}")
            if result["success"]:
                click.echo("  Success")
                if verbose and result["stdout"]:
                    click.echo(f"  Output: {result['stdout'][:200]}")
            else:
                click.echo(f"  Failed: {result['stderr']}")
                break  # Stop on first failure

        # Validate results
        validator = ResultValidator()
        validation = validator.validate(intent, results)

        click.echo("\n" + "=" * 80)
        if validation["success"]:
            click.echo("SUCCESS: " + validation["message"])
        else:
            click.echo("FAILED: " + validation["message"], err=True)
            if "issues" in validation:
                for issue in validation["issues"]:
                    click.echo(f"  - {issue}", err=True)
            sys.exit(1)

    except IntentParseError as e:
        click.echo(f"\nFailed to parse request: {e}", err=True)
        click.echo("\nTry rephrasing your request or use specific azlin commands.", err=True)
        sys.exit(1)

    except CommandExecutionError as e:
        click.echo(f"\nCommand execution failed: {e}", err=True)
        sys.exit(1)

    except Exception as e:
        click.echo(f"\nUnexpected error: {e}", err=True)
        if verbose:
            logger.exception("Unexpected error in do command")
        sys.exit(1)

    except KeyboardInterrupt:
        click.echo("\n\nCancelled by user.")
        sys.exit(130)


@click.command()
@click.argument("request", type=str)
@click.option("--dry-run", is_flag=True, help="Show execution plan without running commands")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--verbose", "-v", is_flag=True, help="Show detailed execution information")
def do(
    request: str,
    dry_run: bool,
    yes: bool,
    resource_group: str | None,
    config: str | None,
    verbose: bool,
):
    """Execute natural language azlin commands using AI.

    The 'do' command understands natural language and automatically translates
    your requests into the appropriate azlin commands. Just describe what you
    want in plain English.

    \b
    Quick Start:
        1. Set API key: export ANTHROPIC_API_KEY=your-key-here
        2. Get key from: https://console.anthropic.com/
        3. Try: azlin do "list all my vms"

    \b
    VM Management Examples:
        azlin do "create a new vm called Sam"
        azlin do "show me all my vms"
        azlin do "what is the status of my vms"
        azlin do "start my development vm"
        azlin do "stop all test vms"

    \b
    Cost & Monitoring:
        azlin do "what are my azure costs"
        azlin do "show me costs by vm"
        azlin do "what's my spending this month"

    \b
    File Operations:
        azlin do "sync all my vms"
        azlin do "sync my home directory to vm Sam"
        azlin do "copy myproject to the vm"

    \b
    Resource Cleanup:
        azlin do "delete vm called test-123" --dry-run  # Preview first
        azlin do "delete all test vms"                   # Then execute
        azlin do "stop idle vms to save costs"

    \b
    Complex Operations:
        azlin do "create 5 test vms and sync them all"
        azlin do "set up a new development environment"
        azlin do "show costs and stop any idle vms"

    \b
    Options:
        --dry-run      Preview actions without executing anything
        --yes, -y      Skip confirmation prompts (for automation)
        --verbose, -v  Show detailed parsing and confidence scores
        --rg NAME      Specify Azure resource group

    \b
    Safety Features:
        - Shows plan and asks for confirmation (unless --yes)
        - High accuracy: 95-100% confidence on VM operations
        - Graceful error handling for invalid requests
        - Dry-run mode to preview without executing

    \b
    Error Handling:
        - Invalid requests (0% confidence): No commands executed
        - Ambiguous requests (low confidence): Asks for confirmation
        - Always shows what will be executed before running

    \b
    Requirements:
        - ANTHROPIC_API_KEY environment variable (get from console.anthropic.com)
        - Azure CLI authenticated (az login)
        - Active Azure subscription

    \b
    For More Examples:
        See docs/AZDOIT.md for 50+ examples and comprehensive guide
        Integration tested: 7/7 tests passing with real Azure resources
    """
    _do_impl(request, dry_run, yes, resource_group, config, verbose)


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
    import sys as sys_module

    sys_module.argv = ["azdoit", request]
    azdoit_cli_main()
