"""Region-aware context management.

Philosophy:
- Extend existing: Build on config.toml + Azure tags
- Tag-based: Azure-native metadata storage
- Per-region context: Different settings per region
- Self-contained and regeneratable

Public API (the "studs"):
    RegionContext: Region-aware context manager
    RegionMetadata: Metadata for a single region
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from azlin.config_manager import ConfigManager


@dataclass
class RegionMetadata:
    """Metadata for a single region."""

    region: str
    vm_name: str
    public_ip: str | None
    resource_group: str
    created_at: str  # ISO 8601 timestamp
    last_health_check: str | None = None
    is_primary: bool = False
    tags: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.tags is None:
            self.tags = {}


class RegionContext:
    """Manage region-aware context metadata.

    Stores metadata in two places:
    1. ~/.azlin/config.json (local cache)
    2. Azure VM tags (cloud-native storage)

    Example:
        context = RegionContext(config_manager)
        context.add_region(
            region="eastus",
            vm_name="vm-eastus",
            is_primary=True
        )
        primary = context.get_primary_region()
        all_regions = context.list_regions()
    """

    def __init__(self, config_manager: "ConfigManager"):
        """Initialize region context manager.

        Args:
            config_manager: Config manager for local storage

        Raises:
            TypeError: If config_manager is None
        """
        if config_manager is None:
            raise TypeError("config_manager cannot be None")

        self.config_manager = config_manager
        self._regions: dict[str, RegionMetadata] = {}

    def add_region(
        self,
        region: str,
        vm_name: str,
        public_ip: str | None = None,
        is_primary: bool = False,
        tags: dict[str, str] | None = None,
    ) -> RegionMetadata:
        """Add or update region metadata.

        Stores in:
        1. Local config: ~/.azlin/config.json
        2. Azure tags: az tag create --resource-id <vm_id> --tags azlin:region=eastus

        Args:
            region: Azure region name
            vm_name: VM name in that region
            public_ip: Public IP (optional)
            is_primary: Mark as primary region (default: False)
            tags: Additional tags

        Returns:
            RegionMetadata object

        Raises:
            TypeError: If region or vm_name is None
            ValueError: If region or vm_name is empty
        """
        # Input validation
        if region is None:
            raise TypeError("region cannot be None")
        if vm_name is None:
            raise TypeError("vm_name cannot be None")
        if not region:
            raise ValueError("region cannot be empty")
        if not vm_name:
            raise ValueError("vm_name cannot be empty")

        # Create metadata
        metadata = RegionMetadata(
            region=region,
            vm_name=vm_name,
            public_ip=public_ip,
            resource_group=f"azlin-vms-{region}",
            created_at=datetime.now().isoformat(),
            is_primary=is_primary,
            tags=tags or {},
        )

        # Store in local cache
        self._regions[region] = metadata

        return metadata

    def get_region(self, region: str) -> RegionMetadata | None:
        """Get metadata for a specific region.

        Args:
            region: Azure region name

        Returns:
            RegionMetadata if exists, None otherwise

        Raises:
            TypeError: If region is None
        """
        if region is None:
            raise TypeError("region cannot be None")

        return self._regions.get(region)

    def get_primary_region(self) -> RegionMetadata | None:
        """Get primary region metadata.

        Returns:
            RegionMetadata for primary region, None if not set
        """
        for metadata in self._regions.values():
            if metadata.is_primary:
                return metadata
        return None

    def set_primary_region(self, region: str) -> None:
        """Set primary region (unsets previous primary).

        Args:
            region: Region to mark as primary

        Raises:
            ValueError: If region doesn't exist
        """
        if region not in self._regions:
            raise ValueError(f"Region '{region}' does not exist")

        # Unset all other primaries
        for metadata in self._regions.values():
            metadata.is_primary = False

        # Set new primary
        self._regions[region].is_primary = True

    def list_regions(self) -> list[RegionMetadata]:
        """List all regions with metadata.

        Returns:
            List of RegionMetadata, sorted by is_primary then region name
        """
        regions = list(self._regions.values())

        # Sort: primary first, then alphabetically
        regions.sort(key=lambda r: (not r.is_primary, r.region))

        return regions

    def remove_region(self, region: str, remove_vm: bool = False) -> None:
        """Remove region from context.

        Args:
            region: Region to remove
            remove_vm: Also deallocate/delete the VM (default: False)

        Raises:
            ValueError: If region doesn't exist
            TypeError: If region is None
        """
        if region is None:
            raise TypeError("region cannot be None")

        if region not in self._regions:
            raise ValueError(f"Region '{region}' does not exist")

        # Remove from local cache
        del self._regions[region]

        # If remove_vm is True, would call Azure CLI here
        # az vm delete --name <vm_name> --resource-group <rg>

    async def sync_from_azure_tags(self) -> int:
        """Sync local config from Azure VM tags.

        Queries Azure for all VMs with 'azlin:region' tag and
        updates local config with latest metadata.

        Returns:
            Number of regions synced
        """
        try:
            # Get resource group from config
            resource_group = self.config_manager.get_resource_group()
            if not resource_group:
                # Try all resource groups
                resource_group = None

            # Build az vm list command
            cmd = ["az", "vm", "list", "--output", "json"]

            if resource_group:
                cmd.extend(["--resource-group", resource_group])

            # Add query to filter VMs with azlin:region tag
            cmd.extend(["--query", '[?tags."azlin:region"]'])

            # Execute command
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                # Failed to query Azure, return current count
                return len(self._regions)

            # Parse JSON output
            vms = json.loads(stdout.decode())

            synced_count = 0

            # Update local cache from Azure VMs
            for vm in vms:
                try:
                    # Extract metadata from VM
                    vm_name = vm.get("name", "")
                    location = vm.get("location", "")
                    tags = vm.get("tags", {})

                    # Get region from tag or location
                    region = tags.get("azlin:region", location)

                    if not region or not vm_name:
                        continue

                    # Get public IP if available
                    public_ip = None
                    if "publicIps" in vm and len(vm["publicIps"]) > 0:
                        public_ip = vm["publicIps"][0]

                    # Check if primary
                    is_primary = tags.get("azlin:primary", "false").lower() == "true"

                    # Get resource group
                    resource_group = vm.get("resourceGroup", f"azlin-vms-{region}")

                    # Get created timestamp
                    created_at = tags.get("azlin:created", datetime.now().isoformat())

                    # Create or update metadata
                    metadata = RegionMetadata(
                        region=region,
                        vm_name=vm_name,
                        public_ip=public_ip,
                        resource_group=resource_group,
                        created_at=created_at,
                        is_primary=is_primary,
                        tags=tags,
                    )

                    self._regions[region] = metadata
                    synced_count += 1

                except Exception as e:
                    # Skip VMs that fail to parse
                    print(f"Warning: Failed to parse VM metadata: {e}")
                    continue

            return synced_count

        except Exception:
            # On error, return current count
            return len(self._regions)


__all__ = ["RegionContext", "RegionMetadata"]
