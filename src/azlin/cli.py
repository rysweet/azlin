"""CLI entry point for azlin v2.0.

This module provides the enhanced command-line interface with:
- Config storage and resource group management
- VM listing and status
- Interactive session selection
- Parallel VM provisioning (pools)
- Remote command execution
- Enhanced help

Commands:
    azlin                    # Interactive menu or provision new VM
    azlin list               # List VMs in resource group
    azlin w                  # Run 'w' command on all VMs
    azlin -- <command>       # Execute command on VM(s)
"""

import sys
import os
import logging
import time
import click
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from azlin import __version__
from azlin.azure_auth import AzureAuthenticator, AuthenticationError
from azlin.vm_provisioning import VMProvisioner, VMConfig, VMDetails, ProvisioningError
from azlin.modules.prerequisites import PrerequisiteChecker, PrerequisiteError
from azlin.modules.ssh_keys import SSHKeyManager, SSHKeyError
from azlin.modules.ssh_connector import SSHConnector, SSHConfig, SSHConnectionError
from azlin.modules.github_setup import GitHubSetupHandler, GitHubSetupError
from azlin.modules.progress import ProgressDisplay, ProgressStage
from azlin.modules.notifications import NotificationHandler

# New modules for v2.0
from azlin.config_manager import ConfigManager, AzlinConfig, ConfigError
from azlin.vm_manager import VMManager, VMInfo, VMManagerError
from azlin.remote_exec import RemoteExecutor, WCommandExecutor, PSCommandExecutor, RemoteExecError
from azlin.terminal_launcher import TerminalLauncher, TerminalConfig
from azlin.vm_lifecycle import VMLifecycleManager, VMLifecycleError, DeletionSummary
from azlin.vm_connector import VMConnector, VMConnectorError

logger = logging.getLogger(__name__)


class AzlinError(Exception):
    """Base exception for azlin errors."""
    exit_code = 1


