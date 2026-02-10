# CLI Commands Pattern Analysis
**Date**: 2026-02-10
**Scope**: src/azlin/commands/ (27 command modules, ~14,594 LOC)

## Executive Summary

Analyzed 27 CLI command modules with focus on three largest files:
- **monitoring.py** (1735 LOC)
- **connectivity.py** (1603 LOC)
- **provisioning.py** (1216 LOC)

**Key Findings**:
- ✅ Good modular decomposition from original cli.py
- ⚠️  Significant code duplication (6 instances of duplicated functions)
- ⚠️  Inconsistent error handling patterns (354 error messages, 493 sys.exit calls)
- ⚠️  Large files exceed single responsibility (>1000 LOC)
- ❌ Missing safe subprocess wrapper (13 subprocess calls, no unified error handling)
- ⚠️  Configuration access repeated 20+ times across files

---

## Pattern Analysis

### ✅ POSITIVE PATTERNS (Keep These)

#### 1. Bricks & Studs Module Design
**Evidence**: All command modules follow clear public API pattern:
```python
# From monitoring.py
__all__ = [
    "cost",
    "list_command",
    "os_update",
    "ps",
    "session_command",
    "status",
    "top",
    "w",
]
```
**Alignment**: ✅ Matches PATTERNS.md "Bricks & Studs Module Design with Clear Public API"

#### 2. Philosophy Documentation
**Evidence**: Files like restore.py include clear philosophy headers:
```python
"""Philosophy:
- Single responsibility (restore sessions)
- Standard library + existing azlin modules
- Self-contained and regeneratable
- Zero-BS implementation (no stubs/placeholders)
"""
```
**Alignment**: ✅ Matches PHILOSOPHY.md "The Zen of Simple Code"

#### 3. Security Validation
**Evidence**: restore.py includes comprehensive input validation:
```python
def _validate_vm_name(vm_name: str) -> None:
    """Validate VM name for command injection prevention."""
    # Azure VM naming: alphanumeric, hyphen, underscore
    pattern = r"^[a-zA-Z0-9_\-]{1,64}$"
    if not re.match(pattern, vm_name):
        raise SecurityValidationError(f"Invalid VM name format: {vm_name}")

    # Check for command injection patterns
    dangerous_chars = [";", "&", "|", "`", "$", "(", ")", "<", ">", "\n", "\r"]
```
**Alignment**: ✅ Good security practice (not explicitly in PATTERNS.md, but should be)

#### 4. Helper Module Pattern
**Evidence**: cli_helpers.py centralizes common utilities:
```python
"""Shared helper functions for CLI commands.

Functions in this module should be:
- Pure or side-effect minimal
- Reusable across multiple commands
- Well-tested
- Clearly documented
"""
```
**Alignment**: ✅ Follows modular design principle

---

## ⚠️  ANTI-PATTERNS (Fix These)

### 1. **God Object Anti-Pattern** (High Priority)
**Issue**: monitoring.py (1735 LOC) and connectivity.py (1603 LOC) exceed single responsibility

**Evidence**:
- monitoring.py contains 8 commands + helper functions
- connectivity.py contains 6 commands + helper functions
- 200 total functions across 27 files = avg 7.4 functions/file
- monitoring.py alone has 35 try blocks

**Impact**:
- Violates "Single Responsibility" principle
- Hard to test, maintain, regenerate
- High cognitive load

**Recommendation**: Split into smaller modules
```
src/azlin/commands/
├── monitoring/
│   ├── __init__.py       # Public API
│   ├── status.py         # status command
│   ├── list.py           # list_command
│   ├── top.py            # top command
│   ├── ps.py             # ps command
│   ├── w.py              # w command
│   ├── session.py        # session_command
│   └── helpers.py        # Shared monitoring helpers
```

**Effort**: Medium (2-3 days)
- Extract each command to separate file
- Preserve public API via __init__.py
- Update imports in tests

### 2. **Duplicated Code** (High Priority)
**Issue**: Multiple instances of identical/similar functions across files

**Evidence**:
```python
# Found in 3 files: connectivity.py, env.py, monitoring.py
def _get_ssh_config_for_vm(vm_identifier, resource_group, config):
    """Helper to get SSH config for VM identifier."""
    # ... 40+ lines of identical logic

