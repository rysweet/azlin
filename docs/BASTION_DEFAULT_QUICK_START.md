# Bastion Default Feature - Quick Start Guide (TDD)
**Issue:** #237
**Testing Approach:** Test-Driven Development

---

## Overview

This guide helps you implement the Bastion Default feature using TDD. All tests are written and will guide your implementation.

**Status:** Tests written, implementation needed
**Tests Total:** ~90 tests across 3 levels
**Estimated Time:** 3 weeks

---

## Quick Start

### Run Tests to See What Needs Implementation

```bash
# See all failing tests
pytest tests/ -v

# Run specific test level
pytest tests/unit/test_bastion_default_behavior.py -v        # Unit
pytest tests/integration/test_bastion_default_integration.py -v  # Integration
pytest tests/e2e/test_bastion_default_e2e.py -v             # E2E
```

### TDD Cycle

1. **Pick a test** (start with unit tests)
2. **Run it** - should fail (Red)
3. **Implement** minimal code to pass
4. **Run it** - should pass (Green)
5. **Refactor** - improve code quality
6. **Repeat** with next test

---

## Test Files Created

### 1. Unit Tests (52 tests)
**File:** `tests/unit/test_bastion_default_behavior.py`

**What to implement:**
- Bastion detection logic
- User prompt handling
- VM provisioning with bastion
- Flag override behavior
- Config persistence
- Error handling
- Security validation

**Run:**
```bash
pytest tests/unit/test_bastion_default_behavior.py -v
```

### 2. Integration Tests (20 tests)
**File:** `tests/integration/test_bastion_default_integration.py`

**What to test:**
- Module interactions
- Complete workflows
- Config persistence across operations
- CLI integration
- Error recovery

**Run:**
```bash
pytest tests/integration/test_bastion_default_integration.py -v
```

### 3. E2E Tests (18 tests)
**File:** `tests/e2e/test_bastion_default_e2e.py`

**What to validate:**
- Acceptance criteria (AC1-AC5)
- Complete user workflows
- Error scenarios
- Performance
- Security compliance

**Run:**
```bash
pytest tests/e2e/test_bastion_default_e2e.py -v
```

---

## Implementation Order

### Phase 1: Detection (Week 1)

**Goal:** Implement bastion auto-detection

**Files to modify:**
- `src/azlin/modules/bastion_detector.py`

**Tests to pass:**
```bash
pytest tests/unit/test_bastion_default_behavior.py::TestBastionAutoDetection -v
```

**Key functions:**
- `detect_bastion_for_vm()` - Main detection logic
- `list_bastions()` - Query Azure API
- Error handling for Azure failures

**Success criteria:**
- 15 detection tests pass
- Graceful error handling
- Logging implemented

---

### Phase 2: User Prompts (Week 1)

**Goal:** Implement user interaction prompts

**Files to modify:**
- `src/azlin/vm_provisioning.py`
- `src/azlin/vm_connector.py`

**Tests to pass:**
```bash
pytest tests/unit/test_bastion_default_behavior.py::TestUserPromptBehavior -v
```

**Key features:**
- `click.confirm()` for user prompts
- Default values (yes for bastion)
- Cost information display
- User choice handling

**Success criteria:**
- 5 prompt tests pass
- User can accept/decline
- Cost info displayed

---

### Phase 3: VM Provisioning (Week 2)

**Goal:** Integrate bastion with VM provisioning

**Files to modify:**
- `src/azlin/vm_provisioning.py`
- `src/azlin/vm_connector.py`

**Tests to pass:**
```bash
pytest tests/unit/test_bastion_default_behavior.py::TestVMProvisioningWithBastion -v
pytest tests/unit/test_bastion_default_behavior.py::TestBastionFlagOverride -v
```

**Key features:**
- Skip public IP when using bastion
- Create public IP when declining bastion
- Flag override behavior (--no-bastion)
- Backward compatibility (--use-bastion)

**Success criteria:**
- 9 provisioning tests pass
- Flag behavior correct
- Backward compatible

---

### Phase 4: Config Persistence (Week 2)

