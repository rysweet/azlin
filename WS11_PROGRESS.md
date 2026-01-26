# WS11: CLI.PY Decomposition - Progress Tracker

**Issue**: #423 - Decompose cli.py Monolith (9,126 lines)
**Priority**: P0 CRITICAL
**Status**: IN PROGRESS - Foundation Complete
**Branch**: `feat/issue-423-cli-decompose-impl`
**Estimated Effort**: 3-4 weeks
**Started**: 2025-12-13

## Executive Summary

This is the final remaining P0 CRITICAL workstream for azlin. The cli.py file has grown to 9,126 lines (31% of the entire codebase) and blocks parallel development. This decomposition will:

- **Reduce cli.py from 9,126 → <500 lines** (94% reduction)
- **Extract 26 commands** into 6 focused modules
- **Enable parallel development** (no more merge conflicts)
- **Improve testability** (isolated command modules)
- **Maintain zero breaking changes** (all functionality preserved)

## Current State

### Before Decomposition
```
cli.py: 9,126 lines
├── 26 inline commands (~3,187 lines)
├── 40+ helper functions (~2,000 lines)
├── 149+ imports
├── Main group definition
└── Command registration
```

### Target State
```
cli.py: <500 lines (routing only)
└── Imports + main group + command registration

commands/
├── cli_helpers.py (~300 lines)
├── monitoring.py (~859 lines, 6 commands)
├── lifecycle.py (~454 lines, 6 commands)
├── connectivity.py (~572 lines, 4 commands)
├── admin.py (~412 lines, 4 commands)
├── provisioning.py (~199 lines, 3 commands)
└── special.py (~122 lines, 2 commands)
```

## Progress by Phase

### ✅ Phase 0: Planning & Analysis (COMPLETED)
**Duration**: 2 hours
**Status**: ✅ COMPLETE

**Deliverables**:
- ✅ Analyzed cli.py structure (9,126 lines, 26 commands)
- ✅ Created categorization script (`extract_commands.py`)
- ✅ Created extraction helper (`extract_module.py`)
- ✅ Documented decomposition plan (`DECOMPOSITION_PLAN.md`)
- ✅ Created comprehensive implementation guide (`IMPLEMENTATION_GUIDE.md`)
- ✅ Set up worktree: `feat/issue-423-cli-decompose-impl`
- ✅ Created foundation infrastructure:
  - `src/azlin/commands/cli_helpers.py` (starter framework)
  - `src/azlin/commands/README.md` (module documentation)
  - `WS11_PROGRESS.md` (this file)

**Artifacts Created**:
```
worktrees/feat-issue-423-cli-decompose-impl/
├── extract_commands.py          # Structure analysis script
├── extract_module.py             # Semi-automated extraction tool
├── DECOMPOSITION_PLAN.md         # High-level strategy
├── IMPLEMENTATION_GUIDE.md       # Detailed phase-by-phase guide
├── WS11_PROGRESS.md              # This progress tracker
└── src/azlin/commands/
    ├── cli_helpers.py            # Shared helper functions
    └── README.md                 # Module documentation
```

### 🔄 Phase 1: Monitoring Commands (IN PROGRESS)
**Target**: ~859 lines, 6 commands
**Status**: 🔄 READY TO START
**Estimated Duration**: 1 day

**Commands to Extract**:
- [ ] `list` (378 lines) - Most complex, has multi-context support
- [ ] `status` (80 lines)
- [ ] `session` (135 lines)
- [ ] `w` (78 lines)
- [ ] `top` (109 lines)
- [ ] `ps` (79 lines)

**Helper Functions**:
- [ ] `_collect_tmux_sessions()`
- [ ] `_handle_multi_context_list()`

**Testing Checklist**:
- [ ] `azlin list`
- [ ] `azlin list --all`
- [ ] `azlin list --contexts "prod*"`
- [ ] `azlin status`
- [ ] `azlin session VM_NAME SESSION_NAME`
- [ ] `azlin w`
- [ ] `azlin top`
- [ ] `azlin ps`

### ⏳ Phase 2: Lifecycle Commands (PENDING)
**Target**: ~454 lines, 6 commands
**Status**: ⏳ PENDING
**Risk**: HIGH (critical VM operations)

