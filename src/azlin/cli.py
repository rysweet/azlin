"""CLI entry point for azlin v2.0.

This module provides the enhanced command-line interface with:
- Config storage and resource group management
- VM listing and status
- Interactive session selection
- Parallel VM provisioning (pools)
- Remote command execution
- Enhanced help

Commands:
    azlin                    # Show help
    azlin new                # Provision new VM
    azlin list               # List VMs in resource group
    azlin w                  # Run 'w' command on all VMs
    azlin -- <command>       # Execute command on VM(s)
"""

import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import click

from azlin import __version__
from azlin.azure_auth import AuthenticationError, AzureAuthenticator

# New modules for v2.0
from azlin.config_manager import AzlinConfig, ConfigError, ConfigManager
from azlin.cost_tracker import CostTracker, CostTrackerError
from azlin.log_viewer import LogType, LogViewer, LogViewerError
from azlin.modules.file_transfer import (
    FileTransfer,
    FileTransferError,
    PathParser,
    SessionManager,
    TransferEndpoint,
)
from azlin.modules.github_setup import GitHubSetupError, GitHubSetupHandler
from azlin.modules.home_sync import (
    HomeSyncError,
    HomeSyncManager,
    RsyncError,
    SecurityValidationError,
)
from azlin.modules.notifications import NotificationHandler
from azlin.modules.prerequisites import PrerequisiteChecker, PrerequisiteError
from azlin.modules.progress import ProgressDisplay, ProgressStage
from azlin.modules.ssh_connector import SSHConfig, SSHConnectionError, SSHConnector
from azlin.modules.ssh_keys import SSHKeyError, SSHKeyManager
from azlin.remote_exec import PSCommandExecutor, RemoteExecError, RemoteExecutor, WCommandExecutor
from azlin.vm_connector import VMConnector, VMConnectorError
from azlin.vm_lifecycle import VMLifecycleError, VMLifecycleManager
from azlin.vm_lifecycle_control import VMLifecycleControlError, VMLifecycleController
from azlin.vm_manager import VMInfo, VMManager, VMManagerError
from azlin.vm_provisioning import (
    ProvisioningError,
    VMDetails,
    VMProvisioner,
)

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
        config_file: Optional[str] = None,
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
                success=True, message=f"Authenticated with subscription: {subscription_id[:8]}..."
            )

            # STEP 3: Generate or retrieve SSH keys
            self.progress.start_operation("SSH Key Setup")
            ssh_key_pair = self._setup_ssh_keys()
            self.progress.complete(
                success=True, message=f"SSH keys ready: {ssh_key_pair.private_path.name}"
            )

            # STEP 4: Provision VM
            timestamp = int(time.time())
            vm_name = f"azlin-vm-{timestamp}"
            rg_name = self.resource_group or f"azlin-rg-{timestamp}"

            self.progress.start_operation(f"Provisioning VM: {vm_name}", estimated_seconds=300)
            vm_details = self._provision_vm(vm_name, rg_name, ssh_key_pair.public_key_content)
            self.vm_details = vm_details
            self.progress.complete(success=True, message=f"VM ready at {vm_details.public_ip}")

            # STEP 5: Wait for VM to be fully ready (cloud-init to complete)
            self.progress.start_operation(
                "Waiting for cloud-init to complete", estimated_seconds=180
            )
            self._wait_for_cloud_init(vm_details, ssh_key_pair.private_path)
            self.progress.complete(success=True, message="All development tools installed")

            # STEP 5.5: Sync home directory (NEW)
            self.progress.start_operation("Syncing home directory")
            self._sync_home_directory(vm_details, ssh_key_pair.private_path)
            self.progress.complete(success=True, message="Home directory synced")

            # STEP 6: GitHub setup (if repo provided)
            if self.repo:
                self.progress.start_operation("GitHub Setup", estimated_seconds=60)
                self._setup_github(vm_details, ssh_key_pair.private_path)
                self.progress.complete(success=True, message=f"Repository cloned: {self.repo}")

            # STEP 7: Send completion notification
            self._send_notification(vm_details, success=True)

            # STEP 8: Display connection info
            self._display_connection_info(vm_details)

            # STEP 9: Auto-connect via SSH with tmux
            if self.auto_connect:
                self.progress.update("Connecting via SSH...", ProgressStage.STARTED)
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
                result.missing, result.platform_name
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

        self.progress.update(f"Using key: {ssh_key_pair.private_path}", ProgressStage.IN_PROGRESS)

        return ssh_key_pair

    def _provision_vm(self, vm_name: str, rg_name: str, public_key: str) -> VMDetails:
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
            ssh_public_key=public_key,
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
            vm_details.public_ip, key_path, timeout=300, interval=5
        )

        if not ssh_ready:
            raise SSHConnectionError("SSH did not become available")

        self.progress.update("SSH available, checking cloud-init status...")

        # Check cloud-init status
        ssh_config = SSHConfig(host=vm_details.public_ip, user="azureuser", key_path=key_path)

        # Wait for cloud-init to complete (check every 10s for up to 3 minutes)
        max_attempts = 18
        for attempt in range(max_attempts):
            try:
                output = SSHConnector.execute_remote_command(
                    ssh_config, "cloud-init status", timeout=30
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
            "cloud-init status check timed out, proceeding anyway", ProgressStage.WARNING
        )

    def _sync_home_directory(self, vm_details: VMDetails, key_path: Path) -> None:
        """Sync home directory to VM.

        Args:
            vm_details: VM details
            key_path: SSH private key path

        Note:
            Sync failures are logged as warnings but don't block VM provisioning.
        """
        try:
            # Create SSH config
            ssh_config = SSHConfig(host=vm_details.public_ip, user="azureuser", key_path=key_path)

            # Progress callback
            def progress_callback(msg: str):
                self.progress.update(msg, ProgressStage.IN_PROGRESS)

            # Attempt sync
            result = HomeSyncManager.sync_to_vm(
                ssh_config, dry_run=False, progress_callback=progress_callback
            )

            if result.success:
                if result.files_synced > 0:
                    self.progress.update(
                        f"Synced {result.files_synced} files "
                        f"({result.bytes_transferred / 1024:.1f} KB) "
                        f"in {result.duration_seconds:.1f}s"
                    )
                else:
                    self.progress.update("No files to sync")
            else:
                # Log errors but don't fail
                for error in result.errors:
                    logger.warning(f"Sync error: {error}")

        except SecurityValidationError as e:
            # Don't fail VM provisioning, just warn
            self.progress.update(f"Home sync skipped: {e}", ProgressStage.WARNING)
            logger.warning(f"Security validation failed: {e}")

        except (RsyncError, HomeSyncError) as e:
            # Don't fail VM provisioning, just warn
            self.progress.update(f"Home sync failed: {e}", ProgressStage.WARNING)
            logger.warning(f"Home sync failed: {e}")

        except Exception:
            # Catch all other errors
            self.progress.update("Home sync failed (unexpected error)", ProgressStage.WARNING)
            logger.exception("Unexpected error during home sync")

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
        ssh_config = SSHConfig(host=vm_details.public_ip, user="azureuser", key_path=key_path)

        # Setup GitHub and clone repo
        self.progress.update("Authenticating with GitHub (may require browser)...")
        repo_details = GitHubSetupHandler.setup_github_on_vm(ssh_config, self.repo)

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
        ssh_config = SSHConfig(host=vm_details.public_ip, user="azureuser", key_path=key_path)

        click.echo("\n" + "=" * 60)
        click.echo(f"Connecting to {vm_details.name} via SSH...")
        click.echo("Starting tmux session 'azlin'")
        click.echo("=" * 60 + "\n")

        # Connect with auto-tmux
        exit_code = SSHConnector.connect(ssh_config, tmux_session="azlin", auto_tmux=True)

        return exit_code

    def _send_notification(self, vm_details: VMDetails, success: bool = True) -> None:
        """Send completion notification via imessR if available.

        Args:
            vm_details: VM details
            success: Whether provisioning succeeded
        """
        result = NotificationHandler.send_completion_notification(
            vm_details.name, vm_details.public_ip, success=success
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
        click.echo("\n" + "=" * 60)
        click.echo("VM Provisioning Complete!")
        click.echo("=" * 60)
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
        click.echo("=" * 60 + "\n")

    def _cleanup_on_failure(self) -> None:
        """Cleanup resources on failure (optional).

        Note: We don't automatically delete the VM on failure
        as the user may want to investigate or keep it.
        """
        if self.vm_details:
            click.echo("\n" + "=" * 60)
            click.echo("Provisioning Failed")
            click.echo("=" * 60)
            click.echo(f"VM may still exist: {self.vm_details.name}")
            click.echo(f"Resource Group: {self.vm_details.resource_group}")
            click.echo("\nTo delete VM and cleanup resources:")
            click.echo(f"  az group delete --name {self.vm_details.resource_group} --yes")
            click.echo("=" * 60 + "\n")


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


def show_interactive_menu(vms: list[VMInfo], ssh_key_path: Path) -> Optional[int]:
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

            exit_code = SSHConnector.connect(ssh_config, tmux_session="azlin", auto_tmux=True)
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
                    "Start it with: az vm start --name {} --resource-group {}".format(
                        vm.name, vm.resource_group
                    )
                )
                return 1

            if not vm.public_ip:
                click.echo(f"\nVM '{vm.name}' has no public IP.")
                return 1

            click.echo(f"\nConnecting to {vm.name}...")
            ssh_config = SSHConfig(host=vm.public_ip, user="azureuser", key_path=ssh_key_path)

            # Sync home directory before connection (silent)
            _auto_sync_home_directory(ssh_config)

            exit_code = SSHConnector.connect(ssh_config, tmux_session="azlin", auto_tmux=True)
            return exit_code
        else:
            click.echo("Invalid selection")
            return 1
    except ValueError:
        click.echo("Invalid input")
        return 1


