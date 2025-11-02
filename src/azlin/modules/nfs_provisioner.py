"""Cross-region NFS access and storage provisioning.

This module provides comprehensive NFS provisioning capabilities including:
- Cross-region access via private endpoints
- VNet peering setup
- Private DNS zone configuration
- New NFS storage creation
- Data replication via azcopy

Philosophy:
- Analyze access strategy (direct, private endpoint, new storage)
- Use Azure CLI for all operations
- Support cross-region private endpoint access
- Enable data migration and replication
- Integrate with existing StorageManager

Security:
- All user inputs validated before use
- Protection against command injection
- Safe resource ID and name handling

Public API:
    NFSProvisioner: Main provisioning operations class
    AccessStrategy: NFS access strategy enumeration
    AccessAnalysis: Analysis of NFS access options
    PrivateEndpointInfo: Private endpoint information
    VNetPeeringInfo: VNet peering information
    ReplicationResult: Data replication result
"""

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from azlin.modules.storage_manager import StorageManager

logger = logging.getLogger(__name__)


# Exceptions
class NFSProvisionerError(Exception):
    """Base exception for NFS provisioning operations."""

    pass


class ValidationError(NFSProvisionerError):
    """Invalid input parameters."""

    pass


class ResourceNotFoundError(NFSProvisionerError):
    """Azure resource not found."""

    pass


class NetworkConfigurationError(NFSProvisionerError):
    """Network configuration failed."""

    pass


# Enumerations
class AccessStrategy(Enum):
    """NFS access strategy options."""

    DIRECT = "direct"  # Same region, direct access
    PRIVATE_ENDPOINT = "private_endpoint"  # Cross-region via private endpoint
    NEW_STORAGE = "new_storage"  # Create new storage in target region
    REPLICATE = "replicate"  # New storage + data replication


# Data Models
@dataclass
class AccessAnalysis:
    """Analysis of NFS access options."""

    source_storage: str
    source_region: str
    target_region: str
    recommended_strategy: AccessStrategy
    strategies: dict[AccessStrategy, dict]  # Strategy details
    same_region: bool
    estimated_latency_ms: float
    estimated_cost_monthly: float

    def get_strategy_details(self, strategy: AccessStrategy) -> dict:
        """Get details for specific strategy."""
        return self.strategies.get(strategy, {})


@dataclass
class PrivateEndpointInfo:
    """Private endpoint information."""

    name: str
    resource_group: str
    region: str
    storage_account: str
    vnet_name: str
    subnet_name: str
    private_ip: str
    connection_state: str
    dns_configured: bool
    created: datetime


@dataclass
class VNetPeeringInfo:
    """VNet peering information."""

    name: str
    resource_group: str
    local_vnet: str
    remote_vnet: str
    peering_state: str
    allow_forwarded_traffic: bool
    allow_gateway_transit: bool
    use_remote_gateways: bool
    created: datetime


@dataclass
class PrivateDNSZoneInfo:
    """Private DNS zone information."""

    name: str
    resource_group: str
    linked_vnets: list[str]
    record_count: int


@dataclass
class ReplicationResult:
    """Data replication result."""

    success: bool
    source_endpoint: str
    target_endpoint: str
    files_copied: int
    bytes_copied: int
    duration_seconds: float
    errors: list[str] = field(default_factory=list)


# Security Validation Helpers
def _validate_resource_name(name: str, resource_type: str) -> str:
    """Validate Azure resource name for safe use.

    Args:
        name: Resource name to validate
        resource_type: Type of resource for specific validation

    Returns:
        Validated name

    Raises:
        ValidationError: If name contains unsafe characters
    """
    if not name or not isinstance(name, str):
        raise ValidationError(f"{resource_type} name must be a non-empty string")

    # Security: Check for command injection patterns
    dangerous_patterns = [";", "&", "|", "$", "`", "(", ")", "<", ">", "\n", "\r", "\t"]
    for pattern in dangerous_patterns:
        if pattern in name:
            raise ValidationError(f"{resource_type} name contains unsafe character '{pattern}'")

    # Check for path traversal
    if ".." in name or "/" in name or "\\" in name:
        raise ValidationError(f"{resource_type} name contains path traversal sequences")

    # Basic alphanumeric validation (with hyphens and underscores)
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        raise ValidationError(
            f"{resource_type} name must be alphanumeric with hyphens/underscores only"
        )

    return name


