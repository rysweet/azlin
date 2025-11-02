"""Cleanup orchestration for orphaned Azure resources.

This module provides automatic detection and cleanup of orphaned resources:
- Bastion hosts with no active VMs
- Orphaned public IPs
- Orphaned NICs
- Unattached disks

Integrates with:
- ResourceCleanup: Core cleanup operations
- VMManager: VM listing and queries
- BastionDetector: Bastion detection
- CostEstimator: Cost savings calculations
- InteractionHandler: User prompts and decisions

Philosophy:
- User consent for all deletions
- Cost transparency (show savings)
- Safe deletion (preserve VNets/subnets)
- Atomic operations with error handling
- Clear reporting of cleanup results

Public API:
    CleanupOrchestrator: Main orchestration class
    OrphanedBastionInfo: Bastion cleanup info
    CleanupDecision: User decision result
    CleanupOrchestratorError: Base exception

Example:
    >>> from azlin.modules.cleanup_orchestrator import CleanupOrchestrator
    >>> from azlin.modules.interaction_handler import CLIInteractionHandler
    >>>
    >>> orchestrator = CleanupOrchestrator(
    ...     resource_group="my-rg",
    ...     interaction_handler=CLIInteractionHandler()
    ... )
    >>>
    >>> # Detect and clean up orphaned Bastions
    >>> result = orchestrator.cleanup_orphaned_bastions()
    >>> print(f"Cleaned up {result.deleted_count} resources")
    >>> print(f"Monthly savings: ${result.estimated_monthly_savings:.2f}")
"""

import json
import logging
import subprocess
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from azlin.resource_cleanup import (
    ResourceCleanup,
    ResourceCleanupError,
)
from azlin.vm_manager import VMInfo, VMManager, VMManagerError

logger = logging.getLogger(__name__)


# Exceptions
class CleanupOrchestratorError(Exception):
    """Base exception for cleanup orchestrator operations."""

    pass


class BastionCleanupError(CleanupOrchestratorError):
    """Raised when Bastion cleanup operations fail."""

    pass


# Data Models
@dataclass
class OrphanedBastionInfo:
    """Information about an orphaned Bastion host.

    Attributes:
        name: Bastion host name
        resource_group: Resource group containing Bastion
        location: Azure region
        sku: Bastion SKU (Basic or Standard)
        public_ip_name: Associated public IP resource name
        public_ip_address: Public IP address
        vnet_name: Virtual network name
        subnet_name: Bastion subnet name
        vm_count: Number of VMs in region (should be 0 for orphaned)
        estimated_monthly_cost: Estimated monthly cost to maintain
        provisioning_state: Current provisioning state
    """

    name: str
    resource_group: str
    location: str
    sku: str | None = None
    public_ip_name: str | None = None
    public_ip_address: str | None = None
    vnet_name: str | None = None
    subnet_name: str | None = None
    vm_count: int = 0
    estimated_monthly_cost: Decimal = Decimal("0.0")
    provisioning_state: str | None = None

    def calculate_cost(self) -> None:
        """Calculate estimated monthly cost for this Bastion."""
        # Bastion pricing (approximate US East):
        # - Basic SKU: ~$0.19/hour = ~$140/month
        # - Standard SKU: ~$0.32/hour = ~$230/month
        # - Public IP: ~$3.65/month
        if self.sku:
            bastion_cost = Decimal("230.0") if "Standard" in self.sku else Decimal("140.0")
        else:
            bastion_cost = Decimal("140.0")

        # Add public IP cost
        public_ip_cost = Decimal("3.65")

        self.estimated_monthly_cost = bastion_cost + public_ip_cost


@dataclass
class CleanupDecision:
    """Result of user decision for cleanup operation.

    Attributes:
        approved: Whether user approved the cleanup
        resources_to_delete: List of resource names to delete
        estimated_savings: Estimated monthly cost savings
        cancelled: Whether user cancelled the operation
        dry_run: Whether this was a dry-run
    """

    approved: bool = False
    resources_to_delete: list[str] = field(default_factory=list)
    estimated_savings: Decimal = Decimal("0.0")
    cancelled: bool = False
    dry_run: bool = False


