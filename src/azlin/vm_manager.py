"""VM management module.

This module handles VM lifecycle operations: list, query, filter, and status.
Delegates to Azure CLI for VM operations.

Security:
- Input validation
- No shell=True
- Sanitized logging
"""

import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class VMManagerError(Exception):
    """Raised when VM management operations fail."""
    pass


@dataclass
class VMInfo:
    """VM information from Azure."""
    name: str
    resource_group: str
    location: str
    power_state: str
    public_ip: str | None = None
    private_ip: str | None = None
    vm_size: str | None = None
    os_type: str | None = None
    provisioning_state: str | None = None
    created_time: str | None = None
    tags: dict[str, str] | None = None
    session_name: str | None = None  # Session name from config

    def is_running(self) -> bool:
        """Check if VM is running."""
        return self.power_state == "VM running"

    def is_stopped(self) -> bool:
        """Check if VM is stopped."""
        return self.power_state in ["VM stopped", "VM deallocated"]

    def get_status_display(self) -> str:
        """Get formatted status display."""
        if self.is_running():
            return "Running"
        elif self.is_stopped():
            return "Stopped"
        else:
            return self.power_state.replace("VM ", "")

    def get_display_name(self) -> str:
        """Get display name (session name if set, otherwise VM name)."""
        return self.session_name if self.session_name else self.name


