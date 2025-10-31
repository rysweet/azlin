# Quick Test Reference - Azure CLI Visibility

## Status: ALL TESTS PASSING ✓
**110 tests in 0.73s**

## Run Tests (Choose One)

### 1. Quick Way - Use Test Runner
```bash
./run_tests.sh tests/unit/test_azure_cli_visibility.py tests/unit/security/test_azure_command_sanitizer.py -v
```

### 2. Direct Way - Use Venv Python
```bash
/Users/ryan/src/TuesdayTmp/azlin/.venv/bin/python3 -m pytest \
  tests/unit/test_azure_cli_visibility.py \
  tests/unit/security/test_azure_command_sanitizer.py -v
```

## Common Commands

```bash
# Run all new module tests
./run_tests.sh tests/unit/test_azure_cli_visibility.py tests/unit/security/

# Run just visibility tests (65 tests)
./run_tests.sh tests/unit/test_azure_cli_visibility.py

# Run just sanitizer tests (45 tests)
./run_tests.sh tests/unit/security/test_azure_command_sanitizer.py

# Quiet mode (summary only)
./run_tests.sh tests/unit/ -q

# Verbose with line-level traceback
./run_tests.sh tests/unit/ -v --tb=line

# With coverage
./run_tests.sh tests/unit/ --cov=src/azlin --cov-report=term-missing
```

## Verify Imports

```bash
/Users/ryan/src/TuesdayTmp/azlin/.venv/bin/python3 -c "
from azlin.azure_cli_visibility import CommandSanitizer
from azlin.security.azure_command_sanitizer import AzureCommandSanitizer
print('✓ All imports work')
"
```

## Test Counts
- **azure_cli_visibility**: 65 tests
- **azure_command_sanitizer**: 45 tests
- **TOTAL**: 110 tests

## Files
- Production: `src/azlin/azure_cli_visibility.py`
- Production: `src/azlin/security/azure_command_sanitizer.py`
- Tests: `tests/unit/test_azure_cli_visibility.py`
- Tests: `tests/unit/security/test_azure_command_sanitizer.py`

## If Tests Fail

1. Check Python: `which python3` (should show venv path)
2. Reinstall: `uv pip install -e ".[dev]"`
3. Use venv Python: `/Users/ryan/src/TuesdayTmp/azlin/.venv/bin/python3`

## Key Paths
- **Venv Python**: `/Users/ryan/src/TuesdayTmp/azlin/.venv/bin/python3`
- **Working Dir**: `/Users/ryan/src/TuesdayTmp/azlin/worktrees/feat/issue-236-azure-ops-visibility`
- **Test Script**: `./run_tests.sh`

---
**Last Run**: 2025-10-31 | **Status**: ✓ PASSING | **Time**: 0.73s
