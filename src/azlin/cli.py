"""CLI entry point for azlin v2.0.

This module provides the enhanced command-line interface with:
- Config storage and resource group management
- VM listing and status
- Interactive session selection
- Parallel VM provisioning (pools)
- Remote command execution
- Enhanced help
- Distributed monitoring

Commands:
    azlin                    # Show help
    azlin new                # Provision new VM
    azlin list               # List VMs in resource group
    azlin w                  # Run 'w' command on all VMs
    azlin top                # Live distributed VM metrics dashboard
    azlin -- <command>       # Execute command on VM(s)
"""

import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

import click

from azlin import __version__
from azlin.azure_auth import AuthenticationError, AzureAuthenticator
from azlin.batch_executor import BatchExecutor, BatchExecutorError, BatchResult

# Import helper functions from cli_helpers
from azlin.cli_helpers import (
    _confirm_batch_operation,
    _display_batch_summary,
    _get_ssh_config_for_vm,
    _perform_startup_checks,
    _select_vms_by_criteria,
    _validate_batch_selection,
)
from azlin.click_group import AzlinGroup

# Import all commands from modular command modules
from azlin.commands import (
    # Additional command groups
    ask_command,
    ask_group,
    autopilot_group,
    azdoit_main,
    bastion_group,
    # Batch Commands
    batch,
    clone,
    code_command,
    compose_group,
    # Connectivity Commands
    connect,
    context_group,
    costs_group,
    cp,
    create,
    destroy,
    # NLP Commands
    do,
    doit_group,
    # Environment Commands
    env,
    fleet_group,
    github_runner_group,
    # IP Commands
    ip,
    # Keys Commands
    keys_group,
    kill,
    killall,
    list_command,
    # Provisioning Commands
    new,
    prune,
    ps,
    restore_command,
    session_command,
    session_group,
    # Snapshot Commands
    snapshot,
    # Lifecycle Commands
    start,
    status,
    stop,
    storage_group,
    sync,
    sync_keys,
    tag_group,
    # Template Commands
    template,
    top,
    vm,
    # Monitoring Commands
    w,
    # Web Commands
    web,
)
from azlin.commands import (
    auth_group as auth,
)

# Backward compatibility exports for tests that patch azlin.cli.*
from azlin.commands.monitoring import (  # noqa: F401
    _collect_tmux_sessions,
    _create_tunnel_with_retry,
    _handle_multi_context_list,
)

# New modules for v2.0
from azlin.config_manager import AzlinConfig, ConfigError, ConfigManager
from azlin.context_manager import ContextManager
from azlin.cost_tracker import CostTracker, CostTrackerError
from azlin.distributed_top import DistributedTopExecutor  # noqa: F401
from azlin.env_manager import EnvManager, EnvManagerError
from azlin.ip_diagnostics import (
    check_connectivity,
    classify_ip_address,
    format_diagnostic_report,
)
from azlin.key_rotator import KeyRotationError, SSHKeyRotator
from azlin.modules.file_transfer import FileTransfer  # noqa: F401
from azlin.modules.file_transfer.path_parser import PathParser  # noqa: F401
from azlin.modules.progress import ProgressDisplay
from azlin.modules.snapshot_manager import SnapshotError, SnapshotManager
from azlin.modules.ssh_keys import SSHKeyError
from azlin.network_security.bastion_connection_pool import (  # noqa: F401
    BastionConnectionPool,
)

# Import orchestrator components
from azlin.orchestrator import AzlinError, CLIOrchestrator
from azlin.remote_exec import (  # noqa: F401
    OSUpdateExecutor,
    PSCommandExecutor,
    RemoteExecError,
    RemoteExecutor,
    TmuxSessionExecutor,
)
from azlin.tag_manager import TagManager  # noqa: F401
from azlin.template_manager import TemplateError, TemplateManager, VMTemplateConfig
from azlin.vm_manager import VMManager, VMManagerError

logger = logging.getLogger(__name__)


@click.group(
    cls=AzlinGroup,
    invoke_without_command=True,
    context_settings={
        "ignore_unknown_options": True,
        "allow_extra_args": True,
        "allow_interspersed_args": False,
        "help_option_names": ["--help", "-h"],
    },
)
@click.option(
    "--auth-profile",
    help="Service principal authentication profile to use",
    type=str,
    default=None,
)
@click.pass_context
@click.version_option(version=__version__)
def main(ctx: click.Context, auth_profile: str | None) -> None:
    """azlin - Azure Ubuntu VM provisioning and management.

    Provisions Azure Ubuntu VMs with development tools, manages existing VMs,
    and executes commands remotely.

    Use --auth-profile to specify a service principal authentication profile
    (configured via 'azlin auth setup').

    \b
    NATURAL LANGUAGE COMMANDS (AI-POWERED):
        ask           Query VM fleet using natural language
                      Example: azlin ask "which VMs cost the most?"
                      Example: azlin ask "show VMs using >80% disk"
                      Example: azlin ask "VMs with old Python versions"
                      Requires: ANTHROPIC_API_KEY environment variable

        do            Execute commands using natural language
                      Example: azlin do "create a new vm called Sam"
                      Example: azlin do "sync all my vms"
                      Example: azlin do "show me the cost over the last week"
                      Requires: ANTHROPIC_API_KEY environment variable

    \b
    VM LIFECYCLE COMMANDS:
        new           Provision a new VM (aliases: vm, create)
        clone         Clone a VM with its home directory contents
        list          List VMs in resource group
        session       Set or view session name for a VM
        status        Show detailed status of VMs
        start         Start a stopped VM
        stop          Stop/deallocate a VM to save costs
        connect       Connect to existing VM via SSH
        update        Update all development tools on a VM
        tag           Manage VM tags (add, remove, list)

    \b
    ENVIRONMENT MANAGEMENT:
        env set       Set environment variable on VM
        env list      List environment variables on VM
        env delete    Delete environment variable from VM
        env export    Export variables to .env file
        env import    Import variables from .env file
        env clear     Clear all environment variables

    \b
    SNAPSHOT COMMANDS:
        snapshot create <vm>              Create snapshot of VM disk
        snapshot list <vm>                List snapshots for VM
        snapshot restore <vm> <snapshot>  Restore VM from snapshot
        snapshot delete <snapshot>        Delete a snapshot

    \b
    STORAGE COMMANDS:
        storage create    Create NFS storage for shared home directories
        storage list      List NFS storage accounts
        storage status    Show storage usage and connected VMs
        storage mount     Mount storage on VM
        storage unmount   Unmount storage from VM
        storage delete    Delete storage account

    \b
    MONITORING COMMANDS:
        w             Run 'w' command on all VMs
        ps            Run 'ps aux' on all VMs
        cost          Show cost estimates for VMs
        logs          View VM logs without SSH connection

    \b
    DELETION COMMANDS:
        kill          Delete a VM and all resources
        destroy       Delete VM with dry-run and RG options
        killall       Delete all VMs in resource group
        cleanup       Find and remove orphaned resources

    \b
    SSH KEY MANAGEMENT:
        keys rotate   Rotate SSH keys across all VMs
        keys list     List VMs and their SSH keys
        keys export   Export public key to file
        keys backup   Backup current SSH keys

    \b
    AUTHENTICATION:
        auth setup    Set up service principal authentication profile
        auth test     Test authentication with a profile
        auth list     List available authentication profiles
        auth show     Show profile details
        auth remove   Remove authentication profile

    \b
    EXAMPLES:
        # Show help
        $ azlin

        # Natural language commands (AI-powered)
        $ azlin do "create a new vm called Sam"
        $ azlin do "sync all my vms"
        $ azlin do "show me the cost over the last week"
        $ azlin do "delete vms older than 30 days" --dry-run

        # Provision a new VM
        $ azlin new

        # Provision with custom session name
        $ azlin new --name my-project

        # List VMs and show status
        $ azlin list
        $ azlin list --tag env=dev
        $ azlin status

        # Manage session names
        $ azlin session azlin-vm-12345 my-project
        $ azlin session azlin-vm-12345 --clear

        # Environment variables
        $ azlin env set my-vm DATABASE_URL="postgres://localhost/db"
        $ azlin env list my-vm
        $ azlin env export my-vm prod.env

        # Manage tags
        $ azlin tag my-vm --add env=dev
        $ azlin tag my-vm --list
        $ azlin tag my-vm --remove env

        # Start/stop VMs
        $ azlin start my-vm
        $ azlin stop my-vm

        # Update VM tools
        $ azlin update my-vm
        $ azlin update my-project

        # Manage snapshots
        $ azlin snapshot create my-vm
        $ azlin snapshot list my-vm
        $ azlin snapshot restore my-vm my-vm-snapshot-20251015-053000

        # Shared NFS storage for home directories
        $ azlin storage create team-shared --size 100 --tier Premium
        $ azlin new --nfs-storage team-shared --name worker-1
        $ azlin new --nfs-storage team-shared --name worker-2
        $ azlin storage status team-shared

        # View costs
        $ azlin cost --by-vm
        $ azlin cost --from 2025-01-01 --to 2025-01-31

        # View VM logs
        $ azlin logs my-vm
        $ azlin logs my-vm --boot
        $ azlin logs my-vm --follow

        # Run 'w' and 'ps' on all VMs
        $ azlin w
        $ azlin ps

        # Delete VMs
        $ azlin kill azlin-vm-12345
        $ azlin destroy my-vm --dry-run
        $ azlin destroy my-vm --delete-rg --force

        # Provision VM with custom name
        $ azlin new --name my-dev-vm

        # Provision VM and clone repository
        $ azlin new --repo https://github.com/owner/repo

        # Provision 5 VMs in parallel
        $ azlin new --pool 5

    \b
    CONFIGURATION:
        Config file: ~/.azlin/config.toml
        Set defaults: default_resource_group, default_region, default_vm_size

    For help on any command: azlin <command> --help
    """
    # Set up logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Check Azure CLI environment (WSL2 compatibility)
    try:
        _perform_startup_checks()
    except Exception as e:
        # Non-fatal - log but continue
        logger.debug(f"Azure CLI environment check skipped: {e}")

    # Check if first-run wizard is needed
    try:
        if ConfigManager.needs_configuration():
            try:
                ConfigManager.run_first_run_wizard()
            except ConfigError as e:
                click.echo(click.style(f"Configuration error: {e}", fg="red"), err=True)
                ctx.exit(1)
                return  # Explicit return for code clarity (never reached)
            except KeyboardInterrupt:
                click.echo()
                click.echo(
                    click.style("Setup cancelled. Run 'azlin' again to configure.", fg="yellow")
                )
                ctx.exit(130)  # Standard exit code for SIGINT
                return  # Explicit return for code clarity (never reached)
    except Exception as e:
        # If wizard check fails, log but continue (allow commands to work)
        logger.debug(f"Could not check configuration status: {e}")

    # If auth profile specified, set up authentication environment
    if auth_profile:
        try:
            auth = AzureAuthenticator(auth_profile=auth_profile)
            auth.get_credentials()  # This sets environment variables for Azure CLI
            logger.debug(f"Initialized authentication with profile: {auth_profile}")
        except AuthenticationError as e:
            click.echo(f"Error: Authentication failed: {e}", err=True)
            ctx.exit(1)
            return  # Explicit return for code clarity (never reached)

    # If no subcommand provided, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(0)  # Use ctx.exit() instead of sys.exit() for Click compatibility
        return  # Explicit return for code clarity (never reached)


