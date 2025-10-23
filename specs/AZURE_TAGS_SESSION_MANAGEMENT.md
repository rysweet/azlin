# Azure Tags for Session Management

## Overview

Replace local config file session management with Azure VM tags as the source of truth.

## Problem Statement

Current implementation stores session names in `~/.azlin/config.toml` which causes:
1. Lost config = lost session names
2. Single resource group limitation
3. No multi-user/multi-machine sync
4. Orphaned entries when VMs deleted externally
5. No way to discover all azlin-managed VMs

## Solution

Use Azure VM tags to store session metadata:

```json
{
  "managed-by": "azlin",
  "azlin-session": "amplihack-dev",
  "azlin-created": "2025-01-23T20:15:00Z",
  "azlin-owner": "rysweet"
}
```

## Tag Schema

### Standard Tags

| Tag Key | Required | Example | Description |
|---------|----------|---------|-------------|
| `managed-by` | Yes | `azlin` | Identifies azlin-managed VMs |
| `azlin-session` | No | `amplihack-dev` | Session name for the VM |
| `azlin-created` | Yes | `2025-01-23T20:15:00Z` | ISO 8601 creation timestamp |
| `azlin-owner` | No | `rysweet` | User who created the VM |

### Tag Rules

- Tag keys are case-sensitive
- Tag values max 256 characters
- Session names must match: `^[a-zA-Z0-9_-]+$`
- Reserved names: `azlin-*` prefix for future tags

## Architecture

### New Module: TagManager

```python
class TagManager:
    """Manage Azure VM tags for azlin."""

    @classmethod
    def get_session_name(cls, vm_name: str, resource_group: str) -> str | None:
        """Get session name from VM tags."""

    @classmethod
    def set_session_name(cls, vm_name: str, resource_group: str, session: str) -> bool:
        """Set session name in VM tags."""

    @classmethod
    def delete_session_name(cls, vm_name: str, resource_group: str) -> bool:
        """Remove session name from VM tags."""

    @classmethod
    def get_vm_by_session(cls, session_name: str, resource_group: str | None) -> VMInfo | None:
        """Find VM by session name, optionally within RG."""

    @classmethod
    def list_managed_vms(cls, resource_group: str | None = None) -> list[VMInfo]:
        """List all azlin-managed VMs, optionally filtered by RG."""

    @classmethod
    def set_managed_tags(cls, vm_name: str, resource_group: str, owner: str | None = None) -> bool:
        """Set standard azlin management tags on VM."""
```

### Hybrid Resolution Strategy

Priority order for session name resolution:

1. **VM Tags** (source of truth)
   - Query Azure for `azlin-session` tag
   - Fast path: cache results for 60 seconds

2. **Local Config** (backward compatibility)
   - Fall back to `~/.azlin/config.toml`
   - Only if VM has no tags OR tag read fails

3. **Manual Override**
   - `--session` flag always takes precedence

### Updated ConfigManager

```python
class ConfigManager:
    @classmethod
    def get_vm_name_by_session(cls, session_name: str, config: str | None = None,
                                resource_group: str | None = None) -> str | None:
        """Resolve session to VM name using hybrid strategy.

        Priority:
        1. Check Azure tags in specified RG (or all RGs if None)
        2. Fall back to local config file
        """
        # Try tags first
        if resource_group:
            vm = TagManager.get_vm_by_session(session_name, resource_group)
            if vm:
                return vm.name
        else:
            # Search across all RGs
            vm = TagManager.get_vm_by_session(session_name, None)
            if vm:
                return vm.name

        # Fall back to local config
        return cls._get_session_from_config(session_name, config)
```

## Implementation Plan

### Phase 1: Core TagManager (Required)

- [ ] Create `src/azlin/tag_manager.py`
- [ ] Implement tag CRUD operations via Azure CLI
- [ ] Add error handling for permission issues
- [ ] Add 60-second LRU cache for tag queries
- [ ] Unit tests with mocked Azure CLI calls

### Phase 2: Integration (Required)

- [ ] Update `ConfigManager.get_vm_name_by_session()` to use hybrid strategy
- [ ] Update `vm_provisioning.py` to add tags on VM creation
- [ ] Update `session` command to write to tags
- [ ] Update `list` command to support cross-RG discovery
- [ ] Update `kill`/`destroy` commands (tags auto-deleted by Azure)

### Phase 3: Migration (Required)

- [ ] Create `azlin migrate-sessions` command
- [ ] Read all sessions from local config
- [ ] Write to VM tags (if VM exists)
- [ ] Report success/failures
- [ ] Backup config file before migration

### Phase 4: Documentation (Required)