@dataclass
class BastionCleanupResult:
    """Result of Bastion cleanup operation.

    Attributes:
        bastion_name: Name of Bastion that was cleaned up
        resource_group: Resource group
        deleted_resources: List of deleted resource names
        failed_resources: List of resources that failed to delete
        estimated_monthly_savings: Cost savings from cleanup
        errors: List of error messages
    """

    bastion_name: str
    resource_group: str
    deleted_resources: list[str] = field(default_factory=list)
    failed_resources: list[str] = field(default_factory=list)
    estimated_monthly_savings: Decimal = Decimal("0.0")
    errors: list[str] = field(default_factory=list)

    def was_successful(self) -> bool:
        """Check if cleanup was fully successful."""
        return len(self.failed_resources) == 0 and len(self.errors) == 0


class CleanupOrchestrator:
    """Orchestrate cleanup of orphaned Azure resources.

    Provides workflows for:
    - Detecting orphaned Bastion hosts
    - Prompting user with cost savings information
    - Safely deleting Bastion and associated resources
    - Preserving VNets and subnets for reuse
    - Reporting cleanup results

    Example:
        >>> from azlin.modules.interaction_handler import CLIInteractionHandler
        >>>
        >>> orchestrator = CleanupOrchestrator(
        ...     resource_group="my-rg",
        ...     interaction_handler=CLIInteractionHandler()
        ... )
        >>>
        >>> # Auto-detect and clean up orphaned Bastions
        >>> results = orchestrator.cleanup_orphaned_bastions()
        >>>
        >>> # Or manually specify Bastion
        >>> result = orchestrator.cleanup_bastion(
        ...     bastion_name="my-bastion",
        ...     location="westus"
        ... )
    """

    def __init__(
        self,
        resource_group: str,
        interaction_handler: Any | None = None,
        dry_run: bool = False,
    ):
        """Initialize cleanup orchestrator.

        Args:
            resource_group: Azure resource group to operate on
            interaction_handler: Handler for user interaction (optional)
            dry_run: If True, simulate operations without deleting resources
        """
        self.resource_group = resource_group
        self.interaction_handler = interaction_handler
        self.dry_run = dry_run

    def detect_orphaned_bastions(self) -> list[OrphanedBastionInfo]:
        """Detect Bastion hosts with no active VMs in their region.

        Detection logic:
        1. List all VMs in resource group
        2. List all Bastions in resource group
        3. Group VMs by region
        4. Find Bastions in regions with 0 VMs using Bastion (no public IP)
        5. Calculate cost estimates

        Returns:
            List of orphaned Bastion hosts with cost information

        Raises:
            BastionCleanupError: If detection fails

        Example:
            >>> orphaned = orchestrator.detect_orphaned_bastions()
            >>> for bastion in orphaned:
            ...     print(f"{bastion.name}: ${bastion.estimated_monthly_cost}/mo")
        """
        try:
            logger.info(
                "Detecting orphaned Bastion hosts in resource group: %s", self.resource_group
            )

            # Step 1: List all VMs in resource group
            try:
                vms = VMManager.list_vms(self.resource_group, include_stopped=True)
                logger.debug("Found %d VMs in resource group", len(vms))
            except VMManagerError as e:
                logger.warning("Failed to list VMs: %s", e)
                vms = []

            # Step 2: List all Bastions in resource group
            bastions = self._list_bastions()
            logger.debug("Found %d Bastion hosts", len(bastions))

            if not bastions:
                logger.info("No Bastion hosts found in resource group")
                return []

            # Step 3: Group VMs by region and count those using Bastion
            vms_by_region = self._group_vms_by_region(vms)

            # Step 4: Identify orphaned Bastions
            orphaned: list[OrphanedBastionInfo] = []

            for bastion_data in bastions:
                bastion_info = self._check_bastion_orphaned(bastion_data, vms_by_region)

                if bastion_info and bastion_info.vm_count == 0:
                    # Calculate cost
                    bastion_info.calculate_cost()
                    orphaned.append(bastion_info)
                    logger.info(
                        "Found orphaned Bastion: %s (region: %s, cost: $%.2f/mo)",
                        bastion_info.name,
                        bastion_info.location,
                        bastion_info.estimated_monthly_cost,
                    )

            return orphaned

        except Exception as e:
            raise BastionCleanupError(f"Failed to detect orphaned Bastions: {e}") from e

    def cleanup_orphaned_bastions(self, force: bool = False) -> list[BastionCleanupResult]:
        """Detect and clean up all orphaned Bastion hosts.

        Workflow:
        1. Detect orphaned Bastions
        2. Calculate total cost savings
        3. Prompt user for confirmation
        4. Delete approved Bastions and their public IPs
        5. Preserve VNets and subnets
        6. Report results

        Args:
            force: If True, skip confirmation prompt

        Returns:
            List of cleanup results for each Bastion

        Raises:
            BastionCleanupError: If cleanup fails

        Example:
            >>> results = orchestrator.cleanup_orphaned_bastions()
            >>> total_savings = sum(r.estimated_monthly_savings for r in results)
            >>> print(f"Total monthly savings: ${total_savings}")
        """
        logger.info("Starting orphaned Bastion cleanup workflow")

        # Step 1: Detect orphaned Bastions
        orphaned = self.detect_orphaned_bastions()

        if not orphaned:
            logger.info("No orphaned Bastions found")
            if self.interaction_handler:
                self.interaction_handler.show_info("No orphaned Bastion hosts found.")
            return []

        # Step 2: Calculate total savings
        total_savings = sum((b.estimated_monthly_cost for b in orphaned), start=Decimal("0.0"))

        # Step 3: Prompt user
        decision = self._prompt_cleanup_decision(orphaned, total_savings, force)

        if decision.cancelled:
            logger.info("User cancelled cleanup")
            if self.interaction_handler:
                self.interaction_handler.show_info("Cleanup cancelled.")
            return []

        if not decision.approved:
            logger.info("User declined cleanup")
            if self.interaction_handler:
                self.interaction_handler.show_info("No resources will be deleted.")
            return []

        # Step 4: Delete approved Bastions
        results: list[BastionCleanupResult] = []

        for bastion_info in orphaned:
            if bastion_info.name in decision.resources_to_delete:
                result = self.cleanup_bastion(
                    bastion_name=bastion_info.name,
                    location=bastion_info.location,
                    public_ip_name=bastion_info.public_ip_name,
                )
                results.append(result)

        # Step 5: Report results
        self._report_cleanup_results(results)

        return results

    def cleanup_bastion(
        self,
        bastion_name: str,
        location: str,
        public_ip_name: str | None = None,
    ) -> BastionCleanupResult:
        """Clean up a specific Bastion host and its public IP.

        Deletes:
        - Bastion host
        - Associated public IP (if specified or auto-detected)

        Preserves:
        - VNet
        - Bastion subnet
        - NSG rules

        Args:
            bastion_name: Name of Bastion to delete
            location: Azure region
            public_ip_name: Public IP resource name (optional, will auto-detect)

        Returns:
            BastionCleanupResult with deletion details

        Raises:
            BastionCleanupError: If cleanup fails

        Example:
            >>> result = orchestrator.cleanup_bastion(
            ...     bastion_name="my-bastion",
            ...     location="westus"
            ... )
            >>> if result.was_successful():
            ...     print(f"Saved ${result.estimated_monthly_savings}/month")
        """
        logger.info(
            "Cleaning up Bastion: %s in region: %s (resource_group: %s)",
            bastion_name,
            location,
            self.resource_group,
        )

        result = BastionCleanupResult(
            bastion_name=bastion_name,
            resource_group=self.resource_group,
        )

        # Auto-detect public IP if not provided
        if not public_ip_name:
            public_ip_name = self._detect_bastion_public_ip(bastion_name)

        # Step 1: Delete Bastion host
        logger.info("Deleting Bastion host: %s", bastion_name)

        if self.dry_run:
            logger.info("[DRY RUN] Would delete Bastion: %s", bastion_name)
            result.deleted_resources.append(f"[DRY RUN] {bastion_name}")
        else:
            if self._delete_bastion(bastion_name):
                result.deleted_resources.append(bastion_name)
                logger.info("Successfully deleted Bastion: %s", bastion_name)
            else:
                result.failed_resources.append(bastion_name)
                result.errors.append(f"Failed to delete Bastion: {bastion_name}")

        # Step 2: Delete public IP (if exists)
        if public_ip_name:
            logger.info("Deleting public IP: %s", public_ip_name)

            if self.dry_run:
                logger.info("[DRY RUN] Would delete public IP: %s", public_ip_name)
                result.deleted_resources.append(f"[DRY RUN] {public_ip_name}")
            else:
                if self._delete_public_ip(public_ip_name):
                    result.deleted_resources.append(public_ip_name)
                    logger.info("Successfully deleted public IP: %s", public_ip_name)
                else:
                    result.failed_resources.append(public_ip_name)
                    result.errors.append(f"Failed to delete public IP: {public_ip_name}")

        # Calculate savings (Bastion + public IP)
        result.estimated_monthly_savings = Decimal("143.65")  # ~$140 Bastion + ~$3.65 IP

        return result

    def get_vms_using_bastion(self, location: str) -> list[VMInfo]:
        """Get list of VMs in region that use Bastion (no public IP).

        VMs using Bastion are identified by:
        - Located in specified region
        - No public IP assigned (relies on Bastion for access)

        Args:
            location: Azure region to filter

        Returns:
            List of VMInfo objects for VMs using Bastion

        Example:
            >>> vms = orchestrator.get_vms_using_bastion("westus")
            >>> print(f"Found {len(vms)} VMs using Bastion in westus")
        """
        try:
            all_vms = VMManager.list_vms(self.resource_group, include_stopped=True)

            # Filter VMs in region without public IP
            bastion_vms = [
                vm
                for vm in all_vms
                if vm.location.lower() == location.lower() and not vm.has_public_ip()
            ]

            logger.debug(
                "Found %d VMs using Bastion in region %s",
                len(bastion_vms),
                location,
            )

            return bastion_vms

        except VMManagerError as e:
            logger.warning("Failed to get VMs using Bastion: %s", e)
            return []

    def cleanup_all_orphaned_resources(self, force: bool = False) -> dict[str, Any]:
        """Clean up all types of orphaned resources in resource group.

        Detects and cleans:
        - Orphaned Bastions (with cost savings)
        - Orphaned disks
        - Orphaned NICs
        - Orphaned public IPs

        Args:
            force: If True, skip confirmation prompts

        Returns:
            Dictionary with cleanup summary

        Example:
            >>> summary = orchestrator.cleanup_all_orphaned_resources()
            >>> print(f"Total savings: ${summary['total_savings']:.2f}/month")
        """
        logger.info("Starting comprehensive orphaned resource cleanup")

        results: dict[str, Any] = {
            "bastion_results": [],
            "other_resources": None,
            "total_savings": Decimal("0.0"),
            "total_deleted": 0,
            "total_failed": 0,
        }

        # Step 1: Clean up orphaned Bastions
        bastion_results = self.cleanup_orphaned_bastions(force=force)
        results["bastion_results"] = bastion_results

        bastion_savings = sum(r.estimated_monthly_savings for r in bastion_results)
        bastion_deleted = sum(len(r.deleted_resources) for r in bastion_results)
        bastion_failed = sum(len(r.failed_resources) for r in bastion_results)

        # Step 2: Clean up other orphaned resources (disks, NICs, IPs)
        try:
            other_summary = ResourceCleanup.cleanup_resources(
                resource_group=self.resource_group,
                dry_run=self.dry_run,
                force=force,
            )
            results["other_resources"] = other_summary

            # Add savings from other resources
            results["total_savings"] = bastion_savings + Decimal(
                str(other_summary.estimated_monthly_savings)
            )
            results["total_deleted"] = bastion_deleted + other_summary.deleted_count
            results["total_failed"] = bastion_failed + other_summary.failed_count

        except ResourceCleanupError as e:
            logger.warning("Failed to clean up other resources: %s", e)
            results["total_savings"] = bastion_savings
            results["total_deleted"] = bastion_deleted
            results["total_failed"] = bastion_failed

        # Report overall results
        if self.interaction_handler:
            self._report_overall_results(results)

        return results

    # Private helper methods

    def _list_bastions(self) -> list[dict[str, Any]]:
        """List all Bastion hosts in resource group.

        Returns:
            List of Bastion data dictionaries

        Raises:
            BastionCleanupError: If listing fails
        """
        try:
            cmd = [
                "az",
                "network",
                "bastion",
                "list",
                "--resource-group",
                self.resource_group,
                "--output",
                "json",
            ]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60, check=False
            )

            if result.returncode != 0:
                raise BastionCleanupError(f"Failed to list Bastions: {result.stderr.strip()}")

            return json.loads(result.stdout)

        except subprocess.TimeoutExpired as e:
            raise BastionCleanupError("Timeout listing Bastions") from e
        except json.JSONDecodeError as e:
            raise BastionCleanupError(f"Failed to parse Bastion list: {e}") from e

    def _group_vms_by_region(self, vms: list[VMInfo]) -> dict[str, list[VMInfo]]:
        """Group VMs by region and filter those using Bastion.

        Args:
            vms: List of all VMs

        Returns:
            Dictionary mapping region to list of VMs using Bastion in that region
        """
        vms_by_region: dict[str, list[VMInfo]] = {}

        for vm in vms:
            location = vm.location.lower()

            # Only count VMs without public IP (likely using Bastion)
            if not vm.has_public_ip():
                if location not in vms_by_region:
                    vms_by_region[location] = []
                vms_by_region[location].append(vm)

        return vms_by_region

    def _check_bastion_orphaned(
        self,
        bastion_data: dict[str, Any],
        vms_by_region: dict[str, list[VMInfo]],
    ) -> OrphanedBastionInfo | None:
        """Check if a Bastion is orphaned (no VMs using it).

        Args:
            bastion_data: Bastion resource data
            vms_by_region: VMs grouped by region

        Returns:
            OrphanedBastionInfo if orphaned, None otherwise
        """
        name = bastion_data.get("name")
        if not name:
            logger.debug("Skipping Bastion with no name")
            return None

        location = bastion_data.get("location", "").lower()
        provisioning_state = bastion_data.get("provisioningState", "")

        # Only consider successfully provisioned Bastions
        if provisioning_state.lower() != "succeeded":
            logger.debug("Skipping Bastion %s (state: %s)", name, provisioning_state)
            return None

        # Count VMs in same region
        vm_count = len(vms_by_region.get(location, []))

        # Extract additional info
        sku = bastion_data.get("sku", {}).get("name") if bastion_data.get("sku") else None
        vnet_name = None
        subnet_name = None
        public_ip_name = None
        public_ip_address = None

        # Extract VNet info
        ip_configs = bastion_data.get("ipConfigurations", [])
        if ip_configs:
            subnet_id = ip_configs[0].get("subnet", {}).get("id", "")
            if subnet_id:
                subnet_name = subnet_id.split("/")[-1]
                vnet_name = subnet_id.split("/")[-3] if len(subnet_id.split("/")) >= 3 else None

            # Extract public IP info
            public_ip_ref = ip_configs[0].get("publicIPAddress", {})
            if public_ip_ref:
                public_ip_id = public_ip_ref.get("id", "")
                if public_ip_id:
                    public_ip_name = public_ip_id.split("/")[-1]

        return OrphanedBastionInfo(
            name=name,
            resource_group=self.resource_group,
            location=location,
            sku=sku,
            public_ip_name=public_ip_name,
            public_ip_address=public_ip_address,
            vnet_name=vnet_name,
            subnet_name=subnet_name,
            vm_count=vm_count,
            provisioning_state=provisioning_state,
        )

    def _prompt_cleanup_decision(
        self,
        orphaned: list[OrphanedBastionInfo],
        total_savings: Decimal,
        force: bool,
    ) -> CleanupDecision:
        """Prompt user to approve cleanup.

        Args:
            orphaned: List of orphaned Bastions
            total_savings: Total estimated monthly savings
            force: If True, skip prompt and approve

        Returns:
            CleanupDecision with user's choice
        """
        decision = CleanupDecision(
            estimated_savings=total_savings,
            dry_run=self.dry_run,
        )

        # Show orphaned resources
        if self.interaction_handler:
            self.interaction_handler.show_info(f"\nFound {len(orphaned)} orphaned Bastion host(s):")
            for bastion in orphaned:
                self.interaction_handler.show_info(
                    f"  - {bastion.name} ({bastion.location}): "
                    f"${bastion.estimated_monthly_cost:.2f}/month, "
                    f"{bastion.vm_count} VMs using it"
                )

            self.interaction_handler.show_info(f"\nEstimated monthly savings: ${total_savings:.2f}")

            if self.dry_run:
                self.interaction_handler.show_info("\n[DRY RUN] No resources will be deleted.")
                decision.approved = True
                decision.resources_to_delete = [b.name for b in orphaned]
                return decision

        # If force, approve all
        if force:
            decision.approved = True
            decision.resources_to_delete = [b.name for b in orphaned]
            return decision

        # Prompt for confirmation
        if self.interaction_handler:
            self.interaction_handler.show_warning(
                "\nThis will delete Bastion hosts and their public IPs."
            )
            self.interaction_handler.show_info("VNets and subnets will be preserved.")

            try:
                response = input("\nType 'delete' to confirm deletion (or 'cancel'): ")

                # Input validation: limit length and sanitize
                if not response:
                    decision.approved = False
                elif len(response) > 50:
                    # Reject suspiciously long input
                    self.interaction_handler.show_error(
                        "Invalid input: response too long (max 50 characters)"
                    )
                    decision.approved = False
                else:
                    # Normalize and validate against whitelist
                    response_normalized = response.strip().lower()

                    # Only accept exact matches from allowed set
                    if response_normalized == "delete":
                        decision.approved = True
                        decision.resources_to_delete = [b.name for b in orphaned]
                    elif response_normalized == "cancel":
                        decision.cancelled = True
                    else:
                        decision.approved = False

            except (KeyboardInterrupt, EOFError):
                decision.cancelled = True

        return decision

    def _detect_bastion_public_ip(self, bastion_name: str) -> str | None:
        """Detect the public IP associated with a Bastion.

        Args:
            bastion_name: Bastion name

        Returns:
            Public IP resource name or None
        """
        try:
            # Common naming convention: {bastion-name}PublicIP or {bastion-name}-pip
            possible_names = [
                f"{bastion_name}PublicIP",
                f"{bastion_name}-pip",
                f"{bastion_name}-ip",
            ]

            # Try to find public IP
            for ip_name in possible_names:
                cmd = [
                    "az",
                    "network",
                    "public-ip",
                    "show",
                    "--name",
                    ip_name,
                    "--resource-group",
                    self.resource_group,
                    "--output",
                    "json",
                ]

                result: subprocess.CompletedProcess[str] = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=10, check=False
                )

                if result.returncode == 0:
                    logger.debug("Found public IP: %s", ip_name)
                    return ip_name

            logger.warning("Could not auto-detect public IP for Bastion: %s", bastion_name)
            return None

        except Exception as e:
            logger.warning("Failed to detect public IP: %s", e)
            return None

    def _delete_bastion(self, bastion_name: str) -> bool:
        """Delete a Bastion host.

        Args:
            bastion_name: Name of Bastion to delete

        Returns:
            True if deletion succeeded, False otherwise
        """
        try:
            cmd = [
                "az",
                "network",
                "bastion",
                "delete",
                "--name",
                bastion_name,
                "--resource-group",
                self.resource_group,
                "--yes",
            ]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600, check=False
            )

            if result.returncode == 0:
                return True

            logger.error("Failed to delete Bastion %s: %s", bastion_name, result.stderr)
            return False

        except subprocess.TimeoutExpired:
            logger.error("Timeout deleting Bastion: %s", bastion_name)
            return False
        except Exception as e:
            logger.error("Error deleting Bastion %s: %s", bastion_name, e)
            return False

    def _delete_public_ip(self, public_ip_name: str) -> bool:
        """Delete a public IP resource.

        Args:
            public_ip_name: Name of public IP to delete

        Returns:
            True if deletion succeeded, False otherwise
        """
        try:
            cmd = [
                "az",
                "network",
                "public-ip",
                "delete",
                "--name",
                public_ip_name,
                "--resource-group",
                self.resource_group,
            ]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, check=False
            )

            if result.returncode == 0:
                return True

            logger.error("Failed to delete public IP %s: %s", public_ip_name, result.stderr)
            return False

        except subprocess.TimeoutExpired:
            logger.error("Timeout deleting public IP: %s", public_ip_name)
            return False
        except Exception as e:
            logger.error("Error deleting public IP %s: %s", public_ip_name, e)
            return False

    def _report_cleanup_results(self, results: list[BastionCleanupResult]) -> None:
        """Report cleanup results to user.

        Args:
            results: List of cleanup results
        """
        if not self.interaction_handler:
            return

        total_deleted = sum(len(r.deleted_resources) for r in results)
        total_failed = sum(len(r.failed_resources) for r in results)
        total_savings = sum(r.estimated_monthly_savings for r in results)

        self.interaction_handler.show_info("\n" + "=" * 80)
        self.interaction_handler.show_info("Bastion Cleanup Results")
        self.interaction_handler.show_info("=" * 80)

        for result in results:
            status = "SUCCESS" if result.was_successful() else "PARTIAL"
            self.interaction_handler.show_info(f"\n{result.bastion_name}: {status}")

            if result.deleted_resources:
                self.interaction_handler.show_info("  Deleted:")
                for resource in result.deleted_resources:
                    self.interaction_handler.show_info(f"    - {resource}")

            if result.failed_resources:
                self.interaction_handler.show_warning("  Failed:")
                for resource in result.failed_resources:
                    self.interaction_handler.show_warning(f"    - {resource}")

            if result.errors:
                for error in result.errors:
                    self.interaction_handler.show_warning(f"  Error: {error}")

        self.interaction_handler.show_info(f"\nTotal resources deleted: {total_deleted}")
        if total_failed > 0:
            self.interaction_handler.show_warning(f"Total failures: {total_failed}")

        self.interaction_handler.show_info(f"Estimated monthly savings: ${total_savings:.2f}")
        self.interaction_handler.show_info("=" * 80 + "\n")

    def _report_overall_results(self, results: dict[str, Any]) -> None:
        """Report overall cleanup results.

        Args:
            results: Dictionary with all cleanup results
        """
        if not self.interaction_handler:
            return

        self.interaction_handler.show_info("\n" + "=" * 80)
        self.interaction_handler.show_info("Overall Cleanup Summary")
        self.interaction_handler.show_info("=" * 80)

        self.interaction_handler.show_info(f"\nTotal resources deleted: {results['total_deleted']}")
        if results["total_failed"] > 0:
            self.interaction_handler.show_warning(f"Total failures: {results['total_failed']}")

        self.interaction_handler.show_info(
            f"Total estimated monthly savings: ${results['total_savings']:.2f}"
        )

        self.interaction_handler.show_info("=" * 80 + "\n")


__all__ = [
    "BastionCleanupError",
    "BastionCleanupResult",
    "CleanupDecision",
    "CleanupOrchestrator",
    "CleanupOrchestratorError",
    "OrphanedBastionInfo",
]
