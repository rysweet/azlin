# Bastion Default Feature - Test Specification (TDD)
**Issue:** #237 - Make Bastion Host Usage Default When Creating VMs
**Version:** 1.0
**Date:** 2025-10-31
**Testing Approach:** Test-Driven Development (TDD)

---

## Executive Summary

This document specifies comprehensive test cases for the Bastion Default feature following TDD principles. Tests are written FIRST and will FAIL until implementation is complete. This ensures all requirements are testable and the implementation meets acceptance criteria.

**Testing Pyramid Distribution:**
- Unit Tests: 60% (Fast, isolated, focused)
- Integration Tests: 30% (Module interactions)
- E2E Tests: 10% (Complete workflows)

---

## 1. Feature Requirements

### User Story
> As a developer, I want bastion hosts to be the default when creating VMs, so that my VMs are secure by default without manual configuration.

### Acceptance Criteria
1. **AC1:** Auto-detect bastion in resource group when creating VM
2. **AC2:** Use bastion automatically if exists (after user confirmation)
3. **AC3:** Prompt to create bastion if doesn't exist (default: yes)
4. **AC4:** Allow user to decline and create public IP instead
5. **AC5:** Maintain backward compatibility with `--use-bastion` flag

---

## 2. Test File Organization

### Unit Tests (60%)
**Location:** `tests/unit/test_bastion_default_behavior.py`

**Test Classes:**
- `TestBastionAutoDetection` - Auto-detection logic (15 tests)
- `TestUserPromptBehavior` - User interaction (5 tests)
- `TestVMProvisioningWithBastion` - Provisioning logic (6 tests)
- `TestBastionFlagOverride` - Flag behavior (3 tests)
- `TestBackwardCompatibility` - Compatibility (4 tests)
- `TestConnectionFlowWithBastion` - Connection flow (3 tests)
- `TestErrorHandling` - Error scenarios (6 tests)
- `TestBastionConfigPersistence` - Config storage (3 tests)
- `TestSecurityRequirements` - Security validation (3 tests)
- `TestBoundaryConditions` - Edge cases (4 tests)

**Total Unit Tests:** ~52 tests

### Integration Tests (30%)
**Location:** `tests/integration/test_bastion_default_integration.py`

**Test Classes:**
- `TestBastionDetectionAndProvisioning` - Detection + provisioning (4 tests)
- `TestConnectionWorkflowWithBastion` - Connection workflow (3 tests)
- `TestBastionConfigPersistence` - Config persistence (3 tests)
- `TestCLIIntegration` - CLI commands (3 tests)
- `TestErrorRecoveryAndFallback` - Error handling (3 tests)
- `TestMultiVMScenarios` - Multi-VM scenarios (2 tests)
- `TestVNetPeeringScenarios` - VNet peering (2 tests)

**Total Integration Tests:** ~20 tests

### E2E Tests (10%)
**Location:** `tests/e2e/test_bastion_default_e2e.py`

**Test Classes:**
- `TestAcceptanceCriteria` - AC validation (5 tests)
- `TestUserWorkflows` - Complete workflows (6 tests)
- `TestErrorScenarios` - Error handling (3 tests)
- `TestPerformanceAndScaling` - Performance (2 tests)
- `TestSecurityCompliance` - Security (2 tests)

**Total E2E Tests:** ~18 tests

**Grand Total:** ~90 tests

---

## 3. Detailed Test Specifications

### 3.1 Unit Tests

#### TestBastionAutoDetection

##### test_detect_bastion_in_resource_group_found
**Purpose:** Verify bastion detection when bastion exists
**Priority:** P0 (Critical)
**AC Coverage:** AC1

```python
def test_detect_bastion_in_resource_group_found(self):
    # Arrange
    resource_group = "my-rg"
    mock_bastions = [{"name": "my-bastion", "resourceGroup": "my-rg"}]

    # Act
    with patch.object(BastionDetector, 'list_bastions', return_value=mock_bastions):
        bastion = BastionDetector.detect_bastion_for_vm("test-vm", resource_group)

    # Assert
    assert bastion is not None
    assert bastion["name"] == "my-bastion"
```

**Expected Result:** Bastion is detected and returned
**Failure Mode:** Returns None when bastion exists
**Implementation Hint:** Query Azure API, filter by resource group

##### test_detect_bastion_in_resource_group_not_found
**Purpose:** Verify graceful handling when no bastion exists
**Priority:** P0 (Critical)
**AC Coverage:** AC1

