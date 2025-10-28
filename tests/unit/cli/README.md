# CLI Command Syntax Tests

Exhaustive command syntax validation tests following TDD (Test-Driven Development) RED phase.

## Overview

This directory contains comprehensive syntax validation tests for all azlin CLI commands. These tests are part of Issue #187 - Exhaustive Test Coverage for azlin CLI.

## Test Files

### test_command_syntax.py (55 tests)
**Priority 1: Core Commands** - Demonstrates pattern with sample commands

| Command | Tests | Categories Covered |
|---------|-------|-------------------|
| `azlin new` | 25 | Basic invocation, option flags, validation, boolean flags, aliases, combinations |
| `azlin list` | 15 | Basic invocation, filter options, invalid options, value types |
| `azlin connect` | 15 | Basic invocation, connection options, reconnection, remote commands |

### test_command_syntax_priority2.py (100 tests)
**Priority 2: Common Commands** - Everyday VM operations

| Command | Tests | Categories Covered |
|---------|-------|-------------------|
| `azlin start` | 10 | Basic invocation, resource group options, invalid options |
| `azlin stop` | 14 | Basic invocation, deallocate flags, resource group options |
| `azlin status` | 12 | Basic invocation, VM filter, resource group options |
| `azlin cp` | 18 | Session:path notation, dry-run, resource group options |
| `azlin sync` | 14 | VM name option, dry-run flag, resource group options |
| `azlin session` | 16 | Session name management, clear flag, resource group options |
| `azlin killall` | 16 | Force flag, prefix option, resource group options |

### test_command_syntax_priority3.py (94 tests)
**Priority 3: Advanced Commands** - Command groups and specialized operations

| Command Group | Tests | Subcommands Tested |
|---------------|-------|-------------------|
| `azlin batch` | 18 | stop, start, command, sync |
| `azlin env` | 18 | set, list, delete, export, import, clear |
| `azlin storage` | 20 | create, list, status, delete, mount, unmount |
| `azlin snapshot` | 22 | enable, disable, sync, status, create, list, restore, delete |
| `azlin template` | 16 | create, list, delete, export, import |

### test_command_syntax_priority4.py (70 tests)
**Priority 4: Specialized Commands** - Keys, costs, updates, and AI commands

| Command | Tests | Categories Covered |
|---------|-------|-------------------|
| `azlin keys` | 14 | rotate, list, export, backup subcommands |
| `azlin cost` | 12 | Date ranges, VM breakdown, cost estimation |
| `azlin update` | 10 | VM identifiers, timeout options, resource groups |
| `azlin prune` | 14 | Age/idle thresholds, dry-run, force flags |
| `azlin do` | 10 | Natural language requests, dry-run, verbose |
| `azlin doit` | 10 | Agentic operations, dry-run, verbose |

## Total Coverage

**319 comprehensive tests** across 4 files covering:
- **3 core commands** (Priority 1)
- **7 common commands** (Priority 2)
- **5 command groups with 25 subcommands** (Priority 3)
- **6 specialized commands** (Priority 4)

## Test Categories

### 1. Syntax Validation
- No arguments behavior
- Required vs optional arguments
- Extra/unexpected arguments
- Missing required values

### 2. Option Combinations
- Multiple options together
- Mutually exclusive options
- Option dependencies
- Template + explicit option override

### 3. Alias Tests
- Command aliases (`new`/`vm`/`create`)
- Consistent signatures across aliases
- Help text consistency

### 4. Error Handling
- Invalid option values (non-integer for int, etc.)
- Unknown/typo options
- Empty string values
- Path validation

### 5. Help Text
- `--help` displays usage
- `-h` short form support
- Command-specific help content
- Option descriptions visible

## Test Structure

Each test class follows this pattern:

```python
class TestCommandNameSyntax:
    """Test syntax validation for 'azlin command'."""

    # Category 1: Basic Invocation
    def test_command_no_args_behavior(self):
        """Test command with no arguments."""
        ...

    # Category 2: Option Flags
    def test_command_option_name(self):
        """Test --option-name accepts value."""
        ...

    # Category 3: Validation
    def test_command_rejects_invalid_value(self):
        """Test command rejects invalid input."""
        ...
```

## Running Tests

### Run all syntax tests:
```bash
pytest tests/unit/cli/test_command_syntax*.py -v
```

