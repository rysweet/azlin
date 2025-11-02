"""Resource orchestration with user interaction and cost transparency.

This module coordinates resource creation workflows with:
- User decision gathering with cost information
- Dependency management between resources
- Atomic operations with rollback capability
- Integration with cost estimator and interaction handlers

Philosophy:
- User consent for all resource creation
- Cost transparency before operations
- Dependency-aware orchestration
- Atomic operations with rollback
- Clear decision workflows

Public API:
    ResourceOrchestrator: Main orchestration class
    ResourceDecision: User decision result
    DecisionAction: Available user actions
    OrchestratorError: Base exception

Example:
    >>> orchestrator = ResourceOrchestrator(
    ...     interaction_handler=CLIInteractionHandler(),
    ...     cost_estimator=CostEstimator(region="westus")
    ... )
    >>>
    >>> # Ensure Bastion exists
    >>> decision = orchestrator.ensure_bastion(
    ...     region="westus",
    ...     resource_group="my-rg",
    ...     vnet_name="my-vnet"
    ... )
    >>>
    >>> if decision.action == DecisionAction.CREATE:
    ...     print(f"Created Bastion: {decision.resource_id}")
    >>> elif decision.action == DecisionAction.USE_EXISTING:
    ...     print(f"Using existing: {decision.resource_id}")
    >>> elif decision.action == DecisionAction.SKIP:
    ...     print("User chose to skip Bastion setup")
"""

import logging
import subprocess
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# Exceptions
class OrchestratorError(Exception):
    """Base exception for orchestrator operations."""

    pass


class DependencyError(OrchestratorError):
    """Raised when resource dependencies cannot be satisfied."""

    pass


class RollbackError(OrchestratorError):
    """Raised when resource rollback fails."""

    pass


# Enums
class DecisionAction(str, Enum):
    """User decision actions for resource operations."""

    CREATE = "create"  # Create the resource
    USE_EXISTING = "use-existing"  # Use existing resource
    SKIP = "skip"  # Skip this resource (use fallback)
    CANCEL = "cancel"  # Cancel entire operation


class ResourceType(str, Enum):
    """Types of resources that can be orchestrated."""

    BASTION = "bastion"
    NFS = "nfs"
    VNET = "vnet"
    SUBNET = "subnet"
    NSG = "nsg"


class ResourceStatus(str, Enum):
    """Status of orchestrated resources."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    CREATED = "created"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


# Data Models
@dataclass
class ResourceDecision:
    """Result of user decision for a resource operation.

    Attributes:
        action: What action to take
        resource_type: Type of resource
        resource_id: Azure resource ID (if resource exists/created)
        resource_name: Resource name
        cost_estimate: Estimated monthly cost (if creating)
        metadata: Additional context about the decision
    """

    action: DecisionAction
    resource_type: ResourceType
    resource_id: str | None = None
    resource_name: str | None = None
    cost_estimate: Decimal | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate decision structure."""
        if self.action == DecisionAction.CREATE and self.cost_estimate is None:
            logger.warning("CREATE decision without cost estimate for %s", self.resource_type.value)


@dataclass
class OrchestratedResource:
    """Tracks an orchestrated resource.

    Attributes:
        resource_type: Type of resource
        resource_id: Azure resource ID
        resource_name: Resource name
        status: Current status
        created_at: When resource was created
        dependencies: Resource IDs this depends on
        rollback_cmd: Command to rollback/delete resource
        metadata: Additional resource information
    """

    resource_type: ResourceType
    resource_id: str
    resource_name: str
    status: ResourceStatus
    created_at: float
    dependencies: list[str] = field(default_factory=list)
    rollback_cmd: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BastionOptions:
    """Options for Bastion orchestration.

    Attributes:
        region: Azure region
        resource_group: Resource group name
        vnet_name: Virtual network name
        vnet_id: Virtual network resource ID
        bastion_subnet_id: Bastion subnet ID (if exists)
        sku: Bastion SKU (Basic or Standard)
        allow_public_ip_fallback: Whether to allow public IP if user declines Bastion
    """

    region: str
    resource_group: str
    vnet_name: str
    vnet_id: str | None = None
    bastion_subnet_id: str | None = None
    sku: str = "Basic"
    allow_public_ip_fallback: bool = True


