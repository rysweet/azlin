# Template System V2 - Technical Specification

**Issue**: #441
**Workstream**: WS7
**Status**: Design Phase
**Philosophy**: Ruthless Simplicity + Zero-BS Implementation

---

## Executive Summary

Enhance azlin's template system with versioning, sharing, composition, validation, and analytics capabilities while maintaining ruthless simplicity.

## Core Principles

1. **Ruthless Simplicity**: Start with simplest implementation that works
2. **Zero-BS**: No stubs, no placeholders - everything must work
3. **Modular Design**: Each feature is a self-contained brick
4. **Backward Compatibility**: Existing templates continue to work

## Current State Analysis

### Existing System
- **Location**: `src/azlin/template_manager.py`
- **Storage**: `~/.azlin/templates/*.yaml`
- **Data Model**: `VMTemplateConfig` with 6 fields
- **Operations**: create, list, delete, export, import
- **CLI**: `azlin template [create|list|delete|export|import]`

### Strengths
- Simple, focused data model
- Clean file-based storage
- Good security (path traversal protection)
- Proper validation

### Gaps
- No versioning or change tracking
- No template composition/inheritance
- No validation beyond basic field checks
- No usage analytics
- No sharing/marketplace capabilities

---

## Feature 1: Template Versioning

### Design Decision
**Metadata-based versioning** (not full git integration)

**Rationale**:
- Simpler than git subprocess calls
- No external git dependency
- Sufficient for user needs
- Maintains single source of truth (YAML file)

### Data Model Extension

```python
@dataclass
class VMTemplateConfig:
    # Existing fields
    name: str
    description: str
    vm_size: str
    region: str
    cloud_init: str | None = None
    custom_metadata: dict[str, Any] = field(default_factory=dict)

    # NEW: Versioning fields
    version: str = "1.0.0"  # Semantic versioning
    created_at: str | None = None  # ISO timestamp
    updated_at: str | None = None  # ISO timestamp
    changelog: list[dict[str, str]] = field(default_factory=list)  # [{version, date, changes}]
    author: str | None = None  # Optional author tracking
```

### Implementation Details

#### Version Tracking
- Semantic versioning: `MAJOR.MINOR.PATCH`
- Auto-increment on update
- Changelog entries include: version, date, changes description

#### Storage Format
```yaml
name: dev-vm
description: Development VM template
version: 1.2.0
created_at: "2025-12-01T10:00:00Z"
updated_at: "2025-12-01T15:30:00Z"
author: user@example.com
vm_size: Standard_B2s
region: eastus
changelog:
  - version: 1.0.0
    date: "2025-12-01T10:00:00Z"
    changes: "Initial version"
  - version: 1.1.0
    date: "2025-12-01T12:00:00Z"
    changes: "Updated VM size to B2s"
  - version: 1.2.0
    date: "2025-12-01T15:30:00Z"
    changes: "Added cloud-init script"
```

#### New CLI Commands
```bash
azlin template version <name>              # Show version history
azlin template update <name> [fields...]   # Update template (auto-increments version)
```

---

## Feature 2: Template Marketplace/Sharing

### Design Decision
**File-based registry** with optional remote sharing

**Rationale**:
- No separate service infrastructure needed
- Uses existing export/import
- Can layer remote registry later if needed
- Aligns with ruthless simplicity

### Implementation Details

#### Registry Structure
```
~/.azlin/templates/
├── local/              # User's templates
│   ├── dev-vm.yaml
│   └── prod-vm.yaml
├── shared/             # Team/community templates
│   ├── azure-basics.yaml
│   └── secure-baseline.yaml
└── registry.yaml       # Metadata index
```

#### Registry Metadata (`registry.yaml`)
```yaml
version: "1.0"
local:
  - name: dev-vm
    version: 1.2.0
    last_updated: "2025-12-01T15:30:00Z"
    usage_count: 15
shared:
  - name: azure-basics
    version: 2.1.0
    author: team@company.com
    last_updated: "2025-11-15T10:00:00Z"
    source: https://github.com/company/azlin-templates/azure-basics.yaml
    usage_count: 142
```