# Found in 6 files: connectivity.py, provisioning.py, batch.py (x3)
def progress_callback(...):
    """Progress callback for operations."""
    # ... identical callback logic
```

**Impact**:
- Bug fixes must be replicated 3-6 times
- Increased maintenance burden
- Potential for inconsistency

**Recommendation**: Extract to shared utilities
```python
# NEW: src/azlin/commands/shared/ssh_helpers.py
class SSHConfigResolver:
    """Centralized SSH configuration resolution."""

    @staticmethod
    def get_ssh_config_for_vm(
        vm_identifier: str,
        resource_group: str | None,
        config: str | None
    ) -> SSHConfig:
        """Resolve SSH config for any VM identifier (name, session, IP)."""
        # Single implementation, used by all commands
        ...

# NEW: src/azlin/commands/shared/progress.py
class ProgressCallbackFactory:
    """Factory for consistent progress callbacks."""

    @staticmethod
    def create_progress_callback() -> Callable:
        """Create standardized progress callback."""
        ...
```

**Effort**: Low (1 day)
- Create shared/ directory
- Extract duplicated functions
- Update imports

### 3. **Missing Safe Subprocess Wrapper** (Medium Priority)
**Issue**: PATTERNS.md defines "Safe Subprocess Wrapper" pattern, but it's not used

**Evidence**:
- 13 subprocess.run() calls across commands
- No unified error handling
- Inconsistent timeout handling
- Example from cli_helpers.py:
```python
try:
    result = subprocess.run(ssh_cmd, check=False)  # ❌ No timeout, no error context
    return result.returncode
except Exception as e:
    click.echo(f"Error executing command: {e}", err=True)  # ❌ Generic message
    return 1
```

**Recommendation**: Implement and use Safe Subprocess Wrapper from PATTERNS.md
```python
# NEW: src/azlin/commands/shared/subprocess_helpers.py
def safe_subprocess_call(
    cmd: List[str],
    context: str,
    timeout: Optional[int] = 30,
) -> Tuple[int, str, str]:
    """Safely execute subprocess with comprehensive error handling.

    Returns:
        Tuple[returncode, stdout, stderr]
    """
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr

    except FileNotFoundError:
        cmd_name = cmd[0] if cmd else "command"
        error_msg = f"Command not found: {cmd_name}\nContext: {context}\n"
        error_msg += "Please ensure the tool is installed and in your PATH."
        return 127, "", error_msg

    except subprocess.TimeoutExpired:
        cmd_name = cmd[0] if cmd else "command"
        error_msg = f"Command timed out after {timeout}s: {cmd_name}\nContext: {context}\n"
        return 124, "", error_msg

    except Exception as e:
        cmd_name = cmd[0] if cmd else "command"
        error_msg = f"Unexpected error running {cmd_name}: {str(e)}\nContext: {context}\n"
        return 1, "", error_msg
```

**Effort**: Medium (1-2 days)
- Implement wrapper
- Replace all subprocess.run() calls
- Add tests

### 4. **Inconsistent Error Handling** (Medium Priority)
**Issue**: No standardized error handling pattern

**Evidence**:
- 354 `click.echo(..., err=True)` calls
- 493 `sys.exit()` calls
- Inconsistent error message format
- Example variations:
```python
# Pattern A: Direct exit
click.echo("Error: ...", err=True)
sys.exit(1)

# Pattern B: Try-except with exit
try:
    ...
except VMManagerError as e:
    click.echo(f"Error: {e}", err=True)
    sys.exit(1)

# Pattern C: Try-except without exit (returns None)
try:
    ...
except Exception as e:
    logger.warning(f"Failed: {e}")
    return None
```

**Recommendation**: Create unified error handler
```python
# NEW: src/azlin/commands/shared/error_handlers.py
class CommandError(Exception):
    """Base exception for command errors."""

    def __init__(self, message: str, exit_code: int = 1):
        self.message = message
        self.exit_code = exit_code
        super().__init__(message)

