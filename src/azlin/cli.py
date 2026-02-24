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
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

import click

from azlin import __version__
from azlin.azure_auth import AuthenticationError, AzureAuthenticator

# Import helper functions from cli_helpers
from azlin.cli_helpers import (
    _perform_startup_checks,
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
    cost,
    costs_group,
    cp,
    create,
    destroy,
    # Disk Commands
    disk_group,
    # NLP Commands
    do,
    doit_group,
    # Environment Commands
    env,
    fleet_group,
    github_runner_group,
    # Health Commands
    health,
    # System Commands
    help_command,
    # IP Commands
    ip,
    # Keys Commands
    keys_group,
    kill,
    killall,
    list_command,
    # Logs Commands
    logs,
    # Provisioning Commands
    new,
    # System Commands
    os_update,
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
    # System Commands
    update,
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
from azlin.commands.monitoring_list import (  # noqa: F401
    _collect_tmux_sessions,
    _create_tunnel_with_retry,
    _handle_multi_context_list,
)

# New modules for v2.0
from azlin.config_manager import ConfigError, ConfigManager
from azlin.distributed_top import DistributedTopExecutor  # noqa: F401
from azlin.modules.file_transfer import FileTransfer  # noqa: F401
from azlin.modules.file_transfer.path_parser import PathParser  # noqa: F401
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
        health        VM health dashboard (Four Golden Signals)
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

# Register disk commands (Issue #685)
main.add_command(disk_group)

# Register costs commands
main.add_command(costs_group)
main.add_command(cost)

# Register system commands (Issue #423 refactor - Phase 3)
main.add_command(help_command, name="help")
main.add_command(os_update, name="os-update")
main.add_command(update)

# Register autopilot commands
main.add_command(autopilot_group)

# Register fleet commands
main.add_command(fleet_group)

# Register GitHub runner commands
main.add_command(github_runner_group)

# Register health dashboard (Issue #566 - Four Golden Signals)
main.add_command(health)

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

# Register logs command (Issue #153)
main.add_command(logs)

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


if __name__ == "__main__":
    main()


__all__ = ["AzlinError", "CLIOrchestrator", "azdoit_main", "main", "web"]
