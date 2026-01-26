# CLI Decomposition Handoff Guide (Issue #423)

## Overview

This document provides comprehensive guidance for continuing the cli.py decomposition work after the proof-of-concept has been completed.

## What Was Completed (Proof-of-Concept)

### Status Command Extraction

**Branch**: `feat/issue-423-cli-decompose-impl`
**Completed**: December 2025

The `status` command has been successfully extracted from `cli.py` to demonstrate the decomposition pattern:

1. **New Module Created**: `/src/azlin/commands/monitoring.py`
   - Contains the `status` command with full Click decorators
   - Minimal dependencies: ConfigManager, ContextManager, VMManager
   - 95 lines of clean, self-contained code

2. **Changes to cli.py**:
   - Added import: `from azlin.commands.monitoring import status`
   - Registered command: `main.add_command(status)` at line 8714
   - Removed original status command definition (lines 6292-6369)
   - Left marker comment indicating extraction

3. **Tests Verified**:
   - All 52 status-related tests passing
   - Command works identically to before: `azlin status --help`
   - No breaking changes to existing functionality

### Files Modified

```
src/azlin/cli.py                    (-78 lines, +2 lines for import/registration)
src/azlin/commands/monitoring.py    (+95 lines, new file)
```

### Net Impact

- **cli.py reduced**: 9,126 lines → 9,050 lines (76 lines removed)
- **Pattern established**: Clear blueprint for extracting remaining 25 commands
- **Tests passing**: All status command tests green

## What Remains (Full Implementation)

### Commands to Extract

cli.py currently contains **26 main commands** that need decomposition:

#### High Priority (Frequently Used)
1. `list` - List VMs (most complex, ~900 lines)
2. `new` - Provision new VM (~500 lines)
3. `connect` - SSH to VM (~400 lines)
4. `clone` - Clone VM (~300 lines)
5. `kill` - Delete VM (~200 lines)

#### Medium Priority (Monitoring & Operations)
6. `top` - Distributed top dashboard
7. `w` - Show who is logged in
8. `ps` - Process listing
9. `killall` - Delete all VMs
10. `prune` - Delete old VMs
11. `update` - Update packages on VM
12. `start` - Start stopped VM
13. `stop` - Stop running VM

#### Lower Priority (File Operations & Utilities)
14. `sync` - Sync files to VM
15. `cp` - Copy files (scp/rsync)
16. `code` - Launch VS Code remote
17. `session` - Manage session names

#### Specialized Commands (Can be grouped)
18. `ip check` - IP diagnostics (already a group)
19. `env` group - Environment variables (5 subcommands)
20. `batch` group - Batch operations (3 subcommands)
21. `keys` group - SSH key management (4 subcommands)
22. `template` group - VM templates (5 subcommands)
23. `snapshot` group - VM snapshots (4 subcommands)
24. `rotate-key` - SSH key rotation
25. `self-update` - Update azlin
26. `azdoit` - Natural language commands

### Target Module Structure

Based on command groupings, create these new modules:

```
src/azlin/commands/
├── monitoring.py        ✅ (status - DONE)
├── lifecycle.py         (new, kill, killall, prune, clone)
├── connection.py        (connect, code)
├── operations.py        (top, w, ps, update, start, stop)
├── files.py            (sync, cp)
├── session.py          (session management)
├── ip_diagnostics.py   (ip check commands)
├── env_commands.py     (env group - already extracted?)
├── batch_commands.py   (batch group)
├── keys_commands.py    (keys group, rotate-key)
├── template_commands.py (template group)
├── snapshot_commands.py (snapshot group)
└── utility.py          (self-update, misc)
```

**Note**: Some command groups (auth, context, bastion, etc.) are already extracted.

## How to Continue

### Step-by-Step Process (Per Command)

Follow this proven process for each command extraction:

#### 1. Identify Command Definition
```bash
# Find command location in cli.py
grep -n "^@main.command()" src/azlin/cli.py
grep -n "^def command_name" src/azlin/cli.py
```

#### 2. Analyze Dependencies
```bash
# Check what the command imports/uses
grep "import" around the command
# Look for ConfigManager, VMManager, etc.
```