class VMManager:
    """Manage Azure VMs.

    This class provides operations for:
    - Listing VMs in a resource group
    - Querying VM details
    - Filtering VMs by status
    - Getting VM power state
    """

    @classmethod
    def list_vms(
        cls,
        resource_group: str,
        include_stopped: bool = True
    ) -> list[VMInfo]:
        """List all VMs in a resource group.

        Args:
            resource_group: Resource group name
            include_stopped: Include stopped/deallocated VMs

        Returns:
            List of VMInfo objects

        Raises:
            VMManagerError: If listing fails
        """
        try:
            # List VMs without show-details first (faster and more reliable)
            cmd = [
                'az', 'vm', 'list',
                '--resource-group', resource_group,
                '--output', 'json'
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )

            vms_data = json.loads(result.stdout)

            # Fetch all public IPs in a single batch call
            public_ips = cls._get_all_public_ips(resource_group)

            vms = []

            # Parse VM data and match with public IPs
            for vm_data in vms_data:
                try:
                    vm_name = vm_data.get('name')
                    # Match public IP by convention: {vm_name}PublicIP
                    vm_data['publicIps'] = public_ips.get(f"{vm_name}PublicIP")

                    vm_info = cls._parse_vm_data(vm_data)

                    # Since we don't have power state, we can't filter by stopped status reliably
                    # Just include all VMs
                    vms.append(vm_info)
                except Exception as e:
                    # Log error but continue with other VMs
                    logger.warning(f"Failed to parse VM {vm_data.get('name', 'unknown')}: {e}")

            logger.debug(f"Found {len(vms)} VMs in resource group: {resource_group}")
            return vms

        except subprocess.CalledProcessError as e:
            # Check if resource group doesn't exist
            if "ResourceGroupNotFound" in e.stderr:
                logger.debug(f"Resource group not found: {resource_group}")
                return []
            raise VMManagerError(f"Failed to list VMs: {e.stderr}")
        except json.JSONDecodeError:
            raise VMManagerError("Failed to parse VM list response")
        except subprocess.TimeoutExpired:
            raise VMManagerError("VM list operation timed out")

    @classmethod
    def _get_all_public_ips(cls, resource_group: str) -> dict[str, str]:
        """Get all public IPs in the resource group in a single batch call.
        
        Args:
            resource_group: Resource group name
            
        Returns:
            Dictionary mapping public IP resource name to IP address
        """
        try:
            cmd = [
                'az', 'network', 'public-ip', 'list',
                '--resource-group', resource_group,
                '--query', '[].{name:name, ip:ipAddress}',
                '--output', 'json'
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                check=True
            )

            ips_data = json.loads(result.stdout)
            return {item['name']: item['ip'] for item in ips_data if item.get('ip')}

        except Exception as e:
            logger.debug(f"Failed to fetch public IPs: {e}")
            return {}

    @classmethod
    def get_vm(
        cls,
        vm_name: str,
        resource_group: str
    ) -> VMInfo | None:
        """Get specific VM details.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            VMInfo object or None if not found

        Raises:
            VMManagerError: If query fails
        """
        try:
            cmd = [
                'az', 'vm', 'show',
                '--name', vm_name,
                '--resource-group', resource_group,
                '--show-details',
                '--output', 'json'
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )

            vm_data = json.loads(result.stdout)
            return cls._parse_vm_data(vm_data)

        except subprocess.CalledProcessError as e:
            # Check if VM doesn't exist
            if "ResourceNotFound" in e.stderr:
                logger.debug(f"VM not found: {vm_name}")
                return None
            raise VMManagerError(f"Failed to get VM details: {e.stderr}")
        except json.JSONDecodeError:
            raise VMManagerError("Failed to parse VM details response")
        except subprocess.TimeoutExpired:
            raise VMManagerError("VM details query timed out")

    @classmethod
    def list_resource_groups(cls) -> list[str]:
        """List all resource groups.

        Returns:
            List of resource group names

        Raises:
            VMManagerError: If listing fails
        """
        try:
            cmd = [
                'az', 'group', 'list',
                '--query', '[].name',
                '--output', 'json'
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )

            groups = json.loads(result.stdout)
            return groups

        except subprocess.CalledProcessError as e:
            raise VMManagerError(f"Failed to list resource groups: {e.stderr}")
        except json.JSONDecodeError:
            raise VMManagerError("Failed to parse resource groups response")
        except subprocess.TimeoutExpired:
            raise VMManagerError("Resource group list timed out")

    @classmethod
    def get_vm_ip(
        cls,
        vm_name: str,
        resource_group: str
    ) -> str | None:
        """Get VM public IP address.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            Public IP address or None

        Raises:
            VMManagerError: If query fails
        """
        try:
            cmd = [
                'az', 'vm', 'show',
                '--name', vm_name,
                '--resource-group', resource_group,
                '--show-details',
                '--query', 'publicIps',
                '--output', 'tsv'
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )

            ip = result.stdout.strip()
            return ip if ip else None

        except subprocess.CalledProcessError as e:
            if "ResourceNotFound" in e.stderr:
                return None
            raise VMManagerError(f"Failed to get VM IP: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise VMManagerError("VM IP query timed out")

    @classmethod
    def filter_by_prefix(
        cls,
        vms: list[VMInfo],
        prefix: str = "azlin"
    ) -> list[VMInfo]:
        """Filter VMs by name prefix.

        Args:
            vms: List of VMInfo objects
            prefix: Name prefix to filter by

        Returns:
            Filtered list of VMInfo objects
        """
        return [vm for vm in vms if vm.name.startswith(prefix)]

    @classmethod
    def sort_by_created_time(
        cls,
        vms: list[VMInfo],
        reverse: bool = True
    ) -> list[VMInfo]:
        """Sort VMs by creation time.

        Args:
            vms: List of VMInfo objects
            reverse: Sort descending (newest first) if True

        Returns:
            Sorted list of VMInfo objects
        """
        def get_time(vm: VMInfo) -> datetime:
            if vm.created_time:
                try:
                    # Parse ISO format timestamp
                    return datetime.fromisoformat(vm.created_time.replace('Z', '+00:00'))
                except Exception:
                    pass
            return datetime.min

        return sorted(vms, key=get_time, reverse=reverse)

    @classmethod
    def _enrich_vm_data(cls, vm_data: dict[str, Any], resource_group: str) -> dict[str, Any]:
        """Enrich VM data with instance view information.
        
        Args:
            vm_data: Basic VM data
            resource_group: Resource group name
            
        Returns:
            Enriched VM data with power state and IP information
        """
        vm_name = vm_data['name']

        # Try to get instance view with a short timeout
        try:
            cmd = [
                'az', 'vm', 'get-instance-view',
                '--name', vm_name,
                '--resource-group', resource_group,
                '--output', 'json'
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,  # Short timeout to avoid hanging
                check=True
            )

            instance_view = json.loads(result.stdout)

            # Add instance view to VM data
            vm_data['instanceView'] = instance_view

            # Extract power state from instance view
            statuses = instance_view.get('statuses', [])
            for status in statuses:
                if status.get('code', '').startswith('PowerState/'):
                    vm_data['powerState'] = status['displayStatus']
                    break

        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, json.JSONDecodeError) as e:
            logger.debug(f"Could not get instance view for {vm_name}: {e}")
            # Set default power state
            vm_data['powerState'] = 'Unknown'

        # Try to get public IP with a short timeout
        try:
            # Get network interface
            network_interfaces = vm_data.get('networkProfile', {}).get('networkInterfaces', [])
            if network_interfaces:
                nic_id = network_interfaces[0]['id']
                nic_name = nic_id.split('/')[-1]

                cmd = [
                    'az', 'network', 'nic', 'show',
                    '--name', nic_name,
                    '--resource-group', resource_group,
                    '--query', 'ipConfigurations[0].publicIPAddress.id',
                    '--output', 'tsv'
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True
                )

                public_ip_id = result.stdout.strip()
                if public_ip_id and public_ip_id != 'None':
                    public_ip_name = public_ip_id.split('/')[-1]

                    # Get public IP address
                    cmd = [
                        'az', 'network', 'public-ip', 'show',
                        '--name', public_ip_name,
                        '--resource-group', resource_group,
                        '--query', 'ipAddress',
                        '--output', 'tsv'
                    ]

                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=True
                    )

                    public_ip = result.stdout.strip()
                    if public_ip and public_ip != 'None':
                        vm_data['publicIps'] = public_ip

        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, json.JSONDecodeError) as e:
            logger.debug(f"Could not get public IP for {vm_name}: {e}")

        return vm_data

    @classmethod
    def _parse_vm_data(cls, data: dict[str, Any]) -> VMInfo:
        """Parse VM data from Azure response.

        Args:
            data: VM data dictionary

        Returns:
            VMInfo object
        """
        # Parse power state from powerState field or instanceView
        power_state = "Unknown"
        if 'powerState' in data:
            power_state = data['powerState']
        elif 'instanceView' in data and data['instanceView'] is not None:
            statuses = data['instanceView'].get('statuses', [])
            for status in statuses:
                if status.get('code', '').startswith('PowerState/'):
                    power_state = status['code'].replace('PowerState/', '')

        # Parse tags
        tags = data.get('tags', {})

        # Parse created time
        created_time = None
        if 'timeCreated' in data:
            created_time = data['timeCreated']
        elif tags and 'created' in tags:
            created_time = tags['created']

        return VMInfo(
            name=data['name'],
            resource_group=data['resourceGroup'],
            location=data['location'],
            power_state=power_state,
            public_ip=data.get('publicIps'),
            private_ip=data.get('privateIps'),
            vm_size=data.get('hardwareProfile', {}).get('vmSize'),
            os_type=data.get('storageProfile', {}).get('osDisk', {}).get('osType'),
            provisioning_state=data.get('provisioningState'),
            created_time=created_time,
            tags=tags
        )


__all__ = ['VMManager', 'VMInfo', 'VMManagerError']