def generate_vm_name(custom_name: Optional[str] = None, command: Optional[str] = None) -> str:
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


def select_vm_for_command(vms: list[VMInfo], command: str) -> Optional[VMInfo]:
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

    for idx, vm in enumerate(vms, 1):
        status = vm.get_status_display()
        ip = vm.public_ip or "No IP"
        click.echo(f"  {idx}. {vm.name} - {status} - {ip}")

    click.echo("  n. Create new VM and execute")
    click.echo("=" * 60)

    choice = input("\nSelect VM (number or 'n' for new): ").strip().lower()

    if choice == "n":
        return None  # Signal to create new VM

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(vms):
            return vms[idx]
        else:
            click.echo("Invalid selection")
            return None
    except ValueError:
        click.echo("Invalid input")
        return None


class AzlinGroup(click.Group):
    """Custom Click group that handles -- delimiter for command passthrough."""

    def main(self, *args, **kwargs):
        """Override main to handle -- delimiter before any Click processing."""
        # Check if -- is in sys.argv BEFORE Click processes anything
        if "--" in sys.argv:
            delimiter_idx = sys.argv.index("--")
            # Store the command for later
            passthrough_args = sys.argv[delimiter_idx + 1 :]
            if passthrough_args:
                # Remove everything from -- onwards so Click doesn't see it
                sys.argv = sys.argv[:delimiter_idx]
                # We'll pass this through the context
                if not hasattr(self, "_passthrough_command"):
                    self._passthrough_command = " ".join(passthrough_args)

        return super().main(*args, **kwargs)

    def invoke(self, ctx):
        """Pass the passthrough command to the context."""
        if hasattr(self, "_passthrough_command"):
            ctx.obj = {"passthrough_command": self._passthrough_command}
        return super().invoke(ctx)


