# Implementation Plan: Issue #22 - azlin tag command

## Feature Overview
Implement resource tagging functionality to help organize and filter Azure VMs using tags.

## Commands to Implement

### 1. `azlin tag` - Manage VM tags
- `azlin tag <vm> --add <key>=<value>` - Add tag(s) to a VM
- `azlin tag <vm> --remove <key>` - Remove tag(s) from a VM  
- `azlin tag <vm> --list` - List all tags on a VM

### 2. `azlin list --tag` - Filter VMs by tag
- `azlin list --tag <key>=<value>` - List VMs with specific tag
- `azlin list --tag <key>` - List VMs with any value for key

## Architecture

### New Module: `tag_manager.py`
**Class: `TagManager`**
- `add_tags(vm_name: str, resource_group: str, tags: Dict[str, str]) -> None`
- `remove_tags(vm_name: str, resource_group: str, tag_keys: List[str]) -> None`
- `get_tags(vm_name: str, resource_group: str) -> Dict[str, str]`
- `filter_vms_by_tag(vms: List[VMInfo], tag_filter: str) -> List[VMInfo]`

**Exception: `TagManagerError`**

### Updates to Existing Modules

#### `vm_manager.py`
- VMInfo already has `tags: Optional[Dict[str, str]]` field ✓
- No changes needed - tags are already parsed from Azure CLI

#### `cli.py`
- Add `@main.command(name='tag')` with subcommands
- Update `list_command()` to add `--tag` option

## Azure CLI Integration
Uses `az vm update` for tag operations:
- Add tags: `az vm update --name <vm> --resource-group <rg> --set tags.key=value`
- Remove tags: `az vm update --name <vm> --resource-group <rg> --remove tags.key`
- Get tags: Already retrieved via `az vm show` (tags field)

## Test Coverage

### Unit Tests: `test_tag_manager.py`
1. `test_add_tags_success()` - Add single tag
2. `test_add_tags_multiple()` - Add multiple tags
3. `test_remove_tags_success()` - Remove single tag
4. `test_remove_tags_multiple()` - Remove multiple tags
5. `test_get_tags()` - Retrieve tags
6. `test_filter_vms_by_tag_exact_match()` - Filter with key=value
7. `test_filter_vms_by_tag_key_only()` - Filter with key only
8. `test_filter_vms_no_match()` - No VMs match filter
9. `test_add_tags_vm_not_found()` - Error handling
10. `test_invalid_tag_format()` - Validation

### Integration with Existing Tests
- Update `test_cli.py` to test tag command
- Test tag filtering in list command

## TDD Workflow

### Phase 1: RED - Write Failing Tests
1. Create `tests/unit/test_tag_manager.py`
2. Write all unit tests (should fail)
3. Run tests to confirm failures

### Phase 2: GREEN - Implement Feature
1. Create `src/azlin/tag_manager.py`
   - Implement `TagManager` class
   - Implement all methods
2. Update `src/azlin/cli.py`
   - Add `tag` command
   - Update `list` command with `--tag` filter
3. Run tests to confirm passes

### Phase 3: REFACTOR
1. Review code for improvements
2. Add docstrings and type hints
3. Ensure error handling is robust
4. Check code style consistency

### Phase 4: Lint
1. Run `ruff` linter
2. Fix any issues

### Phase 5: Commit
1. Commit with message: "Implement tag command for VM organization (fixes #22)"

### Phase 6: Documentation
1. Create `IMPLEMENTATION_COMPLETE_22.md`
2. Update README if needed

## Example Usage

```bash
# Add tags to a VM
azlin tag my-vm --add env=dev team=backend

# Add single tag
azlin tag my-vm --add project=api

# Remove tags
azlin tag my-vm --remove env team

# List tags on a VM
azlin tag my-vm --list

# Filter VMs by tag
azlin list --tag env=dev
azlin list --tag team=backend
azlin list --tag project  # Any VM with 'project' tag

# Combine with other options
azlin list --tag env=prod --all

# Use with cost command (future enhancement)
azlin cost --tag env=dev
```

## Implementation Notes

### Tag Format
- Azure tags: key-value pairs
- Keys: alphanumeric, underscore, hyphen, period
- Values: alphanumeric, spaces, special chars allowed
- Case-sensitive

### CLI Parsing
- `--add` accepts multiple key=value pairs: `--add key1=val1 key2=val2`
- `--remove` accepts multiple keys: `--remove key1 key2`
- `--list` is a flag (no arguments)
- Mutually exclusive: only one of --add, --remove, --list per invocation

### Error Handling
- VM not found
- Resource group not found
- Invalid tag format
- Azure CLI errors
- Permission errors

### Security Considerations
- Input validation for tag keys/values
- No shell injection via subprocess (use list args)
- Sanitized logging (don't log sensitive tag values)

## Success Criteria
- [ ] All unit tests pass
- [ ] Can add tags to VMs
- [ ] Can remove tags from VMs
- [ ] Can list tags on VMs
- [ ] Can filter VMs by tags
- [ ] Error handling works correctly
- [ ] Linter passes
- [ ] Code committed with reference to #22
- [ ] Implementation summary created
