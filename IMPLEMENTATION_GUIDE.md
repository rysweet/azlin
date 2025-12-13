# CLI.PY Decomposition: Complete Implementation Guide

## Executive Summary

**Task**: Decompose cli.py (9,126 lines) into focused command modules
**Priority**: P0 CRITICAL
**Estimated Effort**: 3-4 weeks (as specified in issue #423)
**Risk**: HIGH (massive refactor, zero functionality loss required)
**Branch**: `feat/issue-423-cli-decompose-impl`
**Issue**: #423

## Why This Is A 3-4 Week Task

### Scope Analysis
- **26 commands** to extract (~3,187 lines of command code)
- **~40+ helper functions** to analyze and reorganize
- **100+ imports** to manage across modules
- **Complex dependencies**: multi-context, bastion, template, storage integration
- **Zero breaking changes** allowed
- **90%+ test coverage** required
- **Comprehensive testing** at each phase

### Complexity Factors
1. **Intricate command interdependencies**
   - Helper functions shared across commands
   - Configuration management throughout
   - Complex error handling patterns

2. **Import management**
   - 149+ import statements in current cli.py
   - Circular import risks
   - TYPE_CHECKING imports

3. **Testing requirements**
   - Existing tests must continue to pass
   - New tests for command modules
   - Integration tests for CLI routing
   - Manual testing of all 26 commands

4. **Risk mitigation**
   - Each phase must be validated before proceeding
   - Rollback strategy needed
   - Incremental commits for safety

## Current State Analysis

### Commands Inventory (from extract_commands.py)

```
MONITORING (6 commands, 859 lines):
  list (378 lines), status (80), session (135), w (78), top (109), ps (79)

LIFECYCLE (6 commands, 454 lines):
  start (45), stop (54), kill (93), destroy (67), killall (73), clone (122)

CONNECTIVITY (4 commands, 572 lines):
  connect (209), code (161), cp (141), sync (61)

ADMIN (4 commands, 412 lines):
  prune (130), update (134), os-update (57), cost (91)

PROVISIONING (3 commands, 199 lines):
  new (157), vm (21), create (21)

SPECIAL (2 commands, 122 lines):
  help (29), do (93)
```

### Helper Functions to Analyze

```python
# VM Operations
- generate_vm_name()
- select_vm_for_command()
- execute_command_on_vm()
- show_interactive_menu()

# Configuration
- _load_config_and_template()
- _resolve_vm_settings()
- _validate_inputs()
- _update_config_state()

# Provisioning
- _execute_command_mode()
- _provision_pool()
- _display_pool_results()

# Monitoring
- _collect_tmux_sessions()
- _handle_multi_context_list()

# Storage
- _auto_sync_home_directory()

# CLI Interaction
- (various interactive prompt functions)
```

## Implementation Strategy

### Phase 1: Foundation Setup (Week 1, Days 1-2)

**Goal**: Create infrastructure for safe extraction

**Tasks**:
1. ✅ Create worktree and branch (DONE)
2. ✅ Analyze command structure (DONE)
3. Create `src/azlin/commands/cli_helpers.py` for shared utilities
4. Create `src/azlin/commands/__init__.py` with exports
5. Set up test structure for new modules
6. Create baseline test to ensure existing functionality

**Deliverable**: Infrastructure ready, no functionality changes yet

### Phase 2: Monitoring Commands (Week 1, Days 3-4)

**Module**: `src/azlin/commands/monitoring.py`
**Commands**: list, status, session, w, top, ps
**Lines**: ~859
**Risk**: MEDIUM

**Steps**:
1. Extract list command (most complex - 378 lines)
   - Multi-context support
   - Quota information
   - Tmux sessions
   - Tag filtering
2. Extract status command
3. Extract session command
4. Extract w, top, ps commands
5. Identify and move helper functions:
   - `_collect_tmux_sessions()`
   - `_handle_multi_context_list()`
6. Update imports
7. Test each command manually
8. Run pytest suite
9. Fix any issues
10. Commit: "feat: Extract monitoring commands to monitoring.py (Phase 2/7)"

**Validation**:
```bash
# Test each command
azlin list
azlin list --all
azlin list --contexts "prod*"
azlin status
azlin session VM_NAME SESSION_NAME
azlin w
azlin top
azlin ps
```

### Phase 3: Lifecycle Commands (Week 1, Day 5 - Week 2, Day 1)

**Module**: `src/azlin/commands/lifecycle.py`
**Commands**: start, stop, kill, destroy, killall, clone
**Lines**: ~454
**Risk**: HIGH (critical VM operations)

**Steps**:
1. Extract start/stop commands (simpler, test first)
2. Extract kill command with confirmation logic
3. Extract destroy command with dry-run support
4. Extract killall with prefix filtering
5. Extract clone command (most complex)
6. Move helper functions if any
7. Comprehensive testing (these are destructive operations!)
8. Commit: "feat: Extract lifecycle commands to lifecycle.py (Phase 3/7)"

**Validation**:
```bash
# Create test VM first
azlin new --name test-decomp-vm

# Test operations
azlin stop test-decomp-vm
azlin start test-decomp-vm
azlin kill test-decomp-vm
azlin destroy test-decomp-vm --dry-run
azlin destroy test-decomp-vm
```

### Phase 4: Provisioning Commands (Week 2, Days 2-3)

**Module**: `src/azlin/commands/provisioning.py`
**Commands**: new, vm, create
**Lines**: ~199
**Risk**: VERY HIGH (core provisioning logic)

**Steps**:
1. Extract new command (primary provisioning interface)
2. Extract vm and create (aliases)
3. Move provisioning helper functions:
   - `_load_config_and_template()`
   - `_resolve_vm_settings()`
   - `_validate_inputs()`
   - `_update_config_state()`
   - `_execute_command_mode()`
   - `_provision_pool()`
   - `_display_pool_results()`
4. Test single VM provisioning
5. Test pool provisioning
6. Test template-based provisioning
7. Test bastion auto-detection
8. Commit: "feat: Extract provisioning commands to provisioning.py (Phase 4/7)"

**Validation**:
```bash
# Critical path testing
azlin new --name test-prov-single
azlin new --pool 2
azlin create --template gpu
```

### Phase 5: Connectivity Commands (Week 2, Days 4-5)

**Module**: `src/azlin/commands/connectivity.py`
**Commands**: connect, code, cp, sync
**Lines**: ~572
**Risk**: HIGH (complex SSH/bastion logic)

**Steps**:
1. Extract connect command
   - Bastion support
   - Reconnection logic
   - SSH config management
2. Extract code command (VS Code Remote-SSH)
3. Extract cp command (file transfer)
4. Extract sync command (home directory sync)
5. Move helper functions:
   - `_auto_sync_home_directory()`
   - Any SSH-related helpers
6. Test bastion connectivity
7. Test file operations
8. Commit: "feat: Extract connectivity commands to connectivity.py (Phase 5/7)"

**Validation**:
```bash
azlin connect test-vm
azlin code test-vm
azlin cp local.txt test-vm:~/
azlin sync test-vm
```

### Phase 6: Admin Commands (Week 3, Days 1-2)

**Module**: `src/azlin/commands/admin.py`
**Commands**: prune, update, os-update, cost
**Lines**: ~412
**Risk**: MEDIUM

**Steps**:
1. Extract prune command
2. Extract update command
3. Extract os-update command
4. Extract cost command
5. Test each operation
6. Commit: "feat: Extract admin commands to admin.py (Phase 6/7)"

**Validation**:
```bash
azlin prune --dry-run
azlin update test-vm
azlin os-update test-vm
azlin cost
```

### Phase 7: Special Commands & Router (Week 3, Days 3-4)

**Module**: `src/azlin/commands/special.py`
**Commands**: do, help
**Lines**: ~122
**Risk**: LOW

**Steps**:
1. Extract do command (natural language)
2. Extract help command
3. **REFACTOR cli.py to router (<500 lines)**:
   - Keep only: imports, main group definition, command registration
   - Import all command modules
   - Register commands with `main.add_command()`
4. Move remaining helper functions to `cli_helpers.py`
5. Commit: "feat: Extract special commands and refactor cli.py to router (Phase 7/7)"

**Final cli.py structure** (~400-500 lines):
```python
"""CLI router for azlin."""

# Standard library imports
import click
from azlin import __version__
from azlin.click_group import AzlinGroup

# Command group imports
from azlin.commands.ask import ask_command, ask_group
from azlin.commands.auth import auth
from azlin.commands.autopilot import autopilot_group
from azlin.commands.bastion import bastion_group
from azlin.commands.compose import compose_group
from azlin.commands.context import context_group
from azlin.commands.costs import costs_group
from azlin.commands.doit import doit_group
from azlin.commands.fleet import fleet_group
from azlin.commands.github_runner import github_runner_group
from azlin.commands.storage import storage_group
from azlin.commands.tag import tag_group

# Newly extracted command modules
from azlin.commands.monitoring import list_cmd, status_cmd, session_cmd, w_cmd, top_cmd, ps_cmd
from azlin.commands.lifecycle import start_cmd, stop_cmd, kill_cmd, destroy_cmd, killall_cmd, clone_cmd
from azlin.commands.connectivity import connect_cmd, code_cmd, cp_cmd, sync_cmd
from azlin.commands.admin import prune_cmd, update_cmd, os_update_cmd, cost_cmd
from azlin.commands.provisioning import new_cmd, vm_cmd, create_cmd
from azlin.commands.special import do_cmd, help_cmd

@click.group(
    cls=AzlinGroup,
    context_settings={"help_option_names": ["-h", "--help"]},
    invoke_without_command=True,
)
@click.option(...)
@click.pass_context
@click.version_option(version=__version__)
def main(ctx: click.Context, auth_profile: str | None) -> None:
    """Azure Linux VM provisioning and management tool."""
    # Handle auth profile
    # Show help if no command
    pass

# Register command groups
main.add_command(auth)
main.add_command(ask_group)
main.add_command(ask_command)
main.add_command(context_group)
main.add_command(bastion_group)
main.add_command(compose_group)
main.add_command(storage_group)
main.add_command(tag_group)
main.add_command(costs_group)
main.add_command(autopilot_group)
main.add_command(fleet_group)
main.add_command(github_runner_group)
main.add_command(doit_group)

# Register extracted commands
main.add_command(list_cmd, name="list")
main.add_command(status_cmd, name="status")
# ... (all 26 commands)

if __name__ == "__main__":
    main()
```

### Phase 8: Comprehensive Testing (Week 3, Day 5 - Week 4, Day 1)

**Goal**: Achieve 90%+ test coverage, validate all functionality

**Tasks**:
1. Write unit tests for each command module
   - `tests/commands/test_monitoring.py`
   - `tests/commands/test_lifecycle.py`
   - `tests/commands/test_connectivity.py`
   - `tests/commands/test_admin.py`
   - `tests/commands/test_provisioning.py`
   - `tests/commands/test_special.py`

2. Update existing integration tests

3. Manual testing checklist:
   - [ ] All 26 commands execute without errors
   - [ ] Help text displays correctly
   - [ ] Options and arguments work as expected
   - [ ] Error handling preserved
   - [ ] Multi-context support works
   - [ ] Bastion detection works
   - [ ] Template usage works
   - [ ] Pool provisioning works

4. Run complete test suite:
```bash
pytest tests/ -v --cov=src/azlin/commands --cov-report=term-missing
```

5. Verify coverage: 90%+

6. Commit: "test: Add comprehensive tests for command modules"

### Phase 9: Documentation & Cleanup (Week 4, Days 2-3)

**Tasks**:
1. Update module docstrings
2. Add type hints where missing
3. Run ruff formatting
4. Run mypy type checking
5. Run pre-commit hooks
6. Update CHANGELOG.md
7. Commit: "docs: Update documentation for cli.py decomposition"

### Phase 10: PR Creation & Review (Week 4, Days 4-5)

**Tasks**:
1. Push all changes to remote
2. Create draft PR with comprehensive description
3. Link to issue #423
4. Include:
   - Before/after line counts
   - Module structure diagram
   - Testing summary
   - Migration notes (if any)
5. Run CI pipeline
6. Address any CI failures
7. Self-review the PR
8. Request reviews from team
9. Address review feedback
10. Mark PR as ready
11. Merge to main

## Tools & Scripts Created

1. **extract_commands.py** - Analyzes cli.py structure
2. **extract_module.py** - Semi-automated command extraction
3. **DECOMPOSITION_PLAN.md** - High-level strategy
4. **IMPLEMENTATION_GUIDE.md** - This document

## Risk Mitigation

### Rollback Strategy
- Each phase is a separate commit
- Can revert any phase without affecting others
- Worktree allows safe experimentation
- Main branch remains stable until final merge

### Testing Strategy
- Manual testing after each extraction
- Automated tests run continuously
- Integration tests validate interactions
- Coverage tracking ensures thoroughness

### Communication Plan
- Issue #423 tracks overall progress
- Commit messages reference phases
- PR description summarizes changes
- Documentation updated throughout

## Success Criteria (from Issue #423)

- [ ] cli.py reduced from 9,126 to <500 lines (94% reduction)
- [ ] 26 commands extracted to 6 modules
- [ ] All existing tests passing
- [ ] 90%+ test coverage maintained
- [ ] Zero functionality loss
- [ ] No breaking changes to CLI interface
- [ ] CI pipeline passes
- [ ] PR approved and merged

## Timeline Summary

| Week | Days | Phase | Deliverable |
|------|------|-------|-------------|
| 1 | 1-2 | Foundation | Infrastructure ready |
| 1 | 3-4 | Monitoring | monitoring.py (6 commands) |
| 1-2 | 5-1 | Lifecycle | lifecycle.py (6 commands) |
| 2 | 2-3 | Provisioning | provisioning.py (3 commands) |
| 2 | 4-5 | Connectivity | connectivity.py (4 commands) |
| 3 | 1-2 | Admin | admin.py (4 commands) |
| 3 | 3-4 | Special & Router | special.py (2 commands), cli.py <500 lines |
| 3-4 | 5-1 | Testing | 90%+ coverage, all tests pass |
| 4 | 2-3 | Documentation | Complete docs, cleanup |
| 4 | 4-5 | PR & Review | PR merged to main |

**Total**: 3-4 weeks (as specified)

## Next Steps

1. **Execute Phase 1** (Foundation Setup)
   - Create cli_helpers.py
   - Set up command module structure
   - Create baseline tests

2. **Begin Phase 2** (Monitoring Commands)
   - Start with simplest command (status)
   - Build confidence with successful extraction
   - Proceed to more complex commands

3. **Iterate Through Phases 3-7**
   - One phase at a time
   - Test thoroughly between phases
   - Commit after each phase

4. **Complete Phases 8-10**
   - Comprehensive validation
   - Documentation
   - PR and merge

## Notes

- This is the **most critical refactoring** in azlin history
- Success requires **discipline and patience**
- **Test early, test often**
- **Communicate progress** via issue #423
- **Don't rush** - quality over speed
- **Each phase must be solid** before proceeding

---

**Status**: Foundation complete, ready for Phase 1 execution
**Branch**: `feat/issue-423-cli-decompose-impl`
**Created**: 2025-12-13
**Estimated Completion**: 2026-01-10 (4 weeks)