#### New CLI Commands
```bash
azlin template share <name> [--registry <url>]   # Export to shared registry
azlin template browse [--registry <url>]         # List shared templates
azlin template install <name> [--from <url>]     # Install from shared registry
```

---

## Feature 3: Composite Templates (Inheritance)

### Design Decision
**YAML-based template extension** with field override

**Rationale**:
- Familiar pattern (like Docker FROM)
- Pure YAML, no DSL needed
- Simple override semantics
- Easy to understand and debug

### Implementation Details

#### Extension Syntax
```yaml
# base-vm.yaml
name: base-vm
description: Base VM configuration
vm_size: Standard_B1s
region: eastus
cloud_init: |
  #cloud-config
  packages:
    - docker

# dev-vm-extended.yaml
extends: base-vm  # NEW: Extension field
name: dev-vm-extended
description: Development VM (extends base-vm)
vm_size: Standard_B2s  # Override
cloud_init: |
  #cloud-config
  packages:
    - docker
    - nodejs  # Additional packages
```

#### Resolution Rules
1. Load base template
2. Override fields from extending template
3. For `cloud_init`: concatenate or replace (configurable)
4. For `custom_metadata`: deep merge
5. Validate final template against schema

#### Implementation Strategy
```python
class TemplateManager:
    @classmethod
    def resolve_template(cls, name: str) -> VMTemplateConfig:
        """Resolve template with inheritance chain."""
        template = cls.get_template(name)

        if hasattr(template, 'extends') and template.extends:
            base = cls.resolve_template(template.extends)  # Recursive
            return cls.merge_templates(base, template)

        return template

    @classmethod
    def merge_templates(cls, base: VMTemplateConfig, override: VMTemplateConfig) -> VMTemplateConfig:
        """Merge base and override templates."""
        # Simple field override + special handling for cloud_init and metadata
        pass
```

#### New CLI Commands
```bash
azlin template show <name> --resolved    # Show resolved template (after inheritance)
azlin template validate <name>           # Validate template including inheritance chain
```

---

## Feature 4: Validation and Linting

### Design Decision
**JSON Schema + Azure-specific validation**

**Rationale**:
- JSON Schema is industry standard
- Declarative, not imperative
- Easy to extend
- Clear error messages

### Implementation Details

#### Schema Structure
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["name", "description", "vm_size", "region"],
  "properties": {
    "name": {
      "type": "string",
      "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]*$",
      "maxLength": 128
    },
    "vm_size": {
      "type": "string",
      "enum": ["Standard_B1s", "Standard_B2s", "Standard_D2s_v3", ...]
    },
    "region": {
      "type": "string",
      "enum": ["eastus", "westus", "centralus", ...]
    },
    "version": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+\\.\\d+$"
    }
  }
}
```

#### Azure-Specific Validation
```python
class TemplateValidator:
    """Validate templates against schema and Azure constraints."""

    @classmethod
    def validate_vm_size(cls, vm_size: str) -> list[str]:
        """Validate VM size is available in Azure."""
        # Check against known Azure VM sizes
        # Return list of errors (empty if valid)
        pass

    @classmethod
    def validate_region(cls, region: str) -> list[str]:
        """Validate region is a valid Azure region."""
        pass

    @classmethod
    def validate_cloud_init(cls, cloud_init: str | None) -> list[str]:
        """Validate cloud-init script syntax."""
        # Basic YAML validation for cloud-init
        pass

    @classmethod
    def validate_template(cls, template: VMTemplateConfig) -> tuple[bool, list[str]]:
        """Comprehensive template validation.

        Returns:
            (is_valid, error_messages)
        """
        errors = []

        # JSON Schema validation
        errors.extend(cls.validate_against_schema(template))

        # Azure-specific validation
        errors.extend(cls.validate_vm_size(template.vm_size))
        errors.extend(cls.validate_region(template.region))
        errors.extend(cls.validate_cloud_init(template.cloud_init))

        # Inheritance validation
        if hasattr(template, 'extends'):
            errors.extend(cls.validate_inheritance_chain(template))

        return (len(errors) == 0, errors)