def handle_command_error(func):
    """Decorator for consistent error handling."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except CommandError as e:
            click.echo(f"Error: {e.message}", err=True)
            sys.exit(e.exit_code)
        except VMManagerError as e:
            click.echo(f"VM Error: {e}", err=True)
            sys.exit(1)
        except ConfigError as e:
            click.echo(f"Config Error: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"Unexpected Error: {e}", err=True)
            logger.exception("Unexpected error in command")
            sys.exit(1)
    return wrapper

# Usage:
@click.command()
@handle_command_error
def status(...):
    """Show VM status."""
    # Exceptions automatically caught and formatted
    ...
```

**Effort**: Medium (2 days)
- Implement error handler decorator
- Apply to all commands
- Standardize error messages

### 5. **Configuration Access Duplication** (Low Priority)
**Issue**: `ConfigManager.get_resource_group()` called 20+ times with same pattern

**Evidence**:
```python
# Repeated in 20+ locations across files:
rg = ConfigManager.get_resource_group(resource_group, config)
if not rg:
    click.echo("Error: No resource group specified and no default configured.", err=True)
    click.echo("Use --resource-group or set default in ~/.azlin/config.toml", err=True)
    sys.exit(1)
```

**Recommendation**: Create configuration decorator
```python
# NEW: src/azlin/commands/shared/config_decorators.py
def require_resource_group(func):
    """Decorator to ensure resource group is available."""
    @functools.wraps(func)
    def wrapper(*args, resource_group=None, config=None, **kwargs):
        rg = ConfigManager.get_resource_group(resource_group, config)
        if not rg:
            click.echo("Error: No resource group specified and no default configured.", err=True)
            click.echo("Use --resource-group or set default in ~/.azlin/config.toml", err=True)
            sys.exit(1)
        kwargs['resolved_rg'] = rg
        return func(*args, resource_group=resource_group, config=config, **kwargs)
    return wrapper

# Usage:
@click.command()
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@require_resource_group
def status(resource_group, config, resolved_rg, **kwargs):
    """Show VM status."""
    # resolved_rg is guaranteed to exist here
    vms = VMManager.list_vms(resolved_rg)
    ...
```

**Effort**: Low (1 day)
- Create decorator
- Apply to commands needing resource group
- Reduce LOC by ~100

### 6. **SSH Key Initialization Pattern Duplication** (Low Priority)
**Issue**: `SSHKeyManager.ensure_key_exists()` called 12 times with no error handling

**Evidence**:
```python
# Repeated 12 times:
ssh_key_pair = SSHKeyManager.ensure_key_exists()
```

**Recommendation**: Create SSH key decorator
```python
# NEW: src/azlin/commands/shared/config_decorators.py
def with_ssh_key(func):
    """Decorator to inject SSH key pair."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            ssh_key_pair = SSHKeyManager.ensure_key_exists()
            kwargs['ssh_key_pair'] = ssh_key_pair
            return func(*args, **kwargs)
        except SSHKeyError as e:
            click.echo(f"SSH Key Error: {e}", err=True)
            sys.exit(1)
    return wrapper

# Usage:
@click.command()
@with_ssh_key
def connect(vm_identifier, ssh_key_pair, **kwargs):
    """Connect to VM."""
    # ssh_key_pair automatically injected
    ...
```

**Effort**: Low (0.5 days)

---

## Missing Patterns from PATTERNS.md

### 1. **Fail-Fast Prerequisite Checking** ❌
**Status**: Not implemented
**Location**: Should be in commands that require external tools (docker, ssh, az cli)
**Impact**: Users get cryptic errors mid-workflow instead of clear startup messages

### 2. **API Validation Before Implementation** ❌
**Status**: Minimal validation
**Evidence**: Direct API calls without model name validation:
```python
# From various files - no validation before Azure SDK calls
vm = VMManager.get_vm(vm_name, rg)  # No check if VMManager.get_vm exists or signature
```
**Impact**: Runtime failures instead of early validation

### 3. **Resilient Batch Processing** ❌
**Status**: Not used (should be in batch operations like list, w, ps)
**Evidence**: Commands fail completely if any VM fails:
```python
# From monitoring.py - fails entire operation if one VM fails
for vm in vms:
    ssh_config = _get_ssh_config_for_vm(vm.name, rg, config)  # ❌ No error isolation
