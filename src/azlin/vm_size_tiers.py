"""VM size tier mapping module.

This module provides simplified VM size selection via tiers (s/m/l/xl)
instead of explicit Azure VM size names.

Tiers:
- s (small): Standard_D2s_v3 - 2 vCPU, 8GB RAM (~$70/month) - Original default
- m (medium): Standard_E8as_v5 - 8 vCPU, 64GB RAM (~$363/month) - Good for most dev
- l (large): Standard_E16as_v5 - 16 vCPU, 128GB RAM (~$417/month) - NEW DEFAULT
- xl (extra-large): Standard_E32as_v5 - 32 vCPU, 256GB RAM (~$1,144/month) - Heavy workloads
"""

from typing import ClassVar


class VMSizeTierError(Exception):
    """Raised when VM size tier operations fail."""

    pass


class VMSizeTiers:
    """Map VM size tiers to Azure VM sizes."""

    # Tier definitions with VM specs and approximate monthly costs
    TIER_MAP: ClassVar[dict[str, dict[str, str | int]]] = {
        "s": {
            "size": "Standard_D2s_v3",
            "vcpus": 2,
            "ram_gb": 8,
            "description": "Small - General purpose (2 vCPU, 8GB RAM)",
            "monthly_cost": 70,
            "use_case": "Light development, testing",
        },
        "m": {
            "size": "Standard_E8as_v5",
            "vcpus": 8,
            "ram_gb": 64,
            "description": "Medium - Memory-optimized (8 vCPU, 64GB RAM)",
            "monthly_cost": 363,
            "use_case": "Standard development workloads",
        },
        "l": {
            "size": "Standard_E16as_v5",
            "vcpus": 16,
            "ram_gb": 128,
            "description": "Large - Memory-optimized (16 vCPU, 128GB RAM) [DEFAULT]",
            "monthly_cost": 417,
            "use_case": "Heavy development, large datasets",
        },
        "xl": {
            "size": "Standard_E32as_v5",
            "vcpus": 32,
            "ram_gb": 256,
            "description": "Extra-Large - Memory-optimized (32 vCPU, 256GB RAM)",
            "monthly_cost": 1144,
            "use_case": "Very large datasets, parallel workloads",
        },
    }

    # Default tier
    DEFAULT_TIER = "l"

    @classmethod
    def get_vm_size_from_tier(cls, tier: str) -> str:
        """Get Azure VM size from tier.

        Args:
            tier: Tier name (s, m, l, xl)

        Returns:
            Azure VM size string (e.g., "Standard_E16as_v5")

        Raises:
            VMSizeTierError: If tier is invalid
        """
        tier_lower = tier.lower()
        if tier_lower not in cls.TIER_MAP:
            valid_tiers = ", ".join(sorted(cls.TIER_MAP.keys()))
            raise VMSizeTierError(
                f"Invalid VM size tier: '{tier}'. Valid tiers: {valid_tiers}\n"
                f"Use --size s|m|l|xl or specify exact VM size with --vm-size"
            )

        return str(cls.TIER_MAP[tier_lower]["size"])

    @classmethod
    def get_tier_info(cls, tier: str) -> dict[str, str | int]:
        """Get tier information.

        Args:
            tier: Tier name (s, m, l, xl)

        Returns:
            Dictionary with tier details

        Raises:
            VMSizeTierError: If tier is invalid
        """
        tier_lower = tier.lower()
        if tier_lower not in cls.TIER_MAP:
            raise VMSizeTierError(f"Invalid tier: {tier}")

        return cls.TIER_MAP[tier_lower]

    @classmethod
    def get_default_tier(cls) -> str:
        """Get default tier.

        Returns:
            Default tier name
        """
        return cls.DEFAULT_TIER

    @classmethod
    def get_default_vm_size(cls) -> str:
        """Get default VM size (from default tier).

        Returns:
            Default Azure VM size string
        """
        return cls.get_vm_size_from_tier(cls.DEFAULT_TIER)

    @classmethod
    def list_tiers(cls) -> str:
        """Get formatted list of all tiers.

        Returns:
            Formatted string with all tier information
        """
        lines = ["Available VM Size Tiers:", ""]

        for tier_name in sorted(cls.TIER_MAP.keys()):
            tier_info = cls.TIER_MAP[tier_name]
            default_marker = " [DEFAULT]" if tier_name == cls.DEFAULT_TIER else ""
            lines.append(f"  {tier_name}{default_marker}:")
            lines.append(f"    VM Size: {tier_info['size']}")
            lines.append(f"    Specs: {tier_info['vcpus']} vCPU, {tier_info['ram_gb']}GB RAM")
            lines.append(f"    Cost: ~${tier_info['monthly_cost']}/month")
            lines.append(f"    Use: {tier_info['use_case']}")
            lines.append("")

        lines.append("Usage:")
        lines.append("  azlin new --size m    # Use medium tier")
        lines.append("  azlin new --size xl   # Use extra-large tier")
        lines.append("")
        lines.append("Or specify exact VM size:")
        lines.append("  azlin new --vm-size Standard_E8as_v5")

        return "\n".join(lines)

    @classmethod
    def resolve_vm_size(cls, size_tier: str | None, vm_size: str | None) -> str:
        """Resolve VM size from tier or explicit size.

        Args:
            size_tier: Size tier (s/m/l/xl) - takes precedence
            vm_size: Explicit Azure VM size

        Returns:
            Resolved Azure VM size

        Raises:
            VMSizeTierError: If both are provided or tier is invalid
        """
        # If both provided, error (ambiguous)
        if size_tier and vm_size:
            raise VMSizeTierError(
                "Cannot specify both --size (tier) and --vm-size (explicit). "
                "Use one or the other."
            )

        # If tier provided, resolve to VM size
        if size_tier:
            return cls.get_vm_size_from_tier(size_tier)

        # If explicit VM size provided, use it
        if vm_size:
            return vm_size

        # Neither provided, use default tier
        return cls.get_default_vm_size()


__all__ = ["VMSizeTiers", "VMSizeTierError"]
