# Local Testing Plan - Issue #281 Bastion Routing Fix

## Test Status: ⚠️ PARTIAL - Requires Azure Infrastructure

This document outlines the mandatory local testing required before committing changes per workflow Step 8.

## ✅ Tests Completed (Without Azure Infrastructure)

### 1. Import and Structure Tests
- ✅ All modules import successfully
- ✅ `SSHRoutingResolver` class structure validated
- ✅ `SSHRoute` dataclass has all required fields
- ✅ `get_ssh_configs_for_vms` helper function exists
- ✅ CLI integration points verified (3 commands updated)

### 2. Static Analysis
- ✅ Ruff linting passed
- ✅ Python syntax validation passed
- ✅ Type hints correct (BastionInfo properly imported)
- ✅ No dead code or placeholders

## ⚠️ Tests Requiring Azure Infrastructure (Cannot Run Locally)

### Required Test Scenarios

#### Simple Use Cases (Basic Functionality)
1. **VM with Public IP Only**
   ```bash
   azlin w --rg test-rg
   azlin top --rg test-rg
   azlin ps --rg test-rg
   ```
   - **Expected**: Commands work exactly as before (backwards compatibility)
   - **Verifies**: No regression in existing functionality

2. **VM with Bastion Only (No Public IP)**
   ```bash
   azlin w --rg test-rg  # VM only has private IP + bastion
   ```
   - **Expected**:
     - Detects bastion automatically
     - Creates tunnel to 127.0.0.1:local_port
     - Executes command successfully
     - Shows routing summary
   - **Verifies**: Core fix works

#### Complex Use Cases (Edge Cases)
3. **Mixed Environment**
   - 2 VMs with public IPs
   - 1 VM with only bastion
   - 1 VM with no connectivity
   ```bash
   azlin w --rg test-rg
   ```
   - **Expected**:
     - Summary shows: "3 reachable (2 direct, 1 via bastion), 1 unreachable"
     - Lists unreachable VM with reason
     - Executes on 3 VMs successfully

4. **User Declines Bastion**
   - VM with only private IP
   - User answers "no" to bastion prompt
   ```bash
   azlin w --rg test-rg
   ```
   - **Expected**: VM skipped with message "User declined bastion connection"

5. **Bastion Tunnel Failure**
   - VM with private IP
   - Bastion exists but tunnel creation fails
   - **Expected**: VM skipped with clear error message

#### Integration Points
6. **Bastion Detection**
   - Verify `BastionDetector.detect_bastion_for_vm()` called correctly
   - Check correct bastion selected (same region/resource group)

7. **Tunnel Lifecycle**
   - Verify tunnel created with correct ports
   - Confirm tunnels cleaned up via atexit on command completion
   - Check no lingering processes

8. **Long-Running Commands**
   ```bash
   azlin top --rg test-rg -i 5  # Run for 30+ seconds
   ```
   - **Expected**: Bastion tunnel remains stable throughout

#### Regression Testing
9. **Direct IP Connection Still Works**
   ```bash
   azlin connect 20.1.2.3  # Direct IP
   ```
   - **Expected**: No change in behavior

10. **Error Handling**
    - Non-existent resource group
    - VMs in stopped state
    - Network connectivity issues
    - **Expected**: Clear, user-friendly error messages

## 📋 Manual Testing Checklist

When Azure infrastructure is available, test:

- [ ] `azlin w` with public-only VM
- [ ] `azlin w` with bastion-only VM
- [ ] `azlin w` with mixed VMs
- [ ] `azlin top` with bastion VM (30+ second run)
- [ ] `azlin ps` with bastion VM
- [ ] User declines bastion prompt
- [ ] VM with no connectivity (no public IP, no bastion)
- [ ] Multiple commands in sequence (tunnel reuse)
- [ ] Verify no regressions in `azlin connect`
- [ ] Check tunnel cleanup (no lingering az processes)

## 🎯 Acceptance Criteria

All tests must pass before merge:
- ✅ No Python errors or exceptions
- ✅ Commands complete successfully
- ✅ Bastion tunnels work correctly
- ✅ No regression in existing functionality
- ✅ Clear error messages for failures
- ✅ Proper cleanup of resources

## 🚨 Testing Limitations

**Cannot fully test without**:
- Active Azure subscription
- Resource group with VMs
- At least one VM with only private IP
- Azure Bastion deployed in same VNet

**Recommendation**:
- CI will run integration tests
- Manual testing required before production use
- Consider creating test Azure environment

## ✅ What We CAN Confirm Locally

1. **Code Quality**: ✅ Passed
   - Imports work
   - No syntax errors
   - Linting passed
   - Type hints correct

2. **Structure**: ✅ Validated
   - CLI integration correct
   - Helper function signature matches usage
   - Dataclasses properly defined

3. **Logic Flow**: ✅ Reviewed
   - Routing resolution logic sound
   - Error handling comprehensive
   - Backwards compatibility preserved

## Next Steps

1. ✅ Document test plan (this file)
2. ⏭️ Commit changes with note about testing requirements
3. ⏭️ Create PR with test plan
4. ⏭️ Add comment about manual testing needed
5. ⏭️ Let CI run automated tests
6. ⏭️ Perform manual testing with real Azure infrastructure