**Expected Result:** Returns None without error
**Failure Mode:** Raises exception or crashes
**Implementation Hint:** Return None for empty list

##### test_detect_bastion_multiple_hosts_uses_first
**Purpose:** Verify behavior with multiple bastions
**Priority:** P1 (High)
**AC Coverage:** AC1

**Expected Result:** Uses first bastion in list
**Failure Mode:** Uses wrong bastion or fails
**Implementation Hint:** Take first element from sorted list

##### test_detect_bastion_ignores_failed_state
**Purpose:** Verify failed bastions are filtered out
**Priority:** P0 (Critical)
**AC Coverage:** AC1

**Expected Result:** Failed bastions are ignored
**Failure Mode:** Attempts to use failed bastion
**Implementation Hint:** Filter by provisioningState == "Succeeded"

##### test_detect_bastion_handles_azure_errors_gracefully
**Purpose:** Verify error handling during detection
**Priority:** P0 (Critical)
**AC Coverage:** AC1

**Expected Result:** Returns None on Azure errors
**Failure Mode:** Crashes or leaks error details
**Implementation Hint:** Try-except with logging

#### TestUserPromptBehavior

##### test_prompt_use_existing_bastion_user_accepts
**Purpose:** Verify user can accept using existing bastion
**Priority:** P0 (Critical)
**AC Coverage:** AC2

**Expected Result:** Returns True, bastion is used
**Failure Mode:** Prompt not shown or ignored
**Implementation Hint:** Use click.confirm()

##### test_prompt_create_bastion_default_yes
**Purpose:** Verify default is 'yes' for creating bastion
**Priority:** P0 (Critical)
**AC Coverage:** AC3

**Expected Result:** Default=True in confirm prompt
**Failure Mode:** Default is False or no default
**Implementation Hint:** click.confirm(default=True)

##### test_prompt_includes_cost_information
**Purpose:** Verify cost info is shown to user
**Priority:** P1 (High)
**AC Coverage:** AC3

**Expected Result:** Prompt mentions ~$140/month cost
**Failure Mode:** No cost information shown
**Implementation Hint:** Include cost in prompt message

#### TestVMProvisioningWithBastion

##### test_provision_vm_with_bastion_no_public_ip
**Purpose:** Verify VM with bastion has no public IP
**Priority:** P0 (Critical)
**AC Coverage:** AC2

**Expected Result:** Public IP creation skipped
**Failure Mode:** Public IP is created
**Implementation Hint:** Omit --public-ip-address flag

##### test_provision_vm_without_bastion_has_public_ip
**Purpose:** Verify VM without bastion gets public IP
**Priority:** P0 (Critical)
**AC Coverage:** AC4

**Expected Result:** Public IP is created
**Failure Mode:** No public IP, VM unreachable
**Implementation Hint:** Include --public-ip-address flag

##### test_provision_vm_bastion_auto_detect_success
**Purpose:** Verify auto-detection during provisioning
**Priority:** P0 (Critical)
**AC Coverage:** AC1, AC2

**Expected Result:** Bastion detected, user prompted, used
**Failure Mode:** No detection or no prompt
**Implementation Hint:** Call BastionDetector before provision

#### TestBastionFlagOverride

##### test_no_bastion_flag_skips_detection
**Purpose:** Verify --no-bastion skips all detection
**Priority:** P0 (Critical)
**AC Coverage:** AC4

**Expected Result:** No detection calls made
**Failure Mode:** Detection runs despite flag
**Implementation Hint:** Check flag before detection

##### test_no_bastion_flag_forces_public_ip
**Purpose:** Verify --no-bastion forces public IP
**Priority:** P0 (Critical)
**AC Coverage:** AC4

**Expected Result:** Public IP created regardless of bastion
**Failure Mode:** Bastion used despite flag
**Implementation Hint:** Override all bastion logic with flag

#### TestBackwardCompatibility

##### test_use_bastion_flag_forces_bastion_usage
**Purpose:** Verify --use-bastion still works
**Priority:** P0 (Critical)
**AC Coverage:** AC5

**Expected Result:** Bastion used without prompt
**Failure Mode:** Prompt shown or bastion not used
**Implementation Hint:** Skip prompts when flag set

##### test_use_bastion_and_no_bastion_conflict
**Purpose:** Verify conflicting flags are rejected
**Priority:** P1 (High)
**AC Coverage:** AC5

**Expected Result:** ValueError raised
**Failure Mode:** One flag silently ignored
**Implementation Hint:** Validate flags in __init__

