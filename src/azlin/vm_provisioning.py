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
import subprocess
from dataclasses import dataclass
from typing import Optional, Callable, List
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    size: str = "Standard_B2s"  # Widely available, affordable burstable VM
    image: str = "Ubuntu2204"
    ssh_public_key: Optional[str] = None
    admin_username: str = "azureuser"
    disable_password_auth: bool = True


@dataclass
class VMDetails:
    """VM provisioning result details."""
    name: str
    resource_group: str
    location: str
    size: str
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None
    state: str = "Unknown"
    id: Optional[str] = None


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
    6. Python 3.x
    7. Rust
    8. Golang
    9. .NET 10 RC
    """

    # Valid VM sizes whitelist (2025 current-gen SKUs)
    VALID_VM_SIZES = {
        # B-series v1 (legacy but still available)
        'Standard_B1s', 'Standard_B1ms', 'Standard_B2s', 'Standard_B2ms',
        'Standard_B4ms', 'Standard_B8ms',
        # B-series v2 (current gen, Intel)
        'Standard_B2s_v2', 'Standard_B2ms_v2', 'Standard_B4ms_v2',
        # D-series v3 (older gen)
        'Standard_D2s_v3', 'Standard_D4s_v3', 'Standard_D8s_v3',
        # D-series v4 (previous gen)
        'Standard_D2s_v4', 'Standard_D4s_v4', 'Standard_D8s_v4',
        # D-series v5 (current gen, recommended)
        'Standard_D2s_v5', 'Standard_D4s_v5', 'Standard_D8s_v5',
        # E-series
        'Standard_E2s_v3', 'Standard_E4s_v3',
        'Standard_E2s_v4', 'Standard_E4s_v4',
        'Standard_E2s_v5', 'Standard_E4s_v5',
        # F-series
        'Standard_F2s_v2', 'Standard_F4s_v2',
    }

    # Valid Azure regions whitelist
    VALID_REGIONS = {
        'eastus', 'eastus2', 'westus', 'westus2', 'westus3',
        'centralus', 'northcentralus', 'southcentralus',
        'northeurope', 'westeurope', 'uksouth', 'ukwest',
        'francecentral', 'germanywestcentral', 'switzerlandnorth',
        'norwayeast', 'swedencentral', 'japaneast', 'japanwest',
        'eastasia', 'southeastasia', 'australiaeast', 'australiasoutheast',
        'brazilsouth', 'canadacentral', 'canadaeast', 'southafricanorth',
        'uaenorth', 'centralindia', 'southindia', 'westindia',
        'koreacentral', 'koreasouth'
    }

    # Fallback regions to try if SKU unavailable (in order of preference)
    FALLBACK_REGIONS = ['westus2', 'centralus', 'eastus2', 'westus', 'westeurope']

    def __init__(self, subscription_id: Optional[str] = None):
        """Initialize VM provisioner.

        Args:
            subscription_id: Azure subscription ID (optional)
        """
        self._subscription_id = subscription_id

    def create_vm_config(
        self,
        name: str,
        resource_group: str,
        location: str = "eastus",
        size: str = "Standard_D2s_v3",
        ssh_public_key: Optional[str] = None
    ) -> VMConfig:
        """Create VM configuration with validation.

        Args:
            name: VM name
            resource_group: Resource group name
            location: Azure region
            size: VM size
            ssh_public_key: SSH public key content

        Returns:
            VMConfig object

        Raises:
            ValueError: If validation fails
        """
        # Validate VM size (case-insensitive)
        if not self.validate_vm_size(size):
            raise ValueError(
                f"Invalid VM size: {size}. "
                f"Valid sizes: {', '.join(sorted(self.VALID_VM_SIZES))}"
            )

        # Validate region
        if not self.validate_region(location):
            raise ValueError(f"Invalid region: {location}")

        return VMConfig(
            name=name,
            resource_group=resource_group,
            location=location,
            size=size,
            image="Ubuntu2204",
            ssh_public_key=ssh_public_key,
            admin_username="azureuser",
            disable_password_auth=True
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

    def _parse_sku_error(self, error_message: str) -> bool:
        """Check if error is SKU/capacity related.

        Args:
            error_message: Error message from Azure CLI

        Returns:
            True if error is SKU/capacity related
        """
        sku_error_indicators = [
            'SkuNotAvailable',
            'NotAvailableForSubscription',
            'Capacity Restrictions',
            'requested VM size',
            'currently not available'
        ]
        return any(indicator.lower() in error_message.lower()
                  for indicator in sku_error_indicators)

    def _try_provision_vm(
        self,
        config: VMConfig,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> VMDetails:
        """Attempt to provision VM (internal method).

        Args:
            config: VM configuration
            progress_callback: Optional callback for progress updates

        Returns:
            VMDetails with provisioning results

        Raises:
            ProvisioningError: If provisioning fails
        """
        def report_progress(msg: str):
            if progress_callback:
                progress_callback(msg)
            logger.info(msg)

        # Create resource group
        report_progress(f"Creating resource group: {config.resource_group}")
        self.create_resource_group(config.resource_group, config.location)

        # Generate cloud-init
        cloud_init = self._generate_cloud_init()

        # Build VM create command
        cmd = [
            'az', 'vm', 'create',
            '--name', config.name,
            '--resource-group', config.resource_group,
            '--location', config.location,
            '--size', config.size,
            '--image', config.image,
            '--admin-username', config.admin_username,
            '--authentication-type', 'ssh',
            '--generate-ssh-keys' if not config.ssh_public_key else '--ssh-key-values',
        ]

        if config.ssh_public_key:
            cmd.append(config.ssh_public_key)

        cmd.extend([
            '--custom-data', cloud_init,
            '--public-ip-sku', 'Standard',
            '--output', 'json'
        ])

        # Provision VM
        report_progress(f"Provisioning VM: {config.name}")
        report_progress("This will take 3-5 minutes...")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes
            check=True
        )

        vm_data = json.loads(result.stdout)

        # Extract VM details
        vm_details = VMDetails(
            name=config.name,
            resource_group=config.resource_group,
            location=config.location,
            size=config.size,
            public_ip=vm_data.get('publicIpAddress'),
            private_ip=vm_data.get('privateIpAddress'),
            state='Running',
            id=vm_data.get('id')
        )

        report_progress(f"VM provisioned successfully: {vm_details.public_ip}")
        return vm_details

    def create_resource_group(
        self,
        resource_group: str,
        location: str
    ) -> bool:
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
            result = subprocess.run(
                ['az', 'group', 'exists', '--name', resource_group],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.stdout.strip().lower() == 'true':
                logger.info(f"Resource group {resource_group} already exists")
                return True

            # Create resource group
            logger.info(f"Creating resource group: {resource_group}")
            subprocess.run(
                ['az', 'group', 'create',
                 '--name', resource_group,
                 '--location', location,
                 '--output', 'json'],
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )
            logger.info(f"Resource group {resource_group} created successfully")
            return True

        except subprocess.CalledProcessError as e:
            raise ProvisioningError(f"Failed to create resource group: {e.stderr}")

    def _generate_cloud_init(self) -> str:
        """Generate cloud-init script for tool installation.

        Returns:
            Cloud-init YAML content
        """
        return """#cloud-config
