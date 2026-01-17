"""VM provisioning module.

This module handles Azure VM creation with cloud-init for dev tools installation.
It provisions Ubuntu VMs with all required development tools pre-installed.

Security:
- Input validation (VM names, sizes, regions)
- SSH key authentication only (no passwords)
- Sanitized logging
- Proper error handling
"""

import json
import logging
import re
import subprocess
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, ClassVar

from azlin.azure_cli_visibility import AzureCLIExecutor
from azlin.quota_error_handler import QuotaErrorHandler
from azlin.resource_conflict_error_handler import (
    format_conflict_error,
    is_resource_conflict,
    parse_conflict_error,
)

logger = logging.getLogger(__name__)


class ProvisioningError(Exception):
    """Raised when VM provisioning fails."""

    pass


@dataclass
class VMConfig:
    """VM configuration parameters."""

    name: str
    resource_group: str
    location: str = "westus2"  # Better capacity than eastus
    size: str = "Standard_E16as_v5"  # Memory-optimized: 128GB RAM, 16 vCPU, 12.5 Gbps network
    image: str = "Canonical:ubuntu-24_04-lts:server:latest"
    ssh_public_key: str | None = None
    admin_username: str = "azureuser"
    disable_password_auth: bool = True
    session_name: str | None = None  # Optional session name for tag management
    public_ip_enabled: bool = True  # Whether to create a public IP (False for bastion-only VMs)
    home_disk_enabled: bool = True  # Whether to create separate /home disk
    home_disk_size_gb: int = 100  # Size of separate /home disk in GB
    home_disk_sku: str = "Standard_LRS"  # Storage SKU for /home disk


@dataclass
class VMDetails:
    """VM provisioning result details."""

    name: str
    resource_group: str
    location: str
    size: str
    public_ip: str | None = None
    private_ip: str | None = None
    state: str = "Unknown"
    id: str | None = None


@dataclass
class ProvisioningFailure:
    """Details of a failed VM provisioning."""

    config: VMConfig
    error: str
    error_type: str  # 'sku_unavailable', 'timeout', 'auth', 'unknown'


@dataclass
class ResourceGroupFailure:
    """Details of a failed RG creation."""

    rg_name: str
    location: str
    error: str


@dataclass
class PoolProvisioningResult:
    """Result of pool provisioning operation.

    Supports partial success scenarios where some VMs provision
    successfully while others fail.

    Attributes:
        total_requested: Number of VMs requested
        successful: List of successfully provisioned VMs
        failed: List of failures with error details
        rg_failures: Resource group creation failures
    """

    total_requested: int
    successful: list[VMDetails]
    failed: list[ProvisioningFailure]
    rg_failures: list[ResourceGroupFailure]

    @property
    def success_count(self) -> int:
        """Number of successfully provisioned VMs."""
        return len(self.successful)

    @property
    def failure_count(self) -> int:
        """Number of failed VM provisions."""
        return len(self.failed)

    @property
    def all_succeeded(self) -> bool:
        """True if all VMs provisioned successfully."""
        return self.failure_count == 0 and len(self.rg_failures) == 0

    @property
    def any_succeeded(self) -> bool:
        """True if at least one VM provisioned successfully."""
        return self.success_count > 0

    @property
    def partial_success(self) -> bool:
        """True if some but not all VMs succeeded."""
        return self.any_succeeded and not self.all_succeeded

    def get_summary(self) -> str:
        """Get human-readable summary."""
        rg_msg = f", {len(self.rg_failures)} RG failures" if self.rg_failures else ""
        return (
            f"Pool: {self.success_count}/{self.total_requested} succeeded, "
            f"{self.failure_count} failed{rg_msg}"
        )


class ThreadSafeProgressReporter:
    """Thread-safe progress message coordinator."""

    def __init__(self, callback: Callable[[str], None] | None = None):
        """Initialize progress reporter.

        Args:
            callback: Optional callback function for progress updates
        """
        self._callback = callback
        self._lock = threading.Lock()

    def report(self, message: str):
        """Report progress message (thread-safe).

        Args:
            message: Progress message to report
        """
        with self._lock:
            if self._callback:
                self._callback(message)
            logger.info(message)


class ResourceGroupManager:
    """Thread-safe resource group creation coordinator.

    Ensures only one thread creates each resource group,
    while allowing parallel creation of different RGs.
    """

    def __init__(self):
        """Initialize RG manager."""
        self._rg_locks: dict[str, threading.Lock] = {}
        self._manager_lock = threading.Lock()
        self._created_rgs: set[str] = set()

    def ensure_resource_group(
        self, rg_name: str, location: str, provisioner: "VMProvisioner"
    ) -> bool:
        """Ensure resource group exists (thread-safe).

        Uses per-RG locking to prevent race conditions.
        Multiple threads for same RG serialize on the RG lock.
        Different RGs can be created in parallel.

        Args:
            rg_name: Resource group name
            location: Azure region
            provisioner: VMProvisioner instance to use

        Returns:
            True if RG exists or was created successfully

        Raises:
            ProvisioningError: If RG creation fails
        """
        # Get or create lock for this specific RG
        with self._manager_lock:
            if rg_name not in self._rg_locks:
                self._rg_locks[rg_name] = threading.Lock()
            rg_lock = self._rg_locks[rg_name]

        # Acquire RG-specific lock (only one thread per RG)
        with rg_lock:
            # Check if already created in this session
            if rg_name in self._created_rgs:
                logger.debug(f"RG {rg_name} already created in this session")
                return True

            # Create RG (only one thread per RG gets here)
            logger.info(f"Creating resource group: {rg_name}")
            result = provisioner.create_resource_group(rg_name, location)
            self._created_rgs.add(rg_name)
            return result


