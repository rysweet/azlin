# Template System V2

Advanced template management with versioning, sharing, composition, validation, and analytics.

## Overview

The Template System V2 extends azlin's basic template functionality with enterprise-grade features:

- **Versioning**: Track changes and maintain template history
- **Composition**: Build templates from base templates (inheritance)
- **Validation**: Catch errors before deployment with JSON Schema
- **Analytics**: Track usage patterns and success rates
- **Sharing**: Share templates with teams via registries

## Quick Start

### Creating a Versioned Template

```bash
# Create a base template
azlin template create base-vm \
  --description "Standard base VM configuration" \
  --vm-size Standard_B2s \
  --region eastus \
  --cloud-init base-init.yaml

# View version information
azlin template version base-vm
```

**Output**:
```
Template: base-vm
Version: 1.0.0
Created: 2025-12-01 10:00:00
Last Updated: 2025-12-01 10:00:00
Author: user@example.com

Changelog:
  v1.0.0 (2025-12-01 10:00:00)
    - Initial version
```

### Updating a Template

```bash
# Update template (auto-increments version)
azlin template update base-vm \
  --vm-size Standard_B2ms \
  --changes "Increased VM size for better performance"

# Check new version
azlin template version base-vm
```

**Output**:
```
Template: base-vm
Version: 1.1.0
Created: 2025-12-01 10:00:00
Last Updated: 2025-12-01 11:30:00
Author: user@example.com

Changelog:
  v1.1.0 (2025-12-01 11:30:00)
    - Increased VM size for better performance
  v1.0.0 (2025-12-01 10:00:00)
    - Initial version
```

## Template Composition (Inheritance)

### Creating a Base Template

```bash
# Create base template
azlin template create base-secure \
  --description "Security-hardened base configuration" \
  --vm-size Standard_B1s \
  --region eastus \
  --cloud-init secure-base.yaml
```

**secure-base.yaml**:
```yaml
#cloud-config
packages:
  - fail2ban
  - ufw
  - unattended-upgrades

runcmd:
  - ufw default deny incoming
  - ufw default allow outgoing
  - ufw allow ssh
  - ufw enable
```

### Extending the Base Template

Create `dev-vm.yaml`:
```yaml
extends: base-secure
name: dev-vm-extended
description: Development VM extending security baseline
vm_size: Standard_B2s
cloud_init: |
  #cloud-config
  packages:
    - fail2ban
    - ufw
    - unattended-upgrades
    - nodejs
    - docker.io

  runcmd:
    - ufw default deny incoming
    - ufw default allow outgoing
    - ufw allow ssh
    - ufw allow 3000/tcp
    - ufw enable
    - usermod -aG docker azureuser
```

**Import the extended template**:
```bash
azlin template import dev-vm.yaml
```

### Viewing Resolved Templates

```bash
# Show template with inheritance resolved
azlin template show dev-vm-extended --resolved
```

**Output**:
```yaml
name: dev-vm-extended
description: Development VM extending security baseline
version: 1.0.0
vm_size: Standard_B2s
region: eastus
extends: base-secure
cloud_init: |
  #cloud-config
  packages:
    - fail2ban
    - ufw
    - unattended-upgrades
    - nodejs
    - docker.io
  runcmd:
    - ufw default deny incoming
    - ufw default allow outgoing
    - ufw allow ssh
    - ufw allow 3000/tcp
    - ufw enable
    - usermod -aG docker azureuser
```

## Validation and Linting

### Validating Templates

```bash
# Validate a single template
azlin template validate dev-vm-extended
```

**Output** (success):
```
✓ Template 'dev-vm-extended' is valid
  - Schema validation: PASS
  - VM size check: PASS (Standard_B2s available)
  - Region check: PASS (eastus available)
  - Cloud-init syntax: PASS
  - Inheritance chain: PASS (base-secure found)
```

**Output** (with errors):
```
✗ Template 'broken-vm' has validation errors:
  1. Invalid VM size: 'Standard_INVALID' (line 4)
     Available sizes: Standard_B1s, Standard_B2s, Standard_D2s_v3, ...
  2. Invalid region: 'invalid-region' (line 5)
     Available regions: eastus, westus, centralus, ...
  3. Cloud-init syntax error: Expected mapping at line 12
```

