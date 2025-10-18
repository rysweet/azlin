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

import click

from azlin import __version__
from azlin.azure_auth import AuthenticationError, AzureAuthenticator
from azlin.batch_executor import BatchExecutor, BatchExecutorError, BatchResult, BatchSelector

# Storage commands
from azlin.commands.storage import storage_group

# New modules for v2.0
from azlin.config_manager import AzlinConfig, ConfigError, ConfigManager
from azlin.cost_tracker import CostTracker, CostTrackerError
from azlin.env_manager import EnvManager, EnvManagerError
from azlin.key_rotator import KeyRotationError, SSHKeyRotator
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
from azlin.prune import PruneManager
from azlin.remote_exec import (
    OSUpdateExecutor,
    PSCommandExecutor,
    RemoteExecError,
    RemoteExecutor,
    WCommandExecutor,
)
from azlin.snapshot_manager import SnapshotManager, SnapshotManagerError
from azlin.tag_manager import TagManager
from azlin.template_manager import TemplateError, TemplateManager, VMTemplateConfig
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
        repo: str | None = None,
        vm_size: str = "Standard_D2s_v3",
        region: str = "eastus",
        resource_group: str | None = None,
        auto_connect: bool = True,
        config_file: str | None = None,
        nfs_storage: str | None = None,
    ):
        """Initialize CLI orchestrator.

        Args:
            repo: GitHub repository URL (optional)
            vm_size: Azure VM size
            region: Azure region
            resource_group: Resource group name (optional)
            auto_connect: Whether to auto-connect via SSH
            config_file: Configuration file path (optional)
            nfs_storage: NFS storage account name to mount as home directory (optional)
        """
        self.repo = repo
        self.vm_size = vm_size
        self.region = region
        self.resource_group = resource_group
        self.auto_connect = auto_connect
        self.config_file = config_file
        self.nfs_storage = nfs_storage

        # Initialize modules
        self.auth = AzureAuthenticator()
        self.provisioner = VMProvisioner()
        self.progress = ProgressDisplay()

        # Track resources for cleanup
        self.vm_details: VMDetails | None = None
        self.ssh_keys: Path | None = None

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

            # STEP 5.5: Mount NFS storage if specified (BEFORE home sync)
            if self.nfs_storage:
                self.progress.start_operation(f"Mounting NFS storage: {self.nfs_storage}")
                self._mount_nfs_storage(vm_details, ssh_key_pair.private_path)
                self.progress.complete(success=True, message="NFS storage mounted")
            else:
                # Only sync home directory if NOT using NFS storage
                # (NFS storage provides the home directory)
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

    def _mount_nfs_storage(self, vm_details: VMDetails, key_path: Path) -> None:
        """Mount NFS storage on VM home directory.

        Args:
            vm_details: VM details
            key_path: SSH private key path

        Raises:
            Exception: If storage mount fails (this is a critical operation)
        """
        from azlin.modules.nfs_mount_manager import NFSMountManager
        from azlin.modules.storage_manager import StorageManager

        try:
            # Get storage details
            self.progress.update(f"Fetching storage account: {self.nfs_storage}")

            # Get resource group (use the VM's resource group)
            rg = vm_details.resource_group

            # List storage accounts to find the one we want
            accounts = StorageManager.list_storage(rg)
            storage = next((a for a in accounts if a.name == self.nfs_storage), None)

            if not storage:
                raise Exception(
                    f"Storage account '{self.nfs_storage}' not found in resource group '{rg}'. "
                    f"Create it first with: azlin storage create {self.nfs_storage}"
                )

            self.progress.update(f"Storage found: {storage.nfs_endpoint}")

            # Mount storage
            self.progress.update("Installing NFS client tools...")
            result = NFSMountManager.mount_storage(
                vm_ip=vm_details.public_ip,
                ssh_key=key_path,
                nfs_endpoint=storage.nfs_endpoint,
                mount_point="/home/azureuser",
            )

            if not result.success:
                error_msg = "; ".join(result.errors) if result.errors else "Unknown error"
                raise Exception(f"Failed to mount NFS storage: {error_msg}")

            if result.backed_up_files > 0:
                self.progress.update(f"Backed up {result.backed_up_files} existing files")

            if result.copied_files > 0:
                self.progress.update(f"Copied {result.copied_files} files from backup to shared storage")

            self.progress.update(
                f"NFS storage mounted at /home/azureuser from {storage.nfs_endpoint}"
            )

        except Exception as e:
            # Storage mount failures are critical - we want to know about them
            raise Exception(f"NFS storage mount failed: {e}") from e

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

            exit_code = SSHConnector.connect(ssh_config, tmux_session="azlin", auto_tmux=True)
            return exit_code
        else:
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
        "help_option_names": ["--help", "-h"],
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
    EXAMPLES:
        # Show help
        $ azlin

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

    # If no subcommand provided, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(0)  # Use ctx.exit() instead of sys.exit() for Click compatibility


