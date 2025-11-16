# DoIt Resource Tagging and Management Commands

## Overview

This implementation adds automatic resource tagging and management commands to the azlin doit agent, enabling tracking and cleanup of all resources created by the autonomous deployment system.

## Features Implemented

### 1. Automatic Resource Tagging

All resources created by doit are automatically tagged with:
- `azlin-doit-owner`: Current Azure user or service principal name
- `azlin-doit-created`: ISO timestamp when resource was created

**Implementation:**
- `/src/azlin/doit/utils/tagging.py` - Tagging utilities
- Modified all strategy files to include tags in Azure CLI commands
- Updated executor to generate tags and pass them to strategies

**Modified Files:**
- `/src/azlin/doit/strategies/base.py` - Added tagging support to base Strategy class
- `/src/azlin/doit/strategies/cosmos_db.py` - Added tags to Cosmos DB commands
- `/src/azlin/doit/strategies/app_service.py` - Added tags to App Service commands
- `/src/azlin/doit/strategies/storage.py` - Added tags to Storage commands
- `/src/azlin/doit/strategies/keyvault.py` - Added tags to Key Vault commands
- `/src/azlin/doit/strategies/api_management.py` - Added tags to APIM commands
- `/src/azlin/doit/strategies/resource_group.py` - Added tags to Resource Group commands
- `/src/azlin/doit/engine/executor.py` - Generate and pass tags to strategies

### 2. Resource Management Commands

Four new management commands have been added:

#### `azlin doit list`
Lists all resources created by doit for the current user.

```bash
# List your resources
azlin doit list

# List resources for a specific user
azlin doit list --username user@example.com
```

**Output:**
- Table showing resource name, type, resource group, location, and creation date
- Total count of resources

#### `azlin doit show <resource-id>`
Shows detailed information about a specific resource.

```bash
azlin doit show /subscriptions/.../resourceGroups/rg-name/providers/Microsoft.Web/sites/my-app
```

**Output:**
- Full JSON details of the resource

#### `azlin doit cleanup`
Deletes all doit-created resources for the current user.

```bash
# With confirmation prompt
azlin doit cleanup

# Skip confirmation
azlin doit cleanup --force

# Dry run (show what would be deleted)
azlin doit cleanup --dry-run

# Cleanup specific user's resources
azlin doit cleanup --username user@example.com
```

**Features:**
- Shows list of resources before deletion
- Confirmation prompt (unless --force)
- Deletes in dependency order (data resources last)
- Reports success/failure for each resource

#### Aliases: `azlin doit destroy` and `azlin doit delete`
Both commands are aliases for `cleanup` with the same options.

```bash
azlin doit destroy --force
azlin doit delete --dry-run
```

### 3. Resource Manager Module

**New Module:** `/src/azlin/doit/manager/`

- `resource_manager.py` - Core ResourceManager class
  - `list_resources()` - Query resources by tag
  - `get_resource_details()` - Get detailed resource info
  - `cleanup_resources()` - Delete resources in proper order
- `__init__.py` - Public API exports

**Features:**
- Automatic username detection from Azure CLI
- Smart dependency ordering for deletion
- Comprehensive error handling
- Support for dry-run mode

### 4. End-to-End Test Scenarios

**New File:** `/tests/e2e/test_doit_scenarios.py`

Comprehensive test suite with 6 major scenarios:

1. **Scenario 1: Simple Cosmos DB** - Basic resource creation and tagging
2. **Scenario 2: App Service + Cosmos Connected** - Multi-resource with connections
3. **Scenario 3: Two App Services behind APIM** - Multiple instances, API gateway
4. **Scenario 4: Serverless Pipeline** - Function App with dependencies
5. **Scenario 5: Failure Recovery** - Error handling and recovery
6. **Scenario 6: Multi-Region HA Setup** - Complex multi-region deployment

Plus additional tests for management commands:
- `test_list_command` - Validate resource listing
- `test_show_command` - Validate resource details
- `test_cleanup_command_dry_run` - Validate dry-run behavior
- `test_cleanup_command_actual` - Validate actual deletion

**Running Tests:**
```bash
pytest tests/e2e/test_doit_scenarios.py -v
```

**Note:** Tests require:
- Valid Azure subscription
- Azure CLI authenticated
- ANTHROPIC_API_KEY environment variable
- Tests create real resources and may incur costs

## Usage Examples

### Complete Workflow

```bash
# 1. Deploy infrastructure
azlin doit deploy "Give me App Service with Cosmos DB"

# 2. List created resources
azlin doit list

# Output:
# Doit Resources for: user@example.com
#
# ┌─────────────────┬──────────────┬──────────────────┬──────────┬──────────────────┐
# │ Name            │ Type         │ Resource Group   │ Location │ Created          │
# ├─────────────────┼──────────────┼──────────────────┼──────────┼──────────────────┤
# │ rg-doit-12345   │ resourceGr…  │ rg-doit-12345    │ eastus   │ 2025-11-08 10:00 │
# │ app-service-1   │ sites        │ rg-doit-12345    │ eastus   │ 2025-11-08 10:02 │
# │ cosmos-db-1     │ database…    │ rg-doit-12345    │ eastus   │ 2025-11-08 10:05 │
# └─────────────────┴──────────────┴──────────────────┴──────────┴──────────────────┘
# Total: 3 resources

# 3. Get details of specific resource
azlin doit show /subscriptions/.../providers/Microsoft.Web/sites/app-service-1

# 4. Clean up all resources (with confirmation)
azlin doit cleanup

# Found 3 resources to delete:
# ...
# Are you sure you want to continue? [y/N]: y
#
# Deleting resources...
# ✓ app-service-1
# ✓ cosmos-db-1
# ✓ rg-doit-12345
```

