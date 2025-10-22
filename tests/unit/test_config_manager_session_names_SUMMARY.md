# Session Name Resolution Bug Fix Tests (Issue #160)

## Test Coverage Summary

Comprehensive failing tests written for TDD approach to fixing session name resolution bugs.

**Test File**: `/Users/ryan/src/azlin/tests/unit/test_config_manager_session_names.py`

**Test Results**: 13 failed, 17 passed, 2 skipped (Expected - tests written before fix)

---

## Bug Context

The session name resolution system has three critical bugs:

1. **Self-referential mappings**: `simserv = "simserv"` causes lookup failures
2. **Duplicate session names**: Multiple VMs pointing to same session name creates ambiguity
3. **Wrong VM name returns**: `get_vm_name_by_session()` returns incorrect results

---

## Test Categories

### 1. Validation Tests (8 tests)

**Purpose**: Prevent invalid mappings from being set

| Test | Status | Description |
|------|--------|-------------|
| `test_reject_self_referential_mapping` | FAIL | Should reject vm_name == session_name |
| `test_reject_duplicate_session_name_different_vm` | FAIL | Should reject duplicate session names |
| `test_allow_duplicate_session_name_same_vm` | PASS | Should allow updating same VM |
| `test_allow_changing_session_name_for_vm` | PASS | Should allow changing VM's session |
| `test_reject_vm_name_as_session_name_for_different_vm` | FAIL | Should reject using VM name as session |
| `test_reject_empty_session_name` | FAIL | Should reject empty strings |
| `test_reject_whitespace_only_session_name` | FAIL | Should reject whitespace |
| `test_accept_valid_session_name` | PASS | Should accept valid names |

**Critical Failures** (6):
- No validation for self-referential mappings
- No validation for duplicate session names
- No validation for VM name conflicts
- No validation for empty/whitespace names

---

### 2. Lookup Tests (6 tests)

**Purpose**: Handle invalid entries gracefully during lookups

| Test | Status | Description |
|------|--------|-------------|
| `test_lookup_skips_self_referential_entry` | FAIL | Should return None for self-referential |
| `test_lookup_with_multiple_matches_returns_none` | FAIL | Should return None for duplicates |
| `test_lookup_valid_session_name_works` | PASS | Should work for valid entries |
| `test_lookup_nonexistent_session_returns_none` | PASS | Should return None for not found |
| `test_lookup_with_mixed_valid_invalid_entries` | FAIL | Should filter invalid entries |
| `test_lookup_by_vm_name_directly_returns_none` | PASS | Should not resolve VM names |

**Critical Failures** (3):
- Returns self-referential mappings (should skip)
- Returns first match for duplicates (should detect ambiguity)
- Doesn't filter invalid entries

---

### 3. Config Migration Tests (3 tests)

**Purpose**: Load and clean up corrupted configs

| Test | Status | Description |
|------|--------|-------------|
| `test_load_config_with_self_referential_entry` | PASS | Should load without crashing |
| `test_load_config_with_duplicate_session_names` | PASS | Should load without crashing |
| `test_validate_session_names_method_detects_issues` | SKIP | Method not implemented |
| `test_cleanup_invalid_session_names_method` | SKIP | Method not implemented |

**Skipped** (2):
- Validation method doesn't exist yet
- Cleanup method doesn't exist yet

---

### 4. Edge Cases Tests (13 tests)

**Purpose**: Handle boundary conditions and special characters

| Test | Status | Description |
|------|--------|-------------|
| `test_none_session_name` | PASS | Should reject None |
| `test_numeric_session_name` | PASS | Should accept "123" |
| `test_very_long_session_name` | FAIL | Should reject >64 chars |
| `test_session_name_with_unicode` | FAIL | Should reject unicode |
| `test_session_name_case_sensitivity` | PASS | Should be case-sensitive |
| `test_session_name_starting_with_hyphen` | FAIL | Should reject "-dev" |
| `test_session_name_ending_with_hyphen` | FAIL | Should reject "dev-" |
| `test_delete_session_name_removes_entry` | PASS | Should delete correctly |
| `test_delete_nonexistent_session_name` | PASS | Should return False |
| `test_reject_session_name_with_invalid_characters` | FAIL | Should reject special chars |

**Critical Failures** (5):
- No length validation
- No unicode validation
- No character validation (hyphen positions, special chars)

---

### 5. Integration Tests (4 tests)

**Purpose**: End-to-end workflows