class CLIOrchestrator:
    """Orchestrate azlin workflow.

    This class coordinates all modules to execute the complete workflow:
    1. Prerequisites check
    2. Azure authentication
    3. SSH key generation
    4. VM provisioning
    5. Wait for VM ready
    6. SSH connection
    7. GitHub setup (if --repo provided)
    8. tmux session
    9. Notification (optional)
    """

    def __init__(
        self,
        repo: Optional[str] = None,
        vm_size: str = "Standard_D2s_v3",
        region: str = "eastus",
        resource_group: Optional[str] = None,
        auto_connect: bool = True,
        config_file: Optional[str] = None
    ):
        """Initialize CLI orchestrator.

        Args:
            repo: GitHub repository URL (optional)
            vm_size: Azure VM size
            region: Azure region
            resource_group: Resource group name (optional)
            auto_connect: Whether to auto-connect via SSH
            config_file: Configuration file path (optional)
        """
        self.repo = repo
        self.vm_size = vm_size
        self.region = region
        self.resource_group = resource_group
        self.auto_connect = auto_connect
        self.config_file = config_file

        # Initialize modules
        self.auth = AzureAuthenticator()
        self.provisioner = VMProvisioner()
        self.progress = ProgressDisplay()

        # Track resources for cleanup
        self.vm_details: Optional[VMDetails] = None
        self.ssh_keys: Optional[Path] = None

    def run(self) -> int:
        """Execute main workflow.

        Returns:
            Exit code (0 = success, non-zero = error)
        """
        try:
            # STEP 1: Check prerequisites
            self.progress.start_operation("Prerequisites Check")
            self._check_prerequisites()
            self.progress.complete(success=True, message="All prerequisites available")

            # STEP 2: Authenticate with Azure
            self.progress.start_operation("Azure Authentication")
            subscription_id = self._authenticate_azure()
            self.progress.complete(
                success=True,
                message=f"Authenticated with subscription: {subscription_id[:8]}..."
            )

            # STEP 3: Generate or retrieve SSH keys
            self.progress.start_operation("SSH Key Setup")
            ssh_key_pair = self._setup_ssh_keys()
            self.progress.complete(
                success=True,
                message=f"SSH keys ready: {ssh_key_pair.private_path.name}"
            )

            # STEP 4: Provision VM
            timestamp = int(time.time())
            vm_name = f"azlin-vm-{timestamp}"
            rg_name = self.resource_group or f"azlin-rg-{timestamp}"

            self.progress.start_operation(
                f"Provisioning VM: {vm_name}",
                estimated_seconds=300
            )
            vm_details = self._provision_vm(
                vm_name,
                rg_name,
                ssh_key_pair.public_key_content
            )
            self.vm_details = vm_details
            self.progress.complete(
                success=True,
                message=f"VM ready at {vm_details.public_ip}"
            )

            # STEP 5: Wait for VM to be fully ready (cloud-init to complete)
            self.progress.start_operation(
                "Waiting for cloud-init to complete",
                estimated_seconds=180
            )
            self._wait_for_cloud_init(vm_details, ssh_key_pair.private_path)
            self.progress.complete(
                success=True,
                message="All development tools installed"
            )

            # STEP 6: GitHub setup (if repo provided)
            if self.repo:
                self.progress.start_operation(
                    "GitHub Setup",
                    estimated_seconds=60
                )
                self._setup_github(vm_details, ssh_key_pair.private_path)
                self.progress.complete(
                    success=True,
                    message=f"Repository cloned: {self.repo}"
                )

            # STEP 7: Send completion notification
            self._send_notification(vm_details, success=True)

            # STEP 8: Display connection info
            self._display_connection_info(vm_details)

            # STEP 9: Auto-connect via SSH with tmux
            if self.auto_connect:
                self.progress.update(
                    "Connecting via SSH...",
                    ProgressStage.STARTED
                )
                exit_code = self._connect_ssh(vm_details, ssh_key_pair.private_path)
                return exit_code

            return 0

        except PrerequisiteError as e:
            self.progress.update(str(e), ProgressStage.FAILED)
            return 2
        except AuthenticationError as e:
            self.progress.update(f"Authentication failed: {e}", ProgressStage.FAILED)
            self._send_notification_error(str(e))
            return 3
        except (ProvisioningError, SSHKeyError) as e:
            self.progress.update(f"Provisioning failed: {e}", ProgressStage.FAILED)
            self._send_notification_error(str(e))
            self._cleanup_on_failure()
            return 4
        except SSHConnectionError as e:
            self.progress.update(f"SSH connection failed: {e}", ProgressStage.FAILED)
            # Don't cleanup - VM is still running
            return 5
        except GitHubSetupError as e:
            self.progress.update(f"GitHub setup failed: {e}", ProgressStage.WARNING)
            # Continue - GitHub setup is optional
            self._display_connection_info(self.vm_details)
            if self.auto_connect and self.vm_details:
                return self._connect_ssh(self.vm_details, self.ssh_keys)
            return 0
        except KeyboardInterrupt:
            self.progress.update("Cancelled by user", ProgressStage.FAILED)
            self._cleanup_on_failure()
            return 130
        except Exception as e:
            self.progress.update(f"Unexpected error: {e}", ProgressStage.FAILED)
            logger.exception("Unexpected error in main workflow")
            self._send_notification_error(str(e))
            self._cleanup_on_failure()
            return 1

    def _check_prerequisites(self) -> None:
        """Check all prerequisites are installed.

        Raises:
            PrerequisiteError: If prerequisites missing
        """
        result = PrerequisiteChecker.check_all()

        if not result.all_available:
            message = PrerequisiteChecker.format_missing_message(
                result.missing,
                result.platform_name
            )
            click.echo(message, err=True)
            raise PrerequisiteError(f"Missing required tools: {', '.join(result.missing)}")

        self.progress.update(
            f"Platform: {result.platform_name}, Tools: {', '.join(result.available)}"
        )

    def _authenticate_azure(self) -> str:
        """Authenticate with Azure and get subscription ID.

        Returns:
            str: Subscription ID

        Raises:
            AuthenticationError: If authentication fails
        """
        self.progress.update("Checking Azure CLI authentication...")

        # Verify az CLI is available
        if not self.auth.check_az_cli_available():
            raise AuthenticationError("Azure CLI not available. Please install az CLI.")

        # Get credentials (triggers az login if needed)
        self.auth.get_credentials()

        # Get subscription ID
        subscription_id = self.auth.get_subscription_id()

        self.progress.update(f"Using subscription: {subscription_id}")

        return subscription_id

    def _setup_ssh_keys(self) -> object:
        """Generate or retrieve SSH keys.

        Returns:
            SSHKeyPair object

        Raises:
            SSHKeyError: If key generation fails
        """
        self.progress.update("Checking for existing SSH keys...")

        ssh_key_pair = SSHKeyManager.ensure_key_exists()
        self.ssh_keys = ssh_key_pair.private_path

        self.progress.update(
            f"Using key: {ssh_key_pair.private_path}",
            ProgressStage.IN_PROGRESS
        )

        return ssh_key_pair

    def _provision_vm(
        self,
        vm_name: str,
        rg_name: str,
        public_key: str
    ) -> VMDetails:
        """Provision Azure VM with dev tools.

        Args:
            vm_name: VM name
            rg_name: Resource group name
            public_key: SSH public key content

        Returns:
            VMDetails object

        Raises:
            ProvisioningError: If provisioning fails
        """
        self.progress.update(f"Creating VM: {vm_name}")
        self.progress.update(f"Region: {self.region}, Size: {self.vm_size}")

        # Create VM config
        config = self.provisioner.create_vm_config(
            name=vm_name,
            resource_group=rg_name,
            location=self.region,
            size=self.vm_size,
            ssh_public_key=public_key
        )

        # Progress callback
        def progress_callback(msg: str):
            self.progress.update(msg, ProgressStage.IN_PROGRESS)

        # Provision VM
        vm_details = self.provisioner.provision_vm(config, progress_callback)

        self.progress.update(f"VM created with IP: {vm_details.public_ip}")

        return vm_details

    def _wait_for_cloud_init(self, vm_details: VMDetails, key_path: Path) -> None:
        """Wait for cloud-init to complete on VM.

        Args:
            vm_details: VM details
            key_path: SSH private key path

        Raises:
            SSHConnectionError: If cloud-init check fails
        """
        self.progress.update("Waiting for SSH to be available...")

        # Wait for SSH port to be accessible
        ssh_ready = SSHConnector.wait_for_ssh_ready(
            vm_details.public_ip,
            key_path,
            timeout=300,
            interval=5
        )

        if not ssh_ready:
            raise SSHConnectionError("SSH did not become available")

        self.progress.update("SSH available, checking cloud-init status...")

        # Check cloud-init status
        ssh_config = SSHConfig(
            host=vm_details.public_ip,
            user="azureuser",
            key_path=key_path
        )

        # Wait for cloud-init to complete (check every 10s for up to 3 minutes)
        max_attempts = 18
        for attempt in range(max_attempts):
            try:
                output = SSHConnector.execute_remote_command(
                    ssh_config,
                    "cloud-init status",
                    timeout=30
                )

                if "status: done" in output:
                    self.progress.update("cloud-init completed successfully")
                    return
                elif "status: running" in output:
                    self.progress.update(
                        f"cloud-init still running... (attempt {attempt + 1}/{max_attempts})"
                    )
                    time.sleep(10)
                else:
                    self.progress.update(f"cloud-init status: {output.strip()}")
                    time.sleep(10)

            except Exception as e:
                logger.debug(f"Error checking cloud-init status: {e}")
                time.sleep(10)

        # If we get here, cloud-init didn't complete but we'll proceed anyway
        self.progress.update(
            "cloud-init status check timed out, proceeding anyway",
            ProgressStage.WARNING
        )

    def _setup_github(self, vm_details: VMDetails, key_path: Path) -> None:
        """Setup GitHub on VM and clone repository.

        Args:
            vm_details: VM details
            key_path: SSH private key path

        Raises:
            GitHubSetupError: If GitHub setup fails
        """
        if not self.repo:
            return

        self.progress.update(f"Setting up GitHub for: {self.repo}")

        # Validate repo URL
        valid, message = GitHubSetupHandler.validate_repo_url(self.repo)
        if not valid:
            raise GitHubSetupError(f"Invalid repository URL: {message}")

        # Create SSH config
        ssh_config = SSHConfig(
            host=vm_details.public_ip,
            user="azureuser",
            key_path=key_path
        )

        # Setup GitHub and clone repo
        self.progress.update("Authenticating with GitHub (may require browser)...")
        repo_details = GitHubSetupHandler.setup_github_on_vm(
            ssh_config,
            self.repo
        )

        self.progress.update(f"Repository cloned to: {repo_details.clone_path}")

    def _connect_ssh(self, vm_details: VMDetails, key_path: Path) -> int:
        """Connect to VM via SSH with tmux session.

        Args:
            vm_details: VM details
            key_path: SSH private key path

        Returns:
            int: SSH exit code

        Raises:
            SSHConnectionError: If connection fails
        """
        ssh_config = SSHConfig(
            host=vm_details.public_ip,
            user="azureuser",
            key_path=key_path
        )

        click.echo("\n" + "="*60)
        click.echo(f"Connecting to {vm_details.name} via SSH...")
        click.echo(f"Starting tmux session 'azlin'")
        click.echo("="*60 + "\n")

        # Connect with auto-tmux
        exit_code = SSHConnector.connect(
            ssh_config,
            tmux_session="azlin",
            auto_tmux=True
        )

        return exit_code

    def _send_notification(self, vm_details: VMDetails, success: bool = True) -> None:
        """Send completion notification via imessR if available.

        Args:
            vm_details: VM details
            success: Whether provisioning succeeded
        """
        result = NotificationHandler.send_completion_notification(
            vm_details.name,
            vm_details.public_ip,
            success=success
        )

        if result.sent:
            logger.info("Notification sent successfully")
        else:
            logger.debug(f"Notification not sent: {result.message}")

    def _send_notification_error(self, error_message: str) -> None:
        """Send error notification.

        Args:
            error_message: Error message
        """
        result = NotificationHandler.send_error_notification(error_message)

        if result.sent:
            logger.info("Error notification sent")
        else:
            logger.debug(f"Error notification not sent: {result.message}")

    def _display_connection_info(self, vm_details: VMDetails) -> None:
        """Display VM connection information.

        Args:
            vm_details: VM details
        """
        click.echo("\n" + "="*60)
        click.echo("VM Provisioning Complete!")
        click.echo("="*60)
        click.echo(f"  Name:           {vm_details.name}")
        click.echo(f"  IP Address:     {vm_details.public_ip}")
        click.echo(f"  Resource Group: {vm_details.resource_group}")
        click.echo(f"  Region:         {vm_details.location}")
        click.echo(f"  Size:           {vm_details.size}")
        click.echo("\nInstalled Tools:")
        click.echo("  - Docker, Azure CLI, GitHub CLI, Git")
        click.echo("  - Node.js, Python, Rust, Go, .NET 10 RC")
        click.echo("  - tmux")

        if self.repo:
            click.echo(f"\nRepository: {self.repo}")

        click.echo("\nSSH Connection:")
        click.echo(f"  ssh azureuser@{vm_details.public_ip}")
        click.echo(f"  (using key: {self.ssh_keys})")
        click.echo("="*60 + "\n")

    def _cleanup_on_failure(self) -> None:
        """Cleanup resources on failure (optional).

        Note: We don't automatically delete the VM on failure
        as the user may want to investigate or keep it.
        """
        if self.vm_details:
            click.echo("\n" + "="*60)
            click.echo("Provisioning Failed")
            click.echo("="*60)
            click.echo(f"VM may still exist: {self.vm_details.name}")
            click.echo(f"Resource Group: {self.vm_details.resource_group}")
            click.echo("\nTo delete VM and cleanup resources:")
            click.echo(f"  az group delete --name {self.vm_details.resource_group} --yes")
            click.echo("="*60 + "\n")


