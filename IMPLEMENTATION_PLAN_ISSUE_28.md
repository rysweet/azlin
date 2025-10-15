# Implementation Plan: GitHub Issue #28 - Batch Operations

## Overview
Implement `azlin batch` command for executing operations on multiple VMs simultaneously.

## Feature Requirements
- Tag-based VM selection
- Pattern matching for VM names  
- Parallel execution with progress tracking
- Per-VM error handling
- Support for stop, start, command, sync operations

## Architecture

### 1. Core Module: `batch_executor.py`
**Location:** `src/azlin/batch_executor.py`

**Classes:**
- `BatchSelector` - VM selection logic (tags, patterns, all)
- `BatchExecutor` - Parallel execution orchestrator
- `BatchResult` - Result aggregation and reporting

**Key Methods:**
- `select_vms_by_tag(tag_filter: str)` - Parse and filter by tags
- `select_vms_by_pattern(pattern: str)` - Glob/regex VM name matching
- `select_all_vms(resource_group: str)` - Get all VMs in RG
- `execute_parallel(vms: List[VMInfo], operation, max_workers: int)` - Execute with progress
- `format_results(results: List[BatchResult])` - Format output table

### 2. CLI Integration: `cli.py`
**New Command Group:** `batch`

**Subcommands:**
- `azlin batch stop --tag 'env=dev'`
- `azlin batch start --vm-pattern 'test-*'`
- `azlin batch command 'git pull' --all`
- `azlin batch sync --resource-group my-rg`

**Options:**
- `--tag TAG` - Filter by tag (format: key=value)
- `--vm-pattern PATTERN` - Filter by VM name pattern
- `--all` - Select all VMs in resource group
- `--resource-group RG` - Target resource group
- `--max-workers N` - Parallel execution limit (default: 10)
- `--confirm` - Skip confirmation prompts

### 3. Test Suite: `test_batch_executor.py`
**Location:** `tests/unit/test_batch_executor.py`

**Test Classes:**
- `TestBatchSelector` - VM selection logic
- `TestBatchExecutor` - Parallel execution
- `TestBatchResults` - Result aggregation
- `TestBatchErrorHandling` - Failure scenarios

## Implementation Steps (TDD)

### Phase 1: Architecture & Tests (RED)
1. Create implementation plan document ✓
2. Create `tests/unit/test_batch_executor.py` with failing tests
3. Create `src/azlin/batch_executor.py` stub

### Phase 2: Implementation (GREEN)
4. Implement `BatchSelector` class
5. Implement `BatchExecutor` class
6. Implement `BatchResult` class
7. Add CLI commands to `cli.py`

### Phase 3: Refactoring & Polish (REFACTOR)
8. Refactor for code quality
9. Add logging and error messages
10. Update documentation

### Phase 4: Quality Assurance
11. Run linter (ruff)
12. Run all tests
13. Manual testing

### Phase 5: Commit & Documentation
14. Commit with message: "feat: implement batch operations for fleet management (#28)"
15. Create summary document

## Test Coverage

### Unit Tests
- Tag parsing and filtering
- Pattern matching (glob and regex)
- Parallel execution with mocking
- Error handling per VM
- Result aggregation
- Progress tracking
- Edge cases (empty results, all failures, partial success)

### Integration Tests (future)
- Actual Azure VM operations
- End-to-end batch workflows

## Dependencies
- Existing: `vm_manager.VMManager` for VM listing
- Existing: `vm_lifecycle_control.VMLifecycleController` for stop/start
- Existing: `remote_exec.RemoteExecutor` for command execution
- Existing: `modules.home_sync.HomeSyncManager` for sync
- New: `batch_executor.BatchExecutor` for orchestration

## Edge Cases
1. No VMs match selection criteria - Show message, exit gracefully
2. All VMs fail operation - Show error summary, exit with code 1
3. Partial success - Show summary with successes and failures
4. Invalid tag format - Validate and show error
5. Invalid pattern - Validate and show error
6. Timeout on individual VMs - Continue with others, report timeout
7. User cancellation - Stop gracefully, show partial results

## Security Considerations
- Input validation for tags and patterns
- No shell=True in subprocess calls
- Timeout enforcement per VM
- Resource limits (max_workers)

## Performance
- Default max_workers: 10 (configurable)
- Timeout per VM: 300s for operations
- Progress updates every VM completion
- Non-blocking UI updates

## Success Criteria
- [ ] All unit tests passing
- [ ] Linter passing
- [ ] Can batch stop VMs by tag
- [ ] Can batch start VMs by pattern
- [ ] Can execute commands on multiple VMs
- [ ] Can sync to multiple VMs
- [ ] Progress shown for each VM
- [ ] Individual failures handled gracefully
- [ ] Documentation updated
- [ ] Committed with reference to #28
