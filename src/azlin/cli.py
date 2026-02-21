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

import contextlib
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import click
from rich.console import Console

from azlin import __version__
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
from azlin.auth_models import AuthConfig, AuthMethod
from azlin.azure_auth import AuthenticationError, AzureAuthenticator
from azlin.batch_executor import BatchExecutor, BatchExecutorError, BatchResult, BatchSelector
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
from azlin.modules.bastion_detector import BastionDetector
from azlin.modules.bastion_manager import BastionManager, BastionManagerError
from azlin.modules.cli_detector import CLIDetector
from azlin.modules.cli_installer import CLIInstaller, InstallStatus
from azlin.modules.file_transfer import FileTransfer  # noqa: F401
from azlin.modules.file_transfer.path_parser import PathParser  # noqa: F401
from azlin.modules.home_sync import (
    HomeSyncManager,
)
from azlin.modules.interaction_handler import CLIInteractionHandler
from azlin.modules.progress import ProgressDisplay
from azlin.modules.snapshot_manager import SnapshotError, SnapshotManager
from azlin.modules.ssh_connector import SSHConfig, SSHConnector
from azlin.modules.ssh_key_vault import (
    KeyVaultError,
    create_key_vault_manager,
)
from azlin.modules.ssh_keys import SSHKeyError, SSHKeyManager, SSHKeyPair
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
from azlin.vm_connector import VMConnector
from azlin.vm_lifecycle import DeletionSummary, VMLifecycleManager
from azlin.vm_lifecycle_control import VMLifecycleController
from azlin.vm_manager import VMInfo, VMManager, VMManagerError
from azlin.vm_provisioning import (
    PoolProvisioningResult,
    ProvisioningError,
    VMConfig,
    VMDetails,
    VMProvisioner,
)
from azlin.vm_size_tiers import VMSizeTierError, VMSizeTiers

logger = logging.getLogger(__name__)


def _auto_sync_home_directory(ssh_config: SSHConfig) -> None:
    """Auto-sync home directory before SSH connection (silent).

    Args:
        ssh_config: SSH configuration for target VM

    Note:
        Sync failures are silently ignored to not disrupt connection flow.
    """
    try:
        result = HomeSyncManager.sync_to_vm(ssh_config, dry_run=False)
        if result.success and result.files_synced > 0:
            logger.info(f"Auto-synced {result.files_synced} files")
    except Exception as e:
        # Silent failure - log but don't interrupt connection
        logger.debug(f"Auto-sync failed: {e}")


def show_interactive_menu(vms: list[VMInfo], ssh_key_path: Path) -> int | None:
    """Show interactive VM selection menu.

    Args:
        vms: List of available VMs
        ssh_key_path: Path to SSH private key

    Returns:
        Exit code or None to continue to provisioning
    """
    if not vms:
        click.echo("No VMs found. Create a new one? [Y/n]: ", nl=False)
        response = input().lower()
        if response in ["", "y", "yes"]:
            return None  # Continue to provisioning
        return 0

    # Auto-connect if only 1 VM
    if len(vms) == 1:
        vm = vms[0]
        click.echo(f"\nFound 1 VM: {vm.name}")
        click.echo(f"Status: {vm.get_status_display()}")
        click.echo(f"IP: {vm.public_ip}")
        click.echo("\nConnecting...")

        if vm.is_running() and vm.public_ip:
            ssh_config = SSHConfig(host=vm.public_ip, user="azureuser", key_path=ssh_key_path)

            # Sync home directory before connection (silent)
            _auto_sync_home_directory(ssh_config)

            return SSHConnector.connect(ssh_config, tmux_session="azlin", auto_tmux=True)
        click.echo("VM is not running or has no public IP")
        return 1

    # Multiple VMs - show menu
    click.echo("\n" + "=" * 60)
    click.echo("Available VMs:")
    click.echo("=" * 60)

    for idx, vm_info in enumerate(vms, 1):
        status = vm_info.get_status_display()
        ip = vm_info.public_ip or "No IP"
        click.echo(f"  {idx}. {vm_info.name} - {status} - {ip}")

    click.echo("  n. Create new VM")
    click.echo("=" * 60)

    choice = input("\nSelect VM (number or 'n' for new): ").strip().lower()

    if choice == "n":
        return None  # Continue to provisioning

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(vms):
            vm = vms[idx]

            if not vm.is_running():
                click.echo(f"\nVM '{vm.name}' is not running.")
                click.echo(
                    f"Start it with: az vm start --name {vm.name} --resource-group {vm.resource_group}"
                )
                return 1

            if not vm.public_ip:
                click.echo(f"\nVM '{vm.name}' has no public IP.")
                return 1

            click.echo(f"\nConnecting to {vm.name}...")
            ssh_config = SSHConfig(host=vm.public_ip, user="azureuser", key_path=ssh_key_path)

            # Sync home directory before connection (silent)
            _auto_sync_home_directory(ssh_config)

            return SSHConnector.connect(ssh_config, tmux_session="azlin", auto_tmux=True)
        click.echo("Invalid selection")
        return 1
    except ValueError:
        click.echo("Invalid input")
        return 1


def generate_vm_name(custom_name: str | None = None, command: str | None = None) -> str:
    """Generate VM name.

    Args:
        custom_name: Custom name from --name flag
        command: Command string for slug extraction

    Returns:
        VM name
    """
    if custom_name:
        return custom_name

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    if command:
        slug = RemoteExecutor.extract_command_slug(command)
        return f"azlin-{timestamp}-{slug}"

    return f"azlin-{timestamp}"


def execute_command_on_vm(vm: VMInfo, command: str, ssh_key_path: Path) -> int:
    """Execute a command on a VM and display output.

    Args:
        vm: VM to execute command on
        command: Command to execute
        ssh_key_path: Path to SSH private key

    Returns:
        Exit code from command execution
    """
    if not vm.is_running():
        click.echo(
            f"Error: VM '{vm.name}' is not running (status: {vm.get_status_display()})", err=True
        )
        return 1

    if not vm.public_ip:
        click.echo(f"Error: VM '{vm.name}' has no public IP", err=True)
        return 1

    click.echo(f"\nExecuting on {vm.name} ({vm.public_ip}): {command}")
    click.echo("=" * 60)

    ssh_config = SSHConfig(host=vm.public_ip, user="azureuser", key_path=ssh_key_path)

    try:
        # Build SSH command with the remote command
        args = SSHConnector.build_ssh_command(ssh_config, command)

        # Execute and stream output
        result = subprocess.run(args)

        click.echo("=" * 60)
        if result.returncode == 0:
            click.echo(f"Command completed successfully on {vm.name}")
        else:
            click.echo(f"Command failed on {vm.name} with exit code {result.returncode}", err=True)

        return result.returncode

    except Exception as e:
        click.echo(f"Error executing command on {vm.name}: {e}", err=True)
        return 1


def select_vm_for_command(vms: list[VMInfo], command: str) -> VMInfo | None:
    """Show interactive menu to select VM for command execution.

    Args:
        vms: List of available VMs
        command: Command that will be executed

    Returns:
        Selected VM or None to provision new VM
    """
    click.echo("\n" + "=" * 60)
    click.echo(f"Command to execute: {command}")
    click.echo("=" * 60)
    click.echo("\nAvailable VMs:")

    for idx, vm_info in enumerate(vms, 1):
        status = vm_info.get_status_display()
        ip = vm_info.public_ip or "No IP"
        click.echo(f"  {idx}. {vm_info.name} - {status} - {ip}")

    click.echo("  n. Create new VM and execute")
    click.echo("=" * 60)

    choice = input("\nSelect VM (number or 'n' for new): ").strip().lower()

    if choice == "n":
        return None  # Signal to create new VM

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(vms):
            return vms[idx]
        click.echo("Invalid selection")
        return None
    except ValueError:
        click.echo("Invalid input")
        return None


def _perform_startup_checks() -> None:
    """Perform Azure CLI environment checks at startup.

    Detects WSL2 + Windows Azure CLI and offers Linux CLI installation.
    Non-fatal - failures are logged but don't prevent CLI operation.
    """
    try:
        detector = CLIDetector()
        env_info = detector.detect()

        # If there's a problem, offer installation
        if env_info.has_problem:
            logger.info("Azure CLI environment check: %s", env_info.problem_description)

            installer = CLIInstaller()
            result = installer.install()

            if result.status == InstallStatus.SUCCESS:
                logger.info("Azure CLI installation successful")
            elif result.status == InstallStatus.ALREADY_INSTALLED:
                logger.debug("Linux Azure CLI already installed")
            elif result.status == InstallStatus.CANCELLED:
                logger.info("Azure CLI installation skipped")
            elif result.status == InstallStatus.FAILED and result.error_message:
                logger.warning("Azure CLI installation failed: %s", result.error_message)

    except Exception as e:
        # Non-fatal - log and continue
        logger.debug("Azure CLI environment check failed: %s", e)


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


def _load_config_and_template(
    config: str | None, template: str | None
) -> tuple[AzlinConfig, VMTemplateConfig | None]:
    """Load configuration and template.

    Returns:
        Tuple of (azlin_config, template_config)
    """
    try:
        azlin_config = ConfigManager.load_config(config)
    except ConfigError:
        azlin_config = AzlinConfig()

    template_config = None
    if template:
        try:
            template_config = TemplateManager.get_template(template)
            click.echo(f"Using template: {template}")
        except TemplateError as e:
            click.echo(f"Error loading template: {e}", err=True)
            sys.exit(1)

    return azlin_config, template_config