**Goal:** Save and load bastion preferences

**Files to modify:**
- `src/azlin/modules/bastion_config.py` (already exists)

**Tests to pass:**
```bash
pytest tests/unit/test_bastion_default_behavior.py::TestBastionConfigPersistence -v
pytest tests/integration/test_bastion_default_integration.py::TestBastionConfigPersistence -v
```

**Key features:**
- Save VM-to-Bastion mappings
- Load preferences on next connection
- Secure file permissions (0600)
- Config merge and update

**Success criteria:**
- 6 config tests pass
- Config persists correctly
- Secure permissions enforced

---

### Phase 5: Integration (Week 2)

**Goal:** Test module interactions

**Files to verify:**
- All modules working together
- Complete workflows

**Tests to pass:**
```bash
pytest tests/integration/test_bastion_default_integration.py -v
```

**Key scenarios:**
- Detection + provisioning flow
- Connection with saved config
- CLI integration
- Error recovery
- Multi-VM scenarios

**Success criteria:**
- 20 integration tests pass
- No module conflicts
- Smooth workflows

---

### Phase 6: E2E Validation (Week 3)

**Goal:** Validate acceptance criteria

**Tests to pass:**
```bash
pytest tests/e2e/test_bastion_default_e2e.py -v
```

**Key validation:**
- AC1: Auto-detect bastion ✓
- AC2: Use automatically with confirmation ✓
- AC3: Prompt to create (default yes) ✓
- AC4: Allow decline for public IP ✓
- AC5: Backward compatibility ✓

**Success criteria:**
- 18 E2E tests pass
- All ACs validated
- User workflows smooth
- Performance acceptable

---

### Phase 7: Security Review (Week 3)

**Goal:** Pass all security tests

**Tests to pass:**
```bash
pytest tests/ -v -k security
```

**Security checklist:**
- No credentials in config ✓
- Config file permissions 0600 ✓
- Input validation (injection prevention) ✓
- Error message sanitization ✓
- Path traversal prevention ✓

**Success criteria:**
- All security tests pass
- No vulnerabilities found
- Security review approved

---

## Test Coverage

### Check Coverage

```bash
# Generate coverage report
pytest --cov=azlin.modules.bastion_detector \
       --cov=azlin.vm_provisioning \
       --cov=azlin.vm_connector \
       --cov-report=html \
       --cov-report=term-missing

# View HTML report
open htmlcov/index.html
```

### Coverage Requirements

**Minimum:** 90% for critical paths

**Critical paths:**
- Bastion detection: 95%+
- User prompts: 90%+
- VM provisioning: 95%+
- Flag handling: 100%
- Config persistence: 90%+
- Error handling: 85%+

---

## Common Test Patterns

### Pattern 1: Testing Detection

```python
def test_detection_scenario(self):
    # Arrange - Mock Azure response
    mock_bastions = [{"name": "test-bastion", "resourceGroup": "test-rg"}]

    # Act - Call detection
    with patch.object(BastionDetector, 'list_bastions', return_value=mock_bastions):
        result = BastionDetector.detect_bastion_for_vm("vm", "test-rg")

    # Assert - Verify result
    assert result is not None
    assert result["name"] == "test-bastion"
```

### Pattern 2: Testing User Prompts

```python
def test_prompt_scenario(self):
    # Arrange - Mock user input
    with patch('click.confirm', return_value=True) as mock_confirm:
        # Act - Trigger prompt
        result = mock_confirm("Use bastion?", default=True)

    # Assert - Verify prompt and result
    assert result is True
    mock_confirm.assert_called_once()
```

### Pattern 3: Testing Provisioning

```python
def test_provisioning_scenario(self):
    # Arrange - Mock Azure and detection
    with patch('subprocess.run') as mock_run:
        mock_run.return_value.stdout = '{"privateIpAddress": "10.0.0.4"}'

        # Act - Provision VM
        # Implementation calls subprocess

    # Assert - Verify correct command
    cmd = mock_run.call_args[0][0]
    assert "--public-ip-address" not in cmd  # No public IP
```

