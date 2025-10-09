"""CLI entry point for azlin.

This module provides the command-line interface for azlin,
orchestrating all modules to provision Azure VMs with dev tools.

Usage:
    azlin                    # Provision VM without repo
    azlin --repo <url>       # Provision VM and clone repo
    azlin --help             # Show help
"""

import sys
import logging
import time
import click
from pathlib import Path
from typing import Optional

from azlin import __version__
from azlin.azure_auth import AzureAuthenticator, AuthenticationError
from azlin.vm_provisioning import VMProvisioner, VMConfig, VMDetails, ProvisioningError
from azlin.modules.prerequisites import PrerequisiteChecker, PrerequisiteError
from azlin.modules.ssh_keys import SSHKeyManager, SSHKeyError
from azlin.modules.ssh_connector import SSHConnector, SSHConfig, SSHConnectionError
from azlin.modules.github_setup import GitHubSetupHandler, GitHubSetupError
from azlin.modules.progress import ProgressDisplay, ProgressStage
from azlin.modules.notifications import NotificationHandler

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


@click.command()
@click.option(
    '--repo',
    help='GitHub repository URL to clone',
    type=str,
    default=None
)
@click.option(
    '--vm-size',
    help='Azure VM size',
    type=click.Choice([
        'Standard_B1s', 'Standard_B1ms', 'Standard_B2s', 'Standard_B2ms',
        'Standard_D2s_v3', 'Standard_D4s_v3', 'Standard_D8s_v3',
    ], case_sensitive=False),
    default='Standard_D2s_v3'
)
@click.option(
    '--region',
    help='Azure region',
    type=click.Choice([
        'eastus', 'eastus2', 'westus', 'westus2',
        'centralus', 'northeurope', 'westeurope'
    ], case_sensitive=False),
    default='eastus'
)
@click.option(
    '--resource-group',
    help='Azure resource group name',
    type=str,
    default=None
)
@click.option(
    '--no-auto-connect',
    help='Do not automatically connect via SSH',
    is_flag=True,
    default=False
)
@click.option(
    '--config',
    help='Configuration file path',
    type=click.Path(exists=True),
    default=None
)
@click.version_option(version=__version__)
def main(
    repo: Optional[str],
    vm_size: str,
    region: str,
    resource_group: Optional[str],
    no_auto_connect: bool,
    config: Optional[str]
) -> None:
    """azlin - Azure Ubuntu VM provisioning and setup.

    Provisions an Azure Ubuntu VM with development tools installed,
    configures SSH access, and optionally clones a GitHub repository.

    Examples:

        # Provision VM without repo
        azlin

        # Provision VM and clone repository
        azlin --repo https://github.com/owner/repo

        # Specify custom VM size and region
        azlin --vm-size Standard_D4s_v3 --region westus2
    """
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
    )

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
        vm_size=vm_size,
        region=region,
        resource_group=resource_group,
        auto_connect=not no_auto_connect,
        config_file=config
    )

    exit_code = orchestrator.run()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()


__all__ = ['main', 'CLIOrchestrator', 'AzlinError']