class VMProvisioner:
    """Provision Azure Ubuntu VMs with development tools.

    This class handles VM creation using Azure CLI, including:
    - Resource group creation
    - Network infrastructure setup
    - VM provisioning with cloud-init
    - SSH key configuration
    - Tool installation via cloud-init

    Development tools installed:
    1. Docker
    2. Azure CLI
    3. GitHub CLI
    4. Git
    5. Node.js & npm
    6. Python 3.13+ (from deadsnakes PPA)
    7. Rust
    8. Golang
    9. .NET 10 RC
    10. astral-uv (uv package manager)
    11. OpenAI Codex CLI (optional, disabled by default for faster provisioning)
    12. GitHub Copilot CLI (optional, disabled by default for faster provisioning)
    13. Claude Code CLI (optional, disabled by default for faster provisioning)
    """

    # Valid VM sizes whitelist (2025 current-gen SKUs)
    VALID_VM_SIZES: ClassVar[set[str]] = {
        # B-series v1 (legacy but still available)
        "Standard_B1s",
        "Standard_B1ms",
        "Standard_B2s",
        "Standard_B2ms",
        "Standard_B4ms",
        "Standard_B8ms",
        # B-series v2 (current gen, Intel)
        "Standard_B2s_v2",
        "Standard_B2ms_v2",
        "Standard_B4ms_v2",
        # D-series v3 (older gen)
        "Standard_D2s_v3",
        "Standard_D4s_v3",
        "Standard_D8s_v3",
        # D-series v4 (previous gen)
        "Standard_D2s_v4",
        "Standard_D4s_v4",
        "Standard_D8s_v4",
        # D-series v5 (current gen)
        "Standard_D2s_v5",
        "Standard_D4s_v5",
        "Standard_D8s_v5",
        "Standard_D16s_v5",
        # D-series v5 AMD (cost-optimized)
        "Standard_D2as_v5",
        "Standard_D4as_v5",
        "Standard_D8as_v5",
        "Standard_D16as_v5",
        # E-series v3 (memory-optimized, older gen)
        "Standard_E2s_v3",
        "Standard_E4s_v3",
        "Standard_E8s_v3",
        # E-series v4 (memory-optimized, previous gen)
        "Standard_E2s_v4",
        "Standard_E4s_v4",
        "Standard_E8s_v4",
        # E-series v5 Intel (memory-optimized, current gen)
        "Standard_E2s_v5",
        "Standard_E4s_v5",
        "Standard_E8s_v5",
        "Standard_E16s_v5",
        "Standard_E20s_v5",
        "Standard_E32s_v5",
        # E-series v5 AMD (memory-optimized, cost-effective, recommended for 64GB+)
        "Standard_E2as_v5",
        "Standard_E4as_v5",
        "Standard_E8as_v5",
        "Standard_E16as_v5",  # NEW DEFAULT: 128GB RAM
        "Standard_E20as_v5",
        "Standard_E32as_v5",
        # E-series v5 AMD with local storage
        "Standard_E2ads_v5",
        "Standard_E4ads_v5",
        "Standard_E8ads_v5",
        "Standard_E16ads_v5",
        # F-series (compute-optimized)
        "Standard_F2s_v2",
        "Standard_F4s_v2",
        "Standard_F8s_v2",
    }

    # Valid Azure regions whitelist
    # All regions supported by azlin VM provisioning
    # Note: COMMON_REGIONS (config_manager.py) must be subset of VALID_REGIONS
    # This constraint is enforced by tests/unit/test_region_consistency.py
    VALID_REGIONS: ClassVar[set[str]] = {
        "eastus",
        "eastus2",
        "westus",
        "westus2",
        "westus3",
        "centralus",
        "northcentralus",
        "southcentralus",
        "westcentralus",  # Issue #421 fix
        "northeurope",
        "westeurope",
        "uksouth",
        "ukwest",
        "francecentral",
        "germanywestcentral",
        "switzerlandnorth",
        "norwayeast",
        "swedencentral",
        "japaneast",
        "japanwest",
        "eastasia",
        "southeastasia",
        "australiaeast",
        "australiasoutheast",
        "brazilsouth",
        "canadacentral",
        "canadaeast",
        "southafricanorth",
        "uaenorth",
        "centralindia",
        "southindia",
        "westindia",
        "koreacentral",
        "koreasouth",
    }

    # Fallback regions to try if SKU unavailable (in order of preference)
    FALLBACK_REGIONS: ClassVar[list[str]] = [
        "westus2",
        "centralus",
        "eastus2",
        "westus",
        "westeurope",
    ]

    def __init__(self, subscription_id: str | None = None):
        """Initialize VM provisioner.

        Args:
            subscription_id: Azure subscription ID (optional)
        """
        self._subscription_id = subscription_id

    def create_vm_config(
        self,
        name: str,
        resource_group: str,
        location: str = "westus2",
        size: str = "Standard_E16as_v5",
        ssh_public_key: str | None = None,
        session_name: str | None = None,
        public_ip_enabled: bool = True,
        home_disk_enabled: bool = True,
        home_disk_size_gb: int = 100,
        home_disk_sku: str = "Standard_LRS",
    ) -> VMConfig:
        """Create VM configuration with validation.

        Args:
            name: VM name
            resource_group: Resource group name
            location: Azure region
            size: VM size
            ssh_public_key: SSH public key content
            session_name: Session name for VM tags (optional)
            public_ip_enabled: Whether to create a public IP (default: True)
            home_disk_enabled: Whether to create separate /home disk (default: True)
            home_disk_size_gb: Size of separate /home disk in GB (default: 100)
            home_disk_sku: Storage SKU for /home disk (default: Standard_LRS)

        Returns:
            VMConfig object

        Raises:
            ValueError: If validation fails
        """
        # Validate VM size (case-insensitive)
        if not self.validate_vm_size(size):
            raise ValueError(
                f"Invalid VM size: {size}. Valid sizes: {', '.join(sorted(self.VALID_VM_SIZES))}"
            )

        # Validate region
        if not self.validate_region(location):
            raise ValueError(f"Invalid region: {location}")

        # Validate home disk size
        if home_disk_enabled:
            if home_disk_size_gb < 1:
                raise ValueError("Home disk size must be at least 1GB")
            if home_disk_size_gb > 32767:  # Azure max: 32TB = 32767GB
                raise ValueError(
                    f"Home disk size {home_disk_size_gb}GB exceeds Azure maximum (32767GB / 32TB)"
                )

        return VMConfig(
            name=name,
            resource_group=resource_group,
            location=location,
            size=size,
            image="Ubuntu2204",
            ssh_public_key=ssh_public_key,
            admin_username="azureuser",
            disable_password_auth=True,
            session_name=session_name,
            public_ip_enabled=public_ip_enabled,
            home_disk_enabled=home_disk_enabled,
            home_disk_size_gb=home_disk_size_gb,
            home_disk_sku=home_disk_sku,
        )

    def validate_vm_size(self, size: str) -> bool:
        """Validate VM size against whitelist (case-insensitive).

        Args:
            size: VM size to validate

        Returns:
            True if valid
        """
        # Azure accepts VM sizes in any case, so validate case-insensitively
        size_upper = size.upper()
        return any(s.upper() == size_upper for s in self.VALID_VM_SIZES)

    def validate_region(self, region: str) -> bool:
        """Validate Azure region against whitelist.

        Args:
            region: Region to validate

        Returns:
            True if valid
        """
        return region.lower() in self.VALID_REGIONS

    @staticmethod
    def validate_azure_vm_name(name: str) -> tuple[bool, str]:
        """Validate name against Azure VM naming rules.

        Azure VM naming requirements:
        - Length: 1-64 characters
        - Allowed: alphanumeric, hyphen (-), period (.)
        - Must start with alphanumeric character
        - Cannot end with hyphen or period

        Args:
            name: Proposed VM name

        Returns:
            Tuple of (is_valid, error_message)
            - (True, "") if valid
            - (False, "reason") if invalid
        """
        # Length check
        if not name:
            return False, "VM name cannot be empty"
        if len(name) > 64:
            return False, f"VM name too long ({len(name)} chars, max 64)"

        # Character check (alphanumeric, hyphen, period only)
        if not re.match(r"^[a-zA-Z0-9.-]+$", name):
            return False, "VM name can only contain alphanumeric characters, hyphens, and periods"

        # Start character check (must be alphanumeric)
        if not name[0].isalnum():
            return False, f"VM name must start with alphanumeric character (not '{name[0]}')"

        # End character check (cannot be hyphen or period)
        if name[-1] in ("-", "."):
            return False, f"VM name cannot end with '{name[-1]}'"

        return True, ""

    @staticmethod
    def check_vm_exists(vm_name: str, resource_group: str) -> bool:
        """Check if VM exists in resource group.

        Args:
            vm_name: VM name to check
            resource_group: Resource group name

        Returns:
            True if VM exists, False otherwise

        Note:
            Returns False if resource group doesn't exist (not an error)
            Uses Azure CLI with minimal output for fast check
        """
        try:
            executor = AzureCLIExecutor(show_progress=False, timeout=10)
            result = executor.execute(
                [
                    "az",
                    "vm",
                    "show",
                    "--name",
                    vm_name,
                    "--resource-group",
                    resource_group,
                    "--query",
                    "name",  # Minimal output for speed
                    "--output",
                    "tsv",
                ]
            )
            # VM exists if command succeeds
            return result["success"]
        except Exception as e:
            # Any error means VM doesn't exist or isn't accessible
            logger.debug(f"VM existence check returned false: {e}")
            return False

    def _parse_sku_error(self, error_message: str) -> bool:
        """Check if error is SKU/capacity related.

        Args:
            error_message: Error message from Azure CLI

        Returns:
            True if error is SKU/capacity related
        """
        sku_error_indicators = [
            "SkuNotAvailable",
            "NotAvailableForSubscription",
            "Capacity Restrictions",
            "requested VM size",
            "currently not available",
        ]
        return any(indicator.lower() in error_message.lower() for indicator in sku_error_indicators)

    def _try_provision_vm(
        self,
        config: VMConfig,
        progress_callback: Callable[[str], None] | None = None,
        has_home_disk: bool = False,
        disk_id: str | None = None,
    ) -> VMDetails:
        """Attempt to provision VM (internal method).

        Args:
            config: VM configuration
            progress_callback: Optional callback for progress updates
            has_home_disk: Whether VM will have separate /home disk attached
            disk_id: Optional disk resource ID to attach during VM creation

        Returns:
            VMDetails with provisioning results

        Raises:
            ProvisioningError: If provisioning fails
        """

        def report_progress(msg: str):
            if progress_callback:
                progress_callback(msg)
            logger.info(msg)

        # Resource group already created in provision_vm()
        # Generate cloud-init with SSH key and disk setup flag
        cloud_init = self._generate_cloud_init(config.ssh_public_key, has_home_disk=has_home_disk)

        # Build VM create command
        cmd = [
            "az",
            "vm",
            "create",
            "--name",
            config.name,
            "--resource-group",
            config.resource_group,
            "--location",
            config.location,
            "--size",
            config.size,
            "--image",
            config.image,
            "--admin-username",
            config.admin_username,
            "--authentication-type",
            "ssh",
            "--generate-ssh-keys" if not config.ssh_public_key else "--ssh-key-values",
        ]

        if config.ssh_public_key:
            cmd.append(config.ssh_public_key)

        cmd.extend(["--custom-data", cloud_init])

        # Conditionally add public IP based on configuration
        if config.public_ip_enabled:
            cmd.extend(["--public-ip-sku", "Standard"])
        else:
            cmd.extend(["--public-ip-address", ""])  # Empty string disables public IP creation

        # CRITICAL: Specify subnet AND vnet-name when using Bastion (avoid AzureBastionSubnet)
        # When a VNet exists with multiple subnets (e.g., from Bastion provisioning),
        # Azure may pick the wrong subnet (AzureBastionSubnet). We must explicitly
        # specify the 'default' subnet for VMs.
        # Azure CLI requires BOTH --subnet and --vnet-name together.
        if not config.public_ip_enabled:
            # Bastion-only VM - ensure it uses correct subnet
            vnet_name = f"azlin-bastion-{config.location}-vnet"
            cmd.extend(["--subnet", "default", "--vnet-name", vnet_name])

        # Attach home disk during VM creation (not after!) so cloud-init can find it
        # CRITICAL: Disk must be present when cloud-init runs disk_setup during boot
        if disk_id:
            cmd.extend(["--attach-data-disks", disk_id])

        cmd.append("--output")
        cmd.append("json")

        # Provision VM
        report_progress(f"Provisioning VM: {config.name}")
        report_progress("This will take 3-5 minutes...")

        executor = AzureCLIExecutor(show_progress=True, timeout=600)
        result = executor.execute(cmd)

        if not result["success"]:
            raise subprocess.CalledProcessError(
                result["returncode"], cmd, result["stdout"], result["stderr"]
            )

        vm_data = json.loads(result["stdout"])

        # Extract VM details
        vm_details = VMDetails(
            name=config.name,
            resource_group=config.resource_group,
            location=config.location,
            size=config.size,
            public_ip=vm_data.get("publicIpAddress"),
            private_ip=vm_data.get("privateIpAddress"),
            state="Running",
            id=vm_data.get("id"),
        )

        # Disk attachment handled in provision_vm() after successful VM creation

        # Set azlin management tags on newly created VM
        report_progress("Setting azlin management tags...")
        try:
            import os

            from azlin.tag_manager import TagManager

            owner = os.getenv("USER") or "unknown"
            TagManager.set_managed_tags(
                vm_name=config.name,
                resource_group=config.resource_group,
                owner=owner,
                session_name=config.session_name,
            )
            report_progress("Management tags set successfully")
        except Exception as e:
            # Tag setting is non-critical, don't fail provisioning
            logger.warning(f"Failed to set management tags: {e}")
            report_progress(f"Warning: Failed to set management tags: {e}")

        report_progress(f"VM provisioned successfully: {vm_details.public_ip}")
        return vm_details

    def create_resource_group(self, resource_group: str, location: str) -> bool:
        """Create Azure resource group if it doesn't exist.

        Args:
            resource_group: Resource group name
            location: Azure region

        Returns:
            True if created or already exists

        Raises:
            ProvisioningError: If creation fails
        """
        try:
            # Check if exists first
            executor = AzureCLIExecutor(show_progress=True, timeout=10)
            result = executor.execute(["az", "group", "exists", "--name", resource_group])

            if result["stdout"].strip().lower() == "true":
                logger.info(f"Resource group {resource_group} already exists")
                return True

            # Create resource group
            logger.info(f"Creating resource group: {resource_group}")
            executor = AzureCLIExecutor(show_progress=True, timeout=30)
            create_result = executor.execute(
                [
                    "az",
                    "group",
                    "create",
                    "--name",
                    resource_group,
                    "--location",
                    location,
                    "--output",
                    "json",
                ]
            )

            if not create_result["success"]:
                raise subprocess.CalledProcessError(
                    create_result["returncode"],
                    ["az", "group", "create"],
                    create_result["stdout"],
                    create_result["stderr"],
                )

            logger.info(f"Resource group {resource_group} created successfully")
            return True

        except subprocess.CalledProcessError as e:
            raise ProvisioningError(f"Failed to create resource group: {e.stderr}") from e

    def _execute_azure_command(self, cmd: list[str], timeout: int = 120) -> dict[str, Any]:
        """Execute Azure CLI command and return structured result.

        Args:
            cmd: Command list (e.g., ["az", "disk", "create", ...])
            timeout: Timeout in seconds

        Returns:
            dict with keys: success, stdout, stderr, returncode
        """
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,  # Don't raise on non-zero exit
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }

    def _create_home_disk(
        self, vm_name: str, resource_group: str, location: str, size_gb: int, sku: str
    ) -> str:
        """Create an Azure Managed Disk for /home directory.

        Args:
            vm_name: Name of the VM (used to name the disk)
            resource_group: Resource group name
            location: Azure region
            size_gb: Disk size in GB
            sku: Storage SKU (Standard_LRS, Premium_LRS, etc.)

        Returns:
            str: Disk resource ID

        Raises:
            subprocess.CalledProcessError: If disk creation fails
        """
        # Make disk name globally unique by including region
        # Azure requires disk names unique per resource group across ALL regions
        safe_location = location.replace(" ", "-").lower()
        disk_name = f"{vm_name}-home-{safe_location}"

        cmd = [
            "az",
            "disk",
            "create",
            "--name",
            disk_name,
            "--resource-group",
            resource_group,
            "--location",
            location,
            "--size-gb",
            str(size_gb),
            "--sku",
            sku,
            "--output",
            "json",
        ]

        logger.info(f"Creating managed disk: {disk_name} ({size_gb}GB, {sku})")

        result = self._execute_azure_command(cmd, timeout=120)

        if not result["success"]:
            raise ProvisioningError(f"Failed to create home disk {disk_name}: {result['stderr']}")

        disk_info = json.loads(result["stdout"])
        disk_id = disk_info["id"]

        logger.info(f"Disk created successfully: {disk_id}")
        return disk_id

    def _attach_home_disk(self, vm_name: str, resource_group: str, disk_id: str) -> str:
        """Attach managed disk to VM.

        Args:
            vm_name: Name of the VM
            resource_group: Resource group name
            disk_id: Disk resource ID

        Returns:
            str: LUN (Logical Unit Number) where disk is attached

        Raises:
            subprocess.CalledProcessError: If disk attach fails
        """
        cmd = [
            "az",
            "vm",
            "disk",
            "attach",
            "--vm-name",
            vm_name,
            "--resource-group",
            resource_group,
            "--disk",
            disk_id,
            "--output",
            "json",
        ]

        logger.info(f"Attaching disk {disk_id} to VM {vm_name}")

        result = self._execute_azure_command(cmd, timeout=60)

        if not result["success"]:
            raise ProvisioningError(
                f"Failed to attach home disk to VM {vm_name}: {result['stderr']}"
            )

        # For first data disk, LUN is always 0
        lun = "0"

        logger.info(f"Disk attached successfully at LUN {lun}")
        return lun

    def _generate_cloud_init(
        self, ssh_public_key: str | None = None, has_home_disk: bool = False
    ) -> str:
        """Generate cloud-init script for tool installation.

        Args:
            ssh_public_key: SSH public key to add to authorized_keys (required to override waagent)
            has_home_disk: Whether to include disk setup for separate /home disk

        Returns:
            Cloud-init YAML content
        """
        # Add SSH key explicitly to cloud-init and disable ssh_authkey_fingerprints module
        # The ssh_authkey_fingerprints module overwrites authorized_keys with empty content
        # from Azure's metadata service. We must disable it to preserve our keys.
        ssh_keys_section = ""
        if ssh_public_key:
            ssh_keys_section = f"""ssh_authorized_keys:
  - {ssh_public_key}

cloud_final_modules:
  - package-update-upgrade-install
  - fan
  - landscape
  - lxd
  - ubuntu-advantage
  - puppet
  - chef
  - ansible
  - mcollective
  - salt-minion
  - reset_rmc
  - refresh_rmc_and_interface
  - rightscale_userdata
  - scripts-vendor
  - scripts-per-once
  - scripts-per-boot
  - scripts-per-instance
  - scripts-user
  - ssh-import-id
  # ssh-authkey-fingerprints is INTENTIONALLY OMITTED to prevent key overwriting
  - keys-to-console
  - install-hotplug
  - phone-home
  - final-message
  - power-state-change

"""

        # Add disk setup sections for separate /home disk
        disk_setup_section = ""
        if has_home_disk:
            disk_setup_section = """
disk_setup:
  /dev/disk/azure/scsi1/lun0:
    table_type: gpt
    layout: true
    overwrite: false

fs_setup:
  - label: home_disk
    filesystem: ext4
    device: /dev/disk/azure/scsi1/lun0-part1
    partition: auto

mounts:
  - [ /dev/disk/azure/scsi1/lun0-part1, /home, ext4, "defaults,nofail", "0", "2" ]

"""

        return f"""#cloud-config
{ssh_keys_section}{disk_setup_section}package_update: true
package_upgrade: true

packages:
  - docker.io
  - git
  - tmux
  - curl
  - wget
  - build-essential
  - software-properties-common
  - ripgrep
  - python3-pip
  - pipx

runcmd:
  # Python 3.13+ from deadsnakes PPA
  - add-apt-repository -y ppa:deadsnakes/ppa

  # GitHub CLI repository setup
  - curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
  - chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
  - echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null

  # OPTIMIZATION: Single apt update for both deadsnakes and GitHub CLI
  - apt update

  # Install Python 3.13 packages
  - apt install -y python3.13 python3.13-venv python3.13-dev python3.13-distutils

  # Install GitHub CLI (separate command for explicit error handling)
  - |
    if apt install -y gh; then
      echo "GitHub CLI (gh) installed successfully"
    else
      echo "WARNING: GitHub CLI (gh) installation failed - check repository setup"
    fi

  - update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.13 1
  - update-alternatives --set python3 /usr/bin/python3.13
  - curl -sS https://bootstrap.pypa.io/get-pip.py | python3.13

  # Azure CLI
  - curl -sL https://aka.ms/InstallAzureCLIDeb | bash

  # astral-uv (uv package manager)
  - snap install astral-uv --classic

  # Node.js (via NodeSource)
  - curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  - apt install -y nodejs

  # npm user-local configuration (avoid sudo for global installs)
  - mkdir -p /home/azureuser/.npm-packages
  - echo 'prefix=${{HOME}}/.npm-packages' > /home/azureuser/.npmrc
  - |
    cat >> /home/azureuser/.bashrc << 'EOF'

    # npm user-local configuration
    NPM_PACKAGES="${{HOME}}/.npm-packages"
    PATH="$NPM_PACKAGES/bin:$PATH"
    MANPATH="$NPM_PACKAGES/share/man:$(manpath 2>/dev/null || echo $MANPATH)"

    # azlin alias for convenient VM management
    alias azlin="uvx --from git+https://github.com/rysweet/azlin azlin"
    EOF
  - chown azureuser:azureuser /home/azureuser/.npmrc /home/azureuser/.npm-packages

  # Tmux configuration for session name display
  - |
    cat > /home/azureuser/.tmux.conf << 'EOF'
    # Display hostname and session name in status bar
    set -g status-left-length 50
    set -g status-left "#[fg=cyan][#h]#[fg=green] #S #[fg=yellow]| "
    set -g status-right "#[fg=cyan]%Y-%m-%d %H:%M"

    # Additional useful settings
    set -g status-interval 60
    set -g status-bg black
    set -g status-fg white
    EOF
  - chown azureuser:azureuser /home/azureuser/.tmux.conf

  # AI CLI tools (optional - can be installed later to speed up provisioning)
  # Uncomment these lines to install AI assistants during VM creation:
  # - su - azureuser -c "npm install -g @github/copilot"
  # - su - azureuser -c "npm install -g @openai/codex"
  # - su - azureuser -c "npm install -g @anthropic-ai/claude-code"

  # Rust
  - su - azureuser -c "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"
  - echo 'source $HOME/.cargo/env' >> /home/azureuser/.bashrc

  # Go
  - wget https://go.dev/dl/go1.21.5.linux-amd64.tar.gz -O /tmp/go.tar.gz
  - tar -C /usr/local -xzf /tmp/go.tar.gz
  - echo 'export PATH=$PATH:/usr/local/go/bin' >> /home/azureuser/.bashrc

  # .NET 10 RC
  - wget https://dot.net/v1/dotnet-install.sh -O /tmp/dotnet-install.sh
  - chmod +x /tmp/dotnet-install.sh
  - /tmp/dotnet-install.sh --channel 10.0 --install-dir /usr/share/dotnet
  - ln -s /usr/share/dotnet/dotnet /usr/local/bin/dotnet

  # Docker post-install
  - usermod -aG docker azureuser
  - systemctl enable docker
  - systemctl start docker

final_message: "azlin VM provisioning complete. All dev tools installed."
"""

    def _create_retry_config(self, original: VMConfig, new_region: str) -> VMConfig:
        """Create new config for retry with different region.

        Does NOT mutate the original config - creates a new instance.
        This is critical for thread safety in pool provisioning.

        Args:
            original: Original VM configuration
            new_region: Region to try

        Returns:
            New VMConfig instance with updated region
        """
        return VMConfig(
            name=original.name,
            resource_group=original.resource_group,
            location=new_region,
            size=original.size,
            image=original.image,
            ssh_public_key=original.ssh_public_key,
            admin_username=original.admin_username,
            disable_password_auth=original.disable_password_auth,
        )

    def provision_vm(
        self, config: VMConfig, progress_callback: Callable[[str], None] | None = None
    ) -> VMDetails:
        """Provision Azure VM with development tools.

        Uses smart retry logic: tries the requested region first, then falls back
        to alternative regions if SKU is unavailable.

        THREAD-SAFE: Does NOT mutate the input config. Each retry creates
        a new config instance, making it safe for concurrent use.

        Args:
            config: VM configuration (will not be modified)
            progress_callback: Optional callback for progress updates

        Returns:
            VMDetails with provisioning results

        Raises:
            ProvisioningError: If provisioning fails in all regions
        """

        def report_progress(msg: str):
            if progress_callback:
                progress_callback(msg)
            logger.info(msg)

        # Create resource group first (needed for disk creation)
        report_progress(f"Creating resource group: {config.resource_group}")
        self.create_resource_group(config.resource_group, config.location)

        # Create separate home disk if enabled
        disk_id = None
        if config.home_disk_enabled:
            report_progress(f"Creating separate /home disk ({config.home_disk_size_gb}GB)...")
            disk_id = self._create_home_disk(
                vm_name=config.name,
                resource_group=config.resource_group,
                location=config.location,
                size_gb=config.home_disk_size_gb,
                sku=config.home_disk_sku,
            )
            report_progress("Home disk created successfully")

        # Build list of regions to try (preferred region first, then fallbacks)
        regions_to_try: list[str] = [config.location]
        regions_to_try.extend(
            region for region in self.FALLBACK_REGIONS if region != config.location
        )

        last_error = None

        # Try each region until one succeeds
        for attempt, region in enumerate(regions_to_try):
            try:
                # Create retry config (immutable approach)
                if attempt > 0:
                    report_progress(
                        f"Retrying in {region} (attempt {attempt + 1}/{len(regions_to_try)})..."
                    )
                    retry_config = self._create_retry_config(config, region)
                else:
                    retry_config = config

                # Attempt provisioning with retry config
                # Pass disk_id to attach during VM creation (before cloud-init runs)
                vm_details = self._try_provision_vm(
                    retry_config,
                    progress_callback,
                    has_home_disk=disk_id is not None,
                    disk_id=disk_id,
                )

                # Disk is attached during VM creation via --attach-data-disks
                # This ensures cloud-init's disk_setup can find the disk during boot
                if disk_id is not None:
                    report_progress("Home disk attached and configured via cloud-init")

                return vm_details

            except subprocess.TimeoutExpired as e:
                raise ProvisioningError("VM provisioning timed out after 10 minutes") from e

            except subprocess.CalledProcessError as e:
                error_msg = e.stderr if e.stderr else str(e)
                last_error = error_msg

                # Error detection order matters:
                # 1. Quota errors: Terminal errors - cannot be resolved by region retry
                # 2. Conflict errors: Terminal errors - resource already exists
                # 3. SKU errors: Recoverable - retry in different region

                # Check for quota errors first (terminal - no retry)
                if QuotaErrorHandler.is_quota_error(error_msg):
                    details = QuotaErrorHandler.parse_quota_error(error_msg, config.size, region)
                    if details:
                        # Clean up any partially created resources before failing
                        logger.warning(
                            f"Quota error detected in {region}. Cleaning up partial resources for {config.name}..."
                        )
                        try:
                            # Try to delete VM if it was partially created
                            from azlin.vm_lifecycle import VMLifecycleManager

                            VMLifecycleManager.delete_vm(config.name, config.resource_group)
                            logger.info(f"Cleaned up partial resources for {config.name}")
                        except Exception as cleanup_error:
                            logger.debug(
                                f"Cleanup attempt completed (some resources may not exist): {cleanup_error}"
                            )

                        formatted_msg = QuotaErrorHandler.format_quota_error(
                            details, self.VALID_VM_SIZES
                        )
                        raise ProvisioningError(formatted_msg) from e

                # Check for resource conflict errors (terminal - no retry)
                if is_resource_conflict(error_msg):
                    conflict_info = parse_conflict_error(
                        error_msg, resource_name=config.name, attempted_location=region
                    )
                    if conflict_info:
                        # Format user-friendly message
                        formatted_msg = format_conflict_error(conflict_info)
                        # Preserve full error details in debug log
                        logger.debug(f"Full Azure conflict error: {error_msg}")
                        raise ProvisioningError(formatted_msg) from e

                # Check if this is a SKU/capacity error (recoverable - retry next region)
                if self._parse_sku_error(error_msg):
                    report_progress(
                        f"SKU {config.size} not available in {region}, trying next region..."
                    )
                    continue  # Try next region
                # Non-SKU error - don't retry
                raise ProvisioningError(f"VM provisioning failed: {error_msg}") from e

            except json.JSONDecodeError as e:
                raise ProvisioningError("Failed to parse VM creation response") from e

        # All regions failed
        raise ProvisioningError(
            f"VM size {config.size} not available in any region. "
            f"Last error: {last_error}. "
            f"Try a different VM size (e.g., Standard_B2s_v2, Standard_D2s_v5)"
        )

    def provision_vm_pool(
        self,
        configs: list[VMConfig],
        progress_callback: Callable[[str], None] | None = None,
        max_workers: int = 10,
    ) -> PoolProvisioningResult:
        """Provision multiple VMs in parallel (thread-safe).

        THREAD-SAFE: Uses thread-safe RG creation and progress reporting.
        Does not mutate input configs.

        Supports partial success - returns detailed results even if some VMs fail.

        Args:
            configs: List of VM configurations (will not be modified)
            progress_callback: Optional callback for progress updates
            max_workers: Maximum parallel workers

        Returns:
            PoolProvisioningResult with success/failure details

        Raises:
            ProvisioningError: Only if ALL provisioning attempts fail
        """
        if not configs:
            return PoolProvisioningResult(
                total_requested=0, successful=[], failed=[], rg_failures=[]
            )

        # Thread-safe progress reporter
        progress = ThreadSafeProgressReporter(progress_callback)

        # Thread-safe RG manager
        rg_manager = ResourceGroupManager()

        # Create resource groups first (thread-safe, deduplicated)
        unique_rgs = {(config.resource_group, config.location) for config in configs}
        rg_failures: list[ResourceGroupFailure] = []

        progress.report(f"Creating {len(unique_rgs)} unique resource group(s)...")
        for rg, location in unique_rgs:
            try:
                rg_manager.ensure_resource_group(rg, location, self)
                progress.report(f"Resource group ready: {rg}")
            except ProvisioningError as e:
                error = ResourceGroupFailure(rg_name=rg, location=location, error=str(e))
                rg_failures.append(error)
                logger.error(f"Resource group creation failed: {rg} - {e}")

        progress.report(
            f"Provisioning {len(configs)} VMs in parallel with {max_workers} workers..."
        )

        successful: list[VMDetails] = []
        failed: list[ProvisioningFailure] = []

        num_workers = min(max_workers, len(configs))

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # Submit all provisioning tasks (pass None for callback - we use thread-safe reporter)
            future_to_config = {
                executor.submit(self.provision_vm, config, None): config for config in configs
            }

            # Collect results as they complete
            for future in as_completed(future_to_config):
                config = future_to_config[future]
                try:
                    vm_details = future.result()
                    successful.append(vm_details)
                    progress.report(f"✓ {config.name} provisioned: {vm_details.public_ip}")

                except subprocess.TimeoutExpired:
                    failure = ProvisioningFailure(
                        config=config,
                        error="Provisioning timed out after 10 minutes",
                        error_type="timeout",
                    )
                    failed.append(failure)
                    progress.report(f"✗ {config.name} failed: timeout")

                except ProvisioningError as e:
                    error_msg = str(e)
                    error_type = (
                        "sku_unavailable" if "not available" in error_msg.lower() else "unknown"
                    )
                    failure = ProvisioningFailure(
                        config=config, error=error_msg, error_type=error_type
                    )
                    failed.append(failure)
                    progress.report(f"✗ {config.name} failed: {error_msg}")

                except Exception as e:
                    failure = ProvisioningFailure(config=config, error=str(e), error_type="unknown")
                    failed.append(failure)
                    progress.report(f"✗ {config.name} failed: {e!s}")

        # Build result
        result = PoolProvisioningResult(
            total_requested=len(configs),
            successful=successful,
            failed=failed,
            rg_failures=rg_failures,
        )

        progress.report(result.get_summary())

        # Only raise if ALL failed
        if not result.any_succeeded:
            error_details = [f.error for f in failed[:3]]  # First 3 errors
            raise ProvisioningError(
                f"All {len(configs)} VM provisioning attempts failed. "
                f"Sample errors: {'; '.join(error_details)}"
            )

        return result


__all__ = [
    "PoolProvisioningResult",
    "ProvisioningError",
    "ProvisioningFailure",
    "ResourceGroupFailure",
    "VMConfig",
    "VMDetails",
    "VMProvisioner",
]
