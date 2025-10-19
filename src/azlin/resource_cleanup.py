"""Resource cleanup module for finding and removing orphaned Azure resources.

This module provides functionality to:
- Detect unattached disks
- Find orphaned NICs (not attached to VMs)
- Find orphaned public IPs (not attached to NICs)
- Safe deletion with confirmation
- Cost estimation for cleanup savings
"""

import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class ResourceCleanupError(Exception):
    """Raised when resource cleanup operations fail."""

    pass


@dataclass
class OrphanedResource:
    """Represents an orphaned Azure resource."""

    name: str
    resource_type: str  # "disk", "nic", or "public-ip"
    resource_group: str
    size_gb: int | None = None
    tier: str | None = None
    ip_address: str | None = None
    location: str | None = None

    def get_cost_estimate(self) -> float:
        """Estimate monthly cost for this resource.

        Returns:
            Estimated monthly cost in USD
        """
        if self.resource_type == "disk" and self.size_gb and self.tier:
            # Rough Azure pricing (US East)
            if "Premium" in self.tier:
                # Premium SSD: ~$0.135/GB/month
                return self.size_gb * 0.135
            if "StandardSSD" in self.tier:
                # Standard SSD: ~$0.075/GB/month
                return self.size_gb * 0.075
            # Standard HDD: ~$0.05/GB/month
            return self.size_gb * 0.05
        if self.resource_type == "public-ip":
            # Public IP: ~$3.65/month
            return 3.65
        if self.resource_type == "nic":
            # NICs don't have direct cost, but minimal
            return 0.0
        return 0.0


@dataclass
class CleanupSummary:
    """Summary of cleanup operation results."""

    total_orphaned: int = 0
    orphaned_disks: int = 0
    orphaned_nics: int = 0
    orphaned_public_ips: int = 0
    resources: list[OrphanedResource] = field(default_factory=list)  # type: ignore[misc]
    deleted_count: int = 0
    failed_count: int = 0
    errors: list[str] = field(default_factory=list)  # type: ignore[misc]
    dry_run: bool = False
    cancelled: bool = False
    estimated_monthly_savings: float = 0.0

    def calculate_savings(self) -> None:
        """Calculate estimated monthly savings from cleanup."""
        self.estimated_monthly_savings = sum(r.get_cost_estimate() for r in self.resources)