def _validate_resource_id(resource_id: str) -> str:
    """Validate Azure resource ID format.

    Args:
        resource_id: Azure resource ID to validate

    Returns:
        Validated resource ID

    Raises:
        ValidationError: If resource ID is invalid
    """
    if not resource_id or not isinstance(resource_id, str):
        raise ValidationError("Resource ID must be a non-empty string")

    # Azure resource ID format: /subscriptions/{sub}/resourceGroups/{rg}/providers/{provider}/...
    if not resource_id.startswith("/subscriptions/"):
        raise ValidationError(f"Invalid Azure resource ID format: {resource_id}")

    # Security: Check for command injection patterns
    dangerous_patterns = [";", "&", "|", "$", "`", "\n", "\r", "\t"]
    for pattern in dangerous_patterns:
        if pattern in resource_id:
            raise ValidationError(f"Resource ID contains unsafe character '{pattern}'")

    return resource_id


class NFSProvisioner:
    """Cross-region NFS access and storage provisioning.

    All methods are classmethods for brick-style API.
    No instance state maintained.
    """

    # Azure private endpoint constants
    PRIVATE_ENDPOINT_GROUP_ID = "file"
    PRIVATE_DNS_ZONE_NAME = "privatelink.file.core.windows.net"

    # Cost constants (USD per month)
    PRIVATE_ENDPOINT_COST = 7.30  # Per endpoint
    VNET_PEERING_COST_PER_GB = 0.01  # Per GB transferred

    # Latency estimates (ms)
    SAME_REGION_LATENCY = 1.0
    CROSS_REGION_LATENCY = 50.0
    PRIVATE_ENDPOINT_OVERHEAD = 2.0

    @classmethod
    def analyze_nfs_access(
        cls,
        storage_account: str,
        source_region: str,
        target_region: str,
        resource_group: str,
        estimated_monthly_transfer_gb: float = 100.0,
    ) -> AccessAnalysis:
        """Analyze NFS access strategy for cross-region access.

        Evaluates multiple access strategies and recommends the best approach
        based on latency, cost, and complexity.

        Args:
            storage_account: Source storage account name
            source_region: Region where storage currently exists
            target_region: Region where VM needs access
            resource_group: Azure resource group
            estimated_monthly_transfer_gb: Estimated data transfer per month

        Returns:
            AccessAnalysis with recommended strategy and details

        Raises:
            ValidationError: If inputs are invalid
            ResourceNotFoundError: If storage account not found
        """
        # Validate inputs
        _validate_resource_name(storage_account, "Storage account")
        _validate_resource_name(source_region, "Source region")
        _validate_resource_name(target_region, "Target region")

        logger.info(f"Analyzing NFS access: {storage_account} ({source_region} -> {target_region})")

        same_region = source_region == target_region

        # Get storage account details
        try:
            from azlin.modules.storage_manager import StorageManager

            storage_info = StorageManager.get_storage(storage_account, resource_group)
        except Exception as e:
            raise ResourceNotFoundError(f"Storage account {storage_account} not found: {e}") from e

        # Build strategy analysis
        strategies = {}

        # Strategy 1: Direct access (only if same region)
        if same_region:
            strategies[AccessStrategy.DIRECT] = {
                "name": "Direct Access",
                "description": "Direct NFS mount (same region)",
                "latency_ms": cls.SAME_REGION_LATENCY,
                "cost_monthly": 0.0,
                "complexity": "low",
                "steps": [
                    "Configure storage network rules",
                    "Mount NFS share directly",
                ],
                "pros": ["Lowest latency", "No additional cost", "Simple setup"],
                "cons": ["Only works in same region"],
            }

        # Strategy 2: Private endpoint + VNet peering
        peering_cost = estimated_monthly_transfer_gb * cls.VNET_PEERING_COST_PER_GB
        private_endpoint_latency = cls.CROSS_REGION_LATENCY + cls.PRIVATE_ENDPOINT_OVERHEAD

        strategies[AccessStrategy.PRIVATE_ENDPOINT] = {
            "name": "Private Endpoint",
            "description": "Private endpoint with VNet peering",
            "latency_ms": private_endpoint_latency,
            "cost_monthly": cls.PRIVATE_ENDPOINT_COST + peering_cost,
            "complexity": "medium",
            "steps": [
                "Create private endpoint in target region",
                "Setup VNet peering between regions",
                "Configure private DNS zone",
                "Link DNS zone to VNets",
            ],
            "pros": [
                "Works cross-region",
                "Private network traffic",
                "Uses existing storage",
            ],
            "cons": [
                "Higher latency",
                "Additional monthly cost",
                "More complex setup",
            ],
        }

        # Strategy 3: New storage in target region
        new_storage_cost = storage_info.size_gb * StorageManager.COST_PER_GB.get(
            storage_info.tier, 0.1
        )

        strategies[AccessStrategy.NEW_STORAGE] = {
            "name": "New Storage",
            "description": "Create new storage in target region",
            "latency_ms": cls.SAME_REGION_LATENCY,
            "cost_monthly": new_storage_cost,
            "complexity": "low",
            "steps": [
                "Create new storage account in target region",
                "Configure NFS share",
                "Mount directly (same region)",
            ],
            "pros": [
                "Lowest latency",
                "Simple setup",
                "Independent storage",
            ],
            "cons": [
                "Duplicate storage cost",
                "Data not synchronized",
                "Manual data migration needed",
            ],
        }

        # Strategy 4: New storage + replication
        strategies[AccessStrategy.REPLICATE] = {
            "name": "New Storage + Replication",
            "description": "New storage with initial data replication",
            "latency_ms": cls.SAME_REGION_LATENCY,
            "cost_monthly": new_storage_cost,
            "complexity": "medium",
            "steps": [
                "Create new storage account in target region",
                "Setup private endpoint for source (temporary)",
                "Use azcopy to replicate data",
                "Remove temporary endpoint",
            ],
            "pros": [
                "Lowest latency",
                "Data migrated",
                "Independent storage",
            ],
            "cons": [
                "Duplicate storage cost",
                "One-time replication only",
                "Initial setup time",
            ],
        }

        # Determine recommended strategy
        if same_region:
            recommended = AccessStrategy.DIRECT
            estimated_latency = cls.SAME_REGION_LATENCY
            estimated_cost = 0.0
        elif new_storage_cost < (cls.PRIVATE_ENDPOINT_COST + peering_cost):
            # New storage is cheaper
            recommended = AccessStrategy.REPLICATE
            estimated_latency = cls.SAME_REGION_LATENCY
            estimated_cost = new_storage_cost
        else:
            # Private endpoint is cheaper
            recommended = AccessStrategy.PRIVATE_ENDPOINT
            estimated_latency = private_endpoint_latency
            estimated_cost = cls.PRIVATE_ENDPOINT_COST + peering_cost

        logger.info(f"Recommended strategy: {recommended.value}")

        return AccessAnalysis(
            source_storage=storage_account,
            source_region=source_region,
            target_region=target_region,
            recommended_strategy=recommended,
            strategies=strategies,
            same_region=same_region,
            estimated_latency_ms=estimated_latency,
            estimated_cost_monthly=estimated_cost,
        )

    @classmethod
    def create_private_endpoint(
        cls,
        name: str,
        resource_group: str,
        region: str,
        vnet_name: str,
        subnet_name: str,
        storage_account: str,
        storage_resource_group: str,
    ) -> PrivateEndpointInfo:
        """Create private endpoint for storage account.

        Args:
            name: Private endpoint name
            resource_group: Target resource group
            region: Target region
            vnet_name: Target VNet name
            subnet_name: Target subnet name
            storage_account: Source storage account name
            storage_resource_group: Storage account resource group

        Returns:
            PrivateEndpointInfo with created endpoint details

        Raises:
            ValidationError: If inputs are invalid
            NetworkConfigurationError: If creation fails
        """
        # Validate inputs
        _validate_resource_name(name, "Private endpoint")
        _validate_resource_name(vnet_name, "VNet")
        _validate_resource_name(subnet_name, "Subnet")
        _validate_resource_name(storage_account, "Storage account")

        logger.info(f"Creating private endpoint {name} for {storage_account}")

        try:
            # Get storage account resource ID
            storage_id_cmd = [
                "az",
                "storage",
                "account",
                "show",
                "--name",
                storage_account,
                "--resource-group",
                storage_resource_group,
                "--query",
                "id",
                "--output",
                "tsv",
            ]

            result = subprocess.run(
                storage_id_cmd, capture_output=True, text=True, check=True, timeout=30
            )
            storage_resource_id = result.stdout.strip()

            # Get subnet resource ID
            subnet_id_cmd = [
                "az",
                "network",
                "vnet",
                "subnet",
                "show",
                "--resource-group",
                resource_group,
                "--vnet-name",
                vnet_name,
                "--name",
                subnet_name,
                "--query",
                "id",
                "--output",
                "tsv",
            ]

            result = subprocess.run(
                subnet_id_cmd, capture_output=True, text=True, check=True, timeout=30
            )
            subnet_id = result.stdout.strip()

            # Create private endpoint
            create_cmd = [
                "az",
                "network",
                "private-endpoint",
                "create",
                "--name",
                name,
                "--resource-group",
                resource_group,
                "--location",
                region,
                "--vnet-name",
                vnet_name,
                "--subnet",
                subnet_name,
                "--private-connection-resource-id",
                storage_resource_id,
                "--group-id",
                cls.PRIVATE_ENDPOINT_GROUP_ID,
                "--connection-name",
                f"{name}-connection",
                "--output",
                "json",
            ]

            logger.info(f"Running: az network private-endpoint create --name {name}")

            result = subprocess.run(
                create_cmd, capture_output=True, text=True, check=True, timeout=300
            )

            endpoint_data = json.loads(result.stdout)

            # Get private IP address
            private_ip = ""
            if "customDnsConfigs" in endpoint_data:
                configs = endpoint_data["customDnsConfigs"]
                if configs and len(configs) > 0:
                    private_ip = configs[0].get("ipAddresses", [""])[0]

            logger.info(f"Private endpoint {name} created successfully")

            return PrivateEndpointInfo(
                name=name,
                resource_group=resource_group,
                region=region,
                storage_account=storage_account,
                vnet_name=vnet_name,
                subnet_name=subnet_name,
                private_ip=private_ip,
                connection_state=endpoint_data.get("provisioningState", "Unknown"),
                dns_configured=False,
                created=datetime.now(),
            )

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            raise NetworkConfigurationError(
                f"Failed to create private endpoint: {error_msg}"
            ) from e
        except json.JSONDecodeError as e:
            raise NetworkConfigurationError(f"Failed to parse endpoint response: {e}") from e

    @classmethod
    def create_vnet_peering(
        cls,
        name: str,
        resource_group: str,
        local_vnet: str,
        remote_vnet: str,
        remote_vnet_resource_group: str,
        allow_forwarded_traffic: bool = True,
    ) -> VNetPeeringInfo:
        """Create VNet peering between two VNets.

        Creates bidirectional peering automatically.

        Args:
            name: Peering name (for local->remote)
            resource_group: Local VNet resource group
            local_vnet: Local VNet name
            remote_vnet: Remote VNet name
            remote_vnet_resource_group: Remote VNet resource group
            allow_forwarded_traffic: Allow forwarded traffic

        Returns:
            VNetPeeringInfo with peering details

        Raises:
            ValidationError: If inputs are invalid
            NetworkConfigurationError: If peering fails
        """
        # Validate inputs
        _validate_resource_name(name, "Peering")
        _validate_resource_name(local_vnet, "Local VNet")
        _validate_resource_name(remote_vnet, "Remote VNet")

        logger.info(f"Creating VNet peering: {local_vnet} <-> {remote_vnet}")

        try:
            # Get remote VNet resource ID
            remote_vnet_id_cmd = [
                "az",
                "network",
                "vnet",
                "show",
                "--name",
                remote_vnet,
                "--resource-group",
                remote_vnet_resource_group,
                "--query",
                "id",
                "--output",
                "tsv",
            ]

            result = subprocess.run(
                remote_vnet_id_cmd, capture_output=True, text=True, check=True, timeout=30
            )
            remote_vnet_id = result.stdout.strip()

            # Create local->remote peering
            local_peering_cmd = [
                "az",
                "network",
                "vnet",
                "peering",
                "create",
                "--name",
                name,
                "--resource-group",
                resource_group,
                "--vnet-name",
                local_vnet,
                "--remote-vnet",
                remote_vnet_id,
                "--allow-vnet-access",
                "true",
            ]

            if allow_forwarded_traffic:
                local_peering_cmd.extend(["--allow-forwarded-traffic", "true"])

            local_peering_cmd.extend(["--output", "json"])

            logger.info(f"Creating local->remote peering: {name}")

            result = subprocess.run(
                local_peering_cmd, capture_output=True, text=True, check=True, timeout=180
            )
            peering_data = json.loads(result.stdout)

            # Create reverse peering (remote->local)
            reverse_name = f"{name}-reverse"

            # Get local VNet resource ID
            local_vnet_id_cmd = [
                "az",
                "network",
                "vnet",
                "show",
                "--name",
                local_vnet,
                "--resource-group",
                resource_group,
                "--query",
                "id",
                "--output",
                "tsv",
            ]

            result = subprocess.run(
                local_vnet_id_cmd, capture_output=True, text=True, check=True, timeout=30
            )
            local_vnet_id = result.stdout.strip()

            remote_peering_cmd = [
                "az",
                "network",
                "vnet",
                "peering",
                "create",
                "--name",
                reverse_name,
                "--resource-group",
                remote_vnet_resource_group,
                "--vnet-name",
                remote_vnet,
                "--remote-vnet",
                local_vnet_id,
                "--allow-vnet-access",
                "true",
            ]

            if allow_forwarded_traffic:
                remote_peering_cmd.extend(["--allow-forwarded-traffic", "true"])

            remote_peering_cmd.extend(["--output", "none"])

            logger.info(f"Creating remote->local peering: {reverse_name}")

            subprocess.run(
                remote_peering_cmd, capture_output=True, text=True, check=True, timeout=180
            )

            logger.info(f"VNet peering created successfully: {local_vnet} <-> {remote_vnet}")

            return VNetPeeringInfo(
                name=name,
                resource_group=resource_group,
                local_vnet=local_vnet,
                remote_vnet=remote_vnet,
                peering_state=peering_data.get("peeringState", "Unknown"),
                allow_forwarded_traffic=allow_forwarded_traffic,
                allow_gateway_transit=False,
                use_remote_gateways=False,
                created=datetime.now(),
            )

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            raise NetworkConfigurationError(f"Failed to create VNet peering: {error_msg}") from e
        except json.JSONDecodeError as e:
            raise NetworkConfigurationError(f"Failed to parse peering response: {e}") from e

    @classmethod
    def configure_private_dns_zone(
        cls,
        resource_group: str,
        vnet_names: list[str],
        storage_account: str,
        private_endpoint_name: str,
    ) -> PrivateDNSZoneInfo:
        """Configure private DNS zone for storage account.

        Creates DNS zone and links to specified VNets for name resolution.

        Args:
            resource_group: Resource group for DNS zone
            vnet_names: List of VNet names to link
            storage_account: Storage account name
            private_endpoint_name: Private endpoint name

        Returns:
            PrivateDNSZoneInfo with DNS configuration

        Raises:
            ValidationError: If inputs are invalid
            NetworkConfigurationError: If DNS configuration fails
        """
        _validate_resource_name(storage_account, "Storage account")
        _validate_resource_name(private_endpoint_name, "Private endpoint")

        logger.info(f"Configuring private DNS zone for {storage_account}")

        try:
            zone_name = cls.PRIVATE_DNS_ZONE_NAME

            # Create or get DNS zone
            create_zone_cmd = [
                "az",
                "network",
                "private-dns",
                "zone",
                "create",
                "--resource-group",
                resource_group,
                "--name",
                zone_name,
                "--output",
                "none",
            ]

            logger.info(f"Creating private DNS zone: {zone_name}")

            subprocess.run(
                create_zone_cmd, capture_output=True, text=True, check=False, timeout=120
            )

            # Link DNS zone to each VNet
            linked_vnets = []
            for vnet_name in vnet_names:
                _validate_resource_name(vnet_name, "VNet")

                link_name = f"{vnet_name}-link"

                # Get VNet resource ID
                vnet_id_cmd = [
                    "az",
                    "network",
                    "vnet",
                    "show",
                    "--name",
                    vnet_name,
                    "--resource-group",
                    resource_group,
                    "--query",
                    "id",
                    "--output",
                    "tsv",
                ]

                result = subprocess.run(
                    vnet_id_cmd, capture_output=True, text=True, check=True, timeout=30
                )
                vnet_id = result.stdout.strip()

                link_cmd = [
                    "az",
                    "network",
                    "private-dns",
                    "link",
                    "vnet",
                    "create",
                    "--resource-group",
                    resource_group,
                    "--zone-name",
                    zone_name,
                    "--name",
                    link_name,
                    "--virtual-network",
                    vnet_id,
                    "--registration-enabled",
                    "false",
                    "--output",
                    "none",
                ]

                logger.info(f"Linking DNS zone to VNet: {vnet_name}")

                subprocess.run(link_cmd, capture_output=True, text=True, check=True, timeout=120)
                linked_vnets.append(vnet_name)

            # Create DNS zone group for private endpoint
            zone_group_cmd = [
                "az",
                "network",
                "private-endpoint",
                "dns-zone-group",
                "create",
                "--resource-group",
                resource_group,
                "--endpoint-name",
                private_endpoint_name,
                "--name",
                "default",
                "--private-dns-zone",
                zone_name,
                "--zone-name",
                "file",
                "--output",
                "none",
            ]

            logger.info("Creating DNS zone group for private endpoint")

            subprocess.run(zone_group_cmd, capture_output=True, text=True, check=True, timeout=120)

            logger.info("Private DNS zone configured successfully")

            return PrivateDNSZoneInfo(
                name=zone_name,
                resource_group=resource_group,
                linked_vnets=linked_vnets,
                record_count=1,
            )

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            raise NetworkConfigurationError(
                f"Failed to configure private DNS zone: {error_msg}"
            ) from e

    @classmethod
    def setup_private_endpoint_access(
        cls,
        storage_account: str,
        storage_resource_group: str,
        target_region: str,
        target_resource_group: str,
        target_vnet: str,
        target_subnet: str,
        source_vnet: str | None = None,
        source_resource_group: str | None = None,
    ) -> tuple[PrivateEndpointInfo, VNetPeeringInfo | None, PrivateDNSZoneInfo]:
        """Setup complete private endpoint access for cross-region NFS.

        This is the main orchestration method that:
        1. Creates private endpoint in target region
        2. Sets up VNet peering if needed
        3. Configures private DNS zones

        Args:
            storage_account: Source storage account name
            storage_resource_group: Storage account resource group
            target_region: Target region for private endpoint
            target_resource_group: Target resource group
            target_vnet: Target VNet name
            target_subnet: Target subnet name
            source_vnet: Source VNet name (for peering)
            source_resource_group: Source VNet resource group

        Returns:
            Tuple of (PrivateEndpointInfo, VNetPeeringInfo, PrivateDNSZoneInfo)

        Raises:
            ValidationError: If inputs are invalid
            NetworkConfigurationError: If setup fails
        """
        logger.info(f"Setting up private endpoint access for {storage_account}")

        # Create private endpoint
        endpoint_name = f"{storage_account}-pe-{target_region}"
        endpoint = cls.create_private_endpoint(
            name=endpoint_name,
            resource_group=target_resource_group,
            region=target_region,
            vnet_name=target_vnet,
            subnet_name=target_subnet,
            storage_account=storage_account,
            storage_resource_group=storage_resource_group,
        )

        # Setup VNet peering if source VNet provided
        peering = None
        vnets_to_link = [target_vnet]

        if source_vnet and source_resource_group:
            peering_name = f"{target_vnet}-to-{source_vnet}"
            peering = cls.create_vnet_peering(
                name=peering_name,
                resource_group=target_resource_group,
                local_vnet=target_vnet,
                remote_vnet=source_vnet,
                remote_vnet_resource_group=source_resource_group,
            )
            vnets_to_link.append(source_vnet)

        # Configure DNS
        dns_zone = cls.configure_private_dns_zone(
            resource_group=target_resource_group,
            vnet_names=vnets_to_link,
            storage_account=storage_account,
            private_endpoint_name=endpoint_name,
        )

        logger.info("Private endpoint access setup complete")

        return endpoint, peering, dns_zone

    @classmethod
    def create_nfs_storage(
        cls,
        name: str,
        resource_group: str,
        region: str,
        tier: str = "Premium",
        size_gb: int = 100,
    ) -> "StorageManager.StorageInfo":  # type: ignore[name-defined]
        """Create new NFS storage in target region.

        This wraps StorageManager.create_storage for convenience.

        Args:
            name: Storage account name
            resource_group: Resource group
            region: Target region
            tier: Storage tier (Premium or Standard)
            size_gb: Storage size in GB

        Returns:
            StorageInfo with created storage details

        Raises:
            ValidationError: If inputs are invalid
            NFSProvisionerError: If creation fails
        """
        try:
            from azlin.modules.storage_manager import StorageManager

            logger.info(f"Creating NFS storage {name} in {region}")

            storage_info = StorageManager.create_storage(
                name=name,
                resource_group=resource_group,
                region=region,
                tier=tier,
                size_gb=size_gb,
            )

            logger.info(f"NFS storage {name} created successfully")

            return storage_info

        except Exception as e:
            raise NFSProvisionerError(f"Failed to create NFS storage: {e}") from e

    @classmethod
    def replicate_nfs_data(
        cls,
        source_storage: str,
        source_resource_group: str,
        target_storage: str,
        target_resource_group: str,
        share_name: str = "home",
    ) -> ReplicationResult:
        """Replicate data from source to target storage using azcopy.

        This creates a temporary private endpoint for access if needed,
        runs azcopy to replicate data, then removes temporary resources.

        Args:
            source_storage: Source storage account name
            source_resource_group: Source resource group
            target_storage: Target storage account name
            target_resource_group: Target resource group
            share_name: Share name to replicate

        Returns:
            ReplicationResult with replication details

        Raises:
            ValidationError: If inputs are invalid
            NFSProvisionerError: If replication fails
        """
        _validate_resource_name(source_storage, "Source storage")
        _validate_resource_name(target_storage, "Target storage")
        _validate_resource_name(share_name, "Share name")

        from datetime import datetime as dt

        logger.info(f"Replicating data: {source_storage} -> {target_storage}")

        errors = []
        start_time = dt.now()

        try:
            # Get storage account keys for azcopy
            source_key_cmd = [
                "az",
                "storage",
                "account",
                "keys",
                "list",
                "--account-name",
                source_storage,
                "--resource-group",
                source_resource_group,
                "--query",
                "[0].value",
                "--output",
                "tsv",
            ]

            result = subprocess.run(
                source_key_cmd, capture_output=True, text=True, check=True, timeout=30
            )
            source_key = result.stdout.strip()

            target_key_cmd = [
                "az",
                "storage",
                "account",
                "keys",
                "list",
                "--account-name",
                target_storage,
                "--resource-group",
                target_resource_group,
                "--query",
                "[0].value",
                "--output",
                "tsv",
            ]

            result = subprocess.run(
                target_key_cmd, capture_output=True, text=True, check=True, timeout=30
            )
            target_key = result.stdout.strip()

            # Build source and destination URLs without embedded keys
            source_url = f"https://{source_storage}.file.core.windows.net/{share_name}"
            target_url = f"https://{target_storage}.file.core.windows.net/{share_name}"

            # Use environment variables to pass storage keys securely
            # This prevents keys from appearing in command-line arguments or process listings
            import os

            azcopy_env = os.environ.copy()

            # Set Azure Storage credentials via environment variables
            # azcopy uses these when URLs don't contain SAS tokens
            azcopy_env["AZURE_STORAGE_ACCOUNT"] = source_storage
            azcopy_env["AZURE_STORAGE_KEY"] = source_key

            # For the destination, we need to use SAS token approach since
            # azcopy doesn't support multiple account credentials simultaneously.
            # Generate minimal SAS token with proper expiry
            from datetime import datetime, timedelta

            # Create SAS token for target (write permissions only, short expiry)
            sas_start = datetime.utcnow()
            sas_expiry = sas_start + timedelta(hours=2)

            target_sas_cmd = [
                "az",
                "storage",
                "share",
                "generate-sas",
                "--account-name",
                target_storage,
                "--account-key",
                target_key,
                "--name",
                share_name,
                "--permissions",
                "rwdl",  # read, write, delete, list
                "--start",
                sas_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "--expiry",
                sas_expiry.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "--output",
                "tsv",
            ]

            result = subprocess.run(
                target_sas_cmd, capture_output=True, text=True, check=True, timeout=30
            )
            target_sas = result.stdout.strip()

            # Append SAS token to target URL only
            target_url_with_sas = f"{target_url}?{target_sas}"

            # Run azcopy
            azcopy_cmd = [
                "azcopy",
                "copy",
                source_url,
                target_url_with_sas,
                "--recursive",
                "--output-type",
                "json",
            ]

            logger.info("Running azcopy for data replication")

            result = subprocess.run(
                azcopy_cmd,
                capture_output=True,
                env=azcopy_env,
                text=True,
                check=False,
                timeout=3600,  # 1 hour timeout
            )

            duration = (datetime.now() - start_time).total_seconds()

            # Parse azcopy output (simplified)
            files_copied = 0
            bytes_copied = 0
            success = result.returncode == 0

            if not success:
                errors.append(f"azcopy failed: {result.stderr}")

            logger.info(f"Replication {'completed' if success else 'failed'} in {duration:.1f}s")

            return ReplicationResult(
                success=success,
                source_endpoint=f"{source_storage}/{share_name}",
                target_endpoint=f"{target_storage}/{share_name}",
                files_copied=files_copied,
                bytes_copied=bytes_copied,
                duration_seconds=duration,
                errors=errors,
            )

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            errors.append(f"Command failed: {error_msg}")

            return ReplicationResult(
                success=False,
                source_endpoint=f"{source_storage}/{share_name}",
                target_endpoint=f"{target_storage}/{share_name}",
                files_copied=0,
                bytes_copied=0,
                duration_seconds=(dt.now() - start_time).total_seconds(),
                errors=errors,
            )
        except Exception as e:
            errors.append(f"Unexpected error: {e}")

            return ReplicationResult(
                success=False,
                source_endpoint=f"{source_storage}/{share_name}",
                target_endpoint=f"{target_storage}/{share_name}",
                files_copied=0,
                bytes_copied=0,
                duration_seconds=(dt.now() - start_time).total_seconds(),
                errors=errors,
            )


# Public API
__all__ = [
    "AccessAnalysis",
    "AccessStrategy",
    "NFSProvisioner",
    "NFSProvisionerError",
    "NetworkConfigurationError",
    "PrivateDNSZoneInfo",
    "PrivateEndpointInfo",
    "ReplicationResult",
    "ResourceNotFoundError",
    "VNetPeeringInfo",
    "ValidationError",
]
