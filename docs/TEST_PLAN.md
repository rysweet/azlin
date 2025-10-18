# NFS Storage Feature - Test Plan

## Overview
Complete TDD test plan for Azure Files NFS storage feature following DEFAULT_WORKFLOW.md.

## Test Strategy
1. Unit tests - Test individual functions in isolation
2. Integration tests - Test Azure CLI interactions
3. End-to-end tests - Test actual Azure operations
4. Manual tests - Real Azure resource creation

## Current Status

### Unit Tests (tests/unit/test_storage_manager.py)
✅ All 28 tests passing

### Integration Tests (tests/integration/test_storage_commands.py)
❌ NEEDED - Test CLI commands with mocked Azure CLI

### Bugs Found in Manual Testing

#### Bug 1: attribute 'location' vs 'region'
**File**: `src/azlin/commands/storage.py` line 192
**Issue**: Uses `account.location` but StorageInfo has `account.region`
**Fix**: Change to `account.region`

#### Bug 2: Storage status attribute access
**File**: `src/azlin/commands/storage.py` lines 233-240
**Issue**: Accessing attributes directly on status instead of status.info
**Fix**: Change `status.name` to `status.info.name`, etc.

#### Bug 3: NFS implementation uses wrong Azure service
**File**: `src/azlin/modules/storage_manager.py` lines 148-194
**Issue**: Uses HNS + blob storage for NFS, should use Azure Files NFS
**Fix**: Use FileStorage kind + file shares, not StorageV2 + blob containers

## Test Coverage Matrix

### Storage Manager (Unit Tests)
| Feature | Test | Status |
|---------|------|--------|
| Name validation | test_name_too_short | ✅ |
| Name validation | test_name_too_long | ✅ |
| Name validation | test_name_invalid_characters | ✅ |
| Tier validation | test_tier_invalid | ✅ |
| Size validation | test_size_negative | ✅ |
| Size validation | test_size_zero | ✅ |
| Create storage | test_create_calls_azure_cli | ✅ |
| Create storage | test_create_idempotent | ✅ |
| Create storage | test_create_returns_storage_info | ✅ |
| Create storage | test_create_handles_azure_error | ✅ |
| List storage | test_list_empty | ✅ |
| List storage | test_list_multiple | ✅ |
| List storage | test_list_filters_azlin_only | ✅ |
| Get storage | test_get_existing | ✅ |
| Get storage | test_get_not_found | ✅ |
| Storage status | test_status_includes_usage | ✅ |
| Storage status | test_status_includes_connected_vms | ✅ |
| Storage status | test_status_calculates_cost | ✅ |
| Delete storage | test_delete_success | ✅ |
| Delete storage | test_delete_with_connected_vms | ✅ |
| Delete storage | test_delete_force_with_connected_vms | ✅ |
| Delete storage | test_delete_not_found | ✅ |
| Data models | test_storage_info_creation | ✅ |
| Data models | test_storage_status_creation | ✅ |

### CLI Commands (Integration Tests)
| Command | Test | Status |
|---------|------|--------|
| storage create | Basic creation | ❌ TODO |
| storage create | With custom tier | ❌ TODO |
| storage create | With custom size | ❌ TODO |
| storage create | Validation errors | ❌ TODO |
| storage list | Empty list | ❌ TODO |
| storage list | Multiple accounts | ❌ TODO |
| storage list | Correct formatting | ❌ TODO |
| storage status | Show full status | ❌ TODO |
| storage status | Connected VMs | ❌ TODO |
| storage status | Cost calculation | ❌ TODO |
| storage delete | Success | ❌ TODO |
| storage delete | With confirmation | ❌ TODO |
| storage delete | Force delete | ❌ TODO |
| storage mount | Mount to VM | ❌ TODO |
| storage unmount | Unmount from VM | ❌ TODO |

### Manual Tests (Real Azure)
| Scenario | Status |
|----------|--------|
| Create Premium storage | ❌ FAILED - ConfigManager error |
| Create Standard storage | ❌ NOT TESTED |
| List storage accounts | ❌ FAILED - location attribute |
| Show storage status | ❌ FAILED - attribute access |
| Create VM with --nfs-storage | ❌ NOT TESTED |
| Mount storage to existing VM | ❌ NOT TESTED |
| Unmount storage from VM | ❌ NOT TESTED |
| Delete storage | ❌ NOT TESTED |
| Multi-VM shared storage | ❌ NOT TESTED |

## Next Steps

1. ✅ Create GitHub issue
2. ✅ Create worktree and branch
3. ❌ Write integration tests for CLI commands
4. ❌ Fix all bugs to make tests pass
5. ❌ Run pre-commit hooks
6. ❌ Manual testing with real Azure
7. ❌ Open PR
8. ❌ Code review
9. ❌ Merge

## Acceptance Criteria

All of these must pass before merge:
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Pre-commit hooks pass
- [ ] Manual test: Create storage account
- [ ] Manual test: List storage accounts
- [ ] Manual test: Show storage status
- [ ] Manual test: Create VM with shared storage
- [ ] Manual test: Files shared between 2 VMs
- [ ] Manual test: Mount existing VM to storage
- [ ] Manual test: Unmount storage from VM
- [ ] Manual test: Delete storage account
- [ ] No regressions in existing features
- [ ] Documentation updated
- [ ] All bugs fixed, no TODOs or stubs