- [ ] Update README with new tag-based behavior
- [ ] Document migration process
- [ ] Update API reference
- [ ] Add troubleshooting section for permission issues

## Azure CLI Commands

### Get Tags
```bash
az vm show --name VM_NAME --resource-group RG_NAME --query tags -o json
```

### Set Tag
```bash
az vm update --name VM_NAME --resource-group RG_NAME --set tags.azlin-session=SESSION_NAME
```

### Delete Tag
```bash
az vm update --name VM_NAME --resource-group RG_NAME --remove tags.azlin-session
```

### List VMs by Tag
```bash
# Single RG
az vm list --resource-group RG_NAME --query "[?tags.\"managed-by\"=='azlin']" -o json

# All RGs (cross-subscription discovery)
az vm list --query "[?tags.\"managed-by\"=='azlin']" -o json
```

## Azure Permissions Required

Users need these RBAC permissions:

- `Microsoft.Compute/virtualMachines/read` - Read VM details and tags
- `Microsoft.Compute/virtualMachines/write` - Update VM tags

These are included in standard roles:
- Virtual Machine Contributor
- Contributor
- Owner

## Backward Compatibility

### Existing VMs

VMs created before this feature will NOT have tags. They will:
- Still work with all commands
- Be discovered by `azlin list --rg RG_NAME` (existing behavior)
- NOT appear in cross-RG `azlin list` (new behavior)
- Can be migrated with `azlin migrate-sessions`

### Config File

The `~/.azlin/config.toml` remains for:
- Default settings (region, size, resource group)
- Backward compatibility fallback
- Local overrides if needed

Session names section will be deprecated but still read.

## Error Handling

### Permission Denied
```
Error: Unable to read VM tags. Check Azure permissions.
Required: Microsoft.Compute/virtualMachines/read

Falling back to local config file for session resolution.
```

### Network Errors
```
Warning: Azure API timeout. Using cached session data.
Cache age: 45 seconds (max: 60 seconds)
```

### Tag Conflicts
```
Error: Session name 'prod' already in use by VM 'azlin-vm-123'.
Choose a different session name or delete the existing one.
```

## Performance Considerations

### Caching Strategy

- Cache tag queries for 60 seconds (LRU cache, max 100 entries)
- Cache key: `(vm_name, resource_group)`
- Invalidate on: set/delete operations

### Batch Operations

For `azlin list`:
- Single Azure CLI call to list all VMs with tags
- Parse JSON response (fast)
- No per-VM queries needed

Expected performance:
- Single RG: ~1-2 seconds (existing)
- Cross-RG: ~2-4 seconds (new, acceptable)

## Testing Strategy

### Unit Tests
- Mock Azure CLI responses
- Test tag CRUD operations
- Test hybrid resolution logic
- Test error handling

### Integration Tests
- Create real VM with tags (CI environment)
- Verify tag read/write/delete
- Verify cross-RG discovery
- Clean up after tests

### Manual Testing
- Migrate existing config to tags
- Test all commands with session names
- Test cross-RG list
- Test permission errors

## Acceptance Criteria

- [ ] TagManager can read/write/delete Azure tags
- [ ] Session resolution checks tags before config
- [ ] `azlin list` discovers VMs across all RGs by default
- [ ] `azlin list --rg foo` still works for single RG
- [ ] `azlin create` sets tags automatically
- [ ] `azlin session VM SESSION` updates tags
- [ ] Migration utility moves config → tags
- [ ] All existing tests pass
- [ ] New tests for tag operations ≥ 80% coverage
- [ ] Documentation updated
- [ ] Manual testing with real Azure VMs successful

## Rollout Plan

### Week 1: Development
- Implement TagManager
- Update session resolution
- Write tests

### Week 2: Testing
- Integration tests in CI
- Manual testing with real VMs
- Performance validation

### Week 3: Documentation & Review
- Update all docs
- Code review
- Address feedback

### Week 4: Release
- Merge to main
- Release notes
- User communication about migration

## Future Enhancements (Out of Scope)

- Tag-based cost allocation
- Team-based session namespaces
- Session expiration dates
- Automated session cleanup
- Azure Resource Graph integration (faster queries)

## Complexity

**Medium** - Requires Azure CLI integration, caching, backward compatibility

**Estimated Scope:**
- TagManager: ~300 LOC
- Integration changes: ~200 LOC
- Tests: ~400 LOC
- Migration tool: ~100 LOC
- Total: ~1,000 LOC

**Dependencies:**
- Azure CLI (existing dependency)
- No new external dependencies

## Related Issues

- Fixes session name resolution bugs
- Enables cross-RG VM discovery
- Improves multi-user workflows
- Reduces config file fragility
