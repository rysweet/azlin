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
import random
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from azlin.modules.storage_manager import StorageInfo

import click

from azlin import __version__
from azlin.auth_models import AuthConfig, AuthMethod
from azlin.azure_auth import AuthenticationError, AzureAuthenticator
from azlin.click_group import AzlinGroup

# Ask commands (Natural Language Fleet Queries)
from azlin.commands.ask import ask_command, ask_group

# Auth commands
from azlin.commands.auth import auth

# Autopilot commands
from azlin.commands.autopilot import autopilot_group

# Bastion commands
# Storage commands
from azlin.commands.bastion import bastion_group

# Batch commands (Issue #423 - cli.py decomposition)
from azlin.commands.batch import batch as batch_group
from azlin.commands.compose import compose_group

# Connectivity commands (Issue #423 - cli.py decomposition)
from azlin.commands.connectivity import (
    code_command,
    connect,
    cp,
    sync,
    sync_keys,
    update,
)

# Context commands
from azlin.commands.context import context_group

# Doit commands
from azlin.commands.costs import costs_group
from azlin.commands.doit import doit_group

# Env commands (Issue #423 - cli.py decomposition)
from azlin.commands.env import env_group
from azlin.commands.fleet import fleet_group
from azlin.commands.github_runner import github_runner_group
from azlin.commands.ip_commands import ip

# Keys commands (Issue #423 - cli.py decomposition)
from azlin.commands.keys import keys_group

# Lifecycle commands (Issue #423 - cli.py decomposition)
from azlin.commands.lifecycle import destroy, kill, killall, prune, start, stop

# Monitoring/operations commands (Issue #423 - cli.py decomposition)
from azlin.commands.monitoring import (
    _create_tunnel_with_retry,
    _get_config_float,
    _get_config_int,
    cost,
    list_command,
    os_update,
    ps,
    session_command,
    status,
    top,
    w,
)

# NLP commands (Issue #423 - cli.py decomposition)
from azlin.commands.nlp import azdoit_main, do

# Provisioning commands (Issue #423 - cli.py decomposition)
from azlin.commands.provisioning import (
    clone,
    create_command,
    help_command,
    new_command,
    vm_command,
)

# Restore command
from azlin.commands.restore import restore_command

# Snapshot commands (Issue #423 - cli.py decomposition)
from azlin.commands.snapshots import snapshot as snapshot_group
from azlin.commands.storage import storage_group
from azlin.commands.tag import tag_group

# Template commands (Issue #423 - cli.py decomposition)
from azlin.commands.templates import template_group

# Web commands (Issue #423 - cli.py decomposition)
from azlin.commands.web import web_group

# New modules for v2.0
from azlin.config_manager import AzlinConfig, ConfigError, ConfigManager

# Backward compatibility imports for tests that patch azlin.cli.*
from azlin.context_manager import ContextManager  # noqa: F401

