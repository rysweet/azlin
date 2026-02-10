# CLI Refactoring Requirements

## Task Classification

**Classification**: EXECUTABLE (Refactoring)
**Type**: Code restructuring and modular decomposition
**Complexity**: COMPLEX (50+ lines, multiple file changes, architectural impact)

---

## 1. Objective

Refactor `src/azlin/cli.py` (currently 10,011 lines) into smaller, modular components while preserving ALL existing functionality.

### Success Metrics

| Metric | Current | Target | Notes |
|--------|---------|--------|-------|
| cli.py lines | 10,011 | < 500 | 95% reduction |
| Commands in cli.py | 25+ inline | 0 inline | All extracted |
| Command modules | 16 existing | ~22 total | 6 new modules |
| Test coverage | Maintain | Maintain | No regression |
| Functionality | 100% | 100% | Zero loss |

---

## 2. Current State Analysis

### Already Extracted (16 modules in `/src/azlin/commands/`)

| Module | Size | Status |
|--------|------|--------|
| `auth.py` | 19,619 bytes | Complete |
| `autopilot.py` | 16,508 bytes | Complete |
| `bastion.py` | 8,914 bytes | Complete |
| `cli_helpers.py` | 8,962 bytes | Complete |
| `compose.py` | 7,132 bytes | Complete |
| `context.py` | 17,271 bytes | Complete |
| `costs.py` | 11,728 bytes | Complete |
| `doit.py` | 13,636 bytes | Complete |
| `fleet.py` | 16,876 bytes | Complete |
| `github_runner.py` | 12,801 bytes | Complete |
| `monitoring.py` | 3,485 bytes | Partial (only `status`) |
| `restore.py` | 32,194 bytes | Complete |
| `storage.py` | 35,314 bytes | Complete |
| `tag.py` | 8,840 bytes | Complete |
| `ask.py` | 12,479 bytes | Complete |

### Commands Still in cli.py (Must Extract)

Based on grep analysis of `@main.command`:

| Command | Line # | Estimated Lines | Category |
|---------|--------|-----------------|----------|
| `help` | 2519 | ~50 | Special |
| `new` | 2814 | ~170 | Provisioning |
| `vm` (alias) | 2988 | ~20 | Provisioning |
| `create` (alias) | 3010 | ~20 | Provisioning |
| `list` | 3478 | ~500 | Monitoring |
| `session` | 3982 | ~130 | Monitoring |
| `w` | 4117 | ~75 | Monitoring |
| `top` | 4195 | ~105 | Monitoring |
| `os-update` | 4304 | ~55 | Admin |
| `kill` | 4361 | ~220 | Lifecycle |
| `destroy` | 4586 | ~110 | Lifecycle |
| `killall` | 4700 | ~70 | Lifecycle |
| `prune` | 4773 | ~125 | Lifecycle |
| `ps` | 4903 | ~75 | Monitoring |
| `cost` | 4982 | ~350 | Admin |
| `connect` | 5335 | ~250 | Connectivity |
| `code` | 5588 | ~250 | Connectivity |
| `update` | 5840 | ~130 | Admin |
| `stop` | 5974 | ~50 | Lifecycle |
| `start` | 6028 | ~50 | Lifecycle |
| `sync` | 6243 | ~60 | Files |
| `sync-keys` | 6304 | ~90 | Admin |
| `cp` | 6396 | ~350 | Files |
| `clone` | 6751 | ~680 | Provisioning |
| `azdoit` | 7437 | ~650 | Special |

### Command Groups Still in cli.py

| Group | Line # | Subcommands | Category |
|-------|--------|-------------|----------|
| `ip` | 7085 | check, check-bastion | Diagnostics |
| `env` | 8105 | set, get, list, delete, sync | Environment |
| `keys` | 8157 | ? | SSH Keys |
| `template` | 8166 | ? | Templates |
| `snapshot` | 8204 | ? | Snapshots |
| `web` | 9438 | start, stop | PWA |

---

## 3. Explicit Requirements

### MUST (Non-Negotiable)

1. **Zero Functionality Loss**: Every command must work identically after refactoring
2. **Backward Compatibility**: Same CLI interface, options, arguments, help text
3. **All Tests Pass**: No test regression allowed
4. **Same Error Messages**: User-facing error messages preserved exactly
5. **Same Exit Codes**: Return codes unchanged

### MUST NOT

1. **Change Command Names**: No renaming commands
2. **Change Option Flags**: No changing `--rg` to `--resource-group` etc.
3. **Modify Business Logic**: This is a restructuring, not a rewrite
4. **Break Imports**: External code importing from `azlin.cli` must still work
5. **Skip Testing**: Every extraction must be tested before committing

### SHOULD

1. **Follow Existing Pattern**: Use the pattern from `monitoring.py` extraction
2. **Group Related Commands**: Commands in logical modules (lifecycle, connectivity, etc.)
3. **Minimize Dependencies**: Each module imports only what it needs
4. **Preserve Docstrings**: All documentation maintained

### MAY

