# Azure CLI Visibility Tests (TDD Approach)

## Test Coverage for Issue #236

This test suite provides comprehensive failing tests (TDD approach) for Azure CLI command visibility and progress indicators.

## Test File Location
`tests/unit/test_azure_cli_visibility.py`

## Test Coverage Summary

### UNIT TESTS (60% - 45 tests)

#### 1. CommandSanitizer Tests (14 tests)
- ✓ `test_sanitize_password_flag` - Password flag sanitization
- ✓ `test_sanitize_password_short_flag` - Short form password sanitization
- ✓ `test_sanitize_client_secret` - Client secret sanitization
- ✓ `test_sanitize_account_key` - Storage account key sanitization
- ✓ `test_sanitize_sas_token` - SAS token sanitization
- ✓ `test_sanitize_connection_string` - Connection string sanitization
- ✓ `test_sanitize_token_flag` - Generic token sanitization
- ✓ `test_sanitize_multiple_secrets` - Multiple secrets in one command
- ✓ `test_sanitize_equals_notation` - --flag=value notation
- ✓ `test_sanitize_no_secrets` - Commands without secrets unchanged
- ✓ `test_sanitize_empty_command` - Empty command handling
- ✓ `test_sanitize_custom_patterns` - Custom sanitization patterns
- ✓ `test_sanitize_preserves_order` - Argument order preservation
- ✓ `test_sanitize_case_insensitive` - Case insensitive matching

#### 2. ProgressIndicator Tests (9 tests)
- ✓ `test_progress_start` - Starting progress indicator
- ✓ `test_progress_update` - Updating progress
- ✓ `test_progress_stop_success` - Stopping with success
- ✓ `test_progress_stop_failure` - Stopping with failure
- ✓ `test_progress_elapsed_time` - Elapsed time tracking
- ✓ `test_progress_cannot_start_twice` - Double start protection
- ✓ `test_progress_cannot_update_when_not_active` - Update validation
- ✓ `test_progress_cannot_stop_when_not_active` - Stop validation
- ✓ `test_progress_clear_history` - History clearing

#### 3. TTYDetection Tests (7 tests)
- ✓ `test_is_tty_when_stdout_is_terminal` - TTY detection
- ✓ `test_is_not_tty_when_stdout_redirected` - Redirect detection
- ✓ `test_is_not_tty_in_ci_environment` - CI environment detection
- ✓ `test_is_not_tty_in_github_actions` - GitHub Actions detection
- ✓ `test_supports_color_in_tty` - Color support detection
- ✓ `test_no_color_when_no_color_env_set` - NO_COLOR env var
- ✓ `test_term_dumb_disables_features` - TERM=dumb handling

#### 4. CommandDisplayFormatter Tests (4 tests)
- ✓ `test_format_simple_command` - Simple command formatting
- ✓ `test_format_command_with_long_args` - Long command wrapping
- ✓ `test_format_adds_color_in_tty` - Color code addition
- ✓ `test_format_no_color_in_non_tty` - Non-TTY plain output

#### 5. ThreadSafety Tests (2 tests)
- ✓ `test_progress_indicator_thread_safe` - Concurrent progress updates
- ✓ `test_command_sanitizer_thread_safe` - Concurrent sanitization

### INTEGRATION TESTS (30% - 11 tests)

#### 6. AzureCLIVisibilityWorkflow Tests (9 tests)
- ✓ `test_display_command_before_execution` - Command display timing
- ✓ `test_sanitize_secrets_in_display` - Display sanitization
- ✓ `test_progress_indicator_lifecycle` - Complete lifecycle
- ✓ `test_command_failure_handling` - Failure handling
- ✓ `test_user_cancellation_handling` - Ctrl+C handling
- ✓ `test_tty_vs_non_tty_output` - TTY vs non-TTY output
- ✓ `test_timeout_handling` - Command timeout
- ✓ `test_multiple_commands_in_sequence` - Sequential execution
- ✓ `test_progress_updates_during_execution` - Live updates

#### 7. ProgressIndicatorIntegration Tests (2 tests)
- ✓ `test_progress_updates_during_execution` - Live progress
- ✓ `test_progress_indicator_cleanup_on_error` - Error cleanup

### E2E TESTS (10% - 2 tests)

#### 8. EndToEndVisibility Tests (2 tests)
- ✓ `test_complete_vm_creation_workflow` - Full workflow
- ✓ `test_error_recovery_workflow` - Error recovery

### EDGE CASES & BOUNDARY TESTS (11 tests)

#### 9. EdgeCases Tests (11 tests)
- ✓ `test_very_long_command_display` - Very long commands
- ✓ `test_empty_command_sanitization` - Empty commands
- ✓ `test_single_element_command` - Single element
- ✓ `test_null_bytes_in_command` - Null byte handling
- ✓ `test_unicode_in_command` - Unicode characters
- ✓ `test_rapid_progress_updates` - Rapid updates
- ✓ `test_zero_timeout` - Zero timeout
- ✓ `test_negative_timeout` - Negative timeout
- ✓ `test_command_with_special_characters` - Special chars
- ✓ `test_extremely_long_password` - Long password sanitization

