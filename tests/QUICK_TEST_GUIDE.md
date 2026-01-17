# Quick Test Guide: Bastion Cleanup Tests

## TL;DR

```bash
# Run all cleanup tests
uv run pytest tests/unit/modules/test_ssh_reconnect_cleanup.py tests/integration/test_bastion_reconnect_integration.py -v

# Expected: 23 tests, currently ALL FAILING (by design - TDD)
# After implementation: 23 tests, ALL PASSING
```

## Test Files

1. **Unit Tests**: `tests/unit/modules/test_ssh_reconnect_cleanup.py` (14 tests)
2. **Integration Tests**: `tests/integration/test_bastion_reconnect_integration.py` (9 tests)

## Quick Commands

### Run Specific Test Suites

```bash
# Only unit tests (fast, <1s)
uv run pytest tests/unit/modules/test_ssh_reconnect_cleanup.py -v

# Only integration tests (<3s)
uv run pytest tests/integration/test_bastion_reconnect_integration.py -v

# All reconnect-related tests
uv run pytest tests -k "reconnect" -v

# Specific test by name
uv run pytest tests/unit/modules/test_ssh_reconnect_cleanup.py::TestSSHReconnectCleanupCallback::test_cleanup_called_before_reconnect_attempt -v
```

### Run with Coverage

```bash
# Coverage report
uv run pytest tests/unit/modules/test_ssh_reconnect_cleanup.py tests/integration/test_bastion_reconnect_integration.py --cov=azlin.modules.ssh_reconnect --cov=azlin.vm_connector --cov-report=term-missing

# HTML coverage report
uv run pytest tests/unit/modules/test_ssh_reconnect_cleanup.py tests/integration/test_bastion_reconnect_integration.py --cov=azlin.modules.ssh_reconnect --cov=azlin.vm_connector --cov-report=html
# Open htmlcov/index.html in browser
```

### Watch Mode (TDD)

```bash
# Install pytest-watch
uv pip install pytest-watch

# Watch for changes and re-run tests
uv run ptw tests/unit/modules/test_ssh_reconnect_cleanup.py -- -v
```

## Test Status Checklist

Use this checklist during implementation:

### Phase 1: SSHReconnectHandler Parameter (4 tests)
- [ ] `test_handler_accepts_cleanup_callback_parameter`
- [ ] `test_handler_accepts_none_cleanup_callback`
- [ ] `test_cleanup_callback_parameter_is_optional`
- [ ] `test_reconnect_works_without_cleanup_callback`

### Phase 2: Cleanup Invocation Logic (7 tests)
- [ ] `test_cleanup_not_called_on_first_connect`
- [ ] `test_cleanup_called_before_reconnect_attempt`
- [ ] `test_cleanup_called_on_each_reconnect_attempt`
- [ ] `test_cleanup_not_called_when_user_declines_reconnect`
- [ ] `test_cleanup_not_called_after_max_retries`
- [ ] `test_cleanup_not_called_on_normal_exit`
- [ ] `test_cleanup_not_called_on_ctrl_c_exit`

### Phase 3: Exception Handling (3 tests)
- [ ] `test_cleanup_exception_handled_gracefully`
- [ ] `test_cleanup_exception_logged`
- [ ] `test_cleanup_callback_invocation_order`

### Phase 4: VMConnector Integration (9 tests)
- [ ] `test_bastion_cleanup_callback_passed_to_reconnect_handler`
- [ ] `test_bastion_tunnel_closed_before_reconnect_attempt`
- [ ] `test_bastion_tunnel_closed_on_each_reconnect`
- [ ] `test_bastion_tunnel_not_closed_on_first_connect`
- [ ] `test_bastion_cleanup_error_logged_but_reconnect_continues`
- [ ] `test_no_bastion_cleanup_when_no_bastion_used`
- [ ] `test_no_cleanup_when_reconnect_disabled`
- [ ] `test_bastion_tunnel_passed_to_cleanup_callback`
- [ ] `test_bastion_cleanup_with_user_declined_reconnect`

## Expected Output

### Before Implementation (Current)
```
tests/unit/modules/test_ssh_reconnect_cleanup.py FFFFFFFFFFFF.F [100%]
tests/integration/test_bastion_reconnect_integration.py FFF.F..F. [100%]

============================== 23 failed in 2.45s ===============================
```

### After Implementation (Target)
```
tests/unit/modules/test_ssh_reconnect_cleanup.py .............. [100%]
tests/integration/test_bastion_reconnect_integration.py ......... [100%]

============================== 23 passed in 2.45s ===============================
```

## Debugging Failed Tests

### View Full Test Output
```bash
uv run pytest tests/unit/modules/test_ssh_reconnect_cleanup.py -vv
```

### Stop on First Failure
```bash
uv run pytest tests/unit/modules/test_ssh_reconnect_cleanup.py -x
```

### Show Print Statements
```bash
uv run pytest tests/unit/modules/test_ssh_reconnect_cleanup.py -s
```

### Run Last Failed Tests
```bash
uv run pytest --lf
```

### Run Specific Failed Test
```bash
uv run pytest tests/unit/modules/test_ssh_reconnect_cleanup.py::TestSSHReconnectCleanupCallback::test_cleanup_called_before_reconnect_attempt -vv
```

## Common Issues

### Issue: Tests still failing after implementation

**Solution**: Check implementation matches test expectations:

1. **Parameter name must be `cleanup_callback`**
   ```python
   def __init__(self, max_retries: int = 3, cleanup_callback: Optional[Callable[[], None]] = None):
   ```

2. **Callback must be called BEFORE reconnect**
   ```python
   # User wants to reconnect
   if self.cleanup_callback:
       try:
           self.cleanup_callback()
       except Exception as e:
           logger.warning(f"Cleanup callback failed: {e}")

   # Now reconnect
   exit_code = SSHConnector.connect(...)
   ```

3. **Callback must NOT be called on first connect**
   ```python
   if attempt == 0:  # First attempt
       # Don't call cleanup
   else:  # Reconnect attempt
       # Call cleanup
   ```

### Issue: Integration tests failing but unit tests passing

**Solution**: Check VMConnector integration:

1. **Verify callback is passed when Bastion is used**
   ```python
   if bastion_manager:
       cleanup_callback = lambda: bastion_manager.close_tunnel(bastion_tunnel)
       handler = SSHReconnectHandler(max_retries=max_reconnect_retries, cleanup_callback=cleanup_callback)
   ```

2. **Verify callback captures tunnel correctly**
   ```python
   # Capture tunnel in closure
   cleanup_callback = lambda: bastion_manager.close_tunnel(bastion_tunnel)
   ```

## Test Documentation

- **TEST_SUMMARY.md**: Overview of test strategy and status
- **TEST_COVERAGE_MATRIX.md**: Requirements → Tests mapping
- **This file**: Quick reference for running tests

## Success Criteria

✅ All 23 tests passing
✅ Coverage > 95% for new code
✅ Tests run in < 5 seconds total
✅ No skipped or xfailed tests
✅ All edge cases covered