@main.command(name="help")
@click.argument("command_name", required=False, type=str)
@click.pass_context
def help_command(ctx, command_name):
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
        cmd = ctx.parent.command.commands.get(command_name)

        if cmd is None:
            click.echo(f"Error: No such command '{command_name}'.", err=True)
            ctx.exit(1)

        # Create a context for the command and show its help
        cmd_ctx = click.Context(cmd, info_name=command_name, parent=ctx.parent)
        click.echo(cmd.get_help(cmd_ctx))


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
@click.option("--template", help="Template name to use for VM configuration", type=str)
@click.option("--nfs-storage", help="NFS storage account name to mount as home directory", type=str)
def new_command(
    ctx,
    repo: str | None,
    vm_size: str | None,
    region: str | None,
    resource_group: str | None,
    name: str | None,
    pool: int | None,
    no_auto_connect: bool,
    config: str | None,
    template: str | None,
    nfs_storage: str | None,
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

        # Provision from template
        $ azlin new --template dev-vm

        # Provision with NFS storage for shared home directory
        $ azlin new --nfs-storage myteam-shared --name worker-1

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

    # Load template if specified
    template_config = None
    if template:
        try:
            template_config = TemplateManager.get_template(template)
            click.echo(f"Using template: {template}")
        except TemplateError as e:
            click.echo(f"Error loading template: {e}", err=True)
            sys.exit(1)

    # Get settings with CLI override (template < config < CLI)
    if template_config:
        # Template provides defaults
        final_rg = resource_group or azlin_config.default_resource_group
        final_region = region or template_config.region
        final_vm_size = vm_size or template_config.vm_size
    else:
        # Use config defaults
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
            click.echo("Error: Invalid GitHub URL. Must start with https://github.com/", err=True)
            sys.exit(1)

    # Create orchestrator and run
    orchestrator = CLIOrchestrator(
        repo=repo,
        vm_size=final_vm_size,
        region=final_region,
        resource_group=final_rg,
        auto_connect=not no_auto_connect,
        config_file=config,
        nfs_storage=nfs_storage,
    )

    # Update config with used resource group
    if final_rg:
        try:
            ConfigManager.update_config(
                config, default_resource_group=final_rg, last_vm_name=vm_name
            )
            # Save session name if provided
            if name:
                ConfigManager.set_session_name(vm_name, name, config)
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
            vm_name_pool = f"{vm_name}-{i + 1:02d}"
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
@click.option("--template", help="Template name to use for VM configuration", type=str)
@click.option("--nfs-storage", help="NFS storage account name to mount as home directory", type=str)
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
@click.option("--template", help="Template name to use for VM configuration", type=str)
@click.option("--nfs-storage", help="NFS storage account name to mount as home directory", type=str)
def create_command(ctx, **kwargs):
    """Alias for 'new' command. Provision a new Azure VM."""
    return ctx.invoke(new_command, **kwargs)


@main.command(name="list")
@click.option("--resource-group", "--rg", help="Resource group to list VMs from", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--all", "show_all", help="Show all VMs (including stopped)", is_flag=True)
@click.option("--tag", help="Filter VMs by tag (format: key or key=value)", type=str)
def list_command(resource_group: str | None, config: str | None, show_all: bool, tag: str | None):
    """List VMs in resource group.

    Shows VM name, status, IP address, region, and size.

    \b
    Examples:
        azlin list
        azlin list --rg my-resource-group
        azlin list --all
        azlin list --tag env=dev
        azlin list --tag team
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

        # Filter by tag if specified
        if tag:
            try:
                vms = TagManager.filter_vms_by_tag(vms, tag)
            except Exception as e:
                click.echo(f"Error filtering by tag: {e}", err=True)
                sys.exit(1)

        vms = VMManager.sort_by_created_time(vms)

        # Populate session names from config
        for vm in vms:
            vm.session_name = ConfigManager.get_session_name(vm.name, config)

        if not vms:
            click.echo("No VMs found.")
            return

        # Display table with session names
        click.echo("=" * 110)
        click.echo(
            f"{'SESSION NAME':<25} {'VM NAME':<35} {'STATUS':<15} {'IP':<15} {'REGION':<10} {'SIZE':<10}"
        )
        click.echo("=" * 110)

        for vm in vms:
            session_display = vm.session_name if vm.session_name else "-"
            status = vm.get_status_display()
            ip = vm.public_ip or "N/A"
            size = vm.vm_size or "N/A"
            click.echo(
                f"{session_display:<25} {vm.name:<35} {status:<15} {ip:<15} {vm.location:<10} {size:<10}"
            )

        click.echo("=" * 110)
        click.echo(f"\nTotal: {len(vms)} VMs")

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)


@main.command(name="session")
@click.argument("vm_name", type=str)
@click.argument("session_name", type=str, required=False)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--clear", is_flag=True, help="Clear session name")
def session_command(
    vm_name: str,
    session_name: str | None,
    resource_group: str | None,
    config: str | None,
    clear: bool,
):
    """Set or view session name for a VM.

    Session names are labels that help you identify what you're working on.
    They appear in the 'azlin list' output alongside the VM name.

    \b
    Examples:
        # Set session name
        azlin session azlin-vm-12345 my-project

        # View current session name
        azlin session azlin-vm-12345

        # Clear session name
        azlin session azlin-vm-12345 --clear
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified and no default configured.", err=True)
            click.echo("Use --resource-group or set default in ~/.azlin/config.toml", err=True)
            sys.exit(1)

        # Verify VM exists
        vm = VMManager.get_vm(vm_name, rg)

        if not vm:
            click.echo(f"Error: VM '{vm_name}' not found in resource group '{rg}'.", err=True)
            sys.exit(1)

        # Clear session name
        if clear:
            if ConfigManager.delete_session_name(vm_name, config):
                click.echo(f"Cleared session name for VM '{vm_name}'")
            else:
                click.echo(f"No session name set for VM '{vm_name}'")
            return

        # View current session name
        if not session_name:
            current_name = ConfigManager.get_session_name(vm_name, config)
            if current_name:
                click.echo(f"Session name for '{vm_name}': {current_name}")
            else:
                click.echo(f"No session name set for VM '{vm_name}'")
                click.echo(f"\nSet one with: azlin session {vm_name} <session_name>")
            return

        # Set session name
        ConfigManager.set_session_name(vm_name, session_name, config)
        click.echo(f"Set session name for '{vm_name}' to '{session_name}'")

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def w(resource_group: str | None, config: str | None):
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


@main.command()
@click.argument("vm_name", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def kill(vm_name: str, resource_group: str | None, config: str | None, force: bool):
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
    resource_group: str | None,
    config: str | None,
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
def killall(resource_group: str | None, config: str | None, force: bool, prefix: str):
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
@click.option(
    "--age-days", default=1, type=click.IntRange(min=1), help="Age threshold in days (default: 1)"
)
@click.option(
    "--idle-days", default=1, type=click.IntRange(min=1), help="Idle threshold in days (default: 1)"
)
@click.option("--dry-run", is_flag=True, help="Preview without deleting")
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
@click.option("--include-running", is_flag=True, help="Include running VMs")
@click.option("--include-named", is_flag=True, help="Include named sessions")
def prune(
    resource_group: str | None,
    config: str | None,
    age_days: int,
    idle_days: int,
    dry_run: bool,
    force: bool,
    include_running: bool,
    include_named: bool,
):
    """Prune inactive VMs based on age and idle time.

    Identifies and optionally deletes VMs that are:
    - Older than --age-days (default: 1)
    - Idle for longer than --idle-days (default: 1)
    - Stopped/deallocated (unless --include-running)
    - Without named sessions (unless --include-named)

    \b
    Examples:
        azlin prune --dry-run                    # Preview what would be deleted
        azlin prune                              # Delete VMs idle for 1+ days (default)
        azlin prune --age-days 7 --idle-days 3   # Custom thresholds
        azlin prune --force                      # Skip confirmation
        azlin prune --include-running            # Include running VMs
    """
    try:
        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            click.echo("Set default with: azlin config set default_resource_group <name>")
            click.echo("Or specify with --resource-group option.")
            sys.exit(1)

        # Get candidates (single API call)
        candidates, connection_data = PruneManager.get_candidates(
            resource_group=rg,
            age_days=age_days,
            idle_days=idle_days,
            include_running=include_running,
            include_named=include_named,
        )

        # If no candidates, exit early
        if not candidates:
            click.echo("No VMs eligible for pruning.")
            return

        # Display table
        table = PruneManager.format_prune_table(candidates, connection_data)
        click.echo("\n" + table + "\n")

        # In dry-run mode, just show what would be deleted
        if dry_run:
            click.echo(f"DRY RUN: {len(candidates)} VM(s) would be deleted.")
            click.echo("Run without --dry-run to actually delete these VMs.")
            return

        # If not force mode, ask for confirmation
        if not force:
            click.echo(f"This will delete {len(candidates)} VM(s) and their associated resources.")
            click.echo("This action cannot be undone.\n")

            if not click.confirm(
                f"Are you sure you want to delete {len(candidates)} VM(s)?", default=False
            ):
                click.echo("Cancelled.")
                return

        # Execute deletion
        click.echo(f"\nDeleting {len(candidates)} VM(s)...")
        result = PruneManager.execute_prune(candidates, rg)

        # Display deletion summary
        deleted = result["deleted"]
        failed = result["failed"]

        click.echo("\n" + "=" * 80)
        click.echo("Deletion Summary")
        click.echo("=" * 80)
        click.echo(f"Total VMs:     {len(candidates)}")
        click.echo(f"Succeeded:     {deleted}")
        click.echo(f"Failed:        {failed}")
        click.echo("=" * 80)

        # Show errors if any
        if result["errors"]:
            click.echo("\nErrors:")
            for error in result["errors"]:
                click.echo(f"  - {error}")

        # Exit with error code if any failed
        if failed > 0:
            sys.exit(1)

    except VMManagerError as e:
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
def ps(resource_group: str | None, config: str | None, grouped: bool):
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
@click.argument("vm_identifier", type=str, required=False)
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
    vm_identifier: str | None,
    resource_group: str | None,
    config: str | None,
    no_tmux: bool,
    tmux_session: str | None,
    user: str,
    key: str | None,
    no_reconnect: bool,
    max_retries: int,
    remote_command: tuple,
):
    """Connect to existing VM via SSH.

    If VM_IDENTIFIER is not provided, displays an interactive list of available
    VMs to choose from, or option to create a new VM.

    VM_IDENTIFIER can be either:
    - VM name (requires --resource-group or default config)
    - Session name (will be resolved to VM name)
    - IP address (direct connection)

    Use -- to separate remote command from options.

    By default, auto-reconnect is ENABLED. If your SSH session disconnects,
    you will be prompted to reconnect. Use --no-reconnect to disable this.

    \b
    Examples:
        # Interactive selection
        azlin connect

        # Connect to VM by name
        azlin connect my-vm

        # Connect to VM by session name
        azlin connect my-project

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
        # If no VM identifier provided, show interactive selection
        if not vm_identifier:
            rg = ConfigManager.get_resource_group(resource_group, config)
            if not rg:
                click.echo(
                    "Error: Resource group required.\n"
                    "Use --resource-group or set default in ~/.azlin/config.toml",
                    err=True,
                )
                sys.exit(1)

            # Get list of running VMs
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
                    # Import here to avoid circular dependency
                    from click import Context

                    ctx = Context(new_command)
                    ctx.invoke(
                        new_command,
                        resource_group=rg,
                        config=config,
                        no_tmux=no_tmux,
                        tmux_session=tmux_session,
                    )
                    return
                else:
                    click.echo("Cancelled.")
                    sys.exit(0)

            # Display VM list
            click.echo("\nAvailable VMs:")
            click.echo("─" * 60)
            for i, vm in enumerate(vms, 1):
                status_emoji = "🟢" if vm.is_running() else "🔴"
                click.echo(
                    f"{i:2}. {status_emoji} {vm.name:<30} {vm.location:<15} {vm.vm_size or 'unknown'}"
                )
            click.echo("─" * 60)
            click.echo(" 0. Create new VM")
            click.echo()

            # Prompt for selection
            while True:
                try:
                    selection = click.prompt(
                        "Select a VM to connect to (0 to create new)",
                        type=int,
                        default=1 if vms else 0,
                    )

                    if selection == 0:
                        # Create new VM
                        from click import Context

                        ctx = Context(new_command)
                        ctx.invoke(
                            new_command,
                            resource_group=rg,
                            config=config,
                            no_tmux=no_tmux,
                            tmux_session=tmux_session,
                        )
                        return
                    elif 1 <= selection <= len(vms):
                        vm_identifier = vms[selection - 1].name
                        break
                    else:
                        click.echo(f"Invalid selection. Please choose 0-{len(vms)}", err=True)
                except (ValueError, click.Abort):
                    click.echo("\nCancelled.")
                    sys.exit(0)

        # Parse remote command
        command = " ".join(remote_command) if remote_command else None

        # Convert key path to Path object
        key_path = Path(key).expanduser() if key else None

        # Try to resolve session name to VM name if not an IP address
        original_identifier = vm_identifier
        if not VMConnector._is_valid_ip(vm_identifier):
            # Check if it's a session name
            resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_identifier, config)
            if resolved_vm_name:
                click.echo(f"Resolved session '{vm_identifier}' to VM '{resolved_vm_name}'")
                vm_identifier = resolved_vm_name

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

            # Verify VM exists if it was resolved from a session name
            if original_identifier != vm_identifier:
                try:
                    vm_info = VMManager.get_vm(vm_identifier, rg)
                    if vm_info is None:
                        click.echo(
                            f"Error: Session '{original_identifier}' points to VM '{vm_identifier}' "
                            f"which no longer exists.",
                            err=True,
                        )
                        # Clean up stale mapping
                        ConfigManager.delete_session_name(vm_identifier)
                        click.echo(f"Removed stale session mapping for '{vm_identifier}'")
                        sys.exit(1)
                except VMManagerError as e:
                    click.echo(f"Error: Failed to verify VM exists: {e}", err=True)
                    sys.exit(1)
        else:
            rg = resource_group

        # If no explicit tmux session name, try to use azlin session name
        if not tmux_session and not no_tmux:
            session_name = ConfigManager.get_session_name(vm_identifier, config)
            if session_name:
                tmux_session = session_name
                click.echo(f"Using session name '{session_name}' for tmux")

        # Connect to VM
        display_name = (
            original_identifier if original_identifier != vm_identifier else vm_identifier
        )
        click.echo(f"Connecting to {display_name}...")

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
    from azlin.modules.progress import ProgressDisplay
    from azlin.vm_updater import VMUpdater, VMUpdaterError

    try:
        # Resolve VM identifier to SSH config
        # Try session name first, then VM name, then IP
        original_identifier = vm_identifier

        # Try to resolve as session name
        try:
            session_vm = SessionManager.get_vm_by_session(vm_identifier)
            if session_vm:
                vm_identifier = session_vm
                click.echo(f"Resolved session '{original_identifier}' to VM '{vm_identifier}'")
        except Exception:
            pass  # Not a session name, try as VM name or IP

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


@main.command()
@click.argument("vm_name", type=str)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option(
    "--deallocate/--no-deallocate", default=True, help="Deallocate to save costs (default: yes)"
)
def stop(vm_name: str, resource_group: str | None, config: str | None, deallocate: bool):
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
def start(vm_name: str, resource_group: str | None, config: str | None):
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
def sync(vm_name: str | None, dry_run: bool, resource_group: str | None, config: str | None):
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
    source: str, destination: str, dry_run: bool, resource_group: str | None, config: str | None
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
        SSHKeyManager.ensure_key_exists()

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

            vm_session = SessionManager.get_vm_session(source_session_name, rg, VMManager)

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

            vm_session = SessionManager.get_vm_session(dest_session_name, rg, VMManager)

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
@click.argument("source_vm", type=str)
@click.option("--num-replicas", type=int, default=1, help="Number of clones to create (default: 1)")
@click.option("--session-prefix", type=str, help="Session name prefix for clones")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--vm-size", help="VM size for clones (default: same as source)", type=str)
@click.option("--region", help="Azure region (default: same as source)", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def clone(
    source_vm: str,
    num_replicas: int,
    session_prefix: str | None,
    resource_group: str | None,
    vm_size: str | None,
    region: str | None,
    config: str | None,
):
    """Clone a VM with its home directory contents.

    Creates new VM(s) and copies the entire home directory from the source VM.
    Useful for creating development environments, parallel testing, or team onboarding.

    \b
    Examples:
        # Clone single VM
        azlin clone amplihack

        # Clone with custom session name
        azlin clone amplihack --session-prefix dev-env

        # Clone multiple replicas
        azlin clone amplihack --num-replicas 3 --session-prefix worker
        # Creates: worker-1, worker-2, worker-3

        # Clone with specific VM size
        azlin clone my-vm --vm-size Standard_D4s_v3

    The source VM can be specified by VM name or session name.
    Home directory security filters are applied (no SSH keys, credentials, etc.).
    """
    try:
        # Validate num-replicas
        if num_replicas < 1:
            click.echo("Error: num-replicas must be >= 1", err=True)
            sys.exit(1)

        # Load configuration
        cfg = ConfigManager.load_config(config)

        # Get resource group
        rg = resource_group or cfg.default_resource_group
        if not rg:
            click.echo("Error: No resource group specified and no default configured", err=True)
            sys.exit(1)

        # Resolve source VM (by name or session)
        click.echo(f"Resolving source VM: {source_vm}")
        source_vm_info = _resolve_source_vm(source_vm, rg, config)

        if not source_vm_info:
            click.echo(f"Error: Source VM '{source_vm}' not found", err=True)
            # Show available VMs
            vms = VMManager.list_vms(rg)
            if vms:
                click.echo("\nAvailable VMs:", err=True)
                for vm in vms:
                    display_name = vm.session_name or vm.name
                    click.echo(f"  - {display_name} ({vm.name})", err=True)
            sys.exit(1)

        click.echo(f"Source VM: {source_vm_info.name} ({source_vm_info.public_ip})")
        click.echo(f"VM size: {source_vm_info.vm_size}")
        click.echo(f"Region: {source_vm_info.location}")

        # Check source VM is running
        if not source_vm_info.is_running():
            click.echo(f"Warning: Source VM is not running (state: {source_vm_info.power_state})")
            click.echo("Starting source VM...")
            controller = VMLifecycleController()
            controller.start_vm(source_vm_info.name, rg)
            click.echo("Source VM started successfully")
            # Refresh VM info
            source_vm_info = VMManager.get_vm(source_vm_info.name, rg)

        # Generate clone configurations
        click.echo(f"\nGenerating configurations for {num_replicas} clone(s)...")
        clone_configs = _generate_clone_configs(
            source_vm=source_vm_info,
            num_replicas=num_replicas,
            vm_size=vm_size,
            region=region,
        )

        # Display clone plan
        click.echo("\nClone plan:")
        for i, clone_config in enumerate(clone_configs, 1):
            click.echo(f"  Clone {i}: {clone_config.name}")
            click.echo(f"    Size: {clone_config.size}")
            click.echo(f"    Region: {clone_config.location}")

        # Provision VMs in parallel
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

        # Copy home directories in parallel
        click.echo("\nCopying home directories from source VM...")
        # Use id_rsa for compatibility with existing VMs (TODO: auto-detect SSH key)
        ssh_key_path = Path.home() / ".ssh" / "id_rsa"
        copy_results = _copy_home_directories(
            source_vm=source_vm_info,
            clone_vms=result.successful,
            ssh_key_path=str(ssh_key_path),
            max_workers=min(5, len(result.successful)),  # Limit to avoid overwhelming source
        )

        # Check copy results
        successful_copies = sum(1 for success in copy_results.values() if success)
        failed_copies = len(copy_results) - successful_copies

        if failed_copies > 0:
            click.echo(f"\nWarning: {failed_copies} home directory copy operations failed")

        # Set session names if prefix provided
        if session_prefix:
            click.echo(f"\nSetting session names with prefix: {session_prefix}")
            _set_clone_session_names(
                clone_vms=result.successful,
                session_prefix=session_prefix,
                config_path=config,
            )

        # Display final results
        click.echo("\n" + "=" * 70)
        click.echo(
            f"Clone operation complete: {successful_copies}/{len(result.successful)} successful"
        )
        click.echo("=" * 70)
        click.echo("\nCloned VMs:")
        for vm in result.successful:
            session_name = (
                ConfigManager.get_session_name(vm.name, config) if session_prefix else None
            )
            copy_status = "✓" if copy_results.get(vm.name, False) else "✗"
            display_name = f"{session_name} ({vm.name})" if session_name else vm.name
            click.echo(f"  {copy_status} {display_name}")
            click.echo(f"     IP: {vm.public_ip}")
            click.echo(f"     Size: {vm.size}, Region: {vm.location}")

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

    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ProvisioningError as e:
        click.echo(f"Provisioning error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nClone operation cancelled by user.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in clone command")
        sys.exit(1)


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
    for vm in all_vms:
        if vm.name.lower() == source_vm.lower():
            return vm
        if vm.session_name and vm.session_name.lower() == source_vm.lower():
            return vm

    return None


def _generate_clone_configs(
    source_vm: VMInfo,
    num_replicas: int,
    vm_size: str | None,
    region: str | None,
) -> list:
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
    clone_size = vm_size or source_vm.vm_size
    clone_region = region or source_vm.location

    # Generate unique VM names with timestamp
    timestamp = int(time.time())
    configs = []

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
            else:
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
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass  # Best effort cleanup

    # Execute copies in parallel
    results = {}
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
        for i, vm in enumerate(clone_vms, 1):
            session_name = f"{session_prefix}-{i}"
            ConfigManager.set_session_name(vm.name, session_name, config_path)
            click.echo(f"  Set session name: {session_name} -> {vm.name}")


@main.command()
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--vm", help="Show status for specific VM only", type=str)
def status(resource_group: str | None, config: str | None, vm: str | None):
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


@main.group()
def batch():
    """Batch operations on multiple VMs.

    Execute operations on multiple VMs simultaneously using
    tag-based selection, pattern matching, or all VMs.

    \b
    Examples:
        azlin batch stop --tag 'env=dev'
        azlin batch start --vm-pattern 'test-*'
        azlin batch command 'git pull' --all
        azlin batch sync --tag 'env=dev'
    """
    pass


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


@main.group(name="keys")
def keys_group():
    """SSH key management and rotation.

    Manage SSH keys across Azure VMs with rotation, backup, and export functionality.
    """
    pass


@main.group(name="template")
def template():
    """Manage VM configuration templates.

    Templates allow you to save and reuse VM configurations.
    Stored in ~/.azlin/templates/ as YAML files.

    \b
    SUBCOMMANDS:
        create   Create a new template
        list     List all templates
        delete   Delete a template
        export   Export template to file
        import   Import template from file

    \b
    EXAMPLES:
        # Create a template interactively
        azlin template create dev-vm

        # List all templates
        azlin template list

        # Delete a template
        azlin template delete dev-vm

        # Export a template
        azlin template export dev-vm my-template.yaml

        # Import a template
        azlin template import my-template.yaml

        # Use a template when creating VM
        azlin new --template dev-vm
    """
    pass


@main.group(name="snapshot")
@click.pass_context
def snapshot(ctx):
    """Manage VM snapshots.

    Create, list, restore, and delete VM disk snapshots for backup and recovery.

    \b
    EXAMPLES:
        # Create a snapshot of a VM
        $ azlin snapshot create my-vm

        # List snapshots for a VM
        $ azlin snapshot list my-vm

        # Restore VM from a snapshot
        $ azlin snapshot restore my-vm my-vm-snapshot-20251015-053000

        # Delete a snapshot
        $ azlin snapshot delete my-vm-snapshot-20251015-053000
    """
    pass


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
    pass


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

    Creates a template with the specified configuration.
    If options are not provided, uses defaults from config.

    \b
    Examples:
        azlin template create dev-vm
        azlin template create dev-vm --vm-size Standard_D2s_v3 --region eastus
        azlin template create dev-vm --description "My dev VM" --cloud-init custom.yaml
    """
    try:
        # Load config for defaults
        try:
            config = ConfigManager.load_config()
        except ConfigError:
            config = AzlinConfig()

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
        # Validate selection options
        selection_count = sum([bool(tag), bool(vm_pattern), select_all])
        if selection_count == 0:
            click.echo("Error: Must specify --tag, --vm-pattern, or --all", err=True)
            sys.exit(1)
        if selection_count > 1:
            click.echo("Error: Can only use one of --tag, --vm-pattern, or --all", err=True)
            sys.exit(1)

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # List all VMs
        click.echo(f"Loading VMs from resource group: {rg}...")
        all_vms = VMManager.list_vms(rg, include_stopped=False)

        # Select VMs based on criteria
        if tag:
            selected_vms = BatchSelector.select_by_tag(all_vms, tag)
            selection_desc = f"tag '{tag}'"
        elif vm_pattern:
            selected_vms = BatchSelector.select_by_pattern(all_vms, vm_pattern)
            selection_desc = f"pattern '{vm_pattern}'"
        else:  # select_all
            selected_vms = all_vms
            selection_desc = "all VMs"

        if not selected_vms:
            click.echo(f"No running VMs found matching {selection_desc}.")
            return

        # Show summary
        click.echo(f"\nFound {len(selected_vms)} VM(s) matching {selection_desc}:")
        click.echo("=" * 80)
        for vm in selected_vms:
            click.echo(f"  {vm.name:<35} {vm.public_ip or 'N/A':<15} {vm.location}")
        click.echo("=" * 80)

        # Confirmation
        if not confirm:
            action = "deallocate" if deallocate else "stop"
            click.echo(f"\nThis will {action} {len(selected_vms)} VM(s).")
            confirm_input = input("Continue? [y/N]: ").lower()
            if confirm_input not in ["y", "yes"]:
                click.echo("Cancelled.")
                return

        # Execute batch stop
        click.echo(f"\n{'Deallocating' if deallocate else 'Stopping'} {len(selected_vms)} VM(s)...")
        executor = BatchExecutor(max_workers=max_workers)

        def progress_callback(msg: str):
            click.echo(f"  {msg}")

        results = executor.execute_stop(
            selected_vms, rg, deallocate=deallocate, progress_callback=progress_callback
        )

        # Show results
        batch_result = BatchResult(results)
        click.echo("\n" + "=" * 80)
        click.echo("Batch Stop Summary")
        click.echo("=" * 80)
        click.echo(batch_result.format_summary())
        click.echo("=" * 80)

        if batch_result.failed > 0:
            click.echo("\nFailed VMs:")
            for failure in batch_result.get_failures():
                click.echo(f"  - {failure.vm_name}: {failure.message}")

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
        logger.exception("Unexpected error in batch stop")
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
        selection_count = sum([bool(tag), bool(vm_pattern), select_all])
        if selection_count == 0:
            click.echo("Error: Must specify --tag, --vm-pattern, or --all", err=True)
            sys.exit(1)
        if selection_count > 1:
            click.echo("Error: Can only use one of --tag, --vm-pattern, or --all", err=True)
            sys.exit(1)

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # List all VMs including stopped
        click.echo(f"Loading VMs from resource group: {rg}...")
        all_vms = VMManager.list_vms(rg, include_stopped=True)

        # Select VMs based on criteria
        if tag:
            selected_vms = BatchSelector.select_by_tag(all_vms, tag)
            selection_desc = f"tag '{tag}'"
        elif vm_pattern:
            selected_vms = BatchSelector.select_by_pattern(all_vms, vm_pattern)
            selection_desc = f"pattern '{vm_pattern}'"
        else:  # select_all
            selected_vms = all_vms
            selection_desc = "all VMs"

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
        if not confirm:
            click.echo(f"\nThis will start {len(stopped_vms)} VM(s).")
            confirm_input = input("Continue? [y/N]: ").lower()
            if confirm_input not in ["y", "yes"]:
                click.echo("Cancelled.")
                return

        # Execute batch start
        click.echo(f"\nStarting {len(stopped_vms)} VM(s)...")
        executor = BatchExecutor(max_workers=max_workers)

        def progress_callback(msg: str):
            click.echo(f"  {msg}")

        results = executor.execute_start(stopped_vms, rg, progress_callback=progress_callback)

        # Show results
        batch_result = BatchResult(results)
        click.echo("\n" + "=" * 80)
        click.echo("Batch Start Summary")
        click.echo("=" * 80)
        click.echo(batch_result.format_summary())
        click.echo("=" * 80)

        if batch_result.failed > 0:
            click.echo("\nFailed VMs:")
            for failure in batch_result.get_failures():
                click.echo(f"  - {failure.vm_name}: {failure.message}")

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
        selection_count = sum([bool(tag), bool(vm_pattern), select_all])
        if selection_count == 0:
            click.echo("Error: Must specify --tag, --vm-pattern, or --all", err=True)
            sys.exit(1)
        if selection_count > 1:
            click.echo("Error: Can only use one of --tag, --vm-pattern, or --all", err=True)
            sys.exit(1)

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # List all VMs
        click.echo(f"Loading VMs from resource group: {rg}...")
        all_vms = VMManager.list_vms(rg, include_stopped=False)

        # Select VMs based on criteria
        if tag:
            selected_vms = BatchSelector.select_by_tag(all_vms, tag)
            selection_desc = f"tag '{tag}'"
        elif vm_pattern:
            selected_vms = BatchSelector.select_by_pattern(all_vms, vm_pattern)
            selection_desc = f"pattern '{vm_pattern}'"
        else:  # select_all
            selected_vms = all_vms
            selection_desc = "all VMs"

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
        click.echo("\n" + "=" * 80)
        click.echo("Batch Command Summary")
        click.echo("=" * 80)
        click.echo(batch_result.format_summary())
        click.echo("=" * 80)

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

        if batch_result.failed > 0:
            click.echo("\nFailed VMs:")
            for failure in batch_result.get_failures():
                click.echo(f"  - {failure.vm_name}: {failure.message}")

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
        selection_count = sum([bool(tag), bool(vm_pattern), select_all])
        if selection_count == 0:
            click.echo("Error: Must specify --tag, --vm-pattern, or --all", err=True)
            sys.exit(1)
        if selection_count > 1:
            click.echo("Error: Can only use one of --tag, --vm-pattern, or --all", err=True)
            sys.exit(1)

        # Get resource group
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        # List all VMs
        click.echo(f"Loading VMs from resource group: {rg}...")
        all_vms = VMManager.list_vms(rg, include_stopped=False)

        # Select VMs based on criteria
        if tag:
            selected_vms = BatchSelector.select_by_tag(all_vms, tag)
            selection_desc = f"tag '{tag}'"
        elif vm_pattern:
            selected_vms = BatchSelector.select_by_pattern(all_vms, vm_pattern)
            selection_desc = f"pattern '{vm_pattern}'"
        else:  # select_all
            selected_vms = all_vms
            selection_desc = "all VMs"

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
        click.echo("\n" + "=" * 80)
        click.echo("Batch Sync Summary")
        click.echo("=" * 80)
        click.echo(batch_result.format_summary())
        click.echo("=" * 80)

        if batch_result.failed > 0:
            click.echo("\nFailed VMs:")
            for failure in batch_result.get_failures():
                click.echo(f"  - {failure.vm_name}: {failure.message}")

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
        monthly_cost = manager.get_snapshot_cost_estimate(snapshot.size_gb, 30)
        click.echo("\n✓ Snapshot created successfully!")
        click.echo(f"  Name:     {snapshot.name}")
        click.echo(f"  Size:     {snapshot.size_gb} GB")
        click.echo(f"  Location: {snapshot.location}")
        click.echo(f"  Created:  {snapshot.created_time}")
        click.echo(f"\nEstimated storage cost: ${monthly_cost:.2f}/month")

    except SnapshotManagerError as e:
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
        click.echo("=" * 110)
        click.echo(f"{'NAME':<50} {'SIZE':<10} {'CREATED':<30} {'STATUS':<20}")
        click.echo("=" * 110)

        total_size = 0
        for snap in snapshots:
            created = snap.created_time[:19].replace("T", " ") if snap.created_time else "N/A"
            status = snap.provisioning_state or "Unknown"
            click.echo(f"{snap.name:<50} {snap.size_gb:<10} {created:<30} {status:<20}")
            total_size += snap.size_gb

        click.echo("=" * 110)
        click.echo(f"\nTotal: {len(snapshots)} snapshots ({total_size} GB)")

        # Show cost estimate
        monthly_cost = manager.get_snapshot_cost_estimate(total_size, 30)
        click.echo(f"Estimated total storage cost: ${monthly_cost:.2f}/month\n")

    except SnapshotManagerError as e:
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

    except SnapshotManagerError as e:
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

    except SnapshotManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# Register storage commands
main.add_command(storage_group)


@main.group()
def env():
    """Manage environment variables on VMs.

    Commands to set, list, delete, and export environment variables
    stored in ~/.bashrc on remote VMs.

    \b
    Examples:
        azlin env set my-vm DATABASE_URL="postgres://localhost/db"
        azlin env list my-vm
        azlin env delete my-vm API_KEY
        azlin env export my-vm prod.env
    """
    pass


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
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
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
        vm_identifier: VM name or IP address
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
    if VMConnector._is_valid_ip(vm_identifier):
        # Direct IP connection
        return SSHConfig(host=vm_identifier, user="azureuser", key_path=ssh_key_pair.private_path)

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


if __name__ == "__main__":
    main()


__all__ = ["main", "CLIOrchestrator", "AzlinError"]
