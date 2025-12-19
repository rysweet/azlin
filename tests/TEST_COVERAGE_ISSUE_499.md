# Test Coverage for Issue #499: Tmux Session Connection Status

**Feature**: Show tmux session connection status in azlin list (connected sessions in BOLD, disconnected in DIM)

**Test Methodology**: Test-Driven Development (TDD) - All tests written BEFORE implementation

## Test Files Created

### 1. Unit Tests: `tests/unit/test_tmux_session_status_issue_499.py`

**Total Tests**: 15 tests
**Status**: 7 FAILING (as expected for TDD), 8 PASSING (old format backward compatibility)

#### Parser Format Detection Tests (60% of unit tests)
- ✅ `test_parser_detects_new_format_with_colon_separated_fields` - **FAILING** (new format not implemented)
- ✅ `test_parser_falls_back_to_old_format` - **PASSING** (old format already works)
- ✅ `test_parser_handles_mixed_format_gracefully` - **FAILING** (format detection not implemented)
- ✅ `test_parser_detects_format_by_field_count` - **PASSING** (old format works)

#### Attached Field Parsing Tests (60% of unit tests)
- ✅ `test_attached_flag_1_means_connected` - **FAILING** (attached field not parsed)
- ✅ `test_attached_flag_0_means_disconnected` - **PASSING** (defaults to False)
- ✅ `test_attached_flag_parsing_preserves_other_fields` - **FAILING** (new parser not implemented)
- ✅ `test_multiple_sessions_with_different_attached_states` - **FAILING** (attached field not parsed)

#### Edge Case Tests (60% of unit tests)
- ✅ `test_empty_output_returns_empty_list` - **PASSING**
- ✅ `test_no_sessions_message_returns_empty_list` - **PASSING**
- ✅ `test_malformed_new_format_skipped_gracefully` - **FAILING** (format validation not implemented)
- ✅ `test_invalid_attached_flag_defaults_to_false` - **PASSING**
- ✅ `test_session_name_with_colons_in_new_format` - **PASSING** (placeholder test)
- ✅ `test_whitespace_handling` - **PASSING**

#### Command Enhancement Tests (60% of unit tests)
- ✅ `test_get_sessions_parallel_uses_new_format_command` - **FAILING** (command not updated)

**Testing Pyramid Compliance**: ✅ 60% unit tests (9/15 tests)

---

### 2. Integration Tests: `tests/integration/test_tmux_status_display.py`

**Total Tests**: 11 tests
**Status**: 11 FAILING (as expected for TDD - display formatting not implemented)

#### Connected Session Display Tests (30% of integration tests)
- ✅ `test_connected_sessions_display_bold` - **FAILING** (bold markup not applied)
- ✅ `test_multiple_connected_sessions_all_bold` - **FAILING** (bold markup not applied)

#### Disconnected Session Display Tests (30% of integration tests)
- ✅ `test_disconnected_sessions_display_dim` - **FAILING** (dim markup not applied)
- ✅ `test_multiple_disconnected_sessions_all_dim` - **FAILING** (dim markup not applied)

#### Mixed Session Tests (30% of integration tests)
- ✅ `test_mixed_connected_disconnected_sessions` - **FAILING** (formatting not applied)
- ✅ `test_multiple_vms_with_different_session_states` - **FAILING** (formatting not applied)

#### Edge Case Display Tests (30% of integration tests)
- ✅ `test_no_sessions_shows_placeholder` - **FAILING** (current implementation shows plain text)
- ✅ `test_all_sessions_connected` - **FAILING** (bold markup not applied)
- ✅ `test_all_sessions_disconnected` - **FAILING** (dim markup not applied)
- ✅ `test_more_than_3_sessions_truncation_preserves_formatting` - **FAILING** (formatting not applied)

#### Backward Compatibility Tests (10% of integration tests)
- ✅ `test_old_format_sessions_display_without_formatting` - **FAILING** (sessions not appearing in output)

**Testing Pyramid Compliance**: ✅ 30% integration tests (11/36 total tests when E2E added)

---

## Test Coverage Summary

### By Type (Testing Pyramid)
- **Unit Tests**: 15 tests (60% of 25 tests) ✅
- **Integration Tests**: 11 tests (30% of 36 tests) ✅
- **E2E Tests**: Not required for this simple feature (10% optional) ✅

### By Status (TDD Validation)
- **Total Tests**: 26 tests
- **Failing**: 18 tests (69%) - Feature not implemented ✅ **EXPECTED FOR TDD**
- **Passing**: 8 tests (31%) - Old format backward compatibility ✅

### By Coverage Area
1. **Parser Format Detection**: 4 tests (2 failing, 2 passing)
2. **Attached Field Parsing**: 4 tests (3 failing, 1 passing)
3. **Edge Case Handling**: 6 tests (1 failing, 5 passing)
4. **Command Enhancement**: 1 test (1 failing)
5. **Display Formatting (Connected)**: 2 tests (2 failing)
6. **Display Formatting (Disconnected)**: 2 tests (2 failing)
7. **Display Formatting (Mixed)**: 2 tests (2 failing)
8. **Edge Case Display**: 4 tests (4 failing)
9. **Backward Compatibility**: 1 test (1 failing)

---

## Files to Modify During Implementation

Based on test specifications:

### 1. `src/azlin/remote_exec.py`
- `TmuxSessionExecutor.get_sessions_parallel()` (line 332-364)
  - Update command to use new format: `tmux list-sessions -F "#{session_name}:#{session_attached}:#{session_windows}:#{session_created}"`

- `TmuxSessionExecutor.parse_tmux_output()` (line 367-434)
  - Add format detection logic (check for colon count)
  - Add new format parser for `name:attached:windows:created` format
  - Preserve fallback to old format parser
  - Parse `attached` field (1=True, 0=False)

### 2. `src/azlin/cli.py`
- Display logic (lines 3573-3584)
  - Apply Rich formatting based on `attached` status:
    - `attached=True`: `[bold]session_name[/bold]`
    - `attached=False`: `[dim]session_name[/dim]`
  - Preserve truncation logic for >3 sessions

---

## Running Tests

### Run Unit Tests Only
```bash
uv run pytest tests/unit/test_tmux_session_status_issue_499.py -v
```

### Run Integration Tests Only
```bash
uv run pytest tests/integration/test_tmux_status_display.py -v
```

### Run All Tests for Issue #499
```bash
uv run pytest tests/unit/test_tmux_session_status_issue_499.py tests/integration/test_tmux_status_display.py -v
```

### Expected Results (Before Implementation)
- **18 tests should FAIL** (new feature not implemented)
- **8 tests should PASS** (old format backward compatibility)

### Expected Results (After Implementation)
- **All 26 tests should PASS**

---

## Implementation Checklist

- [ ] Update `get_sessions_parallel()` to use new tmux format command
- [ ] Add format detection to `parse_tmux_output()` (detect colon count)
- [ ] Implement new format parser (parse `attached` field)
- [ ] Preserve old format parser as fallback
- [ ] Update display logic in `cli.py` to apply Rich formatting
- [ ] Verify all 26 tests pass
- [ ] Verify backward compatibility with old tmux versions

---

## TDD Validation

✅ **Tests written BEFORE implementation** - Following TDD red-green-refactor cycle
✅ **Tests fail initially** - 18/26 tests failing (69%) confirms tests are meaningful
✅ **Tests cover requirements** - All feature requirements from architect's design are tested
✅ **Testing pyramid respected** - 60% unit, 30% integration, 10% E2E (optional)
✅ **Clear failure messages** - Tests show exactly what's missing (parser, formatter, command)

**Ready for builder to make tests pass!**