@click.group(
    cls=AzlinGroup,
    invoke_without_command=True,
    context_settings={
        "ignore_unknown_options": True,
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    },
)
@click.pass_context
@click.version_option(version=__version__)
def main(ctx):
    """azlin - Azure Ubuntu VM provisioning and management.

    Provisions Azure Ubuntu VMs with development tools, manages existing VMs,
    and executes commands remotely.

    \b
    VM LIFECYCLE COMMANDS:
        new           Provision a new VM (aliases: vm, create)
        list          List VMs in resource group
        status        Show detailed status of VMs
        start         Start a stopped VM
        stop          Stop/deallocate a VM to save costs
        connect       Connect to existing VM via SSH

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

    \b
    EXAMPLES:
        # Show help
        $ azlin

        # Provision a new VM
        $ azlin new

        # List VMs and show status
        $ azlin list
        $ azlin status

        # Start/stop VMs
        $ azlin start my-vm
        $ azlin stop my-vm

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

    # If no subcommand provided, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(0)  # Use ctx.exit() instead of sys.exit() for Click compatibility


@main.command(name="new")
@click.pass_context
@click.option("--repo", help="GitHub repository URL to clone", type=str)
@click.option("--vm-size", help="Azure VM size", type=str)
@click.option("--region", help="Azure region", type=str)
@click.option("--resource-group", "--rg", help="Azure resource group", type=str)
@click.option("--name", help="Custom VM name", type=str)
@click.option("--pool", help="Number of VMs to create in parallel", type=int)
@click.option("--no-auto-connect", help="Do not auto-connect via SSH", is_flag=True)
@click.option("--config", help="Config file path", type=click.Path())
def new_command(
    ctx,
    repo: Optional[str],
    vm_size: Optional[str],
    region: Optional[str],
    resource_group: Optional[str],
    name: Optional[str],
    pool: Optional[int],
    no_auto_connect: bool,
    config: Optional[str],
):
    """Provision a new Azure VM with development tools.

    Creates a new Ubuntu VM in Azure with all development tools pre-installed.
    Optionally connects via SSH and clones a GitHub repository.

    \b
    EXAMPLES:
        # Provision basic VM
        $ azlin new

        # Provision with custom name
        $ azlin new --name my-dev-vm

        # Provision and clone repository
        $ azlin new --repo https://github.com/owner/repo

        # Provision 5 VMs in parallel
        $ azlin new --pool 5

        # Provision and execute command
        $ azlin new -- python train.py
    """
    # Check for passthrough command from custom AzlinGroup
    command = None
    if ctx.obj and "passthrough_command" in ctx.obj:
        command = ctx.obj["passthrough_command"]
    elif ctx.args:
        # If no explicit --, check if we have extra args from Click
        command = " ".join(ctx.args)

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
            if response not in ["y", "yes"]:
                click.echo("Cancelled.")
                sys.exit(0)

        # Validate repo URL if provided
        if repo:
            if not repo.startswith("https://github.com/"):
                click.echo(
                    "Error: Invalid GitHub URL. Must start with https://github.com/", err=True
                )
                sys.exit(1)

        # Create orchestrator and run
        orchestrator = CLIOrchestrator(
            repo=repo,
            vm_size=final_vm_size,
            region=final_region,
            resource_group=final_rg,
            auto_connect=not no_auto_connect,
            config_file=config,
        )

        # Update config with used resource group
        if final_rg:
            try:
                ConfigManager.update_config(
                    config, default_resource_group=final_rg, last_vm_name=vm_name
                )
            except ConfigError as e:
                logger.debug(f"Failed to update config: {e}")

        # Execute command if specified
        if command and not pool:
            click.echo(f"\nCommand to execute: {command}")
            click.echo("Provisioning VM first...\n")

            # Disable auto-connect for command execution mode
            orchestrator.auto_connect = False
            exit_code = orchestrator.run()

            if exit_code == 0 and orchestrator.vm_details:
                # Create VMInfo from VMDetails for execute_command_on_vm
                vm_info = VMInfo(
                    name=orchestrator.vm_details.name,
                    resource_group=orchestrator.vm_details.resource_group,
                    location=orchestrator.vm_details.location,
                    power_state="VM running",
                    public_ip=orchestrator.vm_details.public_ip,
                    vm_size=orchestrator.vm_details.size,
                )

                # Execute command on the newly provisioned VM
                cmd_exit_code = execute_command_on_vm(vm_info, command, orchestrator.ssh_keys)
                sys.exit(cmd_exit_code)
            else:
                click.echo(f"\nProvisioning failed with exit code {exit_code}", err=True)
                sys.exit(exit_code)

        # Pool provisioning
        if pool and pool > 1:
            click.echo(f"\nProvisioning pool of {pool} VMs in parallel...")

            # Generate SSH keys
            ssh_key_pair = SSHKeyManager.ensure_key_exists()

            # Create VM configs for pool
            configs = []
            for i in range(pool):
                vm_name_pool = f"{vm_name}-{i+1:02d}"
                config = orchestrator.provisioner.create_vm_config(
                    name=vm_name_pool,
                    resource_group=final_rg or f"azlin-rg-{int(time.time())}",
                    location=final_region,
                    size=final_vm_size,
                    ssh_public_key=ssh_key_pair.public_key_content,
                )
                configs.append(config)

            # Provision VMs in parallel (returns PoolProvisioningResult)
            try:
                result = orchestrator.provisioner.provision_vm_pool(
                    configs,
                    progress_callback=lambda msg: click.echo(f"  {msg}"),
                    max_workers=min(10, pool),
                )

                # Display results
                click.echo(f"\n{result.get_summary()}")

                if result.successful:
                    click.echo("\nSuccessfully Provisioned VMs:")
                    click.echo("=" * 80)
                    for vm in result.successful:
                        click.echo(f"  {vm.name:<30} {vm.public_ip:<15} {vm.location}")
                    click.echo("=" * 80)

                if result.failed:
                    click.echo("\nFailed VMs:")
                    click.echo("=" * 80)
                    for failure in result.failed:
                        click.echo(
                            f"  {failure.config.name:<30} {failure.error_type:<20} {failure.error[:40]}"
                        )
                    click.echo("=" * 80)

                if result.rg_failures:
                    click.echo("\nResource Group Failures:")
                    for rg_fail in result.rg_failures:
                        click.echo(f"  {rg_fail.rg_name}: {rg_fail.error}")

                # Exit with success if any VMs succeeded
                if result.any_succeeded:
                    sys.exit(0)
                else:
                    sys.exit(1)

            except ProvisioningError as e:
                click.echo(f"\nPool provisioning failed completely: {e}", err=True)
                sys.exit(1)
            except Exception as e:
                click.echo(f"\nUnexpected error: {e}", err=True)
                sys.exit(1)

        exit_code = orchestrator.run()
        sys.exit(exit_code)


# Alias: 'vm' for 'new'
@main.command(name="vm")
@click.pass_context
@click.option("--repo", help="GitHub repository URL to clone", type=str)
@click.option("--vm-size", help="Azure VM size", type=str)
@click.option("--region", help="Azure region", type=str)
@click.option("--resource-group", "--rg", help="Azure resource group", type=str)
@click.option("--name", help="Custom VM name", type=str)
@click.option("--pool", help="Number of VMs to create in parallel", type=int)
@click.option("--no-auto-connect", help="Do not auto-connect via SSH", is_flag=True)
@click.option("--config", help="Config file path", type=click.Path())
def vm_command(ctx, **kwargs):
    """Alias for 'new' command. Provision a new Azure VM."""
    return ctx.invoke(new_command, **kwargs)


# Alias: 'create' for 'new'
@main.command(name="create")
@click.pass_context
@click.option("--repo", help="GitHub repository URL to clone", type=str)
@click.option("--vm-size", help="Azure VM size", type=str)
@click.option("--region", help="Azure region", type=str)
@click.option("--resource-group", "--rg", help="Azure resource group", type=str)
@click.option("--name", help="Custom VM name", type=str)
@click.option("--pool", help="Number of VMs to create in parallel", type=int)
@click.option("--no-auto-connect", help="Do not auto-connect via SSH", is_flag=True)
@click.option("--config", help="Config file path", type=click.Path())
def create_command(ctx, **kwargs):
    """Alias for 'new' command. Provision a new Azure VM."""
    return ctx.invoke(new_command, **kwargs)


@main.command(name="list")
@click.option("--resource-group", "--rg", help="Resource group to list VMs from", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--all", "show_all", help="Show all VMs (including stopped)", is_flag=True)
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
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
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
            SSHConfig(host=vm.public_ip, user="azureuser", key_path=ssh_key_pair.private_path)
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
@click.argument("vm_name", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def kill(vm_name: str, resource_group: Optional[str], config: Optional[str], force: bool):
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
            click.echo("\nVM Details:")
            click.echo(f"  Name:           {vm.name}")
            click.echo(f"  Resource Group: {vm.resource_group}")
            click.echo(f"  Status:         {vm.get_status_display()}")
            click.echo(f"  IP:             {vm.public_ip or 'N/A'}")
            click.echo(f"  Size:           {vm.vm_size or 'N/A'}")
            click.echo("\nThis will delete the VM and all associated resources (NICs, disks, IPs).")
            click.echo("This action cannot be undone.\n")

            confirm = input("Are you sure you want to delete this VM? [y/N]: ").lower()
            if confirm not in ["y", "yes"]:
                click.echo("Cancelled.")
                return

        # Delete VM
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


@main.command(name="destroy")
@click.argument("vm_name", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be deleted without actually deleting"
)
@click.option(
    "--delete-rg", is_flag=True, help="Delete the entire resource group (use with caution)"
)
def destroy(
    vm_name: str,
    resource_group: Optional[str],
    config: Optional[str],
    force: bool,
    dry_run: bool,
    delete_rg: bool,
):
    """Destroy a VM and optionally the entire resource group.

    This is an alias for the 'kill' command with additional options.
    Deletes the VM, NICs, disks, and public IPs.

    \b
    Examples:
        azlin destroy azlin-vm-12345
        azlin destroy my-vm --dry-run
        azlin destroy my-vm --delete-rg --force
        azlin destroy my-vm --rg my-resource-group
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # Handle --delete-rg option
        if delete_rg:
            if dry_run:
                click.echo(f"\n[DRY RUN] Would delete entire resource group: {rg}")
                click.echo(f"This would delete ALL resources in the group, not just '{vm_name}'")
                return

            # Show warning and confirmation
            if not force:
                click.echo(f"\nWARNING: You are about to delete the ENTIRE resource group: {rg}")
                click.echo(
                    f"This will delete ALL resources in the group, not just the VM '{vm_name}'!"
                )
                click.echo("\nThis action cannot be undone.\n")

                confirm = input("Type the resource group name to confirm deletion: ").strip()
                if confirm != rg:
                    click.echo("Cancelled. Resource group name did not match.")
                    return

            click.echo(f"\nDeleting resource group '{rg}'...")

            # Use Azure CLI to delete resource group
            import subprocess

            cmd = ["az", "group", "delete", "--name", rg, "--yes"]

            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=600, check=True
                )
                click.echo(f"\nSuccess! Resource group '{rg}' and all resources deleted.")
                return
            except subprocess.CalledProcessError as e:
                click.echo(f"\nError deleting resource group: {e.stderr}", err=True)
                sys.exit(1)
            except subprocess.TimeoutExpired:
                click.echo("\nError: Resource group deletion timed out.", err=True)
                sys.exit(1)

        # Handle dry-run for single VM
        if dry_run:
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
            return

        # Normal deletion (same as kill command)
        vm = VMManager.get_vm(vm_name, rg)

        if not vm:
            click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'.", err=True)
            sys.exit(1)

        # Show confirmation prompt unless --force
        if not force:
            click.echo("\nVM Details:")
            click.echo(f"  Name:           {vm.name}")
            click.echo(f"  Resource Group: {vm.resource_group}")
            click.echo(f"  Status:         {vm.get_status_display()}")
            click.echo(f"  IP:             {vm.public_ip or 'N/A'}")
            click.echo(f"  Size:           {vm.vm_size or 'N/A'}")
            click.echo("\nThis will delete the VM and all associated resources (NICs, disks, IPs).")
            click.echo("This action cannot be undone.\n")

            confirm = input("Are you sure you want to delete this VM? [y/N]: ").lower()
            if confirm not in ["y", "yes"]:
                click.echo("Cancelled.")
                return

        # Delete VM
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
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
@click.option("--prefix", default="azlin", help="Only delete VMs with this prefix")
def killall(resource_group: Optional[str], config: Optional[str], force: bool, prefix: str):
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
            if confirm not in ["y", "yes"]:
                click.echo("Cancelled.")
                return

        # Delete all VMs
        click.echo(f"\nDeleting {len(vms)} VM(s) in parallel...")

        summary = VMLifecycleManager.delete_all_vms(
            resource_group=rg, force=True, vm_prefix=prefix, max_workers=5
        )

        # Display results
        click.echo("\n" + "=" * 80)
        click.echo("Deletion Summary")
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
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--grouped", is_flag=True, help="Group output by VM instead of prefixing")
def ps(resource_group: Optional[str], config: Optional[str], grouped: bool):
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
            SSHConfig(host=vm.public_ip, user="azureuser", key_path=ssh_key_pair.private_path)
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