### Linting Templates

```bash
# Lint template (validation + style checks)
azlin template lint dev-vm-extended
```

**Output**:
```
✓ Template 'dev-vm-extended' lint results:
  Validation: PASS
  Style checks:
    ✓ Description is clear and descriptive
    ✓ Cloud-init follows best practices
    ⚠ Warning: VM size may be oversized for dev workloads
    ℹ Info: Consider adding tags in custom_metadata
```

### Validating All Templates

```bash
# Validate entire template registry
azlin template validate-all
```

**Output**:
```
Validating 15 templates...
✓ base-vm (v1.1.0): Valid
✓ base-secure (v1.0.0): Valid
✓ dev-vm-extended (v1.0.0): Valid
✓ prod-vm (v2.3.1): Valid
✗ legacy-vm (v1.0.0): 2 errors
  - Invalid VM size: Standard_A1
  - Missing required field: region

Summary: 14/15 templates valid (93%)
```

## Usage Analytics

### Viewing Template Statistics

```bash
# Get statistics for a specific template
azlin template stats dev-vm-extended
```

**Output**:
```
Template: dev-vm-extended
Version: 1.0.0

Usage Summary:
  Total Deployments: 47
  Successful: 45 (96%)
  Failed: 2 (4%)
  Last Used: 2025-12-01 14:23:15

Performance:
  Avg Deployment Time: 3.2 minutes
  Fastest: 2.1 minutes
  Slowest: 5.7 minutes

Popular Regions:
  1. eastus: 25 deployments (53%)
  2. westus: 15 deployments (32%)
  3. centralus: 7 deployments (15%)

Recent Errors:
  1. Quota exceeded (2 occurrences)
     Last seen: 2025-11-30 16:45:00
  2. Network timeout (1 occurrence)
     Last seen: 2025-11-28 09:12:00
```

### Top Templates

```bash
# Show most-used templates
azlin template stats --top 10
```

**Output**:
```
Top 10 Most-Used Templates:
1. prod-vm (v2.3.1)          - 342 deployments (98% success)
2. dev-vm-extended (v1.0.0)  - 47 deployments (96% success)
3. base-secure (v1.0.0)      - 38 deployments (100% success)
4. test-vm (v1.5.0)          - 29 deployments (93% success)
5. staging-vm (v2.0.0)       - 24 deployments (96% success)
...
```

### Error Pattern Analysis

```bash
# Analyze errors for a specific template
azlin template errors dev-vm-extended
```

**Output**:
```
Error Patterns for 'dev-vm-extended':

1. Quota Exceeded (2 occurrences, 4% of failures)
   Category: azure_api
   First Seen: 2025-11-25 10:30:00
   Last Seen: 2025-11-30 16:45:00
   Message: Quota 'StandardBSFamily' exceeded for region 'eastus'
   Recommendation: Use a different region or request quota increase

2. Network Timeout (1 occurrence, 2% of failures)
   Category: deployment
   First Seen: 2025-11-28 09:12:00
   Last Seen: 2025-11-28 09:12:00
   Message: Timeout waiting for VM to become ready
   Recommendation: Check network configuration and retry
```

### Exporting Analytics

```bash
# Export analytics to CSV
azlin template analytics export --format csv --output templates-analytics.csv

# Export to JSON
azlin template analytics export --format json --output templates-analytics.json
```

## Template Sharing and Marketplace

### Sharing Templates

```bash
# Export template for sharing
azlin template export dev-vm-extended dev-vm-extended.yaml

# Share to team registry (file-based)
azlin template share dev-vm-extended --registry /shared/team/templates

# Share with metadata
azlin template share dev-vm-extended \
  --registry /shared/team/templates \
  --author "DevOps Team" \
  --tags "development,nodejs,docker"
```

### Browsing Shared Templates

```bash
# Browse local shared templates
azlin template browse --registry /shared/team/templates
```

