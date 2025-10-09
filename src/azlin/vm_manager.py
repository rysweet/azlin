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
from typing import List, Optional, Dict, Any
from datetime import datetime

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
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None
    vm_size: Optional[str] = None
    os_type: Optional[str] = None
    provisioning_state: Optional[str] = None
    created_time: Optional[str] = None
    tags: Optional[Dict[str, str]] = None

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
    ) -> List[VMInfo]:
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
            # List VMs with details
            cmd = [
                'az', 'vm', 'list',
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

            vms_data = json.loads(result.stdout)
            vms = []

            for vm_data in vms_data:
                vm_info = cls._parse_vm_data(vm_data)

                # Filter by power state if requested
                if not include_stopped and vm_info.is_stopped():
                    continue

                vms.append(vm_info)

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
    def get_vm(
        cls,
        vm_name: str,
        resource_group: str
    ) -> Optional[VMInfo]:
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
    def list_resource_groups(cls) -> List[str]:
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
    ) -> Optional[str]:
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
        vms: List[VMInfo],
        prefix: str = "azlin"
    ) -> List[VMInfo]:
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
        vms: List[VMInfo],
        reverse: bool = True
    ) -> List[VMInfo]:
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
    def _parse_vm_data(cls, data: Dict[str, Any]) -> VMInfo:
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
        elif 'instanceView' in data:
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