### ERROR HANDLING TESTS (5 tests)

#### 10. ErrorHandling Tests (5 tests)
- ✓ `test_subprocess_not_found` - Command not found
- ✓ `test_permission_denied` - Permission errors
- ✓ `test_keyboard_interrupt_cleanup` - Ctrl+C cleanup
- ✓ `test_invalid_command_structure` - Invalid input
- ✓ `test_sanitizer_with_none_value` - None handling

### PERFORMANCE TESTS (2 tests)

#### 11. Performance Tests (2 tests)
- ✓ `test_sanitizer_performance` - Sanitizer performance
- ✓ `test_progress_update_performance` - Progress performance

## Total Test Count
**73 comprehensive tests** covering all requirements

## Expected Implementation Structure

These tests expect the following modules to be implemented:

```python
azlin.azure_cli_visibility
├── CommandSanitizer         # Sanitizes sensitive data from commands
├── ProgressIndicator        # Manages progress display lifecycle
├── TTYDetector             # Detects TTY vs non-TTY environments
├── CommandDisplayFormatter  # Formats commands for display
├── AzureCLIExecutor        # Main executor with visibility
└── ProgressError           # Exception for progress errors
```

## Running the Tests

### Run all visibility tests:
```bash
pytest tests/unit/test_azure_cli_visibility.py -v
```

### Run specific test classes:
```bash
# Unit tests only
pytest tests/unit/test_azure_cli_visibility.py::TestCommandSanitizer -v

# Integration tests only
pytest tests/unit/test_azure_cli_visibility.py::TestAzureCLIVisibilityWorkflow -v

# E2E tests only
pytest tests/unit/test_azure_cli_visibility.py::TestEndToEndVisibility -v
```

### Run with coverage:
```bash
pytest tests/unit/test_azure_cli_visibility.py --cov=azlin.azure_cli_visibility --cov-report=html
```

## Test Execution Timeline

Since this is a TDD approach:

1. **Currently**: All tests should FAIL (module not implemented)
2. **During development**: Tests gradually pass as features are implemented
3. **Completion**: All tests pass when feature is complete

## Implementation Order (Recommended)

Follow this order to implement features based on test dependencies:

### Phase 1: Core Components (Unit Tests)
1. Implement `CommandSanitizer` (14 tests)
2. Implement `TTYDetector` (7 tests)
3. Implement `CommandDisplayFormatter` (4 tests)
4. Implement `ProgressIndicator` (9 tests)

### Phase 2: Integration (Integration Tests)
5. Implement `AzureCLIExecutor` (11 tests)
6. Add thread safety (2 tests)

### Phase 3: Edge Cases & Polish
7. Handle edge cases (11 tests)
8. Add error handling (5 tests)
9. Optimize performance (2 tests)

### Phase 4: End-to-End
10. Validate complete workflows (2 tests)

## Key Requirements Tested

### 1. Command Display (Issue #236 Requirement)
- Commands displayed before execution
- Sanitized output for security
- Proper formatting for TTY/non-TTY

### 2. Sensitive Data Sanitization (Security Requirement)
- Passwords, secrets, tokens redacted
- Multiple sanitization patterns
- Preserves original command for execution

### 3. Progress Indicator Lifecycle (UX Requirement)
- Start, update, stop operations
- Elapsed time tracking
- Error state handling

### 4. TTY vs Non-TTY Mode (Compatibility Requirement)
- Detects terminal vs redirect
- Adjusts output accordingly
- CI/CD environment detection

### 5. Error Handling (Reliability Requirement)
- Command failures
- User cancellation (Ctrl+C)
- Timeout handling
- Permission errors

### 6. Thread Safety (Concurrency Requirement)
- Safe concurrent operations
- No race conditions
- Proper locking

## Security Considerations

These tests ensure:
- **No credential leakage** in command display
- **Sanitization before logging** to prevent exposure
- **Original commands preserved** for subprocess (not sanitized in execution)
- **Thread-safe operations** to prevent data corruption

## Performance Expectations

Tests validate:
- Sanitization: < 1ms per command (1000 ops in < 1s)
- Progress updates: < 1ms per update (100 ops in < 0.1s)
- No significant overhead on command execution

## Contributing

When adding new features:
1. Write failing tests first (TDD)
2. Implement feature to pass tests
3. Ensure all tests pass
4. Update this README with new test count

## Test Maintenance

- Keep tests fast (< 1s each)
- Mock external dependencies
- Use parametrize for similar test cases
- Keep test names descriptive
- Group tests by functionality