| Test | Status | Description |
|------|--------|-------------|
| `test_full_workflow_set_get_lookup` | PASS | Complete workflow works |
| `test_multiple_vms_with_unique_sessions` | PASS | Multiple VMs work |
| `test_update_session_name_updates_lookup` | PASS | Updates work correctly |
| `test_config_file_format_preserved` | PASS | TOML format preserved |

**All Passing**: Integration tests verify existing functionality works

---

## Test Breakdown by Priority

### High Priority (Must Fix)

1. **Self-referential validation** - Prevents `simserv = "simserv"`
2. **Duplicate detection** - Prevents multiple VMs with same session
3. **Lookup filtering** - Returns None for invalid entries
4. **Empty/whitespace validation** - Prevents invalid names

### Medium Priority (Should Fix)

5. **Character validation** - Alphanumeric, hyphen, underscore only
6. **Length validation** - Max 64 characters
7. **VM name conflicts** - Prevents session name == existing VM name
8. **Hyphen position validation** - No leading/trailing hyphens

### Low Priority (Nice to Have)

9. **Unicode rejection** - ASCII-only names
10. **Validation/cleanup methods** - Helper methods for maintenance

---

## Implementation Requirements

Based on failing tests, the fix should implement:

### 1. In `set_session_name()` method:

```python
def set_session_name(cls, vm_name: str, session_name: str, custom_path: str | None = None):
    # Add validation:
    # 1. Reject if vm_name == session_name (self-referential)
    # 2. Reject if session_name already used by different VM (duplicate)
    # 3. Reject if session_name matches existing VM name (conflict)
    # 4. Reject if empty or whitespace
    # 5. Reject if invalid characters
    # 6. Reject if too long (>64 chars)
    # 7. Reject if starts/ends with hyphen
    # 8. Reject if contains unicode
```

### 2. In `get_vm_name_by_session()` method:

```python
def get_vm_name_by_session(cls, session_name: str, custom_path: str | None = None):
    # Add filtering:
    # 1. Skip self-referential entries (vm_name == session_name)
    # 2. Detect duplicates (multiple VMs with same session)
    # 3. Return None for ambiguous lookups
    # 4. Filter out invalid entries
```

### 3. Optional helper methods:

```python
class AzlinConfig:
    def validate_session_names(self) -> list[str]:
        """Return list of validation issues found"""

    def cleanup_session_names(self) -> None:
        """Remove invalid session name entries"""
```

---

## Test Execution

```bash
# Run all session name tests
pytest tests/unit/test_config_manager_session_names.py -v

# Run specific test category
pytest tests/unit/test_config_manager_session_names.py::TestSessionNameValidation -v

# Run with coverage
pytest tests/unit/test_config_manager_session_names.py --cov=azlin.config_manager --cov-report=html
```

---

## Expected Behavior After Fix

### Current (Broken)
- ✗ Accepts `simserv = "simserv"`
- ✗ Accepts duplicate session names
- ✗ Returns self-referential mappings
- ✗ Returns arbitrary match for duplicates
- ✗ No character validation

### After Fix
- ✓ Rejects self-referential mappings
- ✓ Rejects duplicate session names
- ✓ Returns None for self-referential
- ✓ Returns None for duplicates (ambiguous)
- ✓ Validates characters, length, format

---

## Files Modified

1. **Test file created**: `tests/unit/test_config_manager_session_names.py`
2. **Implementation needed**: `src/azlin/config_manager.py`

---

## Coverage Statistics

- **Total tests**: 32
- **Failing tests**: 13 (40.6%)
- **Passing tests**: 17 (53.1%)
- **Skipped tests**: 2 (6.3%)

**Lines of test code**: ~600 lines
**Test categories**: 5
**Edge cases covered**: 13
**Integration scenarios**: 4

---

## Test Quality Metrics

- ✓ Clear test names describing expected behavior
- ✓ Comprehensive docstrings explaining bug context
- ✓ Parametrized where appropriate (multiple invalid characters)
- ✓ Fixtures for config file management
- ✓ Proper assertions with error messages
- ✓ Follows pytest best practices
- ✓ Follows existing azlin test patterns

---

## Next Steps

1. Run tests to verify they fail (Done)
2. Implement validation in `set_session_name()`
3. Implement filtering in `get_vm_name_by_session()`
4. Add helper validation methods (optional)
5. Run tests again - should pass
6. Update documentation
7. Create PR referencing issue #160
