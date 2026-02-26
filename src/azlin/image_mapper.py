"""OS image mapping for Azure VM provisioning.

This module maps OS identifiers to Azure VM image URNs, supporting shorthand
notation, URN aliases, and full URN passthroughs.

Philosophy:
- Ruthless simplicity: Dict-based O(1) lookup
- Standard library only: No external dependencies
- Self-contained and regeneratable: All mappings defined here

Public API:
    resolve_image: Map OS identifier to Azure URN
    get_default_image: Return default OS URN
    list_supported_os: List all supported OS mappings
"""

from __future__ import annotations

__all__ = ["get_default_image", "list_supported_os", "resolve_image"]

# Canonical OS image mappings (shorthand -> Azure URN)
# Format: publisher:offer:sku:version
_OS_IMAGE_MAP: dict[str, str] = {
    # Ubuntu 25.10 (DEFAULT)
    "25.10": "Canonical:ubuntu-25_10:server:latest",
    "ubuntu2510": "Canonical:ubuntu-25_10:server:latest",
    # Ubuntu 24.10
    "24.10": "Canonical:ubuntu-24_10:server:latest",
    "ubuntu2410": "Canonical:ubuntu-24_10:server:latest",
    # Ubuntu 24.04 LTS
    "24.04": "Canonical:ubuntu-24_04-lts:server:latest",
    "24.04-lts": "Canonical:ubuntu-24_04-lts:server:latest",
    "ubuntu2404": "Canonical:ubuntu-24_04-lts:server:latest",
    # Ubuntu 22.04 LTS
    "22.04": "Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest",
    "22.04-lts": "Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest",
    "ubuntu2204": "Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest",
    # Ubuntu 20.04 LTS
    "20.04": "Canonical:0001-com-ubuntu-server-focal:20_04-lts-gen2:latest",
    "20.04-lts": "Canonical:0001-com-ubuntu-server-focal:20_04-lts-gen2:latest",
    "ubuntu2004": "Canonical:0001-com-ubuntu-server-focal:20_04-lts-gen2:latest",
}

# Default OS image (Ubuntu 25.10)
_DEFAULT_IMAGE = "Canonical:ubuntu-25_10:server:latest"


def get_default_image() -> str:
    """Return the default OS image URN.

    Returns:
        Azure URN for Ubuntu 25.10 (current default)

    Example:
        >>> get_default_image()
        'Canonical:ubuntu-25_10:server:latest'
    """
    return _DEFAULT_IMAGE


def resolve_image(os_identifier: str) -> str:
    """Resolve OS identifier to Azure VM image URN.

    Supports three formats:
    1. Shorthand: "25.10", "24.04-lts", "22.04"
    2. URN alias: "Ubuntu2510", "Ubuntu2404"
    3. Full URN: "Canonical:ubuntu-25_10:server:latest" (passthrough)

    Case-insensitive matching for all formats.

    Args:
        os_identifier: OS identifier in any supported format

    Returns:
        Azure URN string (publisher:offer:sku:version)

    Raises:
        ValueError: If OS identifier is not recognized

    Examples:
        >>> resolve_image("25.10")
        'Canonical:ubuntu-25_10:server:latest'

        >>> resolve_image("Ubuntu2510")
        'Canonical:ubuntu-25_10:server:latest'

        >>> resolve_image("24.04-lts")
        'Canonical:ubuntu-24_04-lts:server:latest'

        >>> resolve_image("Canonical:ubuntu-25_10:server:latest")
        'Canonical:ubuntu-25_10:server:latest'
    """
    # Detect full URN format (contains colons)
    if ":" in os_identifier:
        # Passthrough full URN unchanged
        return os_identifier

    # Normalize to lowercase for case-insensitive lookup
    normalized = os_identifier.lower()

    # Lookup in mapping
    if normalized in _OS_IMAGE_MAP:
        return _OS_IMAGE_MAP[normalized]

    # Not found - build helpful error message
    supported = list_supported_os()
    supported_list = "\n".join(f"  - {key}: {urn}" for key, urn in supported.items())

    raise ValueError(
        f"Unsupported OS identifier: '{os_identifier}'\n\n"
        f"Supported OS options:\n{supported_list}\n\n"
        f"Or provide full Azure URN (e.g., Canonical:ubuntu-25_10:server:latest)"
    )


def list_supported_os() -> dict[str, str]:
    """List all supported OS identifiers and their URNs.

    Returns:
        Dictionary mapping OS identifier to Azure URN

    Example:
        >>> os_map = list_supported_os()
        >>> "25.10" in os_map
        True
        >>> os_map["25.10"]
        'Canonical:ubuntu-25_10:server:latest'
    """
    return _OS_IMAGE_MAP.copy()
