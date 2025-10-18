# Design Document: azlin update Command

## Overview
The `azlin update` command updates all development tools installed on an azlin VM.

## Architecture

### Module: `src/azlin/vm_updater.py`

**Purpose**: Core logic for updating tools on VMs

**Classes**:

1. **`UpdateResult`** (dataclass)
   - `tool_name: str` - Name of the tool updated
   - `success: bool` - Whether update succeeded
   - `message: str` - Success/error message
   - `duration: float` - Time taken in seconds

2. **`VMUpdateSummary`** (dataclass)
   - `vm_name: str` - VM identifier
   - `total_updates: int` - Total tools attempted
   - `successful: List[UpdateResult]` - Successful updates
   - `failed: List[UpdateResult]` - Failed updates
   - `total_duration: float` - Total time taken

   Properties:
   - `success_count` - Count of successful updates
   - `failure_count` - Count of failed updates
   - `all_succeeded` - True if all succeeded
   - `any_failed` - True if any failed

3. **`VMUpdater`**

   Methods:
   - `update_vm(ssh_config: SSHConfig) -> VMUpdateSummary`
     - Main entry point to update all tools on a VM
     - Returns summary of all update attempts

   - `_update_system_packages() -> UpdateResult`
     - Updates apt packages
     - Command: `sudo apt update && sudo apt upgrade -y`

   - `_update_azure_cli() -> UpdateResult`
     - Updates Azure CLI
     - Command: `az upgrade --yes`

   - `_update_github_cli() -> UpdateResult`
     - Updates GitHub CLI extensions
     - Command: `gh extension upgrade --all`

   - `_update_npm() -> UpdateResult`
     - Updates npm itself
     - Command: `npm install -g npm@latest`

   - `_update_npm_packages() -> UpdateResult`
     - Updates global npm packages (copilot, codex, claude-code)
     - Command: `npm update -g`

   - `_update_rust() -> UpdateResult`
     - Updates Rust toolchain
     - Command: `rustup update`

   - `_update_golang() -> UpdateResult`
     - Checks and updates Go
     - Downloads latest if newer version available

   - `_update_dotnet() -> UpdateResult`
     - Checks and updates .NET
     - Downloads latest RC if newer version available

   - `_update_astral_uv() -> UpdateResult`
     - Updates uv snap package
     - Command: `snap refresh astral-uv`

### CLI Integration: `src/azlin/cli.py`

**Command**: `azlin update <vm_identifier>`

**Parameters**:
- `vm_identifier: str` - VM name, session name, or IP
- `--resource-group, -g: str` - Resource group (optional)
- `--config: str` - Config file path (optional)
- `--timeout: int` - Timeout per update in seconds (default: 300)

**Flow**:
1. Resolve VM identifier (session name → VM name, or direct VM name)
2. Get VM info from Azure
3. Build SSH config
4. Create VMUpdater instance
5. Execute update
6. Display progress with ProgressDisplay
7. Show summary at end

## Update Sequence

Updates run **sequentially** because:
1. Some updates may trigger system restarts or reload PATH
2. apt updates should complete before other package managers
3. Easier to troubleshoot failures
4. Lower risk of resource contention

**Order**:
1. System packages (apt) - Foundation, affects other tools
2. Azure CLI - Independent
3. GitHub CLI - Independent
4. npm - Required before npm packages
5. npm packages - Depends on npm
6. Rust - Independent
7. Go - Independent
8. .NET - Independent
9. astral-uv - Independent

## Error Handling

- Each update wrapped in try/except
- Failures don't stop subsequent updates
- All results collected and reported
- Exit codes:
  - 0: All updates succeeded
  - 1: Partial success (some failed)
  - 2: Complete failure (all failed or connection error)

## Progress Display

Use existing `ProgressDisplay` module:
- Show current tool being updated
- Display progress percentage
- Estimated time remaining
- Success/failure indicators (✓/✗)

## Testing Strategy

### Unit Tests: `tests/unit/test_vm_updater.py`

1. Test each `_update_*` method in isolation
2. Mock SSH execution with various responses
3. Test error handling for each tool
4. Test UpdateResult and VMUpdateSummary dataclasses
5. Test update sequencing

### Integration Tests: `tests/integration/test_vm_updater_integration.py`

1. Test full update flow with mock SSH
2. Test session name resolution
3. Test partial failure scenarios
4. Test timeout handling

### Mock Strategy

- Mock `RemoteExecutor.execute_command`
- Return realistic output for each tool
- Simulate various failure scenarios

## Design Decisions

### Q: Should updates run sequentially or in parallel?
**A**: Sequential. Safer, easier to debug, some updates depend on others.

### Q: Should we support selective updates?
**A**: Not in v1. Keep it simple - update everything.

### Q: Should we add --dry-run?
**A**: Not in v1. Can add later if needed.

### Q: Should we log update results?
**A**: Use existing logging infrastructure. INFO level for success, ERROR for failures.

## Security Considerations

- All commands use `RemoteExecutor` (already sanitized)
- No shell=True
- No user input in commands
- Use existing SSH key authentication
- Timeouts enforced on all operations

## Philosophy Alignment

✓ **Ruthless Simplicity**: Single-purpose module, clear responsibilities
✓ **Bricks & Studs**: Reuses existing modules (RemoteExecutor, ProgressDisplay, SSHConnector)
✓ **Zero BS**: No TODOs, no stubs, no placeholders - complete implementation
✓ **Test-Driven**: Write tests first, then implement