def show_interactive_menu(
    vms: List[VMInfo],
    ssh_key_path: Path
) -> Optional[int]:
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
        if response in ['', 'y', 'yes']:
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
            ssh_config = SSHConfig(
                host=vm.public_ip,
                user="azureuser",
                key_path=ssh_key_path
            )
            exit_code = SSHConnector.connect(
                ssh_config,
                tmux_session="azlin",
                auto_tmux=True
            )
            return exit_code
        else:
            click.echo("VM is not running or has no public IP")
            return 1

    # Multiple VMs - show menu
    click.echo("\n" + "=" * 60)
    click.echo("Available VMs:")
    click.echo("=" * 60)

    for idx, vm in enumerate(vms, 1):
        status = vm.get_status_display()
        ip = vm.public_ip or "No IP"
        click.echo(f"  {idx}. {vm.name} - {status} - {ip}")

    click.echo(f"  n. Create new VM")
    click.echo("=" * 60)

    choice = input("\nSelect VM (number or 'n' for new): ").strip().lower()

    if choice == 'n':
        return None  # Continue to provisioning

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(vms):
            vm = vms[idx]

            if not vm.is_running():
                click.echo(f"\nVM '{vm.name}' is not running.")
                click.echo("Start it with: az vm start --name {} --resource-group {}".format(
                    vm.name, vm.resource_group
                ))
                return 1

            if not vm.public_ip:
                click.echo(f"\nVM '{vm.name}' has no public IP.")
                return 1

            click.echo(f"\nConnecting to {vm.name}...")
            ssh_config = SSHConfig(
                host=vm.public_ip,
                user="azureuser",
                key_path=ssh_key_path
            )
            exit_code = SSHConnector.connect(
                ssh_config,
                tmux_session="azlin",
                auto_tmux=True
            )
            return exit_code
        else:
            click.echo("Invalid selection")
            return 1
    except ValueError:
        click.echo("Invalid input")
        return 1


