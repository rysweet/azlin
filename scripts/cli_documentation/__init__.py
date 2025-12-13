"""CLI Documentation Sync System.

Automated documentation generation for azlin CLI commands. This module
extracts metadata from Click commands and generates synchronized markdown
documentation with examples.

Public API ("studs" for external connections):
    - CLIExtractor: Extract metadata from Click commands
    - DocGenerator: Generate markdown from metadata
    - ExampleManager: Load examples from YAML files
    - DocSyncManager: Orchestrate full sync process
    - SyncValidator: Validate generated documentation
    - CLIHasher: Detect command changes via hashing

Data Models:
    - CLIMetadata: Complete command metadata
    - CLIArgument: Positional argument metadata
    - CLIOption: Option/flag metadata
    - CommandExample: Usage example
    - ValidationResult: Validation output
    - SyncResult: Sync operation result
    - ChangeSet: Change detection result

Philosophy:
- Bricks & Studs: Each component self-contained
- Zero-BS: All functionality works, no stubs
- Regeneratable: Can rebuild from specification

Example Usage:
    >>> from scripts.cli_documentation import DocSyncManager
    >>> manager = DocSyncManager()
    >>> results = manager.sync_all()
    >>> print(f"Generated {len(results)} files")
"""

# Core modules
from .example_manager import ExampleManager
from .extractor import CLIExtractor
from .generator import DocGenerator
from .hasher import CLIHasher

# Data models
from .models import (
    ChangeSet,
    CLIArgument,
    CLIMetadata,
    CLIOption,
    CommandExample,
    SyncResult,
    ValidationResult,
)
from .sync_manager import DocSyncManager
from .validator import SyncValidator

# Version
__version__ = "1.0.0"

# Public API (the "studs")
__all__ = [
    "CLIArgument",
    "CLIExtractor",
    "CLIHasher",
    "CLIMetadata",
    "CLIOption",
    "ChangeSet",
    "CommandExample",
    "DocGenerator",
    "DocSyncManager",
    "ExampleManager",
    "SyncResult",
    "SyncValidator",
    "ValidationResult",
]