1. **Create Helper Modules**: Shared utilities can be factored out
2. **Refactor Internal Functions**: Private helpers can be reorganized
3. **Add Type Hints**: Improve typing if already touching the code

---

## 4. Target Architecture

### Final Directory Structure

```
src/azlin/
├── cli.py                      # < 500 lines (router only)
├── commands/
│   ├── __init__.py             # Command exports
│   ├── admin.py                # NEW: os-update, update, sync-keys, cost
│   ├── ask.py                  # EXISTS
│   ├── auth.py                 # EXISTS
│   ├── autopilot.py            # EXISTS
│   ├── bastion.py              # EXISTS
│   ├── cli_helpers.py          # EXISTS (shared helpers)
│   ├── compose.py              # EXISTS
│   ├── connectivity.py         # NEW: connect, code
│   ├── context.py              # EXISTS
│   ├── costs.py                # EXISTS
│   ├── doit.py                 # EXISTS
│   ├── env_commands.py         # NEW: env group
│   ├── files.py                # NEW: sync, cp
│   ├── fleet.py                # EXISTS
│   ├── github_runner.py        # EXISTS
│   ├── ip_diagnostics.py       # NEW: ip group
│   ├── keys_commands.py        # NEW: keys group
│   ├── lifecycle.py            # NEW: kill, destroy, killall, prune, stop, start
│   ├── monitoring.py           # EXPAND: list, session, w, top, ps (+ existing status)
│   ├── provisioning.py         # NEW: new, vm, create, clone
│   ├── restore.py              # EXISTS
│   ├── snapshot_commands.py    # NEW: snapshot group
│   ├── special.py              # NEW: help, azdoit
│   ├── storage.py              # EXISTS
│   ├── tag.py                  # EXISTS
│   ├── template_commands.py    # NEW: template group
│   └── web_commands.py         # NEW: web group
```

### cli.py Final Structure (< 500 lines)

```python
"""CLI entry point for azlin - Router Only.

All commands are implemented in azlin.commands.* modules.
This file handles:
- Click main group definition
- Command registration
- Global options (auth-profile)
"""

import click
from azlin.click_group import AzlinGroup

# Import all command modules
from azlin.commands.admin import os_update, update, sync_keys, cost
from azlin.commands.connectivity import connect, code
from azlin.commands.files import sync, cp
from azlin.commands.lifecycle import kill, destroy, killall, prune, stop, start
from azlin.commands.monitoring import status, list_vms, session, w, top, ps
from azlin.commands.provisioning import new, vm, create, clone
from azlin.commands.special import help_command, azdoit
# ... etc

@click.group(cls=AzlinGroup)
@click.option("--auth-profile", help="Authentication profile")
@click.pass_context
def main(ctx, auth_profile):
    """Azlin - Azure VM Management CLI."""
    # Minimal setup only
    pass

# Register all commands
main.add_command(new)
main.add_command(list_vms, name="list")
# ... etc

# Register all groups
main.add_command(auth)
main.add_command(context_group)
# ... etc
```

---

## 5. Implementation Phases

### Phase 1: Expand Monitoring Module (Priority: HIGH)

**Commands**: `list`, `session`, `w`, `top`, `ps`
**Target**: `monitoring.py` (already has `status`)
**Estimated Lines**: ~885
**Risk**: MEDIUM (complex `list` command)

### Phase 2: Lifecycle Commands (Priority: HIGH)

**Commands**: `kill`, `destroy`, `killall`, `prune`, `stop`, `start`
**Target**: `lifecycle.py` (NEW)
**Estimated Lines**: ~625
**Risk**: MEDIUM (critical VM operations)

### Phase 3: Provisioning Commands (Priority: HIGH)

**Commands**: `new`, `vm`, `create`, `clone`
**Target**: `provisioning.py` (NEW)
**Estimated Lines**: ~890
**Risk**: HIGH (core provisioning logic)

### Phase 4: Connectivity Commands (Priority: MEDIUM)

**Commands**: `connect`, `code`
**Target**: `connectivity.py` (NEW)
**Estimated Lines**: ~500
**Risk**: HIGH (complex SSH/bastion logic)

### Phase 5: File Commands (Priority: MEDIUM)

**Commands**: `sync`, `cp`
**Target**: `files.py` (NEW)
**Estimated Lines**: ~410
**Risk**: MEDIUM (file transfer logic)

### Phase 6: Admin Commands (Priority: MEDIUM)

**Commands**: `os-update`, `update`, `sync-keys`, `cost`
**Target**: `admin.py` (NEW)
**Estimated Lines**: ~625
**Risk**: LOW (well-isolated operations)

### Phase 7: Special Commands (Priority: LOW)

**Commands**: `help`, `azdoit`
**Target**: `special.py` (NEW)
**Estimated Lines**: ~700
**Risk**: LOW (help is simple, azdoit is complex but isolated)

### Phase 8: Command Groups (Priority: LOW)

**Groups**: `ip`, `env`, `keys`, `template`, `snapshot`, `web`
**Targets**: Individual module files
**Risk**: LOW (groups are self-contained)