### Dry Run Example

```bash
# See what would be deleted without actually deleting
azlin doit cleanup --dry-run

# Output shows resources that would be deleted but doesn't delete them
```

### Force Cleanup

```bash
# Delete without confirmation (useful for scripts/automation)
azlin doit cleanup --force
```

## Architecture

### Tagging Flow

```
User Request
    ↓
DoItOrchestrator.execute()
    ↓
ExecutionEngine.__init__()
    → Generates tags: generate_doit_tags()
    ↓
ExecutionEngine._plan_action()
    → Gets strategy for resource type
    → Sets tags on strategy: strategy.set_tags(tags)
    ↓
Strategy.build_command()
    → Adds tags to Azure CLI command: --tags azlin-doit-owner=user azlin-doit-created=timestamp
    ↓
Azure CLI creates resource with tags
```

### Cleanup Flow

```
azlin doit cleanup
    ↓
ResourceManager.list_resources()
    → Queries: az resource list --tag azlin-doit-owner=<username>
    ↓
ResourceManager.cleanup_resources()
    → Groups resources by resource group
    → Sorts by deletion priority (apps before data)
    → Deletes each resource: az resource delete --ids <resource-id>
    → Tracks success/failure
    ↓
Reports results to user
```

## File Structure

```
src/azlin/doit/
├── utils/
│   ├── __init__.py           # Exports tagging utilities
│   └── tagging.py            # Tag generation and formatting
├── manager/
│   ├── __init__.py           # Exports ResourceManager
│   └── resource_manager.py   # Resource management logic
├── strategies/
│   ├── base.py               # Updated with tag support
│   ├── cosmos_db.py          # Updated with tags
│   ├── app_service.py        # Updated with tags
│   ├── storage.py            # Updated with tags
│   ├── keyvault.py           # Updated with tags
│   ├── api_management.py     # Updated with tags
│   └── resource_group.py     # Updated with tags
├── engine/
│   └── executor.py           # Updated to generate and pass tags
└── commands/
    └── doit.py               # Updated with new commands

tests/e2e/
└── test_doit_scenarios.py    # Comprehensive test scenarios
```

## Implementation Notes

### Tag Format

Tags use underscore-separated keys to match Azure naming conventions:
- `azlin-doit-owner`: The Azure account name (user or service principal)
- `azlin-doit-created`: ISO 8601 timestamp with 'Z' suffix

For service principals (UUIDs), only the first 8 characters are used for brevity.

### Dependency-Aware Deletion

Resources are deleted in the following priority order:
1. API Management APIs/backends (priority 1)
2. App Services (priority 2)
3. App Service Plans (priority 3)
4. Key Vaults (priority 4)
5. Cosmos DB and Storage (priority 5)

This ensures dependent resources are deleted before their dependencies.

### Error Handling

- All operations include comprehensive error handling
- Failures during cleanup are tracked and reported
- Exit code 1 if any deletions fail
- Dry-run mode never modifies resources

### CLI Integration

The old single-function `doit` command has been deprecated in favor of the new command group structure:
- Old: `azlin doit "create something"` (deprecated)
- New: `azlin doit deploy "create something"`

The command group provides better organization and more functionality through subcommands.

## Testing

### Manual Testing

```bash
# Test tagging
azlin doit deploy "Create Cosmos DB"
az resource list --tag azlin-doit-owner=$(az account show --query user.name -o tsv)

# Test list
azlin doit list

# Test cleanup dry-run
azlin doit cleanup --dry-run

# Test actual cleanup
azlin doit cleanup --force
```

### Automated Testing

```bash
# Run all e2e tests
pytest tests/e2e/test_doit_scenarios.py -v

# Run specific scenario
pytest tests/e2e/test_doit_scenarios.py::TestDoItScenarios::test_scenario_1_simple_cosmos_db -v

# Run management command tests
pytest tests/e2e/test_doit_scenarios.py::TestDoItManagementCommands -v
```

## Future Enhancements

Potential improvements for future iterations:

1. **Filtering Options**
   - Filter by resource type
   - Filter by date range
   - Filter by location

2. **Export/Import**
   - Export resource list to JSON/CSV
   - Generate cost reports for doit resources

3. **Batch Operations**
   - Tag existing resources retroactively
   - Update tags on all resources

4. **Advanced Cleanup**
   - Delete only specific resource types
   - Keep resources matching certain criteria
   - Schedule delayed cleanup

5. **Integration**
   - Integration with Azure Resource Graph for faster queries
   - Cost tracking per deployment
   - Resource dependency visualization

## Migration Notes

For users with the old `doit` command:
- The old command is now `azlin doit-old` (deprecated)
- Update scripts to use `azlin doit deploy` instead
- Existing resources without tags won't be tracked by management commands
- Consider manually tagging existing resources if needed

## Support

For issues or questions:
- Check the e2e tests for usage examples
- Refer to individual command help: `azlin doit <command> --help`
- See main azlin documentation for general guidance