def generate_vm_name(
    custom_name: Optional[str] = None,
    command: Optional[str] = None
) -> str:
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


@click.group(invoke_without_command=True)
@click.pass_context
@click.option('--repo', help='GitHub repository URL to clone', type=str)
@click.option('--vm-size', help='Azure VM size', type=str)
@click.option('--region', help='Azure region', type=str)
@click.option('--resource-group', '--rg', help='Azure resource group', type=str)
@click.option('--name', help='Custom VM name', type=str)
@click.option('--pool', help='Number of VMs to create in parallel', type=int)
@click.option('--no-auto-connect', help='Do not auto-connect via SSH', is_flag=True)
@click.option('--config', help='Config file path', type=click.Path())
@click.version_option(version=__version__)
def main(
    ctx,
    repo: Optional[str],
    vm_size: Optional[str],
    region: Optional[str],
    resource_group: Optional[str],
    name: Optional[str],
    pool: Optional[int],
    no_auto_connect: bool,
    config: Optional[str]
):
    """azlin - Azure Ubuntu VM provisioning and management.

    Provisions Azure Ubuntu VMs with development tools, manages existing VMs,
    and executes commands remotely.

    \b
    COMMANDS:
        list          List VMs in resource group
        connect       Connect to existing VM via SSH
        w             Run 'w' command on all VMs
        ps            Run 'ps aux' on all VMs
        kill          Delete a VM and all resources
        killall       Delete all VMs in resource group

    \b
    EXAMPLES:
        # Interactive menu (if VMs exist) or provision new VM
        $ azlin

        # List VMs in resource group
        $ azlin list

        # Run 'w' on all VMs
        $ azlin w

        # Run 'ps aux' on all VMs
        $ azlin ps

        # Delete a specific VM
        $ azlin kill azlin-vm-12345

        # Delete all VMs in resource group
        $ azlin killall

        # Provision VM with custom name
        $ azlin --name my-dev-vm

        # Provision VM and clone repository
        $ azlin --repo https://github.com/owner/repo

        # Execute command on new VM (opens in new terminal)
        $ azlin -- python train.py

        # Provision 5 VMs in parallel
        $ azlin --pool 5

    \b
    CONFIGURATION:
        Config file: ~/.azlin/config.toml
        Set defaults: default_resource_group, default_region, default_vm_size

    For help on any command: azlin <command> --help
    """
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
    )

    # If no subcommand, check for interactive mode or provision
    if ctx.invoked_subcommand is None:
        # Check for command after --
        command = None
        if '--' in sys.argv:
            delimiter_idx = sys.argv.index('--')
            command = ' '.join(sys.argv[delimiter_idx + 1:])

        # If no special args, try interactive mode
        if not any([repo, pool, name, command]):
            try:
                # Load config to get resource group
                azlin_config = ConfigManager.load_config(config)
                rg = resource_group or azlin_config.default_resource_group

                if rg:
                    # List VMs and show menu
                    ssh_key_pair = SSHKeyManager.ensure_key_exists()
                    vms = VMManager.list_vms(rg, include_stopped=False)
                    vms = VMManager.filter_by_prefix(vms, "azlin")
                    vms = VMManager.sort_by_created_time(vms)

                    if vms:
                        exit_code = show_interactive_menu(vms, ssh_key_pair.private_path)
                        if exit_code is not None:
                            sys.exit(exit_code)
                        # If None, continue to provisioning

            except Exception as e:
                logger.debug(f"Interactive mode failed: {e}")
                # Continue to provisioning

        # Load config for defaults
        try:
            azlin_config = ConfigManager.load_config(config)
        except ConfigError:
            azlin_config = AzlinConfig()

        # Get settings with CLI override
        final_rg = resource_group or azlin_config.default_resource_group
        final_region = region or azlin_config.default_region
        final_vm_size = vm_size or azlin_config.default_vm_size

        # Generate VM name
        vm_name = generate_vm_name(name, command)

        # Warn if pool > 10
        if pool and pool > 10:
            estimated_cost = pool * 0.10  # Rough estimate
            click.echo(f"\nWARNING: Creating {pool} VMs")
            click.echo(f"Estimated cost: ~${estimated_cost:.2f}/hour")
            click.echo("Continue? [y/N]: ", nl=False)
            response = input().lower()
            if response not in ['y', 'yes']:
                click.echo("Cancelled.")
                sys.exit(0)

        # Validate repo URL if provided
        if repo:
            if not repo.startswith('https://github.com/'):
                click.echo(
                    "Error: Invalid GitHub URL. Must start with https://github.com/",
                    err=True
                )
                sys.exit(1)

        # Create orchestrator and run
        orchestrator = CLIOrchestrator(
            repo=repo,
            vm_size=final_vm_size,
            region=final_region,
            resource_group=final_rg,
            auto_connect=not no_auto_connect,
            config_file=config
        )

        # Update config with used resource group
        if final_rg:
            try:
                ConfigManager.update_config(
                    config,
                    default_resource_group=final_rg,
                    last_vm_name=vm_name
                )
            except ConfigError as e:
                logger.debug(f"Failed to update config: {e}")

        # Execute command if specified
        if command and not pool:
            click.echo(f"\nCommand: {command}")
            click.echo("Will execute after provisioning...\n")

            exit_code = orchestrator.run()

            if exit_code == 0 and orchestrator.vm_details:
                # Launch terminal with command
                try:
                    terminal_config = TerminalConfig(
                        ssh_host=orchestrator.vm_details.public_ip,
                        ssh_user="azureuser",
                        ssh_key_path=orchestrator.ssh_keys,
                        command=command,
                        title=f"azlin - {command}"
                    )
                    TerminalLauncher.launch(terminal_config)
                except Exception as e:
                    logger.error(f"Failed to launch terminal: {e}")
                    click.echo("\nExecute manually:")
                    click.echo(f"  ssh azureuser@{orchestrator.vm_details.public_ip} {command}")

            sys.exit(exit_code)

        # Pool provisioning (placeholder for now)
        if pool and pool > 1:
            click.echo(f"\nPool provisioning ({pool} VMs) is not yet fully implemented.")
            click.echo("Creating first VM...")
            # Fall through to standard provisioning

        exit_code = orchestrator.run()
        sys.exit(exit_code)