---

### 3.2 Integration Tests

#### TestBastionDetectionAndProvisioning

##### test_provision_vm_detects_bastion_and_prompts_user
**Purpose:** Test complete detection and provision flow
**Priority:** P0 (Critical)
**AC Coverage:** AC1, AC2

**Test Flow:**
1. BastionDetector queries Azure
2. Bastion found in RG
3. User prompted via click.confirm
4. User accepts
5. VM provisioned without public IP
6. Bastion mapping saved to config

**Expected Result:** Complete flow succeeds
**Failure Mode:** Any step fails or skipped
**Mock Points:** Azure API, user input, subprocess

##### test_provision_vm_no_bastion_prompts_create
**Purpose:** Test bastion creation prompt flow
**Priority:** P0 (Critical)
**AC Coverage:** AC1, AC3

**Test Flow:**
1. BastionDetector finds no bastion
2. User prompted to create
3. User accepts (default yes)
4. Bastion creation initiated
5. VM provisioned after bastion ready

**Expected Result:** Bastion created, VM uses it
**Failure Mode:** No prompt or creation fails

#### TestConnectionWorkflowWithBastion

##### test_connect_to_vm_uses_saved_bastion_mapping
**Purpose:** Test saved config is used for connections
**Priority:** P1 (High)
**AC Coverage:** AC2

**Test Flow:**
1. Config has VM -> Bastion mapping
2. User connects to VM
3. BastionManager creates tunnel
4. SSH connection via tunnel
5. No user prompt (mapping exists)

**Expected Result:** Automatic connection via bastion
**Failure Mode:** Prompt shown or direct connection

---

### 3.3 E2E Tests

#### TestAcceptanceCriteria

##### test_ac1_auto_detect_bastion_in_resource_group
**Purpose:** Validate AC1 end-to-end
**Priority:** P0 (Critical)
**AC Coverage:** AC1

**User Scenario:**
```bash
# Resource group has bastion
azlin create my-vm --resource-group my-rg

# Expected:
# Detecting Bastion hosts in my-rg...
# Found: my-bastion
# Use this Bastion? (Y/n): [user accepts]
# Provisioning VM without public IP...
```

**Test Steps:**
1. Ensure RG has bastion (setup)
2. Run azlin create command
3. Verify detection message
4. Verify prompt shown
5. Accept prompt
6. Verify VM created
7. Verify no public IP

**Pass Criteria:** All steps succeed, VM uses bastion

##### test_ac2_use_bastion_automatically_with_confirmation
**Purpose:** Validate AC2 end-to-end
**Priority:** P0 (Critical)
**AC Coverage:** AC2

**User Scenario:**
```bash
azlin create my-vm --resource-group my-rg

# Prompt: "Found Bastion 'my-bastion'. Use it? (Y/n)"
# User: Y
# VM created without public IP
```

**Pass Criteria:** Prompt shown, default is yes, VM uses bastion

##### test_ac3_prompt_to_create_bastion_default_yes
**Purpose:** Validate AC3 end-to-end
**Priority:** P0 (Critical)
**AC Coverage:** AC3

**User Scenario:**
```bash
azlin create my-vm --resource-group new-rg

# Prompt: "No Bastion found. Create one? (Y/n) [~$140/month]"
# Default: Y
# User: [press enter]
# Creating Bastion... (10 minutes)
# VM created without public IP
```

**Pass Criteria:** Prompt shows cost, default yes, bastion created

##### test_ac4_allow_decline_bastion_use_public_ip
**Purpose:** Validate AC4 end-to-end
**Priority:** P0 (Critical)
**AC Coverage:** AC4

**User Scenario:**
```bash
azlin create my-vm --resource-group my-rg

# Prompt: "Found Bastion. Use it? (Y/n)"
# User: n
# Creating VM with public IP...
# VM accessible at: 20.1.2.3
```

**Pass Criteria:** User can decline, public IP created

##### test_ac5_backward_compatibility_use_bastion_flag
**Purpose:** Validate AC5 end-to-end
**Priority:** P0 (Critical)
**AC Coverage:** AC5

**User Scenario:**
```bash
azlin connect my-vm --use-bastion

# No prompt (explicit flag)
# Creating Bastion tunnel...
# Connected to my-vm via Bastion
```

**Pass Criteria:** Flag works, no breaking changes

#### TestUserWorkflows

##### test_workflow_create_first_vm_with_bastion
**Purpose:** Test complete first-time user workflow
**Priority:** P0 (Critical)
**AC Coverage:** All