**Commands to Extract**:
- [ ] `start` (45 lines)
- [ ] `stop` (54 lines)
- [ ] `kill` (93 lines)
- [ ] `destroy` (67 lines)
- [ ] `killall` (73 lines)
- [ ] `clone` (122 lines)

### ⏳ Phase 3: Provisioning Commands (PENDING)
**Target**: ~199 lines, 3 commands
**Status**: ⏳ PENDING
**Risk**: VERY HIGH (core provisioning)

**Commands to Extract**:
- [ ] `new` (157 lines) - Primary provisioning interface
- [ ] `vm` (21 lines) - Alias
- [ ] `create` (21 lines) - Alias

**Helper Functions** (critical):
- [ ] `_load_config_and_template()`
- [ ] `_resolve_vm_settings()`
- [ ] `_validate_inputs()`
- [ ] `_update_config_state()`
- [ ] `_execute_command_mode()`
- [ ] `_provision_pool()`
- [ ] `_display_pool_results()`

### ⏳ Phase 4: Connectivity Commands (PENDING)
**Target**: ~572 lines, 4 commands
**Status**: ⏳ PENDING
**Risk**: HIGH (complex SSH/bastion logic)

**Commands to Extract**:
- [ ] `connect` (209 lines) - Most complex
- [ ] `code` (161 lines) - VS Code Remote-SSH
- [ ] `cp` (141 lines) - File transfer
- [ ] `sync` (61 lines) - Home directory sync

**Helper Functions**:
- [ ] `_auto_sync_home_directory()`

### ⏳ Phase 5: Admin Commands (PENDING)
**Target**: ~412 lines, 4 commands
**Status**: ⏳ PENDING
**Risk**: MEDIUM

**Commands to Extract**:
- [ ] `prune` (130 lines)
- [ ] `update` (134 lines)
- [ ] `os-update` (57 lines)
- [ ] `cost` (91 lines)

### ⏳ Phase 6: Special Commands & Router (PENDING)
**Target**: ~122 lines + router refactoring
**Status**: ⏳ PENDING
**Risk**: LOW

**Commands to Extract**:
- [ ] `do` (93 lines) - Natural language
- [ ] `help` (29 lines) - Enhanced help

**Router Refactoring**:
- [ ] Reduce cli.py to <500 lines
- [ ] Import all command modules
- [ ] Register commands with `main.add_command()`
- [ ] Remove extracted code
- [ ] Clean up remaining helpers

### ⏳ Phase 7: Comprehensive Testing (PENDING)
**Target**: 90%+ coverage
**Status**: ⏳ PENDING

**Test Modules to Create**:
- [ ] `tests/commands/test_monitoring.py`
- [ ] `tests/commands/test_lifecycle.py`
- [ ] `tests/commands/test_connectivity.py`
- [ ] `tests/commands/test_admin.py`
- [ ] `tests/commands/test_provisioning.py`
- [ ] `tests/commands/test_special.py`
- [ ] `tests/commands/test_cli_helpers.py`

**Coverage Goals**:
- [ ] Overall: 90%+
- [ ] monitoring.py: 90%+
- [ ] lifecycle.py: 90%+
- [ ] connectivity.py: 90%+
- [ ] admin.py: 90%+
- [ ] provisioning.py: 90%+
- [ ] special.py: 90%+
- [ ] cli_helpers.py: 95%+

### ⏳ Phase 8: Documentation & Cleanup (PENDING)
**Status**: ⏳ PENDING

**Tasks**:
- [ ] Update module docstrings
- [ ] Add type hints where missing
- [ ] Run ruff formatting
- [ ] Run mypy type checking
- [ ] Run pre-commit hooks
- [ ] Update CHANGELOG.md
- [ ] Update main README.md

### ⏳ Phase 9: PR Creation & Review (PENDING)
**Status**: ⏳ PENDING

**Tasks**:
- [ ] Push all changes to remote
- [ ] Create draft PR with comprehensive description
- [ ] Link to issue #423
- [ ] Run CI pipeline
- [ ] Address CI failures
- [ ] Self-review the PR
- [ ] Request team reviews
- [ ] Address review feedback
- [ ] Mark PR as ready
- [ ] Merge to main

