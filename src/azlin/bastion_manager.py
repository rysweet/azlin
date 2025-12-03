"""Compatibility import for bastion_manager.

Tests expect to import from azlin.bastion_manager, but the actual implementation
is in azlin.modules.bastion_manager. This file provides a compatibility layer.
"""

# Re-export everything from the actual module
from azlin.modules.bastion_manager import (
    BastionManager,
    BastionManagerError,
    BastionTunnel,
)

__all__ = ["BastionManager", "BastionManagerError", "BastionTunnel"]