```

#### New CLI Commands
```bash
azlin template validate <name>           # Validate template
azlin template lint <name>              # Lint template (validate + style checks)
azlin template validate-all             # Validate all templates in registry
```

---

## Feature 5: Usage Analytics

### Design Decision
**SQLite database** for local analytics storage

**Rationale**:
- No external service dependency
- Fast queries for common operations
- Standard SQL for complex analytics
- Easy backup/export

### Database Schema

```sql
-- Template usage tracking
CREATE TABLE template_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name TEXT NOT NULL,
    template_version TEXT NOT NULL,
    operation TEXT NOT NULL,  -- 'deploy', 'validate', 'export', etc.
    timestamp TEXT NOT NULL,  -- ISO format
    success INTEGER NOT NULL, -- 1 for success, 0 for failure
    error_message TEXT,       -- NULL if success
    vm_name TEXT,             -- Name of VM created (if deploy)
    region TEXT,              -- Region deployed to (if deploy)
    duration_seconds REAL,    -- Operation duration
    user TEXT                 -- Optional user identifier
);

-- Template metadata cache
CREATE TABLE template_metadata (
    name TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    description TEXT,
    last_used TEXT,           -- ISO format
    usage_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    avg_duration_seconds REAL,
    created_at TEXT,
    updated_at TEXT
);

-- Error patterns for diagnostics
CREATE TABLE error_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name TEXT NOT NULL,
    error_category TEXT NOT NULL,  -- 'validation', 'deployment', 'azure_api', etc.
    error_message TEXT NOT NULL,
    occurrence_count INTEGER DEFAULT 1,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
```

### Implementation Details

```python
class TemplateAnalytics:
    """Track and analyze template usage."""

    DB_PATH = Path.home() / ".azlin" / "templates" / "analytics.db"

    @classmethod
    def track_usage(
        cls,
        template_name: str,
        template_version: str,
        operation: str,
        success: bool,
        error_message: str | None = None,
        **kwargs,
    ) -> None:
        """Track template usage event."""
        pass

    @classmethod
    def get_template_stats(cls, template_name: str) -> dict[str, Any]:
        """Get usage statistics for a template."""
        pass

    @classmethod
    def get_most_used_templates(cls, limit: int = 10) -> list[dict[str, Any]]:
        """Get top N most-used templates."""
        pass

    @classmethod
    def get_error_patterns(cls, template_name: str | None = None) -> list[dict[str, Any]]:
        """Get common error patterns for debugging."""
        pass
