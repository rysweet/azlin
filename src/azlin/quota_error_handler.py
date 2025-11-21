"""Quota error handling for Azure VM provisioning.

This module transforms raw Azure QuotaExceeded errors into clear, actionable
messages with helpful suggestions for alternative VM sizes.

Key features:
- Detects quota errors from Azure CLI output (JSON or plain text)
- Parses quota details (region, limit, usage, requested)
- Formats user-friendly error messages
- Suggests smaller VM sizes as alternatives
- Provides link to Azure quota increase documentation
"""

import json
import re
from dataclasses import dataclass
from typing import ClassVar


@dataclass
class QuotaErrorDetails:
    """Details extracted from a quota exceeded error.

    Attributes:
        vm_family: VM family that hit quota (e.g., "standardEASv5Family")
        region: Azure region where quota was exceeded
        current_usage: Current vCPU usage in that family
        limit: Maximum vCPU quota allowed
        requested: Number of vCPUs requested
        vm_size: The VM size that was requested
    """

    vm_family: str
    region: str
    current_usage: int
    limit: int
    requested: int
    vm_size: str


class QuotaErrorHandler:
    """Handles transformation of quota errors into user-friendly messages."""

    # VM size to vCPU mapping for calculating alternatives
    VM_SIZE_VCPUS: ClassVar[dict[str, int]] = {
        # B-series
        "Standard_B1s": 1,
        "Standard_B1ms": 1,
        "Standard_B2s": 2,
        "Standard_B2ms": 2,
        "Standard_B2s_v2": 2,
        "Standard_B2ms_v2": 2,
        "Standard_B4ms": 4,
        "Standard_B4ms_v2": 4,
        "Standard_B8ms": 8,
        # D-series
        "Standard_D2s_v3": 2,
        "Standard_D2s_v4": 2,
        "Standard_D2s_v5": 2,
        "Standard_D2as_v5": 2,
        "Standard_D4s_v3": 4,
        "Standard_D4s_v4": 4,
        "Standard_D4s_v5": 4,
        "Standard_D4as_v5": 4,
        "Standard_D8s_v3": 8,
        "Standard_D8s_v4": 8,
        "Standard_D8s_v5": 8,
        "Standard_D8as_v5": 8,
        "Standard_D16s_v5": 16,
        "Standard_D16as_v5": 16,
        # E-series
        "Standard_E2s_v3": 2,
        "Standard_E2s_v4": 2,
        "Standard_E2s_v5": 2,
        "Standard_E2as_v5": 2,
        "Standard_E2ads_v5": 2,
        "Standard_E4s_v3": 4,
        "Standard_E4s_v4": 4,
        "Standard_E4s_v5": 4,
        "Standard_E4as_v5": 4,
        "Standard_E4ads_v5": 4,
        "Standard_E8s_v3": 8,
        "Standard_E8s_v4": 8,
        "Standard_E8s_v5": 8,
        "Standard_E8as_v5": 8,
        "Standard_E8ads_v5": 8,
        "Standard_E16s_v5": 16,
        "Standard_E16as_v5": 16,
        "Standard_E16ads_v5": 16,
        "Standard_E20s_v5": 20,
        "Standard_E20as_v5": 20,
        "Standard_E32s_v5": 32,
        "Standard_E32as_v5": 32,
        # F-series
        "Standard_F2s_v2": 2,
        "Standard_F4s_v2": 4,
        "Standard_F8s_v2": 8,
    }

    @staticmethod
    def is_quota_error(error_message: str) -> bool:
        """Detect if an error message indicates a quota issue.

        Args:
            error_message: Error message from Azure CLI

        Returns:
            True if this is a quota exceeded error
        """
        if not error_message:
            return False

        # Check for quota indicators
        quota_indicators = [
            "QuotaExceeded",
            "quota",
            "exceeding approved",
        ]

        error_lower = error_message.lower()
        return any(indicator.lower() in error_lower for indicator in quota_indicators)

    @staticmethod
    def parse_quota_error(
        error_message: str, vm_size: str, location: str
    ) -> QuotaErrorDetails | None:
        """Parse quota error details from Azure error message.

        Supports both JSON-formatted and plain text error messages.

        Args:
            error_message: Raw error message from Azure CLI
            vm_size: VM size that was requested
            location: Region where VM was requested

        Returns:
            QuotaErrorDetails if parsing succeeds, None otherwise
        """
        if not QuotaErrorHandler.is_quota_error(error_message):
            return None

        # Try JSON parsing first
        try:
            error_data = json.loads(error_message)
            if isinstance(error_data, dict) and "error" in error_data:
                return QuotaErrorHandler._parse_json_quota_error(error_data, vm_size, location)
        except (json.JSONDecodeError, KeyError):
            pass

        # Fall back to plain text parsing
        return QuotaErrorHandler._parse_plain_text_quota_error(error_message, vm_size, location)

    @staticmethod
    def _parse_json_quota_error(
        error_data: dict, vm_size: str, location: str
    ) -> QuotaErrorDetails | None:
        """Parse quota error from JSON structure."""
        try:
            error_obj = error_data["error"]

            # Extract VM family from main message
            message = error_obj.get("message", "")
            vm_family_match = re.search(r"(standard\w+Family)", message)
            vm_family = vm_family_match.group(1) if vm_family_match else "Unknown"

            # Extract details from details array
            details = error_obj.get("details", [])
            if details and isinstance(details, list):
                detail = details[0]
                detail_message = detail.get("message", "")

                # Parse numbers from detail message
                usage_match = re.search(r"Current usage:\s*(\d+)", detail_message)
                limit_match = re.search(r"Limit:\s*(\d+)", detail_message)
                requested_match = re.search(r"Requested:\s*(\d+)", detail_message)
                region_match = re.search(r"Region:\s*(\w+)", detail_message)

                current_usage = int(usage_match.group(1)) if usage_match else 0
                limit = int(limit_match.group(1)) if limit_match else 0
                requested = int(requested_match.group(1)) if requested_match else 0
                region = region_match.group(1) if region_match else location

                # Use target if available for more specific VM family
                if "target" in detail:
                    vm_family = detail["target"]

                return QuotaErrorDetails(
                    vm_family=vm_family,
                    region=region,
                    current_usage=current_usage,
                    limit=limit,
                    requested=requested,
                    vm_size=vm_size,
                )

            # No details array - create basic error details
            return QuotaErrorDetails(
                vm_family=vm_family,
                region=location,
                current_usage=0,
                limit=0,
                requested=0,
                vm_size=vm_size,
            )

        except (KeyError, ValueError, AttributeError):
            return None

    @staticmethod
    def _parse_plain_text_quota_error(
        error_message: str, vm_size: str, location: str
    ) -> QuotaErrorDetails | None:
        """Parse quota error from plain text message."""
        try:
            # Extract VM family
            vm_family_match = re.search(r"(standard\w+Family)", error_message)
            vm_family = vm_family_match.group(1) if vm_family_match else "Unknown"

            # Extract numbers
            usage_match = re.search(r"Current[:\s]+(\d+)", error_message, re.IGNORECASE)
            limit_match = re.search(r"Limit[:\s]+(\d+)", error_message, re.IGNORECASE)
            requested_match = re.search(r"Requested[:\s]+(\d+)", error_message, re.IGNORECASE)
            region_match = re.search(r"Region[:\s]+(\w+)", error_message, re.IGNORECASE)

            current_usage = int(usage_match.group(1)) if usage_match else 0
            limit = int(limit_match.group(1)) if limit_match else 0
            requested = int(requested_match.group(1)) if requested_match else 0
            region = region_match.group(1) if region_match else location

            return QuotaErrorDetails(
                vm_family=vm_family,
                region=region,
                current_usage=current_usage,
                limit=limit,
                requested=requested,
                vm_size=vm_size,
            )

        except (ValueError, AttributeError):
            return None

    @staticmethod
    def format_quota_error(details: QuotaErrorDetails, valid_sizes: set[str]) -> str:
        """Format a user-friendly quota error message.

        Args:
            details: Parsed quota error details
            valid_sizes: Set of valid VM sizes for suggestions

        Returns:
            Formatted error message with actionable suggestions
        """
        # Build the main error message
        if details.limit > 0 and details.current_usage > 0:
            message = (
                f"Insufficient vCPU quota in {details.region} for {details.vm_size}.\n"
                f"\n"
                f"Current usage: {details.current_usage} vCPUs\n"
                f"Quota limit: {details.limit} vCPUs\n"
                f"Requested: {details.requested} vCPUs\n"
                f"Available: {details.limit - details.current_usage} vCPUs\n"
            )
        else:
            message = (
                f"Insufficient vCPU quota in {details.region} for {details.vm_size}.\n"
                f"The requested VM size exceeds your current quota limit.\n"
            )

        # Add suggestions for smaller sizes
        alternatives = QuotaErrorHandler.suggest_alternatives(details, valid_sizes)
        if alternatives:
            message += "\nTry a smaller VM size:\n"
            for vm_size, vcpus, tier in alternatives[:3]:  # Show top 3 alternatives
                message += f"  - {vm_size} ({vcpus} vCPUs)\n"

        # Add quota increase information
        message += "\nTo request a quota increase, visit:\nhttps://aka.ms/azquotaincrease"

        return message

    @staticmethod
    def suggest_alternatives(
        details: QuotaErrorDetails, valid_sizes: set[str]
    ) -> list[tuple[str, int, str]]:
        """Suggest smaller VM sizes as alternatives.

        Args:
            details: Quota error details
            valid_sizes: Set of valid VM sizes

        Returns:
            List of tuples (vm_size, vcpus, tier) sorted by suitability
            Only includes sizes smaller than the requested size
        """
        requested_vcpus = QuotaErrorHandler.VM_SIZE_VCPUS.get(details.vm_size, 0)
        if requested_vcpus == 0:
            return []

        # Find sizes in the same family that are smaller
        vm_family_base = details.vm_size.split("_")[0:2]  # e.g., ["Standard", "E16as"]
        vm_series = vm_family_base[1][0] if len(vm_family_base) > 1 else ""  # "E", "D", etc.

        alternatives = []
        for size in valid_sizes:
            if size not in QuotaErrorHandler.VM_SIZE_VCPUS:
                continue

            vcpus = QuotaErrorHandler.VM_SIZE_VCPUS[size]

            # Only suggest smaller sizes
            if vcpus >= requested_vcpus:
                continue

            # Prefer same series (E, D, etc.)
            size_series = size.split("_")[1][0] if "_" in size else ""
            is_same_series = size_series == vm_series

            # Calculate suitability score (prefer larger sizes within constraint)
            # and prefer same series
            score = vcpus + (10 if is_same_series else 0)

            alternatives.append((size, vcpus, "same-series" if is_same_series else "other"))

        # Sort by score (descending) - larger sizes first, same series preferred
        alternatives.sort(key=lambda x: x[1] + (100 if x[2] == "same-series" else 0), reverse=True)

        return alternatives