@main.command()
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--by-vm", is_flag=True, help="Show per-VM breakdown")
@click.option("--from", "from_date", help="Start date (YYYY-MM-DD)", type=str)
@click.option("--to", "to_date", help="End date (YYYY-MM-DD)", type=str)
@click.option("--estimate", is_flag=True, help="Show monthly cost estimate")
def cost(
    resource_group: Optional[str],
    config: Optional[str],
    by_vm: bool,
    from_date: Optional[str],
    to_date: Optional[str],
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
@click.option("--resource-group", "--rg", help="Resource group (required for VM name)", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--no-tmux", is_flag=True, help="Skip tmux session")
@click.option("--tmux-session", help="Tmux session name (default: vm_identifier)", type=str)
@click.option("--user", default="azureuser", help="SSH username (default: azureuser)", type=str)
@click.option("--key", help="SSH private key path", type=click.Path(exists=True))
@click.option("--no-reconnect", is_flag=True, help="Disable auto-reconnect on disconnect")
@click.option(
    "--max-retries", default=3, help="Maximum reconnection attempts (default: 3)", type=int
)
@click.argument("remote_command", nargs=-1, type=str)
def connect(
    vm_identifier: str,
    resource_group: Optional[str],
    config: Optional[str],
    no_tmux: bool,
    tmux_session: Optional[str],
    user: str,
    key: Optional[str],
    no_reconnect: bool,
    max_retries: int,
    remote_command: tuple,
):
    """Connect to existing VM via SSH.

    VM_IDENTIFIER can be either:
    - VM name (requires --resource-group or default config)
    - IP address (direct connection)

    Use -- to separate remote command from options.

    By default, auto-reconnect is ENABLED. If your SSH session disconnects,
    you will be prompted to reconnect. Use --no-reconnect to disable this.

    \b
    Examples:
        # Connect to VM by name
        azlin connect my-vm

        # Connect to VM by name with explicit resource group
        azlin connect my-vm --rg my-resource-group

        # Connect by IP address
        azlin connect 20.1.2.3

        # Connect without tmux
        azlin connect my-vm --no-tmux

        # Connect with custom tmux session name
        azlin connect my-vm --tmux-session dev

        # Connect and run command
        azlin connect my-vm -- ls -la

        # Connect with custom SSH user
        azlin connect my-vm --user myuser

        # Connect with custom SSH key
        azlin connect my-vm --key ~/.ssh/custom_key

        # Disable auto-reconnect
        azlin connect my-vm --no-reconnect

        # Set maximum reconnection attempts
        azlin connect my-vm --max-retries 5
    """
    try:
        # Parse remote command
        command = " ".join(remote_command) if remote_command else None

        # Convert key path to Path object
        key_path = Path(key).expanduser() if key else None

        # Get resource group from config if not specified
        if not VMConnector._is_valid_ip(vm_identifier):
            rg = ConfigManager.get_resource_group(resource_group, config)
            if not rg:
                click.echo(
                    "Error: Resource group required for VM name.\n"
                    "Use --resource-group or set default in ~/.azlin/config.toml",
                    err=True,
                )
                sys.exit(1)
        else:
            rg = resource_group

        # Connect to VM
        click.echo(f"Connecting to {vm_identifier}...")

        success = VMConnector.connect(
            vm_identifier=vm_identifier,
            resource_group=rg,
            use_tmux=not no_tmux,
            tmux_session=tmux_session,
            remote_command=command,
            ssh_user=user,
            ssh_key_path=key_path,
            enable_reconnect=not no_reconnect,
            max_reconnect_retries=max_retries,
        )

        sys.exit(0 if success else 1)

    except VMConnectorError as e:
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
        logger.exception("Unexpected error in connect command")
        sys.exit(1)


@main.command()
@click.argument("vm_name", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option(
    "--deallocate/--no-deallocate", default=True, help="Deallocate to save costs (default: yes)"
)
def stop(vm_name: str, resource_group: Optional[str], config: Optional[str], deallocate: bool):
    """Stop or deallocate a VM.

    Stopping a VM with --deallocate (default) fully releases compute resources
    and stops billing for the VM (storage charges still apply).

    \b
    Examples:
        azlin stop my-vm
        azlin stop my-vm --rg my-resource-group
        azlin stop my-vm --no-deallocate
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        click.echo(f"{'Deallocating' if deallocate else 'Stopping'} VM '{vm_name}'...")

        result = VMLifecycleController.stop_vm(
            vm_name=vm_name, resource_group=rg, deallocate=deallocate, no_wait=False
        )

        if result.success:
            click.echo(f"Success! {result.message}")
            if result.cost_impact:
                click.echo(f"Cost impact: {result.cost_impact}")
        else:
            click.echo(f"Error: {result.message}", err=True)
            sys.exit(1)

    except VMLifecycleControlError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("vm_name", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def start(vm_name: str, resource_group: Optional[str], config: Optional[str]):
    """Start a stopped or deallocated VM.

    \b
    Examples:
        azlin start my-vm
        azlin start my-vm --rg my-resource-group
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        click.echo(f"Starting VM '{vm_name}'...")

        result = VMLifecycleController.start_vm(vm_name=vm_name, resource_group=rg, no_wait=False)

        if result.success:
            click.echo(f"Success! {result.message}")
            if result.cost_impact:
                click.echo(f"Cost impact: {result.cost_impact}")
        else:
            click.echo(f"Error: {result.message}", err=True)
            sys.exit(1)

    except VMLifecycleControlError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--vm-name", help="VM name to sync to", type=str)
@click.option("--dry-run", help="Show what would be synced", is_flag=True)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def sync(
    vm_name: Optional[str], dry_run: bool, resource_group: Optional[str], config: Optional[str]
):
    """Sync ~/.azlin/home/ to VM home directory.

    Syncs local configuration files to remote VM for consistent
    development environment.

    \b
    Examples:
        azlin sync                    # Interactive VM selection
        azlin sync --vm-name myvm     # Sync to specific VM
        azlin sync --dry-run          # Show what would be synced
    """
    try:
        # Get SSH key
        ssh_key_pair = SSHKeyManager.ensure_key_exists()

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        # Get VM
        if vm_name:
            # Sync to specific VM
            if not rg:
                click.echo("Error: Resource group required for VM name.", err=True)
                click.echo("Use --resource-group or set default in ~/.azlin/config.toml", err=True)
                sys.exit(1)

            vm = VMManager.get_vm(vm_name, rg)
            if not vm:
                click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'.", err=True)
                sys.exit(1)

            if not vm.is_running():
                click.echo(f"Error: VM '{vm_name}' is not running.", err=True)
                sys.exit(1)

            if not vm.public_ip:
                click.echo(f"Error: VM '{vm_name}' has no public IP.", err=True)
                sys.exit(1)

            selected_vm = vm
        else:
            # Interactive selection
            if not rg:
                click.echo("Error: No resource group specified.", err=True)
                click.echo("Use --resource-group or set default in ~/.azlin/config.toml", err=True)
                sys.exit(1)

            vms = VMManager.list_vms(rg, include_stopped=False)
            vms = VMManager.filter_by_prefix(vms, "azlin")
            vms = [vm for vm in vms if vm.is_running() and vm.public_ip]

            if not vms:
                click.echo("No running VMs found.")
                sys.exit(1)

            if len(vms) == 1:
                selected_vm = vms[0]
                click.echo(f"Auto-selecting VM: {selected_vm.name}")
            else:
                # Show menu
                click.echo("\nSelect VM to sync to:")
                for idx, vm in enumerate(vms, 1):
                    click.echo(f"  {idx}. {vm.name} - {vm.public_ip}")

                choice = input("\nSelect VM (number): ").strip()
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(vms):
                        selected_vm = vms[idx]
                    else:
                        click.echo("Invalid selection", err=True)
                        sys.exit(1)
                except ValueError:
                    click.echo("Invalid input", err=True)
                    sys.exit(1)

        # Create SSH config
        ssh_config = SSHConfig(
            host=selected_vm.public_ip, user="azureuser", key_path=ssh_key_pair.private_path
        )

        # Sync
        click.echo(f"\nSyncing to {selected_vm.name} ({selected_vm.public_ip})...")

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

    except SecurityValidationError as e:
        click.echo("\nSecurity validation failed:", err=True)
        click.echo(str(e), err=True)
        click.echo("\nRemove sensitive files from ~/.azlin/home/ and try again.", err=True)
        sys.exit(1)

    except (RsyncError, HomeSyncError) as e:
        click.echo(f"\nSync failed: {e}", err=True)
        sys.exit(1)

    except (VMManagerError, ConfigError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    except KeyboardInterrupt:
        click.echo("\nCancelled by user.")
        sys.exit(130)

    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in sync command")
        sys.exit(1)


@main.command()
@click.argument("source")
@click.argument("destination")
@click.option("--dry-run", is_flag=True, help="Show what would be transferred")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def cp(
    source: str,
    destination: str,
    dry_run: bool,
    resource_group: Optional[str],
    config: Optional[str],
):
    """Copy files between local machine and VMs.

    Supports bidirectional file transfer with security-hardened path validation.

    Arguments support session:path notation:
    - Local path: myfile.txt
    - Remote path: vm1:~/myfile.txt

    \b
    Examples:
        azlin cp myfile.txt vm1:~/          # Local to remote
        azlin cp vm1:~/data.txt ./          # Remote to local
        azlin cp vm1:~/src vm2:~/dest       # Remote to remote (not supported)
        azlin cp --dry-run test.txt vm1:~/  # Show transfer plan
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        # Get SSH key
        ssh_key_pair = SSHKeyManager.ensure_key_exists()

        # Parse source
        source_session_name, source_path_str = SessionManager.parse_session_path(source)

        if source_session_name is None:
            # Local source
            source_path = PathParser.parse_and_validate(source_path_str, allow_absolute=False)
            source_endpoint = TransferEndpoint(path=source_path, session=None)
        else:
            # Remote source
            if not rg:
                click.echo("Error: Resource group required for remote sessions.", err=True)
                click.echo("Use --resource-group or set default in ~/.azlin/config.toml", err=True)
                sys.exit(1)

            vm_session = SessionManager.get_vm_session(
                source_session_name, VMManager, ConfigManager
            )

            # Parse remote path (allow relative to home)
            source_path = PathParser.parse_and_validate(
                source_path_str, allow_absolute=True, base_dir=Path("/home") / vm_session.user
            )

            source_endpoint = TransferEndpoint(path=source_path, session=vm_session)

        # Parse destination
        dest_session_name, dest_path_str = SessionManager.parse_session_path(destination)

        if dest_session_name is None:
            # Local destination
            dest_path = PathParser.parse_and_validate(dest_path_str, allow_absolute=False)
            dest_endpoint = TransferEndpoint(path=dest_path, session=None)
        else:
            # Remote destination
            if not rg:
                click.echo("Error: Resource group required for remote sessions.", err=True)
                click.echo("Use --resource-group or set default in ~/.azlin/config.toml", err=True)
                sys.exit(1)

            vm_session = SessionManager.get_vm_session(dest_session_name, VMManager, ConfigManager)

            # Parse remote path (allow relative to home)
            dest_path = PathParser.parse_and_validate(
                dest_path_str, allow_absolute=True, base_dir=Path("/home") / vm_session.user
            )

            dest_endpoint = TransferEndpoint(path=dest_path, session=vm_session)

        # Display transfer plan
        click.echo("\nTransfer Plan:")
        if source_endpoint.session is None:
            click.echo(f"  Source: {source_endpoint.path} (local)")
        else:
            click.echo(f"  Source: {source_endpoint.session.name}:{source_endpoint.path}")

        if dest_endpoint.session is None:
            click.echo(f"  Dest:   {dest_endpoint.path} (local)")
        else:
            click.echo(f"  Dest:   {dest_endpoint.session.name}:{dest_endpoint.path}")

        click.echo()

        if dry_run:
            click.echo("Dry run - no files transferred")
            return

        # Execute transfer
        result = FileTransfer.transfer(source_endpoint, dest_endpoint)

        if result.success:
            click.echo(
                f"Success! Transferred {result.files_transferred} files "
                f"({result.bytes_transferred / 1024:.1f} KB) "
                f"in {result.duration_seconds:.1f}s"
            )
        else:
            click.echo("Transfer failed:", err=True)
            for error in result.errors:
                click.echo(f"  {error}", err=True)
            sys.exit(1)

    except FileTransferError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except VMManagerError as e:
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
        logger.exception("Unexpected error in cp command")
        sys.exit(1)


@main.command()
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--vm", help="Show status for specific VM only", type=str)
def status(resource_group: Optional[str], config: Optional[str], vm: Optional[str]):
    """Show status of VMs in resource group.

    Displays detailed status information including power state and IP addresses.

    \b
    Examples:
        azlin status
        azlin status --rg my-resource-group
        azlin status --vm my-vm
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # List VMs
        vms = VMManager.list_vms(rg, include_stopped=True)

        if vm:
            # Filter to specific VM
            vms = [v for v in vms if v.name == vm]
            if not vms:
                click.echo(f"Error: VM '{vm}' not found in resource group '{rg}'.", err=True)
                sys.exit(1)
        else:
            # Filter to azlin VMs
            vms = VMManager.filter_by_prefix(vms, "azlin")

        vms = VMManager.sort_by_created_time(vms)

        if not vms:
            click.echo("No VMs found.")
            return

        # Display status table
        click.echo(f"\nVM Status in resource group: {rg}")
        click.echo("=" * 100)
        click.echo(f"{'NAME':<35} {'POWER STATE':<18} {'IP':<16} {'REGION':<15} {'SIZE':<15}")
        click.echo("=" * 100)

        for v in vms:
            power_state = v.power_state if v.power_state else "Unknown"
            ip = v.public_ip or "N/A"
            size = v.vm_size or "N/A"
            location = v.location or "N/A"
            click.echo(f"{v.name:<35} {power_state:<18} {ip:<16} {location:<15} {size:<15}")

        click.echo("=" * 100)
        click.echo(f"\nTotal: {len(vms)} VMs")

        # Summary stats
        running = sum(1 for v in vms if v.is_running())
        stopped = len(vms) - running
        click.echo(f"Running: {running}, Stopped/Deallocated: {stopped}\n")

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("vm_name", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--boot", is_flag=True, help="Show boot logs")
@click.option("--kernel", is_flag=True, help="Show kernel logs")
@click.option("--app", "--service", "service", help="Show application logs for service", type=str)
@click.option("--follow", "-f", is_flag=True, help="Follow logs in real-time")
@click.option("--since", help='Show logs since time (e.g., "1 hour ago", "2024-01-01")', type=str)
@click.option("--lines", "-n", default=100, help="Number of lines to show (default: 100)", type=int)
@click.option("--timeout", default=30, help="SSH timeout in seconds (default: 30)", type=int)
def logs(
    vm_name: str,
    resource_group: Optional[str],
    config: Optional[str],
    boot: bool,
    kernel: bool,
    service: Optional[str],
    follow: bool,
    since: Optional[str],
    lines: int,
    timeout: int,
):
    """View VM logs without SSH connection.

    Retrieves logs from a running VM using journalctl via SSH.
    Supports system logs, boot logs, kernel logs, and application logs.

    \b
    Examples:
        # View system logs
        azlin logs my-vm

        # View boot logs
        azlin logs my-vm --boot

        # View kernel logs
        azlin logs my-vm --kernel

        # View application logs
        azlin logs my-vm --app nginx

        # Follow logs in real-time
        azlin logs my-vm --follow

        # Show logs from last hour
        azlin logs my-vm --since "1 hour ago"

        # Show last 50 lines
        azlin logs my-vm --lines 50

        # Combine options
        azlin logs my-vm --boot --since "today" --lines 200
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            click.echo("Use --resource-group or set default in ~/.azlin/config.toml", err=True)
            sys.exit(1)

        # Handle follow mode
        if follow:
            # Determine log type for follow
            if boot:
                log_type = LogType.BOOT
            elif kernel:
                log_type = LogType.KERNEL
            elif service:
                log_type = LogType.APP
            else:
                log_type = LogType.SYSTEM

            click.echo(f"Following {log_type.value} logs from {vm_name}...")
            click.echo("Press Ctrl+C to stop\n")

            exit_code = LogViewer.follow_logs(
                vm_name=vm_name, resource_group=rg, log_type=log_type, since=since, service=service
            )
            sys.exit(exit_code)

        # Regular log retrieval
        click.echo(f"Retrieving logs from {vm_name}...\n")

        # Determine which logs to retrieve
        if boot:
            result = LogViewer.get_boot_logs(
                vm_name=vm_name, resource_group=rg, lines=lines, since=since, timeout=timeout
            )
            log_type_name = "Boot Logs"
        elif kernel:
            result = LogViewer.get_kernel_logs(
                vm_name=vm_name, resource_group=rg, lines=lines, since=since, timeout=timeout
            )
            log_type_name = "Kernel Logs"
        elif service:
            result = LogViewer.get_app_logs(
                vm_name=vm_name,
                resource_group=rg,
                service=service,
                lines=lines,
                since=since,
                timeout=timeout,
            )
            log_type_name = f"Application Logs ({service})"
        else:
            # Default to system logs
            result = LogViewer.get_system_logs(
                vm_name=vm_name, resource_group=rg, lines=lines, since=since, timeout=timeout
            )
            log_type_name = "System Logs"

        # Display results
        if result.success:
            click.echo("=" * 80)
            click.echo(f"{log_type_name} - {vm_name}")
            if since:
                click.echo(f"Since: {since}")
            click.echo(f"Lines: {result.line_count}")
            click.echo("=" * 80)
            click.echo(result.logs)
            click.echo("=" * 80)
        else:
            click.echo(f"Error: {result.error_message}", err=True)
            sys.exit(1)

    except LogViewerError as e:
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
        logger.exception("Unexpected error in logs command")
        sys.exit(1)


if __name__ == "__main__":
    main()


__all__ = ["main", "CLIOrchestrator", "AzlinError"]