class ResourceCleanup:
    """Manage Azure resource cleanup operations."""

    @classmethod
    def detect_orphaned_disks(cls, resource_group: str) -> list[OrphanedResource]:
        """Detect unattached disks in a resource group.

        Args:
            resource_group: Azure resource group name

        Returns:
            List of orphaned disk resources

        Raises:
            ResourceCleanupError: If Azure CLI command fails
        """
        try:
            cmd = ["az", "disk", "list", "--resource-group", resource_group, "--output", "json"]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60, check=False
            )

            if result.returncode != 0:
                raise ResourceCleanupError(f"Failed to list disks: {result.stderr.strip()}")

            disks: list[dict[str, Any]] = json.loads(result.stdout)
            orphaned: list[OrphanedResource] = []

            for disk in disks:
                # Check if disk is unattached
                disk_state = disk.get("diskState", "")
                managed_by = disk.get("managedBy")

                if disk_state == "Unattached" or managed_by is None:
                    orphaned.append(
                        OrphanedResource(
                            name=disk["name"],
                            resource_type="disk",
                            resource_group=resource_group,
                            size_gb=disk.get("diskSizeGb"),
                            tier=disk.get("sku", {}).get("name"),
                            location=disk.get("location"),
                        )
                    )

            return orphaned

        except subprocess.TimeoutExpired as e:
            raise ResourceCleanupError("Timeout listing disks") from e
        except json.JSONDecodeError as e:
            raise ResourceCleanupError(f"Failed to parse disk list: {e}") from e
        except Exception as e:
            raise ResourceCleanupError(f"Error detecting orphaned disks: {e}") from e

    @classmethod
    def detect_orphaned_nics(cls, resource_group: str) -> list[OrphanedResource]:
        """Detect orphaned NICs in a resource group.

        Args:
            resource_group: Azure resource group name

        Returns:
            List of orphaned NIC resources

        Raises:
            ResourceCleanupError: If Azure CLI command fails
        """
        try:
            cmd = [
                "az",
                "network",
                "nic",
                "list",
                "--resource-group",
                resource_group,
                "--output",
                "json",
            ]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60, check=False
            )

            if result.returncode != 0:
                raise ResourceCleanupError(f"Failed to list NICs: {result.stderr.strip()}")

            nics: list[dict[str, Any]] = json.loads(result.stdout)
            orphaned: list[OrphanedResource] = []

            for nic in nics:
                # Check if NIC is not attached to a VM
                virtual_machine = nic.get("virtualMachine")

                if virtual_machine is None:
                    orphaned.append(
                        OrphanedResource(
                            name=nic["name"],
                            resource_type="nic",
                            resource_group=resource_group,
                            location=nic.get("location"),
                        )
                    )

            return orphaned

        except subprocess.TimeoutExpired as e:
            raise ResourceCleanupError("Timeout listing NICs") from e
        except json.JSONDecodeError as e:
            raise ResourceCleanupError(f"Failed to parse NIC list: {e}") from e
        except Exception as e:
            raise ResourceCleanupError(f"Error detecting orphaned NICs: {e}") from e

    @classmethod
    def detect_orphaned_public_ips(cls, resource_group: str) -> list[OrphanedResource]:
        """Detect orphaned public IPs in a resource group.

        Args:
            resource_group: Azure resource group name

        Returns:
            List of orphaned public IP resources

        Raises:
            ResourceCleanupError: If Azure CLI command fails
        """
        try:
            cmd = [
                "az",
                "network",
                "public-ip",
                "list",
                "--resource-group",
                resource_group,
                "--output",
                "json",
            ]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60, check=False
            )

            if result.returncode != 0:
                raise ResourceCleanupError(f"Failed to list public IPs: {result.stderr.strip()}")

            public_ips: list[dict[str, Any]] = json.loads(result.stdout)
            orphaned: list[OrphanedResource] = []

            for ip in public_ips:
                # Check if IP is not attached to a NIC
                ip_configuration = ip.get("ipConfiguration")

                if ip_configuration is None:
                    orphaned.append(
                        OrphanedResource(
                            name=ip["name"],
                            resource_type="public-ip",
                            resource_group=resource_group,
                            ip_address=ip.get("ipAddress"),
                            location=ip.get("location"),
                        )
                    )

            return orphaned

        except subprocess.TimeoutExpired as e:
            raise ResourceCleanupError("Timeout listing public IPs") from e
        except json.JSONDecodeError as e:
            raise ResourceCleanupError(f"Failed to parse public IP list: {e}") from e
        except Exception as e:
            raise ResourceCleanupError(f"Error detecting orphaned public IPs: {e}") from e

    @classmethod
    def find_orphaned_resources(cls, resource_group: str) -> CleanupSummary:
        """Find all orphaned resources in a resource group.

        Args:
            resource_group: Azure resource group name

        Returns:
            CleanupSummary with all orphaned resources
        """
        # Detect all orphaned resources
        orphaned_disks = cls.detect_orphaned_disks(resource_group)
        orphaned_nics = cls.detect_orphaned_nics(resource_group)
        orphaned_public_ips = cls.detect_orphaned_public_ips(resource_group)

        # Combine all resources
        all_resources = orphaned_disks + orphaned_nics + orphaned_public_ips

        # Create summary
        summary = CleanupSummary(
            total_orphaned=len(all_resources),
            orphaned_disks=len(orphaned_disks),
            orphaned_nics=len(orphaned_nics),
            orphaned_public_ips=len(orphaned_public_ips),
            resources=all_resources,
        )

        # Calculate cost savings
        summary.calculate_savings()

        return summary

    @classmethod
    def delete_resource(cls, resource: OrphanedResource) -> bool:
        """Delete a single orphaned resource.

        Args:
            resource: OrphanedResource to delete

        Returns:
            True if deletion succeeded, False otherwise
        """
        try:
            if resource.resource_type == "disk":
                cmd = [
                    "az",
                    "disk",
                    "delete",
                    "--name",
                    resource.name,
                    "--resource-group",
                    resource.resource_group,
                    "--yes",
                ]
            elif resource.resource_type == "nic":
                cmd = [
                    "az",
                    "network",
                    "nic",
                    "delete",
                    "--name",
                    resource.name,
                    "--resource-group",
                    resource.resource_group,
                ]
            elif resource.resource_type == "public-ip":
                cmd = [
                    "az",
                    "network",
                    "public-ip",
                    "delete",
                    "--name",
                    resource.name,
                    "--resource-group",
                    resource.resource_group,
                ]
            else:
                logger.error(f"Unknown resource type: {resource.resource_type}")
                return False

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, check=False
            )

            if result.returncode == 0:
                logger.info(f"Successfully deleted {resource.resource_type}: {resource.name}")
                return True
            logger.error(
                f"Failed to delete {resource.resource_type} {resource.name}: {result.stderr}"
            )
            return False

        except subprocess.TimeoutExpired:
            logger.error(f"Timeout deleting {resource.resource_type}: {resource.name}")
            return False
        except Exception as e:
            logger.error(f"Error deleting {resource.resource_type} {resource.name}: {e}")
            return False

    @classmethod
    def cleanup_resources(
        cls, resource_group: str, dry_run: bool = True, force: bool = False
    ) -> CleanupSummary:
        """Clean up orphaned resources in a resource group.

        Args:
            resource_group: Azure resource group name
            dry_run: If True, only show what would be deleted
            force: If True, skip confirmation prompt

        Returns:
            CleanupSummary with cleanup results
        """
        # Find orphaned resources
        summary = cls.find_orphaned_resources(resource_group)
        summary.dry_run = dry_run

        # If no orphaned resources, return early
        if summary.total_orphaned == 0:
            return summary

        # If dry-run, just return the summary
        if dry_run:
            return summary

        # Prompt for confirmation unless force flag is set
        if not force:
            confirmation = input("Type 'delete' to confirm deletion: ").strip()
            if confirmation != "delete":
                summary.cancelled = True
                return summary

        # Delete resources
        for resource in summary.resources:
            if cls.delete_resource(resource):
                summary.deleted_count += 1
            else:
                summary.failed_count += 1
                summary.errors.append(f"Failed to delete {resource.resource_type}: {resource.name}")

        return summary

    @classmethod
    def format_summary(cls, summary: CleanupSummary, dry_run: bool = False) -> str:
        """Format cleanup summary for display.

        Args:
            summary: CleanupSummary to format
            dry_run: Whether this is a dry-run

        Returns:
            Formatted string for CLI display
        """
        lines: list[str] = []
        lines.append("")
        lines.append("=" * 80)
        lines.append("Orphaned Resources Found")
        lines.append("=" * 80)

        # Group resources by type
        disks = [r for r in summary.resources if r.resource_type == "disk"]
        nics = [r for r in summary.resources if r.resource_type == "nic"]
        ips = [r for r in summary.resources if r.resource_type == "public-ip"]

        if disks:
            lines.append(f"\nDISKS ({len(disks)}):")
            for disk in disks:
                size_info = (
                    f"{disk.size_gb} GB, {disk.tier}" if disk.size_gb and disk.tier else "Unknown"
                )
                lines.append(f"  - {disk.name} ({size_info})")

        if nics:
            lines.append(f"\nNETWORK INTERFACES ({len(nics)}):")
            lines.extend(f"  - {nic.name}" for nic in nics)

        if ips:
            lines.append(f"\nPUBLIC IPs ({len(ips)}):")
            for ip in ips:
                ip_info = f" ({ip.ip_address})" if ip.ip_address else ""
                lines.append(f"  - {ip.name}{ip_info}")

        lines.append("")
        lines.append(f"Total Resources: {summary.total_orphaned}")

        if summary.estimated_monthly_savings > 0:
            lines.append(f"Estimated Cost Savings: ~${summary.estimated_monthly_savings:.2f}/month")

        lines.append("")

        if dry_run or summary.dry_run:
            lines.append("DRY RUN - No resources deleted")
            lines.append("Use --delete to remove these resources")
        elif summary.cancelled:
            lines.append("Cleanup cancelled by user")
        elif summary.deleted_count > 0 or summary.failed_count > 0:
            lines.append("Cleanup Results:")
            lines.append(f"  Successfully deleted: {summary.deleted_count}")
            lines.append(f"  Failed: {summary.failed_count}")
            if summary.errors:
                lines.append("\nErrors:")
                lines.extend(f"  - {error}" for error in summary.errors)

        lines.append("=" * 80)
        lines.append("")

        return "\n".join(lines)


__all__ = ["CleanupSummary", "OrphanedResource", "ResourceCleanup", "ResourceCleanupError"]