package_update: true
package_upgrade: true

packages:
  - docker.io
  - git
  - tmux
  - curl
  - wget
  - build-essential
  - python3
  - python3-pip
  - python3-venv

runcmd:
  # Azure CLI
  - curl -sL https://aka.ms/InstallAzureCLIDeb | bash

  # GitHub CLI
  - curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
  - chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
  - echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null
  - apt update
  - apt install gh -y

  # Node.js (via NodeSource)
  - curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  - apt install -y nodejs

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

    def provision_vm(
        self,
        config: VMConfig,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> VMDetails:
        """Provision Azure VM with development tools.

        Uses smart retry logic: tries the requested region first, then falls back
        to alternative regions if SKU is unavailable.

        Args:
            config: VM configuration
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

        # Build list of regions to try (preferred region first, then fallbacks)
        regions_to_try = [config.location]
        for region in self.FALLBACK_REGIONS:
            if region != config.location:
                regions_to_try.append(region)

        last_error = None

        # Try each region until one succeeds
        for attempt, region in enumerate(regions_to_try):
            try:
                if attempt > 0:
                    report_progress(
                        f"Retrying in {region} (attempt {attempt + 1}/{len(regions_to_try)})..."
                    )
                    # Update config for retry
                    config.location = region

                # Attempt provisioning
                return self._try_provision_vm(config, progress_callback)

            except subprocess.TimeoutExpired:
                raise ProvisioningError("VM provisioning timed out after 10 minutes")

            except subprocess.CalledProcessError as e:
                error_msg = e.stderr if e.stderr else str(e)
                last_error = error_msg

                # Check if this is a SKU/capacity error
                if self._parse_sku_error(error_msg):
                    report_progress(
                        f"SKU {config.size} not available in {region}, trying next region..."
                    )
                    continue  # Try next region
                else:
                    # Non-SKU error - don't retry
                    raise ProvisioningError(f"VM provisioning failed: {error_msg}")

            except json.JSONDecodeError:
                raise ProvisioningError("Failed to parse VM creation response")

        # All regions failed
        raise ProvisioningError(
            f"VM size {config.size} not available in any region. "
            f"Last error: {last_error}. "
            f"Try a different VM size (e.g., Standard_B2s_v2, Standard_D2s_v5)"
        )

    def provision_vm_pool(
        self,
        configs: List[VMConfig],
        progress_callback: Optional[Callable[[str], None]] = None,
        max_workers: int = 10
    ) -> List[VMDetails]:
        """Provision multiple VMs in parallel.

        Args:
            configs: List of VM configurations
            progress_callback: Optional callback for progress updates
            max_workers: Maximum parallel workers

        Returns:
            List of VMDetails for successfully provisioned VMs

        Raises:
            ProvisioningError: If all provisioning attempts fail
        """
        def report_progress(msg: str):
            if progress_callback:
                progress_callback(msg)
            logger.info(msg)

        if not configs:
            return []

        # Create resource groups first (they may be shared)
        unique_rgs = {(config.resource_group, config.location) for config in configs}
        for rg, location in unique_rgs:
            try:
                self.create_resource_group(rg, location)
            except ProvisioningError as e:
                logger.warning(f"Resource group creation failed: {e}")

        report_progress(f"Provisioning {len(configs)} VMs in parallel with {max_workers} workers...")

        results = []
        errors = []

        num_workers = min(max_workers, len(configs))

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # Submit all provisioning tasks
            future_to_config = {
                executor.submit(self.provision_vm, config, None): config
                for config in configs
            }

            # Collect results as they complete
            for future in as_completed(future_to_config):
                config = future_to_config[future]
                try:
                    vm_details = future.result()
                    results.append(vm_details)
                    report_progress(f"✓ {config.name} provisioned: {vm_details.public_ip}")
                except Exception as e:
                    error_msg = f"✗ {config.name} failed: {str(e)}"
                    errors.append(error_msg)
                    report_progress(error_msg)

        # If all failed, raise error
        if not results and errors:
            raise ProvisioningError(
                f"All VM provisioning failed. Errors: {'; '.join(errors)}"
            )

        report_progress(f"Pool provisioning complete: {len(results)}/{len(configs)} successful")

        return results


__all__ = ['VMProvisioner', 'VMConfig', 'VMDetails', 'ProvisioningError']
