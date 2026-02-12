"""Amplihack Profile Management System.

Provides profile-based configuration for commands, agents, skills, and context.
Enables token-efficient sessions by loading only necessary components.

Usage:
    >>> from amplihack.profile_management import ProfileLoader, ComponentDiscovery, ComponentFilter
    >>> loader = ProfileLoader()
    >>> profile = loader.load_profile("minimal")
    >>> discovery = ComponentDiscovery()
    >>> inventory = discovery.discover_all()
    >>> filter = ComponentFilter()
    >>> components = filter.filter(profile, inventory)
"""

from .cli import ProfileCLI
from .cli import main as cli_main
from .config import ConfigManager
from .discovery import ComponentDiscovery, ComponentInventory
from .filter import ComponentFilter
from .index import SkillIndexBuilder
from .loader import ProfileLoader
from .models import (
    ComponentsConfig,
    ComponentSpec,
    MetadataConfig,
    PerformanceConfig,
    ProfileConfig,
    SkillSpec,
)
from .parser import ProfileParser

__all__ = [
    # Discovery & Filtering
    "ComponentDiscovery",
    "ComponentFilter",
    "ComponentInventory",
    "ComponentSpec",
    "ComponentsConfig",
    "ConfigManager",
    "MetadataConfig",
    "PerformanceConfig",
    # CLI & Config
    "ProfileCLI",
    # Models
    "ProfileConfig",
    # Loader & Parser
    "ProfileLoader",
    "ProfileParser",
    # Indexing
    "SkillIndexBuilder",
    "SkillSpec",
    "cli_main",
]

__version__ = "1.0.0"
