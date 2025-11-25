# azlin tag

**Manage Azure VM tags for organization and filtering**

## Description

The `azlin tag` command manages Azure resource tags on VMs, enabling powerful organizational queries, cost tracking, and VM filtering. Tags are key-value pairs that help categorize VMs by environment, project, team, cost center, or any custom criteria.

**Use cases:**
- **Organization**: Group VMs by project, team, or purpose
- **Cost tracking**: Allocate costs to departments or projects
- **Filtering**: Query VMs by tags using `azlin list --tag`
- **Automation**: Target specific VM groups in scripts
- **Compliance**: Track ownership and compliance requirements

**Benefits:**
- Tags persist across VM lifecycle (stop/start/deallocation)
- Visible in Azure portal and CLI
- Support Azure cost management and billing reports
- Enable powerful multi-criteria VM queries

## Commands

| Command | Description |
|---------|-------------|
| [`azlin tag add`](#azlin-tag-add) | Add tags to a VM |
| [`azlin tag remove`](#azlin-tag-remove) | Remove tags from a VM |
| [`azlin tag list`](#azlin-tag-list) | List all tags on a VM |

## azlin tag add

Add one or more tags to a VM.

### Usage

```bash
azlin tag add [OPTIONS] VM_NAME TAGS...
```

### Arguments

| Argument | Description |
|----------|-------------|
| `VM_NAME` | Required. Name of the VM to tag |
| `TAGS...` | Required. One or more tags in `key=value` format |

### Options

| Option | Type | Description |
|--------|------|-------------|
| `--resource-group, --rg TEXT` | Name | Azure resource group (default: from config) |
| `-h, --help` | Flag | Show command help and exit |

### Tag Format

- **Keys**: Alphanumeric, underscore, hyphen, period (e.g., `project`, `cost-center`, `env.type`)
- **Values**: Any characters including spaces (quote if spaces needed)

### Examples

```bash
# Add single tag
azlin tag add my-vm environment=production

# Add multiple tags
azlin tag add my-vm project=webapp team=backend cost-center=engineering

# Add tag with spaces in value
azlin tag add my-vm description="Production web server for API"

# Add tags with explicit resource group
azlin tag add my-vm environment=dev --rg my-resource-group

# Overwrite existing tag value
azlin tag add my-vm environment=staging  # Replaces previous value
```

## azlin tag remove

Remove one or more tags from a VM.

### Usage

```bash
azlin tag remove [OPTIONS] VM_NAME TAG_KEYS...
```

### Arguments

| Argument | Description |
|----------|-------------|
| `VM_NAME` | Required. Name of the VM |
| `TAG_KEYS...` | Required. One or more tag keys to remove |

### Options

| Option | Type | Description |
|--------|------|-------------|
| `--resource-group, --rg TEXT` | Name | Azure resource group (default: from config) |
| `-h, --help` | Flag | Show command help and exit |

### Examples

```bash
# Remove single tag
azlin tag remove my-vm environment

# Remove multiple tags
azlin tag remove my-vm project team cost-center

# Remove tag with explicit resource group
azlin tag remove my-vm environment --rg my-resource-group

# Remove all project-related tags
azlin tag remove my-vm project project-phase project-owner
```

## azlin tag list

List all tags currently set on a VM.

### Usage

```bash
azlin tag list [OPTIONS] VM_NAME
```

### Arguments

| Argument | Description |
|----------|-------------|
| `VM_NAME` | Required. Name of the VM |

### Options

| Option | Type | Description |
|--------|------|-------------|
| `--resource-group, --rg TEXT` | Name | Azure resource group (default: from config) |
| `-h, --help` | Flag | Show command help and exit |

### Examples

```bash
# List all tags on a VM
azlin tag list my-vm

# Example output:
# environment: production
# project: webapp
# team: backend
# cost-center: engineering
# owner: alice@example.com

# List tags with explicit resource group
azlin tag list my-vm --rg my-resource-group
```

## Tag Strategies

### Environment-Based Tagging

```bash
# Development VMs
azlin tag add dev-vm-1 environment=dev
azlin tag add dev-vm-2 environment=dev

# Staging VMs
azlin tag add staging-vm environment=staging

# Production VMs
azlin tag add prod-vm-1 environment=production
azlin tag add prod-vm-2 environment=production

# Query by environment
azlin list --tag environment=production
azlin list --tag environment=dev
```

### Project-Based Tagging

```bash
# Tag VMs by project
azlin tag add vm1 project=webapp-frontend
azlin tag add vm2 project=webapp-backend
azlin tag add vm3 project=ml-pipeline

# Find all VMs for a project
azlin list --tag project=webapp-frontend
```

### Team-Based Tagging

```bash
# Tag by team/department
azlin tag add vm1 team=backend
azlin tag add vm2 team=frontend
azlin tag add vm3 team=data-science

# Find VMs by team
azlin list --tag team=backend
azlin list --tag team=data-science
```

### Cost Tracking

```bash
# Tag for cost allocation
azlin tag add vm1 cost-center=engineering
azlin tag add vm2 cost-center=marketing
azlin tag add vm3 cost-center=research

# Tag with billing codes
azlin tag add vm1 billing-code=ENG-2024-Q4
azlin tag add vm2 billing-code=MKT-2024-Q4

# Query by cost center
azlin list --tag cost-center=engineering
```

### Ownership Tracking

```bash
# Tag with owner information
azlin tag add my-vm owner=alice@example.com
azlin tag add my-vm creator=bob@example.com
azlin tag add my-vm approver=charlie@example.com

# Find VMs by owner
azlin list --tag owner=alice@example.com
```

### Multi-Criteria Tagging

```bash
# Comprehensive tagging
azlin tag add web-server-prod \
    environment=production \
    project=ecommerce \
    team=backend \
    cost-center=engineering \
    owner=alice@example.com \
    criticality=high \
    backup=daily

# Query combinations
azlin list --tag environment=production
azlin list --tag project=ecommerce
```

## Common Tagging Patterns

### Standard Tag Set

Recommended standard tags for all VMs:

```bash
azlin tag add myvm \
    environment=dev \
    project=myproject \
    team=engineering \
    owner=user@example.com \
    cost-center=eng-dept \
    created-date=2024-11-24
```

### Lifecycle Tags

```bash
# Track VM purpose and lifecycle
azlin tag add myvm \
    purpose="Development environment" \
    lifecycle=temporary \
    expires=2024-12-31 \
    auto-shutdown=true
```

### Compliance Tags

```bash
# Compliance and governance
azlin tag add myvm \
    compliance=hipaa \
    data-classification=confidential \
    backup-required=yes \
    security-level=high
```

## Integration with azlin list

Tags enable powerful VM filtering:

```bash
# Find all production VMs
azlin list --tag environment=production

# Find all VMs for a team
azlin list --tag team=backend

# Find all temporary VMs
azlin list --tag lifecycle=temporary

# Find VMs requiring backups
azlin list --tag backup-required=yes

# Include stopped VMs in query
azlin list --tag environment=dev --all
```

## Automation Examples

### Bulk Tagging

```bash
# Tag all VMs with common tags
for vm in $(azlin list --all | awk 'NR>2 {print $1}'); do
    azlin tag add $vm created-date=$(date +%Y-%m-%d)
    azlin tag add $vm managed-by=azlin
done

# Tag VMs matching pattern
azlin list | grep "dev-" | while read vm _; do
    azlin tag add $vm environment=dev
done
```

### Conditional Operations Based on Tags

```bash
# Stop all development VMs at night
azlin list --tag environment=dev | grep Running | while read vm _; do
    azlin stop $vm --deallocate
done

# Start production VMs if stopped
azlin list --tag environment=production --all | grep Deallocated | while read vm _; do
    azlin start $vm
done
```

### Tag-Based Cost Reporting

```bash
# Get VMs by cost center for billing
for center in engineering marketing research; do
    echo "Cost Center: $center"
    azlin list --tag cost-center=$center
done

# Export for cost analysis
azlin list --tag cost-center=engineering --wide --no-quota > engineering-vms.txt
```

### Tag Cleanup

```bash
# Remove deprecated tags
for vm in $(azlin list --all | awk 'NR>2 {print $1}'); do
    azlin tag remove $vm old-tag deprecated-tag legacy-field
done

# Update tag values
for vm in $(azlin list --tag environment=dev | awk 'NR>2 {print $1}'); do
    azlin tag add $vm environment=development  # Standardize naming
done
```

## Azure Cost Management Integration

Tags are visible in Azure Cost Management:

```bash
# Tag VMs for cost tracking
azlin tag add vm1 cost-center=engineering project=webapp

# View in Azure portal:
# Cost Management + Billing > Cost Analysis > Group by tag
```

**Cost analysis queries:**
- Group by `cost-center` tag to see department spending
- Filter by `project` tag to track project costs
- Use `environment` tag to separate dev/staging/prod costs

## Troubleshooting

### Tag Not Applied

**Symptoms:** Tag doesn't appear after adding.

**Solutions:**
```bash
# Verify tag was added
azlin tag list myvm

# Check resource group is correct
azlin tag add myvm key=value --rg correct-rg

# Check Azure permissions (must have tag write permission)
az role assignment list --assignee $(az account show --query user.name -o tsv)
```

### Tag Not Visible in Portal

**Symptoms:** Tag shows in CLI but not Azure portal.

**Solutions:**
```bash
# Refresh portal (can take 1-2 minutes)

# Verify via Azure CLI
az vm show --name myvm --resource-group my-rg --query tags

# Re-apply tag
azlin tag add myvm key=value
```

### Cannot Remove Tag

**Symptoms:** Tag removal command succeeds but tag remains.

**Solutions:**
```bash
# Check tag key spelling
azlin tag list myvm  # Verify exact key name

# Use exact key name
azlin tag remove myvm exact-key-name

# Try Azure CLI directly
az vm update --name myvm --resource-group my-rg --remove tags.key-name
```

### Tag Value Has Special Characters

**Symptoms:** Tag value with spaces or special chars fails.

**Solutions:**
```bash
# Quote values with spaces
azlin tag add myvm description="My VM description"

# Escape special characters if needed
azlin tag add myvm path="/usr/local/bin"

# Avoid problematic characters: < > % & \ ? /
```

### Tag Limit Reached

**Symptoms:** "Too many tags" or "Tag limit exceeded" error.

**Azure limit:** 50 tags per resource

**Solutions:**
```bash
# List all tags
azlin tag list myvm

# Remove unused tags
azlin tag remove myvm old-tag1 old-tag2 old-tag3

# Consolidate tags (e.g., use metadata tag with JSON value)
azlin tag add myvm metadata='{"key1":"val1","key2":"val2"}'
```

## Best Practices

### 1. Establish Naming Conventions

```bash
# Use consistent key formats
# Good: environment, cost-center, project-name
# Avoid: env, COST_CENTER, ProjectName (inconsistent case/format)

# Document your tagging strategy
# Create a tagging policy document for your team
```

### 2. Required Tags

```bash
# Enforce required tags for all VMs
REQUIRED_TAGS="environment project owner cost-center"

for vm in $(azlin list --all | awk 'NR>2 {print $1}'); do
    for tag in $REQUIRED_TAGS; do
        if ! azlin tag list $vm | grep -q "^$tag:"; then
            echo "Missing required tag $tag on $vm"
        fi
    done
done
```

### 3. Tag Validation

```bash
# Validate tag values
VALID_ENVS="dev staging production"

for vm in $(azlin list --all | awk 'NR>2 {print $1}'); do
    env=$(azlin tag list $vm | grep "^environment:" | cut -d: -f2 | tr -d ' ')
    if [[ ! " $VALID_ENVS " =~ " $env " ]]; then
        echo "Invalid environment tag on $vm: $env"
    fi
done
```

### 4. Tag Inheritance

```bash
# Apply resource group tags to VMs
RG_TAGS=$(az group show --name my-rg --query tags -o json)

# Extract and apply to VMs
for vm in $(azlin list | awk 'NR>2 {print $1}'); do
    azlin tag add $vm cost-center=from-rg project=from-rg
done
```

## Related Commands

- [`azlin list --tag`](list.md) - Filter VMs by tags
- [`azlin session`](session.md) - Session names are stored as tags
- [`azlin new`](new.md) - Provision VMs (add tags after creation)

## Source Code

- [tag_manager.py](https://github.com/rysweet/azlin/blob/main/src/azlin/tag_manager.py) - Tag management logic
- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - CLI command definition

## See Also

- [All VM commands](index.md)
- [Azure Resource Tagging Best Practices](https://docs.microsoft.com/azure/azure-resource-manager/management/tag-resources)
- [Cost Management with Tags](https://docs.microsoft.com/azure/cost-management-billing/costs/cost-analysis-common-uses)
