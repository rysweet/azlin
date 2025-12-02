"""Template V2 System - Versioning, Marketplace, Composition, Validation, and Analytics.

This module provides a comprehensive template management system for azlin with:
- Versioning: Semantic versioning and change tracking
- Marketplace: Template registry, discovery, and sharing
- Composition: Template inheritance and dependency resolution
- Validation: JSON Schema and Azure-specific validation
- Analytics: SQLite-based usage tracking and reporting

Philosophy:
- Zero-BS Implementation: Every function works or doesn't exist
- Modular Design: Self-contained modules with clear interfaces
- Regeneratable: Can be rebuilt from specifications

Public API:
"""

from azlin.templates.versioning import (
    TemplateVersion,
    TemplateMetadata,
    ChangeRecord,
    ChangeHistory,
    VersionedTemplate,
)

from azlin.templates.marketplace import (
    TemplateRegistry,
)

from azlin.templates.composition import (
    CompositeTemplate,
    TemplateResolver,
)

from azlin.templates.validation import (
    TemplateValidator,
    AzureValidator,
    TemplateLinter,
    ValidationResult,
)

from azlin.templates.analytics import (
    AnalyticsDB,
    AnalyticsTracker,
    AnalyticsReporter,
)

__all__ = [
    # Versioning
    "TemplateVersion",
    "TemplateMetadata",
    "ChangeRecord",
    "ChangeHistory",
    "VersionedTemplate",
    # Marketplace
    "TemplateRegistry",
    # Composition
    "CompositeTemplate",
    "TemplateResolver",
    # Validation
    "TemplateValidator",
    "AzureValidator",
    "TemplateLinter",
    "ValidationResult",
    # Analytics
    "AnalyticsDB",
    "AnalyticsTracker",
    "AnalyticsReporter",
]