**Output**:
```
Shared Templates (10 found):

1. azure-basics (v2.1.0)
   Author: team@company.com
   Tags: baseline, security, production
   Last Updated: 2025-11-15 10:00:00
   Usage: 142 deployments

2. secure-baseline (v1.5.0)
   Author: security@company.com
   Tags: security, hardening, compliance
   Last Updated: 2025-11-20 14:30:00
   Usage: 89 deployments

3. dev-standard (v1.2.1)
   Author: devops@company.com
   Tags: development, standard
   Last Updated: 2025-11-28 09:15:00
   Usage: 67 deployments
```

### Installing Shared Templates

```bash
# Install from shared registry
azlin template install azure-basics --from /shared/team/templates

# Install with custom name
azlin template install azure-basics \
  --from /shared/team/templates \
  --as my-azure-base
```

**Output**:
```
Installing template 'azure-basics' from /shared/team/templates...
✓ Downloaded template (v2.1.0)
✓ Validated template
✓ Installed as 'azure-basics'

Template Details:
  Name: azure-basics
  Version: 2.1.0
  Author: team@company.com
  Description: Standard Azure VM baseline with security hardening
```

## Advanced Usage

### Multi-Level Inheritance

Templates can inherit from templates that themselves inherit:

```yaml
# Level 1: Base
name: base-linux
vm_size: Standard_B1s
region: eastus

# Level 2: Security baseline
extends: base-linux
name: base-secure
cloud_init: |
  #cloud-config
  packages:
    - fail2ban

# Level 3: Development
extends: base-secure
name: dev-vm
vm_size: Standard_B2s
cloud_init: |
  #cloud-config
  packages:
    - fail2ban
    - nodejs
```

**Inheritance depth limit**: 5 levels (prevents circular references)

### Custom Metadata

Add arbitrary metadata to templates:

```bash
azlin template create app-server \
  --description "Application server template" \
  --vm-size Standard_D2s_v3 \
  --region eastus \
  --metadata '{"team": "backend", "environment": "production", "cost_center": "engineering"}'
```

**Access metadata**:
```bash
azlin template show app-server --format json | jq '.custom_metadata'
```

### Batch Operations

```bash
# Validate multiple templates
azlin template validate base-vm dev-vm prod-vm

# Delete multiple templates
azlin template delete old-* --pattern --force

# Export all templates
azlin template export --all --output ./backups/
```

## Migration from V1

### Automatic Migration

Existing templates are automatically migrated when first accessed:

```bash
# Old template (no version)
azlin template list
```

**Output**:
```
Migrating legacy templates...
✓ Migrated 'dev-vm' to v1.0.0
✓ Migrated 'prod-vm' to v1.0.0
✓ Migrated 'test-vm' to v1.0.0

Templates (3):
  - dev-vm (v1.0.0) - Development VM
  - prod-vm (v1.0.0) - Production VM
  - test-vm (v1.0.0) - Test VM
```

### Manual Migration

```bash
# Migrate specific template
azlin template migrate dev-vm

# Migrate all templates
azlin template migrate --all
```

## Configuration

### Template Schema Location

```
~/.azlin/templates/
├── local/              # User templates
├── shared/             # Shared templates
├── registry.yaml       # Metadata index
├── analytics.db        # Usage analytics (SQLite)
└── schema.json         # Validation schema
```

### Schema Customization

Edit `~/.azlin/templates/schema.json` to add custom validation rules:

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
    "custom_metadata": {
      "type": "object",
      "properties": {
        "cost_center": {"type": "string"},
        "environment": {"enum": ["dev", "staging", "production"]}
      }
    }
  }
}
```

## Troubleshooting

### Validation Errors

**Problem**: Template fails validation with cryptic error

**Solution**:
```bash
# Get detailed validation output
azlin template validate my-template --verbose

# Check specific field
azlin template lint my-template
```

### Inheritance Resolution Fails

**Problem**: `Error: Circular dependency detected in template inheritance`

**Solution**:
```bash
# Check inheritance chain
azlin template show my-template --show-inheritance

# Visualize dependency graph
azlin template deps my-template
```

### Analytics Database Corruption

**Problem**: Analytics commands fail with database errors

**Solution**:
```bash
# Rebuild analytics database
azlin template analytics rebuild