def _resolve_vm_settings(
    resource_group: str | None,
    region: str | None,
    size_tier: str | None,
    vm_size: str | None,
    azlin_config: AzlinConfig,
    template_config: VMTemplateConfig | None,
) -> tuple[str | None, str, str]:
    """Resolve VM settings with precedence: CLI > config > template > defaults.

    Args:
        resource_group: Resource group from CLI
        region: Region from CLI
        size_tier: Size tier (s/m/l/xl) from CLI
        vm_size: Explicit VM size from CLI
        azlin_config: Loaded config
        template_config: Template config if provided

    Returns:
        Tuple of (final_rg, final_region, final_vm_size)
    """
    # Resolve VM size from tier or explicit size
    try:
        resolved_vm_size = VMSizeTiers.resolve_vm_size(size_tier, vm_size)
    except VMSizeTierError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if template_config:
        final_rg = resource_group or azlin_config.default_resource_group
        final_region = region or template_config.region
        final_vm_size = resolved_vm_size or template_config.vm_size
    else:
        final_rg = resource_group or azlin_config.default_resource_group
        final_region = region or azlin_config.default_region
        final_vm_size = resolved_vm_size or azlin_config.default_vm_size

    return final_rg, final_region, final_vm_size


def _validate_inputs(pool: int | None, repo: str | None) -> None:
    """Validate pool size and repo URL."""
    if pool and pool > 10:
        estimated_cost = pool * 0.10
        click.echo(f"\nWARNING: Creating {pool} VMs")
        click.echo(f"Estimated cost: ~${estimated_cost:.2f}/hour")
        click.echo("Continue? [y/N]: ", nl=False)
        response = input().lower()
        if response not in ["y", "yes"]:
            click.echo("Cancelled.")
            sys.exit(0)

    if repo and not repo.startswith("https://github.com/"):
        click.echo("Error: Invalid GitHub URL. Must start with https://github.com/", err=True)
        sys.exit(1)


def _update_config_state(
    config: str | None, final_rg: str | None, vm_name: str, name: str | None
) -> None:
    """Update config with resource group and session name."""
    if final_rg:
        try:
            ConfigManager.update_config(
                config, default_resource_group=final_rg, last_vm_name=vm_name
            )
            if name:
                ConfigManager.set_session_name(vm_name, name, config)
        except ConfigError as e:
            logger.debug(f"Failed to update config: {e}")


def _execute_command_mode(
    orchestrator: CLIOrchestrator,
    command: str,
    session_name: str | None = None,
    config: str | None = None,
) -> None:
    """Execute VM provisioning and command execution."""
    click.echo(f"\nCommand to execute: {command}")
    click.echo("Provisioning VM first...\n")

    orchestrator.auto_connect = False
    exit_code = orchestrator.run()

    # Save session name mapping if provided
    if session_name and orchestrator.vm_details:
        try:
            ConfigManager.set_session_name(orchestrator.vm_details.name, session_name, config)
            logger.debug(
                f"Saved session name mapping: {orchestrator.vm_details.name} -> {session_name}"
            )
        except ConfigError as e:
            logger.warning(f"Failed to save session name: {e}")

    if exit_code == 0 and orchestrator.vm_details:
        vm_info = VMInfo(
            name=orchestrator.vm_details.name,
            resource_group=orchestrator.vm_details.resource_group,
            location=orchestrator.vm_details.location,
            power_state="VM running",
            public_ip=orchestrator.vm_details.public_ip,
            vm_size=orchestrator.vm_details.size,
        )
        if orchestrator.ssh_keys is None:
            click.echo("Error: SSH keys not initialized", err=True)
            sys.exit(1)
        cmd_exit_code = execute_command_on_vm(vm_info, command, orchestrator.ssh_keys)
        sys.exit(cmd_exit_code)
    else:
        click.echo(f"\nProvisioning failed with exit code {exit_code}", err=True)
        sys.exit(exit_code)


def _provision_pool(
    orchestrator: CLIOrchestrator,
    pool: int,
    vm_name: str,
    final_rg: str | None,
    final_region: str,
    final_vm_size: str,
    session_name: str | None = None,
    config: str | None = None,
) -> None:
    """Provision pool of VMs in parallel."""
    click.echo(f"\nProvisioning pool of {pool} VMs in parallel...")

    ssh_key_pair = SSHKeyManager.ensure_key_exists()

    # Check bastion availability once for the entire pool
    # This ensures consistent behavior with single VM provisioning
    rg_for_bastion_check = final_rg or f"azlin-rg-{int(time.time())}"
    use_bastion, bastion_info = orchestrator._check_bastion_availability(
        rg_for_bastion_check, f"{vm_name} (pool)"
    )
    orchestrator.bastion_info = bastion_info  # Store for later use

    # Determine if public IP should be created
    # Public IP is disabled when using bastion
    public_ip_enabled = not use_bastion

    configs: list[VMConfig] = []
    for i in range(pool):
        vm_name_pool = f"{vm_name}-{i + 1:02d}"
        config_item = orchestrator.provisioner.create_vm_config(
            name=vm_name_pool,
            resource_group=rg_for_bastion_check,
            location=final_region,
            size=final_vm_size,
            ssh_public_key=ssh_key_pair.public_key_content,
            session_name=f"{session_name}-{i + 1:02d}" if session_name else None,
            public_ip_enabled=public_ip_enabled,
        )
        configs.append(config_item)

    try:
        result = orchestrator.provisioner.provision_vm_pool(
            configs,
            progress_callback=lambda msg: click.echo(f"  {msg}"),
            max_workers=min(10, pool),
        )

        # Save session names for successfully provisioned VMs in pool
        if session_name and result.successful:
            for i, vm_details in enumerate(result.successful, 1):
                pool_session_name = f"{session_name}-{i:02d}"
                try:
                    ConfigManager.set_session_name(vm_details.name, pool_session_name, config)
                    logger.debug(f"Saved session name: {vm_details.name} -> {pool_session_name}")
                except ConfigError as e:
                    logger.warning(f"Failed to save session name for {vm_details.name}: {e}")

        _display_pool_results(result)
        sys.exit(0 if result.any_succeeded else 1)
    except ProvisioningError as e:
        click.echo(f"\nPool provisioning failed completely: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"\nUnexpected error: {e}", err=True)
        sys.exit(1)


def _display_pool_results(result: PoolProvisioningResult) -> None:
    """Display pool provisioning results."""
    click.echo(f"\n{result.get_summary()}")

    if result.successful:
        click.echo("\nSuccessfully Provisioned VMs:")
        click.echo("=" * 80)
        for vm_item in result.successful:
            # Display 'Bastion' instead of empty string when no public IP
            ip_display = vm_item.public_ip if vm_item.public_ip else "(Bastion)"
            click.echo(f"  {vm_item.name:<30} {ip_display:<15} {vm_item.location}")
        click.echo("=" * 80)

    if result.failed:
        click.echo("\nFailed VMs:")
        click.echo("=" * 80)
        for failure in result.failed:
            click.echo(f"  {failure.config.name:<30} {failure.error_type:<20} {failure.error[:40]}")
        click.echo("=" * 80)

    if result.rg_failures:
        click.echo("\nResource Group Failures:")
        for rg_fail in result.rg_failures:
            click.echo(f"  {rg_fail.rg_name}: {rg_fail.error}")


def _validate_config_path(
    ctx: click.Context, param: click.Parameter, value: str | None
) -> str | None:
    """Validate that config file parent directory exists.

    Args:
        ctx: Click context
        param: Click parameter
        value: Config file path value

    Returns:
        The config path value if valid

    Raises:
        click.BadParameter: If parent directory doesn't exist
    """
    if value is None:
        return value

    config_path = Path(value)
    parent_dir = config_path.parent

    # Check if parent directory exists
    if not parent_dir.exists():
        raise click.BadParameter(
            f"Parent directory does not exist: {parent_dir}",
            ctx=ctx,
            param=param,
        )

    return value


# new command - Moved to azlin.commands.provisioning (Issue #423 refactor)
# vm command - Moved to azlin.commands.provisioning (Issue #423 refactor)
# create command - Moved to azlin.commands.provisioning (Issue #423 refactor)
# list_command command - Moved to azlin.commands.monitoring (Issue #423 refactor)
# session_command command - Moved to azlin.commands.monitoring (Issue #423 refactor)
# w command - Moved to azlin.commands.monitoring (Issue #423 refactor)
# top command - Moved to azlin.commands.monitoring (Issue #423 refactor)


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
def _handle_delete_resource_group(rg: str, vm_name: str, force: bool, dry_run: bool) -> None:
    """Handle resource group deletion."""
    if dry_run:
        click.echo(f"\n[DRY RUN] Would delete entire resource group: {rg}")
        click.echo(f"This would delete ALL resources in the group, not just '{vm_name}'")
        return

    if not force:
        click.echo(f"\nWARNING: You are about to delete the ENTIRE resource group: {rg}")
        click.echo(f"This will delete ALL resources in the group, not just the VM '{vm_name}'!")
        click.echo("\nThis action cannot be undone.\n")

        confirm = input("Type the resource group name to confirm deletion: ").strip()
        if confirm != rg:
            click.echo("Cancelled. Resource group name did not match.")
            return

    click.echo(f"\nDeleting resource group '{rg}'...")

    cmd = ["az", "group", "delete", "--name", rg, "--yes"]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=True)
        click.echo(f"\nSuccess! Resource group '{rg}' and all resources deleted.")
    except subprocess.CalledProcessError as e:
        click.echo(f"\nError deleting resource group: {e.stderr}", err=True)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        click.echo("\nError: Resource group deletion timed out.", err=True)
        sys.exit(1)


