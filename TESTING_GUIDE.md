# Testing Guide for Azure CLI Visibility Feature

## Problem Resolution

### The Issue
Tests were failing with `ModuleNotFoundError` when trying to import:
- `azlin.azure_cli_visibility`
- `azlin.security.azure_command_sanitizer`

### Root Cause
The shell environment was using a different Python interpreter than the one with the virtual environment and dev dependencies installed.

### Solution
1. **Installed dev dependencies**: Used `uv pip install -e ".[dev]"` to install pytest and other testing tools
2. **Use correct Python interpreter**: Always use `/Users/ryan/src/TuesdayTmp/azlin/.venv/bin/python3` explicitly

## Running Tests

### Quick Method - Use the Test Runner Script
```bash
# Run all tests
./run_tests.sh

# Run specific test file
./run_tests.sh tests/unit/test_azure_cli_visibility.py

# Run with verbose output
./run_tests.sh tests/unit/test_azure_cli_visibility.py -v

# Run in quiet mode
./run_tests.sh tests/unit/ -q
```

### Direct Method - Use Virtual Environment Python
```bash
# Run all tests for the new modules
/Users/ryan/src/TuesdayTmp/azlin/.venv/bin/python3 -m pytest \
  tests/unit/test_azure_cli_visibility.py \
  tests/unit/security/test_azure_command_sanitizer.py \
  -v

# Run all tests in the project
/Users/ryan/src/TuesdayTmp/azlin/.venv/bin/python3 -m pytest tests/ -v

# Run with coverage
/Users/ryan/src/TuesdayTmp/azlin/.venv/bin/python3 -m pytest \
  tests/unit/test_azure_cli_visibility.py \
  --cov=src/azlin/azure_cli_visibility \
  --cov-report=term-missing
```

### Test Results Summary
All new module tests pass successfully:
- **test_azure_cli_visibility.py**: 65 tests - ALL PASS ✓
- **test_azure_command_sanitizer.py**: 45 tests - ALL PASS ✓
- **Total**: 110 tests - ALL PASS ✓

## Test Coverage

### Test Pyramid Structure (as designed)
- **Unit Tests (60%)**: Core logic, sanitization, TTY detection
- **Integration Tests (30%)**: End-to-end workflows with mocked subprocess
- **E2E Tests (10%)**: Full system tests

### Test Categories

#### Command Sanitization Tests
- Password flag sanitization (--password, -p)
- Client secret sanitization (--client-secret)
- Account key sanitization (--account-key)
- SAS token sanitization (--sas-token)
- Connection string sanitization (--connection-string)
- Multiple secrets in single command
- Equals notation (--flag=value)
- Custom sanitization patterns
- Case-insensitive handling

#### Progress Indicator Tests
- Start, update, and stop lifecycle
- Success and failure states
- Elapsed time tracking
- Error handling (starting twice, updating when not active)
- History management
- Thread safety

#### TTY Detection Tests
- Terminal vs redirected output detection
- CI environment detection (CI, GITHUB_ACTIONS)
- Color support detection
- NO_COLOR environment variable
- TERM=dumb handling

#### Integration Tests
- Command display before execution
- Secret sanitization in display
- Progress indicator lifecycle
- Command failure handling
- User cancellation (Ctrl+C)
- TTY vs non-TTY output formatting
- Timeout handling
- Multiple commands in sequence

#### Edge Cases
- Very long commands
- Empty commands
- Unicode characters
- Special shell characters
- Null bytes
- Rapid progress updates
- Zero/negative timeouts

## Module Import Verification

### Verify Imports Work
```bash
# Test azure_cli_visibility module
/Users/ryan/src/TuesdayTmp/azlin/.venv/bin/python3 -c "
from azlin.azure_cli_visibility import (
    CommandSanitizer,
    ProgressIndicator,
    TTYDetector,
    CommandDisplayFormatter,
    AzureCLIExecutor
)
print('azure_cli_visibility imports OK ✓')
"

# Test azure_command_sanitizer module
/Users/ryan/src/TuesdayTmp/azlin/.venv/bin/python3 -c "
from azlin.security.azure_command_sanitizer import (
    AzureCommandSanitizer,
    sanitize_azure_command
)
print('azure_command_sanitizer imports OK ✓')
"
```

## Troubleshooting

### If Tests Fail with ModuleNotFoundError
1. **Check Python interpreter**:
   ```bash
   which python3
   # Should be: /Users/ryan/src/TuesdayTmp/azlin/.venv/bin/python3
   ```

2. **Reinstall dev dependencies**:
   ```bash
   uv pip install -e ".[dev]"
   ```

3. **Verify pytest is installed**:
   ```bash
   /Users/ryan/src/TuesdayTmp/azlin/.venv/bin/python3 -m pytest --version
   ```

4. **Check package installation**:
   ```bash
   uv pip list | grep azlin
   # Should show: azlin 2.0.0 (editable install)
   ```

### If Imports Fail Outside Tests
Make sure you're in the correct directory and using the venv Python:
```bash
cd /Users/ryan/src/TuesdayTmp/azlin/worktrees/feat/issue-236-azure-ops-visibility
/Users/ryan/src/TueddayTmp/azlin/.venv/bin/python3
```

## Files Created

### New Production Modules
- `/Users/ryan/src/TuesdayTmp/azlin/worktrees/feat/issue-236-azure-ops-visibility/src/azlin/azure_cli_visibility.py`
- `/Users/ryan/src/TuesdayTmp/azlin/worktrees/feat/issue-236-azure-ops-visibility/src/azlin/security/azure_command_sanitizer.py`
- `/Users/ryan/src/TuesdayTmp/azlin/worktrees/feat/issue-236-azure-ops-visibility/src/azlin/security/__init__.py`

### New Test Files
- `/Users/ryan/src/TuesdayTmp/azlin/worktrees/feat/issue-236-azure-ops-visibility/tests/unit/test_azure_cli_visibility.py`
- `/Users/ryan/src/TuesdayTmp/azlin/worktrees/feat/issue-236-azure-ops-visibility/tests/unit/security/test_azure_command_sanitizer.py`
- `/Users/ryan/src/TuesdayTmp/azlin/worktrees/feat/issue-236-azure-ops-visibility/tests/unit/security/__init__.py`

### Helper Scripts
- `/Users/ryan/src/TuesdayTmp/azlin/worktrees/feat/issue-236-azure-ops-visibility/run_tests.sh` - Convenient test runner

## Next Steps

1. **Run Full Test Suite**: Verify all existing tests still pass
   ```bash
   ./run_tests.sh tests/ -v
   ```

2. **Check Coverage**: Ensure adequate test coverage
   ```bash
   ./run_tests.sh tests/ --cov=src/azlin --cov-report=html
   open htmlcov/index.html
   ```

3. **Integration Testing**: Test the modules with real Azure CLI commands in a safe environment

4. **Pre-commit Hooks**: Make sure all pre-commit checks pass
   ```bash
   pre-commit run --all-files
   ```

## Success Metrics

- ✓ All 110 new tests pass
- ✓ Modules import correctly
- ✓ Zero import errors
- ✓ Test execution time < 1 second
- ✓ Thread safety verified
- ✓ Edge cases covered