#### 3. Create Target Module
```python
# Example: src/azlin/commands/lifecycle.py
"""VM lifecycle commands for azlin.

Commands:
    - new: Provision new VM
    - kill: Delete VM
    - clone: Clone VM
"""

import sys
import click

# Import only what's needed
from azlin.config_manager import ConfigManager
from azlin.vm_manager import VMManager
# ... etc

@click.command()
@click.option("...")
def new(...):
    """Command implementation."""
    pass
```

#### 4. Extract Command Code
- Copy command definition from cli.py
- Copy all Click decorators
- Preserve docstrings and examples
- Include any helper functions used only by this command

#### 5. Update cli.py
```python
# Add import at top
from azlin.commands.lifecycle import new, kill, clone

# Add registration at line ~8714
main.add_command(new)
main.add_command(kill)
main.add_command(clone)

# Remove original definitions
# Leave marker comments
```

#### 6. Test Thoroughly
```bash
# Run command-specific tests
pytest tests/ -xvs -k "test_new"

# Test command help
azlin new --help

# Run smoke tests
pytest tests/unit/cli/test_command_syntax.py -x
```

### Recommended Order of Extraction

Extract commands in this order to minimize risk:

1. **Phase 1 - Simple Commands** (1-2 days)
   - `w`, `ps`, `session` (simple, few dependencies)
   - Builds confidence with the pattern

2. **Phase 2 - Medium Commands** (3-5 days)
   - `top`, `start`, `stop`, `update`, `killall`, `prune`
   - More complex but well-isolated

3. **Phase 3 - Complex Commands** (1-2 weeks)
   - `list` (most complex, ~900 lines)
   - `new` (complex provisioning logic)
   - `connect` (complex SSH logic)
   - `clone` (depends on provisioning)

4. **Phase 4 - File & Special Commands** (3-5 days)
   - `sync`, `cp`, `code`
   - `kill`, `rotate-key`, `self-update`

5. **Phase 5 - Command Groups** (1 week)
   - Review existing groups (some already extracted)
   - Move remaining groups to appropriate modules

**Total Estimated Time**: 3-4 weeks

## Tools & Infrastructure

### Automated Extraction Script

Use `scripts/extract_command.py` (if available):

```bash
python scripts/extract_command.py status monitoring
# Extracts 'status' command to 'monitoring.py'
```

### Testing Infrastructure

```bash
# Run all tests
pytest tests/ -x

# Run command-specific tests
pytest tests/ -k "test_status"

# Run CLI syntax tests
pytest tests/unit/cli/test_command_syntax*.py

# Quick smoke test
pytest tests/unit/cli/ -x --tb=short -q
```

### Code Quality Checks

```bash
# Format code
ruff format src/azlin/commands/

# Lint
ruff check src/azlin/commands/

# Type check
mypy src/azlin/commands/
```

## Key Patterns & Best Practices

### 1. Minimal Dependencies

Only import what's needed:
```python
# Good
from azlin.vm_manager import VMManager, VMManagerError

# Bad
from azlin.vm_manager import *
```

### 2. Preserve Command Behavior

The command must work **identically** before and after extraction:
- Same Click options
- Same error messages
- Same output format
- Same exit codes

### 3. Keep Helper Functions Local

If a helper function is only used by one command, move it to that module:
```python
# monitoring.py
def _format_status_table(vms):
    """Format VM status table."""
    pass

@click.command()
def status(...):
    _format_status_table(vms)
```

### 4. Document Extraction

Leave clear markers in cli.py:
```python
# Status command moved to azlin.commands.monitoring (Issue #423)
```

### 5. Update __all__ Exports

In each new module:
```python
__all__ = ["status", "top", "w"]
```

## Testing Strategy

### Unit Tests
- All existing tests must pass
- No new tests needed for extraction (unless refactoring)

### Integration Tests
- Command help works: `azlin <command> --help`
- Command executes: Test with mocked Azure calls

### Manual Testing
```bash
# Test each extracted command
azlin status --help
azlin status --rg test-rg
azlin status --vm test-vm
```

## Common Pitfalls & Solutions

### Pitfall 1: Circular Imports

**Problem**: Module A imports Module B which imports Module A

