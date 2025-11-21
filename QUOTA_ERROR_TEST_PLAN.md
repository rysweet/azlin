# Test Plan: Quota Error Handling

## Issue #380: Improve quota error handling with clear, actionable messages

This test plan documents testing of the quota error handling improvement.

## Prerequisites

Since simulating quota errors requires either:
1. Actually exhausting quota (expensive, disruptive)
2. Mocking Azure CLI responses

We use **unit tests** for comprehensive coverage and **optional manual testing** for real-world validation.

## Automated Testing (Primary)

### Unit Tests ✅

**Run all quota error tests**:
```bash
uv run pytest tests/unit/test_vm_provisioning_quota_errors.py -v
```

**Expected**: All 13 tests pass

**Test Coverage**:
1. Quota error detection from JSON and plain text
2. Quota detail parsing (region, limit, usage, requested)
3. User-friendly message formatting
4. VM size suggestions algorithm
5. Graceful handling of malformed errors
6. Backward compatibility for non-quota errors

## Manual Testing (Optional)

### Scenario 1: Simulate Quota Error Response

Since you reported the actual error, we can verify the fix handles it correctly.

**Test**: Run unit test with your exact error message

```bash
# The tests already include your error format
uv run pytest tests/unit/test_vm_provisioning_quota_errors.py::TestQuotaExceededErrorMessages::test_quota_exceeded_error_shows_clear_message -v
```

**Expected Output**:
```
PASSED - Quota error properly formatted with:
  - Region: westus2
  - Limit: 100 cores
  - Usage: 96 cores
  - Requested: 16 cores
  - Suggestions: smaller VM sizes
  - Link: aka.ms/azquotaincrease
```

### Scenario 2: Integration Test with Mock (Optional)

**Purpose**: Verify the fix integrates correctly into vm_provisioning flow

```bash
# Run VM provisioning tests (if they exist)
uv run pytest tests/unit/test_vm_provisioning.py -k quota -v
```

## Verification Checklist

- [x] **Unit tests pass**: 13/13 quota error tests passing
- [x] **Pre-commit hooks pass**: All checks passing
- [x] **No regressions**: Existing error handling tests still pass
- [x] **Error message clear**: No stack traces in formatted output
- [x] **Suggestions provided**: Alternative VM sizes suggested
- [x] **Documentation link**: Azure quota increase URL included

## Manual Validation (If Desired)

To test with real Azure quota error:

1. **Find a region near quota limit** (check Azure Portal)
2. **Try to create VM that exceeds quota**:
   ```bash
   uvx --from git+https://github.com/rysweet/azlin@fix/issue-380-quota-error-handling azlin new --size L --region westus2
   ```

3. **Verify error message**:
   - Should show clear quota error (not stack trace)
   - Should include current usage/limit
   - Should suggest smaller sizes
   - Should include quota increase link

4. **Try suggested size**:
   ```bash
   uvx --from git+https://github.com/rysweet/azlin@fix/issue-380-quota-error-handling azlin new --size M --region westus2
   ```

**Expected**: VM creation succeeds with smaller size

## Success Criteria

The bug is fixed when:
- ✅ Quota errors show clear, formatted messages (not Python stack traces)
- ✅ Error includes region, VM size, current usage, limit, requested cores
- ✅ Alternative VM sizes are suggested
- ✅ Link to quota increase documentation provided
- ✅ Non-quota errors still handled normally
- ✅ All existing tests pass (no regressions)

## Notes

- Unit tests provide comprehensive coverage for quota error scenarios
- Real quota errors are rare in testing (hard to reproduce reliably)
- The implementation handles both JSON and plain text Azure error formats
- Graceful degradation: if parsing fails, shows original error (safe fallback)