@main.command(name="help")
@click.argument("command_name", required=False, type=str)
@click.pass_context
def help_command(ctx: click.Context, command_name: str | None) -> None:
    """Show help for commands.

    Display general help or help for a specific command.

    \b
    Examples:
        azlin help              # Show general help
        azlin help connect      # Show help for connect command
        azlin help list         # Show help for list command
    """
    if command_name is None:
        click.echo(ctx.parent.get_help())
    else:
        # Show help for specific command
        cmd = ctx.parent.command.commands.get(command_name)  # type: ignore[union-attr]

        if cmd is None:
            click.echo(f"Error: No such command '{command_name}'.", err=True)
            ctx.exit(1)

        # Create a context for the command and show its help
        cmd_ctx = click.Context(cmd, info_name=command_name, parent=ctx.parent)  # type: ignore[arg-type]
        click.echo(cmd.get_help(cmd_ctx))  # type: ignore[union-attr]


@main.command(name="os-update")
@click.argument("vm_identifier", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--timeout", help="Timeout in seconds (default 300)", type=int, default=300)
def os_update(vm_identifier: str, resource_group: str | None, config: str | None, timeout: int):
    """Update OS packages on a VM.

    Runs 'apt update && apt upgrade -y' on Ubuntu VMs to update all packages.

    VM_IDENTIFIER can be:
    - Session name (resolved to VM)
    - VM name (requires --resource-group or default config)
    - IP address (direct connection)

    \b
    Examples:
        azlin os-update my-session
        azlin os-update azlin-myvm --rg my-resource-group
        azlin os-update 20.1.2.3
        azlin os-update my-vm --timeout 600  # 10 minute timeout
    """
    try:
        # Get SSH config for VM
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        click.echo(f"Updating OS packages on {vm_identifier}...")
        click.echo("This may take several minutes...\n")

        # Execute OS update
        result = OSUpdateExecutor.execute_os_update(ssh_config, timeout=timeout)

        # Format and display output
        output = OSUpdateExecutor.format_output(result)
        click.echo(output)

        # Exit with appropriate code
        if not result.success:
            sys.exit(1)

    except RemoteExecError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except SSHKeyError as e:
        click.echo(f"SSH key error: {e}", err=True)
        sys.exit(1)
    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


# kill command - Moved to azlin.commands.lifecycle (Issue #423 refactor)
@main.command()
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--by-vm", is_flag=True, help="Show per-VM breakdown")
@click.option("--from", "from_date", help="Start date (YYYY-MM-DD)", type=str)
@click.option("--to", "to_date", help="End date (YYYY-MM-DD)", type=str)
@click.option("--estimate", is_flag=True, help="Show monthly cost estimate")
def cost(
    resource_group: str | None,
    config: str | None,
    by_vm: bool,
    from_date: str | None,
    to_date: str | None,
    estimate: bool,
):
    """Show cost estimates for VMs.

    Displays cost estimates based on VM size and uptime.
    Costs are approximate based on Azure pay-as-you-go pricing.

    \b
    Examples:
        azlin cost
        azlin cost --by-vm
        azlin cost --from 2025-01-01 --to 2025-01-31
        azlin cost --estimate
        azlin cost --rg my-resource-group --by-vm
    """
    try:
        # Ensure Azure CLI subscription matches current context
        from azlin.context_manager import ContextError

        try:
            ContextManager.ensure_subscription_active(config)
        except ContextError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # Parse dates if provided
        start_date = None
        end_date = None

        if from_date:
            try:
                start_date = datetime.strptime(from_date, "%Y-%m-%d")
            except ValueError:
                click.echo("Error: Invalid from date format. Use YYYY-MM-DD", err=True)
                sys.exit(1)

        if to_date:
            try:
                end_date = datetime.strptime(to_date, "%Y-%m-%d")
            except ValueError:
                click.echo("Error: Invalid to date format. Use YYYY-MM-DD", err=True)
                sys.exit(1)

        # Get cost estimates
        click.echo(f"Calculating costs for resource group: {rg}\n")

        summary = CostTracker.estimate_costs(
            resource_group=rg, from_date=start_date, to_date=end_date, include_stopped=True
        )

        # Display formatted table
        output = CostTracker.format_cost_table(summary, by_vm=by_vm)
        click.echo(output)

        # Show estimate if requested
        if estimate and summary.running_vms > 0:
            monthly = summary.get_monthly_estimate()
            click.echo(f"Monthly estimate for running VMs: ${monthly:.2f}")
            click.echo("")

    except CostTrackerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("vm_identifier", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--timeout", help="Timeout per update in seconds", type=int, default=300)
def update(vm_identifier: str, resource_group: str | None, config: str | None, timeout: int):
    """Update all development tools on a VM.

    Updates system packages, programming languages, CLIs, and other dev tools
    that were installed during VM provisioning.

    VM_IDENTIFIER can be:
    - VM name (requires --resource-group or default config)
    - Session name (will be resolved to VM name)
    - IP address (direct connection)

    Tools updated:
    - System packages (apt)
    - Azure CLI
    - GitHub CLI
    - npm and npm packages (Copilot, Codex, Claude Code)
    - Rust toolchain
    - astral-uv

    \b
    Examples:
        # Update VM by name
        azlin update my-vm

        # Update VM by session name
        azlin update my-project

        # Update VM by IP
        azlin update 20.1.2.3

        # Update with custom timeout (default 300s per tool)
        azlin update my-vm --timeout 600

        # Update with explicit resource group
        azlin update my-vm --rg my-resource-group
    """
    from azlin.vm_updater import VMUpdater, VMUpdaterError

    try:
        # Resolve VM identifier to SSH config
        # Try session name first, then VM name, then IP
        original_identifier = vm_identifier

        # Try to resolve as session name
        try:
            session_vm = ConfigManager.get_vm_name_by_session(vm_identifier, config)
            if session_vm:
                vm_identifier = session_vm
                click.echo(f"Resolved session '{original_identifier}' to VM '{vm_identifier}'")
        except Exception as e:
            logger.debug(f"Not a session name, trying as VM name or IP: {e}")

        # Get SSH config for VM
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        # Display info
        display_name = (
            original_identifier if original_identifier != vm_identifier else vm_identifier
        )
        click.echo(f"\nUpdating tools on {display_name}...")
        click.echo("This may take several minutes.\n")

        # Create progress display
        progress = ProgressDisplay()

        # Create updater with progress callback
        def progress_callback(message: str):
            click.echo(f"  {message}")

        updater = VMUpdater(
            ssh_config=ssh_config, timeout=timeout, progress_callback=progress_callback
        )

        # Perform update
        progress.start_operation("Updating VM tools", estimated_seconds=180)
        summary = updater.update_vm()
        progress.complete(
            success=summary.all_succeeded,
            message=f"Update completed in {summary.total_duration:.1f}s",
        )

        # Display results
        click.echo("\n" + "=" * 60)
        click.echo("UPDATE SUMMARY")
        click.echo("=" * 60)

        if summary.successful:
            click.echo(f"\n✓ Successful updates ({len(summary.successful)}):")
            for result in summary.successful:
                click.echo(f"  {result.tool_name:<20} {result.duration:>6.1f}s")

        if summary.failed:
            click.echo(f"\n✗ Failed updates ({len(summary.failed)}):")
            for result in summary.failed:
                click.echo(f"  {result.tool_name:<20} {result.message[:40]}")

        click.echo(f"\nTotal time: {summary.total_duration:.1f}s")
        click.echo("=" * 60 + "\n")

        # Exit with appropriate code
        if summary.all_succeeded:
            click.echo("All updates completed successfully!")
            sys.exit(0)
        elif summary.any_failed:
            if summary.success_count > 0:
                click.echo(
                    f"Partial success: {summary.success_count}/{summary.total_updates} updates succeeded"
                )
                sys.exit(1)
            else:
                click.echo("All updates failed!")
                sys.exit(2)

    except VMUpdaterError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in update command")
        sys.exit(1)


# stop command - Moved to azlin.commands.lifecycle (Issue #423 refactor)
# start command - Moved to azlin.commands.lifecycle (Issue #423 refactor)
@ip.command(name="check")
@click.argument("vm_identifier", required=False)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--all", "check_all", is_flag=True, help="Check all VMs in resource group")
@click.option("--port", help="Port to test connectivity (default: 22)", type=int, default=22)
def ip_check(
    vm_identifier: str | None,
    resource_group: str | None,
    config: str | None,
    check_all: bool,
    port: int,
):
    """Check IP address classification and connectivity for VM(s).

    Diagnoses IP classification (Public, Private, or Public-Azure) and tests
    connectivity. Particularly useful for identifying Azure's public IP range
    172.171.0.0/16 which appears private but is actually public.

    \b
    Examples:
        azlin ip check my-vm                  # Check specific VM
        azlin ip check --all                  # Check all VMs
        azlin ip check my-vm --port 80        # Check different port
        azlin ip check 172.171.118.91         # Check by IP address directly
    """
    try:
        # Validate arguments
        if not vm_identifier and not check_all:
            click.echo("Error: Either specify a VM name/IP or use --all flag", err=True)
            sys.exit(1)

        if vm_identifier and check_all:
            click.echo("Error: Cannot specify both VM name and --all flag", err=True)
            sys.exit(1)

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        # Check if vm_identifier is an IP address
        if vm_identifier and "." in vm_identifier:
            # Direct IP check
            click.echo(f"Running diagnostic for IP: {vm_identifier}\n")

            diagnostic_data = {
                "ip": vm_identifier,
                "classification": classify_ip_address(vm_identifier),
                "connectivity": check_connectivity(vm_identifier, port=port),
                "nsg_check": None,  # Can't check NSG without VM context
            }

            report = format_diagnostic_report(diagnostic_data)
            click.echo(report)
            return

        # Get VMs
        if check_all:
            if not rg:
                click.echo("Error: --all requires resource group to be specified", err=True)
                sys.exit(1)

            vms = VMManager.list_vms(rg, include_stopped=True)
            vms = VMManager.filter_by_prefix(vms, "azlin")

            if not vms:
                click.echo("No VMs found.")
                return
        else:
            # Single VM check
            if not rg:
                click.echo("Error: Resource group required. Set via --rg or config.", err=True)
                sys.exit(1)

            vm_name = vm_identifier
            vms = VMManager.list_vms(rg, include_stopped=True)
            vms = [v for v in vms if v.name == vm_name]

            if not vms:
                click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'.", err=True)
                sys.exit(1)

        # Run diagnostics on each VM
        for vm_item in vms:
            if not vm_item.public_ip:
                click.echo(f"\nVM: {vm_item.name}")
                click.echo("  Status: No public IP assigned (VM may be stopped)")
                continue

            click.echo(f"\nVM: {vm_item.name}")

            # Get NSG information if available
            # Note: NSG info would need to be extracted from VM details
            # For now, we'll skip NSG checking as it requires additional Azure API calls

            diagnostic_data = {
                "ip": vm_item.public_ip,
                "classification": classify_ip_address(vm_item.public_ip),
                "connectivity": check_connectivity(vm_item.public_ip, port=port),
                "nsg_check": None,  # Would require additional Azure NSG query
            }

            report = format_diagnostic_report(diagnostic_data)
            click.echo(report)

            if check_all:
                click.echo("\n" + "=" * 70 + "\n")

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@batch.command(name="stop")
@click.option("--tag", help="Filter VMs by tag (format: key=value)", type=str)
@click.option("--vm-pattern", help="Filter VMs by name pattern (glob)", type=str)
@click.option("--all", "select_all", is_flag=True, help="Select all VMs in resource group")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option(
    "--deallocate/--no-deallocate", default=True, help="Deallocate to save costs (default: yes)"
)
@click.option("--max-workers", default=10, help="Maximum parallel workers (default: 10)", type=int)
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def batch_stop(
    tag: str | None,
    vm_pattern: str | None,
    select_all: bool,
    resource_group: str | None,
    config: str | None,
    deallocate: bool,
    max_workers: int,
    confirm: bool,
):
    """Batch stop/deallocate VMs.

    Stop multiple VMs simultaneously. By default, VMs are deallocated
    to stop billing for compute resources.

    \b
    Examples:
        azlin batch stop --tag 'env=dev'
        azlin batch stop --vm-pattern 'test-*'
        azlin batch stop --all --confirm
    """
    pass


# keys_group command - Moved to azlin.commands.keys (Issue #423 refactor)
# template command - Moved to azlin.commands.templates (Issue #423 refactor)
# snapshot command - Moved to azlin.commands.snapshots (Issue #423 refactor)
@snapshot.command(name="enable")
@click.argument("vm_name", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option(
    "--every",
    "interval_hours",
    type=int,
    required=True,
    help="Snapshot interval in hours (e.g., 24 for daily)",
)
@click.option(
    "--keep", "keep_count", type=int, default=2, help="Number of snapshots to keep (default: 2)"
)
@snapshot.command(name="disable")
@click.argument("vm_name", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def snapshot_disable(vm_name: str, resource_group: str | None, config: str | None):
    """Disable scheduled snapshots for a VM.

    Removes the snapshot schedule from the VM. Existing snapshots are not deleted.

    \b
    Example:
        azlin snapshot disable my-vm
    """
    try:
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        SnapshotManager.disable_snapshots(vm_name, rg)

        click.echo(f"✓ Disabled scheduled snapshots for {vm_name}")
        click.echo("Existing snapshots were not deleted.")

    except SnapshotError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@snapshot.command(name="sync")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--vm", "vm_name", help="Sync specific VM only", type=str)
def snapshot_sync(resource_group: str | None, config: str | None, vm_name: str | None):
    """Sync snapshots for VMs with schedules.

    Checks all VMs (or specific VM) and creates snapshots if needed based on their schedules.
    Old snapshots beyond retention count are automatically deleted (FIFO).

    This is the main command to run periodically (e.g., via cron) to trigger snapshot creation.

    \b
    Examples:
        azlin snapshot sync                # Sync all VMs
        azlin snapshot sync --vm my-vm     # Sync specific VM
    """
    try:
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        click.echo("Syncing scheduled snapshots...")

        results = SnapshotManager.sync_snapshots(rg, vm_name)

        click.echo("\n✓ Sync complete:")
        click.echo(f"  VMs checked: {results['checked']}")
        click.echo(f"  Snapshots created: {results['created']}")
        click.echo(f"  Old snapshots cleaned: {results['cleaned']}")
        click.echo(f"  VMs skipped: {results['skipped']}")

    except SnapshotError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@snapshot.command(name="status")
@click.argument("vm_name", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def snapshot_status(vm_name: str, resource_group: str | None, config: str | None):
    """Show snapshot schedule status for a VM.

    \b
    Example:
        azlin snapshot status my-vm
    """
    try:
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        schedule = SnapshotManager.get_snapshot_schedule(vm_name, rg)

        if not schedule:
            click.echo(f"No snapshot schedule configured for {vm_name}")
            return

        click.echo(f"Snapshot schedule for {vm_name}:")
        click.echo(f"  Status: {'Enabled' if schedule.enabled else 'Disabled'}")
        click.echo(f"  Interval: every {schedule.interval_hours} hours")
        click.echo(f"  Retention: keep {schedule.keep_count} snapshots")

        if schedule.last_snapshot_time:
            click.echo(f"  Last snapshot: {schedule.last_snapshot_time.isoformat()}")
        else:
            click.echo("  Last snapshot: Never")

    except SnapshotError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@keys_group.command(name="rotate")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--all-vms", is_flag=True, help="Rotate keys for all VMs (not just azlin prefix)")
@click.option("--no-backup", is_flag=True, help="Skip backup before rotation")
@click.option("--vm-prefix", default="azlin", help="Only update VMs with this prefix")
def keys_rotate(
    resource_group: str | None, config: str | None, all_vms: bool, no_backup: bool, vm_prefix: str
):
    """Rotate SSH keys for all VMs in resource group.

    Generates a new SSH key pair and updates all VMs to use the new key.
    Automatically backs up old keys before rotation for safety.

    \b
    Examples:
        azlin keys rotate
        azlin keys rotate --rg my-resource-group
        azlin keys rotate --all-vms
        azlin keys rotate --no-backup
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # Determine VM prefix
        prefix = "" if all_vms else vm_prefix

        click.echo(f"Rotating SSH keys for VMs in resource group: {rg}")
        if prefix:
            click.echo(f"Only updating VMs with prefix: {prefix}")
        click.echo()

        # Confirm
        confirm = input("Continue with key rotation? [y/N]: ").lower()
        if confirm not in ["y", "yes"]:
            click.echo("Cancelled.")
            return

        # Rotate keys
        result = SSHKeyRotator.rotate_keys(
            resource_group=rg, create_backup=not no_backup, enable_rollback=True, vm_prefix=prefix
        )

        # Display results
        click.echo()
        if result.success:
            click.echo(f"Success! {result.message}")
            if result.new_key_path:
                click.echo(f"New key: {result.new_key_path}")
            if result.backup_path:
                click.echo(f"Backup: {result.backup_path}")
            if result.vms_updated:
                click.echo(f"\nUpdated VMs ({len(result.vms_updated)}):")
                for vm in result.vms_updated:
                    click.echo(f"  - {vm}")
            sys.exit(0)
        else:
            click.echo(f"Failed: {result.message}", err=True)
            if result.vms_failed:
                click.echo(f"\nFailed VMs ({len(result.vms_failed)}):")
                for vm in result.vms_failed:
                    click.echo(f"  - {vm}")
            sys.exit(1)

    except KeyRotationError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@template.command(name="create")
@click.argument("name", type=str)
@click.option("--description", help="Template description", type=str)
@click.option("--vm-size", help="Azure VM size", type=str)
@click.option("--region", help="Azure region", type=str)
@click.option("--cloud-init", help="Path to cloud-init script file", type=click.Path(exists=True))
def template_create(
    name: str,
    description: str | None,
    vm_size: str | None,
    region: str | None,
    cloud_init: str | None,
):
    """Create a new VM template.

    Templates are stored as YAML files in ~/.azlin/templates/ and can be
    used when creating VMs with the --template option.

    \b
    Examples:
        azlin template create dev-vm --vm-size Standard_B2s --region westus2
        azlin template create prod-vm --description "Production configuration"
    """
    try:
        # Load config for defaults
        try:
            config = ConfigManager.load_config(None)
        except ConfigError:
            config = AzlinConfig()

        # Use provided values or defaults
        final_description = description or f"Template: {name}"
        final_vm_size = vm_size or config.default_vm_size
        final_region = region or config.default_region

        # Load cloud-init if provided
        cloud_init_content = None
        if cloud_init:
            cloud_init_path = Path(cloud_init).expanduser().resolve()
            cloud_init_content = cloud_init_path.read_text()

        # Create template
        template = VMTemplateConfig(
            name=name,
            description=final_description,
            vm_size=final_vm_size,
            region=final_region,
            cloud_init=cloud_init_content,
        )

        TemplateManager.create_template(template)

        click.echo(f"Created template: {name}")
        click.echo(f"  Description: {final_description}")
        click.echo(f"  VM Size:     {final_vm_size}")
        click.echo(f"  Region:      {final_region}")
        if cloud_init_content:
            click.echo("  Cloud-init:  Custom script included")

    except TemplateError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in keys rotate")
        sys.exit(1)


@keys_group.command(name="list")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--all-vms", is_flag=True, help="List all VMs (not just azlin prefix)")
@click.option("--vm-prefix", default="azlin", help="Only list VMs with this prefix")
def keys_list(resource_group: str | None, config: str | None, all_vms: bool, vm_prefix: str):
    """List VMs and their SSH public keys.

    Shows which SSH public key is configured on each VM.

    \b
    Examples:
        azlin keys list
        azlin keys list --rg my-resource-group
        azlin keys list --all-vms
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # Determine VM prefix
        prefix = "" if all_vms else vm_prefix

        click.echo(f"Listing SSH keys for VMs in resource group: {rg}\n")

        # List VM keys
        vm_keys = SSHKeyRotator.list_vm_keys(resource_group=rg, vm_prefix=prefix)

        if not vm_keys:
            click.echo("No VMs found.")
            return

        # Display table
        click.echo("=" * 100)
        click.echo(f"{'VM NAME':<35} {'PUBLIC KEY (first 50 chars)':<65}")
        click.echo("=" * 100)

        for vm_key in vm_keys:
            key_display = vm_key.public_key[:50] + "..." if vm_key.public_key else "N/A"
            click.echo(f"{vm_key.vm_name:<35} {key_display:<65}")

        click.echo("=" * 100)
        click.echo(f"\nTotal: {len(vm_keys)} VMs")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        logger.exception("Unexpected error in keys list")
        sys.exit(1)


@batch.command(name="start")
@click.option("--tag", help="Filter VMs by tag (format: key=value)", type=str)
@click.option("--vm-pattern", help="Filter VMs by name pattern (glob)", type=str)
@click.option("--all", "select_all", is_flag=True, help="Select all VMs in resource group")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--max-workers", default=10, help="Maximum parallel workers (default: 10)", type=int)
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def batch_start(
    tag: str | None,
    vm_pattern: str | None,
    select_all: bool,
    resource_group: str | None,
    config: str | None,
    max_workers: int,
    confirm: bool,
):
    """Batch start VMs.

    Start multiple stopped/deallocated VMs simultaneously.

    \b
    Examples:
        azlin batch start --tag 'env=dev'
        azlin batch start --vm-pattern 'test-*'
        azlin batch start --all --confirm
    """
    try:
        # Validate selection options
        _validate_batch_selection(tag, vm_pattern, select_all)

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # List and select VMs
        click.echo(f"Loading VMs from resource group: {rg}...")
        all_vms = VMManager.list_vms(rg, include_stopped=True)
        selected_vms, selection_desc = _select_vms_by_criteria(all_vms, tag, vm_pattern, select_all)

        # Filter to only stopped VMs
        stopped_vms = [vm for vm in selected_vms if vm.is_stopped()]
        if not stopped_vms:
            click.echo(f"No stopped VMs found matching {selection_desc}.")
            return

        # Show summary
        click.echo(f"\nFound {len(stopped_vms)} stopped VM(s) matching {selection_desc}:")
        click.echo("=" * 80)
        for vm in stopped_vms:
            click.echo(f"  {vm.name:<35} {vm.power_state:<20} {vm.location}")
        click.echo("=" * 80)

        # Confirmation
        if not _confirm_batch_operation(len(stopped_vms), "start", confirm):
            return

        # Execute batch start
        click.echo(f"\nStarting {len(stopped_vms)} VM(s)...")
        executor = BatchExecutor(max_workers=max_workers)

        def progress_callback(msg: str):
            click.echo(f"  {msg}")

        results = executor.execute_start(stopped_vms, rg, progress_callback=progress_callback)

        # Show results
        batch_result = BatchResult(results)
        _display_batch_summary(batch_result, "Start")

        sys.exit(0 if batch_result.all_succeeded else 1)

    except BatchExecutorError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in batch start")
        sys.exit(1)


@batch.command()
@click.argument("command", type=str)
@click.option("--tag", help="Filter VMs by tag (format: key=value)", type=str)
@click.option("--vm-pattern", help="Filter VMs by name pattern (glob)", type=str)
@click.option("--all", "select_all", is_flag=True, help="Select all VMs in resource group")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--max-workers", default=10, help="Maximum parallel workers (default: 10)", type=int)
@click.option("--timeout", default=300, help="Command timeout in seconds (default: 300)", type=int)
@click.option("--show-output", is_flag=True, help="Show command output from each VM")
def command(
    command: str,
    tag: str | None,
    vm_pattern: str | None,
    select_all: bool,
    resource_group: str | None,
    config: str | None,
    max_workers: int,
    timeout: int,
    show_output: bool,
):
    """Execute command on multiple VMs.

    Execute a shell command on multiple VMs simultaneously.

    \b
    Examples:
        azlin batch command 'git pull' --tag 'env=dev'
        azlin batch command 'df -h' --vm-pattern 'web-*'
        azlin batch command 'uptime' --all --show-output
    """
    try:
        # Validate selection options
        _validate_batch_selection(tag, vm_pattern, select_all)

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # List and select VMs
        click.echo(f"Loading VMs from resource group: {rg}...")
        all_vms = VMManager.list_vms(rg, include_stopped=False)
        selected_vms, selection_desc = _select_vms_by_criteria(all_vms, tag, vm_pattern, select_all)

        # Filter to running VMs with IPs
        running_vms = [vm for vm in selected_vms if vm.is_running() and vm.public_ip]
        if not running_vms:
            click.echo(f"No running VMs with public IPs found matching {selection_desc}.")
            return

        # Show summary
        click.echo(f"\nFound {len(running_vms)} VM(s) matching {selection_desc}:")
        click.echo("=" * 80)
        for vm in running_vms:
            click.echo(f"  {vm.name:<35} {vm.public_ip:<15}")
        click.echo("=" * 80)
        click.echo(f"\nCommand: {command}")

        # Execute batch command
        click.echo(f"\nExecuting command on {len(running_vms)} VM(s)...")
        executor = BatchExecutor(max_workers=max_workers)

        def progress_callback(msg: str):
            click.echo(f"  {msg}")

        results = executor.execute_command(
            running_vms, command, rg, timeout=timeout, progress_callback=progress_callback
        )

        # Show results
        batch_result = BatchResult(results)
        _display_batch_summary(batch_result, "Command")

        # Show output if requested
        if show_output:
            click.echo("\nCommand Output:")
            click.echo("=" * 80)
            for result in results:
                click.echo(f"\n[{result.vm_name}]")
                if result.output:
                    click.echo(result.output)
                else:
                    click.echo("  (no output)")
            click.echo("=" * 80)

        sys.exit(0 if batch_result.all_succeeded else 1)

    except BatchExecutorError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in batch command")
        sys.exit(1)


@batch.command(name="sync")
@click.option("--tag", help="Filter VMs by tag (format: key=value)", type=str)
@click.option("--vm-pattern", help="Filter VMs by name pattern (glob)", type=str)
@click.option("--all", "select_all", is_flag=True, help="Select all VMs in resource group")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--max-workers", default=10, help="Maximum parallel workers (default: 10)", type=int)
@click.option("--dry-run", is_flag=True, help="Show what would be synced without syncing")
def batch_sync(
    tag: str | None,
    vm_pattern: str | None,
    select_all: bool,
    resource_group: str | None,
    config: str | None,
    max_workers: int,
    dry_run: bool,
):
    """Batch sync home directory to VMs.

    Sync ~/.azlin/home/ to multiple VMs simultaneously.

    \b
    Examples:
        azlin batch sync --tag 'env=dev'
        azlin batch sync --vm-pattern 'web-*'
        azlin batch sync --all --dry-run
    """
    try:
        # Validate selection options
        _validate_batch_selection(tag, vm_pattern, select_all)

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # List and select VMs
        click.echo(f"Loading VMs from resource group: {rg}...")
        all_vms = VMManager.list_vms(rg, include_stopped=False)
        selected_vms, selection_desc = _select_vms_by_criteria(all_vms, tag, vm_pattern, select_all)

        # Filter to running VMs with IPs
        running_vms = [vm for vm in selected_vms if vm.is_running() and vm.public_ip]
        if not running_vms:
            click.echo(f"No running VMs with public IPs found matching {selection_desc}.")
            return

        # Show summary
        click.echo(f"\nFound {len(running_vms)} VM(s) matching {selection_desc}:")
        click.echo("=" * 80)
        for vm in running_vms:
            click.echo(f"  {vm.name:<35} {vm.public_ip:<15}")
        click.echo("=" * 80)

        if dry_run:
            click.echo("\n[DRY RUN] No files will be synced")

        # Execute batch sync
        click.echo(f"\nSyncing to {len(running_vms)} VM(s)...")
        executor = BatchExecutor(max_workers=max_workers)

        def progress_callback(msg: str):
            click.echo(f"  {msg}")

        results = executor.execute_sync(
            running_vms, rg, dry_run=dry_run, progress_callback=progress_callback
        )

        # Show results
        batch_result = BatchResult(results)
        _display_batch_summary(batch_result, "Sync")

        sys.exit(0 if batch_result.all_succeeded else 1)

    except BatchExecutorError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in batch sync")
        sys.exit(1)


@keys_group.command(name="export")
@click.option("--output", help="Output file path", type=click.Path(), required=True)
def keys_export(output: str):
    """Export current SSH public key to file.

    Exports the azlin SSH public key to a specified file.

    \b
    Examples:
        azlin keys export --output ~/my-keys/azlin.pub
        azlin keys export --output ./keys.txt
    """
    try:
        output_path = Path(output).expanduser().resolve()

        click.echo(f"Exporting public key to: {output_path}")

        success = SSHKeyRotator.export_public_key(output_file=output_path)

        if success:
            click.echo(f"\nSuccess! Public key exported to: {output_path}")
        else:
            click.echo("\nFailed to export public key", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        logger.exception("Unexpected error in keys export")
        sys.exit(1)


@keys_group.command(name="backup")
@click.option(
    "--destination", help="Backup destination (default: ~/.azlin/key_backups/)", type=click.Path()
)
@template.command(name="list")
def template_list():
    """List all available templates.

    Shows all templates stored in ~/.azlin/templates/.

    \b
    Examples:
        azlin template list
    """
    try:
        templates = TemplateManager.list_templates()

        if not templates:
            click.echo("No templates found.")
            click.echo("\nCreate a template with: azlin template create <name>")
            return

        click.echo(f"\nAvailable Templates ({len(templates)}):")
        click.echo("=" * 90)
        click.echo(f"{'NAME':<25} {'VM SIZE':<20} {'REGION':<15} {'DESCRIPTION':<30}")
        click.echo("=" * 90)

        for t in templates:
            desc = t.description[:27] + "..." if len(t.description) > 30 else t.description
            click.echo(f"{t.name:<25} {t.vm_size:<20} {t.region:<15} {desc:<30}")

        click.echo("=" * 90)
        click.echo("\nUse with: azlin new --template <name>")

    except TemplateError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@template.command(name="delete")
@click.argument("name", type=str)
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def template_delete(name: str, force: bool):
    """Delete a template.

    Removes the template file from ~/.azlin/templates/.

    \b
    Examples:
        azlin template delete dev-vm
        azlin template delete dev-vm --force
    """
    try:
        # Verify template exists
        template = TemplateManager.get_template(name)

        # Confirm deletion unless --force
        if not force:
            click.echo(f"\nTemplate: {template.name}")
            click.echo(f"  Description: {template.description}")
            click.echo(f"  VM Size:     {template.vm_size}")
            click.echo(f"  Region:      {template.region}")
            click.echo("\nThis action cannot be undone.")

            confirm = input("\nDelete this template? [y/N]: ").lower()
            if confirm not in ["y", "yes"]:
                click.echo("Cancelled.")
                return

        # Delete template
        TemplateManager.delete_template(name)
        click.echo(f"Deleted template: {name}")

    except TemplateError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@template.command(name="export")
@click.argument("name", type=str)
@click.argument("output_file", type=click.Path())
def template_export(name: str, output_file: str):
    """Export a template to a YAML file.

    Exports the template configuration to a file that can be shared
    or imported on another machine.

    \b
    Examples:
        azlin template export dev-vm my-template.yaml
        azlin template export dev-vm ~/shared/template.yaml
    """
    try:
        output_path = Path(output_file).expanduser().resolve()

        # Check if file exists
        if output_path.exists():
            confirm = input(f"\nFile '{output_path}' exists. Overwrite? [y/N]: ").lower()
            if confirm not in ["y", "yes"]:
                click.echo("Cancelled.")
                return

        TemplateManager.export_template(name, output_path)
        click.echo(f"Exported template '{name}' to: {output_path}")

    except TemplateError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@template.command(name="import")
@click.argument("input_file", type=click.Path(exists=True))
def template_import(input_file: str):
    """Import a template from a YAML file.

    Imports a template configuration from a file and saves it
    to ~/.azlin/templates/.

    \b
    Examples:
        azlin template import my-template.yaml
        azlin template import ~/shared/template.yaml
    """
    try:
        input_path = Path(input_file).expanduser().resolve()

        template = TemplateManager.import_template(input_path)

        click.echo(f"Imported template: {template.name}")
        click.echo(f"  Description: {template.description}")
        click.echo(f"  VM Size:     {template.vm_size}")
        click.echo(f"  Region:      {template.region}")

    except TemplateError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@snapshot.command(name="create")
@click.argument("vm_name")
@click.option("--resource-group", "--rg", help="Resource group name", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def snapshot_create(vm_name: str, resource_group: str | None, config: str | None):
    """Create a snapshot of a VM's OS disk.

    Creates a point-in-time snapshot of the VM's OS disk for backup purposes.
    Snapshots are automatically named with timestamps.

    \b
    EXAMPLES:
        # Create snapshot using default resource group
        $ azlin snapshot create my-vm

        # Create snapshot with specific resource group
        $ azlin snapshot create my-vm --rg my-resource-group
    """
    try:
        # Load config for defaults
        try:
            azlin_config = ConfigManager.load_config(config)
        except ConfigError:
            azlin_config = AzlinConfig()

        # Get resource group
        rg = resource_group or azlin_config.default_resource_group
        if not rg:
            click.echo(
                "Error: No resource group specified. Use --rg or set default_resource_group in config.",
                err=True,
            )
            sys.exit(1)

        # Create snapshot
        click.echo(f"\nCreating snapshot for VM: {vm_name}")
        manager = SnapshotManager()
        snapshot = manager.create_snapshot(vm_name, rg)

        # Show cost estimate
        size_gb = snapshot.size_gb or 0
        monthly_cost = manager.get_snapshot_cost_estimate(size_gb, 30)
        click.echo("\n✓ Snapshot created successfully!")
        click.echo(f"  Name:     {snapshot.name}")
        click.echo(f"  Size:     {size_gb} GB")
        click.echo(f"  Created:  {snapshot.creation_time}")
        click.echo(f"\nEstimated storage cost: ${monthly_cost:.2f}/month")

    except SnapshotError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@snapshot.command(name="list")
@click.argument("vm_name")
@click.option("--resource-group", "--rg", help="Resource group name", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def snapshot_list(vm_name: str, resource_group: str | None, config: str | None):
    """List all snapshots for a VM.

    Shows all snapshots created for the specified VM, sorted by creation time.

    \b
    EXAMPLES:
        # List snapshots for a VM
        $ azlin snapshot list my-vm

        # List snapshots with specific resource group
        $ azlin snapshot list my-vm --rg my-resource-group
    """
    try:
        # Load config for defaults
        try:
            azlin_config = ConfigManager.load_config(config)
        except ConfigError:
            azlin_config = AzlinConfig()

        # Get resource group
        rg = resource_group or azlin_config.default_resource_group
        if not rg:
            click.echo(
                "Error: No resource group specified. Use --rg or set default_resource_group in config.",
                err=True,
            )
            sys.exit(1)

        # List snapshots
        manager = SnapshotManager()
        snapshots = manager.list_snapshots(vm_name, rg)

        if not snapshots:
            click.echo(f"\nNo snapshots found for VM: {vm_name}")
            return

        # Display snapshots table
        click.echo(f"\nSnapshots for VM: {vm_name}")
        click.echo("=" * 90)
        click.echo(f"{'NAME':<50} {'SIZE':<10} {'CREATED':<30}")
        click.echo("=" * 90)

        total_size = 0
        for snap in snapshots:
            created = str(snap.creation_time)[:19].replace("T", " ")
            size_gb = snap.size_gb or 0
            click.echo(f"{snap.name:<50} {size_gb:<10} {created:<30}")
            total_size += size_gb

        click.echo("=" * 90)
        click.echo(f"\nTotal: {len(snapshots)} snapshots ({total_size} GB)")

        # Show cost estimate
        monthly_cost = manager.get_snapshot_cost_estimate(total_size, 30)
        click.echo(f"Estimated total storage cost: ${monthly_cost:.2f}/month\n")

    except SnapshotError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@snapshot.command(name="restore")
@click.argument("vm_name")
@click.argument("snapshot_name")
@click.option("--resource-group", "--rg", help="Resource group name", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def snapshot_restore(
    vm_name: str, snapshot_name: str, resource_group: str | None, config: str | None, force: bool
):
    """Restore a VM from a snapshot.

    WARNING: This will stop the VM, delete the current OS disk, and replace it
    with a disk created from the snapshot. All data on the current disk will be lost.

    \b
    EXAMPLES:
        # Restore VM from a snapshot (with confirmation)
        $ azlin snapshot restore my-vm my-vm-snapshot-20251015-053000

        # Restore without confirmation
        $ azlin snapshot restore my-vm my-vm-snapshot-20251015-053000 --force
    """
    try:
        # Load config for defaults
        try:
            azlin_config = ConfigManager.load_config(config)
        except ConfigError:
            azlin_config = AzlinConfig()

        # Get resource group
        rg = resource_group or azlin_config.default_resource_group
        if not rg:
            click.echo(
                "Error: No resource group specified. Use --rg or set default_resource_group in config.",
                err=True,
            )
            sys.exit(1)

        # Confirm restoration
        if not force:
            click.echo(
                f"\nWARNING: This will restore VM '{vm_name}' from snapshot '{snapshot_name}'"
            )
            click.echo("This operation will:")
            click.echo("  1. Stop/deallocate the VM")
            click.echo("  2. Delete the current OS disk")
            click.echo("  3. Create a new disk from the snapshot")
            click.echo("  4. Attach the new disk to the VM")
            click.echo("  5. Start the VM")
            click.echo("\nAll current data on the VM disk will be lost!")
            click.echo("\nContinue? [y/N]: ", nl=False)
            response = input().lower()
            if response not in ["y", "yes"]:
                click.echo("Cancelled.")
                return

        # Restore snapshot
        click.echo(f"\nRestoring VM '{vm_name}' from snapshot '{snapshot_name}'...")
        click.echo("This may take several minutes...\n")

        manager = SnapshotManager()
        manager.restore_snapshot(vm_name, snapshot_name, rg)

        click.echo(f"\n✓ VM '{vm_name}' successfully restored from snapshot!")
        click.echo(f"  The VM is now running with the disk from: {snapshot_name}\n")

    except SnapshotError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@snapshot.command(name="delete")
@click.argument("snapshot_name")
@click.option("--resource-group", "--rg", help="Resource group name", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def snapshot_delete(
    snapshot_name: str, resource_group: str | None, config: str | None, force: bool
):
    """Delete a snapshot.

    Permanently deletes a snapshot to free up storage and reduce costs.

    \b
    EXAMPLES:
        # Delete a snapshot (with confirmation)
        $ azlin snapshot delete my-vm-snapshot-20251015-053000

        # Delete without confirmation
        $ azlin snapshot delete my-vm-snapshot-20251015-053000 --force
    """
    try:
        # Load config for defaults
        try:
            azlin_config = ConfigManager.load_config(config)
        except ConfigError:
            azlin_config = AzlinConfig()

        # Get resource group
        rg = resource_group or azlin_config.default_resource_group
        if not rg:
            click.echo(
                "Error: No resource group specified. Use --rg or set default_resource_group in config.",
                err=True,
            )
            sys.exit(1)

        # Confirm deletion
        if not force:
            click.echo(f"\nAre you sure you want to delete snapshot '{snapshot_name}'?")
            click.echo("This action cannot be undone!")
            click.echo("\nContinue? [y/N]: ", nl=False)
            response = input().lower()
            if response not in ["y", "yes"]:
                click.echo("Cancelled.")
                return

        # Delete snapshot
        manager = SnapshotManager()
        manager.delete_snapshot(snapshot_name, rg)

        click.echo(f"\n✓ Snapshot '{snapshot_name}' deleted successfully!\n")

    except SnapshotError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# Register auth commands
main.add_command(auth)

# Register ask commands (Natural Language Fleet Queries)
main.add_command(ask_group)
main.add_command(ask_command)

# Register context commands
main.add_command(context_group)

# Register bastion commands
main.add_command(bastion_group)

# Register compose commands
main.add_command(compose_group)

# Register storage commands
main.add_command(storage_group)
main.add_command(tag_group)

# Register costs commands
main.add_command(costs_group)

# Register autopilot commands
main.add_command(autopilot_group)

# Register fleet commands
main.add_command(fleet_group)

# Register GitHub runner commands
main.add_command(github_runner_group)

# Register monitoring commands (Issue #423 - cli.py decomposition POC)
main.add_command(status)

# Register restore command
main.add_command(restore_command, name="restore")

# Register doit commands (replace old doit if it exists)
if "doit" in main.commands:
    del main.commands["doit"]
main.add_command(doit_group)

# Register NLP commands (Issue #423 refactor)
main.add_command(do)
main.add_command(azdoit_main, name="azdoit")

# Register provisioning commands (Issue #423 refactor)
main.add_command(new)
main.add_command(vm)
main.add_command(create)
main.add_command(clone)

# Register lifecycle commands (Issue #423 refactor)
main.add_command(start)
main.add_command(stop)
main.add_command(kill)
main.add_command(destroy)
main.add_command(killall)
main.add_command(prune)

# Register connectivity commands (Issue #423 refactor)
main.add_command(connect)
main.add_command(code_command, name="code")
main.add_command(sync)
main.add_command(sync_keys, name="sync-keys")
main.add_command(cp)

# Register monitoring commands (Issue #423 refactor)
main.add_command(list_command, name="list")
main.add_command(session_command, name="session")
main.add_command(session_group)  # Session save/load/list commands
main.add_command(w)
main.add_command(ps)
main.add_command(top)

# Register batch commands (Issue #423 refactor)
main.add_command(batch)

# Register IP diagnostic commands (Issue #423 refactor)
main.add_command(ip)

# Register environment commands (Issue #423 refactor)
main.add_command(env)

# Register keys commands (Issue #423 refactor)
main.add_command(keys_group, name="keys")

# Register snapshot commands (Issue #423 refactor)
main.add_command(snapshot)

# Register template commands (Issue #423 refactor)
main.add_command(template)

# Register web commands (Issue #423 refactor)
main.add_command(web)


# env command - Moved to azlin.commands.env (Issue #423 refactor)
@env.command(name="set")
@click.argument("vm_identifier", type=str)
@click.argument("env_var", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--force", is_flag=True, help="Skip secret detection warnings")
def env_set(
    vm_identifier: str, env_var: str, resource_group: str | None, config: str | None, force: bool
):
    """Set environment variable on VM.

    ENV_VAR should be in format KEY=VALUE.

    \b
    Examples:
        azlin env set my-vm DATABASE_URL="postgres://localhost/db"
        azlin env set my-vm API_KEY=secret123 --force
        azlin env set 20.1.2.3 NODE_ENV=production
    """
    try:
        # Parse KEY=VALUE
        if "=" not in env_var:
            click.echo("Error: ENV_VAR must be in format KEY=VALUE", err=True)
            sys.exit(1)

        key, value = env_var.split("=", 1)
        key = key.strip()
        value = value.strip()

        # Remove quotes if present
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]

        # Get SSH config
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        # Detect secrets and warn
        if not force:
            warnings = EnvManager.detect_secrets(value)
            if warnings:
                click.echo("WARNING: Potential secret detected!", err=True)
                for warning in warnings:
                    click.echo(f"  - {warning}", err=True)
                click.echo("\nAre you sure you want to set this value? [y/N]: ", nl=False)
                response = input().lower()
                if response not in ["y", "yes"]:
                    click.echo("Cancelled.")
                    return

        # Set the variable
        EnvManager.set_env_var(ssh_config, key, value)

        click.echo(f"Set {key} on {vm_identifier}")

    except EnvManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@env.command(name="list")
@click.argument("vm_identifier", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--show-values", is_flag=True, help="Show full values (default: masked)")
def env_list(vm_identifier: str, resource_group: str | None, config: str | None, show_values: bool):
    """List environment variables on VM.

    \b
    Examples:
        azlin env list my-vm
        azlin env list my-vm --show-values
        azlin env list 20.1.2.3
    """
    try:
        # Get SSH config
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        # List variables
        env_vars = EnvManager.list_env_vars(ssh_config)

        if not env_vars:
            click.echo(f"No environment variables set on {vm_identifier}")
            return

        click.echo(f"\nEnvironment variables on {vm_identifier}:")
        click.echo("=" * 80)

        for key, value in sorted(env_vars.items()):
            if show_values:
                click.echo(f"  {key}={value}")
            else:
                # Mask values that might be secrets
                warnings = EnvManager.detect_secrets(value)
                if warnings or len(value) > 20:
                    masked = "***" if warnings else value[:20] + "..."
                    click.echo(f"  {key}={masked}")
                else:
                    click.echo(f"  {key}={value}")

        click.echo("=" * 80)
        click.echo(f"\nTotal: {len(env_vars)} variables")
        if not show_values:
            click.echo("Use --show-values to display full values\n")

    except EnvManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@env.command(name="delete")
@click.argument("vm_identifier", type=str)
@click.argument("key", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def env_delete(vm_identifier: str, key: str, resource_group: str | None, config: str | None):
    """Delete environment variable from VM.

    \b
    Examples:
        azlin env delete my-vm API_KEY
        azlin env delete 20.1.2.3 DATABASE_URL
    """
    try:
        # Get SSH config
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        # Delete the variable
        result = EnvManager.delete_env_var(ssh_config, key)

        if result:
            click.echo(f"Deleted {key} from {vm_identifier}")
        else:
            click.echo(f"Variable {key} not found on {vm_identifier}", err=True)
            sys.exit(1)

    except EnvManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@env.command(name="export")
@click.argument("vm_identifier", type=str)
@click.argument("output_file", type=str, required=False)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def env_export(
    vm_identifier: str, output_file: str | None, resource_group: str | None, config: str | None
):
    """Export environment variables to .env file format.

    \b
    Examples:
        azlin env export my-vm prod.env
        azlin env export my-vm  # Print to stdout
    """
    try:
        # Get SSH config
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        # Export variables
        result = EnvManager.export_env_vars(ssh_config, output_file)

        if output_file:
            click.echo(f"Exported environment variables to {output_file}")
        else:
            click.echo(result)

    except EnvManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@env.command(name="import")
@click.argument("vm_identifier", type=str)
@click.argument("env_file", type=click.Path(exists=True))
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def env_import(vm_identifier: str, env_file: str, resource_group: str | None, config: str | None):
    """Import environment variables from .env file.

    \b
    Examples:
        azlin env import my-vm .env
        azlin env import my-vm prod.env
    """
    try:
        # Get SSH config
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        # Import variables
        count = EnvManager.import_env_file(ssh_config, env_file)

        click.echo(f"Imported {count} variables to {vm_identifier}")

    except EnvManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@env.command(name="clear")
@click.argument("vm_identifier", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def env_clear(vm_identifier: str, resource_group: str | None, config: str | None, force: bool):
    """Clear all environment variables from VM.

    \b
    Examples:
        azlin env clear my-vm
        azlin env clear my-vm --force
    """
    try:
        # Get SSH config
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        # Confirm unless --force
        if not force:
            env_vars = EnvManager.list_env_vars(ssh_config)
            if not env_vars:
                click.echo(f"No environment variables set on {vm_identifier}")
                return

            click.echo(
                f"This will delete {len(env_vars)} environment variable(s) from {vm_identifier}"
            )
            click.echo("Are you sure? [y/N]: ", nl=False)
            response = input().lower()
            if response not in ["y", "yes"]:
                click.echo("Cancelled.")
                return

        # Clear all variables
        EnvManager.clear_all_env_vars(ssh_config)

        click.echo(f"Cleared all environment variables from {vm_identifier}")

    except EnvManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


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
    from .azdoit.cli import main as azdoit_cli_main

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
    import sys

    sys.argv = ["azdoit", request]
    azdoit_cli_main()


@click.group(name="web")
def web():
    """Manage the Azlin Mobile PWA web server."""
    pass


@web.command(name="start")
@click.option("--port", default=3000, help="Port to run the dev server on", type=int)
@click.option("--host", default="localhost", help="Host to bind to", type=str)
def web_start(port: int, host: str):
    """Start the Azlin Mobile PWA development server.

    This command starts the Vite dev server for the React PWA that manages
    azlin VMs from iPhone/mobile devices.

    Once started, open http://localhost:3000 in Safari on your iPhone and
    add to home screen for a native-like app experience.
    """
    from pathlib import Path

    # Find the PWA directory - try multiple locations
    # 1. Development: src/azlin/cli.py -> ../../pwa
    dev_pwa_dir = Path(__file__).parent.parent.parent / "pwa"

    # 2. Installed via pip: site-packages/azlin/cli.py -> ../pwa
    installed_pwa_dir = Path(__file__).parent.parent / "pwa"

    # 3. Git repo: check if we're in a git repo
    git_root_pwa_dir = None
    try:
        import subprocess as sp

        git_root = sp.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=2
        )
        if git_root.returncode == 0:
            git_root_pwa_dir = Path(git_root.stdout.strip()) / "pwa"
    except Exception:
        pass

    # Try paths in order
    pwa_dir = None
    for candidate in [dev_pwa_dir, installed_pwa_dir, git_root_pwa_dir]:
        if candidate and candidate.exists():
            pwa_dir = candidate
            break

    if not pwa_dir:
        click.echo("Error: PWA directory not found. Tried:", err=True)
        click.echo(f"  - {dev_pwa_dir} (development)", err=True)
        click.echo(f"  - {installed_pwa_dir} (installed)", err=True)
        if git_root_pwa_dir:
            click.echo(f"  - {git_root_pwa_dir} (git root)", err=True)
        click.echo("\nThe PWA may not be installed yet.", err=True)
        click.echo("Run this command from the azlin repository root.", err=True)
        sys.exit(1)

    # Auto-generate .env from azlin config if needed
    try:
        from azlin.modules.pwa_config_generator import generate_pwa_env_from_azlin

        result = generate_pwa_env_from_azlin(pwa_dir, force=False)

        # Display success messages
        if result.success and result.message:
            click.echo(f"✅ {result.message}")

            # Show config sources if available
            if result.source_attribution:
                click.echo("\n📋 Configuration sources:")
                for var_name, source in result.source_attribution.items():
                    click.echo(f"  • {var_name}: {source.value}")

        # Display errors (blocking)
        if not result.success:
            click.echo("\n❌ Failed to generate PWA configuration:", err=True)
            if result.error:
                click.echo(f"   {result.error}", err=True)
            click.echo("\n💡 Solutions:", err=True)
            click.echo(
                "   1. Install Azure CLI: https://docs.microsoft.com/cli/azure/install-azure-cli",
                err=True,
            )
            click.echo("   2. Authenticate: az login", err=True)
            click.echo("   3. Or manually create pwa/.env from pwa/.env.example", err=True)
            sys.exit(1)

    except ImportError as e:
        # Module not available - skip config generation
        click.echo(f"⚠️  PWA config generator not available: {e}", err=True)
        click.echo("   Continuing without auto-config generation...", err=True)
    except Exception as e:
        # Non-fatal error - warn but continue
        click.echo(f"⚠️  Config generation failed: {e}", err=True)
        click.echo("   Continuing with manual .env setup...", err=True)

    # Check if node_modules exists
    if not (pwa_dir / "node_modules").exists():
        click.echo("Installing PWA dependencies (first time only)...")
        subprocess.run(["npm", "install"], cwd=pwa_dir, check=True)

    click.echo(f"🏴‍☠️ Starting Azlin Mobile PWA on http://{host}:{port}")
    click.echo("📱 Open in Safari on your iPhone and add to home screen")
    click.echo("Press Ctrl+C to stop the server")
    click.echo("")

    try:
        subprocess.run(
            ["npm", "run", "dev", "--", "--port", str(port), "--host", host],
            cwd=pwa_dir,
            check=True,
        )
    except KeyboardInterrupt:
        click.echo("\n🛑 PWA server stopped")
    except subprocess.CalledProcessError as e:
        click.echo(f"Error starting PWA: {e}", err=True)
        sys.exit(1)


@web.command(name="stop")
def web_stop():
    """Stop the Azlin Mobile PWA development server.

    Finds and terminates any running Vite dev server processes for the PWA.
    """
    import signal

    try:
        # Find vite processes
        result = subprocess.run(["pgrep", "-f", "vite.*azlin"], capture_output=True, text=True)

        if result.returncode != 0 or not result.stdout.strip():
            click.echo("No running PWA server found")
            return

        pids = result.stdout.strip().split("\n")
        click.echo(f"Found {len(pids)} PWA server process(es)")

        for pid in pids:
            try:
                import os

                os.kill(int(pid), signal.SIGTERM)
                click.echo(f"✓ Stopped PWA server (PID: {pid})")
            except ProcessLookupError:
                pass  # Already stopped
            except Exception as e:
                click.echo(f"Warning: Could not stop PID {pid}: {e}", err=True)

    except Exception as e:
        click.echo(f"Error stopping PWA: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()


__all__ = ["AzlinError", "CLIOrchestrator", "azdoit_main", "main", "web"]