# ip_diagnostics imports moved to azlin.commands.ip_commands (Issue #423)
from azlin.modules.bastion_detector import BastionDetector, BastionInfo
from azlin.modules.bastion_manager import BastionManager, BastionManagerError
from azlin.modules.bastion_provisioner import BastionProvisioner
from azlin.modules.cost_estimator import CostEstimator
from azlin.modules.file_transfer.session_manager import SessionManager  # noqa: F401
from azlin.modules.github_setup import GitHubSetupError, GitHubSetupHandler
from azlin.modules.home_sync import (
    HomeSyncError,
    HomeSyncManager,
    SyncResult,
)
from azlin.modules.interaction_handler import CLIInteractionHandler
from azlin.modules.notifications import NotificationHandler
from azlin.modules.prerequisites import PrerequisiteChecker, PrerequisiteError
from azlin.modules.progress import ProgressDisplay, ProgressStage
from azlin.modules.resource_orchestrator import (
    BastionOptions,
    DecisionAction,
    ResourceOrchestrator,
)
from azlin.modules.ssh_connector import SSHConfig, SSHConnectionError, SSHConnector
from azlin.modules.ssh_key_vault import (
    KeyVaultError,
    create_key_vault_manager_with_auto_setup,
)
from azlin.modules.ssh_keys import SSHKeyError, SSHKeyManager, SSHKeyPair
from azlin.remote_exec import RemoteExecutor, TmuxSessionExecutor  # noqa: F401
from azlin.security_audit import SecurityAuditLogger
from azlin.tag_manager import TagManager  # noqa: F401
from azlin.vm_connector import VMConnector, VMConnectorError
from azlin.vm_manager import VMInfo, VMManager  # noqa: F401
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
        no_nfs: bool = False,
        session_name: str | None = None,
        no_bastion: bool = False,
        bastion_name: str | None = None,
        auto_approve: bool = False,
        home_disk_size: int | None = None,
        no_home_disk: bool = False,
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
            no_nfs: Skip NFS storage mounting (use local home directory only)
            session_name: Session name for VM tags (optional)
            no_bastion: Skip bastion auto-detection and always create public IP (optional)
            bastion_name: Explicit bastion host name to use (optional)
            auto_approve: Accept all defaults and confirmations (non-interactive mode)
            home_disk_size: Size of separate /home disk in GB (optional, default: 100)
            no_home_disk: Disable separate /home disk (use OS disk only)

        Note:
            SSH keys are automatically stored in Azure Key Vault (transparent operation)
        """
        self.repo = repo
        self.vm_size = vm_size
        self.region = region
        self.resource_group = resource_group
        self.auto_connect = auto_connect
        self.config_file = config_file
        self.nfs_storage = nfs_storage
        self.no_nfs = no_nfs
        self.session_name = session_name
        self.no_bastion = no_bastion
        self.bastion_name = bastion_name
        self.auto_approve = auto_approve
        self.home_disk_size = home_disk_size
        self.no_home_disk = no_home_disk

        # Initialize modules
        self.auth = AzureAuthenticator()
        self.provisioner = VMProvisioner()
        self.progress = ProgressDisplay()

        # Track resources for cleanup
        self.vm_details: VMDetails | None = None
        self.ssh_keys: Path | None = None
        self.bastion_info: BastionInfo | None = None  # Track bastion if detected

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
            rg_name = self.resource_group or f"azlin-rg-{timestamp}"

            # Determine VM name: use session name if provided and valid
            if self.session_name:
                # Validate against Azure VM naming rules
                is_valid, error_msg = VMProvisioner.validate_azure_vm_name(self.session_name)
                if not is_valid:
                    self.progress.complete(success=False)
                    raise ValueError(
                        f"Session name '{self.session_name}' is not valid as Azure VM name: {error_msg}\n"
                        f"Azure VM naming rules:\n"
                        f"  - Length: 1-64 characters\n"
                        f"  - Allowed: alphanumeric, hyphen (-), period (.)\n"
                        f"  - Must start with alphanumeric character\n"
                        f"  - Cannot end with hyphen or period"
                    )

                # Check if VM with this name already exists
                if VMProvisioner.check_vm_exists(self.session_name, rg_name):
                    self.progress.complete(success=False)
                    raise ValueError(
                        f"VM with name '{self.session_name}' already exists in resource group '{rg_name}'. "
                        f"Please choose a different session name or delete the existing VM."
                    )

                vm_name = self.session_name
                logger.info(f"Using session name as VM name: {vm_name}")
            else:
                # Backward compatible: generate timestamp-based name
                vm_name = f"azlin-vm-{timestamp}"
                logger.info(f"No session name provided, using generated name: {vm_name}")

            # STEP 3.5: Pre-check storage account (if NFS storage is configured)
            # This prevents late failures after expensive VM provisioning
            if not self.no_nfs:
                self.progress.start_operation("Checking storage configuration")
                try:
                    # Load config to check for default_nfs_storage
                    try:
                        azlin_config = ConfigManager.load_config(self.config_file)
                    except ConfigError:
                        azlin_config = AzlinConfig()

                    # Pre-check storage and offer to create if needed
                    self._check_and_create_storage_if_needed(rg_name, azlin_config)
                    self.progress.complete(success=True, message="Storage configuration validated")
                except ValueError as e:
                    # Storage check failed (user declined to create, or creation failed)
                    self.progress.complete(success=False)
                    raise ProvisioningError(str(e)) from e

            self.progress.start_operation(f"Provisioning VM: {vm_name}", estimated_seconds=300)
            vm_details = self._provision_vm(vm_name, rg_name, ssh_key_pair.public_key_content)
            self.vm_details = vm_details
            self.progress.complete(success=True, message=f"VM ready at {vm_details.public_ip}")

            # STEP 4.5: Store SSH key in Key Vault (automatic, silent)
            tenant_id = self.auth.get_tenant_id()
            self._store_key_in_vault_auto(
                vm_name,
                ssh_key_pair.private_path,
                subscription_id,
                tenant_id,
                rg_name,
                vm_details.location,
            )

            # STEP 5: Wait for VM to be fully ready (cloud-init to complete)
            self.progress.start_operation(
                "Waiting for cloud-init to complete", estimated_seconds=180
            )
            self._wait_for_cloud_init(vm_details, ssh_key_pair.private_path)
            self.progress.complete(success=True, message="All development tools installed")

            # STEP 5.5: Resolve and mount NFS storage if configured (BEFORE home sync)
            if self.no_nfs:
                logger.info("Skipping NFS storage mount (--no-nfs flag set)")
                click.echo("VM will use local home directory only (NFS disabled)")
            else:
                # Load config for NFS defaults
                try:
                    azlin_config = ConfigManager.load_config(self.config_file)
                except ConfigError:
                    azlin_config = AzlinConfig()

                resolved_storage = self._resolve_nfs_storage(rg_name, azlin_config)

                if resolved_storage:
                    self.progress.start_operation(f"Mounting NFS storage: {resolved_storage.name}")
                    self._mount_nfs_storage(vm_details, ssh_key_pair.private_path, resolved_storage)
                    self.progress.complete(success=True, message="NFS storage mounted")

            # Always sync home directory (provides initial dotfiles even with NFS)
            # NFS provides persistence, ~/.azlin/home provides initial configuration
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

    def _store_key_in_vault_auto(
        self,
        vm_name: str,
        private_key_path: Path,
        subscription_id: str,
        tenant_id: str,
        resource_group: str,
        location: str,
    ) -> None:
        """Store SSH private key in Azure Key Vault with automatic setup.

        This method automatically:
        1. Finds or creates Key Vault in resource group
        2. Assigns RBAC permissions to current user
        3. Stores SSH key

        Args:
            vm_name: VM name (used in secret name)
            private_key_path: Path to private key file
            subscription_id: Azure subscription ID
            tenant_id: Azure tenant ID
            resource_group: Resource group name
            location: Azure region

        Note:
            - Silent operation (only logs at debug level)
            - Does not fail provisioning if Key Vault storage fails
        """
        try:
            # Build auth config (Azure CLI by default)
            auth_config = AuthConfig(method=AuthMethod.AZURE_CLI)

            # Create Key Vault manager with automatic setup
            manager = create_key_vault_manager_with_auto_setup(
                resource_group=resource_group,
                location=location,
                subscription_id=subscription_id,
                tenant_id=tenant_id,
                auth_config=auth_config,
            )

            # Store key
            manager.store_key(vm_name, private_key_path)

            logger.debug(f"SSH key stored in Key Vault for VM: {vm_name}")

        except KeyVaultError as e:
            # Silent failure - don't block VM provisioning
            logger.debug(f"Key Vault storage skipped: {e}")
        except Exception as e:
            # Silent failure - don't block VM provisioning
            logger.debug(f"Key Vault storage error: {e}")

    def _check_bastion_availability(
        self, resource_group: str, vm_name: str
    ) -> tuple[bool, BastionInfo | None]:
        """Check if Bastion should be used for VM provisioning.

        This method implements the bastion default behavior:
        1. If --no-bastion flag is set, skip bastion (return False, None)
        2. Auto-detect bastion in resource group
        3. If found, prompt user with default=True
        4. If not found, prompt to create with default=True
        5. If user declines, return False to use public IP

        Args:
            resource_group: Resource group where VM will be created
            vm_name: Name of the VM being provisioned

        Returns:
            Tuple of (use_bastion: bool, bastion_info: dict | None)
            - use_bastion: Whether to provision VM without public IP
            - bastion_info: Bastion details if available (name, resource_group)

        Raises:
            No exceptions - all failures result in returning (False, None)
        """
        # Skip bastion if --no-bastion flag is set
        if self.no_bastion:
            # Confirm with user about security implications
            warning_message = (
                f"\nWARNING: --no-bastion flag will create VM '{vm_name}' with PUBLIC IP.\n"
                f"This exposes your VM directly to the internet, which is LESS SECURE.\n"
                f"Continue with public IP?"
            )
            if not self.auto_approve and not click.confirm(warning_message, default=False):
                self.progress.update("User cancelled VM creation", ProgressStage.WARNING)
                raise click.Abort

            # Log security decision
            SecurityAuditLogger.log_bastion_opt_out(
                vm_name=vm_name,
                method="flag",
                user=None,  # Will use system user
            )

            self.progress.update(
                "Skipping bastion (--no-bastion flag set)", ProgressStage.IN_PROGRESS
            )
            return (False, None)

        # If explicit bastion name provided, use it
        if self.bastion_name:
            self.progress.update(
                f"Using explicit bastion: {self.bastion_name}", ProgressStage.IN_PROGRESS
            )
            return (
                True,
                {"name": self.bastion_name, "resource_group": resource_group, "location": None},
            )

        # Auto-detect bastion in resource group
        try:
            self.progress.update(
                "Checking for Bastion host in resource group...", ProgressStage.IN_PROGRESS
            )
            bastion_info = BastionDetector.detect_bastion_for_vm(
                "temp-check", resource_group, self.region
            )

            if bastion_info:
                # Found bastion - prompt user with default=True (or auto-approve)
                if self.auto_approve:
                    # Non-interactive mode: use Bastion by default
                    self.progress.update(
                        f"Using Bastion: {bastion_info['name']} (auto-approved)",
                        ProgressStage.IN_PROGRESS,
                    )
                    return (True, bastion_info)

                message = (
                    f"\nFound Bastion host '{bastion_info['name']}' in resource group.\n"
                    f"\nOptions:\n"
                    f"  - Bastion: Private VM (no public IP, more secure)\n"
                    f"  - No Bastion: Public IP (direct SSH, less secure)\n"
                    f"\nUse Bastion for secure access (recommended)?"
                )
                if self.auto_approve or click.confirm(message, default=True):
                    self.progress.update(
                        f"Using Bastion: {bastion_info['name']}", ProgressStage.IN_PROGRESS
                    )
                    return (True, bastion_info)

                # User declined existing bastion - log security decision
                SecurityAuditLogger.log_bastion_opt_out(
                    vm_name=vm_name, method="prompt_existing", user=None
                )
                self.progress.update(
                    "User declined Bastion, will create public IP", ProgressStage.IN_PROGRESS
                )
                return (False, None)
            # No bastion found - prompt to create with default=True (or auto-approve)
            if self.auto_approve:
                # Non-interactive mode: create Bastion by default
                self.progress.update(
                    "No Bastion found - will create one (auto-approved)", ProgressStage.IN_PROGRESS
                )
                # Skip to Bastion creation logic below
            else:
                message = (
                    f"\nNo Bastion host found in resource group '{resource_group}'.\n"
                    f"\nOptions:\n"
                    f"  - Yes: More secure (private VM, ~$140/month for Bastion)\n"
                    f"  - No: Less secure (public IP, direct internet access)\n"
                    f"\nCreate VM with Bastion access?"
                )
                if not self.auto_approve and not click.confirm(message, default=True):
                    # User declined - abort per security policy
                    self.progress.update("User declined Bastion creation", ProgressStage.FAILED)
                    click.echo(
                        click.style(
                            "\n⚠️  Cannot create VM without Bastion (security policy: no public IPs on VMs).\n"
                            "To proceed, either:\n"
                            f"  1. Accept Bastion creation in {self.region}\n"
                            f"  2. Use --no-bastion flag to override (not recommended)\n",
                            fg="yellow",
                            bold=True,
                        )
                    )
                    raise click.Abort

            # User approved (or auto-approved) - proceed with Bastion creation
            if True:
                # User wants Bastion - use orchestrator to create it
                try:
                    self.progress.update(
                        "Preparing to create Bastion host...", ProgressStage.IN_PROGRESS
                    )

                    # Initialize orchestrator with CLI handler and cost estimator
                    # Use MockInteractionHandler in auto-approve mode to accept defaults
                    if self.auto_approve:
                        from azlin.modules.interaction_handler import MockInteractionHandler

                        # Pre-program to select option 1 (CREATE) for ALL prompts
                        # Need multiple entries for: Bastion + NFS + any other prompts
                        interaction_handler = MockInteractionHandler(
                            choice_responses=[
                                0,
                                0,
                                0,
                                0,
                            ],  # Index 0 = option 1 (CREATE) - enough for all prompts
                            confirm_responses=[True, True, True, True],
                        )
                    else:
                        interaction_handler = CLIInteractionHandler()

                    orchestrator = ResourceOrchestrator(
                        interaction_handler=interaction_handler,
                        cost_estimator=CostEstimator(),
                    )

                    # Get user decision via orchestrator
                    # SECURITY POLICY: No public IPs on VMs, only on Bastion hosts
                    decision = orchestrator.ensure_bastion(
                        BastionOptions(
                            region=self.region,
                            resource_group=resource_group,
                            vnet_name=None,  # Will auto-create VNet if needed
                            vnet_id=None,
                            bastion_subnet_id=None,
                            sku="Standard",
                            allow_public_ip_fallback=False,  # NEVER allow public IP on VMs
                        )
                    )

                    if decision.action == DecisionAction.CREATE:
                        # Create Bastion now
                        bastion_name = f"azlin-bastion-{self.region}"
                        self.progress.update(
                            f"Creating Bastion host '{bastion_name}' (this may take 5-10 minutes)...",
                            ProgressStage.IN_PROGRESS,
                        )

                        result = BastionProvisioner.provision_bastion(
                            bastion_name=bastion_name,
                            resource_group=resource_group,
                            location=self.region,
                            vnet_name=None,  # Auto-create VNet
                            wait_for_completion=True,  # Wait for Bastion to be ready
                        )

                        if result.success:
                            self.progress.update(
                                f"Bastion created successfully: {result.bastion_name}",
                                ProgressStage.COMPLETED,
                            )
                            return (
                                True,
                                {
                                    "name": result.bastion_name,
                                    "resource_group": resource_group,
                                    "location": self.region,
                                },
                            )
                        # Bastion creation failed
                        self.progress.update(
                            f"Bastion creation failed: {result.error_message}",
                            ProgressStage.FAILED,
                        )
                        raise ProvisioningError(
                            f"Failed to create Bastion host: {result.error_message}"
                        )

                    if decision.action == DecisionAction.SKIP:
                        # User declined to create Bastion
                        # SECURITY POLICY: No public IPs on VMs allowed
                        self.progress.update(
                            "Bastion required but user declined creation", ProgressStage.FAILED
                        )
                        click.echo(
                            click.style(
                                "\n⚠️  Cannot create VM without Bastion (security policy: no public IPs on VMs).\n"
                                "To proceed, either:\n"
                                f"  1. Accept Bastion creation in {self.region}\n"
                                f"  2. Use --no-bastion flag to override (not recommended)\n",
                                fg="yellow",
                                bold=True,
                            )
                        )
                        raise click.Abort

                    # CANCEL
                    self.progress.update("User cancelled operation", ProgressStage.WARNING)
                    raise click.Abort

                except ProvisioningError:
                    # Re-raise provisioning errors
                    raise
                except click.Abort:
                    # Re-raise user cancellation
                    raise
                except Exception as e:
                    # Handle unexpected orchestration errors
                    logger.error(f"Bastion orchestration failed: {e}")
                    self.progress.update(f"Bastion creation failed: {e!s}", ProgressStage.FAILED)
                    raise ProvisioningError(f"Failed to orchestrate Bastion creation: {e!s}") from e

            # User declined creating bastion
            # SECURITY POLICY: No public IPs on VMs
            self.progress.update("User declined Bastion creation", ProgressStage.FAILED)
            click.echo(
                click.style(
                    "\n⚠️  Cannot create VM without Bastion (security policy: no public IPs on VMs).\n"
                    "To proceed, either:\n"
                    f"  1. Accept Bastion creation in {self.region}\n"
                    f"  2. Use --no-bastion flag to override (not recommended)\n",
                    fg="yellow",
                    bold=True,
                )
            )
            raise click.Abort

        except (ProvisioningError, click.Abort):
            # Re-raise critical errors - don't fall back to public IP
            raise
        except Exception as e:
            # Any error in detection - abort (no public IP fallback)
            logger.error(f"Bastion detection failed: {e}")
            self.progress.update("Bastion detection failed", ProgressStage.FAILED)
            click.echo(
                click.style(
                    f"\n⚠️  Bastion detection failed: {e}\n"
                    "Cannot create VM without Bastion (security policy: no public IPs on VMs).\n"
                    f"Use --no-bastion flag to override if needed.\n",
                    fg="red",
                    bold=True,
                )
            )
            raise ProvisioningError(f"Bastion detection failed: {e}") from e

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

        # Check bastion availability and get user preference
        use_bastion, bastion_info = self._check_bastion_availability(rg_name, vm_name)
        self.bastion_info = bastion_info  # Store for later use in connection

        # Determine if public IP should be created
        # Public IP is disabled when using bastion
        public_ip_enabled = not use_bastion

        # Determine home disk configuration
        # Home disk is enabled by default UNLESS:
        # 1. User explicitly disabled it with --no-home-disk
        # 2. NFS storage is configured (NFS replaces separate home disk)
        has_nfs_storage = bool(self.nfs_storage)
        if not has_nfs_storage and not self.no_nfs:
            # Check for default NFS storage in config
            try:
                azlin_config = ConfigManager.load_config(self.config_file)
                has_nfs_storage = bool(azlin_config.default_nfs_storage)
            except ConfigError:
                has_nfs_storage = False

        home_disk_enabled = not self.no_home_disk and not has_nfs_storage
        home_disk_size = self.home_disk_size or 100

        # Create VM config
        config = self.provisioner.create_vm_config(
            name=vm_name,
            resource_group=rg_name,
            location=self.region,
            size=self.vm_size,
            ssh_public_key=public_key,
            session_name=self.session_name,
            public_ip_enabled=public_ip_enabled,
            home_disk_enabled=home_disk_enabled,
            home_disk_size_gb=home_disk_size,
            home_disk_sku="Standard_LRS",
        )

        # Progress callback
        def progress_callback(msg: str):
            self.progress.update(msg, ProgressStage.IN_PROGRESS)

        # Provision VM
        vm_details = self.provisioner.provision_vm(config, progress_callback)

        # Update progress message based on IP configuration
        if vm_details.public_ip:
            self.progress.update(f"VM created with public IP: {vm_details.public_ip}")
        else:
            self.progress.update(
                f"VM created with private IP: {vm_details.private_ip} (Bastion access)"
            )

        return vm_details

    def _get_ssh_connection_params(
        self, vm_details: VMDetails
    ) -> tuple[str, int, BastionManager | None]:
        """Get SSH connection parameters (host, port, bastion_manager).

        For VMs with public IPs, returns (public_ip, 22, None) for direct connection.
        For Bastion-only VMs, creates a tunnel and returns (localhost, local_port, bastion_manager).

        Args:
            vm_details: VM details with IP configuration

        Returns:
            Tuple of (host, port, bastion_manager_or_none)

        Raises:
            SSHConnectionError: If no connection method available
        """
        # Public IP VMs: Direct SSH
        if vm_details.public_ip:
            logger.debug(f"Using direct SSH to {vm_details.public_ip}:22")
            return (vm_details.public_ip, 22, None)

        # Bastion-only VMs: Create tunnel
        if not vm_details.private_ip:
            raise SSHConnectionError("VM has neither public nor private IP")

        # Detect Bastion
        logger.info("No public IP - attempting Bastion detection...")
        bastion_info = BastionDetector.detect_bastion_for_vm(
            vm_details.name, vm_details.resource_group, vm_details.location
        )

        if not bastion_info:
            raise SSHConnectionError(
                f"VM {vm_details.name} has no public IP and no Bastion host detected"
            )

        # Create Bastion tunnel
        logger.info(f"Creating Bastion tunnel via {bastion_info['name']} to {vm_details.name}...")
        bastion_manager = BastionManager()

        # Get VM resource ID (needed for Bastion tunnel)
        if not vm_details.id:
            raise SSHConnectionError("VM resource ID not available")

        # Allocate local port
        local_port = bastion_manager.get_available_port()

        # Create tunnel
        bastion_manager.create_tunnel(
            bastion_name=bastion_info["name"],
            resource_group=bastion_info["resource_group"],
            target_vm_id=vm_details.id,
            local_port=local_port,
            remote_port=22,
            wait_for_ready=True,
            timeout=30,
        )

        logger.info(f"Bastion tunnel established on localhost:{local_port}")
        return ("127.0.0.1", local_port, bastion_manager)

    def _wait_for_cloud_init(
        self, vm_details: VMDetails, key_path: Path, newly_provisioned: bool = True
    ) -> None:
        """Wait for cloud-init to complete on VM.

        Supports both direct SSH (public IP) and Bastion tunnels (private IP only).

        Args:
            vm_details: VM details (may or may not have public_ip)
            key_path: SSH private key path

        Raises:
            SSHConnectionError: If cloud-init check fails or no access method available
        """
        # Path 1: Public IP exists (existing behavior)
        if vm_details.public_ip:
            self._wait_for_cloud_init_via_public_ip(vm_details, key_path)
            return

        # Path 2: No public IP - try Bastion
        self.progress.update("VM has no public IP, checking for Bastion access...")

        bastion_info = BastionDetector.detect_bastion_for_vm(
            vm_name=vm_details.name,
            resource_group=vm_details.resource_group,
            vm_location=vm_details.location,
        )

        if not bastion_info:
            raise SSHConnectionError(
                f"VM {vm_details.name} has no public IP and no Bastion host found "
                f"in region '{vm_details.location}'. Cannot access VM for cloud-init check.\n"
                f"Bastion must be in the same region as the VM."
            )

        # Use Bastion tunnel
        self._wait_for_cloud_init_via_bastion(vm_details, key_path, bastion_info)

    def _wait_for_cloud_init_via_public_ip(self, vm_details: VMDetails, key_path: Path) -> None:
        """Wait for cloud-init via direct public IP access.

        Args:
            vm_details: VM details with public_ip
            key_path: SSH private key path
            newly_provisioned: Whether this is a newly provisioned VM (default: True)
                             If True and using Bastion, waits for VM boot before SSH

        Raises:
            SSHConnectionError: If cloud-init check fails
        """
        self.progress.update("Waiting for SSH to be available...")

        # Wait for SSH port to be accessible (direct public IP access)
        # Assert for type narrowing - caller ensures public_ip exists
        assert vm_details.public_ip is not None, "VM must have public IP for direct SSH access"
        public_ip: str = vm_details.public_ip
        ssh_ready = SSHConnector.wait_for_ssh_ready(public_ip, key_path, timeout=300, interval=5)

        if not ssh_ready:
            raise SSHConnectionError("SSH did not become available after 300s timeout")

        self.progress.update("SSH available, checking cloud-init status...")

        # Check cloud-init status
        ssh_config = SSHConfig(host=public_ip, port=22, user="azureuser", key_path=key_path)

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

    def _wait_for_cloud_init_via_bastion(
        self, vm_details: VMDetails, key_path: Path, bastion_info: BastionInfo
    ) -> None:
        """Wait for cloud-init via Bastion tunnel.

        Args:
            vm_details: VM details (must have .id for resource ID)
            key_path: SSH private key path
            bastion_info: Dict with 'name' and 'resource_group' keys

        Raises:
            SSHConnectionError: If tunnel creation or cloud-init check fails
        """
        # STEP 0: Validate prerequisites (fail-fast)
        if not vm_details.id:
            raise SSHConnectionError(
                f"VM {vm_details.name} has no resource ID. Cannot create Bastion tunnel."
            )

        # Create Bastion manager (tracks all tunnels for cleanup)
        bastion_mgr = BastionManager()

        try:
            # Step 1: Find available port
            self.progress.update("Allocating local port for Bastion tunnel...")
            local_port = bastion_mgr.get_available_port()

            # Step 2: Create tunnel with retry logic (60s timeout, Issue #588)
            self.progress.update(
                f"Creating Bastion tunnel via {bastion_info['name']} (localhost:{local_port})..."
            )

            retry_attempts = _get_config_int("AZLIN_BASTION_RETRY_ATTEMPTS", 3)
            last_error: Exception | None = None

            for attempt in range(1, retry_attempts + 1):
                try:
                    _tunnel = bastion_mgr.create_tunnel(
                        bastion_name=bastion_info["name"],
                        resource_group=bastion_info["resource_group"],
                        target_vm_id=vm_details.id,
                        local_port=local_port,
                        remote_port=22,
                        wait_for_ready=True,
                        timeout=60,
                    )
                    break  # Success
                except (BastionManagerError, TimeoutError) as e:
                    last_error = e
                    if attempt < retry_attempts:
                        delay = 1.0 * (2 ** (attempt - 1))
                        delay *= 1 + random.uniform(-0.2, 0.2)  # noqa: S311
                        self.progress.update(
                            f"Tunnel creation failed (attempt {attempt}/{retry_attempts}), "
                            f"retrying in {delay:.0f}s..."
                        )
                        time.sleep(delay)
                    else:
                        raise BastionManagerError(
                            f"Failed to create Bastion tunnel after {retry_attempts} attempts"
                        ) from e

            self.progress.update("Bastion tunnel established")

            # Step 3: Wait for SSH through tunnel
            # Tunnel is already established, so SSH should be ready quickly
            # 2-minute timeout (vs 5 minutes for public IP path)
            self.progress.update("Waiting for SSH through Bastion tunnel...")

            ssh_ready = SSHConnector.wait_for_ssh_ready(
                host="127.0.0.1", key_path=key_path, port=local_port, timeout=120, interval=5
            )

            if not ssh_ready:
                raise SSHConnectionError(
                    "SSH did not become available through Bastion tunnel after 120s"
                )

            self.progress.update("SSH available, checking cloud-init status...")

            # Step 4: Check cloud-init status (same as public IP path)
            ssh_config = SSHConfig(
                host="127.0.0.1",
                port=local_port,
                user=SSHConnector.DEFAULT_USER,
                key_path=key_path,
            )

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
                        # Only show progress every 3rd attempt (every 30s) to reduce noise
                        if attempt % 3 == 0:
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

        except BastionManagerError as e:
            raise SSHConnectionError(f"Bastion tunnel error: {e}") from e
        finally:
            # Step 5: Always cleanup ALL tunnels (even if creation failed mid-way)
            # BastionManager tracks all tunnels, even those that fail during readiness wait
            if bastion_mgr.active_tunnels:
                self.progress.update("Closing Bastion tunnel...")
                bastion_mgr.close_all_tunnels()
                logger.info("Bastion tunnel(s) closed")

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

        Supports both direct connection (public IP) and Bastion routing (private IP only).

        Args:
            vm_details: VM details
            key_path: SSH private key path

        Note:
            Sync failures are logged as warnings but don't block VM provisioning.
        """
        # Check if VM has any IP address
        if not vm_details.public_ip and not vm_details.private_ip:
            logger.warning(
                "VM has no IP address (neither public nor private), skipping home directory sync"
            )
            return

        try:
            # Pre-sync validation check with visible warnings
            sync_dir = HomeSyncManager.get_sync_directory()
            if sync_dir.exists():
                validation = HomeSyncManager.validate_sync_directory(sync_dir)
                if validation.blocked_files:
                    self._show_blocked_files_warning(validation.blocked_files)

            # Progress callback
            def progress_callback(msg: str):
                self.progress.update(msg, ProgressStage.IN_PROGRESS)

            # Direct connection if public IP available
            if vm_details.public_ip:
                ssh_config = SSHConfig(
                    host=vm_details.public_ip, user="azureuser", key_path=key_path
                )
                result = HomeSyncManager.sync_to_vm(
                    ssh_config, dry_run=False, progress_callback=progress_callback
                )
                self._process_sync_result(result)
                return

            # Bastion routing for private IP only VMs
            # Detect Bastion
            bastion_info = BastionDetector.detect_bastion_for_vm(
                vm_name=vm_details.name,
                resource_group=vm_details.resource_group,
                vm_location=vm_details.location,
            )

            if not bastion_info:
                logger.warning(
                    f"VM '{vm_details.name}' has no public IP and no Bastion host detected, "
                    f"skipping home directory sync"
                )
                return

            # Verify VM ID is available (required for Bastion tunnel)
            if not vm_details.id:
                logger.warning(
                    f"VM '{vm_details.name}' has no Azure resource ID, cannot create Bastion tunnel"
                )
                return

            # Create tunnel and sync
            self.progress.update(
                f"Creating Bastion tunnel via {bastion_info['name']}...", ProgressStage.IN_PROGRESS
            )

            with BastionManager() as bastion_mgr:
                # Get available port
                local_port = bastion_mgr.get_available_port()

                # Create tunnel
                _tunnel = bastion_mgr.create_tunnel(
                    bastion_name=bastion_info["name"],
                    resource_group=bastion_info["resource_group"],
                    target_vm_id=vm_details.id,  # Type narrowed by check above
                    local_port=local_port,
                    remote_port=22,
                    wait_for_ready=True,
                )

                # Create SSH config using tunnel
                ssh_config = SSHConfig(
                    host="127.0.0.1", port=local_port, user="azureuser", key_path=key_path
                )

                # Perform sync through tunnel
                result = HomeSyncManager.sync_to_vm(
                    ssh_config, dry_run=False, progress_callback=progress_callback
                )
                self._process_sync_result(result)

        except BastionManagerError as e:
            # Don't fail VM provisioning, just warn
            self.progress.update(f"Home sync failed (Bastion error): {e}", ProgressStage.WARNING)
            logger.warning(f"Home sync failed (Bastion error): {e}")

        except HomeSyncError as e:
            # Don't fail VM provisioning, just warn
            self.progress.update(f"Home sync failed: {e}", ProgressStage.WARNING)
            logger.warning(f"Home sync failed: {e}")

        except Exception:
            # Catch all other errors
            self.progress.update("Home sync failed (unexpected error)", ProgressStage.WARNING)
            logger.exception("Unexpected error during home sync")

    def _lookup_storage_by_name(
        self, resource_group: str, storage_name: str, require_same_region: bool = True
    ) -> "StorageInfo":
        """Lookup storage by name, raising ValueError if not found.

        Args:
            resource_group: Resource group to search in
            storage_name: Name of storage account to find
            require_same_region: If True, raises ValueError for cross-region storage.
                                If False, allows cross-region storage with info log.

        Returns:
            StorageInfo object for the storage account

        Raises:
            ValueError: If storage account not found in resource group, or if
                       require_same_region=True and storage is in different region
        """
        from azlin.modules.storage_manager import StorageManager

        storages = StorageManager.list_storage(resource_group)
        storage = next((s for s in storages if s.name == storage_name), None)
        if not storage:
            raise ValueError(
                f"Storage account '{storage_name}' not found in resource group '{resource_group}'. "
                f"Create it first with: azlin storage create {storage_name}"
            )

        # Cross-region validation
        if storage.region.lower() != self.region.lower():
            if require_same_region:
                raise ValueError(
                    f"Storage account '{storage_name}' is in region '{storage.region}', "
                    f"but VM will be in region '{self.region}'. "
                    f"Cross-region NFS storage is not supported. "
                    f"Please create storage in the same region or use --region {storage.region}."
                )
            # Note: Cross-region storage is now handled in _mount_nfs_storage()
            # with private endpoint setup via ResourceOrchestrator
            logger.info(
                f"Storage account '{storage_name}' is in region '{storage.region}', "
                f"VM will be in region '{self.region}'. Cross-region access will be handled during mount."
            )

        return storage

    def _try_lookup_storage_by_name(
        self, resource_group: str, storage_name: str
    ) -> "StorageInfo | None":
        """Gracefully lookup storage by name, returning None on any failure.

        This is the "graceful" version used for Priority 2 (config file default).
        Returns None instead of raising exceptions, with warning logs for fallback.

        Args:
            resource_group: Resource group to search in
            storage_name: Name of storage account to find

        Returns:
            StorageInfo object if found and in same region, None otherwise
        """
        from azlin.modules.storage_manager import StorageManager

        try:
            storages = StorageManager.list_storage(resource_group)
        except Exception as e:
            logger.warning(
                f"Could not list storage accounts in resource group '{resource_group}': {e}. "
                f"Skipping config default storage '{storage_name}'."
            )
            return None

        storage = next((s for s in storages if s.name == storage_name), None)
        if not storage:
            logger.warning(
                f"Config default storage '{storage_name}' not found in resource group '{resource_group}'. "
                f"Falling back to auto-detection."
            )
            return None

        # Cross-region validation for Priority 2
        if storage.region.lower() != self.region.lower():
            logger.info(
                f"Default storage '{storage_name}' is in {storage.region}, "
                f"VM will be in {self.region}. Cross-region mount will be configured."
            )

        return storage

    def _check_and_create_storage_if_needed(
        self, resource_group: str, config: AzlinConfig | None
    ) -> None:
        """Pre-check storage account existence and offer to create if missing.

        This method runs BEFORE VM provisioning to prevent late failures
        after expensive VM creation. If a storage account is configured
        but doesn't exist, it offers to create it interactively.

        Args:
            resource_group: Resource group to check/create storage in
            config: Configuration object (optional)

        Raises:
            ValueError: If storage is required but doesn't exist and user declines to create
        """
        from azlin.modules.storage_manager import StorageManager

        # Determine which storage we'll need (same logic as _resolve_nfs_storage)
        storage_name = None
        if self.nfs_storage:
            # Priority 1: Explicit --nfs-storage option
            storage_name = self.nfs_storage
        elif config and config.default_nfs_storage:
            # Priority 2: Config file default
            storage_name = config.default_nfs_storage
        else:
            # Priority 3: Auto-detect (will check during mount, no pre-check needed)
            logger.debug("No storage explicitly configured, will auto-detect if needed")
            return

        # Check if storage exists
        try:
            storages = StorageManager.list_storage(resource_group)
        except Exception as e:
            logger.warning(f"Could not list storage accounts: {e}")
            # Can't verify, proceed and let mount phase handle it
            return

        storage_exists = any(s.name == storage_name for s in storages)

        if not storage_exists:
            # Storage is missing - offer to create
            click.echo(
                f"\n⚠️  Storage account '{storage_name}' not found in resource group '{resource_group}'."
            )
            click.echo("   This storage is required for VM home directory persistence.")

            if click.confirm(f"\n   Create storage account '{storage_name}' now?", default=True):
                # User accepted - create storage
                click.echo(f"\nCreating storage account '{storage_name}'...")
                click.echo(f"  Resource Group: {resource_group}")
                click.echo(f"  Region: {self.region}")
                click.echo("  Tier: Premium (high performance)")
                click.echo("  Size: 100GB")

                # Calculate cost
                monthly_cost = 100 * 0.153  # Premium tier cost
                click.echo(f"  Estimated cost: ${monthly_cost:.2f}/month")

                try:
                    result = StorageManager.create_storage(
                        name=storage_name,
                        resource_group=resource_group,
                        region=self.region,
                        tier="Premium",  # Default to Premium for performance
                        size_gb=100,  # Default size
                    )
                    click.echo(f"\n✓ Storage account created: {result.name}")
                except Exception as e:
                    raise ValueError(
                        f"Failed to create storage account '{storage_name}': {e}\n"
                        f"Create it manually with: azlin storage create {storage_name}"
                    ) from e
            else:
                # User declined - fail fast before VM provisioning
                raise ValueError(
                    f"Storage account '{storage_name}' is required but was not created.\n"
                    f"Create it with: azlin storage create {storage_name}\n"
                    f"Or use --no-nfs to skip NFS storage mounting."
                )

    def _resolve_nfs_storage(
        self, resource_group: str, config: AzlinConfig | None
    ) -> "StorageInfo | None":
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
            StorageInfo object or None

        Raises:
            ValueError: If multiple storages exist without explicit choice
        """
        from azlin.modules.storage_manager import StorageManager

        # Priority 1: Explicit --nfs-storage option (strict - raises on cross-region)
        if self.nfs_storage:
            return self._lookup_storage_by_name(resource_group, self.nfs_storage)

        # Priority 2: Config file default (graceful - falls back to Priority 3 on cross-region)
        if config and config.default_nfs_storage:
            storage = self._try_lookup_storage_by_name(resource_group, config.default_nfs_storage)
            if storage:
                self.progress.update(
                    f"Using config default NFS storage: {storage.name} (region: {storage.region})"
                )
                return storage
            # Fall through to Priority 3 if config storage not found or cross-region

        # Priority 3: Auto-detect (more permissive than explicit/config)
        # Note: If storage listing fails during auto-detection, we fallback to
        # home sync instead of failing the entire VM creation operation
        try:
            storages = StorageManager.list_storage(resource_group)
        except Exception as e:
            logger.debug(f"Failed to list storages: {e}")
            return None

        if len(storages) == 0:
            return None

        # Prefer storage accounts in same region as VM for best performance
        # Cross-region storage will be handled with private endpoint setup if needed
        matching_region_storages = [s for s in storages if s.region.lower() == self.region.lower()]

        if len(matching_region_storages) == 0:
            logger.warning(
                f"Found {len(storages)} NFS storage account(s) in {resource_group}, "
                f"but none in VM region '{self.region}'. "
                f"Storage locations: {[s.region for s in storages]}. "
                f"Cross-region access will require private endpoint setup."
            )
            return None

        if len(matching_region_storages) == 1:
            # Auto-detect single storage in matching region
            storage = matching_region_storages[0]
            self.progress.update(
                f"Auto-detected NFS storage: {storage.name} (region: {storage.region})"
            )
            return storage

        # Multiple storages in same region without explicit choice
        storage_names = [s.name for s in matching_region_storages]
        raise ValueError(
            f"Multiple NFS storage accounts found in region '{self.region}': {', '.join(storage_names)}. "
            f"Please specify one with --nfs-storage or set default_nfs_storage in config."
        )

    def _extract_vnet_info_from_subnet_id(self, subnet_id: str) -> tuple[str, str]:
        """Extract VNet name and resource group from subnet resource ID.

        Args:
            subnet_id: Full Azure subnet resource ID

        Returns:
            Tuple of (vnet_name, resource_group)

        Raises:
            ValueError: If subnet ID format is invalid
        """
        # Subnet ID format: /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Network/virtualNetworks/{vnet}/subnets/{subnet}
        import re

        pattern = r"/subscriptions/[^/]+/resourceGroups/([^/]+)/providers/Microsoft\.Network/virtualNetworks/([^/]+)/subnets/[^/]+"
        match = re.match(pattern, subnet_id)

        if not match:
            raise ValueError(f"Invalid subnet ID format: {subnet_id}")

        resource_group = match.group(1)
        vnet_name = match.group(2)

        return vnet_name, resource_group

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

    def _mount_nfs_storage(
        self, vm_details: VMDetails, key_path: Path, storage: "StorageInfo"
    ) -> None:
        """Mount NFS storage on VM home directory.

        Handles both same-region and cross-region storage access:
        - Same region: Direct mount with network ACL configuration
        - Cross region: Offers private endpoint setup via orchestrator

        Args:
            vm_details: VM details
            key_path: SSH private key path
            storage: StorageInfo object with NFS storage account details

        Raises:
            Exception: If storage mount fails (this is a critical operation)
        """
        from azlin.modules.interaction_handler import CLIInteractionHandler
        from azlin.modules.nfs_mount_manager import NFSMountManager
        from azlin.modules.resource_orchestrator import (
            DecisionAction,
            NFSOptions,
            ResourceOrchestrator,
        )
        from azlin.modules.storage_manager import StorageManager

        try:
            # Storage details already resolved, use them directly
            self.progress.update(f"Using storage account: {storage.name}")

            # Get resource group (use the VM's resource group)
            rg = vm_details.resource_group

            self.progress.update(f"Storage endpoint: {storage.nfs_endpoint}")

            # Get VM network information
            vm_subnet_id = self._get_vm_subnet_id(vm_details)
            vnet_name, vnet_rg = self._extract_vnet_info_from_subnet_id(vm_subnet_id)

            # Track if using private endpoint (to skip service endpoint ACL config)
            using_private_endpoint = False

            # Check if cross-region access is needed
            if storage.region.lower() != vm_details.location.lower():
                self.progress.update(
                    f"Storage in {storage.region}, VM in {vm_details.location} - cross-region access required"
                )

                # Use orchestrator to handle cross-region decision
                # Use same interaction handler pattern as Bastion creation
                if self.auto_approve:
                    from azlin.modules.interaction_handler import MockInteractionHandler

                    nfs_interaction_handler = MockInteractionHandler(
                        choice_responses=[0, 0, 0, 0],  # Auto-select CREATE for all prompts
                        confirm_responses=[True, True, True, True],
                    )
                else:
                    nfs_interaction_handler = CLIInteractionHandler()

                orchestrator = ResourceOrchestrator(interaction_handler=nfs_interaction_handler)

                nfs_options = NFSOptions(
                    region=vm_details.location,
                    resource_group=rg,
                    storage_account_name=storage.name,
                    storage_account_region=storage.region,
                    share_name="home",
                    mount_point="/home/azureuser",
                    cross_region_required=True,
                )

                decision = orchestrator.ensure_nfs_access(nfs_options)

                if decision.action == DecisionAction.CREATE:
                    # User wants private endpoint setup
                    self.progress.update("Setting up cross-region private endpoint access...")

                    from azlin.modules.nfs_provisioner import NFSProvisioner

                    # Setup private endpoint, VNet peering, and DNS
                    endpoint, peering, dns_zone = NFSProvisioner.setup_private_endpoint_access(
                        storage_account=storage.name,
                        storage_resource_group=rg,
                        target_region=vm_details.location,
                        target_resource_group=rg,
                        target_vnet=vnet_name,
                        target_subnet="default",  # Use default subnet
                        source_vnet=None,  # No source VNet peering for now
                        source_resource_group=None,
                    )

                    self.progress.update(
                        f"Private endpoint created: {endpoint.name} (IP: {endpoint.private_ip})"
                    )
                    # Flag to skip service endpoint ACL config (private endpoint provides access)
                    using_private_endpoint = True

                elif decision.action == DecisionAction.SKIP:
                    # User chose local storage fallback
                    self.progress.update("Skipping NFS mount - using local storage")
                    return

                elif decision.action == DecisionAction.CANCEL:
                    raise Exception("User cancelled cross-region NFS setup")

            # Configure network access for NFS ONLY if NOT using private endpoint
            # Private endpoints provide access via private IP, service endpoint ACLs not needed
            # and fail cross-region (NetworkAclsValidationFailure)
            if not using_private_endpoint:
                self.progress.update("Configuring NFS network access...")
                StorageManager.configure_nfs_network_access(
                    storage_account=storage.name,
                    resource_group=rg,
                    vm_subnet_id=vm_subnet_id,
                )
            else:
                self.progress.update("Skipping service endpoint ACLs (using private endpoint)")

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

        Supports both direct SSH (public IP) and Bastion tunnels (private IP only).

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

        # Get SSH connection parameters (handles both direct and Bastion)
        host, port, bastion_manager = self._get_ssh_connection_params(vm_details)

        # Use context manager for automatic Bastion cleanup
        with contextlib.ExitStack() as stack:
            # Register bastion_manager cleanup if present
            if bastion_manager:
                stack.enter_context(bastion_manager)
                self.progress.update(f"Using Bastion tunnel on localhost:{port}")

            # Create SSH config with port parameter
            ssh_config = SSHConfig(host=host, port=port, user="azureuser", key_path=key_path)

            # Setup GitHub and clone repo
            self.progress.update("Authenticating with GitHub (may require browser)...")
            repo_details = GitHubSetupHandler.setup_github_on_vm(ssh_config, self.repo)

            self.progress.update(f"Repository cloned to: {repo_details.clone_path}")

    def _connect_ssh(self, vm_details: VMDetails, key_path: Path) -> int:
        """Connect to VM via SSH with tmux session.

        Handles both direct connections (public IP) and bastion tunneling (private IP).

        Args:
            vm_details: VM details
            key_path: SSH private key path

        Returns:
            int: SSH exit code

        Raises:
            SSHConnectionError: If connection fails
        """
        # If VM has no public IP, use bastion
        if not vm_details.public_ip:
            if not self.bastion_info:
                raise SSHConnectionError(
                    "VM has no public IP and no Bastion configured. Cannot establish connection."
                )

            # Use VMConnector which handles bastion tunneling
            click.echo("\n" + "=" * 60)
            click.echo(f"Connecting to {vm_details.name} via Bastion...")
            click.echo(f"Bastion: {self.bastion_info['name']}")
            click.echo("Starting tmux session 'azlin'")
            click.echo("=" * 60 + "\n")

            try:
                VMConnector.connect(
                    vm_identifier=vm_details.name,
                    resource_group=vm_details.resource_group,
                    use_bastion=True,
                    bastion_name=self.bastion_info["name"],
                    bastion_resource_group=self.bastion_info["resource_group"],
                    ssh_key_path=key_path,
                    use_tmux=True,
                    tmux_session="azlin",
                )
                return 0
            except VMConnectorError as e:
                raise SSHConnectionError(f"Bastion connection failed: {e}") from e

        # Direct SSH connection (public IP)
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


# --- Provisioning helper functions extracted to azlin.commands.provisioning (Issue #423) ---
# Functions moved:
#   - _auto_sync_home_directory (also in connectivity.py)
#   - show_interactive_menu
#   - generate_vm_name
#   - execute_command_on_vm
#   - select_vm_for_command
# These are now imported from azlin.commands.provisioning at the top of this file.
# --- End of provisioning helper functions marker ---


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


# --- Provisioning commands extracted to azlin.commands.provisioning (Issue #423) ---
# Commands moved:
#   - help_command: Enhanced help for commands
#   - new_command: Provision a new Azure VM (main provisioning command)
#   - vm_command: Alias for 'new' command
#   - create_command: Alias for 'new' command
#   - clone: Clone an existing VM with its home directory
#
# Also moved helper functions:
#   - _load_config_and_template
#   - _resolve_vm_settings
#   - _validate_inputs
#   - _update_config_state
#   - _execute_command_mode
#   - _provision_pool
#   - _display_pool_results
#   - _validate_config_path
#   - _validate_and_resolve_source_vm
#   - _ensure_source_vm_running
#   - _provision_clone_vms
#   - _display_clone_results
#   - _resolve_source_vm
#   - _generate_clone_configs
#   - _copy_home_directories
#   - _set_clone_session_names
# These are now imported from azlin.commands.provisioning at the top of this file.
# --- End of provisioning commands marker ---


# --- Monitoring/Operations Commands extracted to azlin.commands.monitoring (Issue #423) ---
# The following commands have been moved to src/azlin/commands/monitoring.py:
# - list_command: List VMs in resource group (most complex command)
# - session_command: Set or view session name for a VM
# - w: Run 'w' command on all VMs
# - top: Live distributed metrics dashboard
# - ps: Process listing on all VMs
# - os_update: Update OS packages on a VM
# - cost: Show cost estimates for VMs
#
# Also moved helper functions:
# - _collect_tmux_sessions: Collect tmux sessions from running VMs
# - _handle_multi_context_list: Handle multi-context VM listing
# - _get_config_int, _get_config_float: Config helpers
# - _create_tunnel_with_retry: Bastion tunnel retry helper
# - DIRECT_SSH_TMUX_TIMEOUT, BASTION_TUNNEL_TMUX_TIMEOUT: Constants
# --- End of monitoring commands marker ---

# --- connectivity commands extracted to azlin.commands.connectivity (Issue #423) ---
# Commands: connect, code, update, sync, sync-keys, cp
# Helpers: _interactive_vm_selection, _resolve_vm_identifier, _verify_vm_exists,
#          _resolve_tmux_session, _try_fetch_key_from_vault, _get_sync_vm_by_name,
#          _select_sync_vm_interactive, _perform_sync, _execute_sync
# --- End of connectivity commands marker ---


# Status command moved to azlin.commands.monitoring (Issue #423 - cli.py decomposition POC)

# ip command moved to azlin.commands.ip_commands (Issue #423)

# NLP commands (_do_impl, do, _doit_old_impl) moved to azlin.commands.nlp (Issue #423 - cli.py decomposition)
# See: src/azlin/commands/nlp.py
# The 'do' command is imported above and registered via main.add_command(do) below.


# NLP commands (_do_impl, do, _doit_old_impl) moved to azlin.commands.nlp (Issue #423 - cli.py decomposition)
# See: src/azlin/commands/nlp.py
# The "do" command is imported above and registered via main.add_command(do) below.

# Batch commands moved to azlin.commands.batch (Issue #423 - cli.py decomposition)


# Keys commands extracted to azlin.commands.keys (Issue #423 - cli.py decomposition)
# See: src/azlin/commands/keys.py


# Template commands extracted to azlin.commands.templates (Issue #423 - cli.py decomposition)
# See: src/azlin/commands/templates.py


# --- Snapshot commands extracted to azlin.commands.snapshots (Issue #423 - cli.py decomposition) ---
# See: src/azlin/commands/snapshots.py
# Original snapshot group and subcommands (enable, disable, sync, status, create, list, restore, delete)
# have been moved to the snapshots module and are registered via main.add_command(snapshot_group)


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

# Register monitoring/operations commands (Issue #423 - cli.py decomposition)
main.add_command(status)
main.add_command(list_command)
main.add_command(session_command, name="session")
main.add_command(w)
main.add_command(top)
main.add_command(ps)
main.add_command(os_update)
main.add_command(cost)

# Register IP commands (Issue #423 - cli.py decomposition)
main.add_command(ip)

# Register keys commands (Issue #423 - cli.py decomposition)
main.add_command(keys_group)

# Register restore command
main.add_command(restore_command, name="restore")

# Register doit commands (replace old doit if it exists)
if "doit" in main.commands:
    del main.commands["doit"]
main.add_command(doit_group)

# Register batch commands (Issue #423 - cli.py decomposition)
main.add_command(batch_group)

# Register env commands (Issue #423 - cli.py decomposition)
main.add_command(env_group)

# Register lifecycle commands (Issue #423 - cli.py decomposition)
main.add_command(start)
main.add_command(stop)
main.add_command(kill)
main.add_command(destroy)
main.add_command(killall)
main.add_command(prune)

# Register template commands (Issue #423 - cli.py decomposition)
main.add_command(template_group)

# Register snapshot commands (Issue #423 - cli.py decomposition)
main.add_command(snapshot_group)

# Register web commands (Issue #423 - cli.py decomposition)
main.add_command(web_group)

# Register connectivity commands (Issue #423 - cli.py decomposition)
main.add_command(connect)
main.add_command(code_command, name="code")
main.add_command(update)
main.add_command(sync)
main.add_command(sync_keys)
main.add_command(cp)

# Register NLP commands (Issue #423 - cli.py decomposition)
main.add_command(do)

# Register provisioning commands (Issue #423 - cli.py decomposition)
main.add_command(new_command)
main.add_command(vm_command)
main.add_command(create_command)
main.add_command(clone)
main.add_command(help_command)

# --- env commands extracted to azlin.commands.env (Issue #423) ---

# --- snapshot commands extracted to azlin.commands.snapshots (Issue #423) ---


# azdoit_main standalone command moved to azlin.commands.nlp (Issue #423 - cli.py decomposition)
# The azdoit_main command is imported above.

# --- web commands extracted to azlin.commands.web (Issue #423) ---


if __name__ == "__main__":
    main()


__all__ = [
    "AzlinError",
    "CLIOrchestrator",
    "_create_tunnel_with_retry",
    "_get_config_float",
    "_get_config_int",
    "azdoit_main",
    "main",
]
