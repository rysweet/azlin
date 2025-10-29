"""Azure VM quota management module.

This module handles fetching and managing Azure VM quota information
for vCPU limits across regions.

Security:
- Input validation
- No shell=True
- Timeout enforcement
- Graceful error handling
"""

import json
import logging
import subprocess
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


class QuotaManagerError(Exception):
    """Raised when quota management operations fail."""

    pass


@dataclass
class QuotaInfo:
    """Azure quota information for a region and resource type."""

    region: str
    quota_name: str
    current_usage: int
    limit: int

    def available(self) -> int:
        """Calculate available quota.

        Returns:
            Number of available units
        """
        return max(0, self.limit - self.current_usage)

    def is_available(self, vcpus: int) -> bool:
        """Check if requested vCPUs are available.

        Args:
            vcpus: Number of vCPUs requested

        Returns:
            True if quota is available
        """
        return self.available() >= vcpus

    def usage_percentage(self) -> float:
        """Calculate usage percentage.

        Returns:
            Usage as percentage (0-100)
        """
        if self.limit == 0:
            return 0.0
        return (self.current_usage / self.limit) * 100


class QuotaManager:
    """Manage Azure VM quotas.

    This class provides operations for:
    - Fetching regional vCPU quotas
    - Parsing quota API responses
    - Caching quota data
    - VM size to vCPU mapping
    """

    # Cache for quota data (5-minute TTL)
    _quota_cache: dict[str, tuple[QuotaInfo | None, float]] = {}
    CACHE_TTL = 300  # 5 minutes

    # VM size to vCPU mapping (hardcoded for common sizes)
    VM_SIZE_VCPUS: dict[str, int] = {
        # B-series (Burstable)
        "Standard_B1s": 1,
        "Standard_B1ms": 1,
        "Standard_B2s": 2,
        "Standard_B2ms": 2,
        "Standard_B4ms": 4,
        "Standard_B8ms": 8,
        # D-series v3
        "Standard_D2s_v3": 2,
        "Standard_D4s_v3": 4,
        "Standard_D8s_v3": 8,
        "Standard_D16s_v3": 16,
        "Standard_D32s_v3": 32,
        # E-series v5 (AMD)
        "Standard_E2as_v5": 2,
        "Standard_E4as_v5": 4,
        "Standard_E8as_v5": 8,
        "Standard_E16as_v5": 16,
        "Standard_E32as_v5": 32,
        "Standard_E48as_v5": 48,
        "Standard_E64as_v5": 64,
        # F-series (Compute optimized)
        "Standard_F2s_v2": 2,
        "Standard_F4s_v2": 4,
        "Standard_F8s_v2": 8,
        "Standard_F16s_v2": 16,
        "Standard_F32s_v2": 32,
    }

    @classmethod
    def get_quota(cls, region: str, quota_name: str, use_cache: bool = True) -> QuotaInfo | None:
        """Get quota information for a specific resource type in a region.

        Args:
            region: Azure region (e.g., "eastus")
            quota_name: Quota name (e.g., "standardDSv3Family")
            use_cache: Whether to use cached data if available

        Returns:
            QuotaInfo object or None if not found

        Raises:
            QuotaManagerError: If quota fetch fails
        """
        if not region:
            raise QuotaManagerError("Region cannot be empty")

        # Check cache if enabled
        cache_key = f"{region}:{quota_name}"
        if use_cache and cache_key in cls._quota_cache:
            cached_quota, cache_time = cls._quota_cache[cache_key]
            if time.time() - cache_time < cls.CACHE_TTL:
                return cached_quota

        # Get all quotas for the region
        all_quotas = cls.get_all_quotas(region)

        # Find the requested quota
        for quota in all_quotas:
            if quota.quota_name == quota_name:
                # Cache the result
                if use_cache:
                    cls._quota_cache[cache_key] = (quota, time.time())
                return quota

        # Quota not found
        if use_cache:
            cls._quota_cache[cache_key] = (None, time.time())
        return None

    @classmethod
    def get_all_quotas(cls, region: str) -> list[QuotaInfo]:
        """Get all quota information for a region.

        Args:
            region: Azure region (e.g., "eastus")

        Returns:
            List of QuotaInfo objects

        Raises:
            QuotaManagerError: If quota fetch fails
        """
        if not region:
            raise QuotaManagerError("Region cannot be empty")

        try:
            # Query Azure CLI for all quotas
            cmd = ["az", "vm", "list-usage", "--location", region, "--output", "json"]

            logger.debug(f"Fetching all quotas for {region}")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)

            # Parse JSON response
            try:
                quotas_data: list[dict[str, Any]] = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                raise QuotaManagerError(f"Failed to parse quota response: {e}") from e

            quotas: list[QuotaInfo] = []

            # Parse all quotas
            for quota_data in quotas_data:
                try:
                    name_info = quota_data.get("name", {})
                    quota_name = name_info.get("value", "")

                    if "limit" not in quota_data or "currentValue" not in quota_data:
                        continue

                    quota_info = QuotaInfo(
                        region=region,
                        quota_name=quota_name,
                        current_usage=quota_data["currentValue"],
                        limit=quota_data["limit"],
                    )

                    quotas.append(quota_info)

                except (KeyError, TypeError) as e:
                    logger.warning(f"Skipping malformed quota entry: {e}")
                    continue

            return quotas

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            raise QuotaManagerError(f"Failed to fetch quotas: {error_msg}") from e
        except subprocess.TimeoutExpired as e:
            raise QuotaManagerError("Quota query timed out after 30 seconds") from e
        except Exception as e:
            raise QuotaManagerError(f"Unexpected error fetching quotas: {e}") from e

    @classmethod
    def get_vm_size_vcpus(cls, vm_size: str) -> int:
        """Get vCPU count for a VM size.

        Args:
            vm_size: Azure VM size (e.g., "Standard_B2s")

        Returns:
            Number of vCPUs for the VM size, or 0 if unknown
        """
        # Try hardcoded mapping first
        if vm_size in cls.VM_SIZE_VCPUS:
            return cls.VM_SIZE_VCPUS[vm_size]

        # Try to extract from size name (e.g., "Standard_D8s_v3" -> 8)
        import re

        match = re.search(r"_([A-Z])(\d+)", vm_size)
        if match:
            try:
                return int(match.group(2))
            except ValueError:
                pass

        # Unknown VM size
        logger.warning(f"Unknown VM size for vCPU mapping: {vm_size}")
        return 0

    @classmethod
    def get_regional_quotas(cls, locations: list[str]) -> dict[str, list[QuotaInfo]]:
        """Get quotas for multiple regions in parallel.

        Args:
            locations: List of Azure regions

        Returns:
            Dictionary mapping region to list of QuotaInfo objects
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        regional_quotas: dict[str, list[QuotaInfo]] = {}

        if not locations:
            return regional_quotas

        # Use ThreadPoolExecutor for parallel fetching
        with ThreadPoolExecutor(max_workers=min(10, len(locations))) as executor:
            # Submit all tasks
            future_to_region = {
                executor.submit(cls.get_all_quotas, region): region for region in locations
            }

            # Collect results as they complete
            for future in as_completed(future_to_region):
                region = future_to_region[future]
                try:
                    quotas = future.result()
                    regional_quotas[region] = quotas
                except Exception as e:
                    logger.error(f"Failed to fetch quotas for {region}: {e}")
                    regional_quotas[region] = []

        return regional_quotas

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the quota cache."""
        cls._quota_cache.clear()
        logger.debug("Quota cache cleared")