**Workflow:**
1. New user, new resource group
2. No bastion exists
3. Prompted to create (accepts)
4. Bastion created (~10 min)
5. VM created without public IP
6. Connection via bastion works
7. Config saved for future use

**Pass Criteria:** Smooth workflow, all steps succeed

---

## 4. Test Execution Strategy

### 4.1 Running Tests

#### Run All Tests
```bash
pytest tests/ -v
```

#### Run Unit Tests Only
```bash
pytest tests/unit/test_bastion_default_behavior.py -v
```

#### Run Integration Tests
```bash
pytest tests/integration/test_bastion_default_integration.py -v
```

#### Run E2E Tests (Mocked)
```bash
pytest tests/e2e/test_bastion_default_e2e.py -v
```

#### Run E2E Tests (Real Azure)
```bash
export RUN_E2E_TESTS=true
export AZLIN_E2E_RG=azlin-bastion-e2e
export AZLIN_E2E_LOCATION=westus2
pytest tests/e2e/test_bastion_default_e2e.py -v -m e2e
```

### 4.2 Coverage Requirements

**Minimum Coverage:** 90% for all critical paths

**Critical Paths:**
- Bastion detection logic
- User prompt handling
- VM provisioning with/without bastion
- Flag override behavior
- Config persistence
- Error handling

**Coverage Command:**
```bash
pytest --cov=azlin.modules.bastion_detector \
       --cov=azlin.vm_provisioning \
       --cov=azlin.vm_connector \
       --cov-report=html \
       --cov-report=term-missing
```

### 4.3 TDD Workflow

**Red-Green-Refactor Cycle:**

1. **Red:** Write failing test
   ```bash
   pytest tests/unit/test_bastion_default_behavior.py::TestBastionAutoDetection::test_detect_bastion_in_resource_group_found -v
   # FAILED - Function not implemented
   ```

2. **Green:** Implement minimal code to pass
   ```python
   # azlin/modules/bastion_detector.py
   def detect_bastion_for_vm(vm_name, resource_group):
       bastions = list_bastions(resource_group)
       if bastions:
           return {"name": bastions[0]["name"], "resource_group": resource_group}
       return None
   ```

3. **Refactor:** Improve code quality
   ```python
   def detect_bastion_for_vm(vm_name, resource_group):
       """Detect bastion with error handling and logging."""
       try:
           bastions = list_bastions(resource_group)
           active_bastions = [b for b in bastions if b.get("provisioningState") == "Succeeded"]
           if active_bastions:
               logger.info(f"Detected bastion: {active_bastions[0]['name']}")
               return {"name": active_bastions[0]["name"], "resource_group": resource_group}
           return None
       except Exception as e:
           logger.debug(f"Bastion detection failed: {e}")
           return None
   ```

4. **Repeat:** Next test in the suite

---

## 5. Test Data Requirements

### 5.1 Mock Data

**Bastion Response:**
```json
{
  "name": "test-bastion",
  "resourceGroup": "test-rg",
  "location": "westus2",
  "provisioningState": "Succeeded",
  "sku": {"name": "Standard"},
  "ipConfigurations": [{
    "subnet": {"id": "/subscriptions/.../AzureBastionSubnet"}
  }]
}
```

**VM Response:**
```json
{
  "name": "test-vm",
  "resourceGroup": "test-rg",
  "location": "westus2",
  "powerState": "VM running",
  "privateIps": "10.0.0.4",
  "publicIps": null
}
```

### 5.2 Test Fixtures

**Provided Fixtures:**
- `mock_azure_resources` - Azure API responses
- `temp_config_dir` - Temporary config directory
- `test_env` - Test environment variables
- `skip_e2e` - Skip E2E unless enabled

---

## 6. Security Testing Requirements

### 6.1 Security Tests

All security tests from `BASTION_SECURITY_REQUIREMENTS.md` must pass:

1. **REQ-CONFIG-001:** No secrets in config
   - Test: `test_no_bastion_credentials_stored`
   - Verify: Config contains only names, no tokens

2. **REQ-CONFIG-002:** Config file permissions
   - Test: `test_bastion_config_file_permissions`
   - Verify: Files are 0600 (owner read/write only)

3. **REQ-CONFIG-005:** Bastion name validation
   - Test: `test_bastion_name_validation_injection_prevention`
   - Verify: Injection attempts are rejected

### 6.2 Penetration Testing Scenarios

