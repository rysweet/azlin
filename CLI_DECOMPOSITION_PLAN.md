# CLI Decomposition Plan - Issue #423

## Current State
- **cli.py**: 8,954 lines (331KB)
- **24 inline commands** still in cli.py
- **6 command groups** still in cli.py
- **Already extracted**: 11 command modules in `src/azlin/commands/`

## Analysis: Commands Remaining in cli.py

### Main Commands (24 total)
1. `help` (line 2352) - Help system
2. `new` (line 2599) - Provision new VM **[CRITICAL]**
3. `vm` (line 2757) - Alias for new **[CRITICAL]**
4. `create` (line 2779) - Alias for new **[CRITICAL]**
5. `list` (line 3062) - List VMs **[CRITICAL]**
6. `session` (line 3440) - Session management
7. `w` (line 3575) - Run 'w' on all VMs
8. `top` (line 3653) - Distributed monitoring
9. `os-update` (line 3762) - Update OS on VM
10. `kill` (line 3819) - Delete single VM
11. `destroy` (line 4044) - Alias for kill
12. `killall` (line 4151) - Delete multiple VMs
13. `prune` (line 4224) - Cleanup orphaned resources
14. `ps` (line 4354) - Run ps on all VMs
15. `cost` (line 4433) - Cost estimates
16. `connect` (line 4745) - Connect to VM via SSH **[CRITICAL]**
17. `code` (line 4954) - Launch VSCode
18. `update` (line 5115) - Update VM tools
19. `stop` (line 5249) - Stop VM
20. `start` (line 5303) - Start VM
21. `sync` (line 5518) - Sync home directory
22. `cp` (line 5579) - Copy files to/from VM
23. `clone` (line 5830) - Clone VM
24. `status` (line 6161) - Detailed VM status
25. `do` (line 6593) - Natural language commands
26. `doit-old` (line 6687) - Legacy doit implementation

### Command Groups (6 total)
1. `ip` (line 6241) - IP diagnostics
2. `batch` (line 7218) - Batch operations
3. `keys` (line 7270) - SSH key management
4. `template` (line 7279) - Template management
5. `snapshot` (line 7317) - Snapshot operations
6. `env` (line 8541) - Environment variable management

## Extraction Strategy

### Phase 1: Core VM Lifecycle (Highest Priority)
**Module**: `src/azlin/commands/vm_lifecycle.py` (~1000 lines)
**Commands**:
- `new` (line 2599) + CLIOrchestrator class (lines 168-1990) - **CRITICAL PATH**
- `vm` (line 2757) - alias
- `create` (line 2779) - alias
- `start` (line 5303)
- `stop` (line 5249)
- `kill` (line 3819)
- `destroy` (line 4044)
- `clone` (line 5830)

**Rationale**: These are the most-used commands and form the core value proposition

### Phase 2: VM Discovery & Monitoring
**Module**: `src/azlin/commands/vm_discovery.py` (~800 lines)
**Commands**:
- `list` (line 3062) - **CRITICAL PATH**
- `status` (line 6161)
- `session` (line 3440)
- `w` (line 3575)
- `top` (line 3653)
- `ps` (line 4354)

**Rationale**: Related to finding and monitoring VMs

### Phase 3: Connectivity & File Transfer
**Module**: `src/azlin/commands/connectivity.py` (~700 lines)
**Commands**:
- `connect` (line 4745) - **CRITICAL PATH**
- `code` (line 4954)
- `cp` (line 5579)
- `sync` (line 5518)

**Rationale**: All about connecting to and transferring data with VMs

### Phase 4: Administrative Commands
**Module**: `src/azlin/commands/admin.py` (~600 lines)
**Commands**:
- `prune` (line 4224)
- `killall` (line 4151)
- `update` (line 5115)
- `os-update` (line 3762)
- `cost` (line 4433)

**Rationale**: Administrative and maintenance operations