def _handle_vm_dry_run(vm_name: str, rg: str) -> None:
    """Handle dry-run mode for VM deletion."""
    vm = VMManager.get_vm(vm_name, rg)
    if not vm:
        click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'.", err=True)
        sys.exit(1)

    click.echo(f"\n[DRY RUN] Would delete VM: {vm_name}")
    click.echo(f"  Resource Group: {rg}")
    click.echo(f"  Status:         {vm.get_status_display()}")
    click.echo(f"  IP:             {vm.public_ip or 'N/A'}")
    click.echo(f"  Size:           {vm.vm_size or 'N/A'}")
    click.echo("\nResources that would be deleted:")
    click.echo(f"  - VM: {vm_name}")
    click.echo("  - Associated NICs")
    click.echo("  - Associated disks")
    click.echo("  - Associated public IPs")


def _confirm_vm_deletion(vm: VMInfo) -> bool:
    """Show VM details and get confirmation for deletion."""
    click.echo("\nVM Details:")
    click.echo(f"  Name:           {vm.name}")
    click.echo(f"  Resource Group: {vm.resource_group}")
    click.echo(f"  Status:         {vm.get_status_display()}")
    click.echo(f"  IP:             {vm.public_ip or 'N/A'}")
    click.echo(f"  Size:           {vm.vm_size or 'N/A'}")
    click.echo("\nThis will delete the VM and all associated resources (NICs, disks, IPs).")
    click.echo("This action cannot be undone.\n")

    confirm = input("Are you sure you want to delete this VM? [y/N]: ").lower()
    return confirm in ["y", "yes"]


def _execute_vm_deletion(vm_name: str, rg: str, force: bool, config: str | None = None) -> None:
    """Execute VM deletion and display results."""
    vm = VMManager.get_vm(vm_name, rg)

    if not vm:
        click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'.", err=True)
        sys.exit(1)

    if not force and not _confirm_vm_deletion(vm):
        click.echo("Cancelled.")
        return

    click.echo(f"\nDeleting VM '{vm_name}'...")

    result = VMLifecycleManager.delete_vm(
        vm_name=vm_name, resource_group=rg, force=True, no_wait=False
    )

    if result.success:
        click.echo(f"\nSuccess! {result.message}")
        if result.resources_deleted:
            click.echo("\nDeleted resources:")
            for resource in result.resources_deleted:
                click.echo(f"  - {resource}")

        # Clean up SSH key from Key Vault
        _cleanup_key_from_vault(vm_name, config)

        # Clean up session name mapping if it exists
        try:
            if ConfigManager.delete_session_name(vm_name, config):
                click.echo(f"Removed session name mapping for '{vm_name}'")
        except ConfigError:
            pass  # Config cleanup is non-critical

        # Check for orphaned Bastion after VM deletion
        try:
            from azlin.modules.cleanup_orchestrator import CleanupOrchestrator

            cleanup_orch = CleanupOrchestrator(
                resource_group=rg, interaction_handler=CLIInteractionHandler()
            )

            orphaned = cleanup_orch.detect_orphaned_bastions()
            if orphaned:
                click.echo(f"\n🔍 Detected {len(orphaned)} orphaned Bastion host(s)")
                cleanup_results = cleanup_orch.cleanup_orphaned_bastions()

                for cleanup_result in cleanup_results:
                    if cleanup_result.was_successful():
                        click.echo(
                            click.style(
                                f"✓ Removed {cleanup_result.bastion_name} "
                                f"(saving ${cleanup_result.estimated_monthly_savings:.2f}/month)",
                                fg="green",
                            )
                        )
        except Exception as e:
            # Bastion cleanup is optional - don't fail the entire destroy
            logger.debug(f"Bastion cleanup check failed: {e}")

    else:
        click.echo(f"\nError: {result.message}", err=True)
        sys.exit(1)


# destroy command - Moved to azlin.commands.lifecycle (Issue #423 refactor)


def _confirm_killall(vms: list[Any], rg: str) -> bool:
    """Display VMs and get confirmation for bulk deletion."""
    click.echo(f"\nFound {len(vms)} VM(s) in resource group '{rg}':")
    click.echo("=" * 80)
    for vm_item in vms:
        status = vm_item.get_status_display()
        # Display IP with type indicator (Issue #492)
        ip = (
            f"{vm_item.public_ip} (Public)"
            if vm_item.public_ip
            else f"{vm_item.private_ip} (Private)"
            if vm_item.private_ip
            else "N/A"
        )
        click.echo(f"  {vm_item.name:<35} {status:<15} {ip:<15}")
    click.echo("=" * 80)

    click.echo(f"\nThis will delete all {len(vms)} VM(s) and their associated resources.")
    click.echo("This action cannot be undone.\n")

    confirm = input(f"Are you sure you want to delete {len(vms)} VM(s)? [y/N]: ").lower()
    return confirm in ["y", "yes"]


def _display_killall_results(summary: DeletionSummary) -> None:
    """Display killall operation results."""
    click.echo("\n" + "=" * 80)
    click.echo("Deletion Summary")
    click.echo("=" * 80)
    click.echo(f"Total VMs:     {summary.total}")
    click.echo(f"Succeeded:     {summary.succeeded}")
    click.echo(f"Failed:        {summary.failed}")
    click.echo("=" * 80)

    if summary.succeeded > 0:
        click.echo("\nSuccessfully deleted:")
        for result in summary.results:
            if result.success:
                click.echo(f"  - {result.vm_name}")

    if summary.failed > 0:
        click.echo("\nFailed to delete:")
        for result in summary.results:
            if not result.success:
                click.echo(f"  - {result.vm_name}: {result.message}")


# killall command - Moved to azlin.commands.lifecycle (Issue #423 refactor)
# prune command - Moved to azlin.commands.lifecycle (Issue #423 refactor)
# ps command - Moved to azlin.commands.monitoring (Issue #423 refactor)
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


def _interactive_vm_selection(
    rg: str, config: str | None, no_tmux: bool, tmux_session: str | None
) -> str:
    """Show interactive VM selection menu and return selected VM name."""
    try:
        vms = VMManager.list_vms(resource_group=rg, include_stopped=False)
    except VMManagerError as e:
        click.echo(f"Error listing VMs: {e}", err=True)
        sys.exit(1)

    if not vms:
        click.echo("No running VMs found in resource group.")
        response = click.prompt(
            "\nWould you like to create a new VM?",
            type=click.Choice(["y", "n"], case_sensitive=False),
            default="y",
        )
        if response.lower() == "y":
            from click import Context

            ctx = Context(new)
            ctx.invoke(
                new,
                resource_group=rg,
                config=config,
                no_tmux=no_tmux,
                tmux_session=tmux_session,
            )
        click.echo("Cancelled.")
        sys.exit(0)

    click.echo("\nAvailable VMs:")
    click.echo("─" * 60)
    for i, vm_info in enumerate(vms, 1):
        status_emoji = "🟢" if vm_info.is_running() else "🔴"
        click.echo(
            f"{i:2}. {status_emoji} {vm_info.name:<30} {vm_info.location:<15} {vm_info.vm_size or 'unknown'}"
        )
    click.echo("─" * 60)
    click.echo(" 0. Create new VM")
    click.echo()

    while True:
        try:
            selection = click.prompt(
                "Select a VM to connect to (0 to create new)",
                type=int,
                default=1 if vms else 0,
            )

            if selection == 0:
                from click import Context

                ctx = Context(new)
                ctx.invoke(
                    new,
                    resource_group=rg,
                    config=config,
                    no_tmux=no_tmux,
                    tmux_session=tmux_session,
                )
                sys.exit(0)
            if 1 <= selection <= len(vms):
                selected_vm = vms[selection - 1]  # type: ignore[misc]
                return str(selected_vm.name)  # type: ignore[union-attr]
            click.echo(f"Invalid selection. Please choose 0-{len(vms)}", err=True)
        except (ValueError, click.Abort):
            click.echo("\nCancelled.")
            sys.exit(0)


def _is_valid_vm_name(vm_name: str, config: str | None) -> bool:
    """Check if a string is a valid VM name (exists in the configured resource group).

    Args:
        vm_name: Potential VM name to check
        config: Config file path (optional)

    Returns:
        True if a VM with this name exists, False otherwise
    """
    try:
        rg = ConfigManager.get_resource_group(None, config)
        if not rg:
            return False
        vm_info = VMManager.get_vm(vm_name, rg)
        return vm_info is not None
    except Exception:
        return False


def _resolve_vm_identifier(vm_identifier: str, config: str | None) -> tuple[str, str]:
    """Resolve session name to VM name and return both.

    Only resolves session names to VM names if the identifier is NOT already
    a valid VM name. This prevents accidental redirection when a VM name
    happens to match a session name configured for a different VM.

    Resolution is SKIPPED when:
    - The identifier is a valid IP address
    - The identifier is already a valid VM name
    - The identifier equals the resolved VM name (self-referential)

    Returns:
        Tuple of (resolved_identifier, original_identifier)
    """
    original_identifier = vm_identifier
    if not VMConnector.is_valid_ip(vm_identifier):
        # First check if this is already a valid VM name - if so, don't resolve
        # This prevents: User types "amplifier" (a VM) but session "amplifier"
        # exists on VM "atg-dev" -> should connect to VM "amplifier", not "atg-dev"
        if _is_valid_vm_name(vm_identifier, config):
            logger.debug(f"'{vm_identifier}' is a valid VM name, skipping session resolution")
            return vm_identifier, original_identifier

        # Not a VM name, try to resolve as session name
        resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_identifier, config)
        if resolved_vm_name and resolved_vm_name != vm_identifier:
            click.echo(f"Resolved session '{vm_identifier}' to VM '{resolved_vm_name}'")
            vm_identifier = resolved_vm_name
    return vm_identifier, original_identifier