**Test Cases:**
- Command injection via bastion name
- Path traversal via config file
- Credential leakage in error messages
- Tunnel hijacking attempts

---

## 7. Performance Testing

### 7.1 Performance Criteria

**Bastion Detection:** <5 seconds
**VM Provisioning:** <10 minutes (with bastion)
**Tunnel Creation:** <30 seconds
**Config Load/Save:** <100ms

### 7.2 Performance Tests

```python
def test_bastion_detection_performance():
    start = time.time()
    BastionDetector.detect_bastion_for_vm("test-vm", "test-rg")
    duration = time.time() - start
    assert duration < 5.0, f"Detection took {duration}s, expected <5s"
```

---

## 8. Test Maintenance

### 8.1 Test Review Schedule

- **Weekly:** Review failing tests
- **Per PR:** All tests must pass
- **Monthly:** Review test coverage
- **Quarterly:** Update test data

### 8.2 Test Debt Tracking

**Test Debt Items:**
- [ ] Real Azure E2E tests (currently mocked)
- [ ] VNet peering validation tests
- [ ] Bastion SKU compatibility tests
- [ ] Multi-region bastion tests
- [ ] Cost estimation tests

---

## 9. Implementation Checklist

### 9.1 Before Starting Implementation

- [x] All test files created
- [x] Test specification reviewed
- [x] Mock data prepared
- [x] Fixtures implemented
- [ ] Security requirements understood

### 9.2 Implementation Order

**Phase 1: Detection (Week 1)**
- [ ] Implement `BastionDetector.detect_bastion_for_vm()`
- [ ] Run: `pytest tests/unit/test_bastion_default_behavior.py::TestBastionAutoDetection -v`
- [ ] All detection tests should pass

**Phase 2: Prompts (Week 1)**
- [ ] Implement user prompt logic
- [ ] Run: `pytest tests/unit/test_bastion_default_behavior.py::TestUserPromptBehavior -v`
- [ ] All prompt tests should pass

**Phase 3: Provisioning (Week 2)**
- [ ] Modify `VMProvisioner` to integrate bastion
- [ ] Run: `pytest tests/unit/test_bastion_default_behavior.py::TestVMProvisioningWithBastion -v`
- [ ] All provisioning tests should pass

**Phase 4: Integration (Week 2)**
- [ ] Integrate all modules
- [ ] Run: `pytest tests/integration/test_bastion_default_integration.py -v`
- [ ] All integration tests should pass

**Phase 5: E2E (Week 3)**
- [ ] Complete end-to-end flows
- [ ] Run: `pytest tests/e2e/test_bastion_default_e2e.py -v`
- [ ] All E2E tests should pass

**Phase 6: Security (Week 3)**
- [ ] Security review and testing
- [ ] Run: `pytest tests/ -v -k security`
- [ ] All security tests should pass

---

## 10. Success Metrics

### 10.1 Test Metrics

**Target Metrics:**
- Test Coverage: >90%
- Test Pass Rate: 100%
- Test Execution Time: <5 minutes (unit + integration)
- E2E Execution Time: <20 minutes (with mocks)

### 10.2 Definition of Done

**Feature is complete when:**
- [x] All tests written (TDD approach)
- [ ] All unit tests pass (100%)
- [ ] All integration tests pass (100%)
- [ ] All E2E tests pass (100%)
- [ ] Code coverage >90%
- [ ] Security tests pass (100%)
- [ ] Performance criteria met
- [ ] Documentation updated
- [ ] Code reviewed and approved

---

## 11. References

**Related Documents:**
- [BASTION_SECURITY_REQUIREMENTS.md](./BASTION_SECURITY_REQUIREMENTS.md)
- [BASTION_SECURITY_TESTING.md](./BASTION_SECURITY_TESTING.md)
- Issue #237: Make Bastion Host Usage Default

**Test Files:**
- Unit Tests: `tests/unit/test_bastion_default_behavior.py`
- Integration Tests: `tests/integration/test_bastion_default_integration.py`
- E2E Tests: `tests/e2e/test_bastion_default_e2e.py`

**Testing Resources:**
- [pytest Documentation](https://docs.pytest.org/)
- [Testing Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html)
- [TDD Best Practices](https://www.agilealliance.org/glossary/tdd/)

---

**Document Status:** READY FOR IMPLEMENTATION
**Next Action:** Begin Phase 1 - Detection Implementation
**Estimated Completion:** 3 weeks from start date

---

**END OF TEST SPECIFICATION**
