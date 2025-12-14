# WS11: CLI.PY Decomposition - Handoff Document

## Quick Status

**Phase**: Foundation Complete (Phase 0/9)
**Progress**: 3% (Planning & Infrastructure)
**Branch**: `feat/issue-423-cli-decompose-impl`
**Issue**: #423
**Priority**: P0 CRITICAL
**Estimated Remaining**: 3-4 weeks

## What's Been Done

### ✅ Foundation Setup (Phase 0)

1. **Created Worktree**
   - Branch: `feat/issue-423-cli-decompose-impl`
   - Location: `./worktrees/feat-issue-423-cli-decompose-impl`
   - Committed and pushed to remote

2. **Analysis Complete**
   - Analyzed 9,126 lines of cli.py
   - Identified 26 commands to extract
   - Categorized into 6 logical groups
   - Mapped all helper functions

3. **Infrastructure Created**
   ```
   worktrees/feat-issue-423-cli-decompose-impl/
   ├── extract_commands.py          # Analysis script
   ├── extract_module.py             # Extraction helper
   ├── DECOMPOSITION_PLAN.md         # High-level strategy
   ├── IMPLEMENTATION_GUIDE.md       # Detailed execution guide
   ├── WS11_PROGRESS.md              # Progress tracker
   ├── HANDOFF.md                    # This document
   └── src/azlin/commands/
       ├── cli_helpers.py            # Shared utilities (starter)
       └── README.md                 # Module documentation
   ```

4. **Documentation Complete**
   - Comprehensive implementation guide (16 pages)
   - Phase-by-phase execution plan
   - Risk assessment and mitigation
   - Testing strategy
   - Success criteria

## Command Breakdown

### Monitoring Commands (~859 lines, 6 commands)
```
list (378 lines)     - List VMs with quota/tmux info
status (80 lines)    - Show VM status
session (135 lines)  - Manage session names
w (78 lines)         - Run 'w' command on all VMs
top (109 lines)      - Live distributed metrics
ps (79 lines)        - Process listing
```
**Risk**: MEDIUM (complex multi-context support in list)

### Lifecycle Commands (~454 lines, 6 commands)
```
start (45 lines)     - Start VM
stop (54 lines)      - Stop VM
kill (93 lines)      - Kill single VM
destroy (67 lines)   - Destroy with confirmation
killall (73 lines)   - Batch deletion
clone (122 lines)    - Clone VM
```
**Risk**: HIGH (destructive operations)

### Provisioning Commands (~199 lines, 3 commands)
```
new (157 lines)      - Primary provisioning interface
vm (21 lines)        - Alias for new
create (21 lines)    - Alias for new
```
**Risk**: VERY HIGH (core functionality)

### Connectivity Commands (~572 lines, 4 commands)
```
connect (209 lines)  - SSH connection
code (161 lines)     - VS Code Remote-SSH
cp (141 lines)       - File copy
sync (61 lines)      - Home sync
```
**Risk**: HIGH (complex SSH/bastion logic)

### Admin Commands (~412 lines, 4 commands)
```
prune (130 lines)    - Remove old VMs
update (134 lines)   - Update azlin on VM
os-update (57 lines) - OS package updates
cost (91 lines)      - Cost tracking
```
**Risk**: MEDIUM

### Special Commands (~122 lines, 2 commands)
```
help (29 lines)      - Enhanced help
do (93 lines)        - Natural language commands
```
**Risk**: LOW

## How to Continue

### Step 1: Review Documentation
Read these files in order:
1. `DECOMPOSITION_PLAN.md` - Understand overall strategy
2. `IMPLEMENTATION_GUIDE.md` - Detailed phase-by-phase guide
3. `WS11_PROGRESS.md` - Current progress and metrics
4. `src/azlin/commands/README.md` - Module structure

### Step 2: Start Phase 1 (Monitoring Commands)

**Recommended Order** (simplest to most complex):
1. **status** (80 lines) - Simplest, good warmup
2. **w** (78 lines) - Simple remote execution
3. **ps** (79 lines) - Similar to w
4. **top** (109 lines) - Slightly more complex
5. **session** (135 lines) - Session management
6. **list** (378 lines) - Most complex, save for last

**For Each Command**:
```bash
cd /home/azureuser/src/azlin/worktrees/feat-issue-423-cli-decompose-impl

# 1. Extract command using helper script
python3 extract_module.py monitoring status

# 2. Review generated code in src/azlin/commands/monitoring.py

# 3. Fix imports (the script adds TODO comments)

# 4. Test the command manually
azlin status --help
azlin status

# 5. Run test suite
pytest tests/ -v

# 6. Commit
git add src/azlin/commands/monitoring.py
git commit -m "feat: Extract status command to monitoring.py"

# 7. Repeat for next command
```

### Step 3: Update cli.py After Each Module