def _verify_vm_exists(vm_identifier: str, original_identifier: str, rg: str) -> None:
    """Verify VM exists and clean up stale session mappings."""
    if original_identifier != vm_identifier:
        try:
            vm_info = VMManager.get_vm(vm_identifier, rg)
            if vm_info is None:
                click.echo(
                    f"Error: Session '{original_identifier}' points to VM '{vm_identifier}' "
                    f"which no longer exists.",
                    err=True,
                )
                ConfigManager.delete_session_name(vm_identifier)
                click.echo(f"Removed stale session mapping for '{vm_identifier}'")
                sys.exit(1)
        except VMManagerError as e:
            click.echo(f"Error: Failed to verify VM exists: {e}", err=True)
            sys.exit(1)


def _resolve_tmux_session(
    identifier: str, tmux_session: str | None, no_tmux: bool, config: str | None
) -> str | None:
    """Resolve tmux session name from provided value.

    Returns the explicit --tmux-session value if provided.
    Otherwise defaults to 'azlin' to provide consistent tmux session naming.

    Note: Session name (from config) is used to identify the VM, NOT as the tmux session name.
    """
    if no_tmux:
        return None
    return tmux_session if tmux_session else "azlin"


def _try_fetch_key_from_vault(vm_name: str, key_path: Path, config: str | None) -> bool:
    """Try to fetch SSH key from Azure Key Vault if local key is missing.

    Args:
        vm_name: VM name (used to lookup secret)
        key_path: Target path for private key
        config: Config file path

    Returns:
        True if key was fetched successfully, False otherwise
    """
    try:
        # Load context to get key_vault_name
        context_config = ContextManager.load(config)
        current_context = context_config.get_current_context()

        if not current_context or not current_context.key_vault_name:
            logger.debug("No Key Vault configured, skipping auto-fetch")
            return False

        console = Console()
        console.print("[yellow]SSH key not found locally, checking Key Vault...[/yellow]")

        # Build auth config from context
        # Note: Currently only supports Azure CLI authentication
        # Service Principal support would require storing credentials in context
        auth_config = AuthConfig(method=AuthMethod.AZURE_CLI)

        # Create Key Vault manager
        manager = create_key_vault_manager(
            vault_name=current_context.key_vault_name,
            subscription_id=current_context.subscription_id,
            tenant_id=current_context.tenant_id,
            auth_config=auth_config,
        )

        # Check if key exists in vault
        if not manager.key_exists(vm_name):
            logger.debug(f"SSH key not found in Key Vault for VM: {vm_name}")
            return False

        # Retrieve key
        manager.retrieve_key(vm_name, key_path)
        console.print(
            f"[green]SSH key retrieved from Key Vault: {current_context.key_vault_name}[/green]"
        )
        return True

    except KeyVaultError as e:
        logger.warning(f"Failed to fetch SSH key from Key Vault: {e}")
        return False
    except Exception as e:
        logger.warning(f"Unexpected error fetching SSH key: {e}")
        return False


def _cleanup_key_from_vault(vm_name: str, config: str | None) -> None:
    """Delete SSH key from Azure Key Vault when VM is destroyed.

    Args:
        vm_name: VM name (used to lookup secret)
        config: Config file path

    Note:
        This function logs warnings but does not raise exceptions to avoid
        blocking VM deletion if Key Vault cleanup fails.
    """
    try:
        # Load context to get key_vault_name
        context_config = ContextManager.load(config)
        current_context = context_config.get_current_context()

        if not current_context or not current_context.key_vault_name:
            logger.debug("No Key Vault configured, skipping cleanup")
            return

        logger.info(f"Cleaning up SSH key from Key Vault for VM: {vm_name}")

        # Build auth config from context
        # Note: Currently only supports Azure CLI authentication
        # Service Principal support would require storing credentials in context
        auth_config = AuthConfig(method=AuthMethod.AZURE_CLI)

        # Create Key Vault manager
        manager = create_key_vault_manager(
            vault_name=current_context.key_vault_name,
            subscription_id=current_context.subscription_id,
            tenant_id=current_context.tenant_id,
            auth_config=auth_config,
        )

        # Delete key
        deleted = manager.delete_key(vm_name)
        if deleted:
            click.echo(f"SSH key deleted from Key Vault: {current_context.key_vault_name}")
        else:
            logger.debug(f"SSH key not found in Key Vault for VM: {vm_name}")

    except KeyVaultError as e:
        logger.warning(f"Failed to delete SSH key from Key Vault: {e}")
        # Don't block VM deletion if Key Vault cleanup fails
    except Exception as e:
        logger.warning(f"Unexpected error during Key Vault cleanup: {e}")


# connect command - Moved to azlin.commands.connectivity (Issue #423 refactor)
# code_command command - Moved to azlin.commands.connectivity (Issue #423 refactor)


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
def _get_sync_vm_by_name(vm_name: str, rg: str):
    """Get and validate a specific VM for syncing."""
    vm = VMManager.get_vm(vm_name, rg)
    if not vm:
        click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'.", err=True)
        sys.exit(1)

    if not vm.is_running():
        click.echo(f"Error: VM '{vm_name}' is not running.", err=True)
        sys.exit(1)

    # Check that VM has at least one IP (public or private)
    if not vm.public_ip and not vm.private_ip:
        click.echo(
            f"Error: VM '{vm_name}' has no IP address (neither public nor private).", err=True
        )
        sys.exit(1)

    return vm


