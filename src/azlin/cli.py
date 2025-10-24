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
from typing import Any

import click

from azlin import __version__
from azlin.agentic import (
    CommandExecutionError,
    CommandExecutor,
    IntentParseError,
    IntentParser,
    ResultValidator,
)
from azlin.azure_auth import AuthenticationError, AzureAuthenticator
from azlin.batch_executor import BatchExecutor, BatchExecutorError, BatchResult, BatchSelector

# Storage commands
from azlin.commands.storage import storage_group

# New modules for v2.0
from azlin.config_manager import AzlinConfig, ConfigError, ConfigManager
from azlin.cost_tracker import CostTracker, CostTrackerError
from azlin.distributed_top import DistributedTopError, DistributedTopExecutor
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
    SyncResult,
)
from azlin.modules.notifications import NotificationHandler
from azlin.modules.prerequisites import PrerequisiteChecker, PrerequisiteError
from azlin.modules.progress import ProgressDisplay, ProgressStage
from azlin.modules.snapshot_manager import SnapshotError, SnapshotManager
from azlin.modules.ssh_connector import SSHConfig, SSHConnectionError, SSHConnector
from azlin.modules.ssh_keys import SSHKeyError, SSHKeyManager, SSHKeyPair
from azlin.prune import PruneManager
from azlin.remote_exec import (
    OSUpdateExecutor,
    PSCommandExecutor,
    RemoteExecError,
    RemoteExecutor,
    WCommandExecutor,
)
from azlin.tag_manager import TagManager
from azlin.template_manager import TemplateError, TemplateManager, VMTemplateConfig
from azlin.vm_connector import VMConnector, VMConnectorError
from azlin.vm_lifecycle import DeletionSummary, VMLifecycleError, VMLifecycleManager
from azlin.vm_lifecycle_control import VMLifecycleControlError, VMLifecycleController
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

            # STEP 5.5: Resolve and mount NFS storage if configured (BEFORE home sync)
            # Load config for NFS defaults
            try:
                azlin_config = ConfigManager.load_config(self.config_file)
            except ConfigError:
                azlin_config = AzlinConfig()

            resolved_nfs = self._resolve_nfs_storage(rg_name, azlin_config)

            if resolved_nfs:
                self.progress.start_operation(f"Mounting NFS storage: {resolved_nfs}")
                self._mount_nfs_storage(vm_details, ssh_key_pair.private_path, resolved_nfs)
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
                return self._connect_ssh(vm_details, ssh_key_pair.private_path)

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
            if self.vm_details:
                self._display_connection_info(self.vm_details)
                if self.auto_connect and self.ssh_keys:
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

    def _setup_ssh_keys(self) -> SSHKeyPair:
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
        if not vm_details.public_ip:
            raise SSHConnectionError("VM has no public IP address")

        self.progress.update("Waiting for SSH to be available...")

        # Wait for SSH port to be accessible
        public_ip: str = vm_details.public_ip  # Type narrowed by check above
        ssh_ready = SSHConnector.wait_for_ssh_ready(public_ip, key_path, timeout=300, interval=5)

        if not ssh_ready:
            raise SSHConnectionError("SSH did not become available")

        self.progress.update("SSH available, checking cloud-init status...")

        # Check cloud-init status
        ssh_config = SSHConfig(host=public_ip, user="azureuser", key_path=key_path)

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
                if "status: running" in output:
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

    def _show_blocked_files_warning(self, blocked_files: list[str]) -> None:
        """Display warning about blocked files before sync."""
        import click

        click.echo(
            click.style(
                f"\n  Security: Skipping {len(blocked_files)} sensitive file(s):",
                fg="yellow",
                bold=True,
            )
        )
        for blocked_file in blocked_files[:5]:  # Show first 5
            click.echo(click.style(f"    • {blocked_file}", fg="yellow"))
        if len(blocked_files) > 5:
            click.echo(click.style(f"    ... and {len(blocked_files) - 5} more", fg="yellow"))
        click.echo()  # Empty line for spacing

    def _process_sync_result(self, result: SyncResult) -> None:
        """Process and display sync result."""
        if result.success:
            if result.files_synced > 0:
                # Show sync stats with warning count
                sync_msg = (
                    f"Synced {result.files_synced} files "
                    f"({result.bytes_transferred / 1024:.1f} KB) "
                    f"in {result.duration_seconds:.1f}s"
                )
                if result.warnings:
                    sync_msg += f" ({len(result.warnings)} skipped)"
                self.progress.update(sync_msg)
            else:
                self.progress.update("No files to sync")

            # Display warnings prominently after sync
            if result.warnings:
                import click

                for warning in result.warnings[:3]:  # Show first 3 warnings
                    click.echo(click.style(f"  ⚠  {warning}", fg="yellow"))
                if len(result.warnings) > 3:
                    click.echo(
                        click.style(
                            f"  ⚠  ... and {len(result.warnings) - 3} more warnings",
                            fg="yellow",
                        )
                    )
        else:
            # Log errors but don't fail
            for error in result.errors:
                logger.warning(f"Sync error: {error}")

    def _sync_home_directory(self, vm_details: VMDetails, key_path: Path) -> None:
        """Sync home directory to VM.

        Args:
            vm_details: VM details
            key_path: SSH private key path

        Note:
            Sync failures are logged as warnings but don't block VM provisioning.
        """
        if not vm_details.public_ip:
            logger.warning("VM has no public IP, skipping home directory sync")
            return

        public_ip: str = vm_details.public_ip  # Type narrowed by check above

        try:
            # Create SSH config
            ssh_config = SSHConfig(host=public_ip, user="azureuser", key_path=key_path)

            # Pre-sync validation check with visible warnings
            sync_dir = HomeSyncManager.get_sync_directory()
            if sync_dir.exists():
                validation = HomeSyncManager.validate_sync_directory(sync_dir)
                if validation.blocked_files:
                    self._show_blocked_files_warning(validation.blocked_files)

            # Progress callback
            def progress_callback(msg: str):
                self.progress.update(msg, ProgressStage.IN_PROGRESS)

            # Attempt sync
            result = HomeSyncManager.sync_to_vm(
                ssh_config, dry_run=False, progress_callback=progress_callback
            )

            self._process_sync_result(result)

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

    def _resolve_nfs_storage(self, resource_group: str, config: AzlinConfig | None) -> str | None:
        """Resolve which NFS storage to use.

        Priority:
        1. Explicit --nfs-storage option
        2. Config file default_nfs_storage
        3. Auto-detect if only one storage exists
        4. None if no storage or multiple without explicit choice

        Args:
            resource_group: Resource group to search for storage
            config: Configuration object (optional)

        Returns:
            Storage name or None

        Raises:
            ValueError: If multiple storages exist without explicit choice
        """
        from azlin.modules.storage_manager import StorageManager

        # Priority 1: Explicit --nfs-storage option
        if self.nfs_storage:
            return self.nfs_storage

        # Priority 2: Config file default
        if config and config.default_nfs_storage:
            return config.default_nfs_storage

        # Priority 3: Auto-detect
        try:
            storages = StorageManager.list_storage(resource_group)
        except Exception as e:
            logger.debug(f"Failed to list storages: {e}")
            return None

        if len(storages) == 0:
            return None
        if len(storages) == 1:
            # Auto-detect single storage
            storage_name = storages[0].name
            self.progress.update(f"Auto-detected NFS storage: {storage_name}")
            return storage_name
        # Multiple storages without explicit choice
        storage_names = [s.name for s in storages]
        raise ValueError(
            f"Multiple NFS storage accounts found: {', '.join(storage_names)}. "
            f"Please specify one with --nfs-storage or set default_nfs_storage in config."
        )

    def _get_vm_subnet_id(self, vm_details: VMDetails) -> str:
        """Get the subnet ID for a VM.

        Args:
            vm_details: VM details object

        Returns:
            Full Azure resource ID of the VM's subnet

        Raises:
            Exception: If subnet ID cannot be retrieved
        """
        import subprocess

        try:
            # Get the NIC ID from the VM
            nic_cmd = [
                "az",
                "vm",
                "show",
                "--resource-group",
                vm_details.resource_group,
                "--name",
                vm_details.name,
                "--query",
                "networkProfile.networkInterfaces[0].id",
                "--output",
                "tsv",
            ]
            nic_result = subprocess.run(
                nic_cmd, capture_output=True, text=True, check=True, timeout=30
            )
            nic_id = nic_result.stdout.strip()

            # Get the subnet ID from the NIC
            subnet_cmd = [
                "az",
                "network",
                "nic",
                "show",
                "--ids",
                nic_id,
                "--query",
                "ipConfigurations[0].subnet.id",
                "--output",
                "tsv",
            ]
            subnet_result = subprocess.run(
                subnet_cmd, capture_output=True, text=True, check=True, timeout=30
            )
            subnet_id = subnet_result.stdout.strip()

            if not subnet_id:
                raise Exception("Failed to get subnet ID from VM")

            return subnet_id

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            raise Exception(f"Failed to get VM subnet ID: {error_msg}") from e

    def _restore_ssh_keys_via_runcommand(self, vm_details: VMDetails, key_path: Path) -> None:
        """Restore SSH keys via Azure run-command.

        Azure's waagent overwrites SSH authorized_keys after cloud-init completes,
        breaking SSH access. This method uses Azure's run-command API to restore
        the keys without requiring SSH access.

        Args:
            vm_details: VM details object
            key_path: Path to SSH private key (public key must be at key_path.pub)

        Raises:
            Exception: If key restoration fails
        """
        import subprocess

        try:
            # Read public key
            pub_key_path = Path(str(key_path) + ".pub")
            if not pub_key_path.exists():
                raise Exception(f"SSH public key not found: {pub_key_path}")

            pub_key = pub_key_path.read_text().strip()

            # Create script to restore SSH keys
            script = f"""#!/bin/bash
mkdir -p /home/azureuser/.ssh
echo '{pub_key}' > /home/azureuser/.ssh/authorized_keys
chown -R azureuser:azureuser /home/azureuser/.ssh
chmod 700 /home/azureuser/.ssh
chmod 600 /home/azureuser/.ssh/authorized_keys
"""

            # Execute via Azure run-command
            cmd = [
                "az",
                "vm",
                "run-command",
                "invoke",
                "--resource-group",
                vm_details.resource_group,
                "--name",
                vm_details.name,
                "--command-id",
                "RunShellScript",
                "--scripts",
                script,
            ]

            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)

            logger.info("SSH keys restored successfully via run-command")

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            raise Exception(f"Failed to restore SSH keys via run-command: {error_msg}") from e
        except Exception as e:
            raise Exception(f"Failed to restore SSH keys: {e}") from e

    def _mount_nfs_storage(self, vm_details: VMDetails, key_path: Path, storage_name: str) -> None:
        """Mount NFS storage on VM home directory.

        Args:
            vm_details: VM details
            key_path: SSH private key path
            storage_name: Name of the NFS storage account to mount

        Raises:
            Exception: If storage mount fails (this is a critical operation)
        """
        if not vm_details.public_ip:
            raise Exception("VM has no public IP address, cannot mount NFS storage")

        from azlin.modules.nfs_mount_manager import NFSMountManager
        from azlin.modules.storage_manager import StorageManager

        try:
            # Get storage details
            self.progress.update(f"Fetching storage account: {storage_name}")

            # Get resource group (use the VM's resource group)
            rg = vm_details.resource_group

            # List storage accounts to find the one we want
            accounts = StorageManager.list_storage(rg)
            storage = next((a for a in accounts if a.name == storage_name), None)

            if not storage:
                raise Exception(
                    f"Storage account '{storage_name}' not found in resource group '{rg}'. "
                    f"Create it first with: azlin storage create {storage_name}"
                )

            self.progress.update(f"Storage found: {storage.nfs_endpoint}")

            # Configure network access for NFS (must be done before mount)
            self.progress.update("Configuring NFS network access...")
            vm_subnet_id = self._get_vm_subnet_id(vm_details)
            StorageManager.configure_nfs_network_access(
                storage_account=storage_name,
                resource_group=rg,
                vm_subnet_id=vm_subnet_id,
            )

            # Read SSH public key for restoration after mount
            pub_key_path = Path(str(key_path) + ".pub")
            if not pub_key_path.exists():
                raise Exception(f"SSH public key not found: {pub_key_path}")
            ssh_public_key = pub_key_path.read_text().strip()

            # Mount storage via run-command (bypasses SSH key limitations)
            self.progress.update("Mounting NFS storage via run-command...")
            result = NFSMountManager.mount_storage_via_runcommand(
                vm_name=vm_details.name,
                resource_group=rg,
                nfs_endpoint=storage.nfs_endpoint,
                ssh_public_key=ssh_public_key,
                mount_point="/home/azureuser",
            )

            if not result.success:
                error_msg = "; ".join(result.errors) if result.errors else "Unknown error"
                raise Exception(f"Failed to mount NFS storage: {error_msg}")

            if result.backed_up_files > 0:
                self.progress.update(f"Backed up {result.backed_up_files} existing files")

            if result.copied_files > 0:
                self.progress.update(
                    f"Copied {result.copied_files} files from backup to shared storage"
                )

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

        if not vm_details.public_ip:
            raise GitHubSetupError("VM has no public IP address")

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
        if not vm_details.public_ip:
            raise SSHConnectionError("VM has no public IP address")

        ssh_config = SSHConfig(host=vm_details.public_ip, user="azureuser", key_path=key_path)

        click.echo("\n" + "=" * 60)
        click.echo(f"Connecting to {vm_details.name} via SSH...")
        click.echo("Starting tmux session 'azlin'")
        click.echo("=" * 60 + "\n")

        # Connect with auto-tmux
        return SSHConnector.connect(ssh_config, tmux_session="azlin", auto_tmux=True)

    def _send_notification(self, vm_details: VMDetails, success: bool = True) -> None:
        """Send completion notification via imessR if available.

        Args:
            vm_details: VM details
            success: Whether provisioning succeeded
        """
        # Use public_ip if available, otherwise indicate unknown
        vm_ip = vm_details.public_ip if vm_details.public_ip else "unknown"
        result = NotificationHandler.send_completion_notification(
            vm_details.name, vm_ip, success=success
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

            return SSHConnector.connect(ssh_config, tmux_session="azlin", auto_tmux=True)
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
        click.echo("Invalid selection")
        return None
    except ValueError:
        click.echo("Invalid input")
        return None


class AzlinGroup(click.Group):
    """Custom Click group that handles -- delimiter for command passthrough."""

    def main(self, *args: Any, **kwargs: Any) -> Any:
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

    def invoke(self, ctx: click.Context) -> Any:
        """Pass the passthrough command to the context."""
        if hasattr(self, "_passthrough_command"):
            ctx.obj = {"passthrough_command": self._passthrough_command}
        return super().invoke(ctx)

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        """Override to show help when command is not found."""
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError:
            # Command not found - show help and exit
            click.echo(ctx.get_help())
            ctx.exit(1)


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
def main(ctx: click.Context) -> None:
    """azlin - Azure Ubuntu VM provisioning and management.

    Provisions Azure Ubuntu VMs with development tools, manages existing VMs,
    and executes commands remotely.

    \b
    NATURAL LANGUAGE COMMANDS (AI-POWERED):
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

    # If no subcommand provided, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(0)  # Use ctx.exit() instead of sys.exit() for Click compatibility


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


def _execute_command_mode(orchestrator: CLIOrchestrator, command: str) -> None:
    """Execute VM provisioning and command execution."""
    click.echo(f"\nCommand to execute: {command}")
    click.echo("Provisioning VM first...\n")

    orchestrator.auto_connect = False
    exit_code = orchestrator.run()

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
) -> None:
    """Provision pool of VMs in parallel."""
    click.echo(f"\nProvisioning pool of {pool} VMs in parallel...")

    ssh_key_pair = SSHKeyManager.ensure_key_exists()

    configs: list[VMConfig] = []
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

    try:
        result = orchestrator.provisioner.provision_vm_pool(
            configs,
            progress_callback=lambda msg: click.echo(f"  {msg}"),
            max_workers=min(10, pool),
        )
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
        for vm in result.successful:
            click.echo(f"  {vm.name:<30} {vm.public_ip:<15} {vm.location}")
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


@main.command(name="new")
@click.pass_context
@click.option("--repo", help="GitHub repository URL to clone", type=str)
@click.option(
    "--size",
    help="VM size tier: s(mall), m(edium), l(arge), xl (default: l)",
    type=click.Choice(["s", "m", "l", "xl"], case_sensitive=False),
)
@click.option("--vm-size", help="Azure VM size (overrides --size)", type=str)
@click.option("--region", help="Azure region", type=str)
@click.option("--resource-group", "--rg", help="Azure resource group", type=str)
@click.option("--name", help="Custom VM name", type=str)
@click.option("--pool", help="Number of VMs to create in parallel", type=int)
@click.option("--no-auto-connect", help="Do not auto-connect via SSH", is_flag=True)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--template", help="Template name to use for VM configuration", type=str)
@click.option("--nfs-storage", help="NFS storage account name to mount as home directory", type=str)
def new_command(
    ctx: click.Context,
    repo: str | None,
    size: str | None,
    vm_size: str | None,
    region: str | None,
    resource_group: str | None,
    name: str | None,
    pool: int | None,
    no_auto_connect: bool,
    config: str | None,
    template: str | None,
    nfs_storage: str | None,
) -> None:
    """Provision a new Azure VM with development tools.

    Creates a new Ubuntu VM in Azure with all development tools pre-installed.
    Optionally connects via SSH and clones a GitHub repository.

    \b
    EXAMPLES:
        # Provision basic VM (uses size 'l' = 128GB RAM)
        $ azlin new

        # Provision with size tier (s=8GB, m=64GB, l=128GB, xl=256GB)
        $ azlin new --size m     # Medium: 64GB RAM
        $ azlin new --size s     # Small: 8GB RAM (original default)
        $ azlin new --size xl    # Extra-large: 256GB RAM

        # Provision with exact VM size (overrides --size)
        $ azlin new --vm-size Standard_E8as_v5

        # Provision with custom name
        $ azlin new --name my-dev-vm --size m

        # Provision and clone repository
        $ azlin new --repo https://github.com/owner/repo

        # Provision 5 VMs in parallel
        $ azlin new --pool 5 --size l

        # Provision from template
        $ azlin new --template dev-vm

        # Provision with NFS storage for shared home directory
        $ azlin new --nfs-storage myteam-shared --name worker-1

        # Provision and execute command
        $ azlin new --size xl -- python train.py
    """
    # Check for passthrough command
    command = None
    if ctx.obj and "passthrough_command" in ctx.obj:
        command = ctx.obj["passthrough_command"]
    elif ctx.args:
        command = " ".join(ctx.args)

    # Load configuration and template
    azlin_config, template_config = _load_config_and_template(config, template)

    # Resolve VM settings
    final_rg, final_region, final_vm_size = _resolve_vm_settings(
        resource_group, region, size, vm_size, azlin_config, template_config
    )

    # Generate VM name
    vm_name = generate_vm_name(name, command)

    # Validate inputs
    _validate_inputs(pool, repo)

    # Create orchestrator
    orchestrator = CLIOrchestrator(
        repo=repo,
        vm_size=final_vm_size,
        region=final_region,
        resource_group=final_rg,
        auto_connect=not no_auto_connect,
        config_file=config,
        nfs_storage=nfs_storage,
    )

    # Update config state
    _update_config_state(config, final_rg, vm_name, name)

    # Handle command execution mode
    if command and not pool:
        _execute_command_mode(orchestrator, command)

    # Handle pool provisioning
    if pool and pool > 1:
        _provision_pool(orchestrator, pool, vm_name, final_rg, final_region, final_vm_size)

    # Standard single VM provisioning
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
def vm_command(ctx: click.Context, **kwargs: Any) -> Any:
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
def create_command(ctx: click.Context, **kwargs: Any) -> Any:
    """Alias for 'new' command. Provision a new Azure VM."""
    return ctx.invoke(new_command, **kwargs)


@main.command(name="list")
@click.option("--resource-group", "--rg", help="Resource group to list VMs from", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--all", "show_all", help="Show all VMs (including stopped)", is_flag=True)
@click.option("--tag", help="Filter VMs by tag (format: key or key=value)", type=str)
def list_command(resource_group: str | None, config: str | None, show_all: bool, tag: str | None):
    """List VMs in resource group or across all resource groups.

    By default, lists all azlin-managed VMs (those with managed-by=azlin tag) across all resource groups.
    Use --rg to limit to a specific resource group.

    Shows VM name, status, IP address, region, and size.

    \b
    Examples:
        azlin list                    # All azlin VMs across all RGs
        azlin list --rg my-rg         # VMs in specific RG
        azlin list --all              # Include stopped VMs
        azlin list --tag env=dev      # Filter by tag
    """
    try:
        # Get resource group from config or CLI
        rg = ConfigManager.get_resource_group(resource_group, config)

        # Cross-RG discovery: if no RG specified, list all managed VMs
        if not rg:
            click.echo("Listing all azlin-managed VMs across resource groups...\n")
            try:
                vms = TagManager.list_managed_vms(resource_group=None)
                if not show_all:
                    vms = [vm for vm in vms if vm.is_running()]
            except Exception as e:
                click.echo(
                    f"Warning: Tag-based discovery failed ({e}).\n"
                    "Falling back to default resource group.\n",
                    err=True,
                )
                # Fall back to requiring RG
                click.echo(
                    "Error: No resource group specified and no default configured.", err=True
                )
                click.echo("Use --resource-group or set default in ~/.azlin/config.toml", err=True)
                sys.exit(1)
        else:
            # Single RG listing
            click.echo(f"Listing VMs in resource group: {rg}\n")
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

        # Populate session names from tags (hybrid resolution: tags first, config fallback)
        for vm in vms:
            # Try to get from tags first
            session_from_tag = TagManager.get_session_name(vm.name, vm.resource_group)
            if session_from_tag:
                vm.session_name = session_from_tag
            else:
                # Fall back to config file
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
        # Resolve session name to VM name if applicable
        resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_name, config)
        if resolved_vm_name:
            vm_name = resolved_vm_name

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
            cleared_tag = False
            cleared_config = False

            # Clear from tags
            try:
                cleared_tag = TagManager.delete_session_name(vm_name, rg)
            except Exception as e:
                logger.warning(f"Failed to clear session from tags: {e}")

            # Clear from config
            cleared_config = ConfigManager.delete_session_name(vm_name, config)

            if cleared_tag or cleared_config:
                locations = []
                if cleared_tag:
                    locations.append("VM tags")
                if cleared_config:
                    locations.append("local config")
                click.echo(
                    f"Cleared session name for VM '{vm_name}' from {' and '.join(locations)}"
                )
            else:
                click.echo(f"No session name set for VM '{vm_name}'")
            return

        # View current session name (hybrid: tags first, config fallback)
        if not session_name:
            # Try tags first
            current_name = TagManager.get_session_name(vm_name, rg)
            source = "VM tags" if current_name else None

            # Fall back to config
            if not current_name:
                current_name = ConfigManager.get_session_name(vm_name, config)
                source = "local config" if current_name else None

            if current_name:
                click.echo(f"Session name for '{vm_name}': {current_name} (from {source})")
            else:
                click.echo(f"No session name set for VM '{vm_name}'")
                click.echo(f"\nSet one with: azlin session {vm_name} <session_name>")
            return

        # Set session name (write to both tags and config)
        success_tag = False
        success_config = False

        # Set in tags (primary)
        try:
            TagManager.set_session_name(vm_name, rg, session_name)
            success_tag = True
        except Exception as e:
            logger.warning(f"Failed to set session in tags: {e}")
            click.echo(f"Warning: Could not set session name in VM tags: {e}", err=True)

        # Set in config (backward compatibility)
        try:
            ConfigManager.set_session_name(vm_name, session_name, config)
            success_config = True
        except Exception as e:
            logger.warning(f"Failed to set session in config: {e}")

        if success_tag or success_config:
            locations = []
            if success_tag:
                locations.append("VM tags")
            if success_config:
                locations.append("local config")
            click.echo(
                f"Set session name for '{vm_name}' to '{session_name}' in {' and '.join(locations)}"
            )
        else:
            click.echo("Error: Failed to set session name", err=True)
            sys.exit(1)

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

        # Build SSH configs (all running_vms have public_ip due to filter above)
        ssh_configs: list[SSHConfig] = []
        for vm in running_vms:
            if vm.public_ip:  # Type guard for pyright
                ssh_configs.append(  # noqa: PERF401 (type guard needed for pyright)
                    SSHConfig(
                        host=vm.public_ip, user="azureuser", key_path=ssh_key_pair.private_path
                    )
                )

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
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option(
    "--interval",
    "-i",
    help="Refresh interval in seconds (default 10)",
    type=int,
    default=10,
)
@click.option(
    "--timeout",
    "-t",
    help="SSH timeout per VM in seconds (default 5)",
    type=int,
    default=5,
)
def top(
    resource_group: str | None,
    config: str | None,
    interval: int,
    timeout: int,
):
    """Run distributed top command on all VMs.

    Shows real-time CPU, memory, load, and top processes across all VMs
    in a unified dashboard that updates every N seconds.

    \b
    Examples:
        azlin top                    # Default: 10s refresh
        azlin top -i 5               # 5 second refresh
        azlin top --rg my-rg         # Specific resource group
        azlin top -i 15 -t 10        # 15s refresh, 10s timeout

    \b
    Press Ctrl+C to exit the dashboard.
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

        click.echo(
            f"Starting distributed top for {len(running_vms)} VMs "
            f"(refresh: {interval}s, timeout: {timeout}s)..."
        )
        click.echo("Press Ctrl+C to exit.\n")

        # Build SSH configs (filter out VMs without public IPs)
        ssh_configs = [
            SSHConfig(host=vm.public_ip, user="azureuser", key_path=ssh_key_pair.private_path)
            for vm in running_vms
            if vm.public_ip is not None
        ]

        if not ssh_configs:
            click.echo("Error: No VMs with public IP addresses found", err=True)
            sys.exit(1)

        # Create and run executor
        executor = DistributedTopExecutor(
            ssh_configs=ssh_configs,
            interval=interval,
            timeout=timeout,
        )
        executor.run_dashboard()

    except VMManagerError as e:
        # VMManagerError is already user-friendly
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except DistributedTopError as e:
        # DistributedTopError is already user-friendly
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nDashboard stopped by user.")
        sys.exit(0)
    except Exception as e:
        # Log detailed error for debugging, show generic error to user
        logger.debug(f"Unexpected error in distributed top: {e}", exc_info=True)
        click.echo("Error: An unexpected error occurred. Run with --verbose for details.", err=True)
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
        # Resolve session name to VM name if applicable
        resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_name, config)
        if resolved_vm_name:
            vm_name = resolved_vm_name

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

            # Clean up session name mapping
            try:
                if ConfigManager.delete_session_name(vm_name, config):
                    click.echo("\nRemoved session name mapping")
            except ConfigError:
                pass  # Config cleanup is non-critical
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