After completing a module (e.g., monitoring.py with all 6 commands):

1. **Import commands** in cli.py:
```python
from azlin.commands.monitoring import (
    list_command,
    status_command,
    session_command,
    w_command,
    top_command,
    ps_command,
)
```

2. **Remove old command code** from cli.py

3. **Register commands**:
```python
main.add_command(list_command)
main.add_command(status_command)
# ... etc
```

4. **Test everything still works**

5. **Commit**: `git commit -m "refactor: Move monitoring commands to monitoring.py"`

### Step 4: Proceed Through Phases

Follow this order:
1. ✅ Phase 0: Foundation (DONE)
2. → Phase 1: Monitoring (START HERE)
3. → Phase 2: Lifecycle
4. → Phase 3: Provisioning (highest risk, take care!)
5. → Phase 4: Connectivity
6. → Phase 5: Admin
7. → Phase 6: Special + Router refactoring
8. → Phase 7: Comprehensive testing
9. → Phase 8: Documentation
10. → Phase 9: PR creation and merge

### Step 5: Testing Requirements

**After Each Command Extraction**:
- Manual CLI test: `azlin <command> --help`
- Manual execution test
- Run pytest suite: `pytest tests/`
- Verify no regressions

**After Each Phase**:
- Run full test suite with coverage
- Manual testing of all extracted commands
- Verify cli.py still functions
- Check for import errors

**Final Validation** (Phase 7):
- 90%+ test coverage
- All 26 commands work identically
- No breaking changes
- Performance unchanged
- CI pipeline passes

## Tools Available

### `extract_commands.py`
Analyzes cli.py structure:
```bash
python3 extract_commands.py
```
Output: Command list with line counts and categories

### `extract_module.py`
Semi-automated extraction (needs manual cleanup):
```bash
python3 extract_module.py monitoring list status session w top ps
```
Creates: `src/azlin/commands/monitoring.py` with extracted code

**Note**: Generated code needs manual import fixes and testing!

## Important Notes

### 🚨 Critical Considerations

1. **Zero Breaking Changes**
   - All commands must work identically
   - Same error messages
   - Same behavior
   - Same performance

2. **Helper Function Management**
   - Shared helpers → `cli_helpers.py`
   - Command-specific helpers → stay with command
   - Avoid circular imports

3. **Import Management**
   - Keep TYPE_CHECKING imports separate
   - Import modules, not individual functions (where practical)
   - Watch for circular dependencies

4. **Testing is Mandatory**
   - Test after every extraction
   - Don't batch multiple commands without testing
   - Manual + automated testing

5. **Commit Frequently**
   - One commit per command or small group
   - Clear commit messages with phase numbers
   - Easy to rollback if needed

### ⚠️ High-Risk Areas

**Provisioning Commands** (new/vm/create):
- Most critical functionality
- Complex template/bastion/pool logic
- Test exhaustively before committing

**List Command**:
- 378 lines, most complex
- Multi-context support
- Quota integration
- Many edge cases

**Connect/Code Commands**:
- Bastion auto-detection
- SSH configuration
- File transfer operations

### 📋 Success Criteria

- [ ] cli.py: 9,126 → <500 lines (94% reduction)
- [ ] 26 commands extracted to 6 modules
- [ ] All tests passing
- [ ] 90%+ test coverage
- [ ] Zero functionality loss
- [ ] No breaking changes
- [ ] CI passes
- [ ] PR merged

## Timeline

**Start**: 2025-12-13 (Foundation complete)
**Target Completion**: 2026-01-10 (4 weeks)
**Current Status**: Ready for Phase 1

**Estimated Time by Phase**:
- Phase 1 (Monitoring): 1 day
- Phase 2 (Lifecycle): 1 day
- Phase 3 (Provisioning): 1.5 days
- Phase 4 (Connectivity): 1.5 days
- Phase 5 (Admin): 0.5 days
- Phase 6 (Special + Router): 0.5 days
- Phase 7 (Testing): 2 days
- Phase 8 (Documentation): 1 day
- Phase 9 (PR & Review): 1 day

**Total**: ~10 days of focused work

## Questions & Support

**Issue**: #423 on GitHub
**Branch**: `feat/issue-423-cli-decompose-impl`
**Documentation**: All files in worktree root

**If Stuck**:
1. Review `IMPLEMENTATION_GUIDE.md` for detailed steps
2. Check `WS11_PROGRESS.md` for current status
3. Look at existing command modules for patterns
4. Test early and often

## Final Notes

This is the **most critical refactoring** in azlin history. Take your time, test thoroughly, and don't rush. The foundation is solid, and the path forward is clear.

**The key to success**: Extract one command at a time, test it, commit it, move on.

Good luck! 🚀

---

**Created**: 2025-12-13
**Status**: Foundation Complete, Ready for Phase 1
**Next Step**: Extract monitoring commands starting with `status`