```

#### New CLI Commands
```bash
azlin template stats <name>              # Show usage statistics for template
azlin template stats --top 10            # Show top 10 most-used templates
azlin template errors <name>             # Show error patterns for template
azlin template analytics export          # Export analytics to CSV/JSON
```

---

## Implementation Plan

### Phase 1: Versioning (Core Infrastructure)
1. Extend `VMTemplateConfig` with version fields
2. Update `TemplateManager.create_template()` to set initial version
3. Add `TemplateManager.update_template()` with auto-increment
4. Update YAML serialization/deserialization
5. Add `azlin template version` command
6. **Tests**: 15+ tests for versioning logic

### Phase 2: Validation (Foundation for Safety)
1. Create `template_schema.json`
2. Implement `TemplateValidator` class
3. Add validation to create/update operations
4. Add `azlin template validate` command
5. **Tests**: 20+ tests for validation scenarios

### Phase 3: Composite Templates (Power Feature)
1. Add `extends` field to `VMTemplateConfig`
2. Implement `TemplateManager.resolve_template()`
3. Implement `TemplateManager.merge_templates()`
4. Update CLI to support `--resolved` flag
5. **Tests**: 12+ tests for inheritance scenarios

### Phase 4: Analytics (Usage Tracking)
1. Create SQLite database and schema
2. Implement `TemplateAnalytics` class
3. Integrate tracking into template operations
4. Add analytics CLI commands
5. **Tests**: 10+ tests for analytics operations

### Phase 5: Marketplace/Sharing (Community Feature)
1. Create registry structure
2. Implement registry metadata management
3. Add `share`, `browse`, `install` commands
4. **Tests**: 8+ tests for sharing operations

---

## Testing Strategy

### Unit Tests (60%)
- Template versioning logic
- Schema validation
- Inheritance resolution
- Analytics calculations
- Path validation
- Name validation

### Integration Tests (30%)
- End-to-end template lifecycle
- Multi-level inheritance
- Database operations
- File I/O operations

### End-to-End Tests (10%)
- CLI command execution
- Template deployment workflows
- Error handling scenarios

**Target**: 75%+ code coverage

---

## Migration Strategy

### Backward Compatibility
1. Existing templates without version fields work as-is
2. First access auto-upgrades to versioned format
3. Old templates assigned version "1.0.0"
4. `created_at` set to file modification time

### Migration Script
```python
def migrate_legacy_templates():
    """Migrate pre-v2 templates to versioned format."""
    for template_file in TEMPLATES_DIR.glob("*.yaml"):
        template = load_template(template_file)
        if 'version' not in template:
            template['version'] = "1.0.0"
            template['created_at'] = get_file_mtime(template_file)
            template['updated_at'] = template['created_at']
            template['changelog'] = [{
                "version": "1.0.0",
                "date": template['created_at'],
                "changes": "Migrated from legacy format"
            }]
            save_template(template_file, template)
```

---

## Success Metrics

### Quantitative
- [ ] 80% of VM deployments use templates
- [ ] <1% template deployment failures
- [ ] Template validation catches 95% of issues
- [ ] 75%+ test coverage
- [ ] All CI checks pass

### Qualitative
- [ ] Users can version templates easily
- [ ] Composite templates reduce duplication
- [ ] Validation catches errors before deployment
- [ ] Analytics provide actionable insights
- [ ] System maintains ruthless simplicity

---

## Security Considerations

### Path Traversal
- Continue existing name validation
- Validate `extends` paths
- Sanitize registry URLs

### Injection Attacks
- Validate cloud-init scripts
- Escape special characters in SQL
- Sanitize user-provided metadata

### Access Control
- File permissions: 0644 for templates
- Database permissions: 0600
- No network operations without explicit user consent

---

## Documentation Requirements

### User Documentation
- [ ] Feature overview
- [ ] Version management guide
- [ ] Template composition guide
- [ ] Validation guide
- [ ] Analytics guide
- [ ] Migration guide

### API Documentation
- [ ] Extended `VMTemplateConfig` dataclass
- [ ] `TemplateValidator` class
- [ ] `TemplateAnalytics` class
- [ ] Updated `TemplateManager` methods

---

## Open Questions / Decisions Deferred

1. **Remote registry protocol**: HTTP/S, git, or custom?
   - **Decision**: Start with file-based, add remote later if needed

2. **Analytics privacy**: Opt-in/opt-out mechanism?
   - **Decision**: Local only, no telemetry, user has full control

3. **Composite template depth limit**: How many levels of inheritance?
   - **Decision**: 5 levels (reasonable limit to prevent circular refs)

4. **Schema validation strictness**: Warn or error on unknown fields?
   - **Decision**: Warn (allows forward compatibility)

---

## Appendix: Module Boundaries

### New Files
```
src/azlin/
├── template_manager.py          # Extended (versioning, composition)
├── template_validator.py        # NEW: Validation logic
├── template_analytics.py        # NEW: Analytics tracking
└── template_schema.json         # NEW: JSON Schema

tests/
├── test_template_manager.py     # Extended
├── test_template_validator.py   # NEW
└── test_template_analytics.py   # NEW
```

### CLI Changes
```
src/azlin/cli.py
└── @template.command() additions:
    ├── version
    ├── update
    ├── validate
    ├── lint
    ├── stats
    ├── errors
    ├── share
    ├── browse
    └── install
```

---

**End of Specification**