def _execute_vm_deletion(vm_name: str, rg: str, force: bool) -> None:
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

        # Clean up session name mapping if it exists
        try:
            if ConfigManager.delete_session_name(vm_name):
                click.echo(f"Removed session name mapping for '{vm_name}'")
        except ConfigError:
            pass  # Config cleanup is non-critical
    else:
        click.echo(f"\nError: {result.message}", err=True)
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
        # Resolve session name to VM name if applicable
        resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_name, config)
        if resolved_vm_name:
            vm_name = resolved_vm_name

        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        if delete_rg:
            _handle_delete_resource_group(rg, vm_name, force, dry_run)
            return

        if dry_run:
            _handle_vm_dry_run(vm_name, rg)
            return

        _execute_vm_deletion(vm_name, rg, force)

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


def _confirm_killall(vms: list[Any], rg: str) -> bool:
    """Display VMs and get confirmation for bulk deletion."""
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
        rg = ConfigManager.get_resource_group(resource_group, config)

        if not rg:
            click.echo("Error: No resource group specified.", err=True)
            sys.exit(1)

        vms = VMManager.list_vms(rg, include_stopped=True)
        vms = VMManager.filter_by_prefix(vms, prefix)

        if not vms:
            click.echo(f"No VMs found with prefix '{prefix}' in resource group '{rg}'.")
            return

        if not force and not _confirm_killall(vms, rg):
            click.echo("Cancelled.")
            return

        click.echo(f"\nDeleting {len(vms)} VM(s) in parallel...")

        summary = VMLifecycleManager.delete_all_vms(
            resource_group=rg, force=True, vm_prefix=prefix, max_workers=5
        )

        # Clean up session names for successfully deleted VMs
        cleaned_count = 0
        for result in summary.results:
            if result.success:
                try:
                    if ConfigManager.delete_session_name(result.vm_name):
                        cleaned_count += 1
                except ConfigError:
                    pass  # Config cleanup is non-critical

        _display_killall_results(summary)

        if cleaned_count > 0:
            click.echo(f"\nRemoved {cleaned_count} session name mapping(s)")

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

        # Build SSH configs (all running_vms have public_ip due to filter above)
        ssh_configs: list[SSHConfig] = []
        for vm in running_vms:
            if vm.public_ip:  # Type guard for pyright
                ssh_configs.append(  # noqa: PERF401 (type guard needed for pyright)
                    SSHConfig(
                        host=vm.public_ip, user="azureuser", key_path=ssh_key_pair.private_path
                    )
                )

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

            ctx = Context(new_command)
            ctx.invoke(
                new_command,
                resource_group=rg,
                config=config,
                no_tmux=no_tmux,
                tmux_session=tmux_session,
            )
        click.echo("Cancelled.")
        sys.exit(0)

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

    while True:
        try:
            selection = click.prompt(
                "Select a VM to connect to (0 to create new)",
                type=int,
                default=1 if vms else 0,
            )

            if selection == 0:
                from click import Context

                ctx = Context(new_command)
                ctx.invoke(
                    new_command,
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


def _resolve_vm_identifier(vm_identifier: str, config: str | None) -> tuple[str, str]:
    """Resolve session name to VM name and return both.

    Returns:
        Tuple of (resolved_identifier, original_identifier)
    """
    original_identifier = vm_identifier
    if not VMConnector.is_valid_ip(vm_identifier):
        resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_identifier, config)
        if resolved_vm_name:
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
    vm_identifier: str, tmux_session: str | None, no_tmux: bool, config: str | None
) -> str | None:
    """Resolve tmux session name from config or provided value."""
    if not tmux_session and not no_tmux:
        session_name = ConfigManager.get_session_name(vm_identifier, config)
        if session_name:
            click.echo(f"Using session name '{session_name}' for tmux")
            return session_name
    return tmux_session


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
    remote_command: tuple[str, ...],
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
        # Interactive VM selection if no identifier provided
        if not vm_identifier:
            rg = ConfigManager.get_resource_group(resource_group, config)
            if not rg:
                click.echo(
                    "Error: Resource group required.\n"
                    "Use --resource-group or set default in ~/.azlin/config.toml",
                    err=True,
                )
                sys.exit(1)
            vm_identifier = _interactive_vm_selection(rg, config, no_tmux, tmux_session)

        # Parse remote command and key path
        command = " ".join(remote_command) if remote_command else None
        key_path = Path(key).expanduser() if key else None

        # Resolve session name to VM name
        vm_identifier, original_identifier = _resolve_vm_identifier(vm_identifier, config)

        # Get resource group for VM name (not IP)
        if not VMConnector.is_valid_ip(vm_identifier):
            rg = ConfigManager.get_resource_group(resource_group, config)
            if not rg:
                click.echo(
                    "Error: Resource group required for VM name.\n"
                    "Use --resource-group or set default in ~/.azlin/config.toml",
                    err=True,
                )
                sys.exit(1)
            _verify_vm_exists(vm_identifier, original_identifier, rg)
        else:
            rg = resource_group

        # Resolve tmux session name
        tmux_session = _resolve_tmux_session(vm_identifier, tmux_session, no_tmux, config)

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
        # Resolve session name to VM name if applicable
        resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_name, config)
        if resolved_vm_name:
            vm_name = resolved_vm_name

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
        # Resolve session name to VM name if applicable
        resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_name, config)
        if resolved_vm_name:
            vm_name = resolved_vm_name

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