```

---

## Consistency Analysis

### Import Patterns ✅
- Consistent use of `from azlin.X import Y` (not `import azlin`)
- Alphabetized imports within sections
- Standard library → Third-party → Local imports order

### Click Command Structure ✅
- Consistent option naming (`--resource-group` / `--rg`)
- Consistent help text format
- Consistent use of click.Path() for file paths

### Naming Conventions ✅
- Commands use snake_case
- Private helpers use `_prefix`
- Constants use UPPER_CASE

### Documentation Quality ⚠️
- Module docstrings: ✅ Good (all files have them)
- Function docstrings: ⚠️ Inconsistent (some missing Args/Returns)
- Inline comments: ⚠️ Variable quality

---

## Refactoring Recommendations

### Phase 1: Quick Wins (1-2 weeks)
**Priority**: High impact, low effort

1. **Extract duplicated functions** (1 day)
   - Create `commands/shared/` directory
   - Extract: `_get_ssh_config_for_vm`, `progress_callback`
   - Update imports

2. **Implement safe subprocess wrapper** (1-2 days)
   - Add pattern from PATTERNS.md
   - Replace 13 subprocess calls
   - Add tests

3. **Create config decorators** (1 day)
   - `@require_resource_group`
   - `@with_ssh_key`
   - Apply to commands

4. **Standardize error handling** (2 days)
   - Implement `@handle_command_error` decorator
   - Apply to all commands
   - Unify error messages

**Total Effort**: 5-6 days
**Lines Reduced**: ~200-300 LOC
**Benefit**: Reduced duplication, consistent error handling

### Phase 2: Structural Improvements (2-3 weeks)
**Priority**: Medium impact, medium effort

1. **Split large command files** (2-3 days per file)
   - monitoring.py → monitoring/ module (8 files)
   - connectivity.py → connectivity/ module (6 files)
   - provisioning.py → provisioning/ module (5 files)

2. **Add prerequisite checking** (1-2 days)
   - Implement Fail-Fast pattern
   - Add to commands requiring external tools

3. **Add resilient batch processing** (2-3 days)
   - Implement pattern from PATTERNS.md
   - Apply to list, w, ps commands
   - Add progress tracking

**Total Effort**: 8-12 days
**Lines Reduced**: ~500-700 LOC (through better organization)
**Benefit**: Better maintainability, testability, regenerability

### Phase 3: Advanced Patterns (3-4 weeks)
**Priority**: Lower priority, nice-to-have

1. **Add API validation layer** (3-4 days)
   - Validate Azure SDK calls
   - Add model verification
   - Improve error messages

2. **Implement comprehensive testing** (1-2 weeks)
   - Unit tests for helpers
   - Integration tests for commands
   - TDD pyramid (60% unit, 30% integration, 10% E2E)

3. **Add performance monitoring** (2-3 days)
   - Track command execution time
   - Identify bottlenecks
   - Add telemetry

**Total Effort**: 12-17 days
**Benefit**: Production-ready quality, comprehensive test coverage

---

## File-Specific Recommendations

### monitoring.py (1735 LOC) - Highest Priority
**Current Issues**:
- 8 commands in one file (should be separate)
- 35 try blocks (complex error handling)
- 20+ resource group checks

**Recommended Split**:
```
src/azlin/commands/monitoring/
├── __init__.py           # Public API (__all__ exports)
├── status.py            # status command (200 LOC)
├── list.py              # list_command (400 LOC)
├── session.py           # session_command (150 LOC)
├── w.py                 # w command (100 LOC)
├── top.py               # top command (400 LOC)
├── ps.py                # ps command (200 LOC)
├── os_update.py         # os_update command (150 LOC)
├── cost.py              # cost command (100 LOC)
└── helpers.py           # Shared monitoring helpers (135 LOC)
```
**Effort**: 2-3 days
**Benefit**: Each command testable in isolation

### connectivity.py (1603 LOC) - High Priority
**Current Issues**:
- 6 commands in one file
- Complex connect logic (400+ LOC)
- Duplicated `_get_ssh_config_for_vm`

**Recommended Split**:
```
src/azlin/commands/connectivity/
├── __init__.py           # Public API
├── connect.py           # connect command (500 LOC)
├── code.py              # code_command (200 LOC)
├── update.py            # update command (200 LOC)
├── sync.py              # sync command (250 LOC)
├── sync_keys.py         # sync_keys command (150 LOC)
├── cp.py                # cp command (250 LOC)
└── helpers.py           # Shared connectivity helpers (53 LOC)
```
**Effort**: 2-3 days

### provisioning.py (1216 LOC) - Medium Priority
**Current Issues**:
- Mix of provisioning and helper menu logic
- Duplicated `progress_callback`

**Recommended Split**:
```
src/azlin/commands/provisioning/
├── __init__.py           # Public API
├── new.py               # new_command (400 LOC)
├── clone.py             # clone command (300 LOC)
├── help.py              # help_command (200 LOC)
├── menu.py              # Interactive menu logic (200 LOC)
└── helpers.py           # Shared provisioning helpers (116 LOC)
```
**Effort**: 1-2 days

---

## Architecture Alignment with PATTERNS.md

### ✅ Well-Aligned Patterns
1. **Bricks & Studs Module Design** - All files use `__all__`
2. **Zero-BS Implementation** - No stub code found
3. **Platform-Specific Installation Guidance** - Used in restore.py

### ⚠️  Partially Aligned Patterns
1. **Safe Subprocess Wrapper** - Pattern defined but not used
2. **Fail-Fast Prerequisite Checking** - Pattern defined but not implemented
3. **Resilient Batch Processing** - Pattern defined but not applied

### ❌ Missing Patterns
1. **API Validation Before Implementation** - No validation layer
2. **Intelligent Caching** - No cache management in commands
3. **TDD Testing Pyramid** - Tests exist but not following pyramid

---

## Estimated Effort Summary

| Phase | Tasks | Effort | Lines Reduced | Priority |
|-------|-------|--------|---------------|----------|
| **Phase 1** | Quick wins (decorators, extraction) | 5-6 days | 200-300 | HIGH |
| **Phase 2** | Split large files, add patterns | 8-12 days | 500-700 | MEDIUM |
| **Phase 3** | Advanced patterns, testing | 12-17 days | N/A | LOW |
| **TOTAL** | All phases | 25-35 days | 700-1000 | - |

### Recommended Approach
**Incremental refactoring** - Start with Phase 1 (high impact, low effort):
1. Week 1: Extract duplicated functions, create shared utilities
2. Week 2: Implement decorators, standardize error handling
3. Week 3-4: Split largest files (monitoring.py, connectivity.py)
4. Week 5-6: Add missing patterns (fail-fast, resilient batch)
5. Week 7+: Testing and validation

---

## Philosophy Compliance Score

**Overall**: 7/10 ⚠️

| Principle | Score | Notes |
|-----------|-------|-------|
| Ruthless Simplicity | 6/10 | Large files violate simplicity |
| Modular Design | 8/10 | Good module boundaries, but too coarse |
| Zero-BS Implementation | 10/10 | No stubs/placeholders found |
| DRY Principle | 4/10 | Significant duplication |
| Error Handling | 5/10 | Inconsistent patterns |
| Testing | 6/10 | Tests exist but incomplete |
| Documentation | 7/10 | Good module docs, inconsistent function docs |

**Strengths**:
- ✅ Clean decomposition from original cli.py
- ✅ Clear public APIs via `__all__`
- ✅ Working code (no stubs)

**Weaknesses**:
- ❌ Code duplication (6 duplicated functions)
- ❌ Large files violate single responsibility
- ❌ Missing PATTERNS.md patterns (safe subprocess, fail-fast, resilient batch)

---

## Next Steps

1. **Review this analysis** with team
2. **Prioritize Phase 1 tasks** (highest ROI)
3. **Create tracking issues** for each refactoring task
4. **Assign ownership** (one file per developer)
5. **Set milestone**: Complete Phase 1 in 2-3 weeks

---

## Appendix: Metrics

### File Size Distribution
```
>1500 LOC: 2 files (monitoring.py, connectivity.py)
1000-1500 LOC: 3 files (provisioning.py, storage.py, restore.py)
500-1000 LOC: 4 files (lifecycle.py, auth.py, context.py, autopilot.py)
<500 LOC: 18 files
```

### Complexity Metrics
```
Total functions: 200
Total classes: 6
Avg functions per file: 7.4
Subprocess calls: 13
Error messages: 354
Exit points: 493
Import statements: ~400 (estimated)
```

### Duplication Metrics
```
Exact duplicates: 6 functions
Similar patterns: 20+ (config access, error handling)
Repeated code blocks: 30+ (try-except patterns)
Estimated duplicated LOC: 500-700
```

---

**Generated by**: Claude Code Pattern Analysis
**Methodology**: Static analysis + manual code review
**Files analyzed**: 27 Python modules (14,594 LOC)
**Analysis time**: ~45 minutes
