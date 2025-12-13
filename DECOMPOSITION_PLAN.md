# CLI.PY Decomposition Implementation Plan

## Current State
- **cli.py**: 9,126 lines (31% of codebase)
- **Commands**: 26 inline commands
- **Target**: <500 lines (routing only)
- **Goal**: 94% reduction

## Analysis Results

### Commands by Category (from extract_commands.py)

**MONITORING (6 commands, ~859 lines)**
- list (378 lines) - List VMs with quota/tmux info
- status (80 lines) - Show VM status
- session (135 lines) - Manage session names
- w (78 lines) - Run 'w' command on all VMs
- top (109 lines) - Live distributed metrics
- ps (79 lines) - Process listing

**LIFECYCLE (6 commands, ~454 lines)**
- start (45 lines) - Start VM
- stop (54 lines) - Stop VM
- kill (93 lines) - Kill single VM
- destroy (67 lines) - Destroy VM with confirmation
- killall (73 lines) - Kill multiple VMs
- clone (122 lines) - Clone VM

**CONNECTIVITY (4 commands, ~572 lines)**
- connect (209 lines) - SSH connection with reconnection
- code (161 lines) - VS Code Remote-SSH
- cp (141 lines) - File copy via SSH
- sync (61 lines) - Sync home directory

**ADMIN (4 commands, ~412 lines)**
- prune (130 lines) - Remove old VMs
- update (134 lines) - Update azlin on VM
- os-update (57 lines) - OS package updates
- cost (91 lines) - Cost tracking

**PROVISIONING (3 commands, ~199 lines)**
- new (157 lines) - Provision new VM
- vm (21 lines) - Alias for new
- create (21 lines) - Alias for new

**SPECIAL (2 commands, ~122 lines)**
- help (29 lines) - Enhanced help
- do (93 lines) - Natural language command

**UNCATEGORIZED (1 command, ~569 lines)**
- doit-old (569 lines) - Legacy implementation (commented out)

## Implementation Phases

### Phase 1: Monitoring Commands → `src/azlin/commands/monitoring.py`
**Lines**: ~859
**Commands**: list, status, session, w, top, ps
**Dependencies**: QuotaManager, TmuxSessionExecutor, WCommandExecutor, PSCommandExecutor, TagManager, VMManager
**Risk**: MEDIUM (complex list command with multi-context support)

### Phase 2: Lifecycle Commands → `src/azlin/commands/lifecycle.py`
**Lines**: ~454
**Commands**: start, stop, kill, destroy, killall, clone
**Dependencies**: VMLifecycleManager, VMManager, VMProvisioner
**Risk**: MEDIUM (critical VM operations)

### Phase 3: Connectivity Commands → `src/azlin/commands/connectivity.py`
**Lines**: ~572
**Commands**: connect, code, cp, sync
**Dependencies**: VMConnector, VSCodeLauncher, FileTransfer, HomeSyncManager
**Risk**: HIGH (complex SSH/bastion logic)

### Phase 4: Admin Commands → `src/azlin/commands/admin.py`
**Lines**: ~412
**Commands**: prune, update, os-update, cost
**Dependencies**: PruneManager, RemoteExecutor, OSUpdateExecutor, CostTracker
**Risk**: LOW (well-isolated operations)

### Phase 5: Provisioning Commands → `src/azlin/commands/provisioning.py`
**Lines**: ~199
**Commands**: new, vm, create
**Dependencies**: VMProvisioner, TemplateManager, BastionDetector
**Risk**: HIGH (core provisioning logic)

### Phase 6: Special Commands & Router Refactoring
**Lines**: ~122 + router refactoring
**Commands**: do, help
**Dependencies**: IntentParser, CommandExecutor
**Risk**: LOW (simple commands)
**Router**: Reduce cli.py to <500 lines (imports + Click setup + command registration)

## Extraction Strategy

### Step 1: Helper Functions
Identify and extract helper functions that don't depend on Click decorators:
- `_auto_sync_home_directory()`
- `show_interactive_menu()`
- `generate_vm_name()`
- `execute_command_on_vm()`
- `select_vm_for_command()`
- `_collect_tmux_sessions()`
- `_handle_multi_context_list()`
- etc.

### Step 2: Command Extraction
For each phase:
1. Create new module file
2. Copy command function + decorators
3. Copy any command-specific helper functions
4. Add necessary imports
5. Keep original function names for Click registration
6. Test in isolation

### Step 3: Router Update
Update cli.py to:
1. Import command modules
2. Register commands with `main.add_command()`
3. Remove extracted code
4. Keep only: imports, main group definition, command registration

### Step 4: Testing
For each phase:
1. Run existing tests
2. Manual CLI testing
3. Verify no regressions
4. Check test coverage

## Critical Considerations

### 1. Import Management
- Each module needs full import chain
- Avoid circular imports
- Keep TYPE_CHECKING imports separate

### 2. Helper Function Placement
- Shared helpers → `cli_helpers.py`
- Command-specific helpers → stay with command

### 3. Click Registration
- Commands registered via `main.add_command()`
- Preserve command names and aliases
- Maintain option/argument order

### 4. Backward Compatibility
- All commands work identically
- No breaking changes to CLI interface
- Same error messages and behavior

## Success Criteria

- [ ] cli.py < 500 lines (94% reduction)
- [ ] 26 commands extracted to 6 modules
- [ ] All tests passing
- [ ] 90%+ test coverage maintained
- [ ] Zero functionality loss
- [ ] No breaking changes
- [ ] CI passes
- [ ] PR merged

## File Structure (Final)

```
src/azlin/
├── cli.py                      # <500 lines (router only)
├── commands/
│   ├── __init__.py             # Command exports
│   ├── monitoring.py           # ~859 lines (6 commands)
│   ├── lifecycle.py            # ~454 lines (6 commands)
│   ├── connectivity.py         # ~572 lines (4 commands)
│   ├── admin.py                # ~412 lines (4 commands)
│   ├── provisioning.py         # ~199 lines (3 commands)
│   ├── special.py              # ~122 lines (2 commands + do)
│   └── cli_helpers.py          # Shared helper functions
```

## Execution Timeline

**Phase 1-2**: ~2 hours (monitoring + lifecycle)
**Phase 3**: ~1.5 hours (connectivity - complex)
**Phase 4**: ~1 hour (admin - simpler)
**Phase 5**: ~1.5 hours (provisioning - complex)
**Phase 6**: ~1 hour (special + router refactoring)
**Testing**: ~2 hours (comprehensive validation)
**Total**: ~9-10 hours for complete implementation