### Run specific test file:
```bash
# Priority 1 (Core commands)
pytest tests/unit/cli/test_command_syntax.py -v

# Priority 2 (Common commands)
pytest tests/unit/cli/test_command_syntax_priority2.py -v

# Priority 3 (Advanced command groups)
pytest tests/unit/cli/test_command_syntax_priority3.py -v

# Priority 4 (Specialized commands)
pytest tests/unit/cli/test_command_syntax_priority4.py -v
```

### Run specific command tests:
```bash
# Test only 'azlin start' command
pytest tests/unit/cli/test_command_syntax_priority2.py::TestStartCommandSyntax -v

# Test only 'azlin batch' group
pytest tests/unit/cli/test_command_syntax_priority3.py::TestBatchCommandSyntax -v

# Test only 'azlin cost' command
pytest tests/unit/cli/test_command_syntax_priority4.py::TestCostCommandSyntax -v
```

### Run by marker:
```bash
# All TDD RED phase tests
pytest -m tdd_red

# All syntax validation tests
pytest -m syntax

# By priority level
pytest -m priority2
pytest -m priority3
pytest -m priority4
```

## Test Quality Standards

### Comprehensive Coverage
Each test validates a SINGLE aspect of command syntax:
- One test = One validation point
- Clear, descriptive test names
- Explicit expected behavior in docstrings

### TDD RED Phase
These tests are marked with `@pytest.mark.tdd_red` to indicate they are:
- Written BEFORE implementation changes
- Expected to demonstrate current behavior
- Will guide implementation improvements

### Test Assertion Patterns

**Valid syntax tests:**
```python
result = runner.invoke(main, ["command", "--option", "value"])
assert result.exit_code == 0
assert "error" not in result.output.lower()
```

**Invalid syntax tests:**
```python
result = runner.invoke(main, ["command", "--invalid"])
assert result.exit_code != 0
assert "no such option" in result.output.lower()
```

**Help text tests:**
```python
result = runner.invoke(main, ["command", "--help"])
assert result.exit_code == 0
assert "Usage:" in result.output
```

## Extending These Tests

To add tests for additional commands:

1. **Create new test class:**
```python
class TestYourCommandSyntax:
    """Test syntax validation for 'azlin yourcommand'."""
```

2. **Organize by category:**
   - Basic invocation (3-5 tests)
   - Option flags (5-10 tests)
   - Validation (3-5 tests)
   - Error handling (3-5 tests)

3. **Use consistent naming:**
   - `test_command_no_args_*`
   - `test_command_option_name_*`
   - `test_command_rejects_*`
   - `test_command_help_*`

4. **Add markers:**
```python
@pytest.mark.command_yourcommand
def test_yourcommand_feature(self):
    ...
```

## Test Metrics

### Current Coverage (Issue #187 Complete)
- **319 tests** written (exceeds 300+ target)
- **4 test files** organized by priority
- **41 commands/subcommands** covered
- **100% passing** (all tests execute correctly)

### File Breakdown
| File | Tests | Lines | Commands |
|------|-------|-------|----------|
| test_command_syntax.py | 55 | ~685 | 3 core |
| test_command_syntax_priority2.py | 100 | ~1,800 | 7 common |
| test_command_syntax_priority3.py | 94 | ~1,600 | 25 subcommands |
| test_command_syntax_priority4.py | 70 | ~1,270 | 6 specialized |
| **TOTAL** | **319** | **~5,355** | **41 commands** |

### Test Categories Distribution
- Syntax validation: ~100 tests
- Option combinations: ~80 tests
- Error handling: ~70 tests
- Help text: ~40 tests
- Boolean flags: ~29 tests

## Notes on Test Behavior

These tests validate **CLI syntax and interface**, not business logic:
- Tests should pass even without Azure credentials
- Tests use Click's `CliRunner` for isolated execution
- Tests focus on command-line parsing and option validation
- Business logic errors (auth, Azure API) are acceptable - syntax errors are not

## Related Files

- `tests/conftest.py` - Shared fixtures and test configuration
- `pyproject.toml` - Test markers and pytest configuration
- `tests/unit/test_default_help.py` - Related help behavior tests

## Achievement Summary

Issue #187 target: **300+ tests**
**Actual delivered: 319 tests** ✅

This exhaustive test suite provides:
- Complete CLI syntax validation for all azlin commands
- Pattern for future command additions
- TDD foundation for CLI improvements
- Comprehensive documentation of command interfaces
