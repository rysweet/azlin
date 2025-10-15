# Implementation Plan: Issue #21 - azlin logs Command

## Overview
Add `azlin logs` command to view VM logs without requiring SSH connection.

## Architecture

### Module: `log_viewer.py`
Location: `src/azlin/log_viewer.py`

**Purpose**: View VM logs using SSH-based retrieval

**Classes**:
1. `LogViewerError` - Exception for log viewing errors
2. `LogType` - Enum for log types (SYSTEM, BOOT, APP, KERNEL)
3. `LogViewer` - Main class for log retrieval

**Key Methods**:
- `get_system_logs()` - Retrieve journalctl logs via SSH
- `get_boot_logs()` - Retrieve boot logs via SSH
- `get_app_logs()` - Retrieve application logs
- `follow_logs()` - Stream logs in real-time
- `filter_by_time()` - Apply time-based filtering

### CLI Integration
File: `src/azlin/cli.py`

**Command**: `azlin logs <vm> [options]`

**Options**:
- `--boot` - Show boot logs
- `--app` - Show application logs  
- `--follow` / `-f` - Follow logs (tail -f style)
- `--since <time>` - Filter by time (e.g., "1 hour", "30m", "2024-01-01")
- `--lines <n>` - Number of lines to show (default: 100)
- `--kernel` - Show kernel logs
- `--resource-group` / `--rg` - Resource group
- `--config` - Config file path

## Implementation Strategy

### Phase 1: Architecture Planning ✓
- [x] Create implementation plan document
- [x] Review existing SSH infrastructure (remote_exec.py, vm_connector.py)
- [x] Define API and interfaces

### Phase 2: Write FAILING Tests (RED)
Create `tests/unit/test_log_viewer.py` with tests for:
- [ ] Log type enumeration
- [ ] System log retrieval via SSH
- [ ] Boot log retrieval
- [ ] Application log retrieval
- [ ] Time-based filtering
- [ ] Real-time log following
- [ ] Error handling (VM not found, not running, SSH failures)
- [ ] Line limiting
- [ ] Integration with VMManager and SSH

### Phase 3: Implement Feature (GREEN)
Implement `src/azlin/log_viewer.py`:
- [ ] LogType enum
- [ ] LogViewerError exception
- [ ] LogViewer class with all methods
- [ ] SSH command building for journalctl
- [ ] Time parsing utilities
- [ ] Log streaming support

### Phase 4: CLI Integration
Update `src/azlin/cli.py`:
- [ ] Add `logs` command with all options
- [ ] Integrate with LogViewer
- [ ] Handle VM selection
- [ ] Format output for terminal
- [ ] Add help documentation

### Phase 5: Refactor (REFACTOR)
- [ ] Review code for DRY violations
- [ ] Extract reusable utilities
- [ ] Optimize SSH calls
- [ ] Add docstrings
- [ ] Clean up any temporary code

### Phase 6: Run Linter
- [ ] Run pytest on new tests
- [ ] Run pre-commit hooks / linters
- [ ] Fix any linting issues
- [ ] Ensure all tests pass

### Phase 7: Commit
- [ ] Stage all changes
- [ ] Commit with message: "feat: Add azlin logs command for VM log viewing (#21)"
- [ ] Verify commit

### Phase 8: Documentation
- [ ] Create IMPLEMENTATION_COMPLETE_21.md
- [ ] Document implementation details
- [ ] Add examples
- [ ] Note any limitations

## Technical Details

### SSH Commands for Log Retrieval

**System Logs**:
```bash
journalctl --no-pager -n <lines> --since '<time>'
```

**Boot Logs**:
```bash
journalctl --no-pager -b --since '<time>'
```

**Kernel Logs**:
```bash
journalctl --no-pager -k -n <lines> --since '<time>'
```

**Application Logs** (example):
```bash
journalctl --no-pager -u <service> -n <lines> --since '<time>'
```

**Follow Logs**:
```bash
journalctl -f --no-pager --since '<time>'
```

### Time Format Parsing
Support formats:
- Relative: "1 hour ago", "30 minutes", "2 days"
- Absolute: "2024-01-01", "2024-01-01 14:30:00"
- journalctl native: "1 hour ago", "yesterday", "today"

### Dependencies
- Existing: `remote_exec.py` - RemoteExecutor for SSH commands
- Existing: `vm_manager.py` - VMManager for VM lookup
- Existing: `vm_connector.py` - For VM/IP resolution
- Existing: `modules.ssh_connector` - SSHConfig, SSHConnector

### Error Handling
- VM not found → VMManagerError
- VM not running → Clear error message
- SSH timeout → Timeout error with retry suggestion
- Invalid time format → Parse error with examples
- No logs available → Informative message

## Test Strategy

### Unit Tests
File: `tests/unit/test_log_viewer.py`

**Test Cases**:
1. `test_get_system_logs_success()` - Mock SSH, verify journalctl command
2. `test_get_boot_logs_success()` - Mock SSH, verify boot log command
3. `test_get_app_logs_success()` - Mock SSH, verify app log command
4. `test_follow_logs()` - Mock SSH streaming
5. `test_filter_by_time_relative()` - Test "1 hour" parsing
6. `test_filter_by_time_absolute()` - Test date parsing
7. `test_vm_not_running()` - Error handling
8. `test_ssh_timeout()` - Timeout handling
9. `test_line_limiting()` - Verify -n parameter
10. `test_invalid_log_type()` - Error on invalid type

### Integration Points
- Mock `VMManager.get_vm()` for VM lookup
- Mock `SSHConnector.execute_remote_command()` for command execution
- Mock `RemoteExecutor` for parallel execution

## Success Criteria
- [x] Implementation plan created
- [ ] All unit tests pass
- [ ] CLI command functional
- [ ] Can view system logs
- [ ] Can view boot logs
- [ ] Can follow logs in real-time
- [ ] Time filtering works
- [ ] Proper error messages
- [ ] Code linted and formatted
- [ ] Committed with issue reference
- [ ] Summary document created

## Timeline
Estimated: 2-3 hours
- Planning: 15 min ✓
- Tests: 45 min
- Implementation: 60 min
- Integration: 30 min
- Linting/Cleanup: 15 min
- Documentation: 15 min
