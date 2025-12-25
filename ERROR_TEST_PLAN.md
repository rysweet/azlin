# Error Path Testing Plan - Issue #424

## Current Status
- **Phase 1 (PR #477)**: 14.1% → 14.8% (+36 tests for snapshot_manager) ✅ MERGED
- **Phase 2 (This PR)**: 14.8% → 15.4% (+40 tests for ssh_key_vault) ✅ COMPLETE
- **Current error test coverage**: 15.4% (~712 pytest.raises usages out of 4,615 tests)
- **Target**: 25% (1,153 error tests)
- **Remaining gap**: 441 error tests needed for Phases 3-4

## Source Code Analysis
- **Raise statements**: 978 across 114 files
- **Subprocess calls**: 214 across 63 files (command injection risk)
- **Azure API imports**: 11 files (API failure risk)
- **Network operations**: 25 across 10 files (timeout/connection risk)
- **File operations**: 84 across 33 files (permission/disk space risk)

## Phase 2 Completion Summary

### Completed in Phase 2 (This PR)
- **File**: `tests/unit/modules/test_ssh_key_vault_errors.py`
- **Tests Added**: 40 comprehensive error tests
- **Coverage**: subprocess timeouts, Azure CLI errors, JSON parsing, validation, authentication, RBAC, file system errors
- **Status**: All tests passing ✅

### Error Test Categories Added (40 tests)
1. **get_current_user_principal_id errors** (5 tests): Timeouts, empty responses, not logged in, service principal issues
2. **KeyVault config validation** (1 test): Empty tenant ID
3. **ensure_key_vault_exists errors** (4 tests): Timeouts, race conditions, quota exceeded, unexpected errors
4. **find_key_vault errors** (3 tests): Timeouts, invalid JSON, resource not found
5. **ensure_rbac_permissions errors** (5 tests): Timeouts, race conditions, insufficient permissions
6. **SecretClient creation errors** (1 test): Network errors
7. **store_key errors** (5 tests): Permission denied, whitespace-only, HTTP errors, generic exceptions
8. **retrieve_key errors** (4 tests): Empty value, write permission denied, authentication, generic exceptions
9. **delete_key errors** (2 tests): Authentication errors, generic exceptions
10. **key_exists errors** (2 tests): Authentication errors, generic exceptions
11. **create_key_vault_manager errors** (3 tests): None credentials, auth chain exceptions, generic exceptions
12. **create_with_auto_setup errors** (5 tests): Vault creation, principal ID, RBAC, manager creation, generic errors

## Priority 1: Critical Gaps

### Top 5 Modules (Gap > 20)
1. **cli.py** (Gap: 50) - PENDING Phase 3
   - 50 raise statements, 0 error tests
   - Tests needed: Azure CLI failures, invalid arguments, command failures
   - Target: 50 new error tests

2. **snapshot_manager** (Gap: 41) - ✅ COMPLETE (Phase 1, PR #477)
   - 41 raise statements, 0 error tests → 36 error tests added
   - Tests: Snapshot creation failures, quota exceeded, invalid snapshots

3. **ssh_key_vault** (Gap: 28) - ✅ COMPLETE (Phase 2, This PR)
   - 41 raise statements, 13 existing error tests → 40 NEW comprehensive error tests added
   - Tests: Key Vault auth failures, key not found, permission denied, timeouts, validation

4. **storage_manager** (Gap: 25)
   - 34 raise statements, 9 existing error tests
   - Tests needed: Disk full, mount failures, NFS connection errors
   - Target: 25 new error tests

5. **dr_testing** (Gap: 23)
   - 30 raise statements, 7 existing error tests
   - Tests needed: DR failover failures, replication errors, backup verification
   - Target: 23 new error tests

**Week 1 Total**: 166 new error tests

## Priority 2: High Impact (Week 2)

### Modules with Gap 15-23
6. **nfs_mount_manager** (Gap: 23) - 23 tests
7. **vm_manager** (Gap: 22) - 22 tests
8. **env_manager** (Gap: 21) - 21 tests
9. **config_manager** (Gap: 21) - 21 tests
10. **nfs_provisioner** (Gap: 20) - 20 tests
11. **tag_manager** (Gap: 20) - 20 tests
12. **bastion_provisioner** (Gap: 19) - 19 tests
13. **service_principal_auth** (Gap: 16) - 16 tests
14. **backup_replication** (Gap: 16) - 16 tests
15. **vm_key_sync** (Gap: 16) - 16 tests
16. **resource_cleanup** (Gap: 15) - 15 tests

**Week 2 Total**: 209 new error tests

## Priority 3: Medium Impact (Week 3)

### Modules with Gap 10-14
17. **bastion_manager** (Gap: 14) - 14 tests
18. **backup_verification** (Gap: 12) - 12 tests
19. **context_manager** (Gap: 12) - 12 tests
20. **template_manager** (Gap: 10) - 10 tests

### Additional Critical Error Paths
21. **Network timeouts** - 20 tests across all network modules
22. **Azure API rate limits** - 15 tests
23. **File system errors** - 20 tests (disk full, permissions, etc.)
24. **Authentication failures** - 15 tests

**Week 3 Total**: 118 new error tests

## Summary

| Phase | Status | Modules | New Tests | Cumulative | Coverage |
|-------|--------|---------|-----------|------------|----------|
| Phase 1 (PR #477) | ✅ MERGED | snapshot_manager | 36 | 623 | 14.8% |
| Phase 2 (This PR) | ✅ COMPLETE | ssh_key_vault | 40 | 712 | 15.4% |
| Phase 3 (Next) | PENDING | cli, storage_manager, dr_testing, etc. | ~200 | ~912 | 19.8% |
| Phase 4 (Final) | PENDING | Remaining P2/P3 modules | ~240 | ~1,152 | 25.0% |

**Revised Target**: 1,153 error tests (25.0% coverage) - **ACHIEVES 25% goal**

## Test Categories by Error Type

### 1. Azure API Failures (120 tests)
- Authentication failures (AAD, service principal, CLI)
- Resource not found (VM, disk, network, resource group)
- Quota exceeded (cores, storage, public IPs)
- Rate limiting and throttling
- Invalid resource names/configurations
- Subscription not found/disabled

### 2. Network Errors (80 tests)
- Connection timeouts
- DNS resolution failures
- SSH connection refused
- Bastion connectivity issues
- Port conflicts
- Firewall/NSG blocking

### 3. File System Errors (70 tests)
- Disk full conditions
- Permission denied (read/write/execute)
- File not found
- Path too long
- Invalid file names
- Mount failures (NFS)

### 4. Command Execution Errors (60 tests)
- Subprocess failures (non-zero exit codes)
- Command not found
- Invalid arguments
- Timeout during execution
- Signal interruption

### 5. Validation Errors (80 tests)
- Invalid input formats
- Missing required parameters
- Conflicting options
- Out-of-range values
- Invalid JSON/YAML

### 6. State Management Errors (50 tests)
- Resource already exists
- Resource in wrong state (running/stopped/creating)
- Concurrent modification conflicts
- Lock acquisition failures

### 7. Configuration Errors (40 tests)
- Missing configuration files
- Invalid configuration values
- Conflicting settings
- Environment variable issues

## Implementation Strategy

### TDD Approach
1. **Write failing test first** (Red)
2. **Verify test catches the error** (Red confirmed)
3. **Ensure production code handles error correctly** (Green)
4. **Refactor if needed** (Refactor)

### Test Structure
```python
def test_<module>_<operation>_<error_condition>():
    """Test that <operation> raises <error> when <condition>."""
    # Arrange: Set up error condition
    # Act & Assert: Verify correct exception with pytest.raises
    with pytest.raises(ExpectedException, match="expected message pattern"):
        # Code that should fail
        pass
```

### Mocking Strategy
- Mock Azure SDK clients (avoid real API calls)
- Mock subprocess.run for command failures
- Mock file operations for FS errors
- Mock network calls for timeout simulation

## Success Criteria
- [ ] 450+ new error tests added (actual target: 493)
- [ ] Error coverage ≥ 25% (target: 26%)
- [ ] All new tests passing
- [ ] No false positives (tests that pass when they should fail)
- [ ] CI pipeline updated to enforce 25% minimum error coverage
- [ ] Zero-BS principle maintained (no stub tests, no swallowed exceptions)

## Risks and Mitigation

### Risk 1: Test Duplication
**Mitigation**: Review existing tests before adding new ones

### Risk 2: Fragile Tests
**Mitigation**: Use flexible error message matching (regex patterns)

### Risk 3: Missing Error Paths
**Mitigation**: Use coverage tools to identify untested raise statements

### Risk 4: Time Overrun
**Mitigation**: Focus on P1 first (166 tests gets us to 18.1%), then assess progress