---

## Debugging Failed Tests

### Test Fails: "AttributeError: 'X' object has no attribute 'Y'"

**Cause:** Function/method not implemented
**Fix:** Implement the missing method

### Test Fails: "AssertionError: assert None is not None"

**Cause:** Function returns None instead of expected value
**Fix:** Return correct value from function

### Test Fails: "Mock not called"

**Cause:** Code path not executing expected logic
**Fix:** Check conditional logic, ensure code reaches mock

### Test Fails: "Expected X but got Y"

**Cause:** Incorrect implementation logic
**Fix:** Review test expectations, fix logic

---

## Quick Commands

```bash
# Run all tests
pytest tests/ -v

# Run single test
pytest tests/unit/test_bastion_default_behavior.py::TestBastionAutoDetection::test_detect_bastion_in_resource_group_found -v

# Run tests matching pattern
pytest tests/ -k "test_bastion" -v

# Run with coverage
pytest tests/ --cov=azlin --cov-report=html

# Run only failed tests from last run
pytest --lf -v

# Run in parallel (faster)
pytest tests/ -n auto

# Watch mode (re-run on file change)
pytest-watch tests/ -- -v
```

---

## Acceptance Criteria Checklist

After implementation, verify all ACs:

- [ ] **AC1:** Bastion auto-detected in resource group
  - Test: `test_ac1_auto_detect_bastion_in_resource_group`
  - Command: `pytest tests/e2e/test_bastion_default_e2e.py::TestAcceptanceCriteria::test_ac1_auto_detect_bastion_in_resource_group -v`

- [ ] **AC2:** Used automatically with confirmation
  - Test: `test_ac2_use_bastion_automatically_with_confirmation`
  - Verify: Prompt shows, default yes, bastion used

- [ ] **AC3:** Prompt to create (default yes)
  - Test: `test_ac3_prompt_to_create_bastion_default_yes`
  - Verify: Default is yes, cost shown

- [ ] **AC4:** Can decline for public IP
  - Test: `test_ac4_allow_decline_bastion_use_public_ip`
  - Verify: User can say no, public IP created

- [ ] **AC5:** Backward compatible with --use-bastion
  - Test: `test_ac5_backward_compatibility_use_bastion_flag`
  - Verify: Flag works, no breaking changes

---

## Performance Benchmarks

**Expected Performance:**
- Bastion detection: <5 seconds
- VM provisioning: <10 minutes (includes bastion if needed)
- Tunnel creation: <30 seconds
- Config load/save: <100ms

**Test Performance:**
```bash
# Check test execution time
pytest tests/unit/ --durations=10
pytest tests/integration/ --durations=5
pytest tests/e2e/ --durations=3
```

---

## Getting Help

### Test Documentation
- Full spec: `docs/BASTION_DEFAULT_TEST_SPEC.md`
- Security: `docs/BASTION_SECURITY_REQUIREMENTS.md`

### Test Files
- Unit: `tests/unit/test_bastion_default_behavior.py`
- Integration: `tests/integration/test_bastion_default_integration.py`
- E2E: `tests/e2e/test_bastion_default_e2e.py`

### Common Issues
1. **Tests not found:** Check pytest discovery (files must start with `test_`)
2. **Imports fail:** Check PYTHONPATH includes `src/`
3. **Mocks not working:** Verify patch paths match actual import paths
4. **Fixtures missing:** Check fixture scope and names

---

## Success Criteria

**Feature is done when:**
- ✅ All 90 tests pass (100%)
- ✅ Code coverage >90%
- ✅ All 5 ACs validated
- ✅ Security tests pass
- ✅ Performance acceptable
- ✅ Documentation complete
- ✅ Code reviewed

---

## Next Steps

1. **Start with Phase 1:** Bastion detection
2. **Run tests frequently:** `pytest -v`
3. **Follow TDD cycle:** Red → Green → Refactor
4. **Check coverage:** Maintain >90%
5. **Ask for help:** If stuck on a test

---

**Happy TDD! Let the tests guide your implementation.**