@dataclass
class NFSOptions:
    """Options for NFS orchestration.

    Attributes:
        region: Azure region (where VM is)
        resource_group: Resource group name
        storage_account_name: Storage account name
        storage_account_region: Region where storage account exists
        share_name: NFS share name
        mount_point: Mount point on VM (e.g., /home)
        cross_region_required: Whether cross-region access is needed
    """

    region: str
    resource_group: str
    storage_account_name: str
    storage_account_region: str
    share_name: str
    mount_point: str = "/home"
    cross_region_required: bool = False


class ResourceOrchestrator:
    """Orchestrates resource creation with user interaction.

    Coordinates resource provisioning workflows with:
    - Cost estimation before user decisions
    - Interactive prompts with clear choices
    - Dependency management
    - Atomic operations with rollback
    - Resource tracking for cleanup

    Example:
        >>> from azlin.modules.interaction_handler import CLIInteractionHandler
        >>> from azlin.agentic.cost_estimator import CostEstimator
        >>>
        >>> orchestrator = ResourceOrchestrator(
        ...     interaction_handler=CLIInteractionHandler(),
        ...     cost_estimator=CostEstimator(region="westus")
        ... )
        >>>
        >>> # Ensure Bastion setup
        >>> options = BastionOptions(
        ...     region="westus",
        ...     resource_group="my-rg",
        ...     vnet_name="my-vnet"
        ... )
        >>> decision = orchestrator.ensure_bastion(options)
        >>>
        >>> if decision.action == DecisionAction.CREATE:
        ...     print(f"Bastion will be created: {decision.resource_name}")
    """

    def __init__(
        self,
        interaction_handler: Any,
        cost_estimator: Any | None = None,
        dry_run: bool = False,
    ):
        """Initialize resource orchestrator.

        Args:
            interaction_handler: Handler for user interaction (must implement InteractionHandler protocol)
            cost_estimator: Cost estimator for Azure resources (optional)
            dry_run: If True, simulate operations without creating resources
        """
        self.interaction_handler = interaction_handler
        self.cost_estimator = cost_estimator
        self.dry_run = dry_run
        self.resources: list[OrchestratedResource] = []

    def ensure_bastion(self, options: BastionOptions) -> ResourceDecision:
        """Ensure Bastion host exists or get user decision.

        Workflow:
        1. Check if Bastion already exists in VNet
        2. If exists, return USE_EXISTING decision
        3. If not, estimate cost and prompt user
        4. If user approves, create Bastion (or return CREATE decision for later execution)
        5. If user declines and fallback allowed, return SKIP decision
        6. If user cancels, return CANCEL decision

        Args:
            options: Bastion configuration options

        Returns:
            ResourceDecision with user's choice

        Raises:
            OrchestratorError: If operation fails
            DependencyError: If required dependencies missing

        Example:
            >>> options = BastionOptions(
            ...     region="westus",
            ...     resource_group="my-rg",
            ...     vnet_name="my-vnet",
            ...     vnet_id="/subscriptions/.../my-vnet"
            ... )
            >>> decision = orchestrator.ensure_bastion(options)
            >>> if decision.action == DecisionAction.CREATE:
            ...     # Proceed with creation
            ...     pass
        """
        logger.info(
            "Ensuring Bastion host in region=%s, resource_group=%s, vnet=%s",
            options.region,
            options.resource_group,
            options.vnet_name,
        )

        # Auto-generate VNet name if not provided
        if not options.vnet_id and not options.vnet_name:
            # Auto-generate VNet name based on region
            options.vnet_name = f"azlin-vnet-{options.region}"
            logger.info(f"No VNet specified, will use/create: {options.vnet_name}")

        # Step 1: Check for existing Bastion
        existing_bastion = self._check_existing_bastion(options.resource_group, options.vnet_name)

        if existing_bastion:
            logger.info("Found existing Bastion: %s", existing_bastion["name"])
            self.interaction_handler.show_info(
                f"Found existing Bastion host: {existing_bastion['name']}"
            )

            return ResourceDecision(
                action=DecisionAction.USE_EXISTING,
                resource_type=ResourceType.BASTION,
                resource_id=existing_bastion["id"],
                resource_name=existing_bastion["name"],
                metadata={"sku": existing_bastion.get("sku", "Unknown")},
            )

        # Step 2: Estimate cost for new Bastion
        cost_estimate = self._estimate_bastion_cost(options.region, options.sku)

        # Step 3: Present options to user
        self.interaction_handler.show_info(
            "\nBastion host not found. Azure Bastion provides secure browser-based SSH access."
        )
        self.interaction_handler.show_warning(
            "Bastion resources incur hourly charges even when not in use."
        )

        choices = []

        # Option 1: Create Bastion
        choices.append(
            (
                "create",
                f"Create Azure Bastion ({options.sku} SKU) for secure browser-based access",
                float(cost_estimate["monthly"]),
            )
        )

        # Option 2: Use public IP (if allowed)
        if options.allow_public_ip_fallback:
            choices.append(
                (
                    "public-ip",
                    "Skip Bastion setup - Use public IP for SSH (less secure, no cost)",
                    0.0,
                )
            )

        # Option 3: Cancel
        choices.append(
            (
                "cancel",
                "Cancel operation - Don't create VM",
                0.0,
            )
        )

        # Get user choice
        try:
            choice_idx = self.interaction_handler.prompt_choice(
                "How would you like to access the VM?", choices
            )
            choice_label = choices[choice_idx][0]
        except (KeyboardInterrupt, Exception) as e:
            logger.info("User cancelled Bastion decision: %s", e)
            return ResourceDecision(
                action=DecisionAction.CANCEL,
                resource_type=ResourceType.BASTION,
            )

        # Process user choice
        if choice_label == "create":
            logger.info("User chose to create Bastion")
            return ResourceDecision(
                action=DecisionAction.CREATE,
                resource_type=ResourceType.BASTION,
                resource_name=f"{options.vnet_name}-bastion",
                cost_estimate=cost_estimate["monthly"],
                metadata={
                    "sku": options.sku,
                    "region": options.region,
                    "resource_group": options.resource_group,
                    "vnet_name": options.vnet_name,
                    "estimated_hourly": float(cost_estimate["hourly"]),
                },
            )

        if choice_label == "public-ip":
            logger.info("User chose to skip Bastion (use public IP)")
            self.interaction_handler.show_warning(
                "VM will be created with a public IP address. "
                "Ensure proper network security group rules are configured."
            )
            return ResourceDecision(
                action=DecisionAction.SKIP,
                resource_type=ResourceType.BASTION,
                metadata={"fallback": "public-ip"},
            )

        # cancel
        logger.info("User cancelled operation")
        return ResourceDecision(
            action=DecisionAction.CANCEL,
            resource_type=ResourceType.BASTION,
        )

    def ensure_nfs_access(self, options: NFSOptions) -> ResourceDecision:
        """Ensure NFS share is accessible from VM, handle cross-region if needed.

        Workflow:
        1. Check if storage account region matches VM region
        2. If same region, return USE_EXISTING (simple mount)
        3. If different region, estimate cross-region cost and prompt user
        4. If user approves, return CREATE decision for cross-region setup
        5. If user declines, return SKIP decision (local storage fallback)

        Args:
            options: NFS configuration options

        Returns:
            ResourceDecision with user's choice

        Raises:
            OrchestratorError: If operation fails

        Example:
            >>> options = NFSOptions(
            ...     region="westus",
            ...     resource_group="my-rg",
            ...     storage_account_name="myaccount",
            ...     storage_account_region="eastus",  # Different region
            ...     share_name="home-share"
            ... )
            >>> decision = orchestrator.ensure_nfs_access(options)
            >>> if decision.action == DecisionAction.CREATE:
            ...     # Setup cross-region access
            ...     pass
        """
        logger.info(
            "Ensuring NFS access: VM region=%s, Storage region=%s, account=%s",
            options.region,
            options.storage_account_region,
            options.storage_account_name,
        )

        # Check if cross-region access is needed
        same_region = options.region.lower() == options.storage_account_region.lower()

        if same_region:
            logger.info("Storage and VM in same region - simple NFS mount")
            self.interaction_handler.show_info(
                f"NFS share '{options.share_name}' will be mounted from local region storage."
            )

            return ResourceDecision(
                action=DecisionAction.USE_EXISTING,
                resource_type=ResourceType.NFS,
                resource_id=f"//{options.storage_account_name}.file.core.windows.net/{options.share_name}",
                resource_name=options.share_name,
                metadata={
                    "mount_point": options.mount_point,
                    "storage_region": options.storage_account_region,
                    "vm_region": options.region,
                    "cross_region": False,
                },
            )

        # Cross-region scenario - estimate cost and prompt
        logger.info("Cross-region NFS access required")

        cost_estimate = self._estimate_cross_region_nfs_cost(
            options.region, options.storage_account_region
        )

        self.interaction_handler.show_warning(
            f"\nNFS share is in {options.storage_account_region}, but VM is in {options.region}."
        )
        self.interaction_handler.show_info(
            "Cross-region access will incur data transfer charges and may have higher latency."
        )

        choices = [
            (
                "setup-cross-region",
                "Setup cross-region access (includes private endpoint and data transfer costs)",
                float(cost_estimate["monthly"]),
            ),
            (
                "use-local-storage",
                "Skip NFS mount - Use VM's local disk instead (no transfer costs)",
                0.0,
            ),
            (
                "cancel",
                "Cancel operation",
                0.0,
            ),
        ]

        try:
            choice_idx = self.interaction_handler.prompt_choice(
                "How would you like to handle cross-region NFS access?", choices
            )
            choice_label = choices[choice_idx][0]
        except (KeyboardInterrupt, Exception) as e:
            logger.info("User cancelled NFS decision: %s", e)
            return ResourceDecision(
                action=DecisionAction.CANCEL,
                resource_type=ResourceType.NFS,
            )

        if choice_label == "setup-cross-region":
            logger.info("User chose to setup cross-region NFS access")
            return ResourceDecision(
                action=DecisionAction.CREATE,
                resource_type=ResourceType.NFS,
                resource_name=f"{options.storage_account_name}-cross-region-endpoint",
                cost_estimate=cost_estimate["monthly"],
                metadata={
                    "mount_point": options.mount_point,
                    "storage_region": options.storage_account_region,
                    "vm_region": options.region,
                    "cross_region": True,
                    "storage_account": options.storage_account_name,
                    "share_name": options.share_name,
                    "estimated_hourly": float(cost_estimate["hourly"]),
                },
            )

        if choice_label == "use-local-storage":
            logger.info("User chose to use local storage instead of NFS")
            self.interaction_handler.show_info(
                "VM will use local disk storage. Files will not be shared across VMs."
            )
            return ResourceDecision(
                action=DecisionAction.SKIP,
                resource_type=ResourceType.NFS,
                metadata={"fallback": "local-storage"},
            )

        # cancel
        logger.info("User cancelled operation")
        return ResourceDecision(
            action=DecisionAction.CANCEL,
            resource_type=ResourceType.NFS,
        )

    def track_resource(
        self,
        resource_type: ResourceType,
        resource_id: str,
        resource_name: str,
        dependencies: list[str] | None = None,
        rollback_cmd: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> OrchestratedResource:
        """Track a created resource for potential rollback.

        Args:
            resource_type: Type of resource
            resource_id: Azure resource ID
            resource_name: Resource name
            dependencies: List of resource IDs this depends on
            rollback_cmd: Command to rollback/delete resource
            metadata: Additional resource information

        Returns:
            OrchestratedResource tracking object

        Example:
            >>> import time
            >>> resource = orchestrator.track_resource(
            ...     resource_type=ResourceType.BASTION,
            ...     resource_id="/subscriptions/.../bastionHosts/my-bastion",
            ...     resource_name="my-bastion",
            ...     rollback_cmd="az network bastion delete --ids {resource_id}",
            ...     metadata={"sku": "Basic"}
            ... )
        """
        import time

        resource = OrchestratedResource(
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            status=ResourceStatus.CREATED,
            created_at=time.time(),
            dependencies=dependencies or [],
            rollback_cmd=rollback_cmd,
            metadata=metadata or {},
        )

        self.resources.append(resource)
        logger.info("Tracking resource: %s (%s)", resource_name, resource_type.value)

        return resource

    def rollback_resources(self, error_context: str | None = None) -> None:
        """Rollback all tracked resources in reverse dependency order.

        Args:
            error_context: Optional error message for logging

        Raises:
            RollbackError: If rollback fails for any resource

        Example:
            >>> try:
            ...     # ... operations that create resources ...
            ...     pass
            ... except Exception as e:
            ...     orchestrator.rollback_resources(f"Failed: {e}")
            ...     raise
        """
        if not self.resources:
            logger.info("No resources to rollback")
            return

        logger.warning(
            "Rolling back %d resources%s",
            len(self.resources),
            f": {error_context}" if error_context else "",
        )

        if error_context:
            self.interaction_handler.show_warning(f"Rolling back resources: {error_context}")
        else:
            self.interaction_handler.show_warning("Rolling back created resources...")

        # Rollback in reverse order (newest first, respecting dependencies)
        failures = []

        for resource in reversed(self.resources):
            if resource.status == ResourceStatus.ROLLED_BACK:
                continue

            logger.info("Rolling back %s: %s", resource.resource_type.value, resource.resource_name)

            try:
                if self.dry_run:
                    logger.info("[DRY RUN] Would rollback: %s", resource.resource_id)
                    resource.status = ResourceStatus.ROLLED_BACK
                    continue

                if resource.rollback_cmd:
                    self._execute_rollback_command(resource)
                else:
                    logger.warning(
                        "No rollback command for %s, manual cleanup required: %s",
                        resource.resource_type.value,
                        resource.resource_id,
                    )

                resource.status = ResourceStatus.ROLLED_BACK
                logger.info("Successfully rolled back: %s", resource.resource_name)

            except Exception as e:
                error_msg = f"Failed to rollback {resource.resource_name}: {e}"
                logger.error(error_msg)
                failures.append(error_msg)
                resource.status = ResourceStatus.FAILED

        if failures:
            error_summary = "\n".join(failures)
            raise RollbackError(
                f"Rollback completed with {len(failures)} failures:\n{error_summary}"
            )

        logger.info("Rollback completed successfully")
        self.interaction_handler.show_info("All resources rolled back successfully")

    def get_resource_summary(self) -> dict[str, Any]:
        """Get summary of all tracked resources.

        Returns:
            Dictionary with resource statistics

        Example:
            >>> summary = orchestrator.get_resource_summary()
            >>> print(f"Created {summary['total_resources']} resources")
        """
        status_counts = {}
        for resource in self.resources:
            status_counts[resource.status.value] = status_counts.get(resource.status.value, 0) + 1

        return {
            "total_resources": len(self.resources),
            "by_status": status_counts,
            "by_type": {
                rt.value: len([r for r in self.resources if r.resource_type == rt])
                for rt in ResourceType
            },
            "resources": [
                {
                    "type": r.resource_type.value,
                    "name": r.resource_name,
                    "id": r.resource_id,
                    "status": r.status.value,
                }
                for r in self.resources
            ],
        }

    # Private helper methods

    def _check_existing_bastion(self, resource_group: str, vnet_name: str) -> dict[str, Any] | None:
        """Check if Bastion host already exists in VNet.

        Args:
            resource_group: Resource group name
            vnet_name: Virtual network name

        Returns:
            Bastion info dict if found, None otherwise
        """
        if self.dry_run:
            logger.info("[DRY RUN] Would check for existing Bastion")
            return None

        try:
            # This would call BastionDetector or Azure CLI
            # For now, return None (to be integrated with actual implementation)
            logger.debug("Checking for existing Bastion in VNet: %s", vnet_name)
            return None

        except Exception as e:
            logger.warning("Failed to check for existing Bastion: %s", e)
            return None

    def _estimate_bastion_cost(self, region: str, sku: str) -> dict[str, Decimal]:
        """Estimate Bastion cost.

        Args:
            region: Azure region
            sku: Bastion SKU

        Returns:
            Dictionary with hourly and monthly cost estimates
        """
        if not self.cost_estimator:
            # Default estimates if no cost estimator provided
            # Basic SKU: ~$0.19/hour = ~$140/month
            # Standard SKU: ~$0.32/hour = ~$230/month
            hourly = Decimal("0.19" if sku == "Basic" else "0.32")
            monthly = hourly * Decimal("730")  # Average hours per month

            logger.warning(
                "No cost estimator provided, using default Bastion estimates: $%.2f/month",
                monthly,
            )

            return {
                "hourly": hourly,
                "monthly": monthly,
            }

        # Use cost estimator
        try:
            estimate = self.cost_estimator.estimate(
                {
                    "bastion_sku": sku,
                }
            )
            return {
                "hourly": estimate.total_hourly,
                "monthly": estimate.total_monthly,
            }
        except Exception as e:
            logger.warning("Cost estimation failed: %s, using defaults", e)
            hourly = Decimal("0.19" if sku == "Basic" else "0.32")
            monthly = hourly * Decimal("730")
            return {"hourly": hourly, "monthly": monthly}

    def _estimate_cross_region_nfs_cost(
        self, vm_region: str, storage_region: str
    ) -> dict[str, Decimal]:
        """Estimate cross-region NFS access cost.

        Includes private endpoint and estimated data transfer costs.

        Args:
            vm_region: VM region
            storage_region: Storage account region

        Returns:
            Dictionary with hourly and monthly cost estimates
        """
        if not self.cost_estimator:
            # Default estimates:
            # - Private endpoint: ~$0.01/hour = ~$7.30/month
            # - Data transfer: ~$0.02/GB (estimate 100GB/month) = ~$2/month
            # Total: ~$10/month
            hourly = Decimal("0.014")
            monthly = Decimal("10.0")

            logger.warning(
                "No cost estimator provided, using default cross-region NFS estimates: $%.2f/month",
                monthly,
            )

            return {
                "hourly": hourly,
                "monthly": monthly,
            }

        # Use cost estimator
        try:
            estimate = self.cost_estimator.estimate(
                {
                    "private_endpoint": 1,
                    "data_transfer_gb": 100,  # Estimated monthly transfer
                }
            )
            return {
                "hourly": estimate.total_hourly,
                "monthly": estimate.total_monthly,
            }
        except Exception as e:
            logger.warning("Cost estimation failed: %s, using defaults", e)
            return {"hourly": Decimal("0.014"), "monthly": Decimal("10.0")}

    def _execute_rollback_command(self, resource: OrchestratedResource) -> None:
        """Execute rollback command for a resource.

        Args:
            resource: Resource to rollback

        Raises:
            OrchestratorError: If rollback command fails
        """
        if not resource.rollback_cmd:
            raise OrchestratorError(f"No rollback command for {resource.resource_name}")

        # Substitute resource_id in command
        cmd_string = resource.rollback_cmd.format(resource_id=resource.resource_id)

        # Parse command string into argument list for safe execution
        # This prevents command injection by avoiding shell=True
        import shlex

        try:
            cmd_args = shlex.split(cmd_string)
        except ValueError as e:
            raise OrchestratorError(f"Invalid rollback command format: {e}") from e

        logger.info("Executing rollback command: %s", " ".join(cmd_args))

        try:
            result = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode != 0:
                raise OrchestratorError(
                    f"Rollback command failed (exit {result.returncode}): {result.stderr}"
                )

            logger.debug("Rollback command output: %s", result.stdout)

        except subprocess.TimeoutExpired as e:
            raise OrchestratorError(
                f"Rollback command timed out for {resource.resource_name}"
            ) from e
        except Exception as e:
            raise OrchestratorError(f"Failed to execute rollback command: {e}") from e