@main.command(name='list')
@click.option('--resource-group', '--rg', help='Resource group to list VMs from', type=str)
@click.option('--config', help='Config file path', type=click.Path())
@click.option('--all', 'show_all', help='Show all VMs (including stopped)', is_flag=True)
def list_command(resource_group: Optional[str], config: Optional[str], show_all: bool):
    """List VMs in resource group.

    Shows VM name, status, IP address, region, and size.

    \b
    Examples:
        azlin list
        azlin list --rg my-resource-group
        azlin list --all
    """
    try:
        # Get resource group from config or CLI
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified and no default configured.", err=True)
            click.echo("Use --resource-group or set default in ~/.azlin/config.toml", err=True)
            sys.exit(1)

        click.echo(f"Listing VMs in resource group: {rg}\n")

        # List VMs
        vms = VMManager.list_vms(rg, include_stopped=show_all)

        # Filter to azlin VMs
        vms = VMManager.filter_by_prefix(vms, "azlin")
        vms = VMManager.sort_by_created_time(vms)

        if not vms:
            click.echo("No VMs found.")
            return

        # Display table
        click.echo("=" * 90)
        click.echo(f"{'NAME':<35} {'STATUS':<15} {'IP':<15} {'REGION':<15} {'SIZE':<10}")
        click.echo("=" * 90)

        for vm in vms:
            status = vm.get_status_display()
            ip = vm.public_ip or "N/A"
            size = vm.vm_size or "N/A"
            click.echo(f"{vm.name:<35} {status:<15} {ip:<15} {vm.location:<15} {size:<10}")

        click.echo("=" * 90)
        click.echo(f"\nTotal: {len(vms)} VMs")

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option('--resource-group', '--rg', help='Resource group', type=str)
@click.option('--config', help='Config file path', type=click.Path())
def w(resource_group: Optional[str], config: Optional[str]):
    """Run 'w' command on all VMs.

    Shows who is logged in and what they are doing on each VM.

    \b
    Examples:
        azlin w
        azlin w --rg my-resource-group
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # Get SSH key
        ssh_key_pair = SSHKeyManager.ensure_key_exists()

        # List running VMs
        vms = VMManager.list_vms(rg, include_stopped=False)
        vms = VMManager.filter_by_prefix(vms, "azlin")

        if not vms:
            click.echo("No running VMs found.")
            return

        running_vms = [vm for vm in vms if vm.is_running() and vm.public_ip]

        if not running_vms:
            click.echo("No running VMs with public IPs found.")
            return

        click.echo(f"Running 'w' on {len(running_vms)} VMs...\n")

        # Build SSH configs
        ssh_configs = [
            SSHConfig(
                host=vm.public_ip,
                user="azureuser",
                key_path=ssh_key_pair.private_path
            )
            for vm in running_vms
        ]

        # Execute in parallel
        results = WCommandExecutor.execute_w_on_vms(ssh_configs, timeout=30)

        # Display output
        output = WCommandExecutor.format_w_output(results)
        click.echo(output)

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument('vm_name', type=str)
@click.option('--resource-group', '--rg', help='Resource group', type=str)
@click.option('--config', help='Config file path', type=click.Path())
@click.option('--force', is_flag=True, help='Skip confirmation prompt')
def kill(
    vm_name: str,
    resource_group: Optional[str],
    config: Optional[str],
    force: bool
):
    """Delete a VM and all associated resources.

    Deletes the VM, NICs, disks, and public IPs.

    \b
    Examples:
        azlin kill azlin-vm-12345
        azlin kill my-vm --rg my-resource-group
        azlin kill my-vm --force
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # Validate VM exists
        vm = VMManager.get_vm(vm_name, rg)

        if not vm:
            click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'.", err=True)
            sys.exit(1)

        # Show confirmation prompt unless --force
        if not force:
            click.echo(f"\nVM Details:")
            click.echo(f"  Name:           {vm.name}")
            click.echo(f"  Resource Group: {vm.resource_group}")
            click.echo(f"  Status:         {vm.get_status_display()}")
            click.echo(f"  IP:             {vm.public_ip or 'N/A'}")
            click.echo(f"  Size:           {vm.vm_size or 'N/A'}")
            click.echo(f"\nThis will delete the VM and all associated resources (NICs, disks, IPs).")
            click.echo("This action cannot be undone.\n")

            confirm = input("Are you sure you want to delete this VM? [y/N]: ").lower()
            if confirm not in ['y', 'yes']:
                click.echo("Cancelled.")
                return

        # Delete VM
        click.echo(f"\nDeleting VM '{vm_name}'...")

        result = VMLifecycleManager.delete_vm(
            vm_name=vm_name,
            resource_group=rg,
            force=True,
            no_wait=False
        )

        if result.success:
            click.echo(f"\nSuccess! {result.message}")
            if result.resources_deleted:
                click.echo("\nDeleted resources:")
                for resource in result.resources_deleted:
                    click.echo(f"  - {resource}")
        else:
            click.echo(f"\nError: {result.message}", err=True)
            sys.exit(1)

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except VMLifecycleError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option('--resource-group', '--rg', help='Resource group', type=str)
@click.option('--config', help='Config file path', type=click.Path())
@click.option('--force', is_flag=True, help='Skip confirmation prompt')
@click.option('--prefix', default='azlin', help='Only delete VMs with this prefix')
def killall(
    resource_group: Optional[str],
    config: Optional[str],
    force: bool,
    prefix: str
):
    """Delete all VMs in resource group.

    Deletes all VMs matching the prefix and their associated resources.

    \b
    Examples:
        azlin killall
        azlin killall --rg my-resource-group
        azlin killall --prefix test-vm
        azlin killall --force
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # List VMs
        vms = VMManager.list_vms(rg, include_stopped=True)
        vms = VMManager.filter_by_prefix(vms, prefix)

        if not vms:
            click.echo(f"No VMs found with prefix '{prefix}' in resource group '{rg}'.")
            return

        # Show confirmation prompt unless --force
        if not force:
            click.echo(f"\nFound {len(vms)} VM(s) in resource group '{rg}':")
            click.echo("=" * 80)
            for vm in vms:
                status = vm.get_status_display()
                ip = vm.public_ip or "N/A"
                click.echo(f"  {vm.name:<35} {status:<15} {ip:<15}")
            click.echo("=" * 80)

            click.echo(f"\nThis will delete all {len(vms)} VM(s) and their associated resources.")
            click.echo("This action cannot be undone.\n")

            confirm = input(f"Are you sure you want to delete {len(vms)} VM(s)? [y/N]: ").lower()
            if confirm not in ['y', 'yes']:
                click.echo("Cancelled.")
                return

        # Delete all VMs
        click.echo(f"\nDeleting {len(vms)} VM(s) in parallel...")

        summary = VMLifecycleManager.delete_all_vms(
            resource_group=rg,
            force=True,
            vm_prefix=prefix,
            max_workers=5
        )

        # Display results
        click.echo("\n" + "=" * 80)
        click.echo(f"Deletion Summary")
        click.echo("=" * 80)
        click.echo(f"Total VMs:     {summary.total}")
        click.echo(f"Succeeded:     {summary.succeeded}")
        click.echo(f"Failed:        {summary.failed}")
        click.echo("=" * 80)

        # Show details
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

        # Exit with error code if any failed
        if not summary.all_succeeded:
            sys.exit(1)

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except VMLifecycleError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option('--resource-group', '--rg', help='Resource group', type=str)
@click.option('--config', help='Config file path', type=click.Path())
@click.option('--grouped', is_flag=True, help='Group output by VM instead of prefixing')
def ps(
    resource_group: Optional[str],
    config: Optional[str],
    grouped: bool
):
    """Run 'ps aux' command on all VMs.

    Shows running processes on each VM. Output is prefixed with [vm-name].
    SSH processes are automatically filtered out.

    \b
    Examples:
        azlin ps
        azlin ps --rg my-resource-group
        azlin ps --grouped
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # Get SSH key
        ssh_key_pair = SSHKeyManager.ensure_key_exists()

        # List running VMs
        vms = VMManager.list_vms(rg, include_stopped=False)
        vms = VMManager.filter_by_prefix(vms, "azlin")

        if not vms:
            click.echo("No running VMs found.")
            return

        running_vms = [vm for vm in vms if vm.is_running() and vm.public_ip]

        if not running_vms:
            click.echo("No running VMs with public IPs found.")
            return

        click.echo(f"Running 'ps aux' on {len(running_vms)} VMs...\n")

        # Build SSH configs
        ssh_configs = [
            SSHConfig(
                host=vm.public_ip,
                user="azureuser",
                key_path=ssh_key_pair.private_path
            )
            for vm in running_vms
        ]

        # Execute in parallel
        results = PSCommandExecutor.execute_ps_on_vms(ssh_configs, timeout=30)

        # Display output
        if grouped:
            output = PSCommandExecutor.format_ps_output_grouped(results, filter_ssh=True)
        else:
            output = PSCommandExecutor.format_ps_output(results, filter_ssh=True)

        click.echo(output)

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except RemoteExecError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    main()


__all__ = ['main', 'CLIOrchestrator', 'AzlinError']