### Phase 5: Command Groups
**Modules**: Extract each group to its own file
1. `src/azlin/commands/ip_diagnostics.py` (~300 lines)
   - `ip` group (line 6241)

2. `src/azlin/commands/batch_ops.py` (~500 lines)
   - `batch` group (line 7218)

3. `src/azlin/commands/keys.py` (~400 lines)
   - `keys` group (line 7270)

4. `src/azlin/commands/templates.py` (~400 lines)
   - `template` group (line 7279)

5. `src/azlin/commands/snapshots.py` (~500 lines)
   - `snapshot` group (line 7317)

6. `src/azlin/commands/environment.py` (~400 lines)
   - `env` group (line 8541)

### Phase 6: Special Commands
**Module**: `src/azlin/commands/nlp.py` (~200 lines)
**Commands**:
- `do` (line 6593) - Natural language interface
- `doit-old` (line 6687) - Legacy implementation (mark for deprecation)

**Module**: `src/azlin/commands/help.py` (~100 lines)
**Commands**:
- `help` (line 2352) - Help system

## Refactored cli.py Structure

After extraction, cli.py should contain (~400-500 lines):
1. Imports (50 lines)
2. Main group definition (30 lines)
3. Helper functions for auth, config loading (100 lines)
4. Command registration (30 lines)
5. Legacy support code if needed (50 lines)

## Success Metrics
- [ ] cli.py reduced from 8,954 to < 500 lines (94% reduction)
- [ ] All 24 commands extracted to logical modules
- [ ] All 6 command groups extracted
- [ ] Each module < 1000 lines
- [ ] 100% backward compatibility (no breaking changes)
- [ ] All tests pass
- [ ] 90%+ test coverage for new modules

## Implementation Order
1. ✅ Analyze and create this plan
2. ✅ Setup worktree
3. Extract Phase 1 (VM Lifecycle) - Start with `list` and `connect` as they're most critical
4. Extract Phase 2 (VM Discovery)
5. Extract Phase 3 (Connectivity)
6. Extract Phase 4 (Admin)
7. Extract Phase 5 (Command Groups)
8. Extract Phase 6 (Special Commands)
9. Refactor cli.py to router-only
10. Write comprehensive tests
11. Run full test suite
12. Manual testing

## Risk Mitigation
- **Shared Dependencies**: Many commands share helper functions - extract to `cli_helpers.py` first
- **Import Cycles**: Carefully manage imports to avoid circular dependencies
- **State Management**: Ensure context passing works correctly
- **Testing**: Write tests for each module before marking complete
- **Incremental Commits**: Commit after each phase for easy rollback

## Helper Function Extraction (Pre-req)

These helper functions are used by multiple commands and should be extracted to `cli_helpers.py` or kept as shared utilities:

1. `show_interactive_menu()` (line 2064)
2. `generate_vm_name()` (line 2117)
3. `execute_command_on_vm()` (line 2095)
4. `select_vm_for_command()` (line 2078)
5. `_auto_sync_home_directory()` (line 2043)
6. `_collect_tmux_sessions()` (line 2801)
7. `_handle_multi_context_list()` (line 2881)
8. `_interactive_vm_selection()` (line 4481)
9. `_resolve_vm_identifier()` (line 4550)
10. `_verify_vm_exists()` (line 4601)
11. `_resolve_tmux_session()` (line 4620)
12. `_try_fetch_key_from_vault()` (line 4686)
13. `_cleanup_key_from_vault()` (line 4711)
14. `_get_ssh_config_for_vm()` (multiple references)

These should remain in cli.py or move to a shared helpers module that all command modules import.

## Notes
- The existing `commands/` directory already has 11 modules, so we follow the established pattern
- CLIOrchestrator class (1822 lines!) is part of `new` command and must be carefully extracted
- Many commands share utility functions - need careful dependency management
- Some commands have complex logic (e.g., `new` has 158 lines, but CLIOrchestrator is 1822 lines)
