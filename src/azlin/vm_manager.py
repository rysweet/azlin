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

    def is_managed(self) -> bool:
        """Check if VM is managed by azlin.

        A VM is considered managed if:
        1. Has managed-by=azlin tag, OR
        2. Name starts with 'azlin' prefix

        Returns:
            True if managed, False otherwise
        """
        if self.tags and self.tags.get("managed-by") == "azlin":
            return True
        return self.name.startswith("azlin")

    def get_status_display(self) -> str:
        """Get formatted status display."""
        if self.is_running():
            return "Running"
        if self.is_stopped():
            return "Stopped"
        return self.power_state.replace("VM ", "")

    def get_display_name(self) -> str:
        """Get display name (session name if set, otherwise VM name)."""
        return self.session_name if self.session_name else self.name

    def has_public_ip(self) -> bool:
        """Check if VM has a public IP address.

        Returns:
            True if VM has public IP, False otherwise
        """
        return self.public_ip is not None and self.public_ip != ""

    def get_resource_id(self, subscription_id: str) -> str:
        """Get full Azure resource ID for VM.

        Args:
            subscription_id: Azure subscription ID

        Returns:
            Full resource ID string
        """
        return (
            f"/subscriptions/{subscription_id}/resourceGroups/{self.resource_group}/"
            f"providers/Microsoft.Compute/virtualMachines/{self.name}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert VMInfo to dictionary for caching.

        Returns:
            Dictionary with all VMInfo fields
        """
        return {
            "name": self.name,
            "resource_group": self.resource_group,
            "location": self.location,
            "power_state": self.power_state,
            "public_ip": self.public_ip,
            "private_ip": self.private_ip,
            "vm_size": self.vm_size,
            "os_type": self.os_type,
            "provisioning_state": self.provisioning_state,
            "created_time": self.created_time,
            "tags": self.tags,
            "session_name": self.session_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VMInfo":
        """Create VMInfo from dictionary.

        Args:
            data: Dictionary with VMInfo fields

        Returns:
            VMInfo object
        """
        return cls(
            name=data["name"],
            resource_group=data["resource_group"],
            location=data["location"],
            power_state=data["power_state"],
            public_ip=data.get("public_ip"),
            private_ip=data.get("private_ip"),
            vm_size=data.get("vm_size"),
            os_type=data.get("os_type"),
            provisioning_state=data.get("provisioning_state"),
            created_time=data.get("created_time"),
            tags=data.get("tags"),
            session_name=data.get("session_name"),
        )

    def get_immutable_data(self) -> dict[str, Any]:
        """Get immutable VM data for caching.

        Immutable data (24h TTL): VM metadata that rarely changes.

        Returns:
            Dictionary with immutable fields
        """
        return {
            "name": self.name,
            "resource_group": self.resource_group,
            "location": self.location,
            "vm_size": self.vm_size,
            "os_type": self.os_type,
            "created_time": self.created_time,
            "tags": self.tags,
        }

    def get_mutable_data(self) -> dict[str, Any]:
        """Get mutable VM data for caching.

        Mutable data (5min TTL): VM state that changes frequently.

        Returns:
            Dictionary with mutable fields
        """
        return {
            "power_state": self.power_state,
            "public_ip": self.public_ip,
            "private_ip": self.private_ip,
            "provisioning_state": self.provisioning_state,
            "session_name": self.session_name,
        }

    @classmethod
    def from_cache_data(
        cls, immutable_data: dict[str, Any], mutable_data: dict[str, Any]
    ) -> "VMInfo":
        """Create VMInfo from cached immutable and mutable data.

        Args:
            immutable_data: Cached immutable VM data
            mutable_data: Cached mutable VM data

        Returns:
            VMInfo object
        """
        return cls(
            name=immutable_data["name"],
            resource_group=immutable_data["resource_group"],
            location=immutable_data["location"],
            vm_size=immutable_data.get("vm_size"),
            os_type=immutable_data.get("os_type"),
            created_time=immutable_data.get("created_time"),
            tags=immutable_data.get("tags"),
            power_state=mutable_data["power_state"],
            public_ip=mutable_data.get("public_ip"),
            private_ip=mutable_data.get("private_ip"),
            provisioning_state=mutable_data.get("provisioning_state"),
            session_name=mutable_data.get("session_name"),
        )


class VMManager:
    """Manage Azure VMs.

    This class provides operations for:
    - Listing VMs in a resource group (with optional caching)
    - Querying VM details
    - Filtering VMs by status
    - Getting VM power state
    - Cache invalidation after VM mutations

    Cache Management:
    - invalidate_cache(): Invalidate single VM cache entry
    - invalidate_resource_group_cache(): Invalidate all VMs in resource group
    """

    @classmethod
    def list_vms(cls, resource_group: str, include_stopped: bool = True) -> list[VMInfo]:
        """List all VMs in a resource group.

        Args:
            resource_group: Resource group name
            include_stopped: Include stopped/deallocated VMs

        Returns:
            List of VMInfo objects

        Raises:
            VMManagerError: If listing fails
        """
        start_time = datetime.now()
        try:
            # List VMs with show-details to get power state in single call
            cmd = [
                "az",
                "vm",
                "list",
                "--resource-group",
                resource_group,
                "--show-details",
                "--output",
                "json",
            ]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, check=True
            )

            # Handle empty stdout (e.g., resource group not found but didn't raise error)
            if not result.stdout or result.stdout.strip() == "":
                logger.debug(f"No VMs found in resource group: {resource_group}")
                return []

            vms_data: list[dict[str, Any]] = json.loads(result.stdout)

            # Fetch all public IPs in a single batch call
            public_ips = cls._get_all_public_ips(resource_group)

            vms: list[VMInfo] = []

            # Parse VM data and match with public IPs
            for vm_data in vms_data:
                try:
                    vm_name = vm_data.get("name")
                    # Match public IP by convention: {vm_name}PublicIP (only if not already present)
                    if not vm_data.get("publicIps"):
                        vm_data["publicIps"] = public_ips.get(f"{vm_name}PublicIP")

                    vm_info = cls._parse_vm_data(vm_data)

                    # Filter by power state if include_stopped is False
                    if not include_stopped and not vm_info.is_running():
                        continue

                    vms.append(vm_info)
                except Exception as e:
                    # Log error but continue with other VMs
                    logger.warning(f"Failed to parse VM {vm_data.get('name', 'unknown')}: {e}")

            elapsed_time = (datetime.now() - start_time).total_seconds()
            logger.debug(
                f"Found {len(vms)} VMs in resource group: {resource_group} "
                f"(include_stopped={include_stopped}, elapsed={elapsed_time:.2f}s)"
            )
            return vms

        except subprocess.CalledProcessError as e:
            # Check if resource group doesn't exist
            if "ResourceGroupNotFound" in e.stderr:
                logger.debug(f"Resource group not found: {resource_group}")
                return []
            raise VMManagerError(f"Failed to list VMs: {e.stderr}") from e
        except json.JSONDecodeError as e:
            raise VMManagerError("Failed to parse VM list response") from e
        except subprocess.TimeoutExpired as e:
            raise VMManagerError("VM list operation timed out") from e

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
                "az",
                "network",
                "public-ip",
                "list",
                "--resource-group",
                resource_group,
                "--query",
                "[].{name:name, ip:ipAddress}",
                "--output",
                "json",
            ]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, check=True
            )

            ips_data: list[dict[str, Any]] = json.loads(result.stdout)
            return {item["name"]: item["ip"] for item in ips_data if item.get("ip")}

        except Exception as e:
            logger.debug(f"Failed to fetch public IPs: {e}")
            return {}

    @classmethod
    def get_vm(cls, vm_name: str, resource_group: str) -> VMInfo | None:
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
                "az",
                "vm",
                "show",
                "--name",
                vm_name,
                "--resource-group",
                resource_group,
                "--show-details",
                "--output",
                "json",
            ]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,  # Increased for WSL compatibility (Issue #580)
            )

            vm_data: dict[str, Any] = json.loads(result.stdout)
            return cls._parse_vm_data(vm_data)

        except subprocess.CalledProcessError as e:
            # Check if VM doesn't exist
            if "ResourceNotFound" in e.stderr:
                logger.debug(f"VM not found: {vm_name}")
                return None
            raise VMManagerError(f"Failed to get VM details: {e.stderr}") from e
        except json.JSONDecodeError as e:
            raise VMManagerError("Failed to parse VM details response") from e
        except subprocess.TimeoutExpired as e:
            raise VMManagerError("VM details query timed out") from e

    @classmethod
    def list_resource_groups(cls) -> list[str]:
        """List all resource groups.

        Returns:
            List of resource group names

        Raises:
            VMManagerError: If listing fails
        """
        try:
            cmd = ["az", "group", "list", "--query", "[].name", "--output", "json"]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, check=True
            )

            return json.loads(result.stdout)

        except subprocess.CalledProcessError as e:
            raise VMManagerError(f"Failed to list resource groups: {e.stderr}") from e
        except json.JSONDecodeError as e:
            raise VMManagerError("Failed to parse resource groups response") from e
        except subprocess.TimeoutExpired as e:
            raise VMManagerError("Resource group list timed out") from e

    @classmethod
    def get_subscription_id(cls) -> str | None:
        """Get current Azure subscription ID.

        Returns:
            Subscription ID or None if not available

        Raises:
            VMManagerError: If query fails
        """
        try:
            cmd = [
                "az",
                "account",
                "show",
                "--query",
                "id",
                "--output",
                "tsv",
            ]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,  # Increased for WSL compatibility (Issue #580)
            )

            subscription_id = result.stdout.strip()
            return subscription_id if subscription_id else None

        except subprocess.CalledProcessError as e:
            logger.debug(f"Failed to get subscription ID: {e.stderr}")
            return None
        except subprocess.TimeoutExpired as e:
            raise VMManagerError("Subscription ID query timed out") from e

    @classmethod
    def get_vm_resource_id(cls, vm_name: str, resource_group: str) -> str | None:
        """Get full Azure resource ID for a VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            Full resource ID string or None if subscription unavailable

        Raises:
            VMManagerError: If query fails
        """
        subscription_id = cls.get_subscription_id()
        if not subscription_id:
            return None

        return (
            f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/"
            f"providers/Microsoft.Compute/virtualMachines/{vm_name}"
        )

    @classmethod
    def get_vm_ip(cls, vm_name: str, resource_group: str) -> str | None:
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
                "az",
                "vm",
                "show",
                "--name",
                vm_name,
                "--resource-group",
                resource_group,
                "--show-details",
                "--query",
                "publicIps",
                "--output",
                "tsv",
            ]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,  # Increased for WSL compatibility (Issue #580)
            )

            ip: str = result.stdout.strip()
            return ip if ip else None

        except subprocess.CalledProcessError as e:
            if "ResourceNotFound" in e.stderr:
                return None
            raise VMManagerError(f"Failed to get VM IP: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise VMManagerError("VM IP query timed out") from e

    @classmethod
    def filter_by_prefix(cls, vms: list[VMInfo], prefix: str = "azlin") -> list[VMInfo]:
        """Filter VMs by name prefix.

        Args:
            vms: List of VMInfo objects
            prefix: Name prefix to filter by

        Returns:
            Filtered list of VMInfo objects
        """
        return [vm for vm in vms if vm.name.startswith(prefix)]

    @classmethod
    def sort_by_created_time(cls, vms: list[VMInfo], reverse: bool = True) -> list[VMInfo]:
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
                    return datetime.fromisoformat(vm.created_time.replace("Z", "+00:00"))
                except Exception as e:
                    logger.debug(f"Could not parse timestamp for {vm.name}: {e}")
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
        vm_name = vm_data["name"]

        # Try to get instance view with a short timeout
        try:
            cmd = [
                "az",
                "vm",
                "get-instance-view",
                "--name",
                vm_name,
                "--resource-group",
                resource_group,
                "--output",
                "json",
            ]

            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,  # Increased for WSL compatibility (Issue #580)
                check=True,
            )

            instance_view: dict[str, Any] = json.loads(result.stdout)

            # Add instance view to VM data
            vm_data["instanceView"] = instance_view

            # Extract power state from instance view
            statuses = instance_view.get("statuses", [])
            for status in statuses:
                if status.get("code", "").startswith("PowerState/"):
                    vm_data["powerState"] = status["displayStatus"]
                    break

        except (
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
            json.JSONDecodeError,
        ) as e:
            logger.debug(f"Could not get instance view for {vm_name}: {e}")
            # Set default power state
            vm_data["powerState"] = "Unknown"

        # Try to get public IP with a short timeout
        try:
            # Get network interface
            network_interfaces = vm_data.get("networkProfile", {}).get("networkInterfaces", [])
            if network_interfaces:
                nic_id = network_interfaces[0]["id"]
                nic_name = nic_id.split("/")[-1]

                cmd = [
                    "az",
                    "network",
                    "nic",
                    "show",
                    "--name",
                    nic_name,
                    "--resource-group",
                    resource_group,
                    "--query",
                    "ipConfigurations[0].publicIPAddress.id",
                    "--output",
                    "tsv",
                ]

                result: subprocess.CompletedProcess[str] = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=True,  # Increased for WSL compatibility (Issue #580)
                )

                public_ip_id: str = result.stdout.strip()
                if public_ip_id and public_ip_id != "None":
                    public_ip_name = public_ip_id.split("/")[-1]

                    # Get public IP address
                    cmd = [
                        "az",
                        "network",
                        "public-ip",
                        "show",
                        "--name",
                        public_ip_name,
                        "--resource-group",
                        resource_group,
                        "--query",
                        "ipAddress",
                        "--output",
                        "tsv",
                    ]

                    result: subprocess.CompletedProcess[str] = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=30,
                        check=True,  # Increased for WSL compatibility (Issue #580)
                    )

                    public_ip: str = result.stdout.strip()
                    if public_ip and public_ip != "None":
                        vm_data["publicIps"] = public_ip

        except (
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
            json.JSONDecodeError,
        ) as e:
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
        if "powerState" in data:
            power_state = data["powerState"]
        elif "instanceView" in data and data["instanceView"] is not None:
            statuses = data["instanceView"].get("statuses", [])
            for status in statuses:
                if status.get("code", "").startswith("PowerState/"):
                    # Add "VM " prefix to match expected format in is_running()/is_stopped()
                    power_state = "VM " + status["code"].replace("PowerState/", "")

        # Parse tags
        tags = data.get("tags", {})

        # Parse created time
        created_time = None
        if "timeCreated" in data:
            created_time = data["timeCreated"]
        elif tags and "created" in tags:
            created_time = tags["created"]

        return VMInfo(
            name=data["name"],
            resource_group=data["resourceGroup"],
            location=data["location"],
            power_state=power_state,
            public_ip=data.get("publicIps"),
            private_ip=data.get("privateIps"),
            vm_size=data.get("hardwareProfile", {}).get("vmSize"),
            os_type=data.get("storageProfile", {}).get("osDisk", {}).get("osType"),
            provisioning_state=data.get("provisioningState"),
            created_time=created_time,
            tags=tags,
        )

    @classmethod
    def list_vms_with_cache(
        cls, resource_group: str, include_stopped: bool = True, use_cache: bool = True
    ) -> tuple[list[VMInfo], bool]:
        """List VMs with optional caching.

        This method implements tiered TTL caching:
        - Immutable data (24h TTL): VM metadata that rarely changes
          Rationale: Location, size, OS type change infrequently (VM recreation required)
        - Mutable data (5min TTL): VM state that changes frequently
          Rationale: Power state, IPs change during normal operations (start/stop/networking)

        Performance targets:
        - Cold start: ~10-15s (baseline)
        - Warm start (full cache): <1s (98% improvement)
        - Partial cache: 3-5s (70% improvement)

        Args:
            resource_group: Resource group name
            include_stopped: Include stopped/deallocated VMs
            use_cache: Enable caching (default: True)

        Returns:
            Tuple of (List of VMInfo objects, was_cached: True if returned from cache)

        Raises:
            VMManagerError: If listing fails
        """
        if not use_cache:
            # Bypass cache - direct API call
            return cls.list_vms(resource_group, include_stopped), False

        from azlin.cache.vm_list_cache import VMListCache

        cache = VMListCache()
        result_vms: list[VMInfo] = []
        vms_to_refresh: list[str] = []  # VM names that need full refresh

        # Step 1: Try to get cached VMs
        cached_entries = cache.get_resource_group_entries(resource_group)

        if cached_entries:
            # Build VMs from cache, identifying what needs refresh
            for entry in cached_entries:
                immutable_expired = entry.is_immutable_expired(cache.immutable_ttl)
                mutable_expired = entry.is_mutable_expired(cache.mutable_ttl)

                if immutable_expired and mutable_expired:
                    # Both layers expired - need full refresh
                    vms_to_refresh.append(entry.vm_name)
                elif immutable_expired:
                    # Only immutable expired - need full refresh to get fresh metadata
                    vms_to_refresh.append(entry.vm_name)
                elif mutable_expired:
                    # Only mutable expired - need state refresh
                    # For now, we'll do full refresh (optimization: could do targeted state query)
                    vms_to_refresh.append(entry.vm_name)
                else:
                    # Both layers fresh - use cached data
                    vm = VMInfo.from_cache_data(entry.immutable_data, entry.mutable_data)
                    result_vms.append(vm)

            # If we have some fresh VMs and nothing needs refresh, use cache
            if result_vms and not vms_to_refresh:
                print(f"[CACHE HIT] Using {len(result_vms)} cached VMs (60min TTL)")
                logger.debug(f"Cache hit: Using {len(result_vms)} cached VMs for {resource_group}")
                if not include_stopped:
                    result_vms = [vm for vm in result_vms if vm.is_running()]
                return result_vms, True  # Cache hit

        # Step 2: Cache miss or partial - fetch fresh data from Azure
        print(
            f"[CACHE MISS] Fetching from Azure (cached: {len(result_vms)}, refresh needed: {len(vms_to_refresh)})"
        )
        logger.debug(
            f"Cache miss or partial: Fetching fresh VM data for {resource_group} "
            f"(cached: {len(result_vms)}, to_refresh: {len(vms_to_refresh)})"
        )

        fresh_vms = cls.list_vms(resource_group, include_stopped=True)

        # Step 3: Update cache with fresh data
        for vm in fresh_vms:
            try:
                cache.set_full(
                    vm_name=vm.name,
                    resource_group=vm.resource_group,
                    immutable_data=vm.get_immutable_data(),
                    mutable_data=vm.get_mutable_data(),
                )
            except Exception as e:
                logger.warning(f"Failed to cache VM {vm.name}: {e}")

        # Step 4: Filter by power state if needed
        if not include_stopped:
            fresh_vms = [vm for vm in fresh_vms if vm.is_running()]

        return fresh_vms, False  # Cache miss/refresh

    @classmethod
    def invalidate_cache(cls, vm_name: str, resource_group: str) -> None:
        """Invalidate cache for a specific VM.

        Call this after VM mutations (create, destroy, start, stop, etc.)

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Example:
            # After creating/destroying/starting/stopping a VM:
            VMManager.invalidate_cache(vm_name="my-vm", resource_group="my-rg")
        """
        try:
            from azlin.cache.vm_list_cache import VMListCache

            cache = VMListCache()
            deleted = cache.delete(vm_name, resource_group)
            if deleted:
                logger.debug(f"Cache invalidated for VM: {vm_name} (RG: {resource_group})")
            else:
                logger.debug(f"No cache entry found for VM: {vm_name} (RG: {resource_group})")
        except Exception as e:
            # Don't let cache errors break VM operations
            logger.warning(f"Failed to invalidate cache for {vm_name}: {e}")

    @classmethod
    def invalidate_resource_group_cache(cls, resource_group: str) -> None:
        """Invalidate all cached VMs in a resource group.

        Call this after operations that affect multiple VMs.

        Args:
            resource_group: Resource group name

        Example:
            # After batch operations:
            VMManager.invalidate_resource_group_cache(resource_group="my-rg")
        """
        try:
            from azlin.cache.vm_list_cache import VMListCache

            cache = VMListCache()
            entries = cache.get_resource_group_entries(resource_group)

            count = 0
            for entry in entries:
                if cache.delete(entry.vm_name, entry.resource_group):
                    count += 1

            logger.debug(f"Cache invalidated for {count} VMs in resource group: {resource_group}")
        except Exception as e:
            # Don't let cache errors break VM operations
            logger.warning(f"Failed to invalidate resource group cache: {e}")


__all__ = ["VMInfo", "VMManager", "VMManagerError"]