**Solution**:
- Use TYPE_CHECKING for type hints
- Import at function level if needed
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from azlin.some_module import SomeType
```

### Pitfall 2: Missing Dependencies

**Problem**: Command uses helper function defined elsewhere in cli.py

**Solution**:
- Move helper to new module if only used there
- Create shared helper module if used by multiple commands
- Keep in cli.py if truly shared across many commands

### Pitfall 3: Test Failures

**Problem**: Tests fail after extraction

**Solution**:
- Check import paths in tests
- Verify command is registered with main
- Ensure all Click decorators preserved

### Pitfall 4: Large Commands

**Problem**: Command like `list` is 900 lines

**Solution**:
- Extract in stages
- Move helper functions first
- Create internal helper module if needed
- Consider splitting into multiple functions

## Progress Tracking

Use this checklist to track progress:

### Phase 1 - Simple Commands
- [ ] w
- [ ] ps
- [ ] session

### Phase 2 - Medium Commands
- [ ] top
- [ ] start
- [ ] stop
- [ ] update
- [ ] killall
- [ ] prune

### Phase 3 - Complex Commands
- [ ] list (most complex)
- [ ] new
- [ ] connect
- [ ] clone

### Phase 4 - File & Special Commands
- [ ] sync
- [ ] cp
- [ ] code
- [ ] kill
- [ ] rotate-key
- [ ] self-update

### Phase 5 - Command Groups
- [ ] ip group (check if needed)
- [ ] env group (check if done)
- [ ] batch group
- [ ] keys group
- [ ] template group
- [ ] snapshot group

## Success Metrics

Track these metrics as you progress:

1. **cli.py Size**:
   - Start: 9,050 lines
   - Target: < 3,000 lines (2/3 reduction)
   - Current: ___ lines

2. **Commands Extracted**:
   - Total: 26 commands
   - Completed: 1 (status)
   - Remaining: 25

3. **Test Coverage**:
   - All existing tests pass
   - No reduction in coverage

4. **Module Count**:
   - Target: ~12 command modules
   - Current: 1 (monitoring.py)

## Timeline & Milestones

### Week 1: Simple Commands (Dec 16-20)
- Extract w, ps, session
- Verify pattern works consistently
- Document any issues

### Week 2-3: Medium & Complex Commands (Dec 23 - Jan 3)
- Extract start, stop, update, killall, prune
- Begin work on list, new, connect
- May span holiday break

### Week 3-4: Complex Commands (Jan 6-10)
- Complete list, new, connect, clone
- Most challenging work

### Week 4: Final Commands & Cleanup (Jan 13-17)
- Extract remaining commands
- Move command groups
- Final testing and documentation

**Target Completion**: January 17, 2025

## Rollback Plan

If extraction causes issues:

1. **Revert Single Command**:
   ```bash
   git checkout main -- src/azlin/cli.py
   git checkout main -- src/azlin/commands/monitoring.py
   ```

2. **Revert All Changes**:
   ```bash
   git reset --hard origin/main
   ```

3. **Partial Rollback**:
   - Keep successful extractions
   - Only revert problematic command

## Questions & Support

### Common Questions

**Q**: Can I extract multiple commands at once?
**A**: Yes, but test each one individually first.

**Q**: What if a command depends on another command?
**A**: Extract both to the same module, or create shared helper module.

**Q**: Should I refactor while extracting?
**A**: No. Extract first, refactor later. Keep changes minimal.

**Q**: What if tests fail?
**A**: First ensure command works identically. Check imports and registration.

### Getting Help

- Review this handoff guide
- Check the POC (status command) as reference
- Read Click documentation for command patterns
- Ask questions in Issue #423

## References

- **Issue**: #423 (cli.py decomposition)
- **Branch**: feat/issue-423-cli-decompose-impl
- **POC**: status command in `src/azlin/commands/monitoring.py`
- **Original cli.py**: 9,126 lines
- **Target**: < 3,000 lines

## Conclusion

The proof-of-concept demonstrates that cli.py decomposition is **feasible and straightforward**. The pattern is clear:

1. Create new module
2. Extract command with decorators
3. Update imports and registration
4. Remove old definition
5. Test

Following this guide, the full decomposition can be completed in **3-4 weeks** with confidence.

Good luck! 🚀