def _get_sync_vm_by_name(vm_name: str, rg: str):
    """Get and validate a specific VM for syncing."""
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

    return vm


def _select_sync_vm_interactive(rg: str):
    """Interactively select a VM for syncing."""
    vms = VMManager.list_vms(rg, include_stopped=False)
    vms = VMManager.filter_by_prefix(vms, "azlin")
    vms = [vm for vm in vms if vm.is_running() and vm.public_ip]

    if not vms:
        click.echo("No running VMs found.")
        sys.exit(1)

    if len(vms) == 1:
        selected_vm = vms[0]
        click.echo(f"Auto-selecting VM: {selected_vm.name}")
        return selected_vm

    # Show menu
    click.echo("\nSelect VM to sync to:")
    for idx, vm in enumerate(vms, 1):
        click.echo(f"  {idx}. {vm.name} - {vm.public_ip}")

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


def _execute_sync(selected_vm: VMInfo, ssh_key_pair: SSHKeyPair, dry_run: bool) -> None:
    """Execute the sync operation to the selected VM."""
    if not selected_vm.public_ip:
        click.echo("Error: VM has no public IP address", err=True)
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
        if not rg:
            click.echo("Error: Resource group required for VM name.", err=True)
            click.echo("Use --resource-group or set default in ~/.azlin/config.toml", err=True)
            sys.exit(1)

        # Resolve session name to VM name if applicable
        if vm_name:
            resolved_vm_name = ConfigManager.get_vm_name_by_session(vm_name, config)
            if resolved_vm_name:
                vm_name = resolved_vm_name

        # Get VM
        if vm_name:
            selected_vm = _get_sync_vm_by_name(vm_name, rg)
        else:
            selected_vm = _select_sync_vm_interactive(rg)

        # Execute sync
        _execute_sync(selected_vm, ssh_key_pair, dry_run)

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
            for vm in vms:
                display_name = vm.session_name or vm.name
                click.echo(f"  - {display_name} ({vm.name})", err=True)
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
    for vm in result.successful:
        session_name = ConfigManager.get_session_name(vm.name, config) if session_prefix else None
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

        # Load configuration and get resource group
        cfg = ConfigManager.load_config(config)
        rg = resource_group or cfg.default_resource_group
        if not rg:
            click.echo("Error: No resource group specified and no default configured", err=True)
            sys.exit(1)

        # Resolve and validate source VM
        source_vm_info = _validate_and_resolve_source_vm(source_vm, rg, config)

        # Ensure source VM is running
        source_vm_info = _ensure_source_vm_running(source_vm_info, rg)

        # Generate and display clone configurations
        click.echo(f"\nGenerating configurations for {num_replicas} clone(s)...")
        clone_configs = _generate_clone_configs(
            source_vm=source_vm_info,
            num_replicas=num_replicas,
            vm_size=vm_size,
            region=region,
        )

        click.echo("\nClone plan:")
        for i, clone_config in enumerate(clone_configs, 1):
            click.echo(f"  Clone {i}: {clone_config.name}")
            click.echo(f"    Size: {clone_config.size}")
            click.echo(f"    Region: {clone_config.location}")

        # Provision VMs
        result = _provision_clone_vms(clone_configs, num_replicas)

        # Copy home directories
        click.echo("\nCopying home directories from source VM...")
        ssh_key_path = Path.home() / ".ssh" / "id_rsa"
        copy_results = _copy_home_directories(
            source_vm=source_vm_info,
            clone_vms=result.successful,
            ssh_key_path=str(ssh_key_path),
            max_workers=min(5, len(result.successful)),
        )

        # Check copy results
        failed_copies = len(copy_results) - sum(1 for success in copy_results.values() if success)
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

        # Display results
        _display_clone_results(result, copy_results, session_prefix, config)

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