def _select_sync_vm_interactive(rg: str):
    """Interactively select a VM for syncing."""
    vms = VMManager.list_vms(rg, include_stopped=False)
    vms = VMManager.filter_by_prefix(vms, "azlin")
    # Include all running VMs (both public IP and Bastion-only)
    vms = [vm for vm in vms if vm.is_running()]

    if not vms:
        click.echo("No running VMs found.")
        sys.exit(1)

    if len(vms) == 1:
        selected_vm = vms[0]
        click.echo(f"Auto-selecting VM: {selected_vm.name}")
        return selected_vm

    # Show menu
    click.echo("\nSelect VM to sync to:")
    for idx, vm_info in enumerate(vms, 1):
        # Display public IP if available, otherwise show "(Bastion)"
        ip_display = vm_info.public_ip if vm_info.public_ip else f"{vm_info.private_ip} (Bastion)"
        click.echo(f"  {idx}. {vm_info.name} - {ip_display}")

    choice = input("\nSelect VM (number): ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(vms):
            return vms[idx]
        click.echo("Invalid selection", err=True)
        sys.exit(1)
    except ValueError:
        click.echo("Invalid input", err=True)
        sys.exit(1)


def _perform_sync(ssh_config, dry_run: bool) -> None:
    """Perform the actual sync operation.

    Args:
        ssh_config: SSH configuration for connection
        dry_run: Whether to perform dry run

    Raises:
        SystemExit: On sync errors
    """

    def progress_callback(msg: str):
        click.echo(f"  {msg}")

    result = HomeSyncManager.sync_to_vm(
        ssh_config, dry_run=dry_run, progress_callback=progress_callback
    )

    if result.success:
        click.echo(
            f"\nSuccess! Synced {result.files_synced} files "
            f"({result.bytes_transferred / 1024:.1f} KB) "
            f"in {result.duration_seconds:.1f}s"
        )
    else:
        click.echo("\nSync completed with errors:", err=True)
        for error in result.errors:
            click.echo(f"  - {error}", err=True)
        sys.exit(1)


def _execute_sync(selected_vm: VMInfo, ssh_key_pair: SSHKeyPair, dry_run: bool) -> None:
    """Execute the sync operation to the selected VM.

    Supports both direct connection (public IP) and Bastion routing (private IP only).
    """
    # Check if VM has public IP for direct connection
    if selected_vm.public_ip:
        # Direct connection path (existing behavior)
        click.echo(f"\nSyncing to {selected_vm.name} ({selected_vm.public_ip})...")

        ssh_config = SSHConfig(
            host=selected_vm.public_ip, user="azureuser", key_path=ssh_key_pair.private_path
        )

        _perform_sync(ssh_config, dry_run)
        return

    # VM has no public IP - try Bastion routing
    if not selected_vm.private_ip:
        click.echo("Error: VM has no IP address (neither public nor private)", err=True)
        sys.exit(1)

    # Detect Bastion
    bastion_info = BastionDetector.detect_bastion_for_vm(
        vm_name=selected_vm.name,
        resource_group=selected_vm.resource_group,
        vm_location=selected_vm.location,
    )
    if not bastion_info:
        click.echo(
            f"Error: VM '{selected_vm.name}' has no public IP and no Bastion host was detected.\n"
            f"Please provision a Bastion host or assign a public IP to the VM.",
            err=True,
        )
        sys.exit(1)

    # Use Bastion tunnel
    click.echo(
        f"\nSyncing to {selected_vm.name} (private IP: {selected_vm.private_ip}) via Bastion..."
    )

    try:
        with BastionManager() as bastion_mgr:
            # Get VM resource ID
            vm_resource_id = VMManager.get_vm_resource_id(
                selected_vm.name, selected_vm.resource_group
            )
            if not vm_resource_id:
                raise BastionManagerError("Failed to get VM resource ID")

            # Find available port
            local_port = bastion_mgr.get_available_port()

            # Create tunnel
            click.echo(f"Creating Bastion tunnel through {bastion_info['name']}...")
            _tunnel = bastion_mgr.create_tunnel(
                bastion_name=bastion_info["name"],
                resource_group=bastion_info["resource_group"],
                target_vm_id=vm_resource_id,
                local_port=local_port,
                remote_port=22,
                wait_for_ready=True,
            )

            # Create SSH config using tunnel
            ssh_config = SSHConfig(
                host="127.0.0.1",
                port=local_port,
                user="azureuser",
                key_path=ssh_key_pair.private_path,
            )

            # Perform sync through tunnel
            _perform_sync(ssh_config, dry_run)

    except BastionManagerError as e:
        click.echo(f"\nBastion tunnel error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"\nSync failed: {e}", err=True)
        sys.exit(1)


# sync command - Moved to azlin.commands.connectivity (Issue #423 refactor)
# sync_keys command - Moved to azlin.commands.connectivity (Issue #423 refactor)
# cp command - Moved to azlin.commands.connectivity (Issue #423 refactor)


def _validate_and_resolve_source_vm(source_vm: str, rg: str, config: str | None) -> VMInfo:
    """Validate and resolve source VM, showing error if not found."""
    click.echo(f"Resolving source VM: {source_vm}")
    source_vm_info = _resolve_source_vm(source_vm, rg, config)

    if not source_vm_info:
        click.echo(f"Error: Source VM '{source_vm}' not found", err=True)
        # Show available VMs
        vms = VMManager.list_vms(rg)
        if vms:
            click.echo("\nAvailable VMs:", err=True)
            for vm_item in vms:
                display_name = vm_item.session_name or vm_item.name
                click.echo(f"  - {display_name} ({vm_item.name})", err=True)
        sys.exit(1)

    return source_vm_info

    click.echo(f"Source VM: {source_vm_info.name} ({source_vm_info.public_ip})")
    click.echo(f"VM size: {source_vm_info.vm_size}")
    click.echo(f"Region: {source_vm_info.location}")
    return source_vm_info


def _ensure_source_vm_running(source_vm_info: VMInfo, rg: str) -> VMInfo:
    """Ensure source VM is running, start if needed."""
    if not source_vm_info.is_running():
        click.echo(f"Warning: Source VM is not running (state: {source_vm_info.power_state})")
        click.echo("Starting source VM...")
        controller = VMLifecycleController()
        controller.start_vm(source_vm_info.name, rg)
        click.echo("Source VM started successfully")
        # Refresh VM info
        refreshed_vm = VMManager.get_vm(source_vm_info.name, rg)
        if refreshed_vm is None:
            click.echo("Error: Failed to refresh VM info after starting", err=True)
            sys.exit(1)
        return refreshed_vm
    return source_vm_info


def _provision_clone_vms(
    clone_configs: list[VMConfig], num_replicas: int
) -> PoolProvisioningResult:
    """Provision clone VMs in parallel."""
    click.echo(f"\nProvisioning {num_replicas} VM(s)...")
    provisioner = VMProvisioner()

    def progress_callback(msg: str):
        click.echo(f"  {msg}")

    result = provisioner.provision_vm_pool(
        configs=clone_configs,
        progress_callback=progress_callback,
        max_workers=min(10, num_replicas),
    )

    # Check provisioning results
    if not result.any_succeeded:
        click.echo("\nError: All VM provisioning failed", err=True)
        for failure in result.failed[:3]:  # Show first 3 failures
            click.echo(f"  {failure.config.name}: {failure.error}", err=True)
        sys.exit(1)

    if result.partial_success:
        click.echo(
            f"\nWarning: Partial success - {result.success_count}/{result.total_requested} VMs provisioned"
        )

    click.echo(f"\nSuccessfully provisioned {result.success_count} VM(s)")
    return result


def _display_clone_results(
    result: PoolProvisioningResult,
    copy_results: dict[str, bool],
    session_prefix: str | None,
    config: str | None,
) -> None:
    """Display final clone operation results."""
    successful_copies = sum(1 for success in copy_results.values() if success)

    click.echo("\n" + "=" * 70)
    click.echo(f"Clone operation complete: {successful_copies}/{len(result.successful)} successful")
    click.echo("=" * 70)
    click.echo("\nCloned VMs:")
    for vm_item in result.successful:
        session_name = (
            ConfigManager.get_session_name(vm_item.name, config) if session_prefix else None
        )
        copy_status = "✓" if copy_results.get(vm_item.name, False) else "✗"
        display_name = f"{session_name} ({vm_item.name})" if session_name else vm_item.name
        click.echo(f"  {copy_status} {display_name}")
        click.echo(f"     IP: {vm_item.public_ip}")
        click.echo(f"     Size: {vm_item.size}, Region: {vm_item.location}")

    if result.failed:
        click.echo("\nFailed provisioning:")
        for failure in result.failed:
            click.echo(f"  ✗ {failure.config.name}: {failure.error}")

    # Show connection instructions
    if result.successful:
        first_clone = result.successful[0]
        first_session = (
            ConfigManager.get_session_name(first_clone.name, config) if session_prefix else None
        )
        connect_target = first_session or first_clone.name
        click.echo("\nTo connect to first clone:")
        click.echo(f"  azlin connect {connect_target}")


# clone command - Moved to azlin.commands.provisioning (Issue #423 refactor)


def _resolve_source_vm(
    source_vm: str, resource_group: str, config_path: str | None = None
) -> VMInfo | None:
    """Resolve source VM by session name or VM name.

    Args:
        source_vm: Source VM identifier (session name or VM name)
        resource_group: Resource group name
        config_path: Optional config file path

    Returns:
        VMInfo object or None if not found
    """
    # Try as VM name first
    vm_info = VMManager.get_vm(source_vm, resource_group)
    if vm_info:
        return vm_info

    # Try as session name
    vm_name = ConfigManager.get_vm_name_by_session(source_vm, config_path)
    if vm_name:
        vm_info = VMManager.get_vm(vm_name, resource_group)
        if vm_info:
            return vm_info

    # Try finding in list (case-insensitive match)
    all_vms = VMManager.list_vms(resource_group)
    for vm_item in all_vms:
        if vm_item.name.lower() == source_vm.lower():
            return vm_item
        if vm_item.session_name and vm_item.session_name.lower() == source_vm.lower():
            return vm_item

    return None


def _generate_clone_configs(
    source_vm: VMInfo,
    num_replicas: int,
    vm_size: str | None,
    region: str | None,
) -> list[VMConfig]:
    """Generate VMConfig objects for clones.

    Args:
        source_vm: Source VM information
        num_replicas: Number of clones to create
        vm_size: Custom VM size (None = use source size)
        region: Custom region (None = use source region)

    Returns:
        List of VMConfig objects
    """
    from azlin.vm_provisioning import VMConfig

    # Use custom or source attributes
    clone_size = vm_size or source_vm.vm_size or "Standard_B2s"  # Default if both are None
    clone_region = region or source_vm.location

    # Generate unique VM names with timestamp
    timestamp = int(time.time())
    configs: list[Any] = []

    for i in range(1, num_replicas + 1):
        vm_name = f"azlin-vm-{timestamp}-{i}"
        config = VMConfig(
            name=vm_name,
            resource_group=source_vm.resource_group,
            location=clone_region,
            size=clone_size,
            image="Ubuntu2204",
            ssh_public_key=None,  # Will use default SSH keys
            admin_username="azureuser",
            disable_password_auth=True,
        )
        configs.append(config)

    return configs


def _copy_home_directories(
    source_vm: VMInfo,
    clone_vms: list[VMDetails],
    ssh_key_path: str,
    max_workers: int = 5,
) -> dict[str, bool]:
    """Copy home directories from source to clones in parallel.

    Args:
        source_vm: Source VM information
        clone_vms: List of cloned VM details
        ssh_key_path: Path to SSH private key
        max_workers: Maximum parallel workers

    Returns:
        Dictionary mapping VM name to success status
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def copy_to_vm(clone_vm: VMDetails) -> tuple[str, bool]:
        """Copy home directory to a single clone.

        Uses localhost as staging area to avoid rsync remote-to-remote limitation.
        Two-stage copy: source -> localhost -> destination.
        """
        import shutil
        import tempfile

        temp_dir = None
        try:
            # Create temporary directory for staging
            temp_dir = Path(tempfile.mkdtemp(prefix="azlin_clone_"))

            click.echo(f"  Copying to {clone_vm.name}...")

            # Stage 1: Copy from source VM to localhost
            source_path = f"azureuser@{source_vm.public_ip}:/home/azureuser/"
            rsync_from_source = [
                "rsync",
                "-az",  # Archive mode, compress
                "-e",
                f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10",
                source_path,
                str(temp_dir) + "/",
            ]

            result1 = subprocess.run(
                rsync_from_source,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for download
            )

            if result1.returncode != 0:
                click.echo(f"  ✗ {clone_vm.name} download failed: {result1.stderr[:100]}", err=True)
                return (clone_vm.name, False)

            # Stage 2: Copy from localhost to destination VM
            dest_path = f"azureuser@{clone_vm.public_ip}:/home/azureuser/"
            rsync_to_dest = [
                "rsync",
                "-az",  # Archive mode, compress
                "-e",
                f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10",
                str(temp_dir) + "/",
                dest_path,
            ]

            result2 = subprocess.run(
                rsync_to_dest,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for upload
            )

            if result2.returncode == 0:
                click.echo(f"  ✓ {clone_vm.name} copy complete")
                return (clone_vm.name, True)
            click.echo(f"  ✗ {clone_vm.name} upload failed: {result2.stderr[:100]}", err=True)
            return (clone_vm.name, False)

        except subprocess.TimeoutExpired:
            click.echo(f"  ✗ {clone_vm.name} copy timeout", err=True)
            return (clone_vm.name, False)
        except Exception as e:
            click.echo(f"  ✗ {clone_vm.name} copy error: {e}", err=True)
            return (clone_vm.name, False)
        finally:
            # Clean up temporary directory
            if temp_dir and temp_dir.exists():
                with contextlib.suppress(Exception):
                    shutil.rmtree(temp_dir)

    # Execute copies in parallel
    results: dict[str, bool] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(copy_to_vm, clone): clone for clone in clone_vms}

        for future in as_completed(futures):
            vm_name, success = future.result()
            results[vm_name] = success

    return results


def _set_clone_session_names(
    clone_vms: list[VMDetails],
    session_prefix: str,
    config_path: str | None = None,
) -> None:
    """Set session names for cloned VMs.

    Args:
        clone_vms: List of cloned VM details
        session_prefix: Session name prefix
        config_path: Optional config file path
    """
    if len(clone_vms) == 1:
        # Single clone: use prefix without number
        ConfigManager.set_session_name(clone_vms[0].name, session_prefix, config_path)
        click.echo(f"  Set session name: {session_prefix} -> {clone_vms[0].name}")
    else:
        # Multiple clones: use numbered suffixes
        for i, clone_vm in enumerate(clone_vms, 1):
            session_name = f"{session_prefix}-{i}"
            ConfigManager.set_session_name(clone_vm.name, session_name, config_path)
            click.echo(f"  Set session name: {session_name} -> {clone_vm.name}")


# Status command moved to azlin.commands.monitoring (Issue #423 - cli.py decomposition POC)


# ip command - Moved to azlin.commands.ip_commands (Issue #423 refactor)
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
    logger = logging.getLogger(__name__)

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
                click.echo("  ✓ Success")
                if verbose and result["stdout"]:
                    click.echo(f"  Output: {result['stdout'][:200]}")
            else:
                click.echo(f"  ✗ Failed: {result['stderr']}")
                break  # Stop on first failure

        # Validate results
        validator = ResultValidator()
        validation = validator.validate(intent, results)

        click.echo("\n" + "=" * 80)
        if validation["success"]:
            click.echo("✓ " + validation["message"])
        else:
            click.echo("✗ " + validation["message"], err=True)
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


# do command - Moved to azlin.commands.nlp (Issue #423 refactor)
# NOTE: Old doit command commented out in favor of new doit_group with subcommands
# @main.command(name="doit-old")
# @click.argument("objective", type=str)
# @click.option("--dry-run", is_flag=True, help="Show execution plan without running")
# @click.option("--resource-group", "--rg", help="Resource group", type=str)
# @click.option("--config", help="Config file path", type=click.Path())
# @click.option("--verbose", "-v", is_flag=True, help="Show detailed execution information")
def _doit_old_impl(
    objective: str,
    dry_run: bool,
    resource_group: str | None,
    config: str | None,
    verbose: bool,
):
    """[DEPRECATED] Enhanced agentic Azure infrastructure management (old version).

    This command provides multi-strategy execution with state persistence
    and intelligent fallback handling. It enhances the basic 'do' command
    with objective tracking, cost estimation, and failure recovery.

    \b
    Examples:
        azlin doit "provision an AKS cluster with 3 nodes"
        azlin doit "create a VM optimized for ML workloads" --dry-run
        azlin doit "set up a complete dev environment" --verbose

    \b
    Phase 1 Features (Current):
        - Objective state persistence at ~/.azlin/objectives/<uuid>.json
        - Audit logging to ~/.azlin/audit.log
        - Secure file permissions (0600)

    \b
    Future Phases (Not Yet Implemented):
        - Multi-strategy execution (CLI, Terraform, MCP, Custom)
        - Automatic fallback on failures
        - Cost estimation and optimization
        - MS Learn documentation research
        - Intelligent failure recovery

    \b
    Requirements:
        - ANTHROPIC_API_KEY environment variable must be set
        - Active Azure authentication
    """
    try:
        # Check for API key
        import os

        if not os.getenv("ANTHROPIC_API_KEY"):
            click.echo("Error: ANTHROPIC_API_KEY environment variable is required", err=True)
            click.echo("\nSet your API key with:", err=True)
            click.echo("  export ANTHROPIC_API_KEY=your-key-here", err=True)
            sys.exit(1)

        # Import azdoit components
        from azlin.agentic.audit_logger import AuditLogger
        from azlin.agentic.objective_manager import ObjectiveManager
        from azlin.agentic.types import Intent

        # Parse natural language intent (using existing parser)
        if verbose:
            click.echo(f"Parsing objective: {objective}")

        # Get resource group for context
        rg = ConfigManager.get_resource_group(resource_group, config)
        context = {}
        if rg:
            context["resource_group"] = rg

        # Parse intent
        parser = IntentParser()
        intent_dict = parser.parse(objective, context=context if context else None)

        # Convert to Intent dataclass
        intent = Intent(
            intent=intent_dict["intent"],
            parameters=intent_dict["parameters"],
            confidence=intent_dict["confidence"],
            azlin_commands=intent_dict["azlin_commands"],
            explanation=intent_dict.get("explanation"),
        )

        if verbose:
            click.echo("\nParsed Intent:")
            click.echo(f"  Type: {intent.intent}")
            click.echo(f"  Confidence: {intent.confidence:.1%}")
            if intent.explanation:
                click.echo(f"  Plan: {intent.explanation}")

        # Create objective state
        manager = ObjectiveManager()
        state = manager.create(
            natural_language=objective,
            intent=intent,
        )

        # Log creation
        logger_inst = AuditLogger()
        logger_inst.log(
            "OBJECTIVE_CREATED",
            objective_id=state.id,
            details={"objective": objective[:100], "confidence": f"{intent.confidence:.2f}"},
        )

        # Display objective info
        click.echo("\n" + "=" * 80)
        click.echo(f"Objective Created: {state.id}")
        click.echo("=" * 80)
        click.echo(f"\nObjective: {objective}")
        click.echo(f"Status: {state.status.value}")
        click.echo(f"State file: ~/.azlin/objectives/{state.id}.json")
        click.echo(f"Created at: {state.created_at.strftime('%Y-%m-%d %H:%M:%S')}")

        if verbose:
            click.echo("\nIntent details:")
            click.echo(f"  Type: {intent.intent}")
            click.echo(f"  Parameters: {intent.parameters}")

        # Phase 2: Strategy Selection and Execution
        from azlin.agentic.strategies import (
            AzureCLIStrategy,
            TerraformStrategy,
        )
        from azlin.agentic.strategy_selector import StrategySelector
        from azlin.agentic.types import ExecutionContext, ObjectiveStatus, Strategy

        # Select execution strategy
        click.echo("\n" + "=" * 80)
        click.echo("Phase 2: Strategy Selection")
        click.echo("=" * 80)

        selector = StrategySelector()
        strategy_plan = selector.select_strategy(intent, resource_group=rg)

        # Update objective with strategy plan
        manager.update(
            state.id,
            strategy_plan=strategy_plan,
            selected_strategy=strategy_plan.primary_strategy,
        )

        click.echo(f"\nSelected Strategy: {strategy_plan.primary_strategy.value}")
        click.echo(f"Reasoning: {strategy_plan.reasoning}")
        if strategy_plan.fallback_strategies:
            click.echo(f"Fallback: {', '.join(s.value for s in strategy_plan.fallback_strategies)}")
        if strategy_plan.estimated_duration_seconds:
            mins = strategy_plan.estimated_duration_seconds // 60
            click.echo(f"Estimated Duration: ~{mins} minutes")

        # Check prerequisites
        if not strategy_plan.prerequisites_met:
            click.echo("\n⚠️  Prerequisites not met!", err=True)
            click.echo(f"Unable to execute: {strategy_plan.reasoning}")

            # Log prerequisite failure
            logger_inst.log(
                "PREREQUISITES_FAILED",
                objective_id=state.id,
                details={"strategy": strategy_plan.primary_strategy.value},
            )

            # Update objective as failed
            manager.update(
                state.id, status=ObjectiveStatus.FAILED, error_message=strategy_plan.reasoning
            )
            sys.exit(1)

        # Log strategy selection
        logger_inst.log(
            "STRATEGY_SELECTED",
            objective_id=state.id,
            details={
                "strategy": strategy_plan.primary_strategy.value,
                "fallbacks": [s.value for s in strategy_plan.fallback_strategies],
            },
        )

        # Phase 3: Cost Estimation
        click.echo("\n" + "=" * 80)
        click.echo("Phase 3: Cost Estimation")
        click.echo("=" * 80)

        from azlin.agentic.budget_monitor import BudgetMonitor, BudgetPeriod
        from azlin.agentic.cost_estimator import CostEstimator, PricingRegion

        # Get strategy instance to extract cost factors
        strategy_map = {
            Strategy.AZURE_CLI: AzureCLIStrategy(),
            Strategy.TERRAFORM: TerraformStrategy(),
        }
        strategy = strategy_map.get(strategy_plan.primary_strategy)

        if strategy:
            # Get cost factors from strategy
            execution_context_temp = ExecutionContext(
                objective_id=state.id,
                intent=intent,
                strategy=strategy_plan.primary_strategy,
                dry_run=True,  # Dry run for cost estimation
                resource_group=rg,
            )
            cost_factors = strategy.get_cost_factors(execution_context_temp)

            if cost_factors:
                # Estimate costs using US_EAST pricing (most common region)
                estimator = CostEstimator(region=PricingRegion.US_EAST)
                cost_estimate = estimator.estimate(cost_factors)

                # Display estimate
                if verbose:
                    click.echo("\n" + estimator.format_estimate(cost_estimate, show_breakdown=True))
                else:
                    click.echo(f"\nEstimated Cost: ${float(cost_estimate.total_monthly):.2f}/month")
                    confidence_pct = {"high": "High", "medium": "Medium", "low": "Low"}
                    click.echo(
                        f"Confidence: {confidence_pct.get(cost_estimate.confidence, cost_estimate.confidence)}"
                    )

                # Check budget
                budget_monitor = BudgetMonitor()
                budget_alert = budget_monitor.check_budget(
                    cost_estimate,
                    period=BudgetPeriod.MONTHLY,
                    resource_group=rg,
                )

                if budget_alert:
                    # Show alert
                    if budget_alert.level.value == "exceeded":
                        click.echo(f"\n🛑 {budget_alert.message}", err=True)
                        click.echo(f"   {budget_alert.recommended_action}", err=True)
                        # Block execution if budget would be exceeded
                        if not dry_run:
                            click.echo("\nExecution blocked to prevent budget overrun.", err=True)
                            click.echo("Options:", err=True)
                            click.echo("  1. Use --dry-run to preview without executing", err=True)
                            click.echo("  2. Reduce resource requirements", err=True)
                            click.echo(
                                "  3. Increase budget limit in ~/.azlin/budget.json", err=True
                            )
                            manager.update(
                                state.id,
                                status=ObjectiveStatus.FAILED,
                                error_message="Budget limit would be exceeded",
                            )
                            sys.exit(1)
                    elif budget_alert.level.value == "critical":
                        click.echo(f"\n⚠️  {budget_alert.message}", err=True)
                        click.echo(f"   {budget_alert.recommended_action}", err=True)
                    else:
                        click.echo(f"\nINFO: {budget_alert.message}")

                # Store cost estimate in objective state
                # cost_estimate is already in the correct types.CostEstimate format
                # Update the objective state with it
                manager.update(state.id, cost_estimate=cost_estimate)

                # Log cost estimation
                logger_inst.log(
                    "COST_ESTIMATED",
                    objective_id=state.id,
                    details={
                        "monthly_cost": f"${float(cost_estimate.total_monthly):.2f}",
                        "confidence": cost_estimate.confidence,
                    },
                )
            else:
                click.echo("\nNo cost factors available for estimation")
        else:
            click.echo("\nCost estimation not available for this strategy")

        # Execute strategy
        click.echo("\n" + "=" * 80)
        click.echo("Phase 3: Execution")
        click.echo("=" * 80)

        # Create execution context
        execution_context = ExecutionContext(
            objective_id=state.id,
            intent=intent,
            strategy=strategy_plan.primary_strategy,
            dry_run=dry_run,
            resource_group=rg,
        )

        # Strategy was already obtained in Phase 3
        if not strategy:
            click.echo(
                f"\n⚠️  Strategy {strategy_plan.primary_strategy.value} not yet implemented",
                err=True,
            )
            manager.update(
                state.id,
                status=ObjectiveStatus.FAILED,
                error_message=f"Strategy {strategy_plan.primary_strategy.value} not implemented",
            )
            sys.exit(1)

        # Update status to IN_PROGRESS
        manager.update(state.id, status=ObjectiveStatus.IN_PROGRESS)

        # Log execution start
        logger_inst.log(
            "EXECUTION_STARTED",
            objective_id=state.id,
            details={"strategy": strategy_plan.primary_strategy.value},
        )

        # Phase 4: Execution Orchestrator (with fallback and retry)
        from azlin.agentic.execution_orchestrator import ExecutionOrchestrator

        orchestrator = ExecutionOrchestrator(
            max_retries=3,
            retry_delay_base=2.0,
            enable_rollback=True,
        )

        if verbose:
            click.echo("\nExecuting with orchestrated fallback chain:")
            click.echo(f"  Primary: {strategy_plan.primary_strategy.value}")
            if strategy_plan.fallback_strategies:
                click.echo(
                    f"  Fallbacks: {', '.join(s.value for s in strategy_plan.fallback_strategies)}"
                )

        # Execute with orchestrator (handles retries and fallback automatically)
        result = orchestrator.execute(execution_context, strategy_plan)

        # Show execution summary in verbose mode
        if verbose:
            summary = orchestrator.get_execution_summary()
            click.echo("\nExecution Summary:")
            click.echo(f"  Total Attempts: {summary['total_attempts']}")
            click.echo(f"  Strategies Tried: {', '.join(summary['strategies_tried'])}")
            click.echo(f"  Total Duration: {summary['total_duration']:.1f}s")

        # Update objective with execution result
        manager.update(
            state.id,
            execution_results=[result],
            resources_created=result.resources_created,
        )

        # Display result
        if result.success:
            click.echo("\n✅ Execution successful!")

            # Update objective status
            manager.update(state.id, status=ObjectiveStatus.COMPLETED)

            # Log success
            logger_inst.log(
                "EXECUTION_COMPLETED",
                objective_id=state.id,
                details={
                    "strategy": result.strategy.value,
                    "duration": f"{result.duration_seconds:.1f}s"
                    if result.duration_seconds
                    else None,
                    "resources": len(result.resources_created),
                },
            )

            if result.output and verbose:
                click.echo("\nOutput:")
                click.echo(result.output)

            if result.resources_created:
                click.echo(f"\nResources Created ({len(result.resources_created)}):")
                for resource_id in result.resources_created[:10]:  # Show first 10
                    click.echo(f"  - {resource_id}")
                if len(result.resources_created) > 10:
                    click.echo(f"  ... and {len(result.resources_created) - 10} more")

            if result.duration_seconds:
                click.echo(f"\nDuration: {result.duration_seconds:.1f} seconds")

        else:
            click.echo(f"\n❌ Execution failed: {result.error}", err=True)

            # Phase 5: Failure Analysis & MS Learn Research
            click.echo("\n" + "=" * 80)
            click.echo("Phase 5: Failure Analysis")
            click.echo("=" * 80)

            from azlin.agentic.failure_analyzer import FailureAnalyzer
            from azlin.agentic.ms_learn_client import MSLearnClient

            # Analyze failure
            ms_learn = MSLearnClient()
            analyzer = FailureAnalyzer(ms_learn_client=ms_learn)
            analysis = analyzer.analyze_failure(result)

            # Display analysis
            click.echo(f"\nFailure Type: {analysis.failure_type.value}")
            if analysis.error_signature.error_code:
                click.echo(f"Error Code: {analysis.error_signature.error_code}")
            if analysis.similar_failures > 0:
                click.echo(f"Similar Past Failures: {analysis.similar_failures}")

            # Show suggested fixes
            if analysis.suggested_fixes:
                click.echo("\n📋 Suggested Fixes:")
                for i, fix in enumerate(analysis.suggested_fixes, 1):
                    click.echo(f"  {i}. {fix}")

            # Show runnable commands
            if analysis.runnable_commands:
                click.echo("\n🔧 Diagnostic Commands:")
                for cmd in analysis.runnable_commands:
                    click.echo(f"  $ {cmd}")

            # Show MS Learn documentation
            if analysis.doc_links:
                click.echo("\n📚 MS Learn Documentation:")
                for doc in analysis.doc_links:
                    click.echo(f"  • {doc.title}")
                    click.echo(f"    {doc.url}")
                    if doc.summary and verbose:
                        click.echo(f"    {doc.summary}")

            # Ask user if they want to try suggested commands
            if analysis.runnable_commands and not dry_run:
                click.echo("\n❓ Would you like to run the diagnostic commands? [y/N]: ", nl=False)
                try:
                    if sys.stdin.isatty():
                        response = input().strip().lower()
                        if response == "y":
                            click.echo("\n🔍 Running diagnostic commands...")
                            for cmd in analysis.runnable_commands:
                                click.echo(f"\n$ {cmd}")
                                try:
                                    # Security: Use shlex.split() for safe command parsing
                                    # This protects against command injection
                                    import shlex

                                    # Check if command contains pipes (need special handling)
                                    if "|" in cmd:
                                        # For piped commands, validate they're safe Az CLI commands
                                        if not cmd.strip().startswith(
                                            ("az ", "terraform ", "kubectl ")
                                        ):
                                            click.echo(
                                                "  ⚠️  Skipped: Only az/terraform/kubectl commands allowed for piped execution",
                                                err=True,
                                            )
                                            continue

                                        # Execute pipes securely without shell=True
                                        # Split by pipe and chain processes
                                        pipe_parts = [part.strip() for part in cmd.split("|")]

                                        try:
                                            # Start first process
                                            first_cmd = shlex.split(pipe_parts[0])
                                            current_proc = subprocess.Popen(
                                                first_cmd,
                                                stdout=subprocess.PIPE,
                                                stderr=subprocess.PIPE,
                                                text=True,
                                            )

                                            # Chain remaining processes
                                            for pipe_cmd in pipe_parts[1:]:
                                                cmd_parts = shlex.split(pipe_cmd)
                                                next_proc = subprocess.Popen(
                                                    cmd_parts,
                                                    stdin=current_proc.stdout,
                                                    stdout=subprocess.PIPE,
                                                    stderr=subprocess.PIPE,
                                                    text=True,
                                                )
                                                if current_proc.stdout:
                                                    current_proc.stdout.close()
                                                current_proc = next_proc

                                            # Get final output
                                            stdout, stderr = current_proc.communicate(timeout=30)
                                            proc_result = subprocess.CompletedProcess(
                                                args=cmd,
                                                returncode=current_proc.returncode or 0,
                                                stdout=stdout,
                                                stderr=stderr,
                                            )
                                        except Exception as pipe_error:
                                            click.echo(
                                                f"  ⚠️  Pipe execution failed: {pipe_error}",
                                                err=True,
                                            )
                                            continue

                                    elif any(
                                        char in cmd for char in [">", "<", ";", "&", "`", "$("]
                                    ):
                                        # Redirects, command chains, and substitutions are not supported
                                        click.echo(
                                            "  ⚠️  Skipped: Redirects, command chains, and substitutions not supported",
                                            err=True,
                                        )
                                        continue
                                    else:
                                        # Simple commands: use safe list-based execution
                                        cmd_parts = shlex.split(cmd)
                                        proc_result = subprocess.run(
                                            cmd_parts,
                                            shell=False,
                                            capture_output=True,
                                            text=True,
                                            timeout=30,
                                        )

                                    if proc_result.stdout:
                                        click.echo(proc_result.stdout)
                                    if proc_result.stderr:
                                        click.echo(proc_result.stderr, err=True)
                                except subprocess.TimeoutExpired:
                                    click.echo("  (command timed out)", err=True)
                                except Exception as e:
                                    click.echo(f"  Error: {e}", err=True)
                except (EOFError, KeyboardInterrupt):
                    click.echo("N")

            # Update objective as failed
            manager.update(
                state.id,
                status=ObjectiveStatus.FAILED,
                error_message=result.error,
                failure_type=result.failure_type,
            )

            # Log failure
            logger_inst.log(
                "EXECUTION_FAILED",
                objective_id=state.id,
                details={
                    "strategy": result.strategy.value,
                    "error": result.error,
                    "failure_type": result.failure_type.value if result.failure_type else None,
                },
            )

            if result.output and verbose:
                click.echo("\nOutput:")
                click.echo(result.output)

            sys.exit(1)

        # Show audit trail
        click.echo("\nAudit trail:")
        timeline = logger_inst.get_objective_timeline(state.id)
        for event in timeline:
            click.echo(f"  {event['timestamp']}: {event['event']}")

        click.echo("\nTo view objective state:")
        click.echo(f"  cat ~/.azlin/objectives/{state.id}.json")
        click.echo("\nTo view audit log:")
        click.echo("  tail ~/.azlin/audit.log")

    except IntentParseError as e:
        click.echo(f"\nFailed to parse objective: {e}", err=True)
        click.echo("\nTry rephrasing your objective or use specific azlin commands.", err=True)
        sys.exit(1)

    except Exception as e:
        click.echo(f"\nUnexpected error: {e}", err=True)
        if verbose:
            logger.exception("Unexpected error in doit command")
        sys.exit(1)

    except KeyboardInterrupt:
        click.echo("\n\nCancelled by user.")
        sys.exit(130)


# batch command - Moved to azlin.commands.batch (Issue #423 refactor)
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
def snapshot_enable(
    vm_name: str,
    resource_group: str | None,
    config: str | None,
    interval_hours: int,
    keep_count: int,
):
    """Enable scheduled snapshots for a VM.

    Configures the VM to take snapshots every N hours, keeping only the most recent snapshots.
    Schedule is stored in VM tags and triggered by `azlin snapshot sync`.

    \b
    Examples:
        azlin snapshot enable my-vm --every 24          # Daily, keep 2
        azlin snapshot enable my-vm --every 12 --keep 5 # Every 12h, keep 5
    """
    try:
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        SnapshotManager.enable_snapshots(vm_name, rg, interval_hours, keep_count)

        click.echo(f"✓ Enabled scheduled snapshots for {vm_name}")
        click.echo(f"  Interval: every {interval_hours} hours")
        click.echo(f"  Retention: keep {keep_count} snapshots")
        click.echo("\nRun 'azlin snapshot sync' to trigger snapshot creation.")

    except SnapshotError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


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


def _validate_batch_selection(tag: str | None, vm_pattern: str | None, select_all: bool):
    """Validate that exactly one batch selection option is provided."""
    selection_count = sum([bool(tag), bool(vm_pattern), select_all])
    if selection_count == 0:
        click.echo("Error: Must specify --tag, --vm-pattern, or --all", err=True)
        sys.exit(1)
    if selection_count > 1:
        click.echo("Error: Can only use one of --tag, --vm-pattern, or --all", err=True)
        sys.exit(1)


def _select_vms_by_criteria(
    all_vms: list[VMInfo], tag: str | None, vm_pattern: str | None, select_all: bool
) -> tuple[list[VMInfo], str]:
    """Select VMs based on criteria and return (selected_vms, selection_description)."""
    if tag:
        selected_vms = BatchSelector.select_by_tag(all_vms, tag)
        selection_desc = f"tag '{tag}'"
    elif vm_pattern:
        selected_vms = BatchSelector.select_by_pattern(all_vms, vm_pattern)
        selection_desc = f"pattern '{vm_pattern}'"
    else:  # select_all
        selected_vms = all_vms
        selection_desc = "all VMs"
    return selected_vms, selection_desc


def _confirm_batch_operation(num_vms: int, operation: str, confirm: bool) -> bool:
    """Confirm batch operation with user. Returns True if should proceed."""
    if not confirm:
        click.echo(f"\nThis will {operation} {num_vms} VM(s).")
        confirm_input = input("Continue? [y/N]: ").lower()
        if confirm_input not in ["y", "yes"]:
            click.echo("Cancelled.")
            return False
    return True


def _display_batch_summary(batch_result: BatchResult, operation_name: str) -> None:
    """Display batch operation summary."""
    click.echo("\n" + "=" * 80)
    click.echo(f"Batch {operation_name} Summary")
    click.echo("=" * 80)
    click.echo(batch_result.format_summary())
    click.echo("=" * 80)

    if batch_result.failed > 0:
        click.echo("\nFailed VMs:")
        for failure in batch_result.get_failures():
            click.echo(f"  - {failure.vm_name}: {failure.message}")


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
def keys_backup(destination: str | None):
    """Backup current SSH keys.

    Creates a timestamped backup of current SSH keys.

    \b
    Examples:
        azlin keys backup
        azlin keys backup --destination ~/backups/
    """
    try:
        click.echo("Backing up SSH keys...")

        backup = SSHKeyRotator.backup_keys()

        click.echo("\nSuccess! Keys backed up to:")
        click.echo(f"  Directory: {backup.backup_dir}")
        click.echo(f"  Timestamp: {backup.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        click.echo(f"  Private key: {backup.old_private_key}")
        click.echo(f"  Public key: {backup.old_public_key}")

    except KeyRotationError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in keys backup")

        sys.exit(1)


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


def _get_ssh_config_for_vm(
    vm_identifier: str, resource_group: str | None, config: str | None
) -> SSHConfig:
    """Helper to get SSH config for VM identifier.

    Args:
        vm_identifier: VM name, session name, or IP address
        resource_group: Resource group (required for VM name)
        config: Config file path

    Returns:
        SSHConfig object

    Raises:
        SystemExit on error
    """
    # Get SSH key
    ssh_key_pair = SSHKeyManager.ensure_key_exists()

    # Check if VM identifier is IP address
    if VMConnector.is_valid_ip(vm_identifier):
        # Direct IP connection
        return SSHConfig(host=vm_identifier, user="azureuser", key_path=ssh_key_pair.private_path)

    # Resolve session name to VM name if applicable
    resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_identifier, config)
    if resolved_vm_name:
        vm_identifier = resolved_vm_name

    # VM name - need resource group
    rg = ConfigManager.get_resource_group(resource_group, config)
    if not rg:
        click.echo(
            "Error: Resource group required for VM name.\n"
            "Use --resource-group or set default in ~/.azlin/config.toml",
            err=True,
        )
        sys.exit(1)

    # Get VM
    vm = VMManager.get_vm(vm_identifier, rg)
    if not vm:
        click.echo(f"Error: VM '{vm_identifier}' not found in resource group '{rg}'.", err=True)
        sys.exit(1)

    if not vm.is_running():
        click.echo(f"Error: VM '{vm_identifier}' is not running.", err=True)
        sys.exit(1)

    if not vm.public_ip:
        click.echo(f"Error: VM '{vm_identifier}' has no public IP.", err=True)
        sys.exit(1)

    return SSHConfig(host=vm.public_ip, user="azureuser", key_path=ssh_key_pair.private_path)


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
    import subprocess
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
    import subprocess

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