### Phase 9: Final Router Cleanup (Priority: FINAL)

**Task**: Reduce cli.py to router-only
**Target**: < 500 lines
**Risk**: LOW (just cleanup)

---

## 6. Extraction Pattern (Standard Process)

For each command extraction:

### Step 1: Analyze Dependencies

```bash
# Find command location
grep -n "def command_name" src/azlin/cli.py

# Identify imports used by command
# Look at function body for manager classes, helpers
```

### Step 2: Create/Extend Target Module

```python
"""Module docstring.

Commands:
    - command_name: Description
"""

import click
from azlin.some_manager import SomeManager

@click.command()
@click.option(...)
def command_name(...):
    """Original docstring preserved."""
    # Original implementation
    pass

__all__ = ["command_name"]
```

### Step 3: Update cli.py

```python
# Add import
from azlin.commands.module import command_name

# Add registration (near line 9395+)
main.add_command(command_name)

# Remove original command definition
# Leave marker: # Moved to azlin.commands.module (Issue #XXX)
```

### Step 4: Test

```bash
# Run command-specific tests
pytest tests/ -xvs -k "test_command_name"

# Test help
azlin command_name --help

# Manual smoke test
azlin command_name [args]
```

---

## 7. Constraints

### Technical Constraints

1. **Python 3.11+**: Use modern Python features
2. **Click Framework**: Preserve Click patterns
3. **Rich Library**: Keep rich console output
4. **Existing Tests**: All must pass

### Process Constraints

1. **Incremental Commits**: One phase per commit minimum
2. **CI Must Pass**: Every commit must pass CI
3. **No Force Push**: Preserve history
4. **PR Reviews**: Required for merge

### Scope Constraints

1. **Refactoring Only**: No new features
2. **No API Changes**: External interface unchanged
3. **No Performance Work**: Save for separate PR

---

## 8. Acceptance Criteria

### Per-Phase Acceptance

- [ ] Target module created/updated
- [ ] Commands extracted with all decorators
- [ ] Original code removed from cli.py
- [ ] Marker comments added
- [ ] All imports working
- [ ] Unit tests pass
- [ ] Manual testing complete
- [ ] CI passes

### Final Acceptance

- [ ] cli.py < 500 lines
- [ ] All 25+ commands extracted
- [ ] All 6+ groups extracted
- [ ] All tests pass (unit, integration)
- [ ] Manual testing of ALL commands
- [ ] Documentation updated
- [ ] PR approved and merged

---

## 9. Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Circular imports | HIGH | MEDIUM | Use TYPE_CHECKING, function-level imports |
| Test failures | HIGH | LOW | Test after each extraction |
| Missing helper functions | MEDIUM | MEDIUM | Audit helpers before extraction |
| Complex commands fail | HIGH | MEDIUM | Extract simple commands first |
| Performance regression | MEDIUM | LOW | Benchmark before/after |

---

## 10. Decision: Follow Existing Plan

**Recommendation**: Follow DECOMPOSITION_PLAN.md with these modifications:

1. **Use updated line counts** (cli.py is now 10,011 lines, not 9,126)
2. **Follow the 6-phase approach** from DECOMPOSITION_PLAN.md
3. **Use proven extraction pattern** from monitoring.py POC
4. **Target < 500 lines** for cli.py (not 3,000)

### Why Follow Existing Plan

1. POC already proven (status command extracted successfully)
2. Categories are logical and well-defined
3. Risk assessment is accurate
4. Timeline is realistic

### What to Update

1. Current line counts (plan says 9,126, actual is 10,011)
2. Commands already extracted need verification
3. Add Phase 8-9 for command groups and final cleanup

---

## 11. Estimated Effort

| Phase | Scope | Estimated Time |
|-------|-------|----------------|
| Phase 1 | Monitoring | 2-3 hours |
| Phase 2 | Lifecycle | 2-3 hours |
| Phase 3 | Provisioning | 3-4 hours |
| Phase 4 | Connectivity | 2-3 hours |
| Phase 5 | Files | 1-2 hours |
| Phase 6 | Admin | 2-3 hours |
| Phase 7 | Special | 2-3 hours |
| Phase 8 | Groups | 3-4 hours |
| Phase 9 | Cleanup | 1-2 hours |
| Testing | Comprehensive | 3-4 hours |
| **Total** | | **~24-31 hours** |

---

## 12. Questions Answered

1. **Should I follow existing DECOMPOSITION_PLAN.md?**
   YES - Follow it with updates for current state

2. **What is the prioritized order?**
   Phases 1-3 (Monitoring, Lifecycle, Provisioning) are highest priority

3. **Are there commands that should NOT be extracted?**
   NO - All commands should be extracted for consistency

4. **What is the acceptance criteria for "smaller components"?**
   - cli.py < 500 lines (router only)
   - Each module < 1000 lines (split if larger)
   - All tests passing
   - Zero functionality loss

---

*Document generated: 2026-02-07*
*Issue Reference: #423*
*Based on: DECOMPOSITION_PLAN.md, CLI_DECOMPOSITION_HANDOFF.md*