def _do_impl(  # noqa: C901
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

        # Parse natural language intent
        if verbose:
            click.echo(f"Parsing request: {request}")

        parser = IntentParser()
        intent = parser.parse(request, context=context if context else None)

        if verbose:
            click.echo("\nParsed Intent:")
            click.echo(f"  Type: {intent['intent']}")
            click.echo(f"  Confidence: {intent['confidence']:.1%}")
            if "explanation" in intent:
                click.echo(f"  Plan: {intent['explanation']}")

        # Check confidence
        if intent["confidence"] < 0.7:
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


@main.command()
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


@main.command()
@click.argument("objective", type=str)
@click.option("--dry-run", is_flag=True, help="Show execution plan without running")
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--verbose", "-v", is_flag=True, help="Show detailed execution information")
def doit(  # noqa: C901
    objective: str,
    dry_run: bool,
    resource_group: str | None,
    config: str | None,
    verbose: bool,
):
    """Enhanced agentic Azure infrastructure management.

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
            MCPClientStrategy,
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
            Strategy.MCP_CLIENT: MCPClientStrategy(),
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

                                    # Check if command contains pipes or redirects (shell features)
                                    if any(
                                        char in cmd for char in ["|", ">", "<", ";", "&", "`", "$("]
                                    ):
                                        # For complex shell commands, validate they're safe Az CLI commands
                                        if not cmd.strip().startswith(
                                            ("az ", "terraform ", "kubectl ")
                                        ):
                                            click.echo(
                                                "  ⚠️  Skipped: Only az/terraform/kubectl commands allowed for shell execution",
                                                err=True,
                                            )
                                            continue
                                        # Execute with shell for piped commands, but limit risk
                                        proc_result = subprocess.run(
                                            cmd,
                                            shell=True,  # nosec B602 - Commands from failure analyzer, validated above
                                            capture_output=True,
                                            text=True,
                                            timeout=30,
                                        )
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
def snapshot(ctx: click.Context) -> None:
    """Manage VM snapshots and scheduled backups.

    Enable scheduled snapshots, sync snapshots manually, or manage snapshot schedules.

    \b
    EXAMPLES:
        # Enable scheduled snapshots (every 24 hours, keep 2)
        $ azlin snapshot enable my-vm --every 24

        # Enable with custom retention (every 12 hours, keep 5)
        $ azlin snapshot enable my-vm --every 12 --keep 5

        # Sync snapshots now (checks all VMs with schedules)
        $ azlin snapshot sync

        # Sync specific VM
        $ azlin snapshot sync --vm my-vm

        # Disable scheduled snapshots
        $ azlin snapshot disable my-vm

        # Show snapshot schedule
        $ azlin snapshot status my-vm
    """
    pass


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


if __name__ == "__main__":
    main()


__all__ = ["AzlinError", "CLIOrchestrator", "azdoit_main", "main"]