# Export data before rebuild
azlin template analytics export --output backup.json
azlin template analytics rebuild --import backup.json
```

## API Reference

### VMTemplateConfig

Extended dataclass with new fields:

```python
@dataclass
class VMTemplateConfig:
    # Core fields
    name: str
    description: str
    vm_size: str
    region: str
    cloud_init: str | None = None
    custom_metadata: dict[str, Any] = field(default_factory=dict)

    # Version 2 fields
    version: str = "1.0.0"
    created_at: str | None = None
    updated_at: str | None = None
    changelog: list[dict[str, str]] = field(default_factory=list)
    author: str | None = None
    extends: str | None = None  # Base template name
```

### TemplateValidator

```python
class TemplateValidator:
    @classmethod
    def validate_template(cls, template: VMTemplateConfig) -> tuple[bool, list[str]]:
        """Validate template against schema and Azure constraints.

        Returns:
            (is_valid, error_messages)
        """

    @classmethod
    def validate_inheritance_chain(cls, template: VMTemplateConfig) -> list[str]:
        """Validate template inheritance chain."""
```

### TemplateAnalytics

```python
class TemplateAnalytics:
    @classmethod
    def track_usage(
        cls,
        template_name: str,
        operation: str,
        success: bool,
        **kwargs
    ) -> None:
        """Track template usage event."""

    @classmethod
    def get_template_stats(cls, template_name: str) -> dict[str, Any]:
        """Get usage statistics for template."""
```

## Examples

### Example 1: Complete Development Workflow

```bash
# 1. Create base template
azlin template create base-dev \
  --description "Base development VM" \
  --vm-size Standard_B2s \
  --region eastus

# 2. Create extended template
cat > fullstack-dev.yaml << EOF
extends: base-dev
name: fullstack-dev
description: Full-stack development environment
cloud_init: |
  #cloud-config
  packages:
    - nodejs
    - postgresql
    - redis-server
EOF

azlin template import fullstack-dev.yaml

# 3. Validate before use
azlin template validate fullstack-dev

# 4. Deploy VM using template
azlin create my-dev-vm --template fullstack-dev

# 5. Check analytics
azlin template stats fullstack-dev
```

### Example 2: Team Template Sharing

```bash
# Team lead creates template
azlin template create team-standard \
  --description "Team standard VM configuration" \
  --vm-size Standard_D2s_v3 \
  --region eastus \
  --metadata '{"team": "engineering", "approved": true}'

# Share to team directory
azlin template share team-standard --registry /mnt/shared/templates

# Team members install
azlin template browse --registry /mnt/shared/templates
azlin template install team-standard --from /mnt/shared/templates
```

### Example 3: Template Lifecycle Management

```bash
# Create initial version
azlin template create prod-app \
  --description "Production application server" \
  --vm-size Standard_D4s_v3 \
  --region eastus

# Update with security patches
azlin template update prod-app \
  --cloud-init prod-app-v2.yaml \
  --changes "Added security hardening"

# Validate after update
azlin template validate prod-app

# Check version history
azlin template version prod-app

# Track usage
azlin template stats prod-app
```

## Best Practices

1. **Use Semantic Versioning**
   - MAJOR: Breaking changes (incompatible VM size changes)
   - MINOR: New features (added packages)
   - PATCH: Bug fixes (security updates)

2. **Leverage Composition**
   - Create base templates for common configurations
   - Extend bases for specific use cases
   - Limit inheritance depth to 3 levels for clarity

3. **Validate Before Deployment**
   - Always run `azlin template validate` before deploying
   - Use `azlin template lint` for style checks
   - Validate entire registry regularly

4. **Track Usage**
   - Monitor `azlin template stats` for success rates
   - Review error patterns monthly
   - Use analytics to identify optimization opportunities

5. **Share Responsibly**
   - Validate templates before sharing
   - Include clear descriptions
   - Use meaningful version numbers
   - Document changes in changelog

## See Also

- [Basic Templates Guide](./templates.md)
- [VM Creation](../commands/create.md)
- [Cloud-Init Configuration](./cloud-init.md)
- [Command Reference](../commands/index.md)

---

*Documentation last updated: 2025-12-01*