## Metrics

### Line Count Progress
| Metric | Before | Target | Current | Progress |
|--------|--------|--------|---------|----------|
| cli.py | 9,126 | <500 | 9,126 | 0% |
| Commands extracted | 0 | 26 | 0 | 0% |
| Modules created | 0 | 6 | 0 | 0% |
| Test coverage | TBD | 90%+ | TBD | - |

### Time Investment
| Phase | Estimated | Actual | Status |
|-------|-----------|--------|---------|
| Planning | 4h | 2h | ✅ Complete |
| Phase 1 (Monitoring) | 8h | - | 🔄 Ready |
| Phase 2 (Lifecycle) | 6h | - | ⏳ Pending |
| Phase 3 (Provisioning) | 8h | - | ⏳ Pending |
| Phase 4 (Connectivity) | 8h | - | ⏳ Pending |
| Phase 5 (Admin) | 4h | - | ⏳ Pending |
| Phase 6 (Special) | 4h | - | ⏳ Pending |
| Phase 7 (Testing) | 16h | - | ⏳ Pending |
| Phase 8 (Docs) | 8h | - | ⏳ Pending |
| Phase 9 (PR) | 8h | - | ⏳ Pending |
| **TOTAL** | **74h** | **2h** | **3% Complete** |

## Risk Assessment

### High-Risk Areas
1. **Provisioning commands** (new/vm/create)
   - Core functionality
   - Complex configuration logic
   - Pool provisioning
   - Template system integration

2. **Connectivity commands** (connect/code/cp/sync)
   - Bastion detection and routing
   - SSH configuration management
   - File transfer operations

3. **Lifecycle commands** (kill/destroy/killall)
   - Destructive operations
   - Confirmation flows
   - Batch operations

### Mitigation Strategies
- **Test extensively** after each extraction
- **Manual testing** of critical paths
- **Incremental commits** for easy rollback
- **Preserve all existing tests**
- **Document breaking changes** (if any)

## Success Criteria (from Issue #423)

- [ ] cli.py reduced from 9,126 to <500 lines (94% reduction)
- [ ] 26 commands extracted to 6 modules
- [ ] All existing tests passing
- [ ] 90%+ test coverage maintained
- [ ] Zero functionality loss
- [ ] No breaking changes to CLI interface
- [ ] CI pipeline passes
- [ ] PR approved and merged

## Tools & Scripts

**Analysis**:
- `extract_commands.py` - Analyzes cli.py structure, categorizes commands
- `extract_module.py` - Semi-automated command extraction

**Documentation**:
- `DECOMPOSITION_PLAN.md` - High-level strategy
- `IMPLEMENTATION_GUIDE.md` - Detailed phase-by-phase execution
- `src/azlin/commands/README.md` - Module documentation
- `WS11_PROGRESS.md` - This progress tracker

**Infrastructure**:
- `src/azlin/commands/cli_helpers.py` - Shared helper functions

## Next Steps (Immediate)

1. **Begin Phase 1** - Monitoring Commands
   - Start with `status` command (simplest, 80 lines)
   - Validate extraction process
   - Then proceed to `w`, `ps`, `top`, `session`
   - Save `list` for last (most complex, 378 lines)

2. **Test thoroughly** after each command extraction
   - Manual CLI testing
   - Automated test suite
   - Verify no regressions

3. **Commit after each command group**
   - Atomic commits for safety
   - Clear commit messages
   - Reference phase numbers

## Timeline

**Start Date**: 2025-12-13
**Target Completion**: 2026-01-10 (4 weeks)
**Current Phase**: Phase 1 (Monitoring)
**Current Status**: Foundation complete, ready to extract commands

## Notes

- This is the **most critical refactoring** in azlin history
- **Do not rush** - quality and correctness over speed
- **Test early, test often** - catch issues immediately
- **Communicate progress** via issue #423 and git commits
- **Each phase must be solid** before proceeding to next

## Questions & Blockers

None at this time. Foundation is complete and ready for Phase 1 execution.

---

**Last Updated**: 2025-12-13
**Updated By**: Claude Code
**Next Review**: After Phase 1 completion
